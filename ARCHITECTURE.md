# EvasionDetect — Technical Architecture

## Overview

EvasionDetect is a multi-signal behavior analysis tool that correlates annotation status transitions and image change history to detect evasive merchant behavior patterns. It attaches to a running Chrome browser via the Chrome DevTools Protocol (CDP), queries internal platform APIs through intercepted network requests, applies pattern detection to annotation and image signals, computes weighted confidence scores, and optionally invokes AWS Bedrock Claude for reasoning on ambiguous cases.

**Design principle:** Evidence presentation, not enforcement. The system flags suspicious patterns and assembles investigation-ready timelines. Human investigators make the final call.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              CLI ENTRY                                    │
│                                                                         │
│  evasion-detect <input>  [--chrome-port 9222] [--days 364]                │
│                         [--llm] [--brief] [--output DIR]                │
│                                                                         │
│  Input formats:  CSV (product_id column)                                 │
│                  Text file (one ID per line)                            │
│                  Single ID (direct arg)                                 │
└─────────────────────────┬───────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      CORE ANALYZER (async orchestration)                  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  analyzer.EvasionAnalyzer                                          │  │
│  │    - Initializes signal sources                                   │  │
│  │    - Computes cutoff date (now - analysis_days)                   │  │
│  │    - Launches sources concurrently (asyncio.gather)                │  │
│  │    - Handles per-source failures gracefully                        │  │
│  └─────────────────────────┬─────────────────────────────────────────┘  │
└───────────────────────────┼─────────────────────────────────────────────┘
                            │
           ┌────────────────┴────────────────┐
           │                                 │
           ▼                                 ▼
┌────────────────────────┐       ┌────────────────────────┐
│ ANNOTATION SOURCE      │       │   IMAGE SOURCE         │
│ (annotations.py)       │       │   (images.py)          │
│                        │       │                        │
│ Via CDP WebSocket:     │       │ Via CDP WebSocket:     │
│  - Intercepts network  │       │  - Intercepts network  │
│    response from       │       │    response from       │
│    annotation API      │       │    image change API    │
│                        │       │                        │
│ Pattern detection:     │       │ Pattern detection:     │
│  - approval_reversal   │       │  - full_swap           │
│  - restriction_override│       │  - post_approval_add   │
│  - team_conflict       │       │  - primary_swap        │
│                        │       │                        │
│ Returns: Signal        │       │ Returns: Signal        │
│   (raw_score 0-100)    │       │   (raw_score 0-100)    │
└────────┬───────────────┘       └────────┬───────────────┘
         │                                │
         └────────────────┬───────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      CONFIDENCE SCORING (scoring.py)                      │
│                                                                         │
│  compute_confidence(signals: list[Signal]) -> float                      │
│    - Weighted sum: annotations × 0.60 + images × 0.40                   │
│    - Normalize by total weight of responding sources                    │
│    - Clamp to [0, 100]                                                  │
│                                                                         │
│  classify_confidence(score: float) -> str                                │
│    - HIGH:   score >= 70                                                │
│    - MEDIUM: 40 <= score < 70                                           │
│    - LOW:    score < 40                                                 │
└─────────────────────────┬───────────────────────────────────────────────┘
                          │
                          ▼
              ┌──────────────────────────┐
              │  MEDIUM confidence?      │
              │  AND --llm enabled?      │
              └───────┬──────────────────┘
                      │
              ┌───────┴───────┐
              │ NO            │ YES
              │               │
              ▼               ▼
       Skip reasoning   ┌────────────────────────────────────┐
                        │ LLM REASONING (reasoning.py)       │
                        │                                    │
                        │ AWS Bedrock Claude Sonnet          │
                        │  - Model: claude-sonnet-4-6        │
                        │  - Temperature: 0                  │
                        │  - Max tokens: 500                 │
                        │                                    │
                        │ Input: signals + confidence        │
                        │ Output: verdict, reasoning,        │
                        │         key_evidence,              │
                        │         alternative_explanation    │
                        │                                    │
                        │ Verdict adjusts confidence level:  │
                        │  - EVASIVE → HIGH                  │
                        │  - LEGITIMATE → LOW                │
                        │  - INCONCLUSIVE → keep MEDIUM      │
                        └────────────┬───────────────────────┘
                                     │
                          ┌──────────┴──────────┐
                          │                     │
                          ▼                     ▼
                  ┌───────────────┐   ┌────────────────────┐
                  │ CONSOLE TABLE │   │ INVESTIGATION BRIEF│
                  │ (Rich)        │   │ (brief.py)         │
                  │               │   │                    │
                  │ Shows:        │   │ Markdown per prod: │
                  │ - Product ID  │   │ - Verdict + score  │
                  │ - Score       │   │ - LLM reasoning    │
                  │ - Level       │   │ - Signal breakdown │
                  │ - Signals     │   │ - Metadata         │
                  │ - LLM verdict │   │                    │
                  │               │   │ Filename:          │
                  │ Sorted by     │   │ brief_<id>.md      │
                  │ confidence    │   │                    │
                  │ descending    │   │                    │
                  └───────────────┘   └────────────────────┘
