"""Lightweight additive schema migrator.

Runs at startup before `create_all`: brings existing databases forward
without data loss (new columns via ALTER TABLE ADD COLUMN, plus the one
structural change — app_settings gaining a surrogate PK + workspace scope).

Deliberately additive-only: destructive changes require an explicit
migration script. For long-lived production deployments Alembic remains the
recommended tool; this keeps demo/dev databases seamlessly upgradable.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.models import DEFAULT_WORKSPACE_ID

logger = logging.getLogger(__name__)

# table -> {column: DDL type/default}. Only columns added after v1.0.0.
ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "users": {"workspace_id": f"INTEGER DEFAULT {DEFAULT_WORKSPACE_ID}"},
    "leads": {
        "workspace_id": f"INTEGER DEFAULT {DEFAULT_WORKSPACE_ID}",
        "priority": "VARCHAR(20) DEFAULT 'Medium'",
        "tags": "JSON DEFAULT '[]'",
        "follow_up_at": "TIMESTAMP",
    },
    "conversations": {
        "workspace_id": f"INTEGER DEFAULT {DEFAULT_WORKSPACE_ID}",
        "last_node": "VARCHAR(120) DEFAULT ''",
    },
    "messages": {"meta": "JSON DEFAULT '{}'"},
    "workflows": {
        "workspace_id": f"INTEGER DEFAULT {DEFAULT_WORKSPACE_ID}",
        "prompt_name": "VARCHAR(120) DEFAULT ''",
    },
    "kb_articles": {"workspace_id": f"INTEGER DEFAULT {DEFAULT_WORKSPACE_ID}"},
}


def _existing_columns(engine: Engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def migrate(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        # 1. app_settings: v1 used `key` as the primary key with no workspace
        #    column. Rebuild it as (id PK, workspace_id, key, value).
        if "app_settings" in tables and "workspace_id" not in _existing_columns(engine, "app_settings"):
            logger.info("Migrating app_settings to workspace-scoped schema")
            conn.execute(text("ALTER TABLE app_settings RENAME TO app_settings_legacy"))
            tables.discard("app_settings")

        # 2. Additive columns on existing tables.
        for table, columns in ADDITIVE_COLUMNS.items():
            if table not in tables:
                continue
            existing = _existing_columns(engine, table)
            for column, ddl in columns.items():
                if column not in existing:
                    logger.info("Adding column %s.%s", table, column)
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def post_create(engine: Engine) -> None:
    """Steps that need the new tables to exist (runs after create_all)."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        if "workspaces" in tables:
            existing = conn.execute(
                text("SELECT id FROM workspaces WHERE id = :id"), {"id": DEFAULT_WORKSPACE_ID}
            ).first()
            if existing is None:
                conn.execute(
                    text(
                        "INSERT INTO workspaces (id, name, slug, created_at) "
                        "VALUES (:id, 'Default Workspace', 'default', CURRENT_TIMESTAMP)"
                    ),
                    {"id": DEFAULT_WORKSPACE_ID},
                )
                logger.info("Created default workspace")

        if "app_settings_legacy" in tables:
            conn.execute(
                text(
                    "INSERT INTO app_settings (workspace_id, key, value) "
                    f"SELECT {DEFAULT_WORKSPACE_ID}, key, value FROM app_settings_legacy"
                )
            )
            conn.execute(text("DROP TABLE app_settings_legacy"))
            logger.info("Copied legacy settings into default workspace")

        # Backfill any NULL workspace ids left by ALTER TABLE on old rows.
        for table in ("users", "leads", "conversations", "workflows", "kb_articles"):
            if table in tables and "workspace_id" in _existing_columns(engine, table):
                conn.execute(
                    text(
                        f"UPDATE {table} SET workspace_id = {DEFAULT_WORKSPACE_ID} "
                        "WHERE workspace_id IS NULL"
                    )
                )
