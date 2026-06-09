"""Shared request IP extraction helpers."""

from __future__ import annotations

import ipaddress
import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Request

logger = logging.getLogger(__name__)


def _get_header(request: Request, name: str) -> Optional[str]:
    headers = request.headers
    value = headers.get(name)
    if value is not None:
        return value
    return headers.get(name.title())


def parse_trusted_networks(proxies: List[str]) -> List[Any]:
    """Parse IP/CIDR strings into network objects for proxy trust validation."""
    networks = []
    for proxy in proxies:
        try:
            networks.append(ipaddress.ip_network(proxy, strict=False))
        except ValueError as e:
            logger.warning(f"Invalid trusted proxy address '{proxy}': {e}")
    return networks


def is_local_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback
    except ValueError:
        return False


def extract_ip(
    request: Request,
    trust_proxy: bool = False,
    trusted_networks: Optional[List[Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Return (ip_address, ip_metadata) for a request.

    Proxy headers are only honored when trust_proxy=True and the direct
    connection is from a configured trusted network. Empty trusted networks
    deny proxy headers by default to prevent IP spoofing.
    """
    direct_ip = request.client.host if request.client else None
    trusted_networks = trusted_networks or []

    forwarded = _get_header(request, "x-forwarded-for")
    real_ip = _get_header(request, "x-real-ip")
    use_proxy_header = False
    proxy_header_value = forwarded or real_ip
    if proxy_header_value and trust_proxy and trusted_networks:
        try:
            addr = ipaddress.ip_address(direct_ip or "")
            use_proxy_header = any(addr in net for net in trusted_networks)
        except ValueError:
            pass

    if use_proxy_header:
        raw = proxy_header_value
        clean = proxy_header_value.split(",")[0].strip()
        source = "proxy"
    else:
        clean = direct_ip or "unknown"
        raw = clean
        source = "direct"

    if not clean or clean == "unknown":
        return "unknown", {
            "address": "unknown",
            "type": "unknown",
            "isLocal": False,
            "source": "unknown",
            "originalValue": raw,
        }

    if clean in ("::1", "::ffff:127.0.0.1", "127.0.0.1") or clean.startswith("::ffff:127."):
        return "localhost", {
            "address": "localhost",
            "type": "local",
            "isLocal": True,
            "source": "direct",
            "originalValue": clean,
        }

    if clean.startswith("::ffff:"):
        clean = clean[7:]
        ip_type = "ipv4"
    elif ":" in clean:
        ip_type = "ipv6"
    else:
        ip_type = "ipv4"

    return clean, {
        "address": clean,
        "type": ip_type,
        "isLocal": is_local_ip(clean),
        "source": source,
        "originalValue": raw,
    }