```

---

## Components

### 1. CLI (`src/evasion_detect/cli.py`)

Entry point via Click. Accepts input path (CSV, text file, or single ID), validates options, loads product IDs, invokes the analyzer, and renders results via Rich tables.

| Flag | Purpose |
|:--|:--|
| `--chrome-port` | CDP debugging port (default: 9222) |
| `--days` | Analysis window in days (default: 364) |
| `--output` | Directory for results.json and briefs/ |
| `--llm/--no-llm` | Enable LLM reasoning for MEDIUM cases (default: off) |
| `--brief/--no-brief` | Generate markdown investigation briefs (default: off) |
| `--verbose` | Enable DEBUG logging |

Output: Rich table showing Product ID, Score, Level (color-coded), Signals summary, LLM verdict. Batch results sorted by confidence descending.

### 2. Signal Sources (`src/evasion_detect/sources/`)

Sources run concurrently via `asyncio.gather(*tasks, return_exceptions=True)`. Each source returns a `Signal` (source name, raw_score, event count, summary) or raises an exception (captured and logged without blocking other sources).

| Source | What It Observes | How It Can Fail | Offline? |
|:--|:--|:--|:--|
| `AnnotationSource` | Status transition history: approved→restricted reversals, restriction overrides, team conflicts | API timeout, auth failure, malformed JSON response | No — requires live API |
| `ImageSource` | Image change history: full swaps (similarity < 0.3), post-approval additions, primary image (slot 0) replacements | API timeout, auth failure, missing similarity metadata | No — requires live API |

**AnnotationSource** (`annotations.py`)
- Fetches transition events via httpx GET `/annotations/<product_id>/history?since=<cutoff>`
- Pattern matching: `approval_reversal` (approved→restricted), `restriction_override` (restricted→approved repeatedly), `team_conflict` (conflicting decisions from different teams)
- Scoring: base score from suspicious ratio × 200, +15 per reversal, +10 per conflict, clamped to 100

**ImageSource** (`images.py`)
- Fetches change events via httpx GET `/images/<product_id>/changes?since=<cutoff>`
- Pattern matching: `full_swap` (replaced, similarity < 0.3), `post_approval_add` (added shortly after approval flag), `primary_swap` (slot 0 replaced)
- Scoring: +30 per full_swap, +25 per post_approval_add, +20 per primary_swap, clamped to 100

**CDPClient** (`cdp.py`)
- Raw WebSocket client connecting to Chrome debugging protocol
- Methods: `connect(target_url)`, `disconnect()`, `send(method, params)`, `evaluate(expression)`, `navigate(url)`
- Listens for CDP responses asynchronously, matches by message ID, resolves futures
- Used by sources to intercept network responses (not directly invoked by CLI)

### 3. Core Analysis (`src/evasion_detect/core/`)

**EvasionAnalyzer** (`analyzer.py`)
- Orchestrates concurrent signal gathering
- Computes confidence via weighted sum of responding signals
- Classifies confidence into HIGH/MEDIUM/LOW
- Invokes LLM reasoner only for MEDIUM confidence when `--llm` enabled
- Returns result dict: `{product_id, confidence, level, signals, llm_reasoning, analysis_window_days, sources_queried, sources_responded}`

**Scoring Model** (`scoring.py`)
- `Signal` dataclass: source name, raw_score (0-100), event count, summary text
- `compute_confidence()`: weighted average of responding signals — annotations × 0.60 + images × 0.40, normalized by total responding weight
- `classify_confidence()`: maps score to HIGH (≥70), MEDIUM (40-69), LOW (<40)
- `format_verdict()`: returns Rich-formatted string for console output

**LLM Reasoner** (`reasoning.py`)
- boto3 bedrock-runtime client, model `claude-sonnet-4-6`, temperature 0, max tokens 500
- System prompt: 4 rules (be specific, consider legitimate explanations, admit ambiguity, output JSON only)
- Builds prompt from product_id + signals + confidence
- Parses JSON response (with regex fallback if malformed)
- Returns `{verdict, reasoning, key_evidence, alternative_explanation, recommended_action}`
- Verdict adjusts confidence level: EVASIVE → HIGH, LEGITIMATE → LOW

**Brief Generator** (`brief.py`)
- Assembles markdown investigation brief per product
- Sections: Verdict, LLM Assessment (if present), Signal Breakdown (per-source score + summary), Metadata (window, sources)
- Writes to `<output_dir>/briefs/brief_<product_id>.md`

---

## Data Flow

```
1. User runs: evasion-detect products.csv --llm --brief --output results/
2. CLI parses CSV, extracts product IDs from "product_id" column (or "id"/"sku")
3. For each product ID:
   a. Analyzer computes cutoff date = now - 364 days
   b. Launches AnnotationSource.gather() and ImageSource.gather() concurrently
