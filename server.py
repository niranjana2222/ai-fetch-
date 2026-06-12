"""Web UI for the ai-fetch digest pipeline.

Run:  .venv/bin/python server.py   →  http://127.0.0.1:5050
"""
import json
import threading
import traceback
from datetime import datetime
from pathlib import Path

import markdown as md_lib
from flask import Flask, jsonify, render_template

from graph import build_graph

DIGEST_DIR = Path(__file__).resolve().parent / "digests"
DIGEST_DIR.mkdir(exist_ok=True)

STAGES = ["fetch", "categorize", "summarize", "report"]

app = Flask(__name__)

_lock = threading.Lock()
_state = {
    "running": False,
    "stage": None,
    "done": [],
    "error": None,
    "started_at": None,
    "finished_at": None,
    "counts": {},
}


def _latest_digest_path(suffix="json"):
    files = sorted(DIGEST_DIR.glob(f"digest-*.{suffix}"))
    return files[-1] if files else None


def _run_pipeline():
    graph = build_graph()
    initial = {"raw_items": [], "categorized_items": [],
               "enriched_items": [], "report_markdown": ""}
    try:
        report_md, sections, meta = "", [], {}
        for chunk in graph.stream(initial):
            for node, out in chunk.items():
                with _lock:
                    _state["done"].append(node)
                    nxt = STAGES.index(node) + 1 if node in STAGES else len(STAGES)
                    _state["stage"] = STAGES[nxt] if nxt < len(STAGES) else None
                    if node == "fetch":
                        _state["counts"]["fetched"] = len(out.get("raw_items", []))
                    elif node == "categorize":
                        _state["counts"]["categorized"] = len(out.get("categorized_items", []))
                    elif node == "summarize":
                        _state["counts"]["summarized"] = len(out.get("enriched_items", []))
                if node == "report":
                    report_md = out.get("report_markdown", "")
                    sections = out.get("report_sections", [])
                    meta = out.get("report_meta", {})

        stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        (DIGEST_DIR / f"digest-{stamp}.md").write_text(report_md)
        (DIGEST_DIR / f"digest-{stamp}.json").write_text(
            json.dumps({"sections": sections, "meta": meta}))
        with _lock:
            _state["finished_at"] = datetime.now().isoformat(timespec="seconds")
    except Exception:
        with _lock:
            _state["error"] = traceback.format_exc(limit=3)
    finally:
        with _lock:
            _state["running"] = False
            _state["stage"] = None


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/run")
def run():
    with _lock:
        if _state["running"]:
            return jsonify({"ok": False, "reason": "already running"}), 409
        _state.update(running=True, stage="fetch", done=[], error=None,
                      counts={}, finished_at=None,
                      started_at=datetime.now().isoformat(timespec="seconds"))
    threading.Thread(target=_run_pipeline, daemon=True).start()
    return jsonify({"ok": True})


@app.get("/api/status")
def status():
    with _lock:
        return jsonify(dict(_state))


@app.get("/api/report")
def report():
    path = _latest_digest_path("json")
    if path:
        data = json.loads(path.read_text())
        generated = datetime.fromtimestamp(path.stat().st_mtime).strftime("%B %d, %Y · %H:%M")
        return jsonify({**data, "generated_at": generated, "file": path.name})

    # legacy markdown-only editions
    path = _latest_digest_path("md")
    if not path:
        return jsonify({"sections": None, "html": None, "generated_at": None})
    html = md_lib.markdown(path.read_text(), extensions=["tables", "toc"])
    generated = datetime.fromtimestamp(path.stat().st_mtime).strftime("%B %d, %Y · %H:%M")
    return jsonify({"sections": None, "html": html, "generated_at": generated, "file": path.name})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
