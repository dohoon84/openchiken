from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import yfinance as yf
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# ── 티커 심볼 매핑 ──────────────────────────────────────────────────────────────

_CRYPTO_MAP: dict[str, str] = {
    "비트코인": "BTC-USD", "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "이더리움": "ETH-USD", "ethereum": "ETH-USD", "eth": "ETH-USD",
    "리플": "XRP-USD", "xrp": "XRP-USD",
    "솔라나": "SOL-USD", "solana": "SOL-USD", "sol": "SOL-USD",
    "도지코인": "DOGE-USD", "dogecoin": "DOGE-USD", "doge": "DOGE-USD",
    "에이다": "ADA-USD", "cardano": "ADA-USD", "ada": "ADA-USD",
    "아발란체": "AVAX-USD", "avalanche": "AVAX-USD", "avax": "AVAX-USD",
    "폴리곤": "MATIC-USD", "polygon": "MATIC-USD", "matic": "MATIC-USD",
    "링크": "LINK-USD", "chainlink": "LINK-USD", "link": "LINK-USD",
    "도트": "DOT-USD", "polkadot": "DOT-USD", "dot": "DOT-USD",
}

_INDEX_MAP: dict[str, tuple[str, str]] = {
    "코스피": ("^KS11", "KOSPI"),
    "kospi": ("^KS11", "KOSPI"),
    "코스닥": ("^KQ11", "KOSDAQ"),
    "kosdaq": ("^KQ11", "KOSDAQ"),
    "s&p500": ("^GSPC", "S&P 500"),
    "s&p 500": ("^GSPC", "S&P 500"),
    "sp500": ("^GSPC", "S&P 500"),
    "나스닥": ("^IXIC", "NASDAQ"),
    "nasdaq": ("^IXIC", "NASDAQ"),
    "다우존스": ("^DJI", "Dow Jones"),
    "dow": ("^DJI", "Dow Jones"),
    "닛케이": ("^N225", "Nikkei 225"),
    "nikkei": ("^N225", "Nikkei 225"),
    "항셍": ("^HSI", "Hang Seng"),
    "hang seng": ("^HSI", "Hang Seng"),
    "vix": ("^VIX", "VIX 공포지수"),
    "금": ("GC=F", "금 선물"),
    "gold": ("GC=F", "금 선물"),
    "은": ("SI=F", "은 선물"),
    "silver": ("SI=F", "은 선물"),
    "wti": ("CL=F", "WTI 원유"),
    "원유": ("CL=F", "WTI 원유"),
}

_KR_STOCK_MAP: dict[str, tuple[str, str]] = {
    "삼성전자": ("005930.KS", "삼성전자"),
    "sk하이닉스": ("000660.KS", "SK하이닉스"),
    "hynix": ("000660.KS", "SK하이닉스"),
    "현대차": ("005380.KS", "현대자동차"),
    "현대자동차": ("005380.KS", "현대자동차"),
    "lg에너지솔루션": ("373220.KS", "LG에너지솔루션"),
    "카카오": ("035720.KS", "카카오"),
    "네이버": ("035420.KS", "NAVER"),
    "naver": ("035420.KS", "NAVER"),
    "셀트리온": ("068270.KS", "셀트리온"),
    "기아": ("000270.KS", "기아"),
    "포스코": ("005490.KS", "POSCO홀딩스"),
    "kb금융": ("105560.KS", "KB금융"),
    "신한지주": ("055550.KS", "신한지주"),
    "하나금융지주": ("086790.KS", "하나금융지주"),
    "lg화학": ("051910.KS", "LG화학"),
    "삼성바이오로직스": ("207940.KS", "삼성바이오로직스"),
}

