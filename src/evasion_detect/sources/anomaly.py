import logging
from datetime import datetime
from statistics import median

import httpx

from ..core.scoring import Signal

logger = logging.getLogger("evasion_detect")


class AnomalySource:
    name = "anomaly"

    def __init__(self, chrome_port: int = 9222, api_base: str = "http://localhost:8003"):
        self.api_base = api_base
        self.timeout = httpx.Timeout(15.0)

    async def gather(self, product_id: str, cutoff: datetime) -> Signal | None:
        history = await self._fetch_event_history(product_id, cutoff)
        if not history:
            return Signal(source=self.name, raw_score=0, count=0, summary="No historical data")

        score, summary = self._compute_anomaly_score(history)
        return Signal(source=self.name, raw_score=score, count=len(history), summary=summary)

    async def _fetch_event_history(self, product_id: str, cutoff: datetime) -> list[dict]:
        url = f"{self.api_base}/events/{product_id}/history"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params={"since": cutoff.isoformat()})
                resp.raise_for_status()
                return resp.json().get("history", [])
        except Exception as e:
            logger.warning(f"Event history fetch failed for {product_id}: {e}")
            return []

    def _compute_anomaly_score(self, history: list[dict]) -> tuple[float, str]:
        """Compute anomaly score using Median Absolute Deviation (MAD).

        MAD is chosen over z-score because it is:
        - Robust to outliers in the baseline
        - Suitable for small sample sizes
        - Available via stdlib statistics module
        - More appropriate for non-normal distributions common in event data

        Returns (score, summary) where score is 0-100.
        """
        if len(history) < 3:
            return (0.0, "Insufficient baseline (need 3+ periods)")

        counts = [h.get("count", 0) for h in history]
        current = counts[-1]
        baseline = counts[:-1]

        # Handle zero-variance case (all baseline values identical)
        if len(set(baseline)) == 1:
            if current == baseline[0]:
                return (0.0, "No deviation from baseline")
            else:
                # Current differs from a flat baseline - treat as anomalous
                deviation_pct = abs(current - baseline[0]) / max(baseline[0], 1) * 100
                score = min(100.0, deviation_pct)
                return (score, f"Spike from flat baseline ({baseline[0]} → {current})")

        # Compute MAD
        baseline_median = median(baseline)
        absolute_deviations = [abs(x - baseline_median) for x in baseline]
        mad = median(absolute_deviations)

        # Avoid division by zero when MAD is zero
        if mad == 0:
            # All baseline points equal median but there's variance
            # (shouldn't happen, but defensive)
            deviation = abs(current - baseline_median)
            score = min(100.0, deviation * 10)
            return (
                score,
                f"Current: {current}, baseline median: {baseline_median:.0f}",
            )

        # Modified z-score = 0.6745 * (x - median) / MAD
        # Using constant approximation for normal distribution
        modified_z = 0.6745 * abs(current - baseline_median) / mad

        # Map modified z-score to 0-100 scale
        # Values > 3.5 are commonly considered anomalies (very significant)
        score = min(100.0, (modified_z / 3.5) * 100)

        if modified_z > 3.5:
            summary = f"Significant spike ({current} vs baseline ~{baseline_median:.0f})"
        elif modified_z > 2.0:
            summary = f"Moderate deviation ({current} vs baseline ~{baseline_median:.0f})"
        else:
            summary = f"Normal variance (current: {current}, baseline: ~{baseline_median:.0f})"

        return (score, summary)
