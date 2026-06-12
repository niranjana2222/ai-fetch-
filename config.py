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