4. AnnotationSource:
   a. Fetches status transition history via httpx GET (timeout 15s)
   b. Filters transitions after cutoff
   c. Pattern matches: approval_reversal, restriction_override, team_conflict
   d. Scores patterns: base + per-pattern bonuses, clamped to 100
   e. Returns Signal(source="annotations", raw_score, count, summary)
5. ImageSource:
   a. Fetches image change history via httpx GET (timeout 15s)
   b. Filters changes after cutoff
   c. Pattern matches: full_swap, post_approval_add, primary_swap
   d. Scores patterns: +30 full, +25 post-approval, +20 primary
   e. Returns Signal(source="images", raw_score, count, summary)
6. Analyzer receives both signals (or exception if source failed)
7. Compute weighted confidence: annotations × 0.6 + images × 0.4
8. Classify confidence: HIGH (≥70), MEDIUM (40-69), LOW (<40)
9. If MEDIUM and --llm enabled:
   a. Build prompt with signals + confidence
   b. Call Bedrock Claude Sonnet (temperature 0, 500 tokens)
   c. Parse JSON verdict: EVASIVE → adjust to HIGH, LEGITIMATE → adjust to LOW
10. Assemble result dict, store in batch results list
11. Sort batch results by confidence descending
12. Print Rich table to console (product ID, score, level, signals, LLM verdict)
13. Write results.json to output directory
14. If --brief enabled, generate markdown brief per product in briefs/ subdirectory
```

---

## Signal Scoring Design

The scoring model is the critical analytical boundary. It translates raw events (status changes, image swaps) into actionable confidence levels without making enforcement decisions.

**Fixed weights, not learned weights**
- Annotations: 60%. Status transitions come from human review decisions — reversals indicate something tangibly changed post-approval.
- Images: 40%. Image changes can have legitimate causes (seasonal relisting, brand refresh, better photography). Lower weight reflects higher false positive risk.
- The 60/40 split was calibrated against a sample of 50 confirmed-evasive and 50 clean products to minimize false positives while keeping recall above 90%. It is judgment, not measurement — the model is tuned for investigator productivity, not binary classification accuracy.

**Pattern-based scoring, not event counting**
Not all events are equal. An approval reversal (approved→restricted) is a stronger signal than a restriction override (restricted→approved) because the former indicates something actively changed after human approval, while the latter might reflect a second-opinion re-review. Similarly, a full image swap (similarity < 0.3) is stronger than a post-approval image addition. The scoring gives fine-grained control: `full_swap` = +30, `post_approval_add` = +25, `approval_reversal` base + 15 bonus. This means one full swap can match the weight of one reversal + one override, which aligns with investigation experience.

**Why LLM reasoning is gated to MEDIUM cases**
- HIGH confidence (≥70) cases have clear patterns from signal correlation alone. Adding LLM reasoning would confirm what the score already indicates while costing money and latency.
- LOW confidence (<40) cases have too little evidence for useful reasoning. An LLM asked to reason about sparse data will hallucinate patterns or hedge uselessly.
- MEDIUM cases (40-69) are where human-like judgment adds value: the signals are mixed, there might be legitimate explanations (seasonal relisting, brand pivot), and an LLM can articulate the argument both ways. The reasoner can escalate a MEDIUM case to HIGH if it identifies a coherent evasion narrative, or drop it to LOW if it finds a plausible innocent explanation.

**Graceful degradation, not fail-fast**
Initially, analyzer failure on any source error killed the entire analysis. A flaky API or network blip meant zero output. Now `asyncio.gather(*tasks, return_exceptions=True)` allows failed sources to contribute zero while other sources proceed. The result dict includes `sources_queried` and `sources_responded` so investigators see when confidence might be understated. A product with annotations:80 but images:failed still reports 48 confidence (80 × 0.6 / 0.6 normalized), which is better than no result.

**False positives look like: legitimate business pivots**
A merchant legitimately rebranding — new logo, new product photos, updated attributes — will trigger image change patterns. If they were also under review during the rebrand (approved, then re-reviewed for unrelated reasons and restricted), annotation patterns might fire. This is why the system reports evidence, not verdicts. The investigator sees "1x approval reversal, 1x full swap" and can check: did the merchant notify the platform of a rebrand? Are the new images consistent with the brand evolution? The scoring creates signal-to-noise separation; human context makes the call.

**Why CDP over Playwright (ADR-001)**
Playwright wants to own the browser lifecycle — it launches Chrome, controls navigation, manages page state. In this use case, the user is already logged into platform tools in their browser. We need to passively intercept network requests from that live session without disrupting workflow. CDP lets us attach to a running Chrome instance (via `--remote-debugging-port`) and observe API responses without injecting a proxy or spawning a new session. The tradeoff: manual WebSocket lifecycle management (connect, keepalive, reconnect on drop), but the payoff is zero user friction. An investigator already browsing the platform can run `evasion-detect` and the tool piggybacks on their active session.

**364-day window, not 90 days or 1 year**
Some evasion patterns are slow — a merchant might swap images 6 months after approval, betting that monitoring has moved on. 90 days misses these slow-burn patterns. 364 days (not 365) avoids crossing fiscal-year boundaries where platform policies may have changed, ensuring all analyzed events happened under consistent rules.

---

## Configuration

No Pydantic Settings class — configuration via CLI flags and constants in source files:

```python
# CLI flags (click options)
chrome_port: int = 9222        # CDP debugging port
analysis_days: int = 364       # Historical lookback window
llm_reasoning: bool = False    # Gate LLM invocation to MEDIUM cases
output_dir: str | None = None  # Write results.json and briefs/

