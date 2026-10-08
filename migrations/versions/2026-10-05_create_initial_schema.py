from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b1e8c2d9a47"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_user",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("filter_limit", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "filter_limit >= 0", name=op.f("bot_user_filter_limit_non_negative_check")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("bot_user_pkey")),
        sa.UniqueConstraint("telegram_id", name=op.f("bot_user_telegram_id_key")),
    )
    op.create_table(
        "search_filter",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("consecutive_misses", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_check_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("number > 0", name=op.f("search_filter_number_positive_check")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["bot_user.id"],
            name=op.f("search_filter_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("search_filter_pkey")),
        sa.UniqueConstraint("user_id", "number", name="search_filter_user_id_number_key"),
        sa.UniqueConstraint("user_id", "url_hash", name="search_filter_user_id_url_hash_key"),
    )
    op.create_index(
        "search_filter_next_check_at_idx",
        "search_filter",
        ["next_check_at"],
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "seen_advert",
        sa.Column("search_filter_id", sa.BigInteger(), nullable=False),
        sa.Column("advert_id", sa.String(length=32), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["search_filter_id"],
            ["search_filter.id"],
            name=op.f("seen_advert_search_filter_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("search_filter_id", "advert_id", name=op.f("seen_advert_pkey")),
    )
    op.create_index("seen_advert_last_seen_at_idx", "seen_advert", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("seen_advert_last_seen_at_idx", table_name="seen_advert")
    op.drop_table("seen_advert")
    op.drop_index("search_filter_next_check_at_idx", table_name="search_filter")
    op.drop_table("search_filter")
    op.drop_table("bot_user")
