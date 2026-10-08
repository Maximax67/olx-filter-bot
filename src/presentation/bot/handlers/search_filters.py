from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

from src.application.use_cases.add_search_filter import AddSearchFilter
from src.application.use_cases.delete_search_filter import DeleteSearchFilter
from src.application.use_cases.list_search_filters import ListSearchFilters
from src.domain.entities.user import User
from src.presentation.bot import texts
from src.presentation.bot.callbacks import DeleteFilterCallback
from src.presentation.bot.filters import PRIVATE_CALLBACK, PRIVATE_MESSAGE
from src.presentation.bot.keyboards import delete_filters_keyboard
from src.presentation.bot.url_extraction import extract_candidate

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


async def add_command(
    message: Message,
    command: CommandObject,
    user: User,
    add_search_filter: AddSearchFilter,
) -> None:
    candidate = (command.args or "").strip()
    if not candidate:
        await message.answer(texts.ADD_USAGE)
        return
    await _add_filter(message, user, candidate, add_search_filter)


async def list_command(
    message: Message, user: User, list_search_filters: ListSearchFilters
) -> None:
    filters = await list_search_filters.execute(user_id=user.id)
    await message.answer(
        texts.filters_overview(filters, user.filter_limit),
        reply_markup=delete_filters_keyboard(filters),
        link_preview_options=NO_PREVIEW,
    )


async def delete_command(
    message: Message,
    command: CommandObject,
    user: User,
    delete_search_filter: DeleteSearchFilter,
) -> None:
    argument = (command.args or "").strip()
    if not argument.isdecimal():
        await message.answer(texts.DELETE_USAGE)
        return
    number = int(argument)
    await delete_search_filter.execute(user_id=user.id, number=number)
    await message.answer(texts.filter_deleted(number))


async def delete_button(
    query: CallbackQuery,
    callback_data: DeleteFilterCallback,
    user: User,
    delete_search_filter: DeleteSearchFilter,
    list_search_filters: ListSearchFilters,
) -> None:
    await delete_search_filter.execute(user_id=user.id, number=callback_data.number)
    await query.answer(texts.filter_deleted(callback_data.number))
    if isinstance(query.message, Message):
        filters = await list_search_filters.execute(user_id=user.id)
        await query.message.edit_text(
            texts.filters_overview(filters, user.filter_limit),
            reply_markup=delete_filters_keyboard(filters),
            link_preview_options=NO_PREVIEW,
        )


async def link_message(message: Message, user: User, add_search_filter: AddSearchFilter) -> None:
    candidate = extract_candidate(message.text, message.entities)
    if candidate is None:
        await message.answer(texts.SEND_LINK_HINT)
        return
    await _add_filter(message, user, candidate, add_search_filter)


async def _add_filter(
    message: Message, user: User, candidate: str, add_search_filter: AddSearchFilter
) -> None:
    added = await add_search_filter.execute(user=user, raw_url=candidate)
    await message.answer(texts.filter_added(added))


def create_router() -> Router:
    router = Router(name="search_filters")
    router.message.filter(PRIVATE_MESSAGE)
    router.callback_query.filter(PRIVATE_CALLBACK)
    router.message.register(add_command, Command("add"))
    router.message.register(list_command, Command("list"))
    router.message.register(delete_command, Command("delete"))
    router.callback_query.register(delete_button, DeleteFilterCallback.filter())
    router.message.register(link_message, F.text, ~F.text.startswith("/"))
    return router
