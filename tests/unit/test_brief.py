from evasion_detect.core.brief import generate_brief


class TestBrief:
    def test_generates_markdown(self):
        result = {
            "product_id": "SKU-123",
            "confidence": 65.0,
            "level": "MEDIUM",
            "signals": [
                {
                    "source": "annotations",
                    "score": 75.0,
                    "count": 3,
                    "summary": "2x approval reversal",
                },
                {"source": "images", "score": 50.0, "count": 1, "summary": "1x full swap"},
            ],
            "llm_reasoning": {
                "verdict": "EVASIVE",
                "reasoning": "Two reversals within 30 days combined with image swap is consistent with bait-and-switch.",
                "alternative_explanation": "Could be a brand refresh, but timing aligns with approval dates.",
                "recommended_action": "Check if the merchant has multiple accounts with similar patterns.",
            },
            "analysis_window_days": 364,
            "sources_queried": 2,
            "sources_responded": 2,
        }
        brief = generate_brief(result)
        assert "SKU-123" in brief
        assert "MEDIUM" in brief
        assert "EVASIVE" in brief
        assert "bait-and-switch" in brief
        assert "approval reversal" in brief
        assert "full swap" in brief

    def test_writes_to_file(self, tmp_path):
        result = {
            "product_id": "SKU-456",
            "confidence": 80.0,
            "level": "HIGH",
            "signals": [{"source": "annotations", "score": 80, "count": 2, "summary": "test"}],
            "analysis_window_days": 364,
            "sources_queried": 2,
            "sources_responded": 1,
        }
        generate_brief(result, output_path=tmp_path)
        assert (tmp_path / "brief_SKU-456.md").exists()

    def test_handles_no_llm_reasoning(self):
        result = {
            "product_id": "SKU-789",
            "confidence": 30.0,
            "level": "LOW",
            "signals": [],
            "analysis_window_days": 90,
            "sources_queried": 2,
            "sources_responded": 0,
        }
        brief = generate_brief(result)
        assert "SKU-789" in brief
        assert "LOW" in brief
