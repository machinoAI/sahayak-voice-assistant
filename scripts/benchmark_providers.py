#!/usr/bin/env python3
"""
Automated Provider Latency Benchmarking Suite for Sahayak Voice Assistant.
Systematically benchmarks TTFT (Time-to-First-Token), TTFAB (Time-to-First-Audio-Byte),
token velocity, synthesis throughput, and coupled end-to-end voice latency budgets.

Usage:
    python scripts/benchmark_providers.py --mode all
    python scripts/benchmark_providers.py --llm groq,gemini --tts edge,cartesia --runs 3
    python scripts/benchmark_providers.py --include-mock --output benchmarks/report.json
"""

import os
import sys
import time
import json
import re
import asyncio
import argparse
import statistics
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.interfaces.adapters import LLMClientProtocol, TTSClientProtocol
from app.adapters.registry import (
    get_llm_adapter,
    get_tts_adapter,
    SUPPORTED_PROVIDERS,
    validate_provider,
)

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


# ANSI Color Codes
CLR_RESET = "\033[0m"
CLR_BOLD = "\033[1m"
CLR_DIM = "\033[2m"
CLR_CYAN = "\033[36m"
CLR_GREEN = "\033[32m"
CLR_YELLOW = "\033[33m"
CLR_RED = "\033[31m"
CLR_BLUE = "\033[34m"
CLR_MAGENTA = "\033[35m"


# Mock Simulated Adapters for Unconfigured Cloud Providers
class MockSimulatedLLMAdapter:
    """Simulates a cloud LLM provider with realistic TTFT and token streaming cadence."""
    def __init__(self, provider: str, model: str, base_ttft_ms: float = 380.0, tok_speed_ms: float = 12.0):
        self.provider = provider
        self.model = model
        self.base_ttft_ms = base_ttft_ms
        self.tok_speed_ms = tok_speed_ms

    async def stream_tokens(self, prompt: str, system_prompt: Optional[str] = None):
        await asyncio.sleep(self.base_ttft_ms / 1000.0)
        tokens = [
            "Voice ", "AI ", "empowers ", "citizens ", "by ", "providing ", 
            "instant, ", "natural, ", "and ", "accessible ", "public ", "services."
        ]
        for tok in tokens:
            yield tok
            await asyncio.sleep(self.tok_speed_ms / 1000.0)


class MockSimulatedTTSAdapter:
    """Simulates a neural TTS provider with realistic TTFAB and chunk streaming cadence."""
    def __init__(self, provider: str, base_ttfab_ms: float = 240.0, chunk_cadence_ms: float = 20.0):
        self.provider = provider
        self.base_ttfab_ms = base_ttfab_ms
        self.chunk_cadence_ms = chunk_cadence_ms

    async def synthesize_stream(self, text: str, voice_override: Optional[str] = None, language: Optional[str] = None):
        await asyncio.sleep(self.base_ttfab_ms / 1000.0)
        # Yield 15 chunks of 640 bytes 16kHz linear PCM (total ~9.6KB)
        chunk = b"\x00\x05" * 320
        for _ in range(15):
            yield chunk
            await asyncio.sleep(self.chunk_cadence_ms / 1000.0)


def split_sentences_boundary(text: str) -> List[str]:
    """Lightweight sentence splitter matching Sahayak's streaming voice pipeline regex."""
    pattern = r'(?<=[.!?।])\s+'
    parts = re.split(pattern, text)
    return [p.strip() for p in parts if p.strip()]


