"""
Automated unit & integration test suite for Sahayak Voice RAG Orchestrator.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.services.voice_orchestrator import VoiceRAGOrchestrator, extract_next_sentence
from app.interfaces.adapters import RetrievedDocument

def test_sentence_boundary_extraction():
    """Verify that abbreviations and currencies do not cause premature sentence splitting."""
    text_with_currency = "The fee is Rs. 500 for consultation. Please confirm."
    s1, rem1 = extract_next_sentence(text_with_currency)
    assert s1 == "The fee is Rs. 500 for consultation."
    s2, rem2 = extract_next_sentence(rem1)
    assert s2 == "Please confirm."
    assert rem2.strip() == ""

    text_with_honorific = "Consult Dr. Sharma at the clinic. He is available."
    s1, rem1 = extract_next_sentence(text_with_honorific)
    assert s1 == "Consult Dr. Sharma at the clinic."
    s2, rem2 = extract_next_sentence(rem1)
    assert s2 == "He is available."
    assert rem2.strip() == ""

def test_sentence_buffer_slicing():
    """Verify exact slicing indices when extracting multiple sentences from a buffer."""
    buffer = "First sentence. Second sentence! Remaining text"
    extracted = []
    
    while True:
        sentence, buffer = extract_next_sentence(buffer)
        if sentence is None:
            break
        extracted.append(sentence)

    assert extracted == ["First sentence.", "Second sentence!"]
    assert buffer.strip() == "Remaining text"

def test_token_stream_decoupling():
    """Verify that LLM token reading continues into sentence queue without being blocked by TTS."""
    async def _run():
        queue = asyncio.Queue()
        mock_tokens = ["Sentence one. ", "Sentence two! ", "Finished."]
        
        # Producer
        buffer = ""
        for token in mock_tokens:
            buffer += token
            while True:
                sentence, buffer = extract_next_sentence(buffer)
                if sentence is None:
                    break
                await queue.put(sentence)

        assert queue.qsize() == 3
        assert await queue.get() == "Sentence one."
        assert await queue.get() == "Sentence two!"
        assert await queue.get() == "Finished."

    asyncio.run(_run())

def test_barge_in_cancellation_teardown():
    """Verify that user interruption cleanly cancels in-flight tasks and sends buffer clear."""
    async def _run():
        mock_stt = MagicMock()
        mock_vdb = MagicMock()
        mock_llm = MagicMock()
        mock_tts = MagicMock()

        orchestrator = VoiceRAGOrchestrator(
            stt=mock_stt,
            vdb=mock_vdb,
            llm=mock_llm,
            tts=mock_tts,
        )

        mock_ws = AsyncMock()
        
        # Simulate an active long-running task
        async def dummy_generation():
            await asyncio.sleep(5)

        orchestrator.active_generation_task = asyncio.create_task(dummy_generation())
        
        # Trigger interruption
        await orchestrator.handle_user_interruption(mock_ws)

        assert orchestrator.active_generation_task.cancelled() or orchestrator.active_generation_task.done()
        mock_ws.send_json.assert_called_once_with({"event": "CLEAR_AUDIO_BUFFER"})

    asyncio.run(_run())

def test_websocket_send_concurrency_lock():
    """Verify thread-safe WebSocket send serialization using the asyncio Lock."""
    async def _run():
        mock_stt = MagicMock()
        mock_vdb = MagicMock()
        mock_llm = MagicMock()
        mock_tts = MagicMock()

        orchestrator = VoiceRAGOrchestrator(mock_stt, mock_vdb, mock_llm, mock_tts)
        mock_ws = AsyncMock()

        # Launch parallel sends
        await asyncio.gather(
            orchestrator._send_safe_json(mock_ws, {"event": "TEST"}),
            orchestrator._send_safe_bytes(mock_ws, b"\x00\x01\x02"),
            orchestrator._send_safe_json(mock_ws, {"event": "CLEAR"}),
        )

        assert mock_ws.send_json.call_count == 2
        assert mock_ws.send_bytes.call_count == 1

    asyncio.run(_run())
