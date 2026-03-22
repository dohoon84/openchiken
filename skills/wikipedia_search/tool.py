from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "OpenChiken/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _is_korean(text: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in text)


@tool
def wikipedia_summary(query: str) -> str:
    """Search Wikipedia and return a summary of the most relevant article.
    Supports Korean and English. Uses Wikipedia REST API (free, no API key).
    Args:
        query: Search keyword (e.g. '비트코인', 'Artificial Intelligence', '서울')
    """
    try:
        lang = "ko" if _is_korean(query) else "en"
        encoded = urllib.parse.quote(query)
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{encoded}"

        try:
            data = _fetch_json(url)
        except urllib.error.HTTPError:
            search_url = (
                f"https://{lang}.wikipedia.org/w/api.php?"
                + urllib.parse.urlencode({
                    "action": "opensearch",
                    "search": query,
                    "limit": 1,
                    "format": "json",
                })
            )
            search_data = _fetch_json(search_url)
            titles = search_data[1] if len(search_data) > 1 else []
            if not titles:
                return f"'{query}'에 대한 위키피디아 문서를 찾을 수 없습니다."
            encoded = urllib.parse.quote(titles[0])
            url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{encoded}"
            data = _fetch_json(url)

        title = data.get("title", query)
        extract = data.get("extract", "내용 없음")
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")

        return (
            f"📖 {title}\n\n"
            f"{extract[:500]}\n\n"
            f"🔗 {page_url}"
        )
    except Exception as e:
        logger.error("wikipedia_summary failed: %s", e, exc_info=True)
        return f"위키피디아 검색 실패: {e}"


def get_tools() -> list:
    return [wikipedia_summary]
