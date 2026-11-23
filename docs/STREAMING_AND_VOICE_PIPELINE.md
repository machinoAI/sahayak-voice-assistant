# Streaming Voice Pipeline Architecture

The end-to-end voice pipeline coordinates Speech-to-Text (STT), conversational memory, Large Language Model (LLM) token streaming, sentence boundary splitting, and neural Text-to-Speech (TTS) synthesis with multi-turn session persistence.

---

## 1. Multi-Provider Speech-to-Text (STT) Engines

Sahayak consumes live microphone audio at **16kHz mono, 16-bit linear PCM** in 20ms frames (640 bytes per chunk) across three primary STT engines:

### A. Deepgram Streaming STT (`app/adapters/stt/deepgram.py`)
- **Model**: `nova-2-general` with low-latency endpointing (`endpointing=300ms`, `interim_results=True`).
- **Multilingual Parameterization**: Supports `en-IN` (Indian English), `hi` (Hindi), and `multi` (code-switched Hinglish auto-detection).
- **Inactivity KeepAlive Protocol**: Sends `{"type": "KeepAlive"}` control frames every 5.0s during idle periods to prevent upstream socket dropouts.
- **Lazy Auto-Reconnection**: Reconnects silently upon upstream socket resets with stampede protection via `stt_reconnect_lock`.

### B. Sarvam AI Indic ASR (`app/adapters/stt/sarvam.py`)
- **Model**: `saaras:v3` for high-accuracy phonetic transcription across 10+ Indian languages (Hindi, Bengali, Tamil, etc.).
- **Buffered Streaming**: Batches audio frames in-memory and converts to linear PCM WAV format on utterance boundary.

### C. Local Faster-Whisper (`app/adapters/stt/local_whisper.py`)
- **Offline Zero-Cost Engine**: Powered by `faster-whisper` and CTranslate2, executing quantized Whisper models (`tiny`, `base`, `small`, `medium`) locally without cloud API keys or internet access.
- **Non-Blocking Inference**: Wraps synchronous model execution in `asyncio.to_thread` to preserve FastAPI WebSocket event loop responsiveness.
- **Singleton Model Caching**: Heavy model weights are loaded once into a process-level cache keyed by `(model_size, device, compute_type)`, eliminating 1–2s load times on subsequent turns.
- **Real-Time Voice Activity Detection (VAD)**:
  - Computes RMS audio energy per 20ms PCM chunk (`samples = np.frombuffer(chunk, dtype=np.int16)`).
  - Detects active speech when $\text{RMS} \ge 250.0$.
  - Emits interim transcripts during sustained speech segments.
- **Silence Endpointing (500ms)**:
  - When speech stops and silence accumulates to $\ge 500\text{ms}$, the segment is finalized, transcribed via CTranslate2, and dispatched as a `final` transcript event.
- **Continuous Multi-Turn Session Persistence**:
  - Exposes `@property def is_connected(self) -> bool` to integrate seamlessly with the gateway's `ensure_stt_connected()` guard.
  - Keeps the active session open across multiple user conversational turns without reconnecting.

### D. Server-Side Barge-In Detection
```python
if orchestrator.is_speaking():
    logger.info(f"[BARGE_IN] User interruption detected during speech: '{text[:30]}'")
    await orchestrator.handle_user_interruption(websocket, session_memory=session_memory)
```
If the user speaks while the assistant is streaming tokens or playing audio, the active turn is cancelled in $<40\text{ms}$ and the audio playback buffer is flushed immediately.

---

## 2. Multi-Turn Session Memory (`SessionMemory`)

Located at [`app/services/session_memory.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/services/session_memory.py), the memory buffer maintains a connection-scoped rolling window of the last **3 dialogue turns**:

1. **Multilingual Pronoun Query Augmentation**:
   When a user query contains ambiguous pronouns or back-references (English: *"What services does it provide?"*, *"Tell me more about them"*; Hindi: *"इसके क्या लाभ हैं?"*, *"वह क्या है?"*, *"उनकी पात्रता क्या है?"*):
   ```python
   # Detects English pronouns (it, they, them, this, that) and Indic pronouns (यह, वह, इनका, उनका, इन्हें, उन्हें, इस, उस)
   if self._contains_pronouns(current_query):
       augmented_query = f"{last_turn.user_query} {current_query}"
   ```
   This ensures Qdrant retrieves documents relevant to the true subject (`"What is Sahayak? What services does it provide?"`) rather than an ambiguous fragment.
2. **Conversation History Prompt Injection**:
   Previous turns are formatted into the LLM system prompt:
   ```
   Conversation History:
   User: What is Sahayak?
   Assistant: Sahayak is an ultra-low latency voice assistant designed for Indian multilingual queries.
   ```
3. **Interruption Tagging**: If the user barged in during an answer, the partial response is tagged `[User interrupted here]` so the LLM knows the user cut in.

---

## 3. Incremental Sentence Boundary Splitter

To achieve sub-second TTFAB, we cannot wait for the LLM to finish generating an entire paragraph. Audio synthesis must begin on the **very first completed sentence**.

Located in [`app/services/voice_orchestrator.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/services/voice_orchestrator.py):
```python
RAW_DELIMITER_REGEX = re.compile(r'([^.!?\n।]+[.!?\n।]+)')
ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "prof.", "e.g.", "i.e.", "rs.", "vs.", "approx."}
```

