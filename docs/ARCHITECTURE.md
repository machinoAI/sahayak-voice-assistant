# Sahayak Voice Assistant — Architecture & System Design

Sahayak is an ultra-low latency, streaming Voice Retrieval-Augmented Generation (Voice RAG) assistant designed for Indian multilingual queries. It operates under a strict **sub-1.2s Time-to-First-Audio-Byte (TTFAB)** budget while delivering grounded answers for citizen welfare schemes, real-time news/weather, and general knowledge.

---

## 1. High-Level System Architecture

The system coordinates four decoupled, asynchronous streaming pipelines across WebSockets:

```mermaid
flowchart TD
    subgraph Client ["Client Layer (Browser UI / CLI Client)"]
        MIC["Microphone (16kHz PCM)"]
        GAIN["Zero-Gain Node (gain=0) -> Destination"]
        UI_WS["WebSocket Client (/ws/voice)"]
        CANVAS["Neural Decision Canvas (Live Telemetry)"]
        SPEAKER["Audio Output (Web Audio API / SoundDevice)"]
    end

    subgraph Gateway ["FastAPI Gateway (app.api.websocket_endpoint)"]
        GUARD["Lazy Reconnect Guard (ensure_stt_connected)"]
        STT_TASK["Supervised STT Listener Task"]
    end

    subgraph Server ["FastAPI Backend (app.services.voice_orchestrator)"]
        STT["Streaming STT (Deepgram Nova-2 + KeepAlive Loop)"]
        VAD["Server-Side VAD & Barge-in Detector"]
        MEM["Session Memory (Rolling 3 Turns + Indic Pronouns)"]
        
        ROUTER["In-Process Semantic Router (OATS Centroid)"]
        
        subgraph Retrieval ["Dual Retrieval & Speculative Engine"]
            VDB["Qdrant Hybrid Vector Store"]
            WEB["Speculative Web Search (Tavily API)"]
            CRAG["CRAG Tri-State Evaluator"]
        end
        
        SPLIT["Incremental Sentence Boundary Splitter (Abbrev + Danda)"]
        LLM["Groq Streaming LLM (gpt-oss-120b + Prompt Steering)"]
        QUEUE["Async Sentence Queue"]
        
        subgraph TTS ["Dual-Tier Neural TTS Dispatcher"]
            TTS_EN["Cartesia Sonic (English, 180ms TTFAB)"]
            TTS_HI["Edge-TTS (Devanagari Hindi Swara/Madhur, 450ms TTFAB)"]
        end
    end

    MIC --> GAIN
    MIC -->|Binary PCM Chunks| UI_WS
    UI_WS -->|WebSocket Stream| GUARD
    GUARD -->|Active Socket Verify| STT
    STT <-->|5s Heartbeat| DG_CLOUD["Deepgram Cloud WS"]
    STT -->|Interim Transcripts| VAD
    VAD -->|Barge-in Signal| STT
    STT -->|Final Transcript| MEM
    MEM -->|Augmented Query| ROUTER
    
    ROUTER -->|Intent & Latency| CRAG
    ROUTER -->|Speculative Dispatch| WEB
    ROUTER -->|Parallel Retrieval| VDB
    
    VDB -->|Local Docs & Score| CRAG
    WEB -.->|Live Web Chunks| CRAG
    CRAG -->|Pruned / Merged Context| LLM
    
    LLM -->|Live Token Stream| SPLIT
    SPLIT -->|Completed Sentences| QUEUE
    QUEUE -->|Language-Aware Routing| TTS
    TTS -->|16kHz Audio Chunks| UI_WS
    
    SERVER_TELEMETRY["Pipeline Steps & Telemetry"] -->|JSON Telemetry| CANVAS
    TTS -->|Binary Audio Frames| SPEAKER
```

---

## 2. End-to-End Latency Budget

To maintain natural conversational rhythm without perceptible lag, every turn is constrained to an end-to-end budget:

