# Real-Time Telemetry & Inspector UI

Sahayak includes a self-contained, real-time diagnostic testing interface served directly by FastAPI at **`http://localhost:8000/`**. 

It visually exposes the decision tree, speculative execution, tool calls, and LLM token streaming in real time, featuring an animated cubic Bézier spline canvas that tracks every reasoning step.

---

## 1. WebSocket Protocol Specification (`/ws/voice`)

The WebSocket endpoint manages bi-directional communication between client and server:

### Client $\to$ Server Frames

| Frame Type | Format | Description |
| :--- | :--- | :--- |
| **`Binary PCM Audio`** | Raw bytes | 16kHz, 16-bit signed integer, mono PCM chunks (20ms = 640 bytes). Piped directly to Deepgram STT. |
| **`FINAL_TRANSCRIPT`** | JSON | `{"event": "FINAL_TRANSCRIPT", "text": "..."}`. Manually submits a text query, bypassing microphone STT. |
| **`USER_BARGE_IN`** | JSON | `{"event": "USER_BARGE_IN"}`. Immediately triggers server-side task cancellation and buffer flush. |
| **`RESET_SESSION`** | JSON | `{"event": "RESET_SESSION"}`. Wipes the rolling multi-turn conversational memory. |

### Server $\to$ Client Frames

| Frame Type | Format | Description |
| :--- | :--- | :--- |
| **`INTERIM_TRANSCRIPT`** | JSON | `{"event": "INTERIM_TRANSCRIPT", "text": "..."}`. Live unfinalized speech hypothesis from Deepgram. |
| **`FINAL_TRANSCRIPT`** | JSON | `{"event": "FINAL_TRANSCRIPT", "text": "..."}`. Speech endpoint finalized; triggers turn execution. |
| **`PIPELINE_STEP`** | JSON | `{"event": "PIPELINE_STEP", "step": "...", "elapsed_ms": 12.4, "data": {...}}`. Millisecond-precision telemetry for each pipeline stage. |
| **`LLM_TOKEN`** | JSON | `{"event": "LLM_TOKEN", "token": "...", "token_count": 14}`. Live streaming token off the Groq wire. |
| **`CLEAR_AUDIO_BUFFER`** | JSON | `{"event": "CLEAR_AUDIO_BUFFER"}`. Commands client to immediately mute and discard pending audio packets. |
| **`Binary Audio Chunks`** | Raw bytes | Synthesized 16kHz PCM audio packets from Cartesia Sonic or MP3 packets from Edge-TTS. |

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

1. **Microphone Capture**:
   - Prompts `navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000 } })`.
   - Uses `ScriptProcessorNode` (2048 samples = 128ms) to downsample Float32 audio into `Int16Array` linear PCM buffers.
   - Streams binary frames to `/ws/voice`.
2. **Audio Playback Engine**:
   - Inspects incoming binary headers to auto-detect **raw PCM (`pcm_s16le`)** vs. **MP3 (`ID3` or `0xFF 0xFB`)**.
   - Raw PCM chunks are converted to Float32 `AudioBuffer` and queued into a gapless playback schedule.
   - Features a real-time oscilloscope visualizer canvas displaying the waveform amplitude of synthesized speech.
   - Flushes queued buffers instantly on `CLEAR_AUDIO_BUFFER`.

---

## 4. One-Click Interactive Presets

Located directly above the input bar in the UI:

| Preset Chip | Query | Purpose |
| :--- | :--- | :--- |
| **🌾 PM Kisan (High Conf)** | *"What is the eligibility criteria for PM Kisan scheme?"* | Tests CRAG `CORRECT` state ($\ge 0.82$): Local knowledge authoritative, Tavily search pruned with `(x)` marker. |
| **🌦️ Today's News (Temporal)** | *"What is the latest news update today?"* | Tests `REALTIME_TEMPORAL` classification and parallel speculative web search dispatch. |
| **⚖️ Fertilizer Subsidy (Ambiguous)** | *"Did the government change the fertilizer subsidy rules?"* | Tests CRAG `AMBIGUOUS` state: Merges local baseline rules with live web search facts. |
| **🌍 US President (Out of Domain)** | *"Who was the first president of the United States?"* | Tests CRAG `INCORRECT` state ($< 0.55$): Local docs suppressed; Tavily web search answers the question. |
