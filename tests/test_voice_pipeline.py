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

def test_multi_turn_pipeline_memory_integration():
    """Verify that multi-turn memory augments search and injects conversation history."""
    from app.services.session_memory import SessionMemory

    async def _run():
        mock_stt = MagicMock()
        mock_vdb = MagicMock()
        mock_vdb.hybrid_search = AsyncMock(return_value=[
            RetrievedDocument(id="doc1", text="Sahayak provides multilingual voice RAG services.", score=0.9)
        ])
        
        mock_llm = MagicMock()
        
        # Generator for Turn 1
        async def turn1_tokens(prompt):
            for t in ["Sahayak ", "is ", "a ", "voice ", "assistant."]:
                yield t

        # Generator for Turn 2
        async def turn2_tokens(prompt):
            for t in ["It ", "provides ", "low ", "latency ", "answers."]:
                yield t

        call_count = 0
        recorded_prompts = []
        def stream_mock(prompt):
            nonlocal call_count
            recorded_prompts.append(prompt)
            call_count += 1
            if call_count == 1:
                return turn1_tokens(prompt)
            return turn2_tokens(prompt)

        mock_llm.stream_tokens = MagicMock(side_effect=stream_mock)

        mock_tts = MagicMock()
        async def tts_mock(text):
            yield b"\x00" * 640
        mock_tts.synthesize_stream = MagicMock(side_effect=tts_mock)

        orchestrator = VoiceRAGOrchestrator(mock_stt, mock_vdb, mock_llm, mock_tts)
        mock_ws = AsyncMock()
        session_memory = SessionMemory(max_turns=3)

        # Execute Turn 1
        await orchestrator.process_voice_turn(
            "What is Sahayak?", mock_ws, session_memory=session_memory
        )
        assert len(session_memory) == 1
        assert session_memory.get_turns()[0].user_query == "What is Sahayak?"
        assert session_memory.get_turns()[0].assistant_response == "Sahayak is a voice assistant."

        # Execute Turn 2 with pronoun "it"
        await orchestrator.process_voice_turn(
            "What services does it provide?", mock_ws, session_memory=session_memory
        )
        assert len(session_memory) == 2

        # Verify Qdrant was called with augmented query
        vdb_calls = mock_vdb.hybrid_search.call_args_list
        assert len(vdb_calls) == 2
        turn2_vdb_query = vdb_calls[1].kwargs.get("query")
        assert turn2_vdb_query == "What is Sahayak? What services does it provide?"

        # Verify Turn 2 prompt contained Conversation History
        turn2_prompt = recorded_prompts[1]
        assert "Conversation History:" in turn2_prompt
        assert "User: What is Sahayak?" in turn2_prompt
        assert "Assistant: Sahayak is a voice assistant." in turn2_prompt

    asyncio.run(_run())

def test_orchestrator_web_search_trigger_on_temporal_query():
    """Verify that temporal queries (e.g., 'latest', 'today') trigger external web search."""
    async def _run():
        mock_stt = MagicMock()
        mock_vdb = MagicMock()
        mock_vdb.hybrid_search = AsyncMock(return_value=[
            RetrievedDocument(id="local-doc", text="Local knowledge base context.", score=0.85)
        ])
        
        mock_search = MagicMock()
        mock_search.search = AsyncMock(return_value=[
            RetrievedDocument(id="web-doc-1", text="Live web search result: India news today.", score=0.98)
        ])

        recorded_prompts = []
        async def mock_tokens(prompt):
            recorded_prompts.append(prompt)
            yield "Here is the latest update."

        mock_llm = MagicMock()
        mock_llm.stream_tokens = MagicMock(side_effect=mock_tokens)

        mock_tts = MagicMock()
        async def mock_tts_stream(text):
            yield b"\x00" * 640
        mock_tts.synthesize_stream = MagicMock(side_effect=mock_tts_stream)

        orchestrator = VoiceRAGOrchestrator(
            stt=mock_stt,
            vdb=mock_vdb,
            llm=mock_llm,
            tts=mock_tts,
            search=mock_search,
        )
        mock_ws = AsyncMock()

        # Execute turn with temporal query
        tracker = await orchestrator.process_voice_turn(
            "What is the latest news today?", mock_ws
        )

        steps = tracker.step_history
        assert "WEB_SEARCH_START" in steps
        assert "WEB_SEARCH_COMPLETE" in steps

        # Verify web search was invoked
        mock_search.search.assert_called_once()
        search_query_arg = mock_search.search.call_args.kwargs.get("query")
        assert "latest" in search_query_arg

        # Verify LLM prompt included the web search result
        assert len(recorded_prompts) == 1
        assert "Live web search result: India news today." in recorded_prompts[0]

    asyncio.run(_run())

