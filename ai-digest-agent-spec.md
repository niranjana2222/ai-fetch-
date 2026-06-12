# AI Research Digest — Multi-Agent Build Spec

> **Purpose:** Instructions for Claude (or any agent) to build and operate a daily AI research digest pipeline using LangGraph + Claude CLI (`claude -p`) as the inference engine. No Anthropic SDK model calls — all LLM work goes through the Claude CLI subprocess.

---

## Overview

A four-agent LangGraph pipeline runs each morning, fetches today's AI research from arXiv, Hugging Face, and news RSS feeds, categorizes and summarizes each item, and delivers a Markdown email digest.

**Inference engine:** `claude -p` (Claude Code headless / Agent SDK CLI)
**Orchestration:** LangGraph `StateGraph`
**Scheduler:** GitHub Actions cron (recommended) or `schedule` library
**Delivery:** Resend (email) or Slack webhook

---

## Repository Layout

```
ai-digest/
├── agents/
│   ├── fetcher.py        # pulls raw papers/articles
│   ├── categorizer.py    # bins items by research area
│   ├── summarizer.py     # writes 2-sentence summaries + scores
│   └── reporter.py       # assembles final Markdown digest
├── graph.py              # LangGraph StateGraph wiring
├── deliver.py            # email or Slack delivery
├── scheduler.py          # local cron fallback
├── config.py             # env vars, categories, source URLs
├── prompts/
│   ├── categorize.txt    # system prompt for categorizer agent
│   └── summarize.txt     # system prompt for summarizer agent
├── requirements.txt
├── .env.example
└── .github/
    └── workflows/
        └── digest.yml    # GitHub Actions scheduler
```

---

## Dependencies

```
# requirements.txt
langgraph>=0.2
arxiv
feedparser
requests
markdown
resend
python-dotenv
schedule
```

> **No `langchain-anthropic`, `anthropic`, or any model SDK.** All LLM calls go through `claude -p` as a subprocess.

---

## Environment Variables

```bash
# .env.example
ANTHROPIC_API_KEY=sk-ant-...      # used by the claude CLI, not imported in Python
RESEND_API_KEY=re_...
DIGEST_EMAIL=you@example.com
DIGEST_FROM=digest@yourdomain.com
```

> `ANTHROPIC_API_KEY` must be exported in the shell environment so the `claude` CLI subprocess can authenticate. Claude Code bare mode reads it from the env, not from keychain.

---

## Claude CLI — How to Call It

Every agent that needs LLM work **must** invoke Claude via subprocess using this pattern:

```python
import subprocess, json, os

def call_claude(prompt: str, system: str = "") -> str:
    """
    Call claude CLI in headless bare mode.
    Returns the plain-text result string.
    Raises RuntimeError on non-zero exit.
    """
    cmd = ["claude", "--bare", "-p", prompt, "--output-format", "json"]
    if system:
        cmd += ["--append-system-prompt", system]

    env = {**os.environ}  # forwards ANTHROPIC_API_KEY automatically

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed:\n{result.stderr}")

    payload = json.loads(result.stdout)
    return payload["result"]   # plain text response
```

**Key flags to always use:**

| Flag | Why |
|---|---|
| `--bare` | Skips hooks/plugins/MCP discovery — faster, deterministic, CI-safe |
| `-p` | Headless non-interactive mode |
| `--output-format json` | Gives `result`, `session_id`, `total_cost_usd` — parse `result` field |
| `--append-system-prompt` | Injects a system-level instruction without replacing Claude's defaults |

**Never use** `--dangerously-skip-permissions` — not needed here since agents only read stdin/stdout.

---

## Agent Implementations

### `config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

DIGEST_EMAIL  = os.getenv("DIGEST_EMAIL")
DIGEST_FROM   = os.getenv("DIGEST_FROM", "digest@yourdomain.com")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

CATEGORIES = [
    "LLMs & Foundation Models",
    "Vision & Multimodal",
    "Agents & Robotics",
    "Safety & Alignment",
    "Efficiency & Hardware",
    "Other"
]

