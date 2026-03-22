from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_COIN_ALIASES: dict[str, str] = {
    "btc": "bitcoin", "비트코인": "bitcoin",
    "eth": "ethereum", "이더리움": "ethereum",
    "xrp": "ripple", "리플": "ripple",
    "sol": "solana", "솔라나": "solana",
    "ada": "cardano", "카르다노": "cardano",
    "doge": "dogecoin", "도지코인": "dogecoin",
    "dot": "polkadot", "폴카닷": "polkadot",
    "avax": "avalanche-2", "아발란체": "avalanche-2",
    "matic": "matic-network", "폴리곤": "matic-network",
    "link": "chainlink", "체인링크": "chainlink",
}


def _resolve_coin_id(query: str) -> str:
    q = query.strip().lower()
    return _COIN_ALIASES.get(q, q)


def _fetch_json(url: str, timeout: int = 10) -> dict | list:
    req = urllib.request.Request(url, headers={
        "User-Agent": "OpenChiken/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


@tool
def crypto_price_lookup(coin: str) -> str:
    """Look up current cryptocurrency price, market cap, and 24h change.
    Uses CoinGecko free API (no API key required).
    Args:
        coin: Coin name or symbol (e.g. 'bitcoin', 'btc', '비트코인', 'ethereum')
    """
    try:
        coin_id = _resolve_coin_id(coin)
        params = urllib.parse.urlencode({
            "ids": coin_id,
            "vs_currencies": "usd,krw",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        })
        url = f"https://api.coingecko.com/api/v3/simple/price?{params}"
        data = _fetch_json(url)

        if coin_id not in data:
            return f"'{coin}' 코인을 찾을 수 없습니다. 영문 이름으로 시도해 보세요."

        info = data[coin_id]
        usd = info.get("usd", 0)
        krw = info.get("krw", 0)
        change = info.get("usd_24h_change", 0)
        mcap = info.get("usd_market_cap", 0)
        vol = info.get("usd_24h_vol", 0)

        sign = "+" if change >= 0 else ""
        return (
            f"💰 {coin_id.upper()} 현재 시세\n"
            f"💵 USD: ${usd:,.2f}\n"
            f"🇰🇷 KRW: ₩{krw:,.0f}\n"
            f"📊 24h 변동: {sign}{change:.2f}%\n"
            f"🏦 시가총액: ${mcap:,.0f}\n"
            f"📈 24h 거래량: ${vol:,.0f}"
        )
    except Exception as e:
        logger.error("crypto_price_lookup failed: %s", e, exc_info=True)
        return f"암호화폐 시세 조회 실패: {e}"


@tool
def crypto_market_top(count: int = 10) -> str:
    """Get top N cryptocurrencies by market cap.
    Uses CoinGecko free API (no API key required).
    Args:
        count: Number of coins to return (1-50, default: 10)
    """
    try:
        count = max(1, min(count, 50))
        params = urllib.parse.urlencode({
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": count,
            "page": 1,
            "sparkline": "false",
        })
        url = f"https://api.coingecko.com/api/v3/coins/markets?{params}"
        data = _fetch_json(url)

        lines = [f"📊 시총 TOP {count} 암호화폐"]
        for i, coin in enumerate(data, 1):
            name = coin.get("name", "?")
            symbol = coin.get("symbol", "?").upper()
            price = coin.get("current_price", 0)
            change = coin.get("price_change_percentage_24h", 0) or 0
            sign = "+" if change >= 0 else ""
            lines.append(f"{i}. {name} ({symbol}): ${price:,.2f} ({sign}{change:.1f}%)")

        return "\n".join(lines)
    except Exception as e:
        logger.error("crypto_market_top failed: %s", e, exc_info=True)
        return f"시장 데이터 조회 실패: {e}"


def get_tools() -> list:
    return [crypto_price_lookup, crypto_market_top]