class BenchmarkRunner:
    def __init__(
        self,
        runs: int = 3,
        prompt: str = "Explain in one concise sentence how voice AI improves citizen services in India.",
        tts_text: str = "Sahayak is an ultra low latency multilingual voice assistant for citizen services.",
        include_mock: bool = False,
    ):
        self.runs = runs
        self.prompt = prompt
        self.tts_text = tts_text
        self.include_mock = include_mock

    def get_llm_instance(self, name: str) -> Optional[LLMClientProtocol]:
        has_key = False
        if name == "groq" and bool(settings.GROQ_API_KEY):
            has_key = True
        elif name == "gemini" and bool(settings.GEMINI_API_KEY):
            has_key = True
        elif name == "openai" and bool(settings.OPENAI_API_KEY):
            has_key = True
        elif name == "anthropic" and bool(settings.ANTHROPIC_API_KEY):
            has_key = True
        elif name == "ollama":
            has_key = False  # requires local ollama server

        if has_key:
            try:
                return get_llm_adapter(name, enable_failover=False)
            except Exception:
                pass

        if self.include_mock:
            sim_profiles = {
                "groq": (195.0, 8.0, "openai/gpt-oss-120b"),
                "gemini": (310.0, 12.0, "gemini-3.8-flash"),
                "openai": (320.0, 15.0, "gpt-4o-mini"),
                "anthropic": (280.0, 11.0, "claude-3-5-haiku-20241022"),
                "ollama": (540.0, 22.0, "llama3.2"),
            }
            base_ttft, speed, model_name = sim_profiles.get(name, (350.0, 14.0, "default"))
            return MockSimulatedLLMAdapter(name, model_name, base_ttft, speed)
        return None

    def get_tts_instance(self, name: str) -> Optional[TTSClientProtocol]:
        has_key = False
        if name == "cartesia" and bool(settings.CARTESIA_API_KEY):
            has_key = True
        elif name == "elevenlabs" and bool(settings.ELEVENLABS_API_KEY):
            has_key = True
        elif name == "edge":
            has_key = True

        if has_key:
            try:
                return get_tts_adapter(name, enable_failover=False)
            except Exception:
                pass

        if self.include_mock:
            sim_profiles = {
                "cartesia": (180.0, 20.0),
                "edge": (380.0, 30.0),
                "elevenlabs": (220.0, 20.0),
            }
            base_ttfab, cadence = sim_profiles.get(name, (250.0, 20.0))
            return MockSimulatedTTSAdapter(name, base_ttfab, cadence)
        return None

    async def benchmark_single_llm(self, name: str, adapter: LLMClientProtocol) -> Dict[str, Any]:
        ttft_samples: List[float] = []
        total_time_samples: List[float] = []
        velocity_samples: List[float] = []
        token_count_samples: List[int] = []
        sample_output = ""

        # Warmup iteration
        try:
            async for _ in adapter.stream_tokens("Warmup prompt"):
                break
        except Exception:
            pass

        for i in range(self.runs):
            t_start = time.perf_counter()
            first_tok_time: Optional[float] = None
            tokens: List[str] = []

            try:
                async for tok in adapter.stream_tokens(self.prompt):
                    if first_tok_time is None and tok.strip():
                        first_tok_time = time.perf_counter()
                    tokens.append(tok)

                t_end = time.perf_counter()

                if first_tok_time is not None:
                    ttft_ms = (first_tok_time - t_start) * 1000.0
                    total_ms = (t_end - t_start) * 1000.0
                    tok_count = len(tokens)
                    gen_time_s = max(0.001, (t_end - first_tok_time))
                    tok_vel = tok_count / gen_time_s

                    ttft_samples.append(ttft_ms)
                    total_time_samples.append(total_ms)
                    velocity_samples.append(tok_vel)
                    token_count_samples.append(tok_count)
                    sample_output = "".join(tokens).strip()

            except Exception as e:
                # If cloud fails, break early
                return {
                    "provider": name,
                    "status": "FAILED",
                    "error": str(e),
                }

        if not ttft_samples:
            return {
                "provider": name,
                "status": "ERROR",
                "error": "No tokens collected",
            }

        return {
            "provider": name,
            "status": "SUCCESS",
            "model": getattr(adapter, "model", "default"),
            "is_mock": isinstance(adapter, MockSimulatedLLMAdapter),
            "runs": len(ttft_samples),
            "ttft_ms_mean": round(statistics.mean(ttft_samples), 1),
            "ttft_ms_median": round(statistics.median(ttft_samples), 1),
            "ttft_ms_min": round(min(ttft_samples), 1),
            "ttft_ms_max": round(max(ttft_samples), 1),
            "total_ms_mean": round(statistics.mean(total_time_samples), 1),
            "tokens_sec_mean": round(statistics.mean(velocity_samples), 1),
            "avg_tokens": round(statistics.mean(token_count_samples), 1),
            "sample_output": sample_output[:80] + ("..." if len(sample_output) > 80 else ""),
        }

    async def benchmark_single_tts(self, name: str, adapter: TTSClientProtocol) -> Dict[str, Any]:
        ttfab_samples: List[float] = []
        total_time_samples: List[float] = []
        byte_samples: List[int] = []
        chunk_count_samples: List[int] = []

        # Warmup iteration
        try:
            async for _ in adapter.synthesize_stream("Warmup"):
                break
        except Exception:
            pass

        for i in range(self.runs):
            t_start = time.perf_counter()
            first_byte_time: Optional[float] = None
            total_bytes = 0
            chunks = 0

            try:
                async for chunk in adapter.synthesize_stream(self.tts_text):
                    if first_byte_time is None and len(chunk) > 0:
                        first_byte_time = time.perf_counter()
                    total_bytes += len(chunk)
                    chunks += 1

                t_end = time.perf_counter()

                if first_byte_time is not None:
                    ttfab_ms = (first_byte_time - t_start) * 1000.0
                    total_ms = (t_end - t_start) * 1000.0
                    ttfab_samples.append(ttfab_ms)
                    total_time_samples.append(total_ms)
                    byte_samples.append(total_bytes)
                    chunk_count_samples.append(chunks)

            except Exception as e:
                return {
                    "provider": name,
                    "status": "FAILED",
                    "error": str(e),
                }

        if not ttfab_samples:
            return {
                "provider": name,
                "status": "ERROR",
                "error": "No audio chunks yielded",
            }

        avg_bytes = statistics.mean(byte_samples)
        avg_total_ms = statistics.mean(total_time_samples)
        # Real-Time Factor (RTF): 16kHz 16-bit mono = 32,000 bytes/sec
        est_audio_sec = avg_bytes / 32000.0
        synthesis_sec = avg_total_ms / 1000.0
        rtf = synthesis_sec / max(0.001, est_audio_sec)

        return {
            "provider": name,
            "status": "SUCCESS",
            "is_mock": isinstance(adapter, MockSimulatedTTSAdapter),
            "runs": len(ttfab_samples),
            "ttfab_ms_mean": round(statistics.mean(ttfab_samples), 1),
            "ttfab_ms_median": round(statistics.median(ttfab_samples), 1),
            "ttfab_ms_min": round(min(ttfab_samples), 1),
            "ttfab_ms_max": round(max(ttfab_samples), 1),
            "total_synthesis_ms": round(avg_total_ms, 1),
            "avg_bytes": int(avg_bytes),
            "avg_chunks": round(statistics.mean(chunk_count_samples), 1),
            "rtf": round(rtf, 3),
        }

    async def benchmark_coupled_pipeline(
        self,
        llm_name: str,
        llm_adapter: LLMClientProtocol,
        tts_name: str,
        tts_adapter: TTSClientProtocol,
    ) -> Dict[str, Any]:
        """Measures End-to-End TTFAB simulating Sahayak's decoupled token-to-speech queue worker."""
        e2e_samples: List[float] = []
        llm_ttft_samples: List[float] = []
        tts_ttfab_samples: List[float] = []

        for _ in range(self.runs):
            t_turn_start = time.perf_counter()
            first_llm_tok_time: Optional[float] = None
            first_audio_byte_time: Optional[float] = None

            sentence_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

            # Consumer: TTS synthesis worker
            async def tts_worker():
                nonlocal first_audio_byte_time
                while True:
                    sentence = await sentence_queue.get()
                    if sentence is None:
                        sentence_queue.task_done()
                        break
                    try:
                        async for chunk in tts_adapter.synthesize_stream(sentence):
                            if first_audio_byte_time is None and len(chunk) > 0:
                                first_audio_byte_time = time.perf_counter()
                    finally:
                        sentence_queue.task_done()

            tts_task = asyncio.create_task(tts_worker())

            # Producer: LLM Stream + Incremental Sentence Splitter
            sentence_buffer = ""
            try:
                async for tok in llm_adapter.stream_tokens(self.prompt):
                    if first_llm_tok_time is None and tok.strip():
                        first_llm_tok_time = time.perf_counter()
                    sentence_buffer += tok

                    # Check for sentence completion
                    if re.search(r'[.!?।]\s*$', sentence_buffer):
                        sentences = split_sentences_boundary(sentence_buffer)
                        if len(sentences) > 1:
                            for s in sentences[:-1]:
                                await sentence_queue.put(s)
                            sentence_buffer = sentences[-1]

                if sentence_buffer.strip():
                    await sentence_queue.put(sentence_buffer.strip())
                await sentence_queue.put(None)  # Sentinel

                await tts_task

                if first_audio_byte_time is not None:
                    e2e_ms = (first_audio_byte_time - t_turn_start) * 1000.0
                    llm_ms = ((first_llm_tok_time - t_turn_start) * 1000.0) if first_llm_tok_time else 0.0
                    tts_ms = ((first_audio_byte_time - first_llm_tok_time) * 1000.0) if first_llm_tok_time else e2e_ms
                    e2e_samples.append(e2e_ms)
                    llm_ttft_samples.append(llm_ms)
                    tts_ttfab_samples.append(tts_ms)

            except Exception as e:
                tts_task.cancel()
                return {
                    "pairing": f"{llm_name} + {tts_name}",
                    "status": "FAILED",
                    "error": str(e),
                }

        if not e2e_samples:
            return {
                "pairing": f"{llm_name} + {tts_name}",
                "status": "ERROR",
                "error": "No audio packets produced",
            }

        mean_e2e = statistics.mean(e2e_samples)
        budget_limit = 1200.0  # Sahayak Sub-1.2s target budget
        return {
            "pairing": f"{llm_name} + {tts_name}",
            "llm": llm_name,
            "tts": tts_name,
            "status": "SUCCESS",
            "runs": len(e2e_samples),
            "e2e_ttfab_mean": round(mean_e2e, 1),
            "e2e_ttfab_min": round(min(e2e_samples), 1),
            "e2e_ttfab_max": round(max(e2e_samples), 1),
            "llm_ttft_mean": round(statistics.mean(llm_ttft_samples), 1),
            "tts_ttfab_mean": round(statistics.mean(tts_ttfab_samples), 1),
            "budget_ms": budget_limit,
            "budget_utilization_pct": round((mean_e2e / budget_limit) * 100, 1),
            "target_budget_met": mean_e2e <= budget_limit,
        }


