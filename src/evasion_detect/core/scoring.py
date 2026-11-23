from dataclasses import dataclass

# compute_confidence() divides by the sum of the weights of the signals actually PRESENT,
# so these are self-normalizing and need not total 1.0. That is why adding "anomaly" does not
# require touching the other two: the annotations:images ratio stays exactly as it was.
WEIGHTS = {
    "annotations": 0.60,
    "images": 0.40,
    "anomaly": 0.20,
}

THRESHOLDS = {
    "high": 70,
    "medium": 40,
    "low": 0,
}


@dataclass
class Signal:
    source: str
    raw_score: float  # 0-100
    count: int
    summary: str


def compute_confidence(signals: list[Signal]) -> float:
    if not signals:
        return 0.0

    weighted_sum = 0.0
    total_weight = 0.0

    for signal in signals:
        weight = WEIGHTS.get(signal.source, 0.0)
        weighted_sum += signal.raw_score * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return min(100.0, weighted_sum / total_weight)


def classify_confidence(score: float) -> str:
    if score >= THRESHOLDS["high"]:
        return "HIGH"
    elif score >= THRESHOLDS["medium"]:
        return "MEDIUM"
    return "LOW"


def format_verdict(score: float) -> str:
    level = classify_confidence(score)
    if level == "HIGH":
        return "[bold red]EVASIVE — recommend investigation[/bold red]"
    elif level == "MEDIUM":
        return "[yellow]SUSPICIOUS — review recommended[/yellow]"
    return "[green]LOW RISK — no action needed[/green]"
