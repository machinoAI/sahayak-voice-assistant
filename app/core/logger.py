"""
Structured Logging & Step Tracker for Sahayak Voice Assistant.
Provides millisecond-precision latency tracking and structured diagnostic logs.
"""

import time
import logging
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Ensure persistent log directory exists
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "sahayak.log"

# Configure standard root logger with both stdout and file persistence
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
)

logging.basicConfig(
    level=logging.INFO,
    handlers=[stream_handler, file_handler],
)

logger = logging.getLogger("sahayak")

class TurnTracker:
    """
    Tracks and logs the lifecycle of a voice turn across all pipeline stages with elapsed latency.
    """
    def __init__(self, turn_id: str):
        self.turn_id = turn_id
        self.start_time = time.perf_counter()
        self.last_step_time = self.start_time
        self.step_history: Dict[str, float] = {}

    def log_step(self, step_name: str, details: Optional[Dict[str, Any]] = None):
        now = time.perf_counter()
        step_duration_ms = (now - self.last_step_time) * 1000
        total_elapsed_ms = (now - self.start_time) * 1000
        self.step_history[step_name] = total_elapsed_ms
        self.last_step_time = now

        meta = details or {}
        meta_str = " | ".join(f"{k}={v}" for k, v in meta.items()) if meta else ""
        meta_suffix = f" | {meta_str}" if meta_str else ""

        # High-visibility structured log
        logger.info(
            f"⚡ [TURN {self.turn_id[:8]}] [{step_name:<26}] "
            f"+{step_duration_ms:6.1f}ms (total: {total_elapsed_ms:6.1f}ms){meta_suffix}"
        )

    def log_error(self, step_name: str, error: Exception, details: Optional[Dict[str, Any]] = None):
        now = time.perf_counter()
        total_elapsed_ms = (now - self.start_time) * 1000
        logger.error(
            f"❌ [TURN {self.turn_id[:8]}] [{step_name:<26}] FAILED at {total_elapsed_ms:6.1f}ms: {error} | details={details}"
        )
