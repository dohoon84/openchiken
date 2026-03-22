from __future__ import annotations

import json
import logging
import urllib.request

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_HN_BASE = "https://hacker-news.firebaseio.com/v0"


def _fetch_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": "OpenChiken/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


@tool
def hacker_news_top(count: int = 10) -> str:
    """Get top stories from Hacker News.
    Uses the official HN Firebase API (free, no API key required).
    Args:
        count: Number of stories to return (1-30, default: 10)
    """
    try:
        count = max(1, min(count, 30))
        ids = _fetch_json(f"{_HN_BASE}/topstories.json")[:count]

        lines = [f"🔥 HackerNews TOP {count}"]
        for i, story_id in enumerate(ids, 1):
            story = _fetch_json(f"{_HN_BASE}/item/{story_id}.json")
            title = story.get("title", "(제목 없음)")
            url = story.get("url", f"https://news.ycombinator.com/item?id={story_id}")
            score = story.get("score", 0)
            comments = story.get("descendants", 0)
            lines.append(f"{i}. [{score}pts, {comments}comments] {title}\n   {url}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("hacker_news_top failed: %s", e, exc_info=True)
        return f"HackerNews 조회 실패: {e}"


def get_tools() -> list:
    return [hacker_news_top]
