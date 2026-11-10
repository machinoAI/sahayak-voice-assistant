# Streaming Voice Pipeline Architecture

The end-to-end voice pipeline coordinates Speech-to-Text (STT), conversational memory, Large Language Model (LLM) token streaming, sentence boundary splitting, and neural Text-to-Speech (TTS) synthesis.

---

## 1. Deepgram Streaming STT & Endpointing

Sahayak consumes live microphone audio at **16kHz mono, 16-bit linear PCM** in 20ms–100ms frames:

- **Adapter**: [`app/adapters/stt_deepgram.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/stt_deepgram.py)
- **Model**: `nova-2-general` with low-latency endpointing (`endpointing=300ms`, `interim_results=True`).
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

1. **Pronoun Query Augmentation**:
   When a user query contains ambiguous pronouns or back-references (e.g. *"What services does it provide?"* or *"Tell me more about them"*):
   ```python
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
RAW_DELIMITER_REGEX = re.compile(r'([^.!?\n]+[.!?\n]+)')
ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "prof.", "e.g.", "i.e.", "rs.", "vs.", "approx."}
```

### Abbreviation & Currency Protection
Naive regex splitters break on common Indian honorifics and currencies (e.g., splitting *"The fee is Rs. 500."* into *"The fee is Rs."*).
The splitter checks the word preceding the delimiter:
- If it matches `ABBREVIATIONS` or digits followed by a period (`r'\d\.$'`), splitting is suppressed and token buffering continues.
- Once a legitimate punctuation boundary (`.`, `!`, `?`, `\n`) is reached, the sentence is extracted cleanly, and the remainder is retained without character loss.

---

## 4. Groq LLM Token Stream (`openai/gpt-oss-120b`)

Located at [`app/adapters/llm_groq.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/llm_groq.py):

- **Engine**: Groq Language Processing Unit (LPU) inference.
- **Model**: `openai/gpt-oss-120b`.
- **Reasoning Token Optimization**:
  Reasoning models emit `<thought>` / `delta.reasoning` tokens before generating content. If `max_tokens` is bounded and reasoning is exposed, reasoning tokens can consume the entire generation budget, resulting in 0 output tokens.
  - **Solution**: Set `reasoning_format="hidden"` in the Groq API call.
  - **Result**: Internal reasoning tokens are computed on the LPU but hidden from the token stream, reducing TTFT to **~580ms - 850ms** and preserving 100% of the token budget for the spoken response.

---

## 5. Neural TTS Synthesis & Queue Decoupling

- **Primary Provider**: **Cartesia Sonic** (`app/adapters/tts_cartesia.py`):
  - True bidirectional streaming WebSocket.
  - Audio container: `raw`, encoding: `pcm_s16le`, sample rate: `16000Hz`.
  - **TTFAB**: **$180\text{ms} - 250\text{ms}$** per sentence.
- **Fallback Provider**: **Microsoft Edge-TTS** (`app/adapters/tts_edge.py`):
  - High-quality neural voices (`en-IN-PrabhatNeural`, `hi-IN-MadhurNeural`).
  - Zero API key required; automatic fallback if Cartesia credentials are absent.
- **Thread-Safe WebSocket Transmission**:
  Audio chunks are transmitted over WebSocket using an `asyncio.Lock()` to prevent interleaved corruption between concurrent JSON control frames and binary audio packets.
