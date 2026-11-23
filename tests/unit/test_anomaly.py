from evasion_detect.sources.anomaly import AnomalySource


class TestAnomalyDetection:
    def setup_method(self):
        self.source = AnomalySource()

    def test_flat_series_scores_low(self):
        history = [
            {"count": 10},
            {"count": 10},
            {"count": 10},
            {"count": 10},
        ]
        score, summary = self.source._compute_anomaly_score(history)
        assert score == 0.0
        assert "No deviation from baseline" in summary

    def test_clear_spike_scores_high(self):
        history = [
            {"count": 10},
            {"count": 12},
            {"count": 11},
            {"count": 50},  # Clear spike
        ]
        score, summary = self.source._compute_anomaly_score(history)
        assert score > 70.0
        assert "Significant spike" in summary or "spike" in summary.lower()

    def test_insufficient_history_handled_gracefully(self):
        # Less than 3 periods
        history = [{"count": 10}, {"count": 12}]
        score, summary = self.source._compute_anomaly_score(history)
        assert score == 0.0
        assert "Insufficient baseline" in summary

    def test_empty_history_handled_gracefully(self):
        history = []
        score, summary = self.source._compute_anomaly_score(history)
        assert score == 0.0
        assert "Insufficient baseline" in summary

    def test_zero_variance_baseline_no_division_by_zero(self):
        # All baseline values identical - should not crash
        history = [
            {"count": 5},
            {"count": 5},
            {"count": 5},
            {"count": 5},
        ]
        score, summary = self.source._compute_anomaly_score(history)
        assert score == 0.0
        assert "No deviation" in summary

    def test_zero_variance_with_different_current(self):
        # Flat baseline but current differs
        history = [
            {"count": 10},
            {"count": 10},
            {"count": 10},
            {"count": 20},
        ]
        score, summary = self.source._compute_anomaly_score(history)
        assert score > 0.0
        assert "flat baseline" in summary.lower()

    def test_moderate_deviation_scores_medium(self):
        history = [
            {"count": 10},
            {"count": 12},
            {"count": 11},
            {"count": 20},
        ]
        score, summary = self.source._compute_anomaly_score(history)
        # With MAD method, this is actually a very significant deviation (modified z > 3.5)
        assert score >= 80.0
        assert "spike" in summary.lower()

    def test_normal_variance_scores_low(self):
        history = [
            {"count": 10},
            {"count": 12},
            {"count": 11},
            {"count": 13},
        ]
        score, summary = self.source._compute_anomaly_score(history)
        # Modified z around 1.3, which maps to ~38 on our scale
        assert score < 50.0

    def test_handles_missing_count_field(self):
        history = [
            {"count": 10},
            {},  # Missing count
            {"count": 12},
            {"count": 11},
        ]
        score, summary = self.source._compute_anomaly_score(history)
        # Should not crash, treats missing as 0
        assert score >= 0.0

    def test_downward_spike_detected(self):
        history = [
            {"count": 50},
            {"count": 48},
            {"count": 51},
            {"count": 10},  # Sudden drop
        ]
        score, summary = self.source._compute_anomaly_score(history)
        assert score > 50.0

    def test_score_capped_at_100(self):
        history = [
            {"count": 5},
            {"count": 6},
            {"count": 5},
            {"count": 1000},  # Extreme spike
        ]
        score, summary = self.source._compute_anomaly_score(history)
        assert score <= 100.0

    def test_larger_baseline_more_robust(self):
        # Larger baseline should provide more stable detection
        history = [
            {"count": 10},
            {"count": 12},
            {"count": 11},
            {"count": 13},
            {"count": 10},
            {"count": 11},
            {"count": 12},
            {"count": 50},
        ]
        score, summary = self.source._compute_anomaly_score(history)
        assert score > 60.0
