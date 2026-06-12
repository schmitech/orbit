"""
Fetch Step

Fetches web page content from a URL when the adapter is of type 'fetch'.
Tries Jina Reader first (returns clean markdown, no extra deps) then falls
back to httpx + BeautifulSoup for direct HTML parsing.
Replaces LLMInferenceStep for such adapters.
"""

import ipaddress
import logging
import re
import socket
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..base import PipelineStep, ProcessingContext

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r'https?://[^\s]+')
_JINA_BASE = "https://r.jina.ai/"
_MIN_CONTENT_LEN = 100
_REDIRECT_CODES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 10

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; OrbitBot/1.0)"
DEFAULT_TIMEOUT = 30


def _is_private_host(url: str) -> bool:
    """Return True if the URL resolves to a private/internal address."""
    try:
        hostname = urlparse(url).hostname or ""
        if not hostname:
            return True
        # Resolve to IP and check against private/special ranges
        addr = ipaddress.ip_address(socket.gethostbyname(hostname))
        return (
            addr.is_loopback
            or addr.is_private
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_unspecified
            or addr.is_multicast
        )
    except Exception:
        # DNS failure or invalid IP — treat as unsafe
        return True


def _get_adapter_type(container, adapter_name: str) -> Optional[str]:
    """Return the adapter's 'type' field, or None if unavailable."""
    if not adapter_name or not container.has('adapter_manager'):
        return None
    try:
        adapter_manager = container.get('adapter_manager')
        adapter_config = adapter_manager.get_adapter_config(adapter_name)
        if adapter_config:
            return adapter_config.get('type')
    except Exception:
        pass
    return None


class FetchStep(PipelineStep):
    """
    Fetch web page content from a URL in the user's message.

    Executes only for adapters whose 'type' is 'fetch'.
    Tries Jina Reader (r.jina.ai) first for clean markdown output;
    falls back to direct httpx fetch + BeautifulSoup parsing.
    Stores result in context.response.
    """

    def should_execute(self, context: ProcessingContext) -> bool:
        if context.is_blocked:
            return False
        return _get_adapter_type(self.container, context.adapter_name) == 'fetch'

    def supports_streaming(self) -> bool:
        return False

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        match = _URL_RE.search(context.message)
        if not match:
            context.set_error("No URL found in message. Please provide a URL starting with http:// or https://.")
            return context

        url = match.group(0).rstrip('.,;)')

        adapter_config = {}
        if context.adapter_name and self.container.has('adapter_manager'):
            try:
                adapter_config = self.container.get('adapter_manager').get_adapter_config(context.adapter_name) or {}
            except Exception:
                pass

        timeout = adapter_config.get('fetch_timeout', DEFAULT_TIMEOUT)
        user_agent = adapter_config.get('fetch_user_agent', DEFAULT_USER_AGENT)

        if _is_private_host(url):
            context.set_error(f"Requests to private or internal addresses are not allowed: {url}")
            return context

        logger.debug("FetchStep: fetching %s", url)

        async with httpx.AsyncClient(timeout=timeout) as client:
            # 1. Try Jina Reader — returns markdown directly, no parsing needed.
            # follow_redirects=True is safe here: we control the prefix (r.jina.ai),
            # not the destination, so redirect hops are jina-internal.
            content = await _fetch_jina(client, url)
            if content:
                logger.debug("FetchStep: Jina Reader succeeded for %s", url)
                context.formatted_context = f"Source: {url}\n\n{content}"
                return context

            logger.debug("FetchStep: Jina Reader failed or returned thin content, falling back to direct fetch")

            # 2. Fall back to direct fetch + BS4 parsing.
            # _safe_get follows redirects manually and validates each hop.
            try:
                response = await _safe_get(client, url, user_agent)
                response.raise_for_status()
            except _SSRFRedirectError as e:
                context.set_error(str(e))
                context.response = str(e)
                return context
            except httpx.TimeoutException:
                msg = f"Request timed out after {timeout}s for URL: {url}"
                context.set_error(msg)
                context.response = msg
                return context
            except httpx.HTTPStatusError as e:
                msg = f"HTTP {e.response.status_code} fetching {url}"
                context.set_error(msg)
                context.response = msg
                return context
            except httpx.HTTPError as e:
                msg = f"Failed to fetch {url}: {e}"
                context.set_error(msg)
                context.response = msg
                return context

            content_type = response.headers.get("content-type", "")
            if "html" not in content_type and "text" not in content_type:
                msg = f"Unsupported content type '{content_type}' for {url}. Only HTML/text pages are supported."
                context.set_error(msg)
                context.response = msg
                return context

            context.formatted_context = _parse_html(response.text, url)
        return context


class _SSRFRedirectError(Exception):
    """Raised when a redirect would lead to a private/internal address."""


async def _safe_get(
    client: httpx.AsyncClient,
    url: str,
    user_agent: str,
) -> httpx.Response:
    """
    GET with manual redirect following, validating every hop against SSRF.

    Each Location header is resolved and checked before the next request is
    made, so a public URL that redirects to an internal address is blocked
    before the internal request occurs.
    """
    headers = {"User-Agent": user_agent}
    for _ in range(_MAX_REDIRECTS + 1):
        response = await client.get(url, headers=headers, follow_redirects=False)
        if response.status_code not in _REDIRECT_CODES:
            return response
        location = response.headers.get("location", "")
        if not location:
            return response
        next_url = urljoin(url, location)
        if _is_private_host(next_url):
            raise _SSRFRedirectError(
                f"Redirect to private or internal address blocked: {next_url}"
            )
        url = next_url
    raise httpx.TooManyRedirects(f"Exceeded {_MAX_REDIRECTS} redirects")


async def _fetch_jina(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """
    Fetch via Jina Reader (r.jina.ai), which returns clean markdown.
    Returns None if the request fails or content is too short to be useful.
    Note: free tier — 20 req/min, 500 req/day without an API key.
    """
    try:
        response = await client.get(
            f"{_JINA_BASE}{url}",
            headers={"Accept": "text/plain"},
            follow_redirects=True,
        )
        if response.status_code == 200:
            text = response.text.strip()
            if len(text) >= _MIN_CONTENT_LEN:
                return text
    except Exception as e:
        logger.debug("Jina Reader request failed: %s", e)
    return None


def _parse_html(html: str, url: str) -> str:
    """Extract readable text from HTML, returning a plain-text document."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(["script", "style", "nav", "footer", "noscript", "aside"]):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        description = meta_desc["content"].strip()

    body = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", {"id": "content"})
        or soup.find("div", {"class": "content"})
        or soup.find("body")
        or soup
    )

    text = body.get_text(separator="\n", strip=True)
    lines = [line for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)

    parts = [f"Source: {url}"]
    if title:
        parts.append(f"Title: {title}")
    if description:
        parts.append(f"Description: {description}")
    parts.append("")
    parts.append(text)

    return "\n".join(parts)
