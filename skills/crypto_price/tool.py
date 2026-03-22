from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_COIN_ALIASES: dict[str, str] = {
    # ── Bitcoin 계열 ──────────────────────────────────────────
    "btc": "bitcoin", "비트코인": "bitcoin",
    "bch": "bitcoin-cash", "비트코인캐시": "bitcoin-cash",
    "bsv": "bitcoin-sv", "비트코인sv": "bitcoin-sv",
    "btg": "bitcoin-gold", "비트코인골드": "bitcoin-gold",
    "wbtc": "wrapped-bitcoin", "래핑비트코인": "wrapped-bitcoin",

    # ── Ethereum 계열 ─────────────────────────────────────────
    "eth": "ethereum", "이더리움": "ethereum",
    "etc": "ethereum-classic", "이더리움클래식": "ethereum-classic",
    "steth": "staked-ether", "스테이킹이더": "staked-ether",

    # ── 주요 알트코인 ─────────────────────────────────────────
    "xrp": "ripple", "리플": "ripple",
    "sol": "solana", "솔라나": "solana",
    "ada": "cardano", "카르다노": "cardano", "에이다": "cardano",
    "doge": "dogecoin", "도지코인": "dogecoin", "도지": "dogecoin",
    "dot": "polkadot", "폴카닷": "polkadot",
    "avax": "avalanche-2", "아발란체": "avalanche-2",
    "matic": "matic-network", "폴리곤": "matic-network", "polygon": "matic-network",
    "link": "chainlink", "체인링크": "chainlink",
    "uni": "uniswap", "유니스왑": "uniswap",
    "aave": "aave", "에이브": "aave",
    "atom": "cosmos", "코스모스": "cosmos",
    "near": "near", "니어": "near",
    "apt": "aptos", "앱토스": "aptos",
    "sui": "sui", "수이": "sui",
    "arb": "arbitrum", "아비트럼": "arbitrum",
    "op": "optimism", "옵티미즘": "optimism",
    "algo": "algorand", "알고랜드": "algorand",
    "xlm": "stellar", "스텔라": "stellar", "스텔라루멘": "stellar",
    "vet": "vechain", "비체인": "vechain",
    "fil": "filecoin", "파일코인": "filecoin",
    "icp": "internet-computer", "인터넷컴퓨터": "internet-computer",
    "trx": "tron", "트론": "tron",
    "ltc": "litecoin", "라이트코인": "litecoin",
    "shib": "shiba-inu", "시바이누": "shiba-inu", "시바": "shiba-inu",
    "pepe": "pepe", "페페": "pepe",
    "floki": "floki", "플로키": "floki",
    "bonk": "bonk", "봉크": "bonk",

    # ── DeFi ──────────────────────────────────────────────────
    "mkr": "maker", "메이커": "maker",
    "snx": "havven", "신세틱스": "havven",
    "crv": "curve-dao-token", "커브": "curve-dao-token",
    "comp": "compound-governance-token", "컴파운드": "compound-governance-token",
    "1inch": "1inch", "원인치": "1inch",
    "bal": "balancer", "밸런서": "balancer",
    "sushi": "sushi", "스시": "sushi",
    "cake": "pancakeswap-token", "팬케이크": "pancakeswap-token",
    "ray": "raydium", "레이디움": "raydium",
    "jup": "jupiter-exchange-solana", "주피터": "jupiter-exchange-solana",

    # ── Layer 1 / 2 ───────────────────────────────────────────
    "bnb": "binancecoin", "바이낸스코인": "binancecoin",
    "ton": "the-open-network", "톤": "the-open-network",
    "hbar": "hedera-hashgraph", "헤데라": "hedera-hashgraph",
    "egld": "elrond-erd-2", "멀티버스엑스": "elrond-erd-2", "mx": "elrond-erd-2",
    "ftm": "fantom", "팬텀": "fantom",
    "one": "harmony", "하모니": "harmony",
    "zil": "zilliqa", "질리카": "zilliqa",
    "neo": "neo", "네오": "neo",
    "waves": "waves", "웨이브스": "waves",
    "klay": "klay-token", "클레이튼": "klay-token", "클레이": "klay-token",

    # ── 한국 관련 코인 ────────────────────────────────────────
    "aergo": "aergo", "아르고": "aergo",
    "bora": "bora", "보라": "bora",
    "wemix": "wemix-token", "위믹스": "wemix-token",
    "mvl": "mass-vehicle-ledger", "엠블": "mass-vehicle-ledger",
    "meta": "metadium", "메타디움": "metadium",
    "temco": "temco", "템코": "temco",
    "apis": "apis-token", "에이피아이에스": "apis-token",

    # ── 스테이블코인 ──────────────────────────────────────────
    "usdt": "tether", "테더": "tether",
    "usdc": "usd-coin", "유에스디코인": "usd-coin",
    "dai": "dai", "다이": "dai",
    "busd": "binance-usd", "바이낸스달러": "binance-usd",

    # ── 거래소 토큰 ───────────────────────────────────────────
    "okb": "okb", "오케이비": "okb",
    "ht": "huobi-token", "후오비토큰": "huobi-token",
    "cro": "crypto-com-chain", "크로노스": "crypto-com-chain",
    "ftt": "ftx-token", "에프티엑스": "ftx-token",

    # ── 기타 주요 코인 ────────────────────────────────────────
    "xmr": "monero", "모네로": "monero",
    "zec": "zcash", "지캐시": "zcash",
    "dcr": "decred", "디크레드": "decred",
    "xtz": "tezos", "테조스": "tezos",
    "eos": "eos", "이오스": "eos",
    "xem": "nem", "넴": "nem",
    "iota": "iota", "아이오타": "iota",
    "theta": "theta-token", "쎄타": "theta-token",
    "tfuel": "theta-fuel", "쎄타퓨얼": "theta-fuel",
    "grt": "the-graph", "더그래프": "the-graph",
    "lrc": "loopring", "루프링": "loopring",
    "bat": "basic-attention-token", "배트": "basic-attention-token",
    "zrx": "0x", "제로엑스": "0x",
    "enj": "enjincoin", "엔진코인": "enjincoin",
    "mana": "decentraland", "디센트럴랜드": "decentraland",
    "sand": "the-sandbox", "샌드박스": "the-sandbox",
    "axs": "axie-infinity", "엑시인피니티": "axie-infinity",
    "chr": "chromaway", "크로미아": "chromaway",
    "ankr": "ankr", "앵커": "ankr",
    "ocean": "ocean-protocol", "오션프로토콜": "ocean-protocol",
    "gala": "gala", "갈라": "gala",
    "imx": "immutable-x", "이뮤터블엑스": "immutable-x",
    "blur": "blur", "블러": "blur",
    "ape": "apecoin", "에이프코인": "apecoin",
    "ldo": "lido-dao", "리도": "lido-dao",
    "stx": "blockstack", "스택스": "blockstack",
    "cfx": "conflux-token", "컨플럭스": "conflux-token",
    "jasmy": "jasmycoin", "재스미": "jasmycoin",
    "flux": "zelcash", "플럭스": "zelcash",
    "rndr": "render-token", "렌더": "render-token",
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
        usd = info.get("usd") or 0
        krw = info.get("krw") or 0
        change = info.get("usd_24h_change") or 0
        mcap = info.get("usd_market_cap") or 0
        vol = info.get("usd_24h_vol") or 0

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
            change = coin.get("price_change_percentage_24h") or 0
            sign = "+" if change >= 0 else ""
            lines.append(f"{i}. {name} ({symbol}): ${price:,.2f} ({sign}{change:.1f}%)")

        return "\n".join(lines)
    except Exception as e:
        logger.error("crypto_market_top failed: %s", e, exc_info=True)
        return f"시장 데이터 조회 실패: {e}"


def get_tools() -> list:
    return [crypto_price_lookup, crypto_market_top]
