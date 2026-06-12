import json
from pathlib import Path
from utils import call_claude

SYSTEM = Path(__file__).resolve().parent.parent.joinpath("prompts/summarize.txt").read_text()

BATCH_SIZE = 8

FALLBACK = {"summary": "", "method": "", "discussion": "", "score": 5, "diagram": ""}


def summarize_items(state: dict) -> dict:
    items = state["categorized_items"]
    enriched = []

    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i : i + BATCH_SIZE]
        items_text = "\n\n".join(
            f"[{j}] {item['title']}\n{item['abstract']}"
            for j, item in enumerate(batch)
        )

        prompt = (
            "For each item write:\n"
            '  "summary":    1-2 short sentences — what it does and why it matters\n'
            '  "method":     1-2 short sentences — the core technique or approach\n'
            '  "discussion": 1-2 short sentences — limitations and future research directions\n'
            '  "score":      significance 1-10 (10 = major breakthrough)\n'
            '  "diagram":    a small mermaid flowchart sketching the system architecture or\n'
            "                data flow. Rules: start with 'flowchart LR', 4-7 nodes, labels in\n"
            "                square brackets, plain alphanumeric labels only (no parentheses,\n"
            "                quotes or special characters), no styling directives.\n\n"
            f"Items:\n{items_text}\n\n"
            "Return ONLY a JSON array:\n"
            '[{"index": 0, "summary": "...", "method": "...", "discussion": "...", '
            '"score": 7, "diagram": "flowchart LR\\n  A[Input] --> B[Encoder]\\n  B --> C[Decoder]"}, ...]'
        )

        try:
            raw = call_claude(prompt, system=SYSTEM)
            data = json.loads(raw)
            by_index = {d["index"]: d for d in data}
            for j, item in enumerate(batch):
                d = {**FALLBACK, **by_index.get(j, {})}
                enriched.append({
                    **item,
                    "summary":      d["summary"] or item["abstract"][:200],
                    "method":       d["method"],
                    "discussion":   d["discussion"],
                    "significance": d["score"],
                    "diagram":      d["diagram"],
                })
        except Exception as e:
            print(f"[Summarizer] batch {i} error: {e} — using raw abstracts")
            for item in batch:
                enriched.append({**item, **FALLBACK,
                                 "summary": item["abstract"][:200],
                                 "significance": 5})

    print(f"[Summarizer] {len(enriched)} items scored")
    return {**state, "enriched_items": enriched}
