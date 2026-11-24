"""The `tells` command end to end, with only the analyzer replaced.

The analyzer drives a live Chrome session over CDP; everything else here is real: input
parsing (CSV with any of three id columns, one-per-line text, a single id), the summary
table, results.json and the per-product investigation briefs.
"""

import json

from click.testing import CliRunner

from evasion_detect import cli


def _result(pid, level, confidence, llm=None):
    return {
        "product_id": pid,
        "confidence": confidence,
        "level": level,
        "signals": [
            {"source": "annotations", "score": confidence, "count": 2,
             "summary": "2x approval reversal"},
        ],
        "llm_reasoning": llm,
        "analysis_window_days": 364,
        "sources_queried": 2,
        "sources_responded": 2,
    }


class StandInAnalyzer:
    seen: dict = {}

    def __init__(self, chrome_port, analysis_days, llm_reasoning):
        StandInAnalyzer.seen = {"port": chrome_port, "days": analysis_days, "llm": llm_reasoning}

    async def analyze_batch(self, product_ids):
        StandInAnalyzer.seen["ids"] = list(product_ids)
        levels = ["HIGH", "MEDIUM", "LOW"]
        return [
            _result(pid, levels[i % 3], 90.0 - 30 * (i % 3),
                    llm={"verdict": "EVASIVE"} if i % 3 == 1 else None)
            for i, pid in enumerate(product_ids)
        ]


def invoke(monkeypatch, *args):
    monkeypatch.setattr(cli, "EvasionAnalyzer", StandInAnalyzer)
    return CliRunner().invoke(cli.main, [str(a) for a in args])


def test_csv_input_accepts_any_of_three_id_columns(monkeypatch, tmp_path):
    for column in ("product_id", "id", "sku"):
        path = tmp_path / f"{column}.csv"
        path.write_text(f"{column},note\nSKU-1,a\nSKU-2,b\n,\n", encoding="utf-8")
        result = invoke(monkeypatch, path)
        assert result.exit_code == 0, result.output
        assert StandInAnalyzer.seen["ids"] == ["SKU-1", "SKU-2"]  # blank row skipped


def test_text_input_one_id_per_line_or_a_single_id(monkeypatch, tmp_path):
    many = tmp_path / "ids.txt"
    many.write_text("SKU-1\n\nSKU-2\n", encoding="utf-8")
    invoke(monkeypatch, many)
    assert StandInAnalyzer.seen["ids"] == ["SKU-1", "SKU-2"]

    one = tmp_path / "one.txt"
    one.write_text("SKU-9\n", encoding="utf-8")
    invoke(monkeypatch, one)
    assert StandInAnalyzer.seen["ids"] == ["SKU-9"]


def test_an_empty_input_stops_before_any_analysis(monkeypatch, tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("product_id\n", encoding="utf-8")
    StandInAnalyzer.seen = {}
    result = invoke(monkeypatch, empty)
    assert "No product IDs found" in result.output
    assert StandInAnalyzer.seen == {}


def test_options_reach_the_analyzer(monkeypatch, tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("SKU-1", encoding="utf-8")
    invoke(monkeypatch, path, "--chrome-port", 9333, "--days", 30, "--llm", "--verbose")
    assert StandInAnalyzer.seen["port"] == 9333
    assert StandInAnalyzer.seen["days"] == 30
    assert StandInAnalyzer.seen["llm"] is True


def test_the_summary_counts_each_level(monkeypatch, tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("A\nB\nC\nD\n", encoding="utf-8")
    result = invoke(monkeypatch, path)
    assert "4 analyzed" in result.output
    assert "2 HIGH" in result.output
    assert "1 MEDIUM" in result.output
    assert "1 LOW" in result.output
    assert "EVASIVE" in result.output  # the LLM verdict column


def test_results_and_briefs_are_written(monkeypatch, tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("SKU-1\nSKU-2\n", encoding="utf-8")
    out = tmp_path / "out"
    result = invoke(monkeypatch, path, "--output", out, "--brief")
    assert result.exit_code == 0, result.output
    records = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert [r["product_id"] for r in records] == ["SKU-1", "SKU-2"]
    briefs = sorted(p.name for p in (out / "briefs").iterdir())
    assert len(briefs) == 2
    assert all("SKU-" in name for name in briefs)


def test_briefs_are_not_written_without_the_flag(monkeypatch, tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("SKU-1", encoding="utf-8")
    out = tmp_path / "out"
    invoke(monkeypatch, path, "--output", out)
    assert (out / "results.json").exists()
    assert not (out / "briefs").exists()
