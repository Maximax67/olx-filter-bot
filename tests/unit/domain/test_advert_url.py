import pytest

from src.domain.exceptions import InvalidAdvertUrlError
from src.domain.value_objects.advert_url import AdvertUrl


def test_parses_absolute_url_and_strips_the_query() -> None:
    url = AdvertUrl.parse(
        "https://www.olx.ua/d/uk/obyavlenie/girskyi-velosyped-CID767-ID14zZz1.html?reason=x#y"
    )
    assert url.code == "14zZz1"
    assert url.value == "https://www.olx.ua/d/uk/obyavlenie/girskyi-velosyped-CID767-ID14zZz1.html"


def test_parses_relative_href() -> None:
    url = AdvertUrl.parse("/d/uk/obyavlenie/house-IDabc12.html")
    assert url.value == "https://www.olx.ua/d/uk/obyavlenie/house-IDabc12.html"


def test_parses_variant_without_language_prefix_and_apex_host() -> None:
    url = AdvertUrl.parse("http://olx.ua/d/obyavlenie/house-IDabc12.html")
    assert url.value == "https://www.olx.ua/d/obyavlenie/house-IDabc12.html"


def test_code_is_taken_from_the_last_id_marker() -> None:
    assert AdvertUrl.parse("/d/uk/obyavlenie/a-ID5-CID767-IDxyz99.html").code == "xyz99"


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.olx.pl/d/uk/obyavlenie/house-IDabc12.html",
        "https://evil.com/d/uk/obyavlenie/house-IDabc12.html",
        "https://www.olx.ua@evil.com/d/uk/obyavlenie/house-IDabc12.html",
        "https://www.olx.ua:8443/d/uk/obyavlenie/house-IDabc12.html",
        "https://www.olx.ua/uk/list/q-iphone/",
        "https://www.olx.ua/d/uk/obyavlenie/house.html",
        "https://www.olx.ua/d/uk/obyavlenie/house-IDabc12.php",
        "https://www.olx.ua/d/uk/other/house-IDabc12.html",
        "https://www.olx.ua/d/uk/obyavlenie/house-ID.html",
        "javascript:alert(1)",
        "",
    ],
)
def test_rejects_anything_that_is_not_an_olx_advert(raw: str) -> None:
    with pytest.raises(InvalidAdvertUrlError):
        AdvertUrl.parse(raw)
