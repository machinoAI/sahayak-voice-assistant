"""
Unit tests for concrete LLM streaming adapters (OpenAICompatibleLLMAdapter, AnthropicClaudeAdapter).
"""

import pytest
from app.adapters.llm.openai_compatible import OpenAICompatibleLLMAdapter
from app.adapters.llm.anthropic import AnthropicClaudeAdapter
from app.interfaces.adapters import LLMMessage

@pytest.mark.asyncio
async def test_openai_compatible_mock_fallback():
    """Verify OpenAICompatibleLLMAdapter yields mock tokens when api_key is None."""
    adapter = OpenAICompatibleLLMAdapter(provider="groq", api_key=None, model="llama3")
    tokens = []
    async for token in adapter.stream_tokens("Hello Sahayak"):
        tokens.append(token)

    full_text = "".join(tokens)
    assert len(tokens) > 0
    assert "Sahayak" in full_text
    assert "GROQ_API_KEY" in full_text

def test_openai_compatible_normalize_messages():
    adapter = OpenAICompatibleLLMAdapter(provider="openai", api_key="dummy")
    
    # String prompt
    msgs1 = adapter._normalize_messages("Simple prompt", system_prompt="Be concise.")
    assert len(msgs1) == 2
    assert msgs1[0] == {"role": "system", "content": "Be concise."}
    assert msgs1[1] == {"role": "user", "content": "Simple prompt"}

    # List of LLMMessage
    msgs2 = adapter._normalize_messages([
        LLMMessage(role="user", content="Hi"),
        LLMMessage(role="assistant", content="Hello"),
    ])
    assert len(msgs2) == 2
    assert msgs2[0]["content"] == "Hi"
    assert msgs2[1]["role"] == "assistant"

def test_anthropic_prepare_payload():
    adapter = AnthropicClaudeAdapter(api_key="dummy", model="claude-3-5-haiku-20241022")
    
    # String prompt with system prompt
    system_content, msgs = adapter._prepare_payload("Help me with schemes", system_prompt="System instructions")
    assert system_content == "System instructions"
    assert len(msgs) == 1
    assert msgs[0] == {"role": "user", "content": "Help me with schemes"}

    # List of messages with system role inside
    messages = [
        {"role": "system", "content": "Inline system text"},
        {"role": "user", "content": "Query 1"},
    ]
    system_content_2, msgs2 = adapter._prepare_payload(messages)
    assert "Inline system text" in system_content_2
    assert len(msgs2) == 1
    assert msgs2[0]["content"] == "Query 1"
