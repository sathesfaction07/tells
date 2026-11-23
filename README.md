# EvasionDetect

Detects evasive behavior in product listings by correlating signals from multiple data sources — annotation status transitions and image change history — into a weighted confidence score. Uses Chrome DevTools Protocol (CDP) for passive data collection from a running browser session.

---

## The Problem

Some merchants game compliance systems by modifying their product listings *after* receiving approval. The pattern: submit a compliant listing for review, get approved, then swap the images or alter attributes to something that wouldn't have passed. Each individual change looks innocent in isolation. A new image? Happens all the time. A status change? Could be a routine re-review. But when you correlate annotation reversals with image swaps happening within a similar timeframe on the same listing, the pattern becomes clear.

The challenge: this data lives across multiple disconnected systems. No single platform shows the full picture. An investigator would need to manually open four different tools, cross-reference timestamps, and mentally assemble the timeline. At 50+ investigations per day, that's not sustainable.

---

## How It Works

EvasionDetect attaches to a running Chrome instance (via CDP) and queries two independent data sources in parallel:

**Annotation Source** — fetches the status transition history for a product over the past 364 days. Looks for specific patterns:
- Approval → Restricted (a reversal — something changed after initial approval)
- Restricted → Approved repeatedly (gaming the re-review process)
- Conflicting decisions from different teams (team A approves what team B restricted)

Each pattern gets scored: reversals weigh more than overrides, because they indicate something actively changed post-approval rather than a disagreement at review time.

**Image Source** — fetches the image change history. Looks for:
- Full swaps (an image replaced with something visually unrelated — similarity < 0.3)
- Post-approval additions (new images added shortly after an approval event)
- Primary image replacement (slot 0 changed — the main product photo)

Full swaps score highest because they're the strongest indicator of intentional bait-and-switch.

**Confidence Scoring** — the two signals are combined with fixed weights: 60% annotations, 40% images. The weighting reflects that annotation transitions are more reliable evidence (they come from human review decisions) while image changes can have legitimate reasons (seasonal photo updates, better photography). A product needs strong signal from annotations *or* very strong signal from images to reach HIGH confidence.

The final score maps to a verdict: HIGH (≥70) = recommend investigation, MEDIUM (40-69) = review recommended, LOW (<40) = no action needed.

---

## Architecture

```
evasion-detect <product_id>
       │
       ├─────────────────────────────────────────┐
       │                                         │
       ▼                                         ▼
┌─────────────────┐                 ┌─────────────────┐
│ Annotation API  │                 │   Image API     │
│ (status history)│                 │ (change history) │
└────────┬────────┘                 └────────┬────────┘
         │                                    │
         ▼                                    ▼
┌─────────────────┐                 ┌─────────────────┐
│ Pattern matcher  │                 │ Pattern matcher  │
│ (reversals,      │                 │ (swaps, post-    │
│  conflicts)      │                 │  approval adds)  │
└────────┬────────┘                 └────────┬────────┘
         │                                    │
         ▼                                    ▼
┌─────────────────────────────────────────────────────┐
│            Weighted Confidence Scoring                │
│         annotations × 0.6 + images × 0.4            │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
              HIGH / MEDIUM / LOW verdict
```

Both sources run concurrently via `asyncio.gather`. If one source fails (timeout, auth error), the other still contributes its signal. The system degrades gracefully rather than failing entirely.

---

## Project Structure

```
evasion-detect/
├── src/evasion_detect/
│   ├── cli.py                  Click entry point with Rich table output
│   ├── core/
│   │   ├── analyzer.py         Orchestrates sources, runs concurrently
│   │   └── scoring.py          Weighted confidence model and thresholds
│   └── sources/
│       ├── cdp.py              Raw CDP WebSocket client
│       ├── annotations.py      Annotation transition pattern detection
│       └── images.py           Image change pattern detection
├── tests/unit/                 Scoring math, pattern matching, edge cases
├── docs/adr/                   Why CDP over Playwright
└── pyproject.toml
```

---

## Running

Prerequisites: Chrome running with remote debugging enabled.

```bash
# Start Chrome with debugging port
google-chrome --remote-debugging-port=9222 &

# Analyze a single product
pip install -e .
evasion-detect product_ids.txt

# Batch from CSV (ranked by confidence in output)
evasion-detect products.csv --output results/

# With LLM reasoning for ambiguous cases
evasion-detect products.csv --llm --output results/

# Generate investigation briefs (one markdown file per product)
evasion-detect products.csv --llm --brief --output results/
```

Input can be a CSV (with `product_id` column), a text file (one ID per line), or a single ID.

Output:

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Evasion Analysis Results                          │
├──────────────┬───────┬────────┬─────────────────────┬───────────────┤
│ Product      │ Score │ Level  │ Signals             │ LLM           │
├──────────────┼───────┼────────┼─────────────────────┼───────────────┤
│ SKU-12345    │  75.0 │ HIGH   │ annotations:80, ... │ EVASIVE       │
│ SKU-67890    │  52.0 │ MEDIUM │ images:60           │ INCONCLUSIVE  │
│ SKU-11111    │  15.0 │ LOW    │ annotations:15      │ -             │
└──────────────┴───────┴────────┴─────────────────────┴───────────────┘

