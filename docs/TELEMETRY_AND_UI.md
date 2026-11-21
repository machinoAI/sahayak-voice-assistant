# Real-Time Telemetry & Inspector UI

Sahayak includes a self-contained, real-time diagnostic testing interface served directly by FastAPI at **`http://localhost:8000/`**. 

It visually exposes the decision tree, speculative execution, tool calls, and LLM token streaming in real time, featuring an animated cubic Bézier spline canvas that tracks every reasoning step.

---

## 1. WebSocket Protocol Specification (`/ws/voice`)

The WebSocket endpoint manages bi-directional communication between client and server:

### Connection Handshake Negotiation
Clients can negotiate connection-scoped model profiles during the WebSocket handshake:
`/ws/voice?stt=deepgram&llm=groq&tts=cartesia&lang=auto`

### Client $\to$ Server Frames

| Frame Type | Format | Description |
| :--- | :--- | :--- |
| **`Binary PCM Audio`** | Raw bytes | 16kHz, 16-bit signed integer, mono PCM chunks (20ms = 640 bytes). Piped directly to active STT provider. |
| **`FINAL_TRANSCRIPT`** | JSON | `{"event": "FINAL_TRANSCRIPT", "text": "..."}`. Manually submits a text query, bypassing microphone STT. |
| **`SET_LANGUAGE`** | JSON | `{"event": "SET_LANGUAGE", "language": "hi" \| "en-IN" \| "en" \| "multi"}`. Switches STT language and steers downstream prompt and TTS backend dynamically. |
| **`SET_PROVIDER`** | JSON | `{"event": "SET_PROVIDER", "stt": "sarvam", "llm": "gemini", "tts": "edge"}`. Hot-swaps one or more active providers within the connection-scoped session context. |
| **`USER_BARGE_IN`** | JSON | `{"event": "USER_BARGE_IN"}`. Immediately triggers server-side task cancellation and buffer flush. |
| **`RESET_SESSION`** | JSON | `{"event": "RESET_SESSION"}`. Wipes the rolling multi-turn conversational memory. |

### Server $\to$ Client Frames

| Frame Type | Format | Description |
| :--- | :--- | :--- |
| **`INTERIM_TRANSCRIPT`** | JSON | `{"event": "INTERIM_TRANSCRIPT", "text": "..."}`. Live unfinalized speech hypothesis from active STT. |
| **`FINAL_TRANSCRIPT`** | JSON | `{"event": "FINAL_TRANSCRIPT", "text": "..."}`. Speech endpoint finalized; triggers turn execution. |
| **`LANGUAGE_CHANGED`** | JSON | `{"event": "LANGUAGE_CHANGED", "language": "hi"}`. Confirms active session language. |
| **`PROVIDER_CHANGED`** | JSON | `{"event": "PROVIDER_CHANGED", "stt": "sarvam", "llm": "gemini", "tts": "edge"}`. Confirms dynamic provider re-binding. |
| **`PIPELINE_STEP`** | JSON | `{"event": "PIPELINE_STEP", "step": "...", "elapsed_ms": 12.4, "data": {...}}`. Millisecond-precision telemetry for each pipeline stage. |
| **`LLM_TOKEN`** | JSON | `{"event": "LLM_TOKEN", "token": "...", "token_count": 14}`. Live streaming token off the wire. |
| **`CLEAR_AUDIO_BUFFER`** | JSON | `{"event": "CLEAR_AUDIO_BUFFER"}`. Commands client to immediately mute and discard pending audio packets. |
| **`Binary Audio Chunks`** | Raw bytes | Synthesized 16kHz PCM audio packets (Cartesia, ElevenLabs) or MP3 packets (Edge-TTS). |

---

## 2. The Neural Decision Tree Canvas

Rendered with high-DPI HTML5 Canvas 2D (`app/static/index.html`):

- **Visual Motif**: Dark slate background (`#060910`) with a subtle radial dot-grid pattern.
- **Bézier Spline Routing**:
  - **Root Node**: The transcribed user query.
  - **Branch 1 (Top Sweep)**: Semantic Router (OATS centroid) $\to$ Displays classified intent and sub-millisecond latency.
  - **Branch 2 (Center-Top)**: Qdrant Vector Search $\to$ Displays top similarity score ($0.0 \dots 1.0$) and search latency.
  - **Branch 3 (Center-Bottom)**: Speculative Tavily Web Search:
    - If CRAG confidence is high ($\ge 0.82$), the branch terminates with a **Pruned `(x)` marker** (circle with cross) indicating search cancellation.
    - If confidence is low or ambiguous, the branch illuminates into a glowing **Active `(o)` marker** with retrieved web sources.
  - **Convergence**: CRAG Decision Gate $\to$ Displays `[CORRECT / AMBIGUOUS / INCORRECT]`.
  - **Branch 4 (Forward Sweep)**: Groq LLM Token Stream $\to$ Displays TTFT timer.
  - **Terminal Node**: Cartesia / Edge-TTS Audio Output $\to$ Displays TTFAB and audio chunks delivered.