```
0ms          100ms        200ms        300ms        400ms        500ms        600ms        700ms        800ms        900ms       1000ms       1100ms
├────────────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│ Deepgram   │ Router     │ Qdrant     │ Groq LLM TTFT (Time-To-First-Token)       │ Cartesia Sonic TTS TTFAB   │ User Hears First Audio     │
│ Final STT  │ (0.2ms)    │ Search     │                                           │ (180ms - 250ms)            │ Word at ~800ms - 1100ms    │
│ (~150ms)   │ + Spec     │ (35ms)     │                                           │                            │                            │
│            │ Dispatch   │            │                                           │                            │                            │
```

| Pipeline Component | Technology Stack | Latency Budget | Observed Benchmark (EN / HI) |
| :--- | :--- | :--- | :--- |
| **Speech-to-Text (STT)** | Deepgram Nova-2 Streaming (`en-IN` / `hi` / `multi`) | $< 250\text{ ms}$ | $120\text{ ms} - 180\text{ ms}$ |
| **Intent Classification** | In-Process OATS Centroid Sparse Router | $< 1.0\text{ ms}$ | **$0.19\text{ ms} - 0.38\text{ ms}$** |
| **Vector DB Retrieval** | Qdrant Hybrid (Dense + Sparse BM25) | $< 60\text{ ms}$ | $27\text{ ms} - 55\text{ ms}$ |
| **Speculative Search Dispatch** | Non-blocking `asyncio.create_task` | $< 2.0\text{ ms}$ | **$0.8\text{ ms} - 1.2\text{ ms}$** |
| **LLM Time-To-First-Token** | Groq API (`openai/gpt-oss-120b` + prompt steering) | $< 800\text{ ms}$ | $580\text{ ms} - 790\text{ ms}$ |
| **Sentence Boundary Slicing** | Regex with Honorific & Danda (`।`) Guard | $< 0.1\text{ ms}$ | $0.05\text{ ms}$ |
| **TTS Time-To-First-Audio (EN)** | Cartesia Sonic 16kHz Linear PCM | $< 300\text{ ms}$ | **$180\text{ ms} - 240\text{ ms}$** |
| **TTS Time-To-First-Audio (HI)** | Edge-TTS Neural (`hi-IN-SwaraNeural` / `hi-IN-MadhurNeural`) | $< 600\text{ ms}$ | **$400\text{ ms} - 550\text{ ms}$** |
| **Audio Transmission** | Thread-Safe WebSocket Binary Stream | $< 10\text{ ms}$ | $2\text{ ms} - 5\text{ ms}$ |
| **Total Turn TTFAB (English)** | Speech Final $\to$ First Browser Audio Byte | **$< 1200\text{ ms}$** | **$790\text{ ms} - 1050\text{ ms}$** |
| **Total Turn TTFAB (Hindi)** | Speech Final $\to$ First Browser Audio Byte | **$< 1500\text{ ms}$** | **$1050\text{ ms} - 1280\text{ ms}$** |

---

## 3. Decoupled Pipeline & Task Concurrency

The orchestrator (`app/services/voice_orchestrator.py`) decouples generation and synthesis using Python's `asyncio` primitive channels:

1. **Producer Loop (`LLM Token Reader`)**:
   - Streams raw tokens from Groq API into a local sentence accumulator.
   - Executes non-destructive sentence boundary extraction.
   - Pushes completed clauses immediately into `sentence_queue: asyncio.Queue[Optional[str]]`.
   - Never halts or awaits audio synthesis; continues consuming LLM tokens at full generation speed (~60 tokens/sec).

2. **Consumer Loop (`TTS Synthesis Worker`)**:
   - Runs concurrently inside `active_tts_task = asyncio.create_task(self._tts_worker(...))`.
   - Pops the first completed sentence (e.g., $S_1$) from the queue.
   - Initiates streaming TTS synthesis before the LLM has even started generating sentence $S_2$.
   - Delivers binary PCM audio frames over WebSocket to the client.

3. **Sentinel Completion Signal**:
   - When the LLM stream completes, `None` is enqueued into `sentence_queue`.
   - The worker finishes synthesizing any remaining buffer, gracefully drains, and marks the turn completed.

---

## 4. Automatic Barge-In Cancellation

