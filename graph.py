from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any

from agents.fetcher      import fetch_papers
from agents.categorizer  import categorize_items
from agents.summarizer   import summarize_items
from agents.reporter     import build_report

class DigestState(TypedDict):
    raw_items:         List[Dict[str, Any]]
    categorized_items: List[Dict[str, Any]]
    enriched_items:    List[Dict[str, Any]]
    report_markdown:   str

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