SOURCES = {
    "arxiv_categories": ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.RO"],
    "hf_daily_rss":     "https://huggingface.co/papers.rss",
    "news_rss": [
        "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
        "https://venturebeat.com/category/ai/feed/"
    ]
}

MAX_PAPERS = 30   # total fetched; top ~20 survive scoring
```

---

### `agents/fetcher.py`

No LLM calls here — pure data collection.

```python
import arxiv, feedparser
from datetime import date, timedelta
from config import SOURCES, MAX_PAPERS

def fetch_papers(state: dict) -> dict:
    today     = date.today()
    yesterday = today - timedelta(days=1)
    items = []

    # arXiv
    client = arxiv.Client()
    per_cat = max(1, MAX_PAPERS // len(SOURCES["arxiv_categories"]))
    for cat in SOURCES["arxiv_categories"]:
        query = (
            f"cat:{cat} AND submittedDate:"
            f"[{yesterday.strftime('%Y%m%d')} TO {today.strftime('%Y%m%d')}]"
        )
        for r in client.results(arxiv.Search(query=query, max_results=per_cat,
                                              sort_by=arxiv.SortCriterion.SubmittedDate)):
            items.append({
                "title":    r.title,
                "abstract": r.summary[:800],
                "url":      r.entry_id,
                "source":   "arXiv",
                "authors":  [a.name for a in r.authors[:3]],
            })

    # Hugging Face daily papers RSS
    feed = feedparser.parse(SOURCES["hf_daily_rss"])
    for entry in feed.entries[:15]:
        items.append({
            "title":    entry.title,
            "abstract": entry.get("summary", "")[:800],
            "url":      entry.link,
            "source":   "HuggingFace",
            "authors":  [],
        })

    # News RSS
    for rss_url in SOURCES["news_rss"]:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:5]:
            items.append({
                "title":    entry.title,
                "abstract": entry.get("summary", "")[:500],
                "url":      entry.link,
                "source":   "News",
                "authors":  [],
            })

    print(f"[Fetcher] {len(items)} items retrieved")
    return {**state, "raw_items": items}
```

---

### `agents/categorizer.py`

Uses `call_claude()`. Batch 10 items per call to minimise subprocess overhead.

```python
import json
from config import CATEGORIES
from utils import call_claude   # the helper defined above

SYSTEM = (
    "You are a research categorizer. "
    "Return ONLY valid JSON — no prose, no markdown fences."
)

def categorize_items(state: dict) -> dict:
    items = state["raw_items"]
    categorized = []
    batch_size = 10

    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        batch_text = "\n\n".join(
            f"[{j}] TITLE: {item['title']}\nABSTRACT: {item['abstract']}"
            for j, item in enumerate(batch)
        )

        prompt = (
            f"Categorize each item into exactly one of:\n{json.dumps(CATEGORIES)}\n\n"
            f"Items:\n{batch_text}\n\n"
            f"Return a JSON array: "
            f'[{{"index": 0, "category": "LLMs & Foundation Models"}}, ...]'
        )

        try:
            raw = call_claude(prompt, system=SYSTEM)
            assignments = json.loads(raw)
            for a in assignments:
                item = batch[a["index"]].copy()
                item["category"] = a.get("category", "Other")
                categorized.append(item)
        except Exception as e:
            print(f"[Categorizer] batch {i} error: {e} — defaulting to 'Other'")
            for item in batch:
                categorized.append({**item, "category": "Other"})

    print(f"[Categorizer] {len(categorized)} items categorized")
    return {**state, "categorized_items": categorized}
```

---

### `agents/summarizer.py`

Sends all items in a single prompt. Claude returns a JSON array of summaries and significance scores.

```python
import json
from utils import call_claude

SYSTEM = (
    "You are an AI research analyst writing for technical practitioners. "
    "Be concise and precise. "
    "Return ONLY valid JSON — no prose, no markdown fences."
)

