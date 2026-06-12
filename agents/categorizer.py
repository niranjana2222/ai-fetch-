import json
from pathlib import Path
from config import CATEGORIES
from utils import call_claude

SYSTEM = Path(__file__).resolve().parent.parent.joinpath("prompts/categorize.txt").read_text()

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
