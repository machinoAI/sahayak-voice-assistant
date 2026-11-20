# Sahayak Multi-Provider Latency Benchmarks

*Generated on: 2026-11-20T19:44:25Z*

- **Target Voice Budget:** Sub-1.2s ($1200\text{ms}$) End-to-End TTFAB
- **Benchmark Iterations:** 2 runs per pairing
- **Benchmark Query:** "Explain in one concise sentence how voice AI improves citizen services in India."

## 1. LLM Streaming Performance (TTFT & Velocity)

| Provider | Model | Mean TTFT | Min - Max | Token Velocity | Avg Tokens |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **groq** | `openai/gpt-oss-120b` | **380.7 ms** | 299.3 - 462.0 ms | 468.3 tok/s | 41.5 |
| **openai** | `gpt-4o-mini` | **321.0 ms** | 320.8 - 321.2 ms | 63.7 tok/s | 12 |
| **anthropic** | `claude-3-5-haiku-20241022` | **292.3 ms** | 280.2 - 304.4 ms | 81.7 tok/s | 12 |
| **ollama** | `llama3.2` | **541.0 ms** | 540.8 - 541.2 ms | 43.9 tok/s | 12 |

## 2. Neural TTS Synthesis Performance (TTFAB & RTF)

| TTS Engine | Mean TTFAB | Min - Max | Total Synth Time | Audio Bytes | Real-Time Factor (RTF) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **cartesia** | **637.1 ms** | 576.9 - 697.3 ms | 888.6 ms | 38,448 B | 0.74x |
| **edge** | **441.8 ms** | 441.4 - 442.2 ms | 774.4 ms | 38,448 B | 0.645x |
| **elevenlabs** | **220.4 ms** | 220.1 - 220.6 ms | 532.9 ms | 9,600 B | 1.776x |

## 3. Coupled End-to-End Voice Budget Benchmark

| Pipeline Configuration | LLM TTFT | TTS First Packet | End-to-End TTFAB | Budget Used | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **groq + cartesia** | 509.3 ms | 2087.5 ms | **2596.8 ms** | 216.4% | ❌ EXCEEDED |
| **groq + edge** | 422.2 ms | 2366.8 ms | **2789.1 ms** | 232.4% | ❌ EXCEEDED |
| **groq + elevenlabs** | 498.6 ms | 303.8 ms | **802.4 ms** | 66.9% | ✅ PASS (<1.2s) |
| **openai + cartesia** | 321.2 ms | 1114.6 ms | **1435.8 ms** | 119.6% | ❌ EXCEEDED |
| **openai + edge** | 320.7 ms | 739.1 ms | **1059.8 ms** | 88.3% | ✅ PASS (<1.2s) |
| **openai + elevenlabs** | 321.0 ms | 408.7 ms | **729.7 ms** | 60.8% | ✅ PASS (<1.2s) |
| **anthropic + cartesia** | 280.5 ms | 795.6 ms | **1076.1 ms** | 89.7% | ✅ PASS (<1.2s) |
| **anthropic + edge** | 280.6 ms | 681.9 ms | **962.5 ms** | 80.2% | ✅ PASS (<1.2s) |
| **anthropic + elevenlabs** | 280.3 ms | 363.0 ms | **643.4 ms** | 53.6% | ✅ PASS (<1.2s) |
| **ollama + cartesia** | 540.8 ms | 859.9 ms | **1400.8 ms** | 116.7% | ❌ EXCEEDED |
| **ollama + edge** | 540.9 ms | 760.6 ms | **1301.5 ms** | 108.5% | ❌ EXCEEDED |
| **ollama + elevenlabs** | 540.7 ms | 492.2 ms | **1032.8 ms** | 86.1% | ✅ PASS (<1.2s) |