def summarize_items(state: dict) -> dict:
    items = state["categorized_items"]

    items_text = "\n\n".join(
        f"[{i}] {item['title']}\n{item['abstract']}"
        for i, item in enumerate(items)
    )

    prompt = (
        "For each item write:\n"
        "  1. A 2-sentence plain-English summary (what it does + why it matters)\n"
        "  2. A significance score 1–10 (10 = major breakthrough)\n\n"
        f"Items:\n{items_text}\n\n"
        'Return JSON array: [{"index": 0, "summary": "...", "score": 8}, ...]'
    )

    enriched = []
    try:
        raw = call_claude(prompt, system=SYSTEM)
        summaries = json.loads(raw)
        score_map = {s["index"]: s for s in summaries}
        for i, item in enumerate(items):
            s = score_map.get(i, {"summary": item["abstract"][:200], "score": 5})
            enriched.append({**item, "summary": s["summary"], "significance": s["score"]})
    except Exception as e:
        print(f"[Summarizer] error: {e} — using raw abstracts")
        enriched = [{**item, "summary": item["abstract"][:200], "significance": 5}
                    for item in items]

    print(f"[Summarizer] {len(enriched)} items scored")
    return {**state, "enriched_items": enriched}
```

---

### `agents/reporter.py`

No LLM call needed — pure formatting.

```python
from collections import defaultdict
from datetime import date
from config import CATEGORIES