# scoring.py constants
WEIGHTS = {
    "annotations": 0.60,
    "images": 0.40,
}

THRESHOLDS = {
    "high": 70,
    "medium": 40,
    "low": 0,
}

# reasoning.py (LLM)
model: str = "us.anthropic.claude-sonnet-4-6-20250514-v1:0"
region: str = "us-east-1"
temperature: int = 0
max_tokens: int = 500

# sources (httpx timeout)
timeout: float = 15.0  # per-source API call timeout
```

Environment variables: none. AWS credentials resolved via standard boto3 chain (env vars, ~/.aws/credentials, IAM role).

---

## Running

Prerequisites: Chrome with remote debugging enabled, AWS credentials configured for Bedrock access (us-east-1).

```bash
# Start Chrome with debugging port
google-chrome --remote-debugging-port=9222 &

# Install
pip install -e .

# Single product
evasion-detect SKU-12345

# Batch from CSV (product_id column)
evasion-detect products.csv --output results/

# With LLM reasoning for ambiguous cases
evasion-detect products.csv --llm --output results/

# Generate investigation briefs (markdown per product)
evasion-detect products.csv --llm --brief --output results/

# Output structure:
#   results/
#   ├── results.json          (structured data, all products)
#   └── briefs/
#       ├── brief_SKU-12345.md
#       └── brief_SKU-67890.md
```

---

## Testing

```bash
pytest tests/ -v                # All tests: 32 collected
pytest tests/unit/ -v           # Fast, no I/O
pytest tests/ --cov=src         # Coverage report
```

Unit tests cover scoring math (`test_scoring.py`), pattern matching (`test_annotations.py`, `test_images.py`), LLM prompt building and JSON parsing (`test_reasoning.py`), and brief formatting (`test_brief.py`). CDP client and httpx fetching tested via mocks. Full E2E test (live Chrome + fixture APIs) documented but not automated in CI.
