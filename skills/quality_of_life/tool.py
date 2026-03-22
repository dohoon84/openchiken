from __future__ import annotations

import json
import logging
import urllib.request

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _fetch_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={
        "User-Agent": "OpenChiken/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _find_urban_area(city: str) -> tuple[str, str] | None:
    """도시 이름으로 Teleport urban area를 검색합니다."""
    url = f"https://api.teleport.org/api/urban_areas/?search={city}"
    try:
        data = _fetch_json(url)
        results = data.get("_embedded", {}).get("city:search-results", [])
        if not results:
            return None
        match = results[0]
        name = match.get("matching_full_name", city)
        ua_link = (
            match.get("_links", {})
            .get("city:item", {})
            .get("href", "")
        )
        if not ua_link:
            return None
        city_data = _fetch_json(ua_link)
        ua_href = (
            city_data.get("_links", {})
            .get("city:urban_area", {})
            .get("href")
        )
        if not ua_href:
            return None
        return name, ua_href
    except Exception:
        return None


@tool
def quality_of_life_score(city: str) -> str:
    """Get quality of life scores for a city from Teleport API.
    Covers 17 categories: housing, cost of living, safety, healthcare, education, etc.
    Args:
        city: City name in English (e.g. 'Seoul', 'Tokyo', 'San Francisco')
    """
    try:
        result = _find_urban_area(city)
        if result is None:
            return (
                f"'{city}'에 대한 삶의 질 데이터를 찾을 수 없습니다. "
                "영문 대도시 이름으로 시도해 보세요 (예: Seoul, Tokyo, New York)."
            )

        name, ua_href = result
        scores_url = ua_href.rstrip("/") + "/scores/"
        data = _fetch_json(scores_url)

        summary = data.get("summary", "")
        overall = data.get("teleport_city_score", 0)
        categories = data.get("categories", [])

        lines = [
            f"🏙 {name} 삶의 질 점수",
            f"⭐ 종합 점수: {overall:.1f}/100",
            "",
        ]

        for cat in categories:
            cat_name = cat.get("name", "")
            score = cat.get("score_out_of_10", 0)
            bar = "█" * int(score) + "░" * (10 - int(score))
            lines.append(f"  {cat_name}: {bar} {score:.1f}/10")

        if summary:
            clean = summary.replace("<p>", "").replace("</p>", "\n").replace("<b>", "").replace("</b>", "")
            lines.append(f"\n📝 요약: {clean[:300]}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("quality_of_life_score failed: %s", e, exc_info=True)
        return f"삶의 질 조회 실패: {e}"


def get_tools() -> list:
    return [quality_of_life_score]
