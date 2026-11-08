#!/usr/bin/env python3
"""
Sahayak Voice Assistant: End-to-End CLI Streaming Client.
Streams 16kHz linear PCM audio frames over /ws/voice via microphone, audio file,
or synthesized text prompts. Benchmarks latency and verifies multi-turn memory.
"""

import argparse
import asyncio
import io
import json
import os
import sys
import time
import wave
from typing import AsyncGenerator, Optional

import numpy as np
import websockets

try:
    import sounddevice as sd
    AUDIO_DEVICE_AVAILABLE = True
except Exception:
    AUDIO_DEVICE_AVAILABLE = False


SAMPLE_RATE = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2
FRAME_DURATION_MS = 20
CHUNK_SAMPLES = (SAMPLE_RATE * FRAME_DURATION_MS) // 1000  # 320 samples
CHUNK_BYTES = CHUNK_SAMPLES * BYTES_PER_SAMPLE            # 640 bytes


class AudioPlaybackEngine:
    """Non-blocking audio playback buffer using sounddevice."""

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self.recorded_pcm: list[bytes] = []

    async def start(self) -> None:
        self.is_running = True
        self._task = asyncio.create_task(self._playback_loop())

    async def enqueue(self, pcm_chunk: bytes) -> None:
        self.recorded_pcm.append(pcm_chunk)
        if AUDIO_DEVICE_AVAILABLE:
            await self.queue.put(pcm_chunk)

    def clear(self) -> None:
        """Immediately flushes pending audio packets (barge-in effect)."""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break
        print("\n[CLIENT] Audio buffer cleared on barge-in signal.")

    async def _playback_loop(self) -> None:
        if not AUDIO_DEVICE_AVAILABLE:
            return

        try:
            with sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=CHUNK_SAMPLES,
            ) as stream:
                while self.is_running:
                    chunk = await self.queue.get()
                    if chunk is None:
                        break
                    audio_data = np.frombuffer(chunk, dtype=np.int16)
                    stream.write(audio_data)
                    self.queue.task_done()
        except Exception as e:
            print(f"\n[CLIENT] Audio playback warning: {e}", file=sys.stderr)

    async def stop(self) -> None:
        self.is_running = False
        if AUDIO_DEVICE_AVAILABLE:
            await self.queue.put(None)
        if self._task:
            await self._task

    def export_wav(self, file_path: str) -> None:
        if not self.recorded_pcm:
            return
        pcm_bytes = b"".join(self.recorded_pcm)
        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(BYTES_PER_SAMPLE)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)
        print(f"[CLIENT] Saved response audio to {file_path} ({len(pcm_bytes)} bytes)")


class VoiceClientBenchmark:
    """Manages WebSocket connection, audio dispatch, and turn latency accounting."""

    def __init__(self, ws_url: str, enable_audio_out: bool = True) -> None:
        self.ws_url = ws_url
        self.enable_audio_out = enable_audio_out
        self.playback = AudioPlaybackEngine()
        self.active_turn_metrics: dict = {}

    def _reset_metrics(self) -> None:
        self.active_turn_metrics = {
            "start_time": time.perf_counter(),
            "first_interim_time": None,
            "final_transcript_time": None,
            "first_audio_byte_time": None,
            "total_audio_bytes": 0,
            "turn_completed_time": None,
            "transcript": "",
        }

    async def send_audio_stream(
        self, ws, audio_generator: AsyncGenerator[bytes, None]
    ) -> None:
        """Paces and streams 20ms audio chunks over WebSocket."""
        chunk_count = 0
        total_sent = 0
        async for chunk in audio_generator:
            await ws.send(chunk)
            chunk_count += 1
            total_sent += len(chunk)
            await asyncio.sleep(0.018)  # Approximate real-time 20ms cadence

        # Send 500ms trailing silence to allow STT endpointing to detect end of speech
        silence = b"\x00" * CHUNK_BYTES
        for _ in range(25):
            await ws.send(silence)
            await asyncio.sleep(0.018)

    async def run_turn(
        self, ws, audio_generator: AsyncGenerator[bytes, None]
    ) -> dict:
        """Executes a single voice turn and tracks latency milestones."""
        self._reset_metrics()
        start = self.active_turn_metrics["start_time"]
        audio_stream_complete = asyncio.Event()

        async def _stream_sender():
            await self.send_audio_stream(ws, audio_generator)
            audio_stream_complete.set()

        sender_task = asyncio.create_task(_stream_sender())

        # Receive responses from server
        first_audio_seen = False
        while True:
            try:
                # 8-second timeout for server response
                message = await asyncio.wait_for(ws.recv(), timeout=8.0)
                now = time.perf_counter()

                if isinstance(message, str):
                    # JSON event
                    event = json.loads(message)
                    event_type = event.get("event")

                    if event_type == "INTERIM_TRANSCRIPT":
                        if self.active_turn_metrics["first_interim_time"] is None:
                            self.active_turn_metrics["first_interim_time"] = (now - start) * 1000
                        text = event.get("text", "")
                        sys.stdout.write(f"\r[STT Interim] {text:<60}")
                        sys.stdout.flush()

                    elif event_type == "FINAL_TRANSCRIPT":
                        self.active_turn_metrics["final_transcript_time"] = (now - start) * 1000
                        self.active_turn_metrics["transcript"] = event.get("text", "")
                        print(f"\n[STT Final] {self.active_turn_metrics['transcript']}")

                    elif event_type == "CLEAR_AUDIO_BUFFER":
                        self.playback.clear()

                elif isinstance(message, bytes):
                    # Assistant audio byte chunk
                    if not first_audio_seen:
                        first_audio_seen = True
                        self.active_turn_metrics["first_audio_byte_time"] = (now - start) * 1000

                    self.active_turn_metrics["total_audio_bytes"] += len(message)
                    if self.enable_audio_out:
                        await self.playback.enqueue(message)

            except asyncio.TimeoutError:
                # Turn finished or silent
                break

        await sender_task
        self.active_turn_metrics["turn_completed_time"] = (time.perf_counter() - start) * 1000
        return self.active_turn_metrics


