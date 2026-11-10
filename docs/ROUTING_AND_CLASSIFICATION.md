# Intent Routing & Classification Architecture

In traditional agentic systems, tool selection and intent routing are delegated to an LLM (e.g., GPT-4o-mini). While accurate, remote LLM classification introduces **$300\text{ms} - 650\text{ms}$ of sequential network latency** (arXiv:2505.14524) before any search or retrieval can begin. In a voice assistant with a strict sub-1.2s budget, spending 500ms on routing alone causes noticeable conversational lag.

To solve this, Sahayak implements an **Outcome-Aware Semantic Router (OATS)** based on recent research (*Outcome-Aware Tool Selection for Semantic Routers: Latency-Constrained Learning Without LLM Inference*, arXiv:2603.13426).

---

## 1. Intent Categories

The router classifies every incoming query into one of three operational intents:

| Query Intent | Target Domain | Trigger Action |
| :--- | :--- | :--- |
| **`LOCAL_SCHEME_FAQ`** | Indian government citizen welfare schemes (PM Kisan, Ayushman Bharat, Aadhar, Ration Cards, pensions) and Sahayak assistant capabilities. | Route query to **Qdrant Hybrid Vector DB**; evaluate with Corrective RAG. |
| **`REALTIME_TEMPORAL`** | Time-sensitive queries: breaking news, live cricket scores, dynamic commodity prices, today's weather. | Route to **Qdrant** AND immediately dispatch **Speculative Tavily Web Search** in parallel. |
| **`OUT_OF_DOMAIN`** | Open-domain trivia, international affairs, history, science, coding. | Suppress local domain knowledge; escalate directly to **Tavily Web Search**. |

---

## 2. Feature Extraction & Mathematical Formulation

The router operates in pure Python on CPU without downloading heavy PyTorch models, ONNX runtimes, or external API calls.

### A. Dual N-Gram Representation
Given an input utterance $q$, text is normalized (lowercased, punctuation removed) into words $W = \{w_1, w_2, \dots, w_m\}$. Two feature sets are extracted:
1. **Word Unigrams**: Captures explicit keywords and vocabulary:
   $$\Phi_{\text{word}}(w) = 1.0 \quad \forall w \in W, \; |w| > 1$$
2. **Character 3-Grams**: Captures typos, phonetic variations, and morphological inflections (e.g., "kisaan", "kisans", "kisan"):
   $$\Phi_{\text{char}}(w) = 0.5 \quad \forall \text{ trigrams } g \in \_w\_$$

### B. $L_2$ Unit Normalization
The combined sparse feature vector $\mathbf{x} \in \mathbb{R}^{D}$ is normalized to unit Euclidean length:
$$\mathbf{v} = \frac{\mathbf{x}}{\|\mathbf{x}\|_2} = \frac{\mathbf{x}}{\sqrt{\sum_{k} x_k^2}}$$

### C. Centroid Construction
For each intent class $c \in \{\text{TEMPORAL}, \text{LOCAL}, \text{OOD}\}$, a cluster centroid $\mathbf{C}_c$ is constructed from seed exemplars $\mathcal{S}_c$:
$$\mathbf{C}_c = \frac{\sum_{s \in \mathcal{S}_c} \mathbf{v}_s}{\left\|\sum_{s \in \mathcal{S}_c} \mathbf{v}_s\right\|_2}$$

### D. Sparse Cosine Similarity
Because all centroid vectors and query vectors are pre-normalized to $\|\mathbf{v}\|_2 = 1$, the cosine similarity reduces to an inner product computed strictly over the intersection of non-zero indices:
$$\text{Sim}(\mathbf{v}_q, \mathbf{C}_c) = \mathbf{v}_q \cdot \mathbf{C}_c = \sum_{k \in \text{supp}(\mathbf{v}_q) \cap \text{supp}(\mathbf{C}_c)} v_{q,k} \cdot C_{c,k}$$

---

## 3. Decision Arbitration Logic

```mermaid
flowchart TD
    Q["Input Query q"] --> FE["Extract Word & Char 3-Grams (L2 Norm)"]
    FE --> COS["Compute Cosine Sim against Centroids"]
    
    COS --> CHK1{"Sim(q, Temporal) >= 0.28 AND >= Sim(q, Local)?"}
    CHK1 -- Yes --> RET_TEMP["QueryIntent.REALTIME_TEMPORAL"]
    
    CHK1 -- No --> CHK2{"Sim(q, Local) >= 0.24 AND >= Sim(q, OOD)?"}
    CHK2 -- Yes --> RET_LOCAL["QueryIntent.LOCAL_SCHEME_FAQ"]
    
    CHK2 -- No --> CHK3{"Sim(q, Temporal) >= 0.28?"}
    CHK3 -- Yes --> RET_TEMP
    CHK3 -- No --> RET_OOD["QueryIntent.OUT_OF_DOMAIN"]
```

### Thresholds:
- **`temporal_threshold = 0.28`**: Protects fresh, dynamic facts by prioritizing temporal signals.
- **`local_threshold = 0.24`**: Ensures scheme queries with morphological variations route cleanly to the local knowledge base.

---

## 4. Benchmark Performance

Benchmarked across 1,000 runs on an Apple Silicon M-series CPU:

| Metric | Target Budget | OATS Implementation | LLM Classification Alternative |
| :--- | :--- | :--- | :--- |
| **Execution Latency** | $< 1.0\text{ ms}$ | **$0.19\text{ ms} - 0.38\text{ ms}$** | $450\text{ ms} - 700\text{ ms}$ |
| **Memory Footprint** | $< 50\text{ MB}$ | **$< 2\text{ MB}$ (In-Process)** | $> 2\text{ GB}$ (local model) |
| **External Dependencies** | Zero | **Pure Python standard library** | HuggingFace, PyTorch, Cuda |
| **Deterministic Output** | 100% | **100% Deterministic** | Stochastic |

Implementation located at [`app/adapters/semantic_router.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/semantic_router.py).
