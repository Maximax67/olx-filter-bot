import argparse
import asyncio
import sys
from collections.abc import Sequence

from src.application.exceptions import AdvertSourceError
from src.domain.exceptions import InvalidFilterUrlError
from src.domain.value_objects.filter_url import FilterUrl
from src.infrastructure.config import OlxSettings
from src.infrastructure.olx.advert_source import OlxAdvertSource
from src.infrastructure.olx.client import OlxHttpClient
from src.infrastructure.olx.parser import OlxListingParser


def _write(line: str) -> None:
    sys.stdout.write(f"{line}\n")


async def _run(raw_url: str) -> int:
    try:
        url = FilterUrl.parse(raw_url)
    except InvalidFilterUrlError as error:
        _write(f"rejected: {error.reason.value}")
        return 2

    _write(f"canonical: {url.value}")
    async with OlxHttpClient(OlxSettings()) as client:
        source = OlxAdvertSource(client=client, parser=OlxListingParser())
        try:
            listing = await source.fetch_latest(url)
        except AdvertSourceError as error:
            _write(f"fetch failed: {type(error).__name__}: {error}")
            return 1

    _write(f"adverts: {len(listing.adverts)}")
    for advert in listing.adverts:
        published = advert.published_at.isoformat() if advert.published_at else "-"
        _write(f"{advert.id}\t{published}\t{advert.url.value}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.presentation.cli.probe")
    parser.add_argument("url", help="OLX.ua search or category URL")
    return asyncio.run(_run(parser.parse_args(argv).url))


if __name__ == "__main__":
    raise SystemExit(main())
