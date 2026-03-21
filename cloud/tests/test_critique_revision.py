"""Tests for the critique/revision pipeline helpers in debate.py."""


from hivemind_core.debate import _create_revision_prompt, _parse_critique_response
from hivemind_core.types import Critique, TheoryUnitSolution

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_solution(**overrides) -> TheoryUnitSolution:
    defaults = dict(
        unit_id="u1",
        unit_name="Unit 1",
        solution="test solution",
        reasoning="test reasoning",
        knowledge_base_ids=[],
        retrieved_chunk_ids=[],
    )
    defaults.update(overrides)
    return TheoryUnitSolution(**defaults)


def _make_critique(**overrides) -> Critique:
    defaults = dict(
        source_unit_id="u2",
        target_unit_id="u1",
        critique_text="full critique text",
        strengths=["s1"],
        weaknesses=["w1"],
        suggestions=["sg1"],
    )
    defaults.update(overrides)
    return Critique(**defaults)


# ---------------------------------------------------------------------------
# _parse_critique_response
# ---------------------------------------------------------------------------

class TestParseCritiqueResponse:
    """Tests for _parse_critique_response."""

    def test_well_formed_text(self):
        """All three sections with bullet points are extracted correctly."""
        text = (
            "STRENGTHS:\n"
            "- Good structure\n"
            "- Clear reasoning\n"
            "\n"
            "WEAKNESSES:\n"
            "- Missing evidence\n"
            "- Too vague\n"
            "\n"
            "SUGGESTIONS:\n"
            "- Add citations\n"
            "- Be more specific\n"
        )
        strengths, weaknesses, suggestions = _parse_critique_response(text)

        assert strengths == ["Good structure", "Clear reasoning"]
        assert weaknesses == ["Missing evidence", "Too vague"]
        assert suggestions == ["Add citations", "Be more specific"]

    def test_empty_text(self):
        """Empty input returns three empty lists."""
        strengths, weaknesses, suggestions = _parse_critique_response("")

        assert strengths == []
        assert weaknesses == []
        assert suggestions == []

    def test_only_strengths_section(self):
        """When only STRENGTHS is present, weaknesses and suggestions are empty."""
        text = (
            "STRENGTHS:\n"
            "- Innovative approach\n"
            "- Well-supported claims\n"
        )
        strengths, weaknesses, suggestions = _parse_critique_response(text)

        assert strengths == ["Innovative approach", "Well-supported claims"]
        assert weaknesses == []
        assert suggestions == []


# ---------------------------------------------------------------------------
# _create_revision_prompt
# ---------------------------------------------------------------------------

class TestCreateRevisionPrompt:
    """Tests for _create_revision_prompt."""

    def test_revision_strength_zero(self):
        """revision_strength=0.0 produces '0%' in the output."""
        solution = _make_solution()
        critique = _make_critique()

        prompt = _create_revision_prompt(solution, [critique], revision_strength=0.0)

        assert "0%" in prompt

    def test_revision_strength_full(self):
        """revision_strength=1.0 produces '100%' in the output."""
        solution = _make_solution()
        critique = _make_critique()

        prompt = _create_revision_prompt(solution, [critique], revision_strength=1.0)

        assert "100%" in prompt

    def test_includes_all_critique_texts(self):
        """All critique texts from multiple critiques appear in the prompt."""
        solution = _make_solution()
        c1 = _make_critique(
            source_unit_id="u2",
            critique_text="first critique text",
        )
        c2 = _make_critique(
            source_unit_id="u3",
            critique_text="second critique text",
        )

        prompt = _create_revision_prompt(solution, [c1, c2])

        assert "first critique text" in prompt
        assert "second critique text" in prompt
        assert "CRITIQUE FROM UNIT u2" in prompt
        assert "CRITIQUE FROM UNIT u3" in prompt

    def test_includes_original_solution(self):
        """The original solution text appears in the prompt."""
        solution = _make_solution(
            solution="my unique solution content",
            reasoning="my unique reasoning content",
        )
        critique = _make_critique()

        prompt = _create_revision_prompt(solution, [critique])

        assert "my unique solution content" in prompt
        assert "my unique reasoning content" in prompt
