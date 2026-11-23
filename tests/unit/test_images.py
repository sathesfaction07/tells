from evasion_detect.sources.images import ImageSource


class TestImagePatterns:
    def setup_method(self):
        self.source = ImageSource()

    def test_detects_full_swap(self):
        changes = [{"type": "replaced", "similarity": 0.1, "slot": 1}]
        suspicious = self.source._find_suspicious_changes(changes)
        assert len(suspicious) == 1
        assert suspicious[0]["pattern"] == "full_swap"

    def test_detects_post_approval_add(self):
        changes = [{"type": "added", "post_approval": True, "slot": 3}]
        suspicious = self.source._find_suspicious_changes(changes)
        assert len(suspicious) == 1
        assert suspicious[0]["pattern"] == "post_approval_add"

    def test_detects_primary_swap(self):
        changes = [{"type": "replaced", "similarity": 0.5, "slot": 0}]
        suspicious = self.source._find_suspicious_changes(changes)
        assert len(suspicious) == 1
        assert suspicious[0]["pattern"] == "primary_swap"

    def test_ignores_minor_replacement(self):
        changes = [{"type": "replaced", "similarity": 0.85, "slot": 2}]
        suspicious = self.source._find_suspicious_changes(changes)
        assert suspicious == []

    def test_ignores_normal_add(self):
        changes = [{"type": "added", "post_approval": False, "slot": 4}]
        suspicious = self.source._find_suspicious_changes(changes)
        assert suspicious == []

    def test_score_full_swap_highest(self):
        full_swap = [{"pattern": "full_swap"}]
        post_add = [{"pattern": "post_approval_add"}]
        primary = [{"pattern": "primary_swap"}]

        assert self.source._score_changes(full_swap) > self.source._score_changes(post_add)
        assert self.source._score_changes(post_add) > self.source._score_changes(primary)

    def test_score_accumulates(self):
        multiple = [{"pattern": "full_swap"}, {"pattern": "primary_swap"}]
        score = self.source._score_changes(multiple)
        assert score == 50.0  # 30 + 20

    def test_score_capped_at_100(self):
        many = [{"pattern": "full_swap"}] * 10
        assert self.source._score_changes(many) == 100.0