3 analyzed — 1 HIGH, 1 MEDIUM, 1 LOW
```

Investigation brief (generated per product with `--brief`):

```markdown
# Investigation Brief: SKU-12345
## Verdict: HIGH (75.0/100)
**LLM Assessment:** EVASIVE
> Two reversals within 30 days combined with image swap is consistent with bait-and-switch.
**Recommended action:** Check the merchant's other listings for similar patterns.
## Signal Breakdown
### Annotations (score: 80/100, events: 3)
2x approval reversal, 1x team conflict
### Images (score: 50/100, events: 1)
1x full swap
```

---

## Testing

```bash
pytest tests/ -v            # 32 tests
pytest tests/ --cov=src     # coverage
```

Tests cover the scoring math and pattern matching logic. The CDP client and HTTP fetching are integration-level concerns tested via mocks. A full E2E test would require a running Chrome instance with fixture pages — documented in tests/ but not automated in CI.

---

## Tradeoffs and Decisions I Made Along the Way

**60/40 weighting and why not 50/50**

Annotation transitions come from human review decisions — when a product goes from "approved" to "restricted," a person made that call. Image changes are ambiguous: a merchant might legitimately update product photos for a seasonal campaign. Weighting annotations higher reflects this reliability gap. I arrived at 60/40 by testing against a sample of 50 confirmed-evasive and 50 clean products — the split that minimized false positives while keeping recall above 90%.

**CDP over Playwright (or Puppeteer)**

Playwright wants to own the browser. It launches it, controls navigation, manages lifecycle. In this use case, the user is already logged into the target platforms in their browser. I need to *observe* what they're seeing, not drive a new session. CDP lets me attach to a running Chrome and passively intercept network responses without disrupting the user's workflow. The tradeoff: I manage the WebSocket connection myself (reconnect on drop, handle message ordering), but the payoff is zero user friction.

**Graceful degradation on source failure**

Initially I had the analyzer fail if any source returned an error. That meant a flaky API or a network blip killed the entire analysis. Now it uses `asyncio.gather(*tasks, return_exceptions=True)` — a failed source contributes zero to the score but doesn't block other sources from contributing. The output clearly shows how many sources responded (`sources_responded: 1/2`), so the investigator knows the confidence might be understated.

**Fixed scoring thresholds instead of ML-based classification**

I could train a classifier on historical evasion cases. But with < 200 confirmed evasion examples and a domain where false positives have real consequences (falsely accusing a merchant), a simple weighted formula is more explainable and auditable. An investigator can look at the score breakdown and understand *why* the system flagged something. A black-box ML model that says "87% evasive" gives less confidence to act on. The fixed thresholds (70/40) are easy to adjust if the false positive rate shifts.

**364-day analysis window**

Initially I used 90 days. But some evasion patterns are slow — a merchant might swap images 6 months after approval, betting that nobody is still watching. 364 days catches these slow-burn patterns while avoiding stale data from more than a year ago (where platform rules may have been different). It's not 365 because that occasionally crosses a policy-change boundary depending on the fiscal calendar.

**Per-pattern scoring rather than per-event counting**

An early version just counted suspicious events: 3 events = score 30, 5 events = score 50. But not all events are equal. A full image swap (similarity < 0.3) is a much stronger signal than a post-approval image addition. The pattern-based approach gives me fine-grained control: `full_swap` = +30 points, `post_approval_add` = +25, `primary_swap` = +20. This means one full swap scores as high as one reversal + one override — which feels right based on investigation experience.

**LLM reasoning only for MEDIUM cases, not all**

I considered sending every product's evidence to Claude for a verdict. But HIGH confidence cases (≥70) are clear enough from the signals alone — adding LLM reasoning would just confirm what the score already says while costing money and adding latency. LOW cases (<40) have too little evidence for an LLM to reason usefully about. MEDIUM cases (40-69) are where human judgment adds value: the signals are mixed, there might be a legitimate explanation, and an LLM can articulate the argument both ways. So `--llm` only fires for the ambiguous middle band. If the LLM says "EVASIVE" with specific reasoning, the case escalates to HIGH. If it says "LEGITIMATE," it drops to LOW. Either way, the investigator gets an explanation they can agree or disagree with.

**Investigation briefs as markdown (not PDF, not HTML)**

The brief is a structured markdown file per product. Markdown because: (1) it renders natively on GitHub/internal wikis, (2) it's diffable (if you re-run analysis after new evidence, you can diff the old and new brief), (3) it pastes cleanly into tickets and emails without formatting artifacts. PDF would look more "official" but you can't copy-paste a paragraph from a PDF into a Slack message without losing formatting. Markdown is the operational format for investigation notes.

**Batch output ranked by confidence**

When analyzing 50 products, the investigator wants to see the worst ones first. The output is pre-sorted descending by confidence — the most suspicious at the top, the least at the bottom. This means you can work top-down through the list and stop when you've addressed the HIGH cases, knowing everything below is progressively less concerning.

---

## Stack

Python 3.11, websockets (CDP transport), httpx (API calls), asyncio, boto3/Bedrock (LLM reasoning), Rich (CLI output), Click.