def render_ascii_bar(val: float, max_val: float, width: int = 24, fill_char: str = "█", empty_char: str = "░") -> str:
    """Renders a clean ASCII progress/latency bar."""
    if max_val <= 0:
        return empty_char * width
    pct = min(1.0, max(0.0, val / max_val))
    filled = int(round(pct * width))
    return (fill_char * filled) + (empty_char * (width - filled))


def print_banner(text: str):
    print(f"\n{CLR_CYAN}{CLR_BOLD}{'='*78}{CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}  {text}{CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}{'='*78}{CLR_RESET}\n")


async def main():
    parser = argparse.ArgumentParser(description="Sahayak Multi-Provider Latency Benchmarking Suite")
    parser.add_argument("--mode", choices=["all", "llm", "tts", "pipeline"], default="all", help="Benchmark target mode")
    parser.add_argument("--llm", default="all", help="Comma-separated LLM providers or 'all'")
    parser.add_argument("--tts", default="all", help="Comma-separated TTS providers or 'all'")
    parser.add_argument("--runs", type=int, default=3, help="Benchmark iterations per test")
    parser.add_argument("--prompt", default="Explain in one concise sentence how voice AI improves citizen services in India.", help="Benchmark prompt")
    parser.add_argument("--tts-text", default="Sahayak is an ultra low latency multilingual voice assistant for citizen services.", help="TTS test text")
    parser.add_argument("--output", default="docs/BENCHMARKS.md", help="Export report path (.md or .json)")
    parser.add_argument("--include-mock", action="store_true", help="Include simulated mock adapters for unconfigured keys")
    args = parser.parse_args()

    print_banner("SAHAYAK MULTI-PROVIDER LATENCY BENCHMARK SUITE")
    print(f"{CLR_BOLD}Target Budget:{CLR_RESET} Sub-1.2s End-to-End Voice TTFAB")
    print(f"{CLR_BOLD}Iterations:{CLR_RESET} {args.runs} runs per provider/pairing")
    print(f"{CLR_BOLD}Include Mocks:{CLR_RESET} {args.include_mock}")
    print(f"{CLR_BOLD}Test Prompt:{CLR_RESET} \"{args.prompt}\"")

    runner = BenchmarkRunner(
        runs=args.runs,
        prompt=args.prompt,
        tts_text=args.tts_text,
        include_mock=args.include_mock,
    )

    # 1. Resolve Target Providers
    all_llms = ["groq", "gemini", "openai", "anthropic", "ollama"]
    all_tts = ["cartesia", "edge", "elevenlabs"]

    selected_llms = all_llms if args.llm == "all" else [p.strip().lower() for p in args.llm.split(",")]
    selected_tts = all_tts if args.tts == "all" else [p.strip().lower() for p in args.tts.split(",")]

    results: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runs_per_test": args.runs,
        "prompt": args.prompt,
        "llm_benchmarks": [],
        "tts_benchmarks": [],
        "pipeline_benchmarks": [],
    }

    # =========================================================================
    # PART 1: LLM BENCHMARK
    # =========================================================================
    if args.mode in ("all", "llm"):
        print_banner("STAGE 1: LLM STREAMING INFERENCE LATENCY (TTFT & VELOCITY)")
        llm_table_rows = []

        for name in selected_llms:
            print(f"Benchmarking LLM [{name}]...", end=" ", flush=True)
            adapter = runner.get_llm_instance(name)
            if not adapter:
                print(f"{CLR_YELLOW}[SKIPPED: Missing API key/server]{CLR_RESET}")
                llm_table_rows.append([name, "SKIPPED", "--", "--", "--", "--", "Key/Endpoint missing"])
                continue

            res = await runner.benchmark_single_llm(name, adapter)
            results["llm_benchmarks"].append(res)

            if res["status"] == "SUCCESS":
                tag = f" {CLR_DIM}(mock){CLR_RESET}" if res["is_mock"] else ""
                print(f"{CLR_GREEN}[OK]{CLR_RESET} TTFT: {res['ttft_ms_mean']}ms | Velocity: {res['tokens_sec_mean']} tok/s")
                llm_table_rows.append([
                    f"{res['provider']}{tag}",
                    res["model"],
                    f"{res['ttft_ms_mean']} ms",
                    f"{res['ttft_ms_min']} - {res['ttft_ms_max']} ms",
                    f"{res['tokens_sec_mean']} tok/s",
                    res["avg_tokens"],
                    "SUCCESS"
                ])
            else:
                print(f"{CLR_RED}[FAILED]{CLR_RESET} {res.get('error', 'Unknown')}")
                llm_table_rows.append([name, "FAILED", "--", "--", "--", "--", res.get("error", "Error")[:25]])

        headers_llm = ["Provider", "Model", "Mean TTFT", "Min-Max Range", "Velocity", "Avg Tokens", "Status"]
        if HAS_TABULATE:
            print("\n" + tabulate(llm_table_rows, headers=headers_llm, tablefmt="github") + "\n")

    # =========================================================================
    # PART 2: TTS BENCHMARK
    # =========================================================================
    if args.mode in ("all", "tts"):
        print_banner("STAGE 2: NEURAL TTS SYNTHESIS LATENCY (TTFAB & RTF)")
        tts_table_rows = []

        for name in selected_tts:
            print(f"Benchmarking TTS [{name}]...", end=" ", flush=True)
            adapter = runner.get_tts_instance(name)
            if not adapter:
                print(f"{CLR_YELLOW}[SKIPPED: Missing API key]{CLR_RESET}")
                tts_table_rows.append([name, "SKIPPED", "--", "--", "--", "--", "Key missing"])
                continue

            res = await runner.benchmark_single_tts(name, adapter)
            results["tts_benchmarks"].append(res)

            if res["status"] == "SUCCESS":
                tag = f" {CLR_DIM}(mock){CLR_RESET}" if res["is_mock"] else ""
                print(f"{CLR_GREEN}[OK]{CLR_RESET} TTFAB: {res['ttfab_ms_mean']}ms | RTF: {res['rtf']}x")
                tts_table_rows.append([
                    f"{res['provider']}{tag}",
                    f"{res['ttfab_ms_mean']} ms",
                    f"{res['ttfab_ms_min']} - {res['ttfab_ms_max']} ms",
                    f"{res['total_synthesis_ms']} ms",
                    f"{res['avg_bytes']:,} B",
                    f"{res['rtf']}x",
                    "SUCCESS"
                ])
            else:
                print(f"{CLR_RED}[FAILED]{CLR_RESET} {res.get('error', 'Unknown')}")
                tts_table_rows.append([name, "FAILED", "--", "--", "--", "--", res.get("error", "Error")[:25]])

        headers_tts = ["TTS Engine", "Mean TTFAB", "Min-Max Range", "Total Synth", "Audio Bytes", "RTF (Realtime)", "Status"]
        if HAS_TABULATE:
            print("\n" + tabulate(tts_table_rows, headers=headers_tts, tablefmt="github") + "\n")

    # =========================================================================
    # PART 3: COUPLED PIPELINE BENCHMARK (VOICE BUDGET < 1.2s)
    # =========================================================================
    if args.mode in ("all", "pipeline"):
        print_banner("STAGE 3: COUPLED END-TO-END VOICE BUDGET (TARGET < 1200ms)")
        pipeline_table_rows = []

        active_llm_adapters = [(name, runner.get_llm_instance(name)) for name in selected_llms]
        active_tts_adapters = [(name, runner.get_tts_instance(name)) for name in selected_tts]

        valid_llm_pairs = [(name, inst) for name, inst in active_llm_adapters if inst is not None]
        valid_tts_pairs = [(name, inst) for name, inst in active_tts_adapters if inst is not None]

        for llm_name, llm_inst in valid_llm_pairs:
            for tts_name, tts_inst in valid_tts_pairs:
                pairing_key = f"{llm_name} + {tts_name}"
                print(f"Benchmarking Pipeline [{pairing_key}]...", end=" ", flush=True)

                res = await runner.benchmark_coupled_pipeline(llm_name, llm_inst, tts_name, tts_inst)
                results["pipeline_benchmarks"].append(res)

                if res["status"] == "SUCCESS":
                    e2e = res["e2e_ttfab_mean"]
                    pass_str = f"{CLR_GREEN}PASS (<1.2s){CLR_RESET}" if res["target_budget_met"] else f"{CLR_RED}EXCEEDED{CLR_RESET}"
                    print(f"{CLR_GREEN}[OK]{CLR_RESET} End-to-End TTFAB: {e2e}ms ({res['budget_utilization_pct']}% of 1.2s budget)")
                    pipeline_table_rows.append([
                        pairing_key,
                        f"{res['llm_ttft_mean']} ms",
                        f"{res['tts_ttfab_mean']} ms",
                        f"{e2e} ms",
                        f"{res['budget_utilization_pct']}%",
                        "PASS" if res["target_budget_met"] else "EXCEEDED"
                    ])
                else:
                    print(f"{CLR_RED}[FAILED]{CLR_RESET} {res.get('error', 'Error')}")
                    pipeline_table_rows.append([pairing_key, "--", "--", "--", "--", "FAILED"])

        headers_pipe = ["Pipeline Pairing", "LLM TTFT", "TTS Delta", "E2E TTFAB", "Budget Used", "Budget Met"]
        if HAS_TABULATE:
            print("\n" + tabulate(pipeline_table_rows, headers=headers_pipe, tablefmt="github") + "\n")

    # =========================================================================
    # PART 4: VISUAL ASCII COMPARISON CHARTS
    # =========================================================================
    print_banner("VISUAL LATENCY PROFILES & COMPARATIVE CHARTS")

    # LLM TTFT Chart
    valid_llm_results = [r for r in results["llm_benchmarks"] if r.get("status") == "SUCCESS"]
    if valid_llm_results:
        print(f"{CLR_BOLD}LLM Streaming Latency (Time to First Token - Lower is Better):{CLR_RESET}")
        max_ttft = max([r["ttft_ms_mean"] for r in valid_llm_results] + [600.0])
        fastest_llm = min(valid_llm_results, key=lambda x: x["ttft_ms_mean"])
        for r in sorted(valid_llm_results, key=lambda x: x["ttft_ms_mean"]):
            bar = render_ascii_bar(r["ttft_ms_mean"], max_ttft, width=28)
            crown = " ⚡ (Fastest)" if r["provider"] == fastest_llm["provider"] else ""
            print(f"  {r['provider']:<12} [{bar}] {r['ttft_ms_mean']:>6.1f} ms{crown}")
        print()

    # TTS TTFAB Chart
    valid_tts_results = [r for r in results["tts_benchmarks"] if r.get("status") == "SUCCESS"]
    if valid_tts_results:
        print(f"{CLR_BOLD}TTS Synthesis Latency (Time to First Audio Byte - Lower is Better):{CLR_RESET}")
        max_ttfab = max([r["ttfab_ms_mean"] for r in valid_tts_results] + [500.0])
        fastest_tts = min(valid_tts_results, key=lambda x: x["ttfab_ms_mean"])
        for r in sorted(valid_tts_results, key=lambda x: x["ttfab_ms_mean"]):
            bar = render_ascii_bar(r["ttfab_ms_mean"], max_ttfab, width=28)
            crown = " 🔊 (Fastest)" if r["provider"] == fastest_tts["provider"] else ""
            print(f"  {r['provider']:<12} [{bar}] {r['ttfab_ms_mean']:>6.1f} ms{crown}")
        print()

    # End-to-End Voice Budget Chart
    valid_pipe_results = [r for r in results["pipeline_benchmarks"] if r.get("status") == "SUCCESS"]
    if valid_pipe_results:
        print(f"{CLR_BOLD}Coupled Pipeline End-to-End Voice Budget (Target < 1200ms):{CLR_RESET}")
        max_e2e = 1400.0
        for r in sorted(valid_pipe_results, key=lambda x: x["e2e_ttfab_mean"]):
            bar = render_ascii_bar(r["e2e_ttfab_mean"], max_e2e, width=30)
            status_tag = f"{CLR_GREEN}PASS{CLR_RESET}" if r["target_budget_met"] else f"{CLR_RED}FAIL{CLR_RESET}"
            print(f"  {r['pairing']:<24} [{bar}] {r['e2e_ttfab_mean']:>6.1f} ms  [{status_tag}] ({r['budget_utilization_pct']}%)")
        print(f"  {'1200ms Budget Threshold':<24}  ------------------------------| (Budget Ceiling)")
        print()

    # =========================================================================
    # PART 5: EXPORT BENCHMARK REPORT
    # =========================================================================
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.suffix.lower() == ".json":
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"{CLR_GREEN}✓ Exported raw benchmark JSON to {out_path}{CLR_RESET}")
    else:
        # Markdown Output
        md_lines = [
            "# Sahayak Multi-Provider Latency Benchmarks\n",
            f"*Generated on: {results['timestamp']}*\n",
            f"- **Target Voice Budget:** Sub-1.2s ($1200\\text{{ms}}$) End-to-End TTFAB",
            f"- **Benchmark Iterations:** {args.runs} runs per pairing",
            f"- **Benchmark Query:** \"{args.prompt}\"\n",
            "## 1. LLM Streaming Performance (TTFT & Velocity)\n",
        ]
        if valid_llm_results:
            md_lines.append("| Provider | Model | Mean TTFT | Min - Max | Token Velocity | Avg Tokens |")
            md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for r in valid_llm_results:
                md_lines.append(f"| **{r['provider']}** | `{r['model']}` | **{r['ttft_ms_mean']} ms** | {r['ttft_ms_min']} - {r['ttft_ms_max']} ms | {r['tokens_sec_mean']} tok/s | {r['avg_tokens']} |")
            md_lines.append("")

        md_lines.append("## 2. Neural TTS Synthesis Performance (TTFAB & RTF)\n")
        if valid_tts_results:
            md_lines.append("| TTS Engine | Mean TTFAB | Min - Max | Total Synth Time | Audio Bytes | Real-Time Factor (RTF) |")
            md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for r in valid_tts_results:
                md_lines.append(f"| **{r['provider']}** | **{r['ttfab_ms_mean']} ms** | {r['ttfab_ms_min']} - {r['ttfab_ms_max']} ms | {r['total_synthesis_ms']} ms | {r['avg_bytes']:,} B | {r['rtf']}x |")
            md_lines.append("")

        md_lines.append("## 3. Coupled End-to-End Voice Budget Benchmark\n")
        if valid_pipe_results:
            md_lines.append("| Pipeline Configuration | LLM TTFT | TTS First Packet | End-to-End TTFAB | Budget Used | Status |")
            md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for r in valid_pipe_results:
                st = "✅ PASS (<1.2s)" if r["target_budget_met"] else "❌ EXCEEDED"
                md_lines.append(f"| **{r['pairing']}** | {r['llm_ttft_mean']} ms | {r['tts_ttfab_mean']} ms | **{r['e2e_ttfab_mean']} ms** | {r['budget_utilization_pct']}% | {st} |")
            md_lines.append("")

        with open(out_path, "w") as f:
            f.write("\n".join(md_lines))
        print(f"{CLR_GREEN}✓ Exported comprehensive Markdown benchmark report to {out_path}{CLR_RESET}")


if __name__ == "__main__":
    asyncio.run(main())
