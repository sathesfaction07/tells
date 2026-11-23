import logging
from datetime import datetime

import httpx

from ..core.scoring import Signal

logger = logging.getLogger("evasion_detect")


class AnnotationSource:
    name = "annotations"

    def __init__(self, chrome_port: int = 9222, api_base: str = "http://localhost:8001"):
        self.api_base = api_base
        self.timeout = httpx.Timeout(15.0)

    async def gather(self, product_id: str, cutoff: datetime) -> Signal | None:
        transitions = await self._fetch_transitions(product_id, cutoff)
        if not transitions:
            return Signal(source=self.name, raw_score=0, count=0, summary="No annotation history")

        suspicious = self._find_suspicious_transitions(transitions)
        if not suspicious:
            return Signal(
                source=self.name, raw_score=0, count=0, summary="No suspicious transitions"
            )

        score = self._score_transitions(suspicious, len(transitions))
        summary = self._build_summary(suspicious)

        return Signal(source=self.name, raw_score=score, count=len(suspicious), summary=summary)

    async def _fetch_transitions(self, product_id: str, cutoff: datetime) -> list[dict]:
        url = f"{self.api_base}/annotations/{product_id}/history"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params={"since": cutoff.isoformat()})
                resp.raise_for_status()
                return resp.json().get("transitions", [])
        except Exception as e:
            logger.warning(f"Annotation fetch failed for {product_id}: {e}")
            return []

    def _find_suspicious_transitions(self, transitions: list[dict]) -> list[dict]:
        suspicious = []
        for t in transitions:
            from_status = t.get("from_status", "")
            to_status = t.get("to_status", "")

            # Approved → Restricted within a short window = potential gaming
            if from_status == "approved" and to_status == "restricted":
                suspicious.append({**t, "pattern": "approval_reversal"})
            # Restricted → Approved repeatedly = potential re-submission gaming
            elif from_status == "restricted" and to_status == "approved":
                suspicious.append({**t, "pattern": "restriction_override"})
            # Multiple team conflicts (team A says yes, team B says no)
            elif t.get("conflict"):
                suspicious.append({**t, "pattern": "team_conflict"})

        return suspicious

    def _score_transitions(self, suspicious: list[dict], total: int) -> float:
        if total == 0:
            return 0.0

        base_score = min(100.0, (len(suspicious) / max(total, 1)) * 200)

        reversal_count = sum(1 for s in suspicious if s["pattern"] == "approval_reversal")
        conflict_count = sum(1 for s in suspicious if s["pattern"] == "team_conflict")

        # Reversals are stronger signals than overrides
        base_score += reversal_count * 15
        base_score += conflict_count * 10

        return min(100.0, base_score)

    def _build_summary(self, suspicious: list[dict]) -> str:
        patterns = {}
        for s in suspicious:
            p = s["pattern"]
            patterns[p] = patterns.get(p, 0) + 1
        parts = [f"{count}x {pattern.replace('_', ' ')}" for pattern, count in patterns.items()]
        return ", ".join(parts)
