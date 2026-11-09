"""
Tavily Search API Adapter implementing WebSearchProtocol.
Provides real-time external web search and clean AI-summarized answer snippets
optimized for low-latency Voice RAG.
"""

from typing import List, Optional
import httpx

from app.core.config import settings
from app.core.logger import logger
from app.interfaces.adapters import RetrievedDocument, WebSearchProtocol

TAVILY_API_URL = "https://api.tavily.com/search"


class TavilySearchAdapter:
    """Tavily search client conforming to WebSearchProtocol."""

    def __init__(
        self,
        api_key: Optional[str] = settings.TAVILY_API_KEY,
        timeout: float = settings.WEB_SEARCH_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout

    async def search(self, query: str, max_results: int = 2) -> List[RetrievedDocument]:
        """
        Executes an asynchronous web search query via Tavily API.
        Returns a list of clean text snippets and direct answer summaries.
        """
        if not self.api_key:
            logger.info("[TAVILY] No TAVILY_API_KEY configured; skipping web search.")
            return []

        payload = {
            "api_key": self.api_key,
            "query": query.strip(),
            "search_depth": "basic",  # Fast search optimized for low-latency (<600ms)
            "max_results": max_results,
            "include_answer": True,   # Direct AI summarized response
            "include_raw_content": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(TAVILY_API_URL, json=payload)
                response.raise_for_status()
                data = response.json()

            documents: List[RetrievedDocument] = []

            # 1. Include direct summarized answer if returned by Tavily
            direct_answer = data.get("answer")
            if direct_answer:
                documents.append(
                    RetrievedDocument(
                        id="tavily-direct-answer",
                        text=f"Direct Search Answer: {direct_answer.strip()}",
                        score=1.0,
                    )
                )

            # 2. Include individual top search results
            for idx, res in enumerate(data.get("results", []), 1):
                title = res.get("title", "").strip()
                content = res.get("content", "").strip()
                score = float(res.get("score", 0.8))
                snippet = f"{title}: {content}" if title else content
                if snippet:
                    documents.append(
                        RetrievedDocument(
                            id=f"tavily-res-{idx}",
                            text=snippet,
                            score=score,
                        )
                    )

            logger.info(
                f"[TAVILY] Retrieved {len(documents)} search results for query: '{query[:40]}'"
            )
            return documents[: max_results + (1 if direct_answer else 0)]

        except httpx.TimeoutException:
            logger.warning(
                f"[TAVILY] Web search timed out after {self.timeout}s for query: '{query[:30]}'"
            )
            return []
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"[TAVILY] HTTP error {e.response.status_code} during web search: {e}"
            )
            return []
        except Exception as e:
            logger.warning(f"[TAVILY] Unexpected error during search: {e}")
            return []