def build_report(state: dict) -> dict:
    items  = state["enriched_items"]
    today  = date.today().strftime("%B %d, %Y")

    # Group and sort
    by_cat = defaultdict(list)
    for item in items:
        by_cat[item["category"]].append(item)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda x: x["significance"], reverse=True)
        by_cat[cat] = by_cat[cat][:5]   # top 5 per category

    # Build Markdown
    lines = [
        f"# 🤖 AI Research Digest — {today}\n",
        f"*{len(items)} papers reviewed · {len(by_cat)} active categories*\n",
        "---\n",
    ]

    for cat in CATEGORIES:
        cat_items = by_cat.get(cat, [])
        if not cat_items:
            continue
        lines.append(f"## {cat}\n")
        for item in cat_items:
            stars = "⭐" * max(1, item["significance"] // 3)
            lines.append(f"### [{item['title']}]({item['url']}) {stars}")
            if item["authors"]:
                lines.append(f"*{', '.join(item['authors'][:3])}*")
            lines.append(f"\n{item['summary']}\n")
            lines.append(
                f"*Source: {item['source']} | Significance: {item['significance']}/10*\n"
            )
            lines.append("---\n")

    report = "\n".join(lines)
    print(f"[Reporter] Digest built ({len(report)} chars)")
    return {**state, "report_markdown": report}
```

---

### `utils.py`

```python
import subprocess, json, os

def call_claude(prompt: str, system: str = "") -> str:
    cmd = ["claude", "--bare", "-p", prompt, "--output-format", "json"]
    if system:
        cmd += ["--append-system-prompt", system]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env={**os.environ},
        timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed:\n{result.stderr}")

    payload = json.loads(result.stdout)
    return payload["result"]
```

---

### `graph.py`

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any

from agents.fetcher      import fetch_papers
from agents.categorizer  import categorize_items
from agents.summarizer   import summarize_items
from agents.reporter     import build_report

class DigestState(TypedDict):
    raw_items:        List[Dict[str, Any]]
    categorized_items: List[Dict[str, Any]]
    enriched_items:   List[Dict[str, Any]]
    report_markdown:  str

def build_graph():
    g = StateGraph(DigestState)
    g.add_node("fetch",      fetch_papers)
    g.add_node("categorize", categorize_items)
    g.add_node("summarize",  summarize_items)
    g.add_node("report",     build_report)

    g.set_entry_point("fetch")
    g.add_edge("fetch",      "categorize")
    g.add_edge("categorize", "summarize")
    g.add_edge("summarize",  "report")
    g.add_edge("report",     END)

    return g.compile()

def run_digest() -> str:
    app = build_graph()
    result = app.invoke({
        "raw_items": [], "categorized_items": [],
        "enriched_items": [], "report_markdown": ""
    })
    return result["report_markdown"]
```

---

### `deliver.py`

```python
import resend, markdown as md_lib
from datetime import date
from config import RESEND_API_KEY, DIGEST_EMAIL, DIGEST_FROM

resend.api_key = RESEND_API_KEY

def send_digest(report_md: str):
    html_body = md_lib.markdown(report_md, extensions=["tables", "toc"])
    html = f"""
    <html><body style="font-family:-apple-system,sans-serif;max-width:700px;
                       margin:0 auto;padding:20px;color:#1a1a1a;line-height:1.6">
    {html_body}
    </body></html>"""

    resend.Emails.send({
        "from":    DIGEST_FROM,
        "to":      DIGEST_EMAIL,
        "subject": f"🤖 AI Research Digest — {date.today()}",
        "html":    html
    })
    print(f"[Deliver] Sent to {DIGEST_EMAIL}")
```

---

## Deployment

### Option 1 — GitHub Actions (recommended)

```yaml
# .github/workflows/digest.yml
name: Daily AI Digest

on:
  schedule:
    - cron: '0 7 * * *'   # 07:00 UTC daily
  workflow_dispatch:        # manual trigger for testing

jobs:
  digest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Claude CLI
        run: npm install -g @anthropic-ai/claude-code

      - name: Install Python deps
        run: pip install -r requirements.txt

      - name: Run digest
        run: |
          python -c "
          from graph import run_digest
          from deliver import send_digest
          send_digest(run_digest())
          "
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          RESEND_API_KEY:    ${{ secrets.RESEND_API_KEY }}
          DIGEST_EMAIL:      ${{ secrets.DIGEST_EMAIL }}
          DIGEST_FROM:       ${{ secrets.DIGEST_FROM }}
```

### Option 2 — local cron

```python
# scheduler.py
import schedule, time
from graph import run_digest
from deliver import send_digest

def morning_run():
    print("Starting daily digest...")
    send_digest(run_digest())
    print("Done.")

schedule.every().day.at("07:00").do(morning_run)

if __name__ == "__main__":
    morning_run()          # run immediately on startup
    while True:
        schedule.run_pending()
        time.sleep(60)
```

```bash
# Run as a background process
nohup python scheduler.py &> digest.log &
```

---

## Claude CLI Setup

```bash
# Install Node.js >= 18 first, then:
npm install -g @anthropic-ai/claude-code

# Authenticate once (interactive, sets up keychain)
claude

# Verify headless mode works
claude --bare -p "Hello" --output-format json
```

> In CI/GitHub Actions, keychain is unavailable. `ANTHROPIC_API_KEY` in the environment is sufficient — `--bare` mode reads it directly.

---

## Estimated Daily Cost

| Component | Cost |
|---|---|
| Claude CLI (~3 subprocess calls, ~60 items) | ~$0.08–0.15/day |
| Resend email | Free tier (100/day) |
| GitHub Actions runner | Free (2,000 min/month) |
| **Total** | **~$3–5/month** |

Track exact spend per run from the `total_cost_usd` field in the `--output-format json` response.

---

## Extension Ideas

| Feature | How |
|---|---|
| Slack delivery | Replace `deliver.py` with `slack_sdk` webhook post |
| Deduplication | Store paper URLs in SQLite; skip already-seen items |
| Trending detection | Count category appearances across days; surface repeating topics |
| Category filter | Add `INCLUDE_CATEGORIES` env var; reporter skips others |
| Pipe mode testing | `echo "test prompt" \| claude --bare -p - --output-format json` |

---

## Prompt Files (optional externalization)

Store reusable system prompts in `prompts/` and load them at runtime:

```python
# In categorizer.py
from pathlib import Path
SYSTEM = Path("prompts/categorize.txt").read_text()
```

This makes prompt iteration faster without touching Python code.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `claude: command not found` | `npm install -g @anthropic-ai/claude-code` |
| `Authentication required` in CI | Ensure `ANTHROPIC_API_KEY` is in env; use `--bare` |
| `claude CLI failed` RuntimeError | Check `result.stderr`; add `--verbose` to cmd for detail |
| JSON parse error from agent | Tighten the prompt: add `"Return ONLY valid JSON, no prose"` |
| Run takes > 5 min | Reduce `MAX_PAPERS` in config or cut batch count |
| `Error: Claude Code cannot be launched inside another Claude Code session` | You're running from inside a Claude Code session; set `CLAUDECODE=""` in subprocess env |
