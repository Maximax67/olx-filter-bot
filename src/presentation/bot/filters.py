from aiogram import F
from aiogram.enums import ChatType

PRIVATE_MESSAGE = F.chat.type == ChatType.PRIVATE
PRIVATE_CALLBACK = F.message.chat.type == ChatType.PRIVATE
