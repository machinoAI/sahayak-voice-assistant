"""
Unit tests for SemanticRouterAdapter verifying sub-millisecond classification latency,
intent clustering accuracy, and boundary condition handling.
"""

import time
import pytest
from app.adapters.semantic_router import SemanticRouterAdapter
from app.interfaces.adapters import QueryIntent

def test_semantic_router_sub_millisecond_latency():
    """Verify that classification executes in <1.0ms on CPU."""
    router = SemanticRouterAdapter()
    query = "What is the latest weather forecast in New Delhi today?"

    # Warmup
    for _ in range(5):
        router.classify_intent(query)

    start = time.perf_counter()
    iterations = 200
    for _ in range(iterations):
        router.classify_intent(query)
    total_time_ms = (time.perf_counter() - start) * 1000
    avg_latency_ms = total_time_ms / iterations

    print(f"\n[SEMANTIC ROUTER] Average Latency: {avg_latency_ms:.3f}ms across {iterations} queries")
    assert avg_latency_ms < 1.0, f"Router too slow: {avg_latency_ms}ms"

def test_semantic_router_temporal_intent():
    """Verify that real-time and temporal queries classify as REALTIME_TEMPORAL."""
    router = SemanticRouterAdapter()
    queries = [
        "What is the latest news in India today?",
        "What is the current weather in New Delhi right now?",
        "Live cricket score update",
        "What is today gold price in Delhi?",
        "Latest stock market updates",
    ]
    for q in queries:
        intent = router.classify_intent(q)
        assert intent == QueryIntent.REALTIME_TEMPORAL, f"Query '{q}' mapped to {intent}, expected REALTIME_TEMPORAL"

def test_semantic_router_local_scheme_faq_intent():
    """Verify that welfare schemes and assistant FAQ queries classify as LOCAL_SCHEME_FAQ."""
    router = SemanticRouterAdapter()
    queries = [
        "How to apply for PM Kisan scheme?",
        "What are the eligibility criteria for Ayushman Bharat card?",
        "Documents required for ration card application",
        "What is Sahayak and what services does it provide?",
        "Government pension scheme for senior citizens",
    ]
    for q in queries:
        intent = router.classify_intent(q)
        assert intent == QueryIntent.LOCAL_SCHEME_FAQ, f"Query '{q}' mapped to {intent}, expected LOCAL_SCHEME_FAQ"

def test_semantic_router_out_of_domain_intent():
    """Verify that general knowledge queries absent from the local index classify as OUT_OF_DOMAIN."""
    router = SemanticRouterAdapter()
    queries = [
        "Who was the first president of the United States?",
        "What is the capital of Madagascar?",
        "How do airplanes fly in physics?",
        "Distance between earth and moon",
    ]
    for q in queries:
        intent = router.classify_intent(q)
        assert intent == QueryIntent.OUT_OF_DOMAIN, f"Query '{q}' mapped to {intent}, expected OUT_OF_DOMAIN"

def test_semantic_router_boundary_and_empty_queries():
    """Verify safe fallback on empty, whitespace, and symbol-only queries."""
    router = SemanticRouterAdapter()
    assert router.classify_intent("") == QueryIntent.OUT_OF_DOMAIN
    assert router.classify_intent("   ") == QueryIntent.OUT_OF_DOMAIN
    assert router.classify_intent("??? !!! ...") == QueryIntent.OUT_OF_DOMAIN
