from evasion_detect.core.scoring import Signal, classify_confidence, compute_confidence


class TestComputeConfidence:
    def test_both_signals_high(self):
        signals = [
            Signal(source="annotations", raw_score=80, count=3, summary=""),
            Signal(source="images", raw_score=90, count=2, summary=""),
        ]
        score = compute_confidence(signals)
        # 80*0.6 + 90*0.4 = 48 + 36 = 84; 84/(0.6+0.4) = 84.0
        assert score == 84.0

    def test_annotations_only(self):
        signals = [Signal(source="annotations", raw_score=100, count=5, summary="")]
        score = compute_confidence(signals)
        # 100*0.6 / 0.6 = 100
        assert score == 100.0

    def test_images_only(self):
        signals = [Signal(source="images", raw_score=50, count=1, summary="")]
        score = compute_confidence(signals)
        # 50*0.4 / 0.4 = 50
        assert score == 50.0

    def test_empty_signals(self):
        assert compute_confidence([]) == 0.0

    def test_capped_at_100(self):
        signals = [
            Signal(source="annotations", raw_score=100, count=10, summary=""),
            Signal(source="images", raw_score=100, count=10, summary=""),
        ]
        assert compute_confidence(signals) <= 100.0

    def test_zero_scores(self):
        signals = [
            Signal(source="annotations", raw_score=0, count=0, summary=""),
            Signal(source="images", raw_score=0, count=0, summary=""),
        ]
        assert compute_confidence(signals) == 0.0


class TestClassifyConfidence:
    def test_high(self):
        assert classify_confidence(70) == "HIGH"
        assert classify_confidence(95) == "HIGH"

    def test_medium(self):
        assert classify_confidence(40) == "MEDIUM"
        assert classify_confidence(69.9) == "MEDIUM"

    def test_low(self):
        assert classify_confidence(0) == "LOW"
        assert classify_confidence(39.9) == "LOW"
