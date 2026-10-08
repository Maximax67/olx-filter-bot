from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base


class SearchFilterModel(Base):
    __tablename__ = "search_filter"
    __table_args__ = (
        CheckConstraint("number > 0", name="number_positive"),
        UniqueConstraint("user_id", "number", name="search_filter_user_id_number_key"),
        UniqueConstraint("user_id", "url_hash", name="search_filter_user_id_url_hash_key"),
        Index(
            "search_filter_next_check_at_idx",
            "next_check_at",
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bot_user.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String(2048))
    url_hash: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    consecutive_failures: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    consecutive_misses: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_check_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
