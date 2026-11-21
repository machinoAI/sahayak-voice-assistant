# Knowledge Retrieval & Corrective RAG (CRAG)

Retrieval-Augmented Generation (RAG) grounds assistant answers in factual documentation. However, in naive RAG systems, two severe failure modes routinely occur:
1. **Low-Confidence Hallucinations**: When the knowledge base lacks information for an out-of-domain query, it retrieves the "least bad" documents (e.g. cosine similarity 0.35) and forces the LLM to answer from them, resulting in fabricated or irrelevant responses.
2. **Redundant Search Overhead**: Blindly executing web search on every query adds 2–3 seconds of latency even when the local database already possesses authoritative facts.

To eliminate both pitfalls, Sahayak implements **Corrective Retrieval-Augmented Generation (CRAG)** based on *Corrective Retrieval Augmented Generation* (arXiv:2401.15884).

---

## 1. Qdrant Hybrid Retrieval Architecture

Sahayak integrates **Qdrant Vector Database** via [`app/adapters/vector_store_qdrant.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/vector_store_qdrant.py):

- **Vector Dimensions**: 384 dimensions (optimized for fast embedding models like `all-MiniLM-L6-v2` or `bge-small-en-v1.5`).
- **Distance Metric**: Cosine Similarity.
- **Hybrid Retrieval**: Combines dense semantic vector search with sparse lexical matching (BM25) to accurately match proper nouns, scheme acronyms (e.g. *PM-KISAN*, *AB-PMJAY*), and conversational queries.
- **Payload Schema**:
  ```json
  {
    "id": "doc-pm-kisan-01",
    "text": "Under the PM Kisan Samman Nidhi scheme...",
    "category": "agriculture_welfare",
    "score": 0.94
  }
  ```

---

## 2. CRAG Tri-State Confidence Arbitration

Rather than a binary threshold, CRAG partitions retrieval confidence into **three distinct operating zones**:

```
0.00                              0.55                              0.82                              1.00
├──────────────────────────────────┼──────────────────────────────────┼──────────────────────────────────┤
│           INCORRECT              │            AMBIGUOUS             │             CORRECT              │
│       (Score < 0.55)             │       (0.55 <= Score < 0.82)     │       (Score >= 0.82)            │
│  • Local knowledge absent        │  • Partial / outdated match      │  • Authoritative local facts     │
│  • Suppress local chunks         │  • Merge local background        │  • Prune external web search     │
│  • Web search mandatory          │    with live web search facts    │  • Minimal latency (~1.1s turn)  │
```

```mermaid
flowchart TD
    RET["Execute Qdrant Hybrid Retrieval"] --> EVAL["Compute top_score = max(doc.score)"]
    
    EVAL --> COND{"CRAG Confidence Zone"}
    
    COND -- "top_score >= 0.82 (CORRECT)" --> ACTION_CORRECT["Use Local Knowledge Only<br/>Cancel / Prune Tavily Web Search"]
    COND -- "0.55 <= top_score < 0.82 (AMBIGUOUS)" --> ACTION_AMBIGUOUS["Hybrid Merge<br/>Dispatch Web Search & Prepend to Local Docs"]
    COND -- "top_score < 0.55 (INCORRECT)" --> ACTION_INCORRECT["Web Search Fallback<br/>Suppress Irrelevant Local Docs to Prevent Hallucination"]
    
    ACTION_CORRECT --> PROMPT["Compile LLM System Prompt"]
    ACTION_AMBIGUOUS --> PROMPT
    ACTION_INCORRECT --> PROMPT
```

---

## 3. The Action Matrix in Detail

### State 1: `CORRECT` ($\ge 0.82$)
- **Condition**: Top retrieved local chunk has a cosine similarity $\ge 0.82$.
- **Interpretation**: The internal knowledge base contains authoritative, complete documentation.
- **Action**:
  - The local chunks are supplied directly to the LLM.
  - If a speculative web search was dispatched in parallel, it is **immediately cancelled** (`search_task.cancel()`).
- **Telemetry Event**: Emits `SPECULATIVE_SEARCH_CANCELLED` and `CRAG_DECISION: CORRECT`.

### State 2: `AMBIGUOUS` ($0.55 \le \text{Score} < 0.82$)
- **Condition**: Moderate relevance overlap (e.g. matching general keywords but missing specific rules or recent revisions).
- **Interpretation**: Local documentation provides baseline context, but may be incomplete or amended by new government notifications.
- **Action**:
  - Dispatches or awaits Tavily web search.
  - Concatenates web search results with local chunks: $\mathcal{D}_{\text{final}} = \mathcal{D}_{\text{web}} \cup \mathcal{D}_{\text{local}}$.
  - Supplies merged context to the LLM.
- **Telemetry Event**: Emits `CRAG_DECISION: AMBIGUOUS`.

### State 3: `INCORRECT` ($< 0.55$)
- **Condition**: Top similarity score is $< 0.55$ (e.g., query asks about sports trivia, world history, or an unindexed topic).
- **Interpretation**: Local database contains no relevant knowledge.
- **Action**:
  - **Suppresses local chunks entirely**: $\mathcal{D}_{\text{local}} = \emptyset$. This prevents the LLM from trying to answer a cricket question using agricultural scheme text.
  - Dispatches Tavily Web Search to fetch the actual answer from the internet.
  - Supplies only web results: $\mathcal{D}_{\text{final}} = \mathcal{D}_{\text{web}}$.
- **Telemetry Event**: Emits `CRAG_DECISION: INCORRECT`.

---

## 4. Fallback Knowledge Corpus & Dynamic Scoring

When running in local in-memory or embedded storage mode without an active Docker instance, [`QdrantVectorStoreAdapter`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/vector_store_qdrant.py) computes dynamic relevance scores over standard welfare scheme documentation:

1. **Token Filtering**: Strips conversational stopwords (`what`, `is`, `the`, `tell`, `me`, `about`).
2. **Lexical & Semantic Overlap**:
   - $\ge 2$ core term matches (e.g. `eligibility`, `pm`, `kisan`): Score assigned between **$0.78 - 0.95$**.
   - 1 term match: Score assigned **$0.65$** (Ambiguous).
   - 0 term matches: Score assigned **$0.30$** (Triggers CRAG `INCORRECT` fallback).

This ensures deterministic, testable behavior that accurately triggers each branch of the Corrective RAG pipeline.

---

## 5. Grounded Citizen Knowledge Base & Ingestion Pipeline

To provide grounded responses without relying solely on live search or synthetic fallbacks, Sahayak includes authoritative welfare datasets in [`data/knowledge_base/`](../data/knowledge_base/):

### Indexed Datasets

| File | Scheme | Key Grounded Information |
| :--- | :--- | :--- |
| `pm_kisan.json` | PM-KISAN | Financial benefit (₹6,000/yr), 3 installments of ₹2,000, Aadhaar/DBT mandatory, landholding criteria, exclusions. |
| `ayushman_bharat.json` | AB-PMJAY | ₹5 lakh health coverage, cashless secondary/tertiary hospital treatment, SECC 2011 criteria, senior citizen age 70+ expansion. |
| `pm_awas_yojana.json` | PMAY | Financial grants for rural housing (₹1.20L/₹1.30L), Urban interest subsidies (CLSS), female head co-ownership. |
| `atal_pension_yojana.json` | APY | Guaranteed monthly pension ₹1,000-₹5,000 at age 60, entry age 18-40, spouse and nominee corpus return. |
| `pm_ujjwala_yojana.json` | PMUY | Free LPG connections for women in BPL households, ₹1,600 assistance, ₹300 cylinder subsidies. |
| `sukanya_samriddhi_yojana.json` | SSY | Small savings for girl child under 10 years, 8.2% compound interest, EEE tax exemption, 21-year maturity. |

### Ingestion CLI & Execution
The ingestion script ([`scripts/ingest_knowledge.py`](../scripts/ingest_knowledge.py)) parses these documents, generates 384-dimensional dense vectors using FastEmbed (`BAAI/bge-small-en-v1.5`), and indexes them into collection `sahayak_kb`:

```bash
# Using Makefile shortcut:
make ingest

# Or directly via Python script:
python scripts/ingest_knowledge.py

# Or via adapter module:
python -m app.adapters.vector_store_qdrant --ingest
```

### Storage Concurrency & Testing Safety
- **Local Disk Mode (`qdrant_storage/.lock`)**: When running embedded storage on disk, Qdrant enforces exclusive file locks (`portalocker`). The ingestion script detects if the directory is locked by a running uvicorn instance and guides the user.
- **Standalone Docker Mode**: Running `make docker-up` launches a dedicated Qdrant server container on port 6333, allowing concurrent API access and background ingestion without lock contention.
- **Isolated Testing Mode**: Automated unit and integration tests always run against an in-memory database (`QDRANT_PATH=":memory:" pytest tests/`) to ensure complete isolation.
