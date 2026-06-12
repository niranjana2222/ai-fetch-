import re
from collections import defaultdict
from datetime import date
from config import CATEGORIES

ARXIV_ID = re.compile(r"(\d{4}\.\d{4,5})")


def alphaxiv_url(url: str):
    """arXiv and HF paper URLs carry an arXiv id — map them to alphaXiv."""
    if "arxiv.org" in url or "huggingface.co/papers" in url:
        m = ARXIV_ID.search(url)
        if m:
            return f"https://www.alphaxiv.org/abs/{m.group(1)}"
    return None


def build_report(state: dict) -> dict:
    items  = state["enriched_items"]
    today  = date.today().strftime("%B %d, %Y")

    by_cat = defaultdict(list)
    for item in items:
        by_cat[item["category"]].append(item)

    sections = []
    for cat in CATEGORIES:
        cat_items = sorted(by_cat.get(cat, []),
                           key=lambda x: x["significance"], reverse=True)[:5]
        if not cat_items:
            continue
        sections.append({
            "category": cat,
            "items": [{**it, "alphaxiv": alphaxiv_url(it["url"])} for it in cat_items],
        })

    # Markdown version (for email delivery) — no emojis
    lines = [
        f"# AI Research Digest — {today}\n",
        f"*{len(items)} papers reviewed · {len(sections)} active categories*\n",
        "---\n",
    ]
    for sec in sections:
        lines.append(f"## {sec['category']}\n")
        for item in sec["items"]:
            lines.append(f"### [{item['title']}]({item['url']})")
            if item["authors"]:
                lines.append(f"*{', '.join(item['authors'][:3])}*")
            lines.append(f"\n{item['summary']}\n")
            if item.get("method"):
                lines.append(f"**Method:** {item['method']}\n")
            if item.get("discussion"):
                lines.append(f"**Discussion:** {item['discussion']}\n")
            tail = f"*Source: {item['source']} | Significance: {item['significance']}/10*"
            if item.get("alphaxiv"):
                tail += f" · [Read on alphaXiv]({item['alphaxiv']})"
            lines.append(tail + "\n")
            lines.append("---\n")

    report = "\n".join(lines)
    meta = {"date": today, "reviewed": len(items), "categories": len(sections)}
    print(f"[Reporter] Digest built ({len(report)} chars, {len(sections)} sections)")
    return {**state, "report_markdown": report,
            "report_sections": sections, "report_meta": meta}