- **Particle Dynamics**: Glowing cyan/emerald particles travel along active Bézier curves via `requestAnimationFrame`, visually representing data flow.

---

## 3. Web Audio API Engine

1. **Microphone Capture & Zero-Gain Loopback Isolation**:
   - Prompts `navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000 } })`.
   - Uses `ScriptProcessorNode` (2048 samples = 128ms) to downsample Float32 audio into `Int16Array` linear PCM buffers.
   - **Zero-Gain Loopback Prevention**: Modern browsers (Chrome, Edge, Safari) require `ScriptProcessorNode` to be connected downstream to an `AudioDestinationNode` for `onaudioprocess` events to continuously fire. Connecting directly routes raw microphone audio straight through the client's speakers, causing acoustic feedback loops that destroy STT transcription accuracy. Sahayak connects the processor through a `GainNode` with `gain.value = 0` before routing to `audioContext.destination`, ensuring continuous audio processing with complete speaker silence.
   - Streams binary frames to `/ws/voice`.

2. **Audio Playback Engine & Source Lifecycle Tracking**:
   - Inspects incoming binary headers to auto-detect **raw PCM (`pcm_s16le`)** vs. **MP3 (`ID3` or `0xFF 0xFB`)**.
   - Raw PCM chunks are converted to Float32 `AudioBuffer` and queued into a gapless playback schedule.
   - **Active Source Tracking (`stopAudioPlayback`)**: Every instantiated `AudioBufferSourceNode` is registered in `state.currentAudioSource`. When the user interrupts (`USER_BARGE_IN`), or when a new turn begins, `stopAudioPlayback()` immediately executes `source.stop()`, clears queued chunks, and resets `nextPlayTime = 0`.
   - Features a real-time oscilloscope visualizer canvas displaying the waveform amplitude of synthesized speech.
   - Flushes queued buffers instantly on `CLEAR_AUDIO_BUFFER`.

---

## 4. UI Controls & Interactive Presets

### Dynamic Multi-Provider & Language Selectors
Located in the top navigation bar, four synchronized dropdown selectors allow one-click switching:
- **Speech-to-Text (STT)**:
  - `🎙️ Deepgram Nova-2`: Real-time streaming WebSocket with KeepAlive.
  - `🎙️ Sarvam Indic ASR`: High-accuracy Indic multilingual ASR with client buffering.
  - `🎙️ Local Whisper`: Zero-cost offline local development profile.
- **Large Language Model (LLM)**:
  - `⚡ Groq LPU`: Ultra-fast inference on `openai/gpt-oss-120b`.
  - `✨ Gemini Flash`: Google Gemini 3.8 Flash via OpenAI-compatible endpoint.
  - `🤖 OpenAI GPT-4o`: OpenAI GPT-4o-mini completion stream.
  - `🧠 Claude 3.5 Haiku`: Anthropic Claude native streaming.
  - `💻 Ollama (Local)`: Local self-hosted OpenAI-compatible endpoint.
- **Text-to-Speech (TTS)**:
  - `🔊 Cartesia Sonic`: 16kHz linear PCM baseline for English ($180\text{ms}$ TTFAB).
  - `🔊 Edge-TTS (Free)`: Zero-cost neural synthesis for Indic & English.
  - `🔊 ElevenLabs Turbo`: High-fidelity low-latency 16kHz PCM voice.
- **Language Selector**:
  - `🌐 Auto-Detect` (`auto`), `🇮🇳 हिन्दी` (`hi`), `🇬🇧 English` (`en`).

Changing any provider immediately transmits a `SET_PROVIDER` WebSocket control frame, re-binding the connection-scoped session context without dropping the WebSocket.

### One-Click Interactive Presets
Located directly above the input bar in the UI:

| Preset Chip | Query | Purpose |
| :--- | :--- | :--- |
| **🌾 PM Kisan (High Conf)** | *"What is the eligibility criteria for PM Kisan scheme?"* | Tests CRAG `CORRECT` state ($\ge 0.82$): Local knowledge authoritative, Tavily search pruned with `(x)` marker. |
| **🌦️ Today's News (Temporal)** | *"What is the latest news update today?"* | Tests `REALTIME_TEMPORAL` classification and parallel speculative web search dispatch. |
| **⚖️ Fertilizer Subsidy (Ambiguous)** | *"Did the government change the fertilizer subsidy rules?"* | Tests CRAG `AMBIGUOUS` state: Merges local baseline rules with live web search facts. |
| **🌍 US President (Out of Domain)** | *"Who was the first president of the United States?"* | Tests CRAG `INCORRECT` state ($< 0.55$): Local docs suppressed; Tavily web search answers the question. |

---

## 5. Favicon & Static Asset Handling

- **Inline SVG Favicon**: To eliminate continuous `404 Not Found` log spam when browsers request `/favicon.ico`, FastAPI serves an inline vector microphone SVG with a dark slate background, warm saffron mic body, and cyan sound wave accents matching Sahayak's branding.
- **Self-Contained Static Assets**: The single-page interface is served from [`app/static/index.html`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/static/index.html), utilizing CSS variables and canvas rendering without requiring external build pipelines or node tooling. |
