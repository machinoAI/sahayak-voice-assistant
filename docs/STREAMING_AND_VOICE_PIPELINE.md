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

## 4. Groq LLM Token Stream (`openai/gpt-oss-120b`) & Multilingual Steering

Located at [`app/adapters/llm_groq.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/llm_groq.py):

- **Engine**: Groq Language Processing Unit (LPU) inference.
- **Model**: `openai/gpt-oss-120b`.
- **Reasoning Token Optimization**:
  Reasoning models emit `<thought>` / `delta.reasoning` tokens before generating content.
  - **Solution**: Set `reasoning_format="hidden"` in the Groq API call and set completion token budget to 1200.
  - **Result**: Internal reasoning tokens are computed on the LPU but hidden from the token stream, reducing TTFT to **~580ms - 850ms** and preserving 100% of the token budget for the spoken response.
- **Strict Language Steering**:
  - If input is Hindi or code-switched Hinglish, the system prompt instructs the model to reply strictly in grammatically correct Hindi using Devanagari script.
  - If input is English, the model responds in standard English.
  - Constrains responses to 1–2 spoken sentences (<35 words) for rapid speech pacing.

---

## 5. Dual-Tier Neural TTS Architecture & Turn Boundary Cleanup

- **Tier 1: English Low-Latency Synthesis — Cartesia Sonic** (`app/adapters/tts_cartesia.py`):
  - Used for English dialogue turns (`en-IN`, `en-US`).
  - True bidirectional streaming WebSocket.
  - Voice: Cartesia Sonic English voice (`c45bc5ec-5968-4f0b-a898-92743eed0000`).
  - Audio container: `raw`, encoding: `pcm_s16le`, sample rate: `16000Hz`.
  - **TTFAB**: **$180\text{ms} - 250\text{ms}$** per sentence.
- **Tier 2: Indic Neural Voice Synthesis — Microsoft Edge-TTS** (`app/adapters/tts_edge.py`):
  - Used for Hindi and Hinglish dialogue turns containing Devanagari Unicode.
  - Voices: `hi-IN-SwaraNeural` (female) and `hi-IN-MadhurNeural` (male).
  - High-fidelity pronunciation of Hindi phonemes and Devanagari numerals.
  - **TTFAB**: **$400\text{ms} - 550\text{ms}$** per sentence.
- **Clean Turn Boundary Transitions**:
  - In `VoiceRAGOrchestrator.process_voice_turn()`:
    - Before initiating a new turn, cancels both `self.active_generation_task` (LLM generation) and `self.active_tts_task` (audio synthesis).
    - Flushes and re-instantiates `self.sentence_queue = asyncio.Queue()` so residual tokens from prior turns never leak into the new turn.
- **Thread-Safe WebSocket Transmission**:
  Audio chunks are transmitted over WebSocket using an `asyncio.Lock()` to prevent interleaved corruption between concurrent JSON control frames and binary audio packets.
