from evasion_detect.core.reasoning import LLMReasoner
from evasion_detect.core.scoring import Signal


class TestLLMReasoner:
    def test_parse_valid_json(self):
        reasoner = LLMReasoner.__new__(LLMReasoner)
        result = reasoner._parse('{"verdict": "EVASIVE", "reasoning": "clear pattern"}')
        assert result["verdict"] == "EVASIVE"

    def test_parse_json_in_prose(self):
        reasoner = LLMReasoner.__new__(LLMReasoner)
        result = reasoner._parse(
            'Here is my analysis:\n{"verdict": "LEGITIMATE", "reasoning": "normal"}\nEnd.'
        )
        assert result["verdict"] == "LEGITIMATE"

    def test_parse_malformed_returns_empty(self):
        reasoner = LLMReasoner.__new__(LLMReasoner)
        result = reasoner._parse("completely broken response")
        assert result == {}

    def test_build_prompt_includes_signals(self):
        reasoner = LLMReasoner.__new__(LLMReasoner)
        signals = [
            Signal(source="annotations", raw_score=75, count=3, summary="2x reversal"),
            Signal(source="images", raw_score=50, count=1, summary="1x swap"),
        ]
        prompt = reasoner._build_prompt("SKU-123", signals, 65.0)
        assert "SKU-123" in prompt
        assert "65.0" in prompt
        assert "ANNOTATIONS" in prompt
        assert "2x reversal" in prompt
        assert "IMAGES" in prompt
