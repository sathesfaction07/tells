import logging
from datetime import datetime

import httpx

from ..core.scoring import Signal

logger = logging.getLogger("evasion_detect")


class ImageSource:
    name = "images"

    def __init__(self, chrome_port: int = 9222, api_base: str = "http://localhost:8002"):
        self.api_base = api_base
        self.timeout = httpx.Timeout(15.0)

    async def gather(self, product_id: str, cutoff: datetime) -> Signal | None:
        changes = await self._fetch_image_changes(product_id, cutoff)
        if not changes:
            return Signal(source=self.name, raw_score=0, count=0, summary="No image changes")

        suspicious = self._find_suspicious_changes(changes)
        if not suspicious:
            return Signal(
                source=self.name, raw_score=0, count=0, summary="No suspicious image swaps"
            )

        score = self._score_changes(suspicious)
        summary = self._build_summary(suspicious)

        return Signal(source=self.name, raw_score=score, count=len(suspicious), summary=summary)

    async def _fetch_image_changes(self, product_id: str, cutoff: datetime) -> list[dict]:
        url = f"{self.api_base}/images/{product_id}/changes"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params={"since": cutoff.isoformat()})
                resp.raise_for_status()
                return resp.json().get("changes", [])
        except Exception as e:
            logger.warning(f"Image change fetch failed for {product_id}: {e}")
            return []

    def _find_suspicious_changes(self, changes: list[dict]) -> list[dict]:
        suspicious = []
        for change in changes:
            # Complete image swap (different image, same slot)
            if change.get("type") == "replaced" and change.get("similarity", 1.0) < 0.3:
                suspicious.append({**change, "pattern": "full_swap"})
            # Image added shortly after approval
            elif change.get("type") == "added" and change.get("post_approval"):
                suspicious.append({**change, "pattern": "post_approval_add"})
            # Primary image changed (slot 0)
            elif change.get("type") == "replaced" and change.get("slot") == 0:
                suspicious.append({**change, "pattern": "primary_swap"})

        return suspicious

    def _score_changes(self, suspicious: list[dict]) -> float:
        score = 0.0
        for s in suspicious:
            if s["pattern"] == "full_swap":
                score += 30
            elif s["pattern"] == "post_approval_add":
                score += 25
            elif s["pattern"] == "primary_swap":
                score += 20
        return min(100.0, score)

    def _build_summary(self, suspicious: list[dict]) -> str:
        patterns = {}
        for s in suspicious:
            p = s["pattern"]
            patterns[p] = patterns.get(p, 0) + 1
        parts = [f"{count}x {pattern.replace('_', ' ')}" for pattern, count in patterns.items()]
        return ", ".join(parts)
