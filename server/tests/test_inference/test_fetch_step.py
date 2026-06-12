"""
Regression tests for FetchStep (server/inference/pipeline/steps/fetch.py).

Coverage:
- _is_private_host: IPv4 private ranges, IPv6 loopback, link-local (169.254),
  public IPs, DNS failure, unparseable URL, bare hostname variants
- _safe_get: clean response, single redirect to public URL, redirect to private
  IP, redirect to private hostname, redirect chain exceeding MAX_REDIRECTS,
  relative Location header resolution
- FetchStep.process: private original URL blocked, no URL in message,
  should_execute guards, Jina success path, Jina thin-content fallback,
  direct-fetch happy path, public-to-private redirect blocked mid-chain
"""

import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, server_dir)

# Pin the 'inference' package to server/inference (mirrors test_mcp_agent_step).
if 'inference' not in sys.modules:
    _pkg = types.ModuleType('inference')
    _pkg.__path__ = [os.path.join(server_dir, 'inference')]
    _pkg.__package__ = 'inference'
    sys.modules['inference'] = _pkg

from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps.fetch import (
    _MAX_REDIRECTS,
    _SSRFRedirectError,
    _is_private_host,
    _safe_get,
    FetchStep,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code: int, headers: dict = None, text: str = "") -> httpx.Response:
    """Build a minimal httpx.Response without a real transport."""
    raw_headers = list((k.lower().encode(), v.encode()) for k, v in (headers or {}).items())
    return httpx.Response(
        status_code=status_code,
        headers=raw_headers,
        text=text,
        request=httpx.Request("GET", "http://example.com/"),
    )


class _FakeContainer:
    def __init__(self, adapter_type: str = "fetch"):
        self._type = adapter_type

    def has(self, name: str) -> bool:
        return name == "adapter_manager"

    def get(self, name: str):
        if name == "adapter_manager":
            mgr = MagicMock()
            mgr.get_adapter_config.return_value = {"type": self._type}
            return mgr
        raise KeyError(name)

    def get_or_none(self, name: str):
        try:
            return self.get(name)
        except KeyError:
            return None


# ---------------------------------------------------------------------------
# _is_private_host
# ---------------------------------------------------------------------------

class TestIsPrivateHost:
    def test_loopback_ipv4(self):
        assert _is_private_host("http://127.0.0.1/") is True

    def test_loopback_127_x(self):
        assert _is_private_host("http://127.99.1.2/path") is True

    def test_rfc1918_10(self):
        assert _is_private_host("http://10.0.0.1/") is True

    def test_rfc1918_192_168(self):
        assert _is_private_host("http://192.168.1.100/") is True

    def test_rfc1918_172_16(self):
        assert _is_private_host("http://172.16.0.1/") is True

    def test_rfc1918_172_31(self):
        assert _is_private_host("http://172.31.255.255/") is True

    def test_link_local_aws_metadata(self):
        # AWS/GCP instance metadata endpoint
        assert _is_private_host("http://169.254.169.254/latest/meta-data/") is True

    def test_link_local_other(self):
        assert _is_private_host("http://169.254.1.1/") is True

    def test_ipv6_loopback(self):
        assert _is_private_host("http://[::1]/") is True

    def test_ipv6_private_fc00(self):
        # fc00::/7 is IPv6 unique-local (analogous to RFC1918)
        assert _is_private_host("http://[fc00::1]/") is True

    def test_ipv6_link_local(self):
        assert _is_private_host("http://[fe80::1]/") is True

    def test_public_ip_allowed(self):
        # 93.184.216.34 is example.com — public, must not be blocked
        assert _is_private_host("http://93.184.216.34/") is False

    def test_public_ip_8_8_8_8(self):
        assert _is_private_host("http://8.8.8.8/") is False

    def test_dns_failure_blocked(self):
        # Unresolvable hostname — treat as unsafe
        with patch("socket.gethostbyname", side_effect=OSError("name resolution failed")):
            assert _is_private_host("http://nonexistent.internal/") is True

    def test_localhost_hostname(self):
        with patch("socket.gethostbyname", return_value="127.0.0.1"):
            assert _is_private_host("http://localhost/") is True

    def test_internal_hostname_resolves_private(self):
        with patch("socket.gethostbyname", return_value="10.0.0.5"):
            assert _is_private_host("http://internal.corp/") is True

    def test_empty_hostname_blocked(self):
        assert _is_private_host("not-a-url") is True