_US_STOCK_MAP: dict[str, tuple[str, str]] = {
    "애플": ("AAPL", "Apple"),
    "apple": ("AAPL", "Apple"),
    "aapl": ("AAPL", "Apple"),
    "구글": ("GOOGL", "Google"),
    "google": ("GOOGL", "Google"),
    "알파벳": ("GOOGL", "Alphabet"),
    "마이크로소프트": ("MSFT", "Microsoft"),
    "microsoft": ("MSFT", "Microsoft"),
    "msft": ("MSFT", "Microsoft"),
    "테슬라": ("TSLA", "Tesla"),
    "tesla": ("TSLA", "Tesla"),
    "tsla": ("TSLA", "Tesla"),
    "엔비디아": ("NVDA", "NVIDIA"),
    "nvidia": ("NVDA", "NVIDIA"),
    "nvda": ("NVDA", "NVIDIA"),
    "아마존": ("AMZN", "Amazon"),
    "amazon": ("AMZN", "Amazon"),
    "메타": ("META", "Meta"),
    "meta": ("META", "Meta"),
    "넷플릭스": ("NFLX", "Netflix"),
    "netflix": ("NFLX", "Netflix"),
}


def _resolve_ticker(name: str) -> Optional[tuple[str, str, str]]:
    """이름을 (ticker, display_name, category)로 변환합니다."""
    key = name.strip().lower()

    if key in _CRYPTO_MAP:
        ticker = _CRYPTO_MAP[key]
        return ticker, name, "crypto"

    if key in _INDEX_MAP:
        ticker, display = _INDEX_MAP[key]
        return ticker, display, "index"

    if key in _KR_STOCK_MAP:
        ticker, display = _KR_STOCK_MAP[key]
        return ticker, display, "stock"

    if key in _US_STOCK_MAP:
        ticker, display = _US_STOCK_MAP[key]
        return ticker, display, "stock"

    # 직접 티커 심볼로 시도
    upper = name.strip().upper()
    if upper.endswith(".KS") or upper.endswith(".KQ") or "^" in upper or "-" in upper:
        return upper, upper, "direct"

    # 알파벳만으로 구성된 1~5자 → 미국 주식 직접 시도
    if name.strip().isalpha() and len(name.strip()) <= 5:
        return upper, upper, "direct"

    return None


def _format_price(price: float, currency: str) -> str:
    if currency == "KRW":
        return f"{price:,.0f}원"
    if currency in ("USD", ""):
        return f"${price:,.2f}"
    return f"{price:,.2f} {currency}"


def _fetch_quote(ticker: str, display_name: str) -> str:
    """yfinance로 현재가와 변동 정보를 조회합니다."""
    t = yf.Ticker(ticker)
    info = t.fast_info

    try:
        price = info.last_price
        currency = getattr(info, "currency", "USD") or "USD"
    except Exception:
        return f"'{display_name}' 시세 조회에 실패했습니다."

    if price is None:
        return f"'{display_name}' 시세 데이터를 가져올 수 없습니다."

    lines = [f"**{display_name}** 현재가: {_format_price(price, currency)}"]

    try:
        prev_close = info.previous_close
        if prev_close and prev_close > 0:
            change = price - prev_close
            change_pct = (change / prev_close) * 100
            sign = "+" if change >= 0 else ""
            lines.append(f"전일 대비: {sign}{_format_price(change, currency)} ({sign}{change_pct:.2f}%)")
            lines.append(f"전일 종가: {_format_price(prev_close, currency)}")
    except Exception:
        pass

    try:
        day_high = info.day_high
        day_low = info.day_low
        if day_high and day_low:
            lines.append(f"당일 범위: {_format_price(day_low, currency)} ~ {_format_price(day_high, currency)}")
    except Exception:
        pass

    try:
        year_high = info.year_high
        year_low = info.year_low
        if year_high and year_low:
            lines.append(f"52주 범위: {_format_price(year_low, currency)} ~ {_format_price(year_high, currency)}")
    except Exception:
        pass

    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    lines.append(f"(조회 시각: {now_kst})")

    return "\n".join(lines)


