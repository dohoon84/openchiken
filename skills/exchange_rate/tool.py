from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_CURRENCY_ALIASES: dict[str, str] = {
    "달러": "USD", "미국달러": "USD", "dollar": "USD",
    "원": "KRW", "한국원": "KRW", "won": "KRW",
    "유로": "EUR", "euro": "EUR",
    "엔": "JPY", "엔화": "JPY", "yen": "JPY",
    "파운드": "GBP", "pound": "GBP",
    "위안": "CNY", "위안화": "CNY", "yuan": "CNY",
}


def _resolve_currency(code: str) -> str:
    c = code.strip()
    return _CURRENCY_ALIASES.get(c.lower(), c.upper())


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "OpenChiken/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


@tool
def exchange_rate_lookup(base: str = "USD", target: str = "KRW") -> str:
    """Look up the current exchange rate between two currencies.
    Uses Frankfurter API (free, no API key required).
    Args:
        base: Base currency code or name (e.g. 'USD', '달러')
        target: Target currency code or name (e.g. 'KRW', '원')
    """
    try:
        b = _resolve_currency(base)
        t = _resolve_currency(target)
        url = f"https://api.frankfurter.app/latest?from={b}&to={t}"
        data = _fetch_json(url)

        rate = data.get("rates", {}).get(t)
        if rate is None:
            return f"'{b}' → '{t}' 환율을 찾을 수 없습니다."

        date = data.get("date", "")
        return (
            f"💱 환율 정보 ({date})\n"
            f"1 {b} = {rate:,.4f} {t}"
        )
    except Exception as e:
        logger.error("exchange_rate_lookup failed: %s", e, exc_info=True)
        return f"환율 조회 실패: {e}"


@tool
def exchange_rate_convert(amount: float, base: str = "USD", target: str = "KRW") -> str:
    """Convert an amount from one currency to another.
    Uses Frankfurter API (free, no API key required).
    Args:
        amount: Amount to convert
        base: Source currency code or name (e.g. 'USD', '달러')
        target: Target currency code or name (e.g. 'KRW', '원')
    """
    try:
        b = _resolve_currency(base)
        t = _resolve_currency(target)
        params = urllib.parse.urlencode({"from": b, "to": t, "amount": amount})
        url = f"https://api.frankfurter.app/latest?{params}"
        data = _fetch_json(url)

        converted = data.get("rates", {}).get(t)
        if converted is None:
            return f"변환 실패: '{b}' → '{t}'"

        return (
            f"💱 통화 변환 결과\n"
            f"{amount:,.2f} {b} = {converted:,.2f} {t}"
        )
    except Exception as e:
        logger.error("exchange_rate_convert failed: %s", e, exc_info=True)
        return f"통화 변환 실패: {e}"


def get_tools() -> list:
    return [exchange_rate_lookup, exchange_rate_convert]
