"""The migration chain is the schema Render actually gets — check it directly.

The rest of the suite builds its schema with db.create_all() from the models,
which means the migrations are exercised by nothing. That is how a second head
reached production, and how three columns came to exist in the database but on
no model. These tests close that gap.

Postgres, not SQLite, because production is Postgres and the differences are
exactly what we are trying to catch: SQLite has no real NOT NULL enforcement
story for ALTER, and its type affinity hides column-type drift.
"""

import ast
import glob
import os
import re
import tempfile

import pytest

from app import create_app
from app.extensions import db


# ---------------------------------------------------------------------------
# The revision graph — pure, no database needed
# ---------------------------------------------------------------------------


def _revision_graph() -> dict[str, tuple[str, ...]]:
    """Map every revision to its parents, read straight from the files."""
    graph = {}
    for path in glob.glob("migrations/versions/*.py"):
        source = open(path).read()
        revision = ast.literal_eval(re.search(r"^revision\s*=\s*(.+)$", source, re.M).group(1))
        down = ast.literal_eval(re.search(r"^down_revision\s*=\s*(.+)$", source, re.M).group(1))
        if down is None:
            parents = ()
        elif isinstance(down, str):
            parents = (down,)
        else:
            parents = tuple(down)
        graph[revision] = parents
    return graph


class TestRevisionGraph:
    def test_exactly_one_head(self):
        """Two heads make `flask db upgrade` fail on deploy, before it touches the DB."""
        graph = _revision_graph()
        parents = {p for ps in graph.values() for p in ps}
        heads = sorted(r for r in graph if r not in parents)
        assert len(heads) == 1, f"expected one head, found {heads} — add a merge revision"

    def test_exactly_one_base(self):
        graph = _revision_graph()
        bases = sorted(r for r, parents in graph.items() if not parents)
        assert len(bases) == 1, f"expected one base, found {bases}"

    def test_no_dangling_parents(self):
        graph = _revision_graph()
        parents = {p for ps in graph.values() for p in ps}
        missing = sorted(parents - set(graph))
        assert not missing, f"revisions reference missing parents: {missing}"


# ---------------------------------------------------------------------------
# The chain against a real Postgres
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_url():
    """A throwaway Postgres to migrate.

    CI provides one via TEST_DATABASE_URL (a service container). Locally we
    start one with pgserver, which ships real Postgres binaries as a wheel and
    so needs neither Docker nor a system install. With neither available these
    tests skip — they must never quietly fall back to SQLite, because the
    engine is the whole point.
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        yield url
        return

    pgserver = pytest.importorskip(
        "pgserver",
        reason="set TEST_DATABASE_URL, or `pip install -r requirements-dev.txt` for pgserver",
    )
    with tempfile.TemporaryDirectory() as data_dir:
        server = pgserver.get_server(data_dir)
        try:
            yield server.get_uri()
        finally:
            server.cleanup()


@pytest.fixture(scope="session")
def migrated_database(postgres_url):
    """Run the whole migration chain from base to head, once."""
    from alembic import command
    from alembic.config import Config

    # create_app() reads the URI off the config class and hands it to
    # db.init_app(), which builds the engine there and then — so the class
    # attribute has to be set before the factory runs, not after.
    import app.config as app_config

    original_uri = app_config.DevelopmentConfig.SQLALCHEMY_DATABASE_URI
    app_config.DevelopmentConfig.SQLALCHEMY_DATABASE_URI = postgres_url
    try:
        app = create_app("development")
    finally:
        app_config.DevelopmentConfig.SQLALCHEMY_DATABASE_URI = original_uri

    with app.app_context():
        assert db.engine.dialect.name == "postgresql", (
            f"migration tests must run on Postgres, got {db.engine.dialect.name} — "
            "a SQLite fallback would pass while hiding exactly the drift we check for"
        )
        config = Config("migrations/alembic.ini")
        config.set_main_option("script_location", "migrations")
        command.upgrade(config, "head")
        yield app


class TestMigrationChain:
    def test_chain_applies_from_base_to_head(self, migrated_database):
        """A clean database migrates all the way up without error."""
        with migrated_database.app_context():
            from sqlalchemy import inspect

            tables = set(inspect(db.engine).get_table_names())
        assert {"advertisers", "campaigns", "ad_runs", "api_keys", "admin_users"} <= tables

    def test_migrated_schema_matches_the_models(self, migrated_database):
        """The models and the migrations must describe the same database.

        Alembic's own autogenerate diff, so anything it would write a migration
        for is caught here: added or removed tables and columns, changed types,
        changed nullability, added or dropped indexes and constraints.
        """
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext

        with migrated_database.app_context():
            with db.engine.connect() as connection:
                context = MigrationContext.configure(connection)
                diff = compare_metadata(context, db.metadata)

        assert diff == [], (
            "models and migrations have drifted — "
            f"alembic would generate: {_describe(diff)}"
        )


def _describe(diff) -> str:
    """Render an alembic diff as something a human can act on."""
    out = []
    for entry in diff:
        # Nested lists are per-column modifications; flat tuples are add/remove.
        for item in entry if isinstance(entry, list) else [entry]:
            operation = item[0]
            if operation in ("add_column", "remove_column"):
                out.append(f"{operation} {item[2]}.{item[3].name}")
            elif operation in ("add_table", "remove_table"):
                out.append(f"{operation} {item[1].name}")
            elif operation.startswith("modify_"):
                out.append(f"{operation} {item[2]}.{item[3]} ({item[5]!r} -> {item[6]!r})")
            else:
                out.append(str(operation))
    return "; ".join(out)
