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
        "follow_up_notified_at": "TIMESTAMP",
    },
    "conversations": {
        "workspace_id": f"INTEGER DEFAULT {DEFAULT_WORKSPACE_ID}",
        "last_node": "VARCHAR(120) DEFAULT ''",
        "external_ref": "VARCHAR(120) DEFAULT ''",
    },
    "messages": {"meta": "JSON DEFAULT '{}'"},
    "workflows": {
        "workspace_id": f"INTEGER DEFAULT {DEFAULT_WORKSPACE_ID}",
        "prompt_name": "VARCHAR(120) DEFAULT ''",
    },
    "kb_articles": {
        "workspace_id": f"INTEGER DEFAULT {DEFAULT_WORKSPACE_ID}",
        "source_type": "VARCHAR(20) DEFAULT 'manual'",
        "source_filename": "VARCHAR(255) DEFAULT ''",
        "version": "INTEGER DEFAULT 1",
        "index_status": "VARCHAR(20) DEFAULT 'pending'",
        "index_error": "TEXT DEFAULT ''",
        "indexed_at": "TIMESTAMP",
        "chunk_count": "INTEGER DEFAULT 0",
        "doc_metadata": "JSON DEFAULT '{}'",
        "hit_count": "INTEGER DEFAULT 0",
    },
    "kb_embeddings": {"chunk_id": "INTEGER"},
}

# Tables replaced by a new schema; dropped after their data is migrated (or
# when they were never used).
OBSOLETE_TABLES = ("provider_configs",)


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

        # 3. v2.0 stored one embedding per article; v2.1 embeds chunks. The old
        #    rows have no chunk_id and would never match a search, so clear them
        #    and let the reindex-on-write path rebuild.
        if "kb_embeddings" in tables and "chunk_id" in _existing_columns(engine, "kb_embeddings"):
            conn.execute(text("DELETE FROM kb_embeddings WHERE chunk_id IS NULL"))

        # 4. Drop tables that no longer back any model.
        for table in OBSOLETE_TABLES:
            if table in tables:
                logger.info("Dropping obsolete table %s", table)
                conn.execute(text(f"DROP TABLE {table}"))


def enforce_sqlite_foreign_keys(engine: Engine) -> None:
    """SQLite ignores FOREIGN KEY clauses unless the pragma is enabled per
    connection. Without this the ON DELETE rules declared on the models are
    silently inert on the default development database."""
    if not engine.url.get_backend_name().startswith("sqlite"):
        return

    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def ensure_indexes(engine: Engine) -> None:
    """Create declared indexes that are missing from an existing table.

    `create_all` only creates missing *tables*; it never adds an index to a
    table that already exists. Combined with ADDITIVE_COLUMNS — which uses
    ALTER TABLE ADD COLUMN, and so cannot carry an index — a column declared
    `index=True` ends up indexed on a fresh database and unindexed on every
    upgraded one. The scan that results is invisible until the table is large.
    """
    from app.db import Base

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all will build it, indexes included
        # get_indexes() omits indexes that back a UNIQUE constraint, so consult
        # the unique constraints too — otherwise those are "missing" on every
        # boot and re-created into an error.
        present = {idx["name"] for idx in inspector.get_indexes(table.name)}
        present |= {uc.get("name") for uc in inspector.get_unique_constraints(table.name)}

        for index in table.indexes:
            if index.name in present:
                continue
            try:
                index.create(bind=engine)
                logger.info("Created missing index %s on %s", index.name, table.name)
            except Exception as exc:  # pragma: no cover - defensive
                # A missing index is a performance problem, never a reason to
                # refuse to start.
                logger.warning("Could not create index %s on %s: %s", index.name, table.name, exc)


def post_create(engine: Engine) -> None:
    """Steps that need the new tables to exist (runs after create_all)."""
    ensure_indexes(engine)

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

        # Demo seeding up to v2.2.0 wrote the placeholder "sales@example.com"
        # into staff_notification_email on every boot. A stored value outranks
        # the env default, so those rows keep hijacking lead alerts long after
        # STAFF_NOTIFICATION_EMAIL is configured. Clear the placeholder only —
        # an empty value falls through to env / the admin UI. Any address an
        # operator actually chose is left untouched.
        if "app_settings" in tables:
            result = conn.execute(
                text(
                    "UPDATE app_settings SET value = '' "
                    "WHERE key = 'staff_notification_email' AND value = :placeholder"
                ),
                {"placeholder": "sales@example.com"},
            )
            if result.rowcount:
                logger.info(
                    "Cleared %s placeholder staff_notification_email row(s); "
                    "resolving from STAFF_NOTIFICATION_EMAIL instead",
                    result.rowcount,
                )

        # Backfill any NULL workspace ids left by ALTER TABLE on old rows.
        for table in ("users", "leads", "conversations", "workflows", "kb_articles"):
            if table in tables and "workspace_id" in _existing_columns(engine, table):
                conn.execute(
                    text(
                        f"UPDATE {table} SET workspace_id = {DEFAULT_WORKSPACE_ID} WHERE workspace_id IS NULL"
                    )
                )
