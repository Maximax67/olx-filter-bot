from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from src.domain.entities.user import User
from src.presentation.bot import texts
from src.presentation.bot.filters import PRIVATE_MESSAGE


async def show_help(message: Message, user: User) -> None:
    await message.answer(texts.welcome(user.filter_limit))


async def reject_unknown_command(message: Message) -> None:
    await message.answer(texts.UNKNOWN_COMMAND)


def create_router() -> Router:
    router = Router(name="start")
    router.message.filter(PRIVATE_MESSAGE)
    router.message.register(show_help, CommandStart())
    router.message.register(show_help, Command("help"))
    router.message.register(reject_unknown_command, F.text.startswith("/"))
    return router
