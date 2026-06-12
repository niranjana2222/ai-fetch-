import json
from pathlib import Path
from utils import call_claude

SYSTEM = Path(__file__).resolve().parent.parent.joinpath("prompts/summarize.txt").read_text()

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
