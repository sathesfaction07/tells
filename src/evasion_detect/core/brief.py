import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("evasion_detect")


def generate_brief(result: dict, output_path: Path | None = None) -> str:
    product_id = result["product_id"]
    confidence = result["confidence"]
    level = result["level"]
    signals = result.get("signals", [])
    reasoning = result.get("llm_reasoning", {})

    lines = [
        f"# Investigation Brief: {product_id}",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"## Verdict: {level} ({confidence:.1f}/100)",
        "",
    ]

    if reasoning:
        lines.append(f"**LLM Assessment:** {reasoning.get('verdict', 'N/A')}")
        lines.append(f"> {reasoning.get('reasoning', '')}")
        if reasoning.get("alternative_explanation"):
            lines.append("")
            lines.append(f"**Alternative explanation:** {reasoning['alternative_explanation']}")
        if reasoning.get("recommended_action"):
            lines.append("")
            lines.append(f"**Recommended action:** {reasoning['recommended_action']}")
        lines.append("")

    lines.append("## Signal Breakdown")
    lines.append("")
    for signal in signals:
        lines.append(
            f"### {signal['source'].title()} (score: {signal['score']:.0f}/100, events: {signal['count']})"
        )
        lines.append(f"{signal['summary']}")
        lines.append("")

    lines.append("## Metadata")
    lines.append(f"- Analysis window: {result.get('analysis_window_days', 364)} days")
    lines.append(f"- Sources queried: {result.get('sources_queried', 0)}")
    lines.append(f"- Sources responded: {result.get('sources_responded', 0)}")

    brief = "\n".join(lines)

    if output_path:
        output_path.mkdir(parents=True, exist_ok=True)
        file_path = output_path / f"brief_{product_id}.md"
        file_path.write_text(brief)
        logger.info(f"Brief written to {file_path}")

    return brief
