# Goldfish Annotated Review Report

**Target:** [`docs/designs/indic_multilingual_speech_support.md`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/docs/designs/indic_multilingual_speech_support.md) (`Lines 207-301`)  
**Status:** Resolved (Author selected continue without automated doc updates)

## Prioritized Findings & AI Suggestions

### Issue 1 [`egm-codebase-details` / `egm-implementation-readiness`] - Severity: Blocker
*   **Affected Scope:** [Lines 245-256](docs/designs/indic_multilingual_speech_support.md#L245-L256) (`#### 5. app/core/orchestrator.py (Modify)`)
*   **Discrepancy Description:** The plan targets `app/core/orchestrator.py` and class `VoiceOrchestrator`.
*   **Rationale:** `app/core/orchestrator.py` does not exist in the codebase. The actual orchestrator is at `app/services/voice_orchestrator.py` with class `VoiceRAGOrchestrator`. Verification commands targeting `app/core/orchestrator.py` will fail with `FileNotFoundError`.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Confirmed by direct codebase inspection. The orchestrator file path and class name must match reality.
*   ***Proposed Edit:***
    *   Location: Lines 245–256
    *   Change: Replace `app/core/orchestrator.py` with `app/services/voice_orchestrator.py` and reference `VoiceRAGOrchestrator`.

---

### Issue 2 [`egm-codebase-details` / `egm-implementation-readiness`] - Severity: Blocker
*   **Affected Scope:** [Line 249](docs/designs/indic_multilingual_speech_support.md#L249) (`handle_websocket_message`)
*   **Discrepancy Description:** The plan specifies that `handle_websocket_message()` parses WebSocket JSON frames and invokes STT reconnection.
*   **Rationale:** No such method exists on the orchestrator. WebSocket frames are received and dispatched in `voice_websocket()` inside `app/api/websocket_endpoint.py`. `app/api/websocket_endpoint.py` was omitted from the target files list.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Confirmed by inspecting `app/api/websocket_endpoint.py`. Connection-level WebSocket control frames are handled in the API router, not the internal RAG orchestrator service.
*   ***Proposed Edit:***
    *   Location: Target Files List
    *   Change: Add `app/api/websocket_endpoint.py` to the modification list. Add concrete instructions to parse `{"event": "SET_LANGUAGE", "language": "<val>"}` within `voice_websocket()` and recreate the connection-scoped `DeepgramStreamSession`.

---

### Issue 3 [`egm-codebase-details` / `egm-implementation-readiness`] - Severity: Blocker
*   **Affected Scope:** [Lines 227-234](docs/designs/indic_multilingual_speech_support.md#L227-L234) (`#### 3. app/adapters/semantic_router.py (Modify)`)
*   **Discrepancy Description:** The plan directs expanding `_SCHEME_KEYWORDS` and `_TEMPORAL_KEYWORDS`, and adding normalization to `classify()`.
*   **Rationale:** `SemanticRouterAdapter` has no keyword list attributes and no `classify()` method. It uses centroid prototype vectors built from seed exemplar sentence lists (`DEFAULT_LOCAL_SCHEME_SEED`, `DEFAULT_TEMPORAL_SEED`, `DEFAULT_OUT_OF_DOMAIN_SEED`) over unigram and character 3-gram sparse features, evaluated via `classify_intent(self, query: str) -> QueryIntent`.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Adding keywords to non-existent variables will have zero effect on OATS centroid classification.
*   ***Proposed Edit:***
    *   Location: Lines 227–234
    *   Change: Replace the keyword instructions with explicit Hindi and Hinglish seed exemplar sentences to append to `DEFAULT_LOCAL_SCHEME_SEED` and `DEFAULT_TEMPORAL_SEED`. Specify adding `unicodedata.normalize("NFKC", text)` within `_extract_features(self, text: str)`.

---

### Issue 4 [`egm-codebase-details` / `egm-implementation-readiness`] - Severity: Blocker
*   **Affected Scope:** [Lines 235-244](docs/designs/indic_multilingual_speech_support.md#L235-L244) (`#### 4. app/adapters/llm_groq.py (Modify)`)
*   **Discrepancy Description:** The plan specifies updating `SYSTEM_PROMPT` in `GroqLLMAdapter`.
*   **Rationale:** `GroqLLMAdapter` has no system prompt constants or logic; it accepts a compiled prompt string and submits it directly. The system prompt is constructed inside `VoiceRAGOrchestrator.process_voice_turn()` at `voice_orchestrator.py` lines 524–528.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Confirmed by inspecting `llm_groq.py` and `voice_orchestrator.py`.
*   ***Proposed Edit:***
    *   Location: Lines 235–244
    *   Change: Remove `app/adapters/llm_groq.py` from target files. Direct system prompt modifications to `VoiceRAGOrchestrator.process_voice_turn()` in `app/services/voice_orchestrator.py`.

---

### Issue 5 [`egm-codebase-details` / `egm-implementation-readiness`] - Severity: Blocker
*   **Affected Scope:** [Lines 219-225](docs/designs/indic_multilingual_speech_support.md#L219-L225) (`#### 2. app/adapters/stt_deepgram.py (Modify)`)
*   **Discrepancy Description:** The plan specifies modifying `start_stream(self, language: str = "auto")` and adding `reconnect_with_language()`.
*   **Rationale:** No `start_stream()` method exists in `stt_deepgram.py`. `DeepgramSTTAdapter` is an application singleton providing `create_stream_session(self)`, while connection sessions are managed per WebSocket client by `DeepgramStreamSession`.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Reconnection must be performed on the per-client session instance, not the application-wide adapter.
*   ***Proposed Edit:***
    *   Location: Lines 219–225
    *   Change: Update `DeepgramSTTAdapter.create_stream_session(self, language: str = "auto")` to accept `language` and forward it to `DeepgramStreamSession.__init__`. Specify how `websocket_endpoint.py` creates a new session upon receiving a `SET_LANGUAGE` control frame.

---

### Issue 6 [`egm-style` / `egm-codebase-details`] - Severity: Major
*   **Affected Scope:** [Lines 254-255](docs/designs/indic_multilingual_speech_support.md#L254-L255) (`Audio Format Standardization`)
*   **Discrepancy Description:** The plan states all audio output will be standardized to "24kHz 16-bit linear PCM".
*   **Rationale:** The entire codebase (`adapters.py`, `tts_cartesia.py`, `index.html`, `client_stream.py`) is standardized on 16kHz linear PCM. Sending 24kHz audio to 16kHz client audio buffers causes 0.66x down-pitch audio distortion. Furthermore, Edge-TTS outputs raw MP3 frames, which the browser client already decodes transparently.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Maintaining 16kHz linear PCM preserves end-to-end compatibility across Web Audio and CLI playback buffers without requiring unvetted audio resampling dependencies.
*   ***Proposed Edit:***
    *   Location: Lines 254–255
    *   Change: Revert the 24kHz specification and standardize on 16kHz linear PCM for Cartesia, preserving existing MP3 streaming for Edge-TTS with transparent client-side Web Audio decoding.

---

### Issue 7 [`egm-codebase-details` / `egm-implementation-readiness`] - Severity: Major
*   **Affected Scope:** [Lines 250-253](docs/designs/indic_multilingual_speech_support.md#L250-L253) (`Dual-TTS Routing`)
*   **Discrepancy Description:** `VoiceRAGOrchestrator` accepts only a single `tts: TTSClientProtocol`. `app/main.py` conditionally instantiates either Cartesia or Edge-TTS.
*   **Rationale:** The plan does not specify how the orchestrator obtains references to both adapters, and omits `app/main.py` from target files.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Both adapters must be injected at application startup.
*   ***Proposed Edit:***
    *   Location: Target Files List
    *   Change: Add `app/main.py` to the modification list to instantiate both `CartesiaTTSAdapter` (primary English) and `EdgeTTSAdapter` (primary Indic). Update `VoiceRAGOrchestrator.__init__` to accept `indic_tts: Optional[TTSClientProtocol] = None`.

---

### Issue 8 [`egm-implementation-readiness`] - Severity: Major
*   **Affected Scope:** [Lines 207-274](docs/designs/indic_multilingual_speech_support.md#L207-L274) (`Detailed Implementation Plan`)
*   **Discrepancy Description:** The plan contains a flat list of 7 files with no sequencing or phased verification milestones.
*   **Rationale:** Violates the Phasing & Checkpoints requirement of `implementation-readiness-standard.md`.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Structuring work into five sequential, buildable phases guarantees regression isolation.
*   ***Proposed Edit:***
    *   Location: Lines 207–274
    *   Change: Reorganize the implementation plan into five discrete phases with intermediate build/test criteria:
        *   Phase 1: Configuration & Bilingual Centroid Seeds (`config.py`, `semantic_router.py`).
        *   Phase 2: Per-Connection Deepgram STT Language Session (`stt_deepgram.py`, `websocket_endpoint.py`).
        *   Phase 3: Orchestrator Dual-TTS Dispatch, Context Prompt & Memory (`voice_orchestrator.py`, `main.py`, `session_memory.py`).
        *   Phase 4: Frontend UI Language Controls (`index.html`).
        *   Phase 5: Automated Multilingual Unit Tests & CLI Benchmark Updates (`test_multilingual.py`, `client_stream.py`).

---

### Issue 9 [`egm-style` / `egm-codebase-details`] - Severity: Major
*   **Affected Scope:** [Lines 289-299](docs/designs/indic_multilingual_speech_support.md#L289-L299) (`End-to-End Synthetic Streaming Turn`)
*   **Discrepancy Description:** `client_stream.py --say "..."` invokes `generate_synthetic_audio()` with English Cartesia, has no `--language` flag, and cannot emit `SET_LANGUAGE`.
*   **Rationale:** The documented end-to-end verification command cannot execute against Hindi speech without updates to `client_stream.py`.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Adding `client_stream.py` to target files enables automated CLI validation of Hindi turns.
*   ***Proposed Edit:***
    *   Location: Target Files List & Verification Plan
    *   Change: Add `client_stream.py` to target files, adding `--language` argument support and language frame transmission. Specify verification via both `--say` and recorded Hindi WAV files.

---

### Issue 10 [`egm-codebase-details`] - Severity: Major
*   **Affected Scope:** [Lines 245-256](docs/designs/indic_multilingual_speech_support.md#L245-L256) (Implicitly `app/services/session_memory.py`)
*   **Discrepancy Description:** `SessionMemory` uses hardcoded English pronouns (`PRONOUNS`) and question starters for query augmentation.
*   **Rationale:** Hindi queries using demonstrative pronouns (`यह`, `वह`, `इसका`, `उनका`) will fail to trigger multi-turn query augmentation in Qdrant vector retrieval.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Expanding demonstratives ensures multi-turn memory works across Hindi conversations.
*   ***Proposed Edit:***
    *   Location: Target Files List
    *   Change: Add `app/services/session_memory.py` to target files, expanding `PRONOUNS` with Hindi demonstratives.

---

### Issue 11 [`egm-implementation-readiness`] - Severity: Nit
*   **Affected Scope:** [Lines 30, 124, 214](docs/designs/indic_multilingual_speech_support.md#L30)
*   **Discrepancy Description:** Nomenclature alternates between `auto` and `multi`.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** Standardize on `auto` across all config keys and documentation.

---

### Issue 12 [`egm-style` / `egm-codebase-details`] - Severity: Nit
*   **Affected Scope:** [Lines 260-261](docs/designs/indic_multilingual_speech_support.md#L260-L261)
*   **Discrepancy Description:** UI selector option markup omits explicit `value` attributes.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** Explicitly specify `<option value="en">English</option>`, `<option value="hi">हिन्दी (Hindi)</option>`, `<option value="auto">Auto-Detect</option>`.

---

### Issue 13 [`egm-style`] - Severity: Nit
*   **Affected Scope:** [Line 215](docs/designs/indic_multilingual_speech_support.md#L215)
*   **Discrepancy Description:** `EDGE_TTS_INDIC_VOICE_MALE` is defined in config but never referenced in logic.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** Remove `EDGE_TTS_INDIC_VOICE_MALE` to eliminate dead configuration.

---

### Issue 14 [`egm-style`] - Severity: Nit
*   **Affected Scope:** [Line 277](docs/designs/indic_multilingual_speech_support.md#L277)
*   **Discrepancy Description:** Section header reads `Syntax & Static Typing` but runs `py_compile`.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Proposed Edit:*** Rename to `Syntax Compilation`.
