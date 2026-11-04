RSS_SOURCES = [
    {
        "id": "openai_news",
        "name": "OpenAI",
        "url": "https://openai.com/news/rss.xml",
        "category": "AI",
        "max_items": 8,
    },
    {
        "id": "google_deepmind",
        "name": "Google DeepMind",
        "url": "https://deepmind.google/blog/rss.xml",
        "category": "AI Research",
        "max_items": 8,
    },
    {
        "id": "huggingface",
        "name": "Hugging Face",
        "url": "https://huggingface.co/blog/feed.xml",
        "category": "Open Source AI",
        "max_items": 8,
    },
    {
        "id": "arxiv_ai",
        "name": "arXiv",
        "url": "https://rss.arxiv.org/rss/cs.AI+cs.LG+cs.CL",
        "category": "AI Research",
        "max_items": 12,
    },
]

HACKER_NEWS_CONFIG = {
    "name": "Hacker News",
    "top_stories_limit": 15,
    "category": "Developer Community",
}

DEFAULT_LOOKBACK_HOURS = 36

HTTP_TIMEOUT = 20
USER_AGENT = "TechIntelligence/0.1 (personal research project)"