import pytest
from aiogram.types import MessageEntity

from src.presentation.bot.url_extraction import extract_candidate

URL = "https://www.olx.ua/uk/list/q-iphone/?currency=UAH"


def entity(kind: str, offset: int, length: int, url: str | None = None) -> MessageEntity:
    return MessageEntity(type=kind, offset=offset, length=length, url=url)


def test_uses_url_entity() -> None:
    text = f"look at {URL} please"
    assert extract_candidate(text, [entity("url", 8, len(URL))]) == URL


def test_uses_text_link_target() -> None:
    assert extract_candidate("my search", [entity("text_link", 0, 9, URL)]) == URL


def test_takes_the_first_link_when_several_are_present() -> None:
    text = f"{URL} and https://other.example/"
    entities = [entity("url", 0, len(URL)), entity("url", len(URL) + 5, 21)]
    assert extract_candidate(text, entities) == URL


def test_accepts_a_bare_url_without_entities() -> None:
    assert extract_candidate(f"  {URL}\n", None) == URL


def test_ignores_non_url_entities() -> None:
    assert extract_candidate("hello", [entity("bold", 0, 5)]) is None


@pytest.mark.parametrize("text", ["hello there", "see https://www.olx.ua/x/ for details", "", None])
def test_returns_nothing_for_plain_text(text: str | None) -> None:
    assert extract_candidate(text, None) is None
