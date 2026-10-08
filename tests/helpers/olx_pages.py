import json
from collections.abc import Mapping, Sequence
from typing import Any


def advert_url(code: str, *, host: str = "www.olx.ua", query: str = "") -> str:
    return f"https://{host}/d/uk/obyavlenie/budynok-CID767-ID{code}.html{query}"


def ad(code: str, *, created: str | None = None, url: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": abs(hash(code)) % 10**9, "title": f"Advert {code}"}
    payload["url"] = url if url is not None else advert_url(code, query="?reason=observed")
    if created is not None:
        payload["createdTime"] = created
    return payload


def state_page(
    ads: Sequence[Mapping[str, Any]],
    *,
    total: int | None = None,
    state: Mapping[str, Any] | None = None,
) -> str:
    document = state or {
        "config": {"ads": [{"slot": "top-banner"}]},
        "listing": {
            "listing": {
                "ads": list(ads),
                "totalElements": len(ads) if total is None else total,
            }
        },
    }
    literal = json.dumps(json.dumps(document, ensure_ascii=False))
    return (
        "<!DOCTYPE html><html lang='uk'><head><title>OLX</title>"
        "<script id='olx-init-config'>"
        f"window.__APP_VERSION__ = '1.2.3'; window.__PRERENDERED_STATE__= {literal};"
        "</script></head><body><div id='root'></div></body></html>"
    )


def cards_page(*codes: str) -> str:
    cards = "".join(
        f'<div data-cy="l-card" data-testid="l-card" id="{index}">'
        f'<a class="css-xyz" href="/d/uk/obyavlenie/budynok-ID{code}.html?reason=r">Advert</a>'
        "</div>"
        for index, code in enumerate(codes, start=1)
    )
    return f"<html><body><div data-testid='listing-grid'>{cards}</div></body></html>"