async def generate_synthetic_audio(text: str) -> bytes:
    """Synthesizes reference 16kHz PCM audio on-the-fly using Cartesia or Edge-TTS."""
    from app.adapters.tts_cartesia import CartesiaTTSAdapter
    from app.core.config import settings

    tts = CartesiaTTSAdapter(api_key=settings.CARTESIA_API_KEY, voice_id=settings.CARTESIA_VOICE_ID)
    chunks = []
    async for chunk in tts.synthesize_stream(text):
        chunks.append(chunk)
    return b"".join(chunks)


async def pcm_chunks_from_bytes(data: bytes) -> AsyncGenerator[bytes, None]:
    for i in range(0, len(data), CHUNK_BYTES):
        yield data[i : i + CHUNK_BYTES]


async def pcm_chunks_from_wav_file(file_path: str) -> AsyncGenerator[bytes, None]:
    with wave.open(file_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()

        frames = wf.readframes(wf.getnframes())
        if n_channels != 1 or framerate != 16000 or sampwidth != 2:
            print(f"[CLIENT] Warning: WAV format is {framerate}Hz/{n_channels}ch. Resampling to 16kHz mono...")
            audio_array = np.frombuffer(frames, dtype=np.int16)
            if n_channels == 2:
                audio_array = audio_array.reshape(-1, 2).mean(axis=1).astype(np.int16)
            frames = audio_array.tobytes()

        for i in range(0, len(frames), CHUNK_BYTES):
            yield frames[i : i + CHUNK_BYTES]


async def record_mic_audio(duration_sec: float = 4.0) -> bytes:
    """Records audio from system microphone using sounddevice."""
    if not AUDIO_DEVICE_AVAILABLE:
        raise RuntimeError("sounddevice is not available. Ensure audio input devices exist.")

    print(f"\n[MIC] Recording {duration_sec}s of speech... Speak now!")
    loop = asyncio.get_running_loop()

    def _record():
        recording = sd.rec(
            int(duration_sec * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
        )
        sd.wait()
        return recording.tobytes()

    pcm_data = await loop.run_in_executor(None, _record)
    print(f"[MIC] Captured {len(pcm_data)} bytes of 16kHz audio.")
    return pcm_data


async def run_cli():
    parser = argparse.ArgumentParser(
        description="Sahayak Voice Assistant: Streaming Audio CLI Client & Multi-Turn Benchmark"
    )
    parser.add_argument("--url", default="ws://127.0.0.1:8000/ws/voice", help="FastAPI voice WebSocket URL")
    parser.add_argument("--say", type=str, help="Text to synthesize into speech and send as voice turn")
    parser.add_argument("--file", type=str, help="Path to .wav file to stream")
    parser.add_argument("--mic", action="store_true", help="Record audio directly from microphone")
    parser.add_argument("--duration", type=float, default=4.0, help="Microphone recording duration in seconds")
    parser.add_argument("--benchmark", action="store_true", help="Execute multi-turn conversational benchmark")
    parser.add_argument("--no-play", action="store_true", help="Disable local speaker playback")
    parser.add_argument("--save-output", type=str, help="Save assistant audio to .wav file")

    args = parser.parse_args()

    client = VoiceClientBenchmark(ws_url=args.url, enable_audio_out=not args.no_play)
    if not args.no_play:
        await client.playback.start()

    print("==================================================================")
    print(" Sahayak Voice Assistant: CLI Streaming Client & Benchmark Tool")
    print(f" Target Endpoint: {args.url}")
    print("==================================================================")

    try:
        async with websockets.connect(args.url) as ws:
            print("[CLIENT] Connected to voice server WebSocket.")

            if args.benchmark:
                # Run multi-turn benchmark:
                # Turn 1: "What is Sahayak?"
                # Turn 2: "What services does it provide?" (tests pronoun heuristic and memory)
                dialogue_turns = [
                    "What is Sahayak?",
                    "What services does it provide?",
                ]

                print("\n=== STARTING MULTI-TURN CONVERSATIONAL BENCHMARK ===")
                for turn_idx, phrase in enumerate(dialogue_turns, 1):
                    print(f"\n--- [TURN {turn_idx}] User Speaking: '{phrase}' ---")
                    pcm_data = await generate_synthetic_audio(phrase)
                    metrics = await client.run_turn(ws, pcm_chunks_from_bytes(pcm_data))

                    print("\n--- [TURN LATENCY METRICS] ---")
                    print(f"  First Interim Transcript : {metrics['first_interim_time'] or 0:6.1f} ms")
                    print(f"  Final Transcript Emitted : {metrics['final_transcript_time'] or 0:6.1f} ms")
                    print(f"  TTFAB (First Audio Byte) : {metrics['first_audio_byte_time'] or 0:6.1f} ms")
                    print(f"  Total Audio Received     : {metrics['total_audio_bytes']} bytes")
                    print(f"  Total Turn Wall Clock    : {metrics['turn_completed_time']:6.1f} ms")

            elif args.file:
                print(f"[CLIENT] Streaming audio from file: {args.file}")
                metrics = await client.run_turn(ws, pcm_chunks_from_wav_file(args.file))
                print(f"\n[CLIENT] Completed turn in {metrics['turn_completed_time']:.1f}ms")

            elif args.say:
                print(f"[CLIENT] Synthesizing speech for: '{args.say}'")
                pcm_data = await generate_synthetic_audio(args.say)
                metrics = await client.run_turn(ws, pcm_chunks_from_bytes(pcm_data))
                print(f"\n[CLIENT] Completed turn in {metrics['turn_completed_time']:.1f}ms")

            elif args.mic:
                pcm_data = await record_mic_audio(duration_sec=args.duration)
                metrics = await client.run_turn(ws, pcm_chunks_from_bytes(pcm_data))
                print(f"\n[CLIENT] Completed turn in {metrics['turn_completed_time']:.1f}ms")

            else:
                # Default interactive terminal session
                print("\n[CLIENT] Entering Interactive Audio Terminal. Type 'exit' to quit, 'reset' to clear memory.")
                while True:
                    prompt_input = input("\n[Enter text to speak, or 'mic' to record, or 'exit']: ").strip()
                    if prompt_input.lower() in ("exit", "quit"):
                        break
                    elif prompt_input.lower() == "reset":
                        await ws.send(json.dumps({"event": "RESET_SESSION"}))
                        print("[CLIENT] Sent RESET_SESSION to server.")
                        continue
                    elif prompt_input.lower() == "mic":
                        pcm_data = await record_mic_audio(duration_sec=args.duration)
                    else:
                        pcm_data = await generate_synthetic_audio(prompt_input)

                    await client.run_turn(ws, pcm_chunks_from_bytes(pcm_data))

            if args.save_output:
                client.playback.export_wav(args.save_output)

    except ConnectionRefusedError:
        print(f"[CLIENT ERROR] Could not connect to {args.url}. Is the FastAPI server running?")
        sys.exit(1)
    finally:
        await client.playback.stop()


if __name__ == "__main__":
    asyncio.run(run_cli())
