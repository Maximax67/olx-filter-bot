from aiogram.filters.callback_data import CallbackData


class DeleteFilterCallback(CallbackData, prefix="delete_filter"):
    number: int
