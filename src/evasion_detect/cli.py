import asyncio
import csv
import json
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .core.analyzer import EvasionAnalyzer
from .core.brief import generate_brief

console = Console()


@click.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--chrome-port", default=9222, help="Chrome remote debugging port")
@click.option("--days", default=364, help="Analysis window in days")
@click.option(
    "--output",
    "output_dir",
    default=None,
    type=click.Path(),
    help="Output directory for results and briefs",
)
@click.option(
    "--llm/--no-llm",
    "llm_reasoning",
    default=False,
    help="Use LLM to reason about MEDIUM-confidence cases",
)
@click.option(
    "--brief/--no-brief", default=False, help="Generate markdown investigation brief per product"
)
@click.option("--verbose", is_flag=True)
def main(
    input_path: str,
    chrome_port: int,
    days: int,
    output_dir: str | None,
    llm_reasoning: bool,
    brief: bool,
    verbose: bool,
):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    product_ids = _load_input(Path(input_path))
    if not product_ids:
        console.print("[red]No product IDs found in input[/red]")
        return

    results = asyncio.run(_run(product_ids, chrome_port, days, llm_reasoning))

    _print_summary(results)

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        console.print(f"\n[dim]Results: {out / 'results.json'}[/dim]")

        if brief:
            for r in results:
                generate_brief(r, out / "briefs")
            console.print(f"[dim]Briefs: {out / 'briefs/'}[/dim]")


async def _run(
    product_ids: list[str], chrome_port: int, days: int, llm_reasoning: bool
) -> list[dict]:
    analyzer = EvasionAnalyzer(
        chrome_port=chrome_port, analysis_days=days, llm_reasoning=llm_reasoning
    )
    return await analyzer.analyze_batch(product_ids)


def _load_input(path: Path) -> list[str]:
    if path.suffix == ".csv":
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [
                row.get("product_id") or row.get("id") or row.get("sku")
                for row in reader
                if any(row.values())
            ]

    text = path.read_text(encoding="utf-8").strip()
    if "\n" in text:
        return [line.strip() for line in text.splitlines() if line.strip()]
    return [text]


def _print_summary(results: list[dict]) -> None:
    table = Table(title="Evasion Analysis Results")
    table.add_column("Product", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("Level")
    table.add_column("Signals")
    table.add_column("LLM", style="dim")

    for r in results:
        level_style = {"HIGH": "bold red", "MEDIUM": "yellow", "LOW": "green"}.get(r["level"], "")
        signal_summary = ", ".join(f"{s['source']}:{s['score']:.0f}" for s in r.get("signals", []))
        llm_verdict = (
            r.get("llm_reasoning", {}).get("verdict", "-") if r.get("llm_reasoning") else "-"
        )
        table.add_row(
            r["product_id"],
            f"{r['confidence']:.1f}",
            f"[{level_style}]{r['level']}[/{level_style}]",
            signal_summary,
            llm_verdict,
        )

    console.print(table)

    high = sum(1 for r in results if r["level"] == "HIGH")
    med = sum(1 for r in results if r["level"] == "MEDIUM")
    console.print(
        f"\n[bold]{len(results)} analyzed[/bold] — [red]{high} HIGH[/red], [yellow]{med} MEDIUM[/yellow], [green]{len(results) - high - med} LOW[/green]"
    )


if __name__ == "__main__":
    main()
