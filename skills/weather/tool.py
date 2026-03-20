from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# WMO Weather interpretation codes → Korean description
_WMO_CODES: dict[int, str] = {
    0: "맑음", 1: "대체로 맑음", 2: "부분적으로 흐림", 3: "흐림",
    45: "안개", 48: "안개(서리)",
    51: "이슬비(약)", 53: "이슬비(보통)", 55: "이슬비(강)",
    61: "비(약)", 63: "비(보통)", 65: "비(강)",
    71: "눈(약)", 73: "눈(보통)", 75: "눈(강)", 77: "싸락눈",
    80: "소나기(약)", 81: "소나기(보통)", 82: "소나기(강)",
    85: "눈소나기(약)", 86: "눈소나기(강)",
    95: "뇌우", 96: "뇌우+우박(약)", 99: "뇌우+우박(강)",
}


# Open-Meteo geocoding API indexes cities by their English/local names.
# Korean city names must be transliterated before querying.
_KO_TO_EN: dict[str, str] = {
    "서울": "Seoul", "부산": "Busan", "인천": "Incheon", "대구": "Daegu",
    "대전": "Daejeon", "광주": "Gwangju", "울산": "Ulsan", "수원": "Suwon",
    "성남": "Seongnam", "고양": "Goyang", "용인": "Yongin", "창원": "Changwon",
    "청주": "Cheongju", "전주": "Jeonju", "천안": "Cheonan", "안산": "Ansan",
    "안양": "Anyang", "남양주": "Namyangju", "화성": "Hwaseong",
    "평택": "Pyeongtaek", "의정부": "Uijeongbu", "시흥": "Siheung",
    "파주": "Paju", "김포": "Gimpo", "광명": "Gwangmyeong",
    "하남": "Hanam", "군포": "Gunpo", "오산": "Osan", "이천": "Icheon",
    "양주": "Yangju", "구리": "Guri", "안성": "Anseong", "포천": "Pocheon",
    "제주": "Jeju", "제주도": "Jeju", "강릉": "Gangneung", "춘천": "Chuncheon",
    "원주": "Wonju", "속초": "Sokcho", "동해": "Donghae",
    "포항": "Pohang", "경주": "Gyeongju", "구미": "Gumi", "안동": "Andong",
    "진주": "Jinju", "거제": "Geoje", "통영": "Tongyeong",
    "목포": "Mokpo", "여수": "Yeosu", "순천": "Suncheon", "익산": "Iksan",
    "군산": "Gunsan", "정읍": "Jeongeup",
    "평양": "Pyongyang", "도쿄": "Tokyo", "오사카": "Osaka", "베이징": "Beijing",
    "상하이": "Shanghai", "뉴욕": "New York", "런던": "London", "파리": "Paris",
}


def _geocode(city: str) -> tuple[float, float, str]:
    """Return (lat, lon, resolved_name) for a city name via Open-Meteo geocoding.

    Tries Korean→English mapping first, then falls back to querying as-is.
    """
    query = _KO_TO_EN.get(city, city)

    def _query(name: str) -> list:
        url = (
            "https://geocoding-api.open-meteo.com/v1/search?"
            + urllib.parse.urlencode({"name": name, "count": 1, "format": "json"})
        )
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read()).get("results") or []

    results = _query(query)

    # If mapped name also fails, try the original input as a last resort
    if not results and query != city:
        results = _query(city)

    if not results:
        raise ValueError(f"'{city}' 위치를 찾을 수 없습니다. 영문 도시명으로 시도해 보세요.")

    r = results[0]
    name = r.get("name", query)
    country = r.get("country", "")
    return r["latitude"], r["longitude"], f"{name}, {country}"


@tool
def weather_current(city: str) -> str:
    """Get the current weather conditions for a given city.
    Uses Open-Meteo (free, no API key required).
    Args:
        city: City name in Korean or English (e.g. '서울', 'Tokyo', 'New York')
    """
    try:
        lat, lon, resolved = _geocode(city)

        params = urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,weathercode,windspeed_10m,relativehumidity_2m",
            "timezone": "Asia/Seoul",
        })
        url = f"https://api.open-meteo.com/v1/forecast?{params}"

        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())

        cur = data["current"]
        code = cur.get("weathercode", 0)
        condition = _WMO_CODES.get(code, f"코드 {code}")

        return (
            f"📍 {resolved} 현재 날씨\n"
            f"🌤 날씨: {condition}\n"
            f"🌡 기온: {cur['temperature_2m']}°C (체감 {cur['apparent_temperature']}°C)\n"
            f"💧 습도: {cur['relativehumidity_2m']}%\n"
            f"💨 풍속: {cur['windspeed_10m']} km/h"
        )
    except Exception as e:
        logger.error("weather_current failed: %s", e, exc_info=True)
        return f"날씨 조회 중 오류가 발생했습니다: {e}"


@tool
def weather_forecast(city: str, days: int = 3) -> str:
    """Get a weather forecast for the next N days for a given city.
    Uses Open-Meteo (free, no API key required).
    Args:
        city: City name in Korean or English (e.g. '서울', 'Tokyo', 'New York')
        days: Number of forecast days (1–7, default: 3)
    """
    try:
        days = max(1, min(days, 7))
        lat, lon, resolved = _geocode(city)

        params = urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "Asia/Seoul",
            "forecast_days": days,
        })
        url = f"https://api.open-meteo.com/v1/forecast?{params}"

        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())

        daily = data["daily"]
        lines = [f"📍 {resolved} {days}일 예보"]
        for i in range(days):
            code = daily["weathercode"][i]
            condition = _WMO_CODES.get(code, f"코드 {code}")
            lines.append(
                f"- {daily['time'][i]}: {condition} "
                f"최고 {daily['temperature_2m_max'][i]}°C / "
                f"최저 {daily['temperature_2m_min'][i]}°C "
                f"강수 {daily['precipitation_sum'][i]}mm"
            )

        return "\n".join(lines)
    except Exception as e:
        logger.error("weather_forecast failed: %s", e, exc_info=True)
        return f"날씨 예보 조회 중 오류가 발생했습니다: {e}"


def get_weather_tools() -> list:
    """Return all weather tools for agent binding."""
    return [weather_current, weather_forecast]
