from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _nominatim_request(url: str) -> list | dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": "OpenChiken/1.0 (https://github.com/openchiken)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


@tool
def geocode_address(address: str) -> str:
    """Convert an address or place name to latitude/longitude coordinates.
    Uses OpenStreetMap Nominatim (free, no API key required).
    Args:
        address: Address or place name (e.g. '서울 강남구', 'Tokyo Tower', '1600 Pennsylvania Ave')
    """
    try:
        params = urllib.parse.urlencode({
            "q": address,
            "format": "jsonv2",
            "limit": 3,
            "accept-language": "ko,en",
        })
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        results = _nominatim_request(url)

        if not results:
            return f"'{address}'에 대한 위치 정보를 찾을 수 없습니다."

        lines = [f"📍 '{address}' 검색 결과"]
        for r in results:
            name = r.get("display_name", "")
            lat = r.get("lat", "")
            lon = r.get("lon", "")
            cat = r.get("category", "")
            lines.append(f"- {name}\n  좌표: ({lat}, {lon}) [{cat}]")

        return "\n".join(lines)
    except Exception as e:
        logger.error("geocode_address failed: %s", e, exc_info=True)
        return f"지오코딩 실패: {e}"


@tool
def geocode_reverse(latitude: float, longitude: float) -> str:
    """Convert latitude/longitude coordinates to an address.
    Uses OpenStreetMap Nominatim (free, no API key required).
    Args:
        latitude: Latitude value (e.g. 37.5665)
        longitude: Longitude value (e.g. 126.9780)
    """
    try:
        params = urllib.parse.urlencode({
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "accept-language": "ko,en",
        })
        url = f"https://nominatim.openstreetmap.org/reverse?{params}"
        result = _nominatim_request(url)

        name = result.get("display_name", "주소 없음")
        addr = result.get("address", {})
        country = addr.get("country", "")
        city = addr.get("city", addr.get("town", addr.get("village", "")))

        return (
            f"📍 역지오코딩 결과\n"
            f"좌표: ({latitude}, {longitude})\n"
            f"주소: {name}\n"
            f"도시: {city}, {country}"
        )
    except Exception as e:
        logger.error("geocode_reverse failed: %s", e, exc_info=True)
        return f"역지오코딩 실패: {e}"


def get_tools() -> list:
    return [geocode_address, geocode_reverse]
