"""
Shared HTTP client pooling and adapter lifecycle management.
"""

from typing import Dict
import httpx

class HTTPClientManager:
    """Manages shared HTTP client connection pools across adapters."""
    _clients: Dict[str, httpx.AsyncClient] = {}

    @classmethod
    def get_client(cls, pool_name: str = "default", timeout: float = 10.0) -> httpx.AsyncClient:
        """Returns or creates a pooled AsyncClient."""
        client = cls._clients.get(pool_name)
        if client is None or client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=100, keepalive_expiry=30.0)
            client = httpx.AsyncClient(limits=limits, timeout=timeout)
            cls._clients[pool_name] = client
        return client

    @classmethod
    async def close_all(cls) -> None:
        """Gracefully closes all pooled HTTP clients."""
        for name, client in list(cls._clients.items()):
            if not client.is_closed:
                await client.aclose()
        cls._clients.clear()
