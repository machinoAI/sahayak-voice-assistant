# Implementation Readiness Report: Indic & Multilingual Speech Support

**Target Document**: [`docs/designs/indic_multilingual_speech_support.md`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/docs/designs/indic_multilingual_speech_support.md)  
**Evaluated Scope**: Lines 207 to 301 (`Detailed Implementation Plan` & `Verification Plan`)  
**Standard**: `implementation-readiness-standard.md`  
**Evaluation Verdict**: **FAIL (Implementation Blocked - 5 Blockers, 5 Majors, 4 Nits)**

The Implementation Plan contains structural discrepancies against the existing codebase, specifies non-existent files and methods, omits critical wiring in WebSocket handling and dependency injection, and introduces breaking audio sample rate conflicts between server output and client playback buffers.

---

## Consolidated Findings by Priority

### 🔴 Blockers (Immediate Execution Breakages)

#### 1. Non-Existent File Path & Class Reference (`app/core/orchestrator.py` / `VoiceOrchestrator`)
* **Affected Scope**: Line 245, Line 248, Line 279
* **Discrepancy**:
  * The plan specifies modifying `app/core/orchestrator.py` and class `VoiceOrchestrator`.
  * The actual file is [`app/services/voice_orchestrator.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/services/voice_orchestrator.py) and the class is `VoiceRAGOrchestrator`.
  * The verification step `python -m py_compile ... app/core/orchestrator.py` will fail with `FileNotFoundError`.
* **Remediation**: Update target path to `app/services/voice_orchestrator.py` and target class to `VoiceRAGOrchestrator`.

#### 2. Non-Existent Method & Misplaced WebSocket Control Logic (`handle_websocket_message()`)
* **Affected Scope**: Line 249
* **Discrepancy**:
  * The plan claims `handle_websocket_message()` parses WebSocket JSON frames and invokes STT reconnection.
  * No such method exists on the orchestrator. Client WebSocket messages are received and processed inside `voice_websocket()` in [`app/api/websocket_endpoint.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/api/websocket_endpoint.py#L77-L105).
  * `app/api/websocket_endpoint.py` is omitted from the plan's target file list.
* **Remediation**: Add `app/api/websocket_endpoint.py` to the modification list. Specify exact parsing logic for `SET_LANGUAGE` control frames and session re-parameterization.

#### 3. Semantic Router Structural Disconnect (`_SCHEME_KEYWORDS` & `classify()`)
* **Affected Scope**: Lines 227–234
* **Discrepancy**:
  * The plan instructs modifying `_SCHEME_KEYWORDS`, `_TEMPORAL_KEYWORDS`, and `classify()`.
  * `SemanticRouterAdapter` contains none of these attributes or methods. It uses an OATS centroid embedding model with sparse n-gram features over seed exemplar sentences (`DEFAULT_LOCAL_SCHEME_SEED`, `DEFAULT_TEMPORAL_SEED`, `DEFAULT_OUT_OF_DOMAIN_SEED`), evaluated via `classify_intent(self, query: str) -> QueryIntent`.
  * Modifying non-existent variables will have zero effect on classification.
* **Remediation**: Detail exact Hindi Devanagari and Hinglish exemplar sentences to append to `DEFAULT_LOCAL_SCHEME_SEED` and `DEFAULT_TEMPORAL_SEED`. Specify the placement of `unicodedata.normalize("NFKC", text)` within `_extract_features()`.

#### 4. Non-Existent `SYSTEM_PROMPT` in `app/adapters/llm_groq.py`
* **Affected Scope**: Lines 235–244
* **Discrepancy**:
  * The plan directs prompt updates to `GroqLLMAdapter`.
  * `GroqLLMAdapter` has no prompt constants; it passes incoming compiled prompts directly to Groq.
  * The system prompt is constructed inside `VoiceRAGOrchestrator.process_voice_turn()` at [`voice_orchestrator.py#L524-L528`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/services/voice_orchestrator.py#L524-L528).
* **Remediation**: Move system prompt steering instructions from `llm_groq.py` to `voice_orchestrator.py`.

#### 5. Non-Existent `start_stream()` Method on `DeepgramSTTAdapter`
* **Affected Scope**: Lines 219–225
* **Discrepancy**:
  * The plan specifies modifying `start_stream(self, language: str = "auto")` on `DeepgramSTTAdapter`.
  * `DeepgramSTTAdapter` implements `create_stream_session()` and `stream_audio_frames()`. Connection management lives in `DeepgramStreamSession.start()`.
  * `DeepgramSTTAdapter` is an application singleton, whereas `DeepgramStreamSession` is created per WebSocket connection in `websocket_endpoint.py`.
* **Remediation**: Update `DeepgramSTTAdapter.create_stream_session()` to accept `language: str = "auto"` and configure `DeepgramStreamSession` query parameters on a per-connection basis.

---

### 🟡 Majors (High Implementation & Operational Risks)

#### 6. Audio Sample Rate & Encoding Incompatibility (24kHz vs 16kHz)
* **Affected Scope**: Lines 254–255
* **Discrepancy**:
  * The plan specifies standardizing output chunks to "24kHz 16-bit linear PCM".
  * The entire codebase is hardcoded to 16kHz: `TTSClientProtocol` specifies 16kHz, Cartesia outputs 16kHz, `index.html` creates 16kHz Web Audio contexts, and `client_stream.py` expects 16kHz.
  * Streaming 24kHz audio to clients expecting 16kHz causes 0.66x slowed-down, pitch-distorted playback.
  * Edge-TTS returns raw MP3 chunks, not linear PCM. The plan specifies no decoding library (`ffmpeg`, `pydub`, `miniaudio`) to convert MP3 to PCM.
* **Remediation**: Standardize the audio contract at 16kHz linear PCM. Specify how Edge-TTS MP3 chunks are decoded or leverage browser-side MP3 decoding (which `index.html` already supports).

#### 7. Undefined Dual-TTS Dependency Injection in `app/main.py`
* **Affected Scope**: Lines 250–253
* **Discrepancy**:
  * `VoiceRAGOrchestrator` accepts a single `tts: TTSClientProtocol`. `app/main.py` conditionally instantiates either Cartesia or Edge-TTS at startup.
  * The plan does not specify whether `VoiceRAGOrchestrator.__init__` accepts two separate TTS clients or whether a composite `DualLanguageTTSAdapter` should be created.
* **Remediation**: Define constructor signature changes in `VoiceRAGOrchestrator` or introduce a composite TTS adapter in `app/adapters/tts_composite.py`. Add `app/main.py` to the modification list.

#### 8. Missing Phasing and Incremental Checkpoints
* **Affected Scope**: Lines 207–274
* **Discrepancy**:
  * The plan presents a flat file list without execution sequencing, violating the Phasing requirement of the standard.
* **Remediation**: Partition implementation into sequential phases:
  * Phase 1: Configuration, Seed Exemplars & Router Normalization.
  * Phase 2: Per-Connection Deepgram STT Language Session Parameterization.
  * Phase 3: Orchestrator Dual-TTS Dispatch, System Prompt & WebSocket Control Frames.
  * Phase 4: Frontend Language Selector & Telemetry Display.
  * Phase 5: Automated Multilingual Unit Tests & CLI Benchmark Updates.

#### 9. Inexecutable Verification Command for Synthetic Speech Turns
* **Affected Scope**: Lines 289–299
* **Discrepancy**:
  * The command `python client_stream.py --say "..."` invokes `generate_synthetic_audio()` using Cartesia's English voice, which rejects Devanagari text.
  * `client_stream.py` lacks a `--language` flag and cannot emit `SET_LANGUAGE` control frames.
* **Remediation**: Add `client_stream.py` to the modification scope to support multilingual synthetic speech and language flag arguments, or specify verification via a recorded Hindi WAV file (`--file`).

#### 10. Missing Hindi Contextual Resolution in `SessionMemory`
* **Affected Scope**: Implicitly affects `app/services/session_memory.py`
* **Discrepancy**:
  * Multi-turn query augmentation in `SessionMemory` relies on hardcoded English pronoun lists (`PRONOUNS` = `["it", "this", "that", "they", ...]`).
  * Hindi queries using pronouns (`"यह"`, `"वह"`, `"इसका"`, `"उनका"`) will not trigger entity substitution.
* **Remediation**: Add `app/services/session_memory.py` to target files, expanding `PRONOUNS` with Devanagari demonstratives.

---

### 🟢 Nits (Precision & Cleanliness)

#### 11. Language Code Nomenclature Inconsistency (`auto` vs `multi`)
* **Affected Scope**: Line 30, Line 124, Line 214
* **Discrepancy**: Deepgram uses `detect_language=true`, while the document alternates between `auto` and `multi`.
* **Remediation**: Standardize on `auto` across all config keys and protocols.

#### 12. Underspecified Select Options in `app/static/index.html`
* **Affected Scope**: Lines 260–261
* **Discrepancy**: Omitting `value` attributes (`<option value="en">English</option>`, `<option value="hi">हिन्दी</option>`) causes `this.value` to default to display text.
* **Remediation**: Explicitly document the `<option>` markup with matching value keys.

#### 13. Dead Configuration Definition (`EDGE_TTS_INDIC_VOICE_MALE`)
* **Affected Scope**: Line 215
* **Discrepancy**: `EDGE_TTS_INDIC_VOICE_MALE` is defined in `config.py` but never referenced in dispatch logic.
* **Remediation**: Remove unused male voice configuration or define selection criteria.

#### 14. Verification Section Header Accuracy
* **Affected Scope**: Line 277
* **Discrepancy**: Labeled `Syntax & Static Typing`, but executes `py_compile` (which does not check types).
* **Remediation**: Rename to `Syntax Compilation`.

---

## Action Plan for Remediation

1. **Update Target Files List**:
   * Change `app/core/orchestrator.py` $\to$ `app/services/voice_orchestrator.py`.
   * Add `app/api/websocket_endpoint.py`.
   * Add `app/main.py`.
   * Add `client_stream.py`.
   * Add `app/services/session_memory.py`.
2. **Re-align Component Logic**:
   * Correct `SemanticRouterAdapter` to add seed sentences to `DEFAULT_LOCAL_SCHEME_SEED` and `DEFAULT_TEMPORAL_SEED`.
   * Move system prompt rules into `VoiceRAGOrchestrator.process_voice_turn()`.
   * Update `DeepgramStreamSession` rather than `DeepgramSTTAdapter` for connection language strings.
   * Lock output audio standard at 16kHz linear PCM across the entire pipeline.
3. **Restructure Plan with Phased Checkpoints**:
   * Break the implementation into 5 sequential phases with explicit intermediate verification criteria.
