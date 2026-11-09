"""
Unit and integration tests for TavilySearchAdapter.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.adapters.search_tavily import TavilySearchAdapter
from app.core.config import settings

def test_tavily_adapter_without_key_returns_empty():
    """Verify that search returns empty list when API key is None."""
    async def _run():
        adapter = TavilySearchAdapter(api_key=None)
        results = await adapter.search("latest news in India")
        assert results == []

    asyncio.run(_run())

def test_tavily_response_parsing():
    """Verify parsing of Tavily direct answer and search results into RetrievedDocuments."""
    mock_response_data = {
        "query": "Who is the Prime Minister of India?",
        "answer": "Narendra Modi is the current Prime Minister of India.",
        "results": [
            {
                "title": "Prime Minister of India - Official Website",
                "content": "Official portal of the Prime Minister of India.",
                "url": "https://pmindia.gov.in",
                "score": 0.95,
            },
            {
                "title": "Government of India Directory",
                "content": "Directory of executive branch officials.",
                "url": "https://india.gov.in",
                "score": 0.85,
            },
        ],
    }

    async def _run():
        adapter = TavilySearchAdapter(api_key="tvly-mock-key")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_data
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            results = await adapter.search("Who is the Prime Minister of India?", max_results=2)

            assert len(results) == 3  # 1 direct answer + 2 results
            assert results[0].id == "tavily-direct-answer"
            assert "Narendra Modi" in results[0].text
            assert results[1].id == "tavily-res-1"
            assert "pmindia.gov.in" in results[1].text or "Official portal" in results[1].text

    asyncio.run(_run())

def test_tavily_timeout_resilience():
    """Verify that search timeouts do not raise exceptions and return empty list."""
    async def _run():
        adapter = TavilySearchAdapter(api_key="tvly-mock-key", timeout=0.1)

        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout")):
            results = await adapter.search("slow query")
            assert results == []

    asyncio.run(_run())

def test_tavily_http_error_resilience():
    """Verify that HTTP 4xx/5xx errors are caught and return empty list."""
    async def _run():
        adapter = TavilySearchAdapter(api_key="tvly-mock-key")
        mock_request = MagicMock()
        mock_response = MagicMock(status_code=401)
        err = httpx.HTTPStatusError("Unauthorized", request=mock_request, response=mock_response)

        with patch("httpx.AsyncClient.post", side_effect=err):
            results = await adapter.search("unauthorized query")
            assert results == []

    asyncio.run(_run())

def test_tavily_live_search():
    """Optional live integration test if TAVILY_API_KEY is configured in .env."""
    if not settings.TAVILY_API_KEY:
        pytest.skip("TAVILY_API_KEY not configured in .env")

    async def _run():
        adapter = TavilySearchAdapter(api_key=settings.TAVILY_API_KEY)
        results = await adapter.search("current weather in New Delhi today", max_results=2)
        print(f"\n[TAVILY LIVE] Retrieved {len(results)} results")
        for doc in results:
            print(f"  --> [{doc.score:.2f}] {doc.text[:70]}...")
        assert len(results) > 0

    asyncio.run(_run())
