"""
Shared HTTP client pooling and adapter lifecycle management.
"""

import asyncio
from typing import Dict, Tuple, Optional
import httpx

class HTTPClientManager:
    """Manages shared HTTP client connection pools across adapters."""
    _clients: Dict[str, Tuple[httpx.AsyncClient, Optional[asyncio.AbstractEventLoop]]] = {}

    @classmethod
    def get_client(cls, pool_name: str = "default", timeout: float = 10.0) -> httpx.AsyncClient:
        """Returns or creates a pooled AsyncClient bound to the current running event loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        entry = cls._clients.get(pool_name)
        if entry is not None:
            client, client_loop = entry
            if client.is_closed or (current_loop and client_loop != current_loop):
                entry = None

        if entry is None:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=100, keepalive_expiry=30.0)
            client = httpx.AsyncClient(limits=limits, timeout=timeout)
            cls._clients[pool_name] = (client, current_loop)
            return client

        return entry[0]

    @classmethod
    async def close_all(cls) -> None:
        """Gracefully closes all pooled HTTP clients."""
        for name, (client, _) in list(cls._clients.items()):
            if not client.is_closed:
                try:
                    await client.aclose()
                except Exception:
                    pass
        cls._clients.clear()
