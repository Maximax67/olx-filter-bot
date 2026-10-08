import re
from collections.abc import Sequence

from aiogram.enums import MessageEntityType
from aiogram.types import MessageEntity

_BARE_URL = re.compile(r"https?://\S+", re.IGNORECASE)


def extract_candidate(text: str | None, entities: Sequence[MessageEntity] | None) -> str | None:
    if not text:
        return None
    for entity in entities or ():
        if entity.type == MessageEntityType.TEXT_LINK and entity.url:
            return entity.url
        if entity.type == MessageEntityType.URL:
            return entity.extract_from(text)
    stripped = text.strip()
    return stripped if _BARE_URL.fullmatch(stripped) else None