@tool
def finance_search(name: str) -> str:
    """Get real-time financial data for stocks, cryptocurrencies, and market indices.
    Use this tool when the user asks about prices, current values, or market data for:
    - Cryptocurrencies: 비트코인(BTC), 이더리움(ETH), 리플(XRP), 솔라나(SOL) etc.
    - Korean indices: 코스피, 코스닥
    - Global indices: 나스닥, S&P500, 다우존스, 닛케이
    - Korean stocks: 삼성전자, SK하이닉스, 현대차, 카카오, 네이버 etc.
    - US stocks: 애플, 구글, 테슬라, 엔비디아, 마이크로소프트 etc.
    - Commodities: 금(Gold), 은(Silver), WTI 원유
    Args:
        name: Asset name in Korean or English, or ticker symbol (e.g. '비트코인', 'AAPL', '^KS11')
    """
    try:
        resolved = _resolve_ticker(name)
        if resolved is None:
            return (
                f"'{name}'에 해당하는 금융 자산을 찾을 수 없습니다.\n"
                "지원 예시: 비트코인, 이더리움, 코스피, 코스닥, 나스닥, S&P500, "
                "삼성전자, 애플, 테슬라, 엔비디아, 금, WTI원유"
            )
        ticker, display_name, _ = resolved
        return _fetch_quote(ticker, display_name)
    except Exception as e:
        logger.error("finance_search failed for '%s': %s", name, e, exc_info=True)
        return f"'{name}' 시세 조회 중 오류가 발생했습니다: {e}"


# ── 기술적 지표 계산 헬퍼 ────────────────────────────────────────────────────────

def _calc_rsi(closes: "np.ndarray", period: int = 14) -> float:
    """RSI(Relative Strength Index) 계산."""
    if len(closes) < period + 1:
        return float("nan")
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _calc_macd(closes: "np.ndarray") -> tuple[float, float, float]:
    """MACD (12, 26, 9) → (macd_line, signal_line, histogram) 반환."""
    def ema(arr: np.ndarray, span: int) -> np.ndarray:
        k = 2 / (span + 1)
        result = np.empty_like(arr, dtype=float)
        result[0] = arr[0]
        for i in range(1, len(arr)):
            result[i] = arr[i] * k + result[i - 1] * (1 - k)
        return result

    if len(closes) < 35:
        return float("nan"), float("nan"), float("nan")

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd_line = ema12 - ema26
    signal = ema(macd_line, 9)
    histogram = macd_line - signal
    return round(float(macd_line[-1]), 4), round(float(signal[-1]), 4), round(float(histogram[-1]), 4)


def _calc_bollinger(closes: "np.ndarray", period: int = 20) -> tuple[float, float, float]:
    """볼린저 밴드 (상단, 중앙 MA, 하단) 반환."""
    if len(closes) < period:
        return float("nan"), float("nan"), float("nan")
    window = closes[-period:]
    mid = float(window.mean())
    std = float(window.std(ddof=0))
    return round(mid + 2 * std, 2), round(mid, 2), round(mid - 2 * std, 2)


def _signal_summary(
    rsi: float,
    macd: float,
    signal: float,
    histogram: float,
    price: float,
    ma20: float,
    ma60: float,
    bb_upper: float,
    bb_lower: float,
) -> str:
    """각 지표를 해석하여 매수/중립/매도 신호 텍스트를 생성합니다."""
    signals: list[str] = []
    buy_count = sell_count = 0

    # RSI
    if not np.isnan(rsi):
        if rsi < 30:
            signals.append(f"RSI {rsi} → 과매도 구간 (매수 신호)")
            buy_count += 1
        elif rsi > 70:
            signals.append(f"RSI {rsi} → 과매수 구간 (매도 신호)")
            sell_count += 1
        else:
            signals.append(f"RSI {rsi} → 중립 구간")

    # MACD
    if not np.isnan(macd):
        if histogram > 0:
            signals.append(f"MACD {macd:.4f} / Signal {signal:.4f} → 히스토그램 양수, 상승 모멘텀")
            buy_count += 1
        else:
            signals.append(f"MACD {macd:.4f} / Signal {signal:.4f} → 히스토그램 음수, 하락 모멘텀")
            sell_count += 1

    # 이동평균선
    if not (np.isnan(ma20) or np.isnan(ma60)):
        if price > ma20 > ma60:
            signals.append(f"가격({price:,.2f}) > MA20({ma20:,.2f}) > MA60({ma60:,.2f}) → 정배열 (상승 추세)")
            buy_count += 1
        elif price < ma20 < ma60:
            signals.append(f"가격({price:,.2f}) < MA20({ma20:,.2f}) < MA60({ma60:,.2f}) → 역배열 (하락 추세)")
            sell_count += 1
        else:
            signals.append(f"MA20({ma20:,.2f}) / MA60({ma60:,.2f}) → 혼조")

    # 볼린저 밴드
    if not (np.isnan(bb_upper) or np.isnan(bb_lower)):
        if price <= bb_lower:
            signals.append(f"볼린저 하단({bb_lower:,.2f}) 근접/하회 → 반등 가능성")
            buy_count += 1
        elif price >= bb_upper:
            signals.append(f"볼린저 상단({bb_upper:,.2f}) 근접/상회 → 과열 주의")
            sell_count += 1
        else:
            signals.append(f"볼린저 밴드 내 ({bb_lower:,.2f} ~ {bb_upper:,.2f})")

    # 종합 판단
    total = buy_count + sell_count
    if total == 0:
        verdict = "⚪ 판단 불가 (데이터 부족)"
    elif buy_count > sell_count:
        verdict = f"🟢 매수 우세 ({buy_count}/{total} 지표 매수 신호)"
    elif sell_count > buy_count:
        verdict = f"🔴 매도 우세 ({sell_count}/{total} 지표 매도 신호)"
    else:
        verdict = f"🟡 중립 (매수 {buy_count} / 매도 {sell_count} 균형)"

    body = "\n".join(f"  - {s}" for s in signals)
    return f"{verdict}\n\n{body}"


