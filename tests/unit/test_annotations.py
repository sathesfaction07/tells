from evasion_detect.sources.annotations import AnnotationSource


class TestAnnotationPatterns:
    def setup_method(self):
        self.source = AnnotationSource()

    def test_detects_approval_reversal(self):
        transitions = [
            {"from_status": "approved", "to_status": "restricted", "date": "2025-01-15"},
        ]
        suspicious = self.source._find_suspicious_transitions(transitions)
        assert len(suspicious) == 1
        assert suspicious[0]["pattern"] == "approval_reversal"

    def test_detects_restriction_override(self):
        transitions = [
            {"from_status": "restricted", "to_status": "approved", "date": "2025-02-01"},
        ]
        suspicious = self.source._find_suspicious_transitions(transitions)
        assert len(suspicious) == 1
        assert suspicious[0]["pattern"] == "restriction_override"

    def test_detects_team_conflict(self):
        transitions = [
            {"from_status": "approved", "to_status": "approved", "conflict": True},
        ]
        suspicious = self.source._find_suspicious_transitions(transitions)
        assert len(suspicious) == 1
        assert suspicious[0]["pattern"] == "team_conflict"

    def test_ignores_normal_transitions(self):
        transitions = [
            {"from_status": "pending", "to_status": "approved"},
            {"from_status": "pending", "to_status": "restricted"},
        ]
        suspicious = self.source._find_suspicious_transitions(transitions)
        assert suspicious == []

    def test_score_scales_with_count(self):
        few = [{"pattern": "approval_reversal"}]
        many = [{"pattern": "approval_reversal"}] * 5

        score_few = self.source._score_transitions(few, total=10)
        score_many = self.source._score_transitions(many, total=10)
        assert score_many > score_few

    def test_reversals_weighted_higher_than_overrides(self):
        reversals = [{"pattern": "approval_reversal"}] * 2
        overrides = [{"pattern": "restriction_override"}] * 2

        score_rev = self.source._score_transitions(reversals, total=5)
        score_ovr = self.source._score_transitions(overrides, total=5)
        assert score_rev > score_ovr

    def test_score_capped_at_100(self):
        many = [{"pattern": "approval_reversal"}] * 20
        score = self.source._score_transitions(many, total=20)
        assert score <= 100.0

    def test_summary_format(self):
        suspicious = [
            {"pattern": "approval_reversal"},
            {"pattern": "approval_reversal"},
            {"pattern": "team_conflict"},
        ]
        summary = self.source._build_summary(suspicious)
        assert "2x approval reversal" in summary
        assert "1x team conflict" in summary
