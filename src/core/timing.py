"""Small, dependency-free timing records for conversational turns.

``total_ms`` is full turn elapsed time. It includes caller speech and
turn-detection silence, so it is not a perceived-response-latency metric.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
import json
import time
from typing import Any
from uuid import uuid4


class TurnTiming:
    """Collect ordered timing stages for one conversational turn."""

    def __init__(self, turn_id: str | None = None) -> None:
        self.turn_id = turn_id or str(uuid4())
        self._started_monotonic = time.monotonic()
        self._last_stage_end_monotonic = self._started_monotonic
        self._stages: list[dict[str, Any]] = []

    def stage(self, name: str) -> "_StageTiming":
        """Return a context manager that records one named stage.

        Example:
            with turn.stage("stt"):
                transcript = transcribe(audio)
        """
        return _StageTiming(self, name)

    def _start_stage(self, name: str) -> tuple[float, str, float]:
        started_monotonic = time.monotonic()
        return (
            started_monotonic,
            _iso_timestamp(),
            0.0
            if not self._stages
            else max(
                0.0, (started_monotonic - self._last_stage_end_monotonic) * 1000
            ),
        )

    def _finish_stage(
        self,
        name: str,
        started_monotonic: float,
        start_timestamp: str,
        gap_before_ms: float,
    ) -> None:
        ended_monotonic = time.monotonic()
        self._stages.append(
            {
                "name": name,
                "start_timestamp": start_timestamp,
                "end_timestamp": _iso_timestamp(),
                "duration_ms": round(
                    max(0.0, (ended_monotonic - started_monotonic) * 1000), 2
                ),
                "gap_before_ms": round(gap_before_ms, 2),
            }
        )
        self._last_stage_end_monotonic = ended_monotonic

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable timing record."""
        total_end = (
            self._last_stage_end_monotonic if self._stages else time.monotonic()
        )
        return {
            "turn_id": self.turn_id,
            "stages": list(self._stages),
            "total_ms": round(
                max(0.0, (total_end - self._started_monotonic) * 1000), 2
            ),
        }

    def to_json(self) -> str:
        """Serialize one conversational-turn timing record as JSON."""
        return json.dumps(self.to_dict())


class _StageTiming(AbstractContextManager[None]):
    """One active stage for ``TurnTiming``."""

    def __init__(self, turn: TurnTiming, name: str) -> None:
        self._turn = turn
        self._name = name
        self._started_monotonic: float | None = None
        self._start_timestamp: str | None = None
        self._gap_before_ms: float | None = None

    def __enter__(self) -> None:
        (
            self._started_monotonic,
            self._start_timestamp,
            self._gap_before_ms,
        ) = self._turn._start_stage(self._name)
        return None

    def __exit__(self, *exc_info: object) -> None:
        if self._started_monotonic is None or self._start_timestamp is None:
            return None
        self._turn._finish_stage(
            self._name,
            self._started_monotonic,
            self._start_timestamp,
            self._gap_before_ms or 0.0,
        )
        return None


def _iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
