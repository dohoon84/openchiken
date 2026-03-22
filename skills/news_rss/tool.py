from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_FEED_PRESETS: dict[str, str] = {
    "bbc": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "reuters": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best",
    "cnn": "http://rss.cnn.com/rss/edition.rss",
    "techcrunch": "https://techcrunch.com/feed/",
    "hackernews": "https://hnrss.org/frontpage",
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "nyt": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
}


def _fetch_rss_json(feed_url: str) -> dict:
    api_url = "https://api.rss2json.com/v1/api.json?" + urllib.parse.urlencode({
        "rss_url": feed_url,
    })
    req = urllib.request.Request(api_url, headers={"User-Agent": "OpenChiken/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


@tool
def news_rss_fetch(source: str = "bbc", count: int = 5) -> str:
    """Fetch latest news headlines from an RSS feed.
    Uses rss2json free API (no API key required).
    Args:
        source: Feed preset name (bbc, reuters, cnn, techcrunch, hackernews, coindesk, nyt) or direct RSS URL
        count: Number of articles to return (1-20, default: 5)
    """
    try:
        count = max(1, min(count, 20))
        feed_url = _FEED_PRESETS.get(source.lower().strip(), source)

        data = _fetch_rss_json(feed_url)
        if data.get("status") != "ok":
            return f"RSS 피드 조회 실패: {data.get('message', 'unknown error')}"

        feed_title = data.get("feed", {}).get("title", source)
        items = data.get("items", [])[:count]

        if not items:
            return f"'{source}' 피드에서 기사를 찾을 수 없습니다."

        lines = [f"📰 {feed_title} — 최신 {len(items)}건"]
        for i, item in enumerate(items, 1):
            title = item.get("title", "(제목 없음)")
            pub = item.get("pubDate", "")[:10]
            link = item.get("link", "")
            lines.append(f"{i}. [{pub}] {title}\n   {link}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("news_rss_fetch failed: %s", e, exc_info=True)
        return f"뉴스 피드 조회 실패: {e}"


def get_tools() -> list:
    return [news_rss_fetch]
