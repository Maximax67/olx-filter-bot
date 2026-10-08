from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base


class SeenAdvertModel(Base):
    __tablename__ = "seen_advert"
    __table_args__ = (Index("seen_advert_last_seen_at_idx", "last_seen_at"),)

    search_filter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("search_filter.id", ondelete="CASCADE"), primary_key=True
    )
    advert_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