@tool
def finance_analysis(name: str, period: str = "3mo") -> str:
    """Analyze buy/sell timing for a stock or cryptocurrency using technical indicators.
    Use this tool when the user asks about buy timing, sell timing, technical analysis,
    trend analysis, RSI, MACD, moving averages, or Bollinger Bands for:
    - Cryptocurrencies: 비트코인(BTC), 이더리움(ETH), 리플(XRP), 솔라나(SOL) etc.
    - Korean stocks: 삼성전자, SK하이닉스, 현대차 etc.
    - US stocks: 애플, 구글, 테슬라, 엔비디아 etc.
    - Market indices: 코스피, 나스닥, S&P500 etc.
    Args:
        name: Asset name in Korean or English, or ticker symbol (e.g. '비트코인', 'AAPL')
        period: Historical data period. One of '1mo', '3mo', '6mo', '1y'. Default '3mo'.
    """
    try:
        resolved = _resolve_ticker(name)
        if resolved is None:
            return (
                f"'{name}'에 해당하는 금융 자산을 찾을 수 없습니다.\n"
                "지원 예시: 비트코인, 이더리움, 코스피, 삼성전자, 애플, 테슬라"
            )
        ticker, display_name, _ = resolved

        t = yf.Ticker(ticker)
        hist = t.history(period=period)

        if hist.empty or len(hist) < 20:
            return f"'{display_name}' 의 과거 데이터가 부족하여 기술적 분석을 수행할 수 없습니다."

        closes = hist["Close"].to_numpy(dtype=float)
        price = float(closes[-1])
        currency = getattr(t.fast_info, "currency", "USD") or "USD"

        rsi = _calc_rsi(closes)
        macd_val, signal_val, histogram_val = _calc_macd(closes)

        ma20 = float(closes[-20:].mean()) if len(closes) >= 20 else float("nan")
        ma60 = float(closes[-60:].mean()) if len(closes) >= 60 else float("nan")
        bb_upper, bb_mid, bb_lower = _calc_bollinger(closes)

        summary = _signal_summary(rsi, macd_val, signal_val, histogram_val, price, ma20, ma60, bb_upper, bb_lower)

        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
        header = (
            f"## {display_name} 기술적 분석 ({period} 기준)\n"
            f"현재가: {_format_price(price, currency)} | 분석 시각: {now_kst}\n"
        )

        disclaimer = (
            "\n⚠️ 본 분석은 과거 데이터 기반 기술적 지표로, 투자 권유가 아닙니다. "
            "투자 결정은 본인 판단 하에 하시기 바랍니다."
        )

        return header + "\n" + summary + disclaimer

    except Exception as e:
        logger.error("finance_analysis failed for '%s': %s", name, e, exc_info=True)
        return f"'{name}' 기술적 분석 중 오류가 발생했습니다: {e}"


def get_tools() -> list:
    """Return all finance tools for agent binding."""
    return [finance_search, finance_analysis]
