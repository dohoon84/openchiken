from __future__ import annotations

import logging
import time

from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 1.5


def _create_wrapper() -> DuckDuckGoSearchAPIWrapper:
    return DuckDuckGoSearchAPIWrapper(max_results=10, region="kr-kr", time="y")


def _search_with_retry(query: str) -> str:
    """DuckDuckGo 검색을 재시도 로직과 함께 실행합니다."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            wrapper = _create_wrapper()
            results = wrapper.results(query, max_results=10)
            if not results:
                logger.warning("web_search: empty results on attempt %d for query '%s'", attempt + 1, query)
                time.sleep(_RETRY_DELAY)
                continue
            snippets = [r.get("snippet", "") for r in results if r.get("snippet")]
            if not snippets:
                time.sleep(_RETRY_DELAY)
                continue
            return "\n\n".join(snippets)
        except Exception as e:
            last_exc = e
            logger.warning("web_search attempt %d/%d failed: %s", attempt + 1, _MAX_RETRIES, e)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY * (attempt + 1))

    if last_exc:
        raise last_exc
    return ""


@tool
def web_search(query: str) -> str:
    """Search the web for current information using DuckDuckGo.
    Use this when you need up-to-date information that may not be in your training data,
    such as recent news, current events, product info, or any factual question.
    Do NOT use this for real-time stock prices, cryptocurrency prices, or financial indices
    — use finance_search instead for accurate real-time financial data.
    Args:
        query: The search query in natural language (Korean or English)
    """
    try:
        result = _search_with_retry(query)
        return result if result else "검색 결과를 찾을 수 없습니다. 다른 검색어로 다시 시도해 보세요."
    except Exception as e:
        logger.error("web_search failed: %s", e, exc_info=True)
        return f"웹 검색 중 오류가 발생했습니다: {e}"


def get_tools() -> list:
    """Return all web search tools for agent binding."""
    return [web_search]


def get_web_search_tools() -> list:
    return get_tools()
