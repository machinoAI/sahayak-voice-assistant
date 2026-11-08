"""
Unit tests for connection-scoped SessionMemory and retrieval heuristic.
"""

from app.services.session_memory import SessionMemory, TurnRecord

def test_session_memory_fifo_eviction():
    """Verify that session memory strictly bounds history to max_turns."""
    memory = SessionMemory(max_turns=3)
    assert len(memory) == 0

    memory.add_turn("t1", "What is PM Kisan?", "PM Kisan gives 6000 rupees.")
    memory.add_turn("t2", "Who is eligible?", "Small and marginal farmers.")
    memory.add_turn("t3", "When is it paid?", "In three installments.")
    assert len(memory) == 3

    # Adding a 4th turn should evict t1
    memory.add_turn("t4", "How to apply?", "Apply on pmkisan.gov.in.")
    assert len(memory) == 3
    turns = memory.get_turns()
    turn_ids = [t.turn_id for t in turns]
    assert "t1" not in turn_ids
    assert turn_ids == ["t2", "t3", "t4"]

def test_pronoun_heuristic_query_augmentation():
    """Verify that pronouns and short follow-ups are augmented with prior topic."""
    memory = SessionMemory(max_turns=3)
    memory.add_turn("t1", "What is Ayushman Bharat?", "It is a health insurance scheme.")

    # 1. Query with pronoun "it" -> Augmented
    q1 = memory.get_augmented_query("Who is eligible for it?")
    assert q1 == "What is Ayushman Bharat? Who is eligible for it?"

    # 2. Query with pronoun "this" -> Augmented
    q2 = memory.get_augmented_query("What is the coverage in this?")
    assert q2 == "What is Ayushman Bharat? What is the coverage in this?"

    # 3. Short question clause (<= 4 words starting with question word) -> Augmented
    q3 = memory.get_augmented_query("How much?")
    assert q3 == "What is Ayushman Bharat? How much?"

    # 4. Brand new self-contained query -> NOT augmented
    q4 = memory.get_augmented_query("What is the capital of India?")
    assert q4 == "What is the capital of India?"

def test_prompt_history_formatting():
    """Verify that dialogue turns are correctly formatted for LLM system prompt."""
    memory = SessionMemory(max_turns=3)
    memory.add_turn("t1", "Hello Sahayak", "Namaste! How can I help you today?")
    memory.add_turn("t2", "Tell me a scheme", "PM Kisan is popular", was_interrupted=True)

    formatted = memory.format_history_for_prompt()
    assert "Conversation History:" in formatted
    assert "User: Hello Sahayak" in formatted
    assert "Assistant: Namaste! How can I help you today?" in formatted
    assert "Assistant: PM Kisan is popular [Interrupted]" in formatted

def test_session_memory_clear():
    """Verify session reset empties the conversation buffer."""
    memory = SessionMemory(max_turns=3)
    memory.add_turn("t1", "User question", "Assistant response")
    assert len(memory) == 1

    memory.clear()
    assert len(memory) == 0
    assert memory.format_history_for_prompt() == ""
