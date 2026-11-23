import json
import logging

import boto3

from .scoring import Signal

logger = logging.getLogger("evasion_detect")

SYSTEM_PROMPT = """You analyze evidence of potentially evasive merchant behavior on an e-commerce platform. You receive signals from multiple data sources and determine whether the pattern indicates intentional manipulation or has a legitimate explanation.

Rules:
1. Be specific. Cite the exact signals that support your conclusion.
2. Consider legitimate explanations: seasonal relisting, brand refresh, honest mistakes.
3. If evidence is mixed, say so explicitly. Don't force a conclusion.
4. Output valid JSON only."""

RESPONSE_SCHEMA = """
Respond with:
{
    "verdict": "EVASIVE" | "LEGITIMATE" | "INCONCLUSIVE",
    "reasoning": "<2-3 sentences explaining your conclusion>",
    "key_evidence": ["<most compelling signal 1>", "<signal 2>"],
    "alternative_explanation": "<most plausible innocent explanation, or null>",
    "recommended_action": "<what a human investigator should do next>"
}"""


class LLMReasoner:
    def __init__(
        self, region: str = "us-east-1", model: str = "us.anthropic.claude-sonnet-4-6-20250514-v1:0"
    ):
        self.client = boto3.client("bedrock-runtime", region_name=region)
        self.model = model

    def reason(self, product_id: str, signals: list[Signal], confidence: float) -> dict | None:
        if not signals:
            return None

        prompt = self._build_prompt(product_id, signals, confidence)

        try:
            response = self.client.invoke_model(
                modelId=self.model,
                body=json.dumps(
                    {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 500,
                        "temperature": 0,
                        "system": SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": prompt + RESPONSE_SCHEMA}],
                    }
                ),
                contentType="application/json",
            )
            body = json.loads(response["body"].read())
            text = body["content"][0]["text"]
            return self._parse(text)
        except Exception as e:
            logger.warning(f"LLM reasoning failed: {e}")
            return None

    def _build_prompt(self, product_id: str, signals: list[Signal], confidence: float) -> str:
        parts = [
            f"Product: {product_id}",
            f"Overall confidence score: {confidence:.1f}/100",
            "",
            "EVIDENCE:",
        ]
        for signal in signals:
            parts.append(
                f"\n[{signal.source.upper()}] Score: {signal.raw_score:.0f}/100, Events: {signal.count}"
            )
            parts.append(f"  Summary: {signal.summary}")

        parts.append("\nIs this pattern evasive behavior or is there a legitimate explanation?")
        return "\n".join(parts)

    def _parse(self, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            import re

            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return {}
