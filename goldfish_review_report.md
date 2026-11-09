# Goldfish Annotated Review Report

**Target:** [`design_draft.md`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md) (`DetailedRange: Lines 208–235`)  
**Status:** In Review  
**Review Standard:** [`implementation-readiness-standard.md`](file:///Users/amankumar/.gemini/config/plugins/egm/resources/document_standards/implementation-readiness-standard.md)

---

## Prioritized Findings & AI Suggestions

### Finding 1: Unresolved Architecture & Missing Specification for Semantic Router [`egm-implementation-readiness`, `egm-codebase-details`]
*   **Severity:** Blocker
*   **Affected Scope:** [`design_draft.md` Lines 52–54, 216, 231](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L52-L54)
*   **Discrepancy Description:** Open Question 2 remains unresolved in the design. The plan requires prototype centroid embeddings for `SemanticRouterAdapter` but provides zero centroid vectors, exemplar training sets, runtime vectorization methods, or dependency choices.
*   **Rationale:** Leaving the embedding model and vectorization method to the implementer violates the Zero-Decision Rule.
*   ***AI Suggestion:*** `PROPOSE FIX`
*   ***Justification:*** To preserve the strict sub-1.2s voice budget and avoid introducing 100MB+ dependencies (Torch/ONNX/transformers) into a minimal container, resolve Open Question 2 by implementing an in-process sparse n-gram / TF-IDF centroid router in pure Python. It executes in `<0.5ms` on CPU with zero new runtime dependencies.
*   ***Proposed Edit:***
    *   **Location:** `design_draft.md` Open Questions (Lines 52–54) & Detailed Implementation Plan (Line 216)
    *   **Change:** Resolve Question 2 explicitly. Document the exact class `SemanticRouterAdapter`, the exemplar phrase dictionaries for `[LOCAL_SCHEME_FAQ, REALTIME_TEMPORAL, OUT_OF_DOMAIN]`, the cosine similarity formula, and the fallback confidence threshold in the plan.

---

### Finding 2: Plan Claims Pre-existing Production & Test Code as Unwritten Work [`egm-codebase-details`, `egm-style`]
*   **Severity:** Blocker
*   **Affected Scope:** [`design_draft.md` Lines 214, 215, 218, 219, 220, 228–229](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L214-L229)
*   **Discrepancy Description:** The implementation table marks `app/adapters/search_tavily.py`, `tests/test_search_tavily.py`, `WebSearchProtocol`, and `app/main.py` Tavily wiring as work to be created or modified, when they already exist in production.
*   **Rationale:** Misrepresenting existing code as new tasks creates confusion and implementation drift.
*   ***AI Suggestion:*** `PROPOSE FIX`
*   ***Justification:*** Differentiate pre-existing infrastructure from new delta work. Mark `app/adapters/search_tavily.py` and `tests/test_search_tavily.py` as `Retain / Verify`.
*   ***Proposed Edit:***
    *   **Location:** `design_draft.md` File Mapping Table (Lines 212–223) & Execution Sequencing (Lines 228–229)
    *   **Change:** Reclassify existing files under `Retain / Verify` and restrict modification descriptions strictly to the new CRAG thresholds, `SemanticRouterProtocol`, and orchestrator speculative execution logic.

---

### Finding 3: Missing Dependency Injection in Orchestrator Constructor & `app/main.py` [`egm-implementation-readiness`, `egm-codebase-details`, `egm-style`]
*   **Severity:** Blocker
*   **Affected Scope:** [`design_draft.md` Lines 217, 219, 230](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L217-L230)
*   **Discrepancy Description:** `VoiceRAGOrchestrator.__init__` is not specified to accept `router: Optional[SemanticRouterProtocol] = None`, and `app/main.py` omits instantiating `SemanticRouterAdapter` and passing it to the orchestrator.
*   **Rationale:** The semantic router would remain dead code without explicit dependency injection.
*   ***AI Suggestion:*** `PROPOSE FIX`
*   ***Justification:*** Document constructor modification in `app/services/voice_orchestrator.py` with backward-compatible fallback, and add the instantiation and injection step in `app/main.py`.
*   ***Proposed Edit:***
    *   **Location:** `design_draft.md` Lines 217, 219, and 230
    *   **Change:** Update table entries for `voice_orchestrator.py` and `main.py` to specify:
        `router: Optional[SemanticRouterProtocol] = None` parameter in `VoiceRAGOrchestrator.__init__`, and `orchestrator = VoiceRAGOrchestrator(..., router=router_adapter)` in `app/main.py`.

---

### Finding 4: Underspecified `QueryIntent` Data Model and Protocol Signature [`egm-implementation-readiness`, `egm-codebase-details`]
*   **Severity:** Major
*   **Affected Scope:** [`design_draft.md` Line 214](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L214)
*   **Discrepancy Description:** `QueryIntent` is not defined, and `classify_intent` does not specify whether it is synchronous or asynchronous.
*   **Rationale:** Leaves interface design choices to the implementer.
*   ***AI Suggestion:*** `PROPOSE FIX`
*   ***Justification:*** Provide the concrete Enum and Protocol definitions directly in the plan.
*   ***Proposed Edit:***
    *   **Location:** `design_draft.md` Line 214
    *   **Change:** Add explicit code block:
        ```python
        class QueryIntent(str, Enum):
            LOCAL_SCHEME_FAQ = "local_scheme_faq"
            REALTIME_TEMPORAL = "realtime_temporal"
            OUT_OF_DOMAIN = "out_of_domain"

        class SemanticRouterProtocol(Protocol):
            def classify_intent(self, query: str) -> QueryIntent: ...
        ```

---

### Finding 5: Contradictory High Threshold Constants Across Document [`egm-implementation-readiness`]
*   **Severity:** Major
*   **Affected Scope:** [`design_draft.md` Lines 39, 180, 218](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L39)
*   **Discrepancy Description:** Line 39 cites cancellation at `0.85`, while lines 180 and 218 define `CRAG_HIGH_THRESHOLD = 0.82`.
*   **Rationale:** Ambiguous threshold values cause conflicting test assertions.
*   ***AI Suggestion:*** `PROPOSE FIX`
*   ***Justification:*** Harmonize the high threshold constant to `0.82` across the entire document.
*   ***Proposed Edit:***
    *   **Location:** `design_draft.md` Line 39
    *   **Change:** Replace `(>= 0.85)` with `(>= 0.82)`.

---

### Finding 6: Underspecified Control Flow for Speculative Dispatch & CRAG Branching [`egm-implementation-readiness`, `egm-codebase-details`, `egm-style`]
*   **Severity:** Major
*   **Affected Scope:** [`design_draft.md` Lines 217, 232–233](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L217-L233)
*   **Discrepancy Description:** Control flow does not specify how `search_task` is created, how score aggregation works, how cancellation is handled, or which new milestones are logged.
*   **Rationale:** The implementer must invent concurrency handling and score evaluation.
*   ***AI Suggestion:*** `PROPOSE FIX`
*   ***Justification:*** Provide the exact control-flow block and name new milestones (`ROUTER_CLASSIFY_COMPLETE`, `SPECULATIVE_SEARCH_DISPATCHED`, `SPECULATIVE_SEARCH_CANCELLED`).
*   ***Proposed Edit:***
    *   **Location:** `design_draft.md` Lines 217, 232–233
    *   **Change:** Include concrete implementation logic showing `asyncio.create_task`, `top_score = max([d.score for d in docs], default=0.0)`, CRAG tri-state branch conditions, and cancellation handling.

---

### Finding 7: Unactionable Test Plan and Uncalibrated Test Counts [`egm-implementation-readiness`, `egm-codebase-details`, `egm-style`]
*   **Severity:** Major
*   **Affected Scope:** [`design_draft.md` Lines 220–222, 235](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L220-L235)
*   **Discrepancy Description:** Test plan lacks concrete test function names and fixtures, and line 235 uses hyperbole ("34+ tests ensuring zero regression").
*   **Rationale:** Fails the Test Plan requirement of the Implementation Readiness Standard.
*   ***AI Suggestion:*** `PROPOSE FIX`
*   ***Justification:*** Enumerate exact test function names and replace hyperbole with verifiable criteria.
*   ***Proposed Edit:***
    *   **Location:** `design_draft.md` Lines 221–222, 235
    *   **Change:** List concrete test functions (`test_router_classification_latency`, `test_router_temporal_intent`, `test_crag_high_confidence_bypasses_web`, `test_crag_ambiguous_merges_docs`, `test_crag_low_confidence_suppresses_local`, `test_speculative_tavily_cancellation`), and state that the full test suite passes within the 1.2s TTFAB target.

---

### Finding 8: Missing Configuration Setting for Semantic Router [`egm-codebase-details`]
*   **Severity:** Nit
*   **Affected Scope:** [`design_draft.md` Line 218](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/design_draft.md#L218)
*   **Discrepancy Description:** No toggle setting is provided to enable or disable the router.
*   ***AI Suggestion:*** `PROPOSE FIX`
*   ***Justification:*** Adding `SEMANTIC_ROUTER_ENABLED: bool = True` allows disabling the router during tests or when testing pure keyword fallback.
*   ***Proposed Edit:***
    *   **Location:** `design_draft.md` Line 218
    *   **Change:** Include `SEMANTIC_ROUTER_ENABLED: bool = True` in `app/core/config.py`.
