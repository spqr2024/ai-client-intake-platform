"""The additive migrator's upgrade path.

The risk these cover is silent divergence: a fresh database and an upgraded one
must end up with the same schema. Anything that only `create_all` produces —
indexes especially — is invisible on a developer's clean database and missing
on every real deployment.
"""

import sqlalchemy as sa

from app import db_migrate


def _indexes(engine, table: str) -> set[str]:
    return {idx["name"] for idx in sa.inspect(engine).get_indexes(table)}


def test_missing_indexes_are_created_on_an_existing_table(tmp_path):
    """Regression: `external_ref` is declared index=True, but it reaches an
    existing database through ALTER TABLE ADD COLUMN, which cannot carry an
    index — and `create_all` only builds indexes for tables it creates. The
    column ended up indexed on fresh installs and unindexed on upgraded ones,
    turning a per-message lookup into a scan.
    """
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.sqlite3'}")

    # A table that exists but predates the indexed column.
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE conversations (id VARCHAR(32) PRIMARY KEY)"))

    assert "ix_conversations_external_ref" not in _indexes(engine, "conversations")

    from app.db import Base

    db_migrate.migrate(engine)
    Base.metadata.create_all(bind=engine)
    db_migrate.post_create(engine)

    assert "ix_conversations_external_ref" in _indexes(engine, "conversations")


def test_ensure_indexes_is_idempotent(tmp_path):
    """It runs on every boot, so a second pass must not fail on an existing
    index."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'repeat.sqlite3'}")

    from app.db import Base

    Base.metadata.create_all(bind=engine)
    before = _indexes(engine, "leads")

    for _ in range(3):
        db_migrate.ensure_indexes(engine)

    assert _indexes(engine, "leads") == before


def test_a_fresh_database_and_an_upgraded_one_agree(tmp_path):
    """The property that matters: upgrading must not leave you with a
    different schema from a clean install."""
    from app.db import Base

    fresh = sa.create_engine(f"sqlite:///{tmp_path / 'fresh.sqlite3'}")
    Base.metadata.create_all(bind=fresh)
    db_migrate.post_create(fresh)

    upgraded = sa.create_engine(f"sqlite:///{tmp_path / 'upgraded.sqlite3'}")
    # Stand in for the previous release: every column except the ones the
    # migrator is responsible for adding, and none of the indexes that only
    # create_all would have built. Deriving it from the live model rather than
    # hand-writing DDL keeps this honest as the schema grows — the migrator
    # only claims to add what ADDITIVE_COLUMNS lists.
    leads = Base.metadata.tables["leads"]
    added_since = set(db_migrate.ADDITIVE_COLUMNS["leads"])
    old_columns = [c.copy() for c in leads.columns if c.name not in added_since]
    old_leads = sa.Table("leads", sa.MetaData(), *old_columns)
    old_leads.create(bind=upgraded)

    db_migrate.migrate(upgraded)
    Base.metadata.create_all(bind=upgraded)
    db_migrate.post_create(upgraded)

    fresh_cols = {c["name"] for c in sa.inspect(fresh).get_columns("leads")}
    upgraded_cols = {c["name"] for c in sa.inspect(upgraded).get_columns("leads")}
    assert fresh_cols - upgraded_cols == set(), "upgraded database is missing columns"

    assert _indexes(fresh, "leads") - _indexes(upgraded, "leads") == set(), (
        "upgraded database is missing indexes a fresh one has"
    )