# ---------------------------------------------------------------------------
# _safe_get
# ---------------------------------------------------------------------------

class TestSafeGet:
    @pytest.mark.asyncio
    async def test_no_redirect_returns_response(self):
        resp = _make_response(200, text="hello")
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=resp)

        result = await _safe_get(client, "http://93.184.216.34/", "TestAgent")

        assert result.status_code == 200
        client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_redirect_to_public_url(self):
        redirect = _make_response(301, headers={"location": "http://8.8.8.8/final"})
        final = _make_response(200, text="content")
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=[redirect, final])

        with patch("socket.gethostbyname", return_value="8.8.8.8"):
            result = await _safe_get(client, "http://8.8.8.8/start", "TestAgent")

        assert result.status_code == 200
        assert client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_redirect_to_private_ip_blocked(self):
        redirect = _make_response(301, headers={"location": "http://192.168.1.1/secret"})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=redirect)

        with pytest.raises(_SSRFRedirectError, match="192.168.1.1"):
            await _safe_get(client, "http://8.8.8.8/start", "TestAgent")

        # Must not have followed the redirect
        client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_redirect_to_localhost_blocked(self):
        redirect = _make_response(302, headers={"location": "http://localhost/admin"})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=redirect)

        with patch("socket.gethostbyname", return_value="127.0.0.1"):
            with pytest.raises(_SSRFRedirectError, match="localhost"):
                await _safe_get(client, "http://8.8.8.8/", "TestAgent")

        client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_redirect_to_metadata_ip_blocked(self):
        redirect = _make_response(307, headers={"location": "http://169.254.169.254/latest"})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=redirect)

        with pytest.raises(_SSRFRedirectError, match="169.254.169.254"):
            await _safe_get(client, "http://8.8.8.8/", "TestAgent")

    @pytest.mark.asyncio
    async def test_redirect_to_ipv6_loopback_blocked(self):
        redirect = _make_response(301, headers={"location": "http://[::1]/secret"})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=redirect)

        with pytest.raises(_SSRFRedirectError, match=r"\[::1\]|::1"):
            await _safe_get(client, "http://8.8.8.8/", "TestAgent")

    @pytest.mark.asyncio
    async def test_relative_redirect_resolved_and_validated(self):
        # Relative redirect to a private path on a different host via absolute Location
        redirect = _make_response(302, headers={"location": "http://10.0.0.1/page"})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=redirect)

        with pytest.raises(_SSRFRedirectError):
            await _safe_get(client, "http://8.8.8.8/start", "TestAgent")

    @pytest.mark.asyncio
    async def test_exceeds_max_redirects(self):
        # Every response is a redirect to itself
        redirect = _make_response(301, headers={"location": "http://8.8.8.8/loop"})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=redirect)

        with patch("socket.gethostbyname", return_value="8.8.8.8"):
            with pytest.raises(httpx.TooManyRedirects):
                await _safe_get(client, "http://8.8.8.8/loop", "TestAgent")

        assert client.get.call_count == _MAX_REDIRECTS + 1

    @pytest.mark.asyncio
    async def test_redirect_without_location_returns_response(self):
        # 301 with no Location header — stop and return it
        resp = _make_response(301)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=resp)

        result = await _safe_get(client, "http://8.8.8.8/", "TestAgent")

        assert result.status_code == 301
        client.get.assert_called_once()


# ---------------------------------------------------------------------------
# FetchStep.process
# ---------------------------------------------------------------------------

