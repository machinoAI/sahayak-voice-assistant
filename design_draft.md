# Technical Design: Cartesia Sonic Streaming TTS Adapter

**Feature Name**: Low-Latency Cartesia Sonic WebSocket TTS Adapter  
**Author**: Amankumar006  
**Status**: Implemented & Verified  
**Target File**: `app/adapters/tts_cartesia.py`  
**Target Project**: `sahayak-voice-assistant`  

---

## 1. Overview, Goals & Problem Statement

### 1.1 The Problem
In real-time voice assistants, the delay between when a user stops speaking and when the assistant's voice begins playing determines whether the conversation feels natural or sluggish. The benchmark for human conversation pause is **under 750 milliseconds**.

Previously, the default TTS implementation in Sahayak relied on Edge-TTS:
1. **High Initial Audio Latency (TTFAB)**: Edge-TTS takes **680ms to 950ms** to return its first audio chunk. Combined with Groq LLM first-token generation (~600ms) and retrieval (~5ms), total response time reaches **1.3 to 1.6 seconds**, causing dead air.
2. **Compressed Audio Format**: Edge-TTS emits compressed MP3 audio chunks. The assistant pipeline prefers raw 16kHz linear PCM to match input audio framing and eliminate client-side codec negotiation or transcoding overhead.
3. **No Upstream Barge-in Cancellation**: Edge-TTS provides no protocol mechanism to halt generation on the provider's servers when a user interrupts.

### 1.2 Overview
Implemented a streaming Text-to-Speech adapter implementing `TTSClientProtocol` using **Cartesia Sonic** (`wss://api.cartesia.ai/tts/websocket`).

Cartesia Sonic is built for real-time conversational agents, using state-space model architecture to achieve **150ms to 350ms Time-to-First-Audio-Byte (TTFAB)**. The adapter:
- Maintains a persistent, bi-directional WebSocket connection with Cartesia's inference API using `certifi` SSL verification.
- Streams text sentences incrementally and receives raw, uncompressed 16kHz 16-bit mono PCM audio packets directly.
- Implements an automated failover to `EdgeTTSAdapter` if Cartesia credentials are missing, rate-limited, or encounter socket errors.

### 1.3 Goals Met
- **Low-Latency Streaming**: Measured live TTFAB of **~290–330ms** (down from Edge-TTS's ~680ms).
- **Native 16kHz PCM Output**: Emits raw 16-bit linear PCM mono audio at 16,000 Hz, matching `app/core/audio_config.py` without server transcoding.
- **Graceful Fallback**: Automatically routes synthesis requests to `EdgeTTSAdapter` if `CARTESIA_API_KEY` is absent or unreachable.
- **Contract Conformance**: Adheres strictly to `TTSClientProtocol` (`async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]`).

---

## 2. Technical Architecture & Live Verification

```
+-------------------------------------------------------------+
|                     VoiceRAGOrchestrator                    |
+-------------------------------------------------------------+
                               |
                   sentence_queue.get()
                               |
                               v
+-------------------------------------------------------------+
|                      CartesiaTTSAdapter                     |
|                                                             |
|  - client.tts.websocket(options={"ssl": certifi_context})   |
|  - output_format: 16kHz pcm_s16le raw mono                 |
|  - model: sonic-latest                                      |
|  - voice_id: 30894953-bcce-41fe-892c-15ce19c843ff          |
|  - On Exception / Missing Key -> Fallback to EdgeTTSAdapter |
+-------------------------------------------------------------+
                               |
                    yields raw audio chunks
                               |
                               v
+-------------------------------------------------------------+
|                FastAPI WebSocket Client (/ws/voice)          |
+-------------------------------------------------------------+
```

### 2.1 Test Verification
```bash
../.venv/bin/pytest tests/
======================== 15 passed in 8.19s ========================
```
- `test_cartesia_adapter_fallback_without_key`: Verified fallback to Edge-TTS when key is None.
- `test_cartesia_live_stream_synthesis`: Verified live WebSocket streaming with real API key (TTFAB: 292.4ms, 14 chunks, 76.8 KB audio).
- `test_full_pipeline_step_by_step_tracking`: Verified end-to-end pipeline execution with live Groq LLM + Qdrant + Cartesia/Edge-TTS.