def test_crag_high_confidence_bypasses_web_search():
    """Verify CRAG CORRECT state: score >= 0.82 bypasses web search completely."""
    from app.adapters.semantic_router import SemanticRouterAdapter

    async def _run():
        mock_stt = MagicMock()
        mock_vdb = MagicMock()
        mock_vdb.hybrid_search = AsyncMock(return_value=[
            RetrievedDocument(id="local-kisan", text="PM Kisan scheme provides ₹6000 per year.", score=0.94)
        ])
        mock_search = MagicMock()
        mock_search.search = AsyncMock()

        recorded_prompts = []
        mock_llm = MagicMock()
        async def mock_tokens(prompt):
            recorded_prompts.append(prompt)
            yield "PM Kisan provides financial assistance to farmers."
        mock_llm.stream_tokens = MagicMock(side_effect=mock_tokens)

        mock_tts = MagicMock()
        async def mock_tts_stream(text):
            yield b"\x00" * 640
        mock_tts.synthesize_stream = MagicMock(side_effect=mock_tts_stream)

        orchestrator = VoiceRAGOrchestrator(
            stt=mock_stt,
            vdb=mock_vdb,
            llm=mock_llm,
            tts=mock_tts,
            search=mock_search,
            router=SemanticRouterAdapter(),
        )
        mock_ws = AsyncMock()

        tracker = await orchestrator.process_voice_turn(
            "What is the eligibility criteria for PM Kisan scheme?", mock_ws
        )

        steps = tracker.step_history
        assert "ROUTER_CLASSIFY_COMPLETE" in steps
        assert "WEB_SEARCH_START" not in steps
        assert "WEB_SEARCH_COMPLETE" not in steps
        mock_search.search.assert_not_called()
        assert len(recorded_prompts) == 1
        assert "PM Kisan scheme provides ₹6000 per year." in recorded_prompts[0]

    asyncio.run(_run())

def test_crag_ambiguous_merges_local_and_web_docs():
    """Verify CRAG AMBIGUOUS state: 0.55 <= score < 0.82 merges local background with web facts."""
    from app.adapters.semantic_router import SemanticRouterAdapter

    async def _run():
        mock_stt = MagicMock()
        mock_vdb = MagicMock()
        mock_vdb.hybrid_search = AsyncMock(return_value=[
            RetrievedDocument(id="local-doc", text="Baseline government subsidy guidelines.", score=0.68)
        ])
        mock_search = MagicMock()
        mock_search.search = AsyncMock(return_value=[
            RetrievedDocument(id="web-doc", text="Recent 2026 subsidy amendment update.", score=0.91)
        ])

        recorded_prompts = []
        mock_llm = MagicMock()
        async def mock_tokens(prompt):
            recorded_prompts.append(prompt)
            yield "The subsidy was amended recently."
        mock_llm.stream_tokens = MagicMock(side_effect=mock_tokens)

        mock_tts = MagicMock()
        async def mock_tts_stream(text):
            yield b"\x00" * 640
        mock_tts.synthesize_stream = MagicMock(side_effect=mock_tts_stream)

        orchestrator = VoiceRAGOrchestrator(
            stt=mock_stt,
            vdb=mock_vdb,
            llm=mock_llm,
            tts=mock_tts,
            search=mock_search,
            router=SemanticRouterAdapter(),
        )
        mock_ws = AsyncMock()

        tracker = await orchestrator.process_voice_turn(
            "Did government change the subsidy rules recently?", mock_ws
        )

        steps = tracker.step_history
        assert "ROUTER_CLASSIFY_COMPLETE" in steps
        assert "WEB_SEARCH_START" in steps
        assert "WEB_SEARCH_COMPLETE" in steps
        mock_search.search.assert_called_once()

        # Both local and web context must be present in the prompt
        assert len(recorded_prompts) == 1
        assert "Recent 2026 subsidy amendment update." in recorded_prompts[0]
        assert "Baseline government subsidy guidelines." in recorded_prompts[0]

    asyncio.run(_run())

