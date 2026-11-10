# Speculative Web Search & Concurrent Retrieval

When an assistant requires real-time information from the internet (e.g. today's breaking news, weather forecast, live scores, or out-of-domain knowledge), external web search APIs like Tavily introduce network round-trips of **1.5s to 2.8s**. 

If retrieval is implemented **sequentially** (Query $\to$ Vector Search $\to$ Evaluate Score $\to$ Web Search $\to$ LLM), the search latency sits entirely on the critical path, pushing the turn time well past 3.5 seconds.

To eliminate this sequential penalty, Sahayak implements **Speculative Concurrent Fetching**, inspired by *Accelerating Retrieval-Augmented Language Model Serving with Speculation (RaLMSpec)* (arXiv:2401.14021) and *Speculative RAG* (arXiv:2407.08223).

---

## 1. Speculative Concurrency Architecture

Whenever the [Semantic Router](ROUTING_AND_CLASSIFICATION.md) detects a temporal signal (`REALTIME_TEMPORAL`), the orchestrator **immediately dispatches Tavily Web Search concurrently** with local Qdrant retrieval at $t \approx 1\text{ms}$ using non-blocking Python tasks:

```
Sequential Pipeline (Naive RAG):
[STT Final] ────> [Qdrant Search: 50ms] ────> [Tavily Search: 2500ms] ────> [LLM TTFT: 800ms] ────> [TTS Audio: 250ms]
Total to Audio: ~3600ms (Unacceptable Voice Lag)

Speculative Pipeline (Sahayak Architecture):
[STT Final] ─┬──> [Semantic Router: 0.2ms]
             ├──> [Speculative Tavily Task: Dispatched at t=1ms] ─────────┐
             └──> [Qdrant Hybrid Search: 50ms] ───────────────────────────┤
                                                                          │
                                       [CRAG Tri-State Arbitration] <─────┘
                                                    │
                                                    └──> [Groq LLM Stream: 800ms] ────> [TTS Audio: 220ms]
Total to Audio: ~2700ms (Saved 800ms-1200ms of critical-path overhead)
```

---

## 2. Early Task Cancellation (Pruning on High Confidence)

What if the query contained temporal keywords, but the local knowledge base actually possesses authoritative, high-confidence information?
- Qdrant finishes in **$30\text{ms} - 50\text{ms}$**, while Tavily is still connecting to the internet.
- CRAG evaluates `top_score >= 0.82` (`CORRECT`).
- The orchestrator immediately calls:
  ```python
  if search_task and not search_task.done():
      search_task.cancel()
      tracker.log_step("SPECULATIVE_SEARCH_CANCELLED", {
          "reason": "high_local_confidence",
          "score": top_score,
          "threshold": settings.CRAG_HIGH_THRESHOLD,
      })
  ```
- **Result**: The in-flight HTTP request is cancelled cleanly. The system pays **zero latency penalty**, consumes zero external API tokens, and immediately proceeds to LLM token generation at $t \approx 55\text{ms}$.

---

## 3. Tavily Search Adapter Integration

Located at [`app/adapters/search_tavily.py`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/adapters/search_tavily.py), the adapter implements `WebSearchProtocol`:

```python
class TavilySearchAdapter(WebSearchProtocol):
    def __init__(self, api_key: Optional[str] = settings.TAVILY_API_KEY, timeout: float = 4.0):
        self.api_key = api_key
        self.client = AsyncTavilyClient(api_key=self.api_key) if self.api_key else None
        self.timeout = timeout
```

### Search Features:
1. **Direct Answer Extraction**: If Tavily produces an AI synthesized direct answer, it is prepended as an authoritative document chunk (`id="tavily-direct-answer"`, `score=1.0`).
2. **Result Scoring & Formatting**: Each web source is converted into a `RetrievedDocument`:
   - Title, URL, and raw text content are structured.
   - Text is cleaned and bounded to prevent prompt bloat.
3. **Graceful Fallback & Timeouts**: If the network times out ($>4.0\text{s}$) or encounters rate limits, the search fails gracefully without crashing the turn, falling back to local context.

---

## 4. Prompt Assembly with Live Web Chunks

When web search results are approved by CRAG, they are injected into the system prompt:

```
You are Sahayak, a voice assistant.
Answer using ONLY the provided context in 1-2 spoken sentences.
Never use lists, markdown, asterisks, or URLs. Speak naturally.

Context:
Direct Search Answer: The latest news updates include a mass wedding of 250 couples in Gaza...
World | Latest News & Updates | BBC News: Six people were killed in the shooting...

User Question: What is the latest news update today?
```

Because of the voice-first constraints (`1-2 spoken sentences`, `never use markdown or URLs`), the Groq LLM synthesizes a concise, spoken news brief that Cartesia Sonic speaks smoothly to the user.
