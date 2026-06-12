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
