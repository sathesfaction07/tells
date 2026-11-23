import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ..sources.annotations import AnnotationSource
from ..sources.anomaly import AnomalySource
from ..sources.images import ImageSource
from .reasoning import LLMReasoner
from .scoring import Signal, classify_confidence, compute_confidence

logger = logging.getLogger("evasion_detect")


class EvasionAnalyzer:
    def __init__(
        self,
        chrome_port: int = 9222,
        analysis_days: int = 364,
        llm_reasoning: bool = False,
        aws_region: str = "us-east-1",
    ):
        self.chrome_port = chrome_port
        self.cutoff = datetime.now(timezone.utc) - timedelta(days=analysis_days)
        self.sources = [
            AnnotationSource(chrome_port=chrome_port),
            ImageSource(chrome_port=chrome_port),

            AnomalySource(chrome_port=chrome_port),
        ]
        self.reasoner = LLMReasoner(region=aws_region) if llm_reasoning else None

    async def analyze(self, product_id: str) -> dict:
        logger.info(f"Starting analysis for {product_id} (cutoff: {self.cutoff.date()})")

        tasks = [source.gather(product_id, self.cutoff) for source in self.sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        signals: list[Signal] = []
        for source, result in zip(self.sources, results):
            if isinstance(result, Exception):
                logger.warning(f"Source {source.name} failed: {result}")
                continue
            if result:
                signals.append(result)

        confidence = compute_confidence(signals)
        level = classify_confidence(confidence)

        llm_reasoning = None
        if self.reasoner and level == "MEDIUM":
            logger.info(f"MEDIUM confidence ({confidence:.1f}) — invoking LLM reasoning")
            llm_reasoning = self.reasoner.reason(product_id, signals, confidence)
            if llm_reasoning and llm_reasoning.get("verdict") == "EVASIVE":
                level = "HIGH"
            elif llm_reasoning and llm_reasoning.get("verdict") == "LEGITIMATE":
                level = "LOW"

        logger.info(f"Analysis complete: {confidence:.1f} ({level})")

        return {
            "product_id": product_id,
            "confidence": confidence,
            "level": level,
            "signals": [
                {"source": s.source, "score": s.raw_score, "count": s.count, "summary": s.summary}
                for s in signals
            ],
            "llm_reasoning": llm_reasoning,
            "analysis_window_days": (datetime.now(timezone.utc) - self.cutoff).days,
            "sources_queried": len(self.sources),
            "sources_responded": len(signals),
        }

    async def analyze_batch(self, product_ids: list[str]) -> list[dict]:
        results = []
        for pid in product_ids:
            result = await self.analyze(pid)
            results.append(result)
        results.sort(key=lambda r: r["confidence"], reverse=True)
        return results
