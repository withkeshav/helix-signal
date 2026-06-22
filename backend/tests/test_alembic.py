"""Smoke tests for Alembic migration round-trips.

Creates a temporary SQLite database, runs the full migration chain
up and down, then cleans up.  Does NOT use the ``client`` fixture
(in-memory DB) to avoid interference.
"""
import os
import tempfile
from pathlib import Path

import pytest
from alembic.config import Config
from alembic import command


_ALEMBIC_CFG_PATH = str(Path(__file__).resolve().parent.parent / "alembic.ini")


def _alembic(cfg: Config, *args, **kwargs):
    """Helper to run an Alembic command with the test DB URL injected."""
    os.environ["DATABASE_URL"] = cfg.get_main_option("sqlalchemy.url")
    return command.upgrade(cfg, *args, **kwargs)


@pytest.fixture()
def alembic_cfg():
    """Yield an Alembic Config pointed at a temporary SQLite database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    cfg = Config(_ALEMBIC_CFG_PATH)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    try:
        yield cfg
    finally:
        os.unlink(path)


class TestAlembicMigrations:
    """Verify all Alembic migrations can upgrade and round-trip."""

    def test_upgrade_head(self, alembic_cfg):
        """Apply all migrations to a fresh database."""
        command.upgrade(alembic_cfg, "head")
        # If we got here without an exception, all revisions applied.
        assert True

    @pytest.mark.slow
    def test_full_round_trip(self, alembic_cfg):
        """Upgrade to head, downgrade to base, then back to head."""
        command.upgrade(alembic_cfg, "head")
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")

    def test_idempotent_upgrade(self, alembic_cfg):
        """Running upgrade head twice should be a no-op."""
        command.upgrade(alembic_cfg, "head")
        command.upgrade(alembic_cfg, "head")  # second run
        assert True

    def test_stamp_and_upgrade(self, alembic_cfg):
        """Stamp at base, then upgrade to head."""
        command.stamp(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")
        assert True
