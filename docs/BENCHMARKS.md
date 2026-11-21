# Sahayak Multi-Provider Latency Benchmarks

*Generated on: 2026-11-21T17:10:25Z*

- **Target Voice Budget:** Sub-1.2s ($1200\text{ms}$) End-to-End TTFAB
- **Benchmark Iterations:** 1 runs per pairing
- **Benchmark Query:** "Explain in one concise sentence how voice AI improves citizen services in India."

## 1. LLM Streaming Performance (TTFT & Velocity)

| Provider | Model | Mean TTFT | Min - Max | Token Velocity | Avg Tokens |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **groq** | `openai/gpt-oss-120b` | **568.8 ms** | 568.8 - 568.8 ms | 463.7 tok/s | 40 |
| **gemini** | `gemini-3-flash-preview` | **2256.7 ms** | 2256.7 - 2256.7 ms | 1011.8 tok/s | 2 |

## 2. Neural TTS Synthesis Performance (TTFAB & RTF)

| TTS Engine | Mean TTFAB | Min - Max | Total Synth Time | Audio Bytes | Real-Time Factor (RTF) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **cartesia** | **554.1 ms** | 554.1 - 554.1 ms | 846.5 ms | 38,448 B | 0.705x |
| **edge** | **550.4 ms** | 550.4 - 550.4 ms | 799.8 ms | 38,448 B | 0.666x |
| **elevenlabs** | **358.0 ms** | 358.0 - 358.0 ms | 454.9 ms | 182,788 B | 0.08x |

## 3. Coupled End-to-End Voice Budget Benchmark

| Pipeline Configuration | LLM TTFT | TTS First Packet | End-to-End TTFAB | Budget Used | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **groq + cartesia** | 351.8 ms | 1415.3 ms | **1767.1 ms** | 147.3% | ❌ EXCEEDED |
| **groq + edge** | 543.8 ms | 4133.8 ms | **4677.6 ms** | 389.8% | ❌ EXCEEDED |
| **groq + elevenlabs** | 479.2 ms | 878.2 ms | **1357.4 ms** | 113.1% | ❌ EXCEEDED |
| **gemini + cartesia** | 2025.2 ms | 901.5 ms | **2926.7 ms** | 243.9% | ❌ EXCEEDED |
| **gemini + edge** | 2238.2 ms | 3240.4 ms | **5478.6 ms** | 456.6% | ❌ EXCEEDED |
| **gemini + elevenlabs** | 2674.4 ms | 549.5 ms | **3223.9 ms** | 268.7% | ❌ EXCEEDED |
