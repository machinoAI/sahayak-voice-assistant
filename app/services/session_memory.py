"""
In-memory conversational session memory manager for Sahayak Voice Assistant.
Maintains bounded rolling history per WebSocket connection and provides
zero-latency pronoun heuristic retrieval augmentation.
"""

from dataclasses import dataclass, field
from collections import deque
from typing import List, Optional
import time

PRONOUNS = {
    "it", "this", "that", "these", "those",
    "they", "them", "their", "theirs",
    "he", "him", "his", "she", "her", "hers",
    "its", "itself", "themselves",
}

QUESTION_STARTERS = {
    "who", "what", "where", "when", "why", "how", "which"
}

@dataclass
class TurnRecord:
    turn_id: str
    user_query: str
    assistant_response: str
    was_interrupted: bool = False
    timestamp: float = field(default_factory=time.time)


class SessionMemory:
    """Manages an active connection's rolling conversation memory."""

    def __init__(self, max_turns: int = 3) -> None:
        self.max_turns = max_turns
        self._history: deque[TurnRecord] = deque(maxlen=max_turns)

    def add_turn(
        self,
        turn_id: str,
        user_query: str,
        assistant_response: str,
        was_interrupted: bool = False,
    ) -> None:
        self._history.append(
            TurnRecord(
                turn_id=turn_id,
                user_query=user_query.strip(),
                assistant_response=assistant_response.strip(),
                was_interrupted=was_interrupted,
            )
        )

    def mark_last_interrupted(self, partial_response: str = "") -> None:
        """Flags the most recent turn as interrupted and optionally records partial output."""
        if self._history:
            self._history[-1].was_interrupted = True
            if partial_response:
                self._history[-1].assistant_response = partial_response.strip()

    def get_turns(self) -> List[TurnRecord]:
        return list(self._history)

    def get_last_turn(self) -> Optional[TurnRecord]:
        return self._history[-1] if self._history else None

    def get_augmented_query(self, current_query: str) -> str:
        """
        Subject-Augmented Retrieval Heuristic (Option 2):
        Detects if current_query is a follow-up containing pronouns or short clauses.
        If so, prepends the root query from the prior turn to ensure Qdrant vector retrieval
        matches the underlying entity.
        """
        query_text = current_query.strip()
        if not self._history:
            return query_text

        last_turn = self._history[-1]
        prior_query = last_turn.user_query.strip()
        if not prior_query:
            return query_text

        words = [w.lower().strip("?,.!") for w in query_text.split() if w.strip("?,.!")]
        if not words:
            return query_text

        is_follow_up = False

        # Condition 1: Contains pronouns referring to prior entities
        if any(w in PRONOUNS for w in words):
            is_follow_up = True

        # Condition 2: Short question (<= 4 words) starting with question word
        elif len(words) <= 4 and words[0] in QUESTION_STARTERS:
            is_follow_up = True

        # Condition 3: Very short follow-up clause (<= 3 words)
        elif len(words) <= 3:
            is_follow_up = True

        if is_follow_up:
            return f"{prior_query} {query_text}"

        return query_text

    def format_history_for_prompt(self) -> str:
        """Formats past dialogue turns into a compact conversational prompt block."""
        if not self._history:
            return ""

        lines = ["Conversation History:"]
        for turn in self._history:
            lines.append(f"User: {turn.user_query}")
            if turn.was_interrupted:
                lines.append(f"Assistant: {turn.assistant_response} [Interrupted]")
            else:
                lines.append(f"Assistant: {turn.assistant_response}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._history.clear()

    def __len__(self) -> int:
        return len(self._history)

    def __bool__(self) -> bool:
        return True
