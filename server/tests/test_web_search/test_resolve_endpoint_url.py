import pytest
from web_search.base import resolve_endpoint_url


def test_omitted_returns_default():
    assert resolve_endpoint_url(None, "https://example.com/default", provider="x") == (
        "https://example.com/default"
    )


def test_omitted_with_no_default_raises():
    with pytest.raises(ValueError, match="required"):
        resolve_endpoint_url(None, None, provider="x")


def test_valid_value_overrides_default():
    assert resolve_endpoint_url(
        "https://example.com/other", "https://example.com/default", provider="x"
    ) == "https://example.com/other"


def test_blank_raises_even_with_valid_default():
    with pytest.raises(ValueError, match="x"):
        resolve_endpoint_url("", "https://example.com/default", provider="x")


@pytest.mark.parametrize(
    "bad_value",
    [
        "/api/blogs",
        "ftp://example.com/path",
        "not-a-url",
        "https://",
        "https://example.com:abc/search",
    ],
)
def test_malformed_raises(bad_value):
    with pytest.raises(ValueError):
        resolve_endpoint_url(bad_value, "https://example.com/default", provider="x")


def test_parse_error_still_names_provider():
    with pytest.raises(ValueError, match="webz"):
        resolve_endpoint_url("https://[::1/search", "https://example.com/default", provider="webz")
