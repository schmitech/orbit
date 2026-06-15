"""Async utility helpers."""

import asyncio
from typing import Any, Optional


async def close_client(client: Any) -> Optional[str]:
    """Close a client with async or sync close methods. Returns an error string on failure."""
    try:
        aclose_method = getattr(client, 'aclose', None)
        if aclose_method and callable(aclose_method):
            await aclose_method()
            return None

        close_method = getattr(client, 'close', None)
        if close_method and callable(close_method):
            result = close_method()
            if asyncio.iscoroutine(result):
                await result
    except AttributeError:
        return None
    except Exception as e:
        return str(e)

    return None
