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
        try:
            for r in client.results(arxiv.Search(query=query, max_results=per_cat,
                                                  sort_by=arxiv.SortCriterion.SubmittedDate)):
                items.append({
                    "title":    r.title,
                    "abstract": r.summary[:800],
                    "url":      r.entry_id,
                    "source":   "arXiv",
                    "authors":  [a.name for a in r.authors[:3]],
                })
        except Exception as e:
            print(f"[Fetcher] arXiv {cat} error: {e}")

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