def test_crag_low_confidence_suppresses_local_docs():
    """Verify CRAG INCORRECT state: score < 0.55 suppresses irrelevant local docs and uses web search."""
    from app.adapters.semantic_router import SemanticRouterAdapter

    async def _run():
        mock_stt = MagicMock()
        mock_vdb = MagicMock()
        mock_vdb.hybrid_search = AsyncMock(return_value=[
            RetrievedDocument(id="irrelevant-doc", text="Irrelevant agricultural welfare text.", score=0.38)
        ])
        mock_search = MagicMock()
        mock_search.search = AsyncMock(return_value=[
            RetrievedDocument(id="web-answer", text="George Washington was the first US president.", score=0.99)
        ])

        recorded_prompts = []
        mock_llm = MagicMock()
        async def mock_tokens(prompt):
            recorded_prompts.append(prompt)
            yield "George Washington was the first president."
        mock_llm.stream_tokens = MagicMock(side_effect=mock_tokens)

        mock_tts = MagicMock()
        async def mock_tts_stream(text):
            yield b"\x00" * 640
        mock_tts.synthesize_stream = MagicMock(side_effect=mock_tts_stream)

        orchestrator = VoiceRAGOrchestrator(
            stt=mock_stt,
            vdb=mock_vdb,
            llm=mock_llm,
            tts=mock_tts,
            search=mock_search,
            router=SemanticRouterAdapter(),
        )
        mock_ws = AsyncMock()

        tracker = await orchestrator.process_voice_turn(
            "Who was the first president of the United States?", mock_ws
        )

        steps = tracker.step_history
        assert "ROUTER_CLASSIFY_COMPLETE" in steps
        assert "WEB_SEARCH_START" in steps
        assert "WEB_SEARCH_COMPLETE" in steps
        mock_search.search.assert_called_once()

        # Web context must be present; irrelevant local doc must be suppressed!
        assert len(recorded_prompts) == 1
        assert "George Washington was the first US president." in recorded_prompts[0]
        assert "Irrelevant agricultural welfare text." not in recorded_prompts[0]

    asyncio.run(_run())

def test_speculative_tavily_dispatch_on_temporal_intent():
    """Verify speculative concurrent dispatch when semantic router detects REALTIME_TEMPORAL."""
    from app.adapters.semantic_router import SemanticRouterAdapter

    async def _run():
        mock_stt = MagicMock()
        mock_vdb = MagicMock()
        mock_vdb.hybrid_search = AsyncMock(return_value=[
            RetrievedDocument(id="local-doc", text="Local news text.", score=0.52)
        ])
        mock_search = MagicMock()
        mock_search.search = AsyncMock(return_value=[
            RetrievedDocument(id="web-doc", text="Live breaking news update today in India.", score=0.99)
        ])

        mock_llm = MagicMock()
        async def mock_tokens(prompt):
            yield "Here are today's headlines."
        mock_llm.stream_tokens = MagicMock(side_effect=mock_tokens)

        mock_tts = MagicMock()
        async def mock_tts_stream(text):
            yield b"\x00" * 640
        mock_tts.synthesize_stream = MagicMock(side_effect=mock_tts_stream)

        orchestrator = VoiceRAGOrchestrator(
            stt=mock_stt,
            vdb=mock_vdb,
            llm=mock_llm,
            tts=mock_tts,
            search=mock_search,
            router=SemanticRouterAdapter(),
        )
        mock_ws = AsyncMock()

        tracker = await orchestrator.process_voice_turn(
            "What is the latest news in India today?", mock_ws
        )

        steps = tracker.step_history
        assert "ROUTER_CLASSIFY_COMPLETE" in steps
        assert "SPECULATIVE_SEARCH_DISPATCHED" in steps
        assert "WEB_SEARCH_COMPLETE" in steps
        mock_search.search.assert_called_once()

    asyncio.run(_run())