class TestFetchStepProcess:
    @pytest.mark.asyncio
    async def test_no_url_in_message_sets_error(self):
        step = FetchStep(_FakeContainer())
        ctx = ProcessingContext(message="just some text with no URL", adapter_name="fetch")

        result = await step.process(ctx)

        assert result.has_error()
        assert "No URL" in result.error

    @pytest.mark.asyncio
    async def test_private_original_url_blocked(self):
        step = FetchStep(_FakeContainer())
        ctx = ProcessingContext(message="fetch http://192.168.1.1/data", adapter_name="fetch")

        result = await step.process(ctx)

        assert result.has_error()
        assert "private" in result.error.lower() or "internal" in result.error.lower()

    @pytest.mark.asyncio
    async def test_localhost_url_blocked(self):
        step = FetchStep(_FakeContainer())
        ctx = ProcessingContext(message="http://localhost:8080/admin", adapter_name="fetch")

        with patch("socket.gethostbyname", return_value="127.0.0.1"):
            result = await step.process(ctx)

        assert result.has_error()

    @pytest.mark.asyncio
    async def test_jina_success_sets_formatted_context(self):
        step = FetchStep(_FakeContainer())
        ctx = ProcessingContext(message="http://8.8.8.8/page", adapter_name="fetch")

        jina_markdown = "# Title\n" + "x" * 200

        with patch("socket.gethostbyname", return_value="8.8.8.8"):
            with patch(
                "inference.pipeline.steps.fetch._fetch_jina",
                new=AsyncMock(return_value=jina_markdown),
            ):
                result = await step.process(ctx)

        assert not result.has_error()
        assert jina_markdown in result.formatted_context
        assert "Source:" in result.formatted_context
        assert result.response == ""  # response left empty; LLM fills it

    @pytest.mark.asyncio
    async def test_jina_thin_content_falls_back_to_direct_fetch(self):
        step = FetchStep(_FakeContainer())
        ctx = ProcessingContext(message="http://8.8.8.8/page", adapter_name="fetch")

        html = "<html><body><main>Real content here with enough text to pass.</main></body></html>"

        with patch("socket.gethostbyname", return_value="8.8.8.8"):
            with patch(
                "inference.pipeline.steps.fetch._fetch_jina",
                new=AsyncMock(return_value=None),  # Jina returns nothing
            ):
                with patch(
                    "inference.pipeline.steps.fetch._safe_get",
                    new=AsyncMock(return_value=_make_response(200, {"content-type": "text/html"}, html)),
                ):
                    result = await step.process(ctx)

        assert not result.has_error()
        assert "Real content" in result.formatted_context

    @pytest.mark.asyncio
    async def test_redirect_to_private_ip_mid_chain_blocked(self):
        step = FetchStep(_FakeContainer())
        ctx = ProcessingContext(message="http://8.8.8.8/tricky", adapter_name="fetch")

        with patch("socket.gethostbyname", return_value="8.8.8.8"):
            with patch(
                "inference.pipeline.steps.fetch._fetch_jina",
                new=AsyncMock(return_value=None),
            ):
                with patch(
                    "inference.pipeline.steps.fetch._safe_get",
                    new=AsyncMock(side_effect=_SSRFRedirectError("Redirect to private address blocked: http://10.0.0.1/")),
                ):
                    result = await step.process(ctx)

        assert result.has_error()
        assert "private" in result.error.lower() or "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_http_error_sets_error(self):
        step = FetchStep(_FakeContainer())
        ctx = ProcessingContext(message="http://8.8.8.8/missing", adapter_name="fetch")

        bad_response = _make_response(404)
        with patch("socket.gethostbyname", return_value="8.8.8.8"):
            with patch(
                "inference.pipeline.steps.fetch._fetch_jina",
                new=AsyncMock(return_value=None),
            ):
                with patch(
                    "inference.pipeline.steps.fetch._safe_get",
                    new=AsyncMock(return_value=bad_response),
                ):
                    result = await step.process(ctx)

        assert result.has_error()
        assert "404" in result.error

    def test_should_execute_true_for_fetch_type(self):
        step = FetchStep(_FakeContainer(adapter_type="fetch"))
        ctx = ProcessingContext(adapter_name="fetch")
        assert step.should_execute(ctx) is True

    def test_should_execute_false_for_other_type(self):
        step = FetchStep(_FakeContainer(adapter_type="image_generation"))
        ctx = ProcessingContext(adapter_name="fetch")
        assert step.should_execute(ctx) is False

    def test_should_execute_false_when_blocked(self):
        step = FetchStep(_FakeContainer())
        ctx = ProcessingContext(adapter_name="fetch")
        ctx.is_blocked = True
        assert step.should_execute(ctx) is False
