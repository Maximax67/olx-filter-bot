from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.domain.entities.search_filter import SearchFilter
from src.presentation.bot.callbacks import DeleteFilterCallback


def delete_filters_keyboard(filters: Sequence[SearchFilter]) -> InlineKeyboardMarkup | None:
    if not filters:
        return None
    builder = InlineKeyboardBuilder()
    for search_filter in filters:
        builder.button(
            text=f"🗑 Delete filter {search_filter.number}",
            callback_data=DeleteFilterCallback(number=search_filter.number),
        )
    builder.adjust(2)
    return builder.as_markup()
