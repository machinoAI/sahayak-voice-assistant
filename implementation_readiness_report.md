# Implementation Readiness Audit Report (Stage 9)

*   **Target Document:** [`design_draft.md`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md) (Lines 208–235: "Detailed Implementation Plan")
*   **Standard:** [`implementation-readiness-standard.md`](file:///Users/amankumar/.gemini/config/plugins/egm/resources/document_standards/implementation-readiness-standard.md)
*   **Reviewers:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
*   **Overall Verdict:** **FAIL (Requires Remediation)**

The Detailed Implementation Plan in [`design_draft.md`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md) fails the Zero-Decision Rule. It leaves key architectural decisions unmade, lacks concrete data structures and class signatures, claims pre-existing repository code as unwritten work, and provides an unactionable test plan.

---

## Consolidated Findings & Remediation Matrix

### 1. [Blocker] Unresolved Architecture & Missing Specification for Semantic Router
*   **Reviewers**: `egm-implementation-readiness`, `egm-codebase-details`
*   **Affected Scope**: [`design_draft.md` Lines 52–54, 216, 231](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L52-L54)
*   **Problem**:
    *   Open Question 2 (*"Should the semantic router use a lightweight local ONNX model or a fastText / WideMLP continuous bag-of-words model?"*) remains open, violating the Zero-Decision Rule.
    *   The plan specifies pre-computed prototype centroid embeddings but provides zero vector representations, embedding models, seed utterances, or dimensional definitions.
    *   The plan does not define how queries are vectorized at runtime in `<3ms` without adding heavyweight ML dependencies, nor does it list [`requirements.txt`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/requirements.txt) in the file modification table.
*   **Actionable Remediation**:
    *   Resolve Question 2 explicitly: Use a zero-external-dependency, TF-IDF / normalized sparse prototype centroid approach or lightweight `fastembed` / ONNX table with defined dimensions.
    *   Define exact class signature `SemanticRouterAdapter(centroid_map, threshold)`.
    *   Specify exemplar query sets for `LOCAL_SCHEME_FAQ`, `REALTIME_TEMPORAL`, and `OUT_OF_DOMAIN`.
    *   If adding a dependency, explicitly add [`requirements.txt`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/requirements.txt) to the file modification table.

---

### 2. [Blocker] Plan Claims Pre-existing Production & Test Code as Unwritten Work
*   **Reviewers**: `egm-codebase-details`, `egm-style`
*   **Affected Scope**: [`design_draft.md` Lines 214, 215, 218, 219, 220, 228–229](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L214-L229)
*   **Problem**:
    *   [`app/adapters/search_tavily.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/search_tavily.py) already implements `TavilySearchAdapter`, basic search depth, answer extraction, and 4.0s timeout resilience.
    *   [`tests/test_search_tavily.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/tests/test_search_tavily.py) already contains 5 passing unit and integration tests.
    *   [`app/interfaces/adapters.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/interfaces/adapters.py) already defines `WebSearchProtocol`.
    *   [`app/core/config.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/core/config.py) already contains `TAVILY_API_KEY`, `WEB_SEARCH_ENABLED`, `WEB_SEARCH_MAX_RESULTS`, and `WEB_SEARCH_TIMEOUT_SECONDS`.
    *   [`app/main.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/main.py) already wires `TavilySearchAdapter` into `VoiceRAGOrchestrator` and `/health`.
*   **Actionable Remediation**:
    *   Differentiate pre-existing infrastructure from new feature work in the File Mapping table and Execution Sequence.
    *   Mark `app/adapters/search_tavily.py` and `tests/test_search_tavily.py` as `Retain / Verify`.
    *   Restrict modification descriptions to actual delta: adding `CRAG_HIGH_THRESHOLD`, `CRAG_LOW_THRESHOLD`, `SEMANTIC_ROUTER_ENABLED`, `SemanticRouterProtocol`, and orchestrator speculative execution logic.

---

### 3. [Blocker] Missing Dependency Injection in Orchestrator Constructor & `app/main.py`
*   **Reviewers**: `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
*   **Affected Scope**: [`design_draft.md` Lines 217, 219, 230](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L217-L230)
*   **Problem**:
    *   [`VoiceRAGOrchestrator.__init__`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/services/voice_orchestrator.py#L58-L65) currently takes only `stt, vdb, llm, tts, search`. The plan does not specify adding `router: Optional[SemanticRouterProtocol] = None`.
    *   Line 219 and the execution sequence completely omit instantiating `SemanticRouterAdapter` in [`app/main.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/main.py) and injecting it into the orchestrator.
*   **Actionable Remediation**:
    *   Update `app/services/voice_orchestrator.py` specification to accept `router: Optional[SemanticRouterProtocol] = None`.
    *   Update `app/main.py` specification to import `SemanticRouterAdapter`, instantiate it if `SEMANTIC_ROUTER_ENABLED`, and pass it to `VoiceRAGOrchestrator(..., router=router_adapter)`.

---

### 4. [Major] Underspecified `QueryIntent` Data Model and Protocol Signature
*   **Reviewers**: `egm-implementation-readiness`, `egm-codebase-details`
*   **Affected Scope**: [`design_draft.md` Line 214](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L214)
*   **Problem**:
    *   `QueryIntent` is referenced as a return type but is never defined.
    *   The plan does not clarify whether `classify_intent` is synchronous (`def classify_intent(self, query: str) -> QueryIntent:`) or asynchronous (`async def ...`).
*   **Actionable Remediation**:
    *   Provide the explicit enum definition:
        ```python
        from enum import Enum
        from typing import Protocol

        class QueryIntent(str, Enum):
            LOCAL_SCHEME_FAQ = "local_scheme_faq"
            REALTIME_TEMPORAL = "realtime_temporal"
            OUT_OF_DOMAIN = "out_of_domain"

        class SemanticRouterProtocol(Protocol):
            def classify_intent(self, query: str) -> QueryIntent:
                """Classifies input query intent into pre-defined routing classes in <3ms."""
                ...
        ```

---

### 5. [Major] Inconsistent High Threshold Constants in Design vs. Plan
*   **Reviewers**: `egm-implementation-readiness`
*   **Affected Scope**: [`design_draft.md` Lines 39, 180, 218](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L39)
*   **Problem**:
    *   Line 39 cites: *"canceling the Tavily call if local retrieval yields a decisive score ($\ge 0.85$)"*.
    *   Line 180 and Line 218 specify $\theta_{high} = 0.82$.
*   **Actionable Remediation**:
    *   Harmonize all references across Goals, Architecture, and Implementation to `0.82` (`CRAG_HIGH_THRESHOLD = 0.82`).

---

### 6. [Major] Underspecified Control Flow for Speculative Dispatch & CRAG Branching
*   **Reviewers**: `egm-implementation-readiness`, `egm-codebase-details`
*   **Affected Scope**: [`design_draft.md` Lines 217, 232–233](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L217-L233)
*   **Problem**:
    *   The plan lacks exact branching logic: how confidence is calculated from `docs`, when `task.cancel()` is called, how `CancelledError` is suppressed, and how documents are merged under `INCORRECT` vs `AMBIGUOUS`.
    *   Existing milestones (`WEB_SEARCH_START`, `WEB_SEARCH_COMPLETE`) are claimed as new work; new milestones (`ROUTER_CLASSIFY_COMPLETE`, `SPECULATIVE_SEARCH_DISPATCHED`, `SPECULATIVE_SEARCH_CANCELLED`) are omitted.
*   **Actionable Remediation**:
    *   Provide step-by-step logic in the implementation plan showing task creation, score aggregation (`max([d.score for d in docs], default=0.0)`), threshold evaluation, and document array assembly.

---

### 7. [Major] Unactionable Test Plan and Uncalibrated Test Baselines
*   **Reviewers**: `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
*   **Affected Scope**: [`design_draft.md` Lines 220–222, 235](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L220-L235)
*   **Problem**:
    *   The plan lacks specific test function names, inputs, and assertion criteria for `tests/test_semantic_router.py` and `tests/test_voice_pipeline.py`.
    *   Line 235 claims: *"Run unit tests and live pipeline benchmarks across all 34+ tests ensuring zero regression"*, which uses promotional hyperbole and uncalibrated metrics.
*   **Actionable Remediation**:
    *   Enumerate specific test functions: `test_router_classification_latency`, `test_router_temporal_intent`, `test_crag_high_confidence_bypasses_web`, `test_crag_ambiguous_merges_docs`, `test_crag_low_confidence_suppresses_local`, `test_speculative_cancellation_on_decisive_score`.
    *   Calibrate regression test assertion to the actual test suite suite.
