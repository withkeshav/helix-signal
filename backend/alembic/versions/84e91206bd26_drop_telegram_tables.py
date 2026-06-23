"""drop_telegram_tables

Revision ID: 84e91206bd26
Revises: 3d37f6302ff9
Create Date: 2026-06-23 21:29:18.654008

Drop orphan Telegram tables after application code removal.
Schema definitions for downgrade() mirror:
  - a9409ead8fc4_add_telegram_users_table.py
  - 8344a415ccb7_add_telegram_user_preferences_columns.py
  - 1f18a71856ad_add_telegram_persistent_features.py
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "84e91206bd26"
down_revision: Union[str, Sequence[str], None] = "3d37f6302ff9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TELEGRAM_SETTING_KEYS = (
    "alert_telegram_bot_token",
    "alert_telegram_chat_id",
    "feature_telegram_bot",
    "telegram_channel",
)


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _delete_telegram_settings() -> None:
    """Remove orphan settings rows; values are not restored on downgrade."""
    if "settings" not in _table_names():
        return
    keys_sql = ", ".join(f"'{key}'" for key in _TELEGRAM_SETTING_KEYS)
    op.execute(f"DELETE FROM settings WHERE key IN ({keys_sql})")


def upgrade() -> None:
    tables = _table_names()

    if "telegram_rate_limits" in tables:
        op.drop_index(op.f("ix_telegram_rate_limits_id"), table_name="telegram_rate_limits")
        op.drop_index(op.f("ix_telegram_rate_limits_telegram_id"), table_name="telegram_rate_limits")
        op.drop_table("telegram_rate_limits")

    if "telegram_review_items" in tables:
        op.drop_index(op.f("ix_telegram_review_items_id"), table_name="telegram_review_items")
        op.drop_index(op.f("ix_telegram_review_items_review_id"), table_name="telegram_review_items")
        op.drop_table("telegram_review_items")

    if "telegram_users" in tables:
        op.drop_index(op.f("ix_telegram_users_id"), table_name="telegram_users")
        op.drop_index(op.f("ix_telegram_users_telegram_id"), table_name="telegram_users")
        op.drop_table("telegram_users")

    _delete_telegram_settings()


def downgrade() -> None:
    tables = _table_names()

    if "telegram_users" not in tables:
        op.create_table(
            "telegram_users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("telegram_id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=128), nullable=True),
            sa.Column("first_name", sa.String(length=128), nullable=True),
            sa.Column("last_name", sa.String(length=128), nullable=True),
            sa.Column("is_subscribed", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column(
                "preferred_assets",
                sa.String(length=512),
                nullable=True,
                server_default="USDT,USDC,DAI",
            ),
            sa.Column(
                "alert_types",
                sa.String(length=512),
                nullable=True,
                server_default="signal,anomaly,osint",
            ),
            sa.Column(
                "min_severity",
                sa.String(length=20),
                nullable=True,
                server_default="medium",
            ),
            sa.Column(
                "timezone",
                sa.String(length=50),
                nullable=True,
                server_default="UTC",
            ),
            sa.Column("quiet_hours_start", sa.String(length=5), nullable=True),
            sa.Column("quiet_hours_end", sa.String(length=5), nullable=True),
            sa.Column(
                "receive_digest",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "digest_time",
                sa.String(length=5),
                nullable=True,
                server_default="09:00",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_telegram_users_telegram_id"),
            "telegram_users",
            ["telegram_id"],
            unique=True,
        )
        op.create_index(op.f("ix_telegram_users_id"), "telegram_users", ["id"], unique=False)

    if "telegram_review_items" not in tables:
        op.create_table(
            "telegram_review_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("review_id", sa.String(length=64), nullable=False),
            sa.Column("alert_data", sa.Text(), nullable=False),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("approved", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_telegram_review_items_review_id"),
            "telegram_review_items",
            ["review_id"],
            unique=True,
        )
        op.create_index(
            op.f("ix_telegram_review_items_id"),
            "telegram_review_items",
            ["id"],
            unique=False,
        )

    if "telegram_rate_limits" not in tables:
        op.create_table(
            "telegram_rate_limits",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("telegram_id", sa.Integer(), nullable=False),
            sa.Column("command_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_reset", sa.DateTime(), nullable=False),
            sa.Column("window_seconds", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("max_commands", sa.Integer(), nullable=False, server_default="10"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_telegram_rate_limits_telegram_id"),
            "telegram_rate_limits",
            ["telegram_id"],
            unique=True,
        )
        op.create_index(
            op.f("ix_telegram_rate_limits_id"),
            "telegram_rate_limits",
            ["id"],
            unique=False,
        )

    # Orphan telegram_* settings rows are not recreated on downgrade (harmless if absent).