### Abbreviation, Currency & Danda Protection
Naive regex splitters break on common Indian honorifics, currencies, and Devanagari full stops (danda `।`):
- Checks the word preceding the delimiter: if it matches `ABBREVIATIONS` or digits followed by a period (`r'\d\.$'`), splitting is suppressed and token buffering continues.
- Accurately splits on Devanagari purna viram (`।`) for Hindi speech generation.
- Once a legitimate punctuation boundary is reached, the sentence is extracted cleanly, and the remainder is retained without character loss.

---

## 4. Multi-Provider LLM Streaming & Prefix Continuation Failover

Located at [`app/adapters/llm/`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/llm/) and [`app/adapters/failover.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/failover.py):

- **Consolidated `OpenAICompatibleLLMAdapter`**:
  - Implements `LLMClientProtocol` over standard OpenAI chat completion streaming endpoints.
  - Covers **Groq LPU** (`openai/gpt-oss-120b`, `llama-3.3-70b-versatile`), **OpenAI** (`gpt-4o`, `gpt-4o-mini`), **Google Gemini** (`gemini-3.8-flash`), and local **Ollama** (`llama3.2`).
  - Automatically hides internal reasoning tokens (`reasoning_format="hidden"`) on Groq to preserve TTFT.
- **`AnthropicClaudeAdapter`**:
  - Native streaming integration via `AsyncAnthropic` (`claude-3-5-sonnet`, `claude-3-5-haiku`).
- **Prefix Continuation Failover**:
  - When a primary LLM (e.g., Groq) fails after speaking sentence $S_1$, `FailoverLLMAdapter` captures the error, respects `Retry-After` cooldowns, and passes $S_1$ as assistant history to the fallback provider.
  - The fallback provider generates only the missing remainder without stuttering or repeating prior speech.

---

## 5. Multi-Provider Neural TTS Architecture & Turn Stickiness

Located at [`app/adapters/tts/`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/tts/) and [`app/adapters/failover_tts.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/failover_tts.py):

- **Cartesia Sonic (`CartesiaTTSAdapter`)**:
  - Raw 16kHz linear PCM stream over WebSocket.
  - TTFAB: **$180\text{ms} - 250\text{ms}$** for English queries.
- **Microsoft Edge-TTS (`EdgeTTSAdapter`)**:
  - Free neural synthesis with zero API keys (`en-IN-NeerjaNeural`, `hi-IN-SwaraNeural`).
  - Delivers native Hindi pronunciation for Devanagari text.
- **ElevenLabs Streaming (`ElevenLabsTTSAdapter`)**:
  - High-fidelity 16kHz linear PCM streaming using `AsyncElevenLabs`.
- **Turn Stickiness (`FailoverTTSAdapter`)**:
  - Prevents mid-turn voice oscillations. If sentence $S_1$ fails over to a secondary provider, sentences $S_2$ and $S_3$ in the same turn remain on that provider until the turn completes.

---

## 6. Connection-Scoped Session Context (`VoiceSessionContext`)

Located at [`app/services/voice_orchestrator.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/services/voice_orchestrator.py):

- Encapsulates mutable turn tasks (`active_generation_task`, `active_tts_task`), sentence queues, and locks per active WebSocket socket.
- Eliminates singleton race conditions across concurrent users.
- Supports handshake query negotiation (`/ws/voice?stt=...&llm=...&tts=...&lang=...`) and dynamic mid-session switching via `SET_PROVIDER` frames.

---

## 7. Event Loop-Aware Client Pool Management

To eliminate `RuntimeError: Event loop is closed` errors across independent asyncio loops (e.g., in automated tests, background subprocesses, or multi-turn test runners):
- `OpenAICompatibleLLMAdapter`, `AnthropicClaudeAdapter`, and `HTTPClientManager` dynamically detect the active event loop via `asyncio.get_running_loop()`.
- Client instances are cached alongside their owning event loop reference.
- When an invocation occurs on a new or revived event loop, adapters lazily instantiate a fresh client, guaranteeing that in-flight network sockets and HTTP keepalive pools remain bound to the active loop.
