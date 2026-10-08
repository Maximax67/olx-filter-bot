import json
import re
from collections import deque
from datetime import UTC, datetime
from typing import Any

from selectolax.lexbor import LexborHTMLParser, LexborNode

from src.application.exceptions import ListingNotRecognizedError
from src.domain.entities.advert import Advert
from src.domain.exceptions import InvalidAdvertUrlError
from src.domain.value_objects.advert_url import AdvertUrl

_STATE_MARKER = "__PRERENDERED_STATE__"
_ASSIGNMENT = re.compile(r"\s*=\s*")
_DECODER = json.JSONDecoder()
_CARD_SELECTOR = '[data-cy="l-card"]'
_MAX_SEARCH_DEPTH = 6


class OlxListingParser:
    def parse(self, html: str) -> tuple[Advert, ...]:
        adverts = _from_state(html)
        if adverts is None:
            adverts = _from_cards(html)
        if adverts is None:
            raise ListingNotRecognizedError("no advert listing found in page")
        return adverts


def _from_state(html: str) -> tuple[Advert, ...] | None:
    position = html.find(_STATE_MARKER)
    while position != -1:
        end = position + len(_STATE_MARKER)
        state = _decode_state(html, end)
        if state is not None:
            adverts = _adverts_from_state(state)
            if adverts is not None:
                return adverts
        position = html.find(_STATE_MARKER, end)
    return None


def _decode_state(html: str, position: int) -> dict[str, Any] | None:
    assignment = _ASSIGNMENT.match(html, position)
    if assignment is None:
        return None
    try:
        value, _ = _DECODER.raw_decode(html, assignment.end())
        if isinstance(value, str):
            value = json.loads(value)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _adverts_from_state(state: dict[str, Any]) -> tuple[Advert, ...] | None:
    listing = _dig(state, "listing", "listing")
    if isinstance(listing, dict) and isinstance(listing.get("ads"), list):
        ads: list[Any] = listing["ads"]
        if not ads and _declares_results(listing):
            return None
        return _convert(ads)
    discovered = _search_ads(state)
    return _convert(discovered) if discovered else None


def _declares_results(listing: dict[str, Any]) -> bool:
    total = listing.get("totalElements")
    return isinstance(total, int) and not isinstance(total, bool) and total > 0


def _dig(node: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _search_ads(state: Any) -> list[Any] | None:
    queue: deque[tuple[Any, int]] = deque([(state, 0)])
    while queue:
        node, depth = queue.popleft()
        children: list[Any]
        if isinstance(node, dict):
            ads = node.get("ads")
            if isinstance(ads, list) and ads and all(_to_advert(ad) is not None for ad in ads):
                return ads
            children = list(node.values())
        elif isinstance(node, list):
            children = node
        else:
            continue
        if depth < _MAX_SEARCH_DEPTH:
            queue.extend((child, depth + 1) for child in children if isinstance(child, dict | list))
    return None


def _convert(ads: list[Any]) -> tuple[Advert, ...] | None:
    adverts: dict[str, Advert] = {}
    for ad in ads:
        advert = _to_advert(ad)
        if advert is not None:
            adverts.setdefault(advert.id, advert)
    if ads and not adverts:
        return None
    return tuple(adverts.values())


def _to_advert(ad: Any) -> Advert | None:
    if not isinstance(ad, dict):
        return None
    url = ad.get("url")
    if not isinstance(url, str):
        return None
    try:
        advert_url = AdvertUrl.parse(url)
    except InvalidAdvertUrlError:
        return None
    created = ad.get("createdTime", ad.get("created_time"))
    return Advert(url=advert_url, published_at=_parse_timestamp(created))


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _from_cards(html: str) -> tuple[Advert, ...] | None:
    cards = LexborHTMLParser(html).css(_CARD_SELECTOR)
    adverts: dict[str, Advert] = {}
    for card in cards:
        advert = _advert_from_card(card)
        if advert is not None:
            adverts.setdefault(advert.id, advert)
    return tuple(adverts.values()) if adverts else None


def _advert_from_card(card: LexborNode) -> Advert | None:
    for anchor in card.css("a[href]"):
        href = anchor.attributes.get("href")
        if not href:
            continue
        try:
            return Advert(url=AdvertUrl.parse(href))
        except InvalidAdvertUrlError:
            continue
    return None
