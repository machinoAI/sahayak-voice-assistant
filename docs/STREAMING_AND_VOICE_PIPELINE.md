# Streaming Voice Pipeline Architecture

The end-to-end voice pipeline coordinates Speech-to-Text (STT), conversational memory, Large Language Model (LLM) token streaming, sentence boundary splitting, and neural Text-to-Speech (TTS) synthesis with multi-turn session persistence.

---

## 1. Deepgram Streaming STT, Multilingual Support & KeepAlive

Sahayak consumes live microphone audio at **16kHz mono, 16-bit linear PCM** in 20ms–100ms frames:

- **Adapter**: [`app/adapters/stt_deepgram.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/stt_deepgram.py)
- **Model**: `nova-2-general` with low-latency endpointing (`endpointing=300ms`, `interim_results=True`).
- **Multilingual Language Parameterization**:
  - `en-IN`: Indian English dialect with domain terminology.
  - `hi`: Hindi spoken input.
  - `multi`: Multilingual auto-detection for code-switched Hinglish.
  - Dynamically configured per WebSocket session upon connection and re-bound in-flight via `SET_LANGUAGE` client frames.
- **Heartbeat & Inactivity KeepAlive Protocol**:
  - Deepgram streaming WebSockets enforce an aggressive 10–12 second inactivity timeout. To prevent the upstream connection from dropping while the user listens to the assistant's reply:
  - `DeepgramStreamSession._keepalive_loop()` runs an autonomous background monitor that transmits `{"type": "KeepAlive"}` JSON frames every 5.0 seconds when idle audio time exceeds 4.0s.
  - Keepalive transmission is synchronized with audio streaming using `async with self._send_lock:`.
- **Lazy Auto-Reconnection & Stampede Protection**:
  - In [`app/api/websocket_endpoint.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/api/websocket_endpoint.py), `ensure_stt_connected()` inspects `session.is_connected` before forwarding incoming binary frames.
  - If upstream socket resets occur, the gateway automatically re-establishes the Deepgram connection and restarts the transcript listener under an `asyncio.Lock()` to prevent connection stampedes.
- **Server-Side Barge-In Detection**:
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
  - Covers **Groq LPU** (`openai/gpt-oss-120b`, `llama-3.3-70b-versatile`), **OpenAI** (`gpt-4o`, `gpt-4o-mini`), **Google Gemini** (`gemini-2.0-flash`), and local **Ollama** (`llama3.2`).
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