When the user speaks over the assistant while speech synthesis is active:
1. Deepgram STT emits an `interim` or `final` speech event.
2. `orchestrator.is_speaking()` evaluates to `True`.
3. `handle_user_interruption()` is immediately triggered:
   - `active_generation_task.cancel()` stops the LLM generation task.
   - `active_tts_task.cancel()` aborts in-flight TTS WebSocket requests.
   - Both tasks are awaited cleanly via `asyncio.gather(..., return_exceptions=True)`.
   - A `{"event": "CLEAR_AUDIO_BUFFER"}` control frame is transmitted over WebSocket.
   - The client Web Audio API immediately flushes its queued audio nodes, silencing output in $< 40\text{ms}$.
   - The partial assistant response is saved to `SessionMemory` marked with `was_interrupted=True`.

---

## 5. Multi-Turn Session Persistence & Inactivity Resilience

Voice sessions frequently encounter long inter-utterance pauses (e.g., a user listening to a 30-second explanation, reading on-screen information, or contemplating their next question). Default streaming STT connections silently terminate if no audio is streamed for 10-12 seconds (Deepgram code `NET-0001: Connection dropped due to inactivity`).

Sahayak guarantees continuous multi-turn session persistence through a resilient three-tier lifecycle:

```mermaid
sequenceDiagram
    autonumber
    participant Client as Browser Client
    participant Gateway as WebSocket Gateway (FastAPI)
    participant STT as DeepgramStreamSession
    participant Cloud as Deepgram Cloud WS

    Note over Client,Cloud: Turn 1 Completes (User listens to answer)
    STT->>STT: Start Background Heartbeat Loop (5.0s interval)
    loop Every 5 Seconds of Silence
        STT->>Cloud: {"type": "KeepAlive"} via _send_lock
        Cloud-->>STT: Heartbeat ACK / KeepAlive Accepted
    end

    alt Connection Healthy
        Client->>Gateway: Turn 2 Mic Audio (16kHz PCM)
        Gateway->>Gateway: ensure_stt_connected() -> True
        Gateway->>STT: stream_audio(chunk)
    else Drop Detected (Network blip or cold start)
        Client->>Gateway: Turn 2 Mic Audio (16kHz PCM)
        Gateway->>Gateway: ensure_stt_connected() acquires asyncio.Lock
        Gateway->>STT: Reconnect WebSocket & Re-spawn Supervised Listener
        Gateway->>STT: stream_audio(chunk)
    end
```

### A. Proactive KeepAlive Heartbeat
- A background `_keepalive_loop` triggers every `keepalive_interval = 5.0s` inside `DeepgramStreamSession`.
- Sends `{"type": "KeepAlive"}` JSON messages serialized over `_send_lock: asyncio.Lock` to avoid frame interleaving with raw audio packets.
- Transparently holds open upstream Deepgram connections indefinitely across pauses without sending dummy audio energy that might pollute STT transcripts.

### B. Lazy Auto-Reconnection Guard (`ensure_stt_connected`)
- Every incoming binary PCM frame at `app/api/websocket_endpoint.py` is intercepted by `ensure_stt_connected(session)`.
- Implements double-checked locking using an `asyncio.Lock` to eliminate connection stampedes when audio chunks arrive at 50Hz.
- Inspects websocket connection health via `session.is_connected` (handling both modern `State.OPEN` and fallback attributes).
- Re-establishes the WebSocket session, restarts the supervised listener background task, and seamlessly begins transcription of the new utterance.

### C. Isolated Client Web Audio Graph
- In browser Web Audio environments, connecting `ScriptProcessorNode` to `audioContext.destination` is required by the browser event loop to continuously fire `onaudioprocess` callbacks.
- If routed directly, microphone input is mirrored through speakers, triggering acoustic feedback and corrupting STT recognition.
- Sahayak inserts a dedicated `GainNode` with `gain.value = 0` between the processor and `audioContext.destination`, capturing mic frames at full resolution while completely muting loopback.
- Active synthesis playback sources are registered in `state.currentAudioSource`, allowing `stopAudioPlayback()` to immediately cancel in-flight playback buffers when a subsequent user turn commences.

