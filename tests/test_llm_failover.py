"""
Unit tests for FailoverLLMAdapter (circuit breaker cooldowns and prefix continuation).
"""

import time
import pytest
from typing import AsyncGenerator, List, Dict, Optional, Union
from app.adapters.failover import FailoverLLMAdapter
from app.interfaces.adapters import LLMMessage

class MockFailingLLMAdapter:
    def __init__(self, name: str, fail_at_token: int = 0, tokens: Optional[List[str]] = None):
        self.name = name
        self.fail_at_token = fail_at_token
        self.tokens = tokens or ["Sentence 1. ", "Sentence 2. "]
        self.last_received_prompt = None

    @property
    def model(self) -> str:
        return f"mock-{self.name}"

    async def stream_tokens(
        self,
        prompt: Union[str, List[LLMMessage], List[Dict[str, str]]],
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        self.last_received_prompt = prompt
        for i, token in enumerate(self.tokens):
            if i == self.fail_at_token:
                raise RuntimeError(f"{self.name} connection dropped at token {i}")
            yield token

class MockHealthyLLMAdapter:
    def __init__(self, name: str, tokens: Optional[List[str]] = None):
        self.name = name
        self.tokens = tokens or ["Fallback sentence 1. ", "Fallback sentence 2."]
        self.last_received_prompt = None

    @property
    def model(self) -> str:
        return f"mock-{self.name}"

    async def stream_tokens(
        self,
        prompt: Union[str, List[LLMMessage], List[Dict[str, str]]],
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        self.last_received_prompt = prompt
        for token in self.tokens:
            yield token

@pytest.mark.asyncio
async def test_llm_failover_immediate_failure():
    """Verify clean failover when primary fails immediately before emitting tokens."""
    primary = MockFailingLLMAdapter("primary", fail_at_token=0)
    fallback = MockHealthyLLMAdapter("fallback")

    adapter = FailoverLLMAdapter(
        adapters=[("primary", primary), ("fallback", fallback)],
        cooldown_seconds=10.0,
    )

    tokens = []
    async for token in adapter.stream_tokens("Test prompt"):
        tokens.append(token)

    result_text = "".join(tokens)
    assert "Fallback sentence 1." in result_text
    assert adapter._is_cooling_down("primary") is True
    assert adapter._is_cooling_down("fallback") is False

@pytest.mark.asyncio
async def test_llm_failover_with_prefix_continuation():
    """Verify that mid-stream failure triggers prefix continuation on fallback."""
    primary = MockFailingLLMAdapter("primary", fail_at_token=1, tokens=["Primary token 1. ", "Primary token 2."])
    fallback = MockHealthyLLMAdapter("fallback", tokens=["Continuation part 2."])

    adapter = FailoverLLMAdapter(
        adapters=[("primary", primary), ("fallback", fallback)],
        cooldown_seconds=10.0,
    )

    tokens = []
    async for token in adapter.stream_tokens("Original query"):
        tokens.append(token)

    # Check that tokens from both primary (before crash) and fallback (continuation) were yielded
    assert tokens[0] == "Primary token 1. "
    assert tokens[1] == "Continuation part 2."

    # Check that fallback received prefix continuation in prompt
    assert fallback.last_received_prompt is not None
    # Must contain assistant history with "Primary token 1. "
    assistant_roles = [m for m in fallback.last_received_prompt if m.get("role") == "assistant"]
    assert len(assistant_roles) == 1
    assert "Primary token 1." in assistant_roles[0]["content"]

@pytest.mark.asyncio
async def test_llm_failover_all_exhausted():
    """Verify that if all adapters fail, last exception is raised."""
    p1 = MockFailingLLMAdapter("p1", fail_at_token=0)
    p2 = MockFailingLLMAdapter("p2", fail_at_token=0)

    adapter = FailoverLLMAdapter(
        adapters=[("p1", p1), ("p2", p2)],
        cooldown_seconds=10.0,
    )

    with pytest.raises(RuntimeError) as exc_info:
        async for _ in adapter.stream_tokens("Prompt"):
            pass

    assert "dropped at token 0" in str(exc_info.value)
