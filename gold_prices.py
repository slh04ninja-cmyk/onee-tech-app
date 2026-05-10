"""
Gold Price Fetcher - Récupère les données de prix XAUUSD via Yahoo Finance et OANDA.
Supporte les bougies 1min par blocs de 7 jours pour le scalping.
Supporte un nombre dynamique de TP.
"""

import os
import requests
import time
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

YAHOO_API_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Yahoo Finance limits 1m data to 7 days per request
CHUNK_DAYS_1M = 7
MAX_CHUNKS = 4  # Max 4 chunks = 28 days of 1m data

# OANDA config
OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")
OANDA_BASE_URL = "https://api-fxpractice.oanda.com" if OANDA_ENV == "practice" else "https://api-fxtrade.oanda.com"
OANDA_INSTRUMENT = "XAU_USD"


def _fetch_oanda_candles(start_dt: datetime, end_dt: datetime, granularity: str = "M1") -> pd.DataFrame:
    """
    Fetch OHLCV candles from OANDA v20 API.
    Max 5000 candles per request (~3.5 days for M1).

    Args:
        start_dt: Start datetime (UTC)
        end_dt: End datetime (UTC)
        granularity: OANDA granularity (M1, M5, M15, H1, etc.)

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
    """
    if not OANDA_API_KEY:
        return pd.DataFrame()

    url = f"{OANDA_BASE_URL}/v3/instruments/{OANDA_INSTRUMENT}/candles"
    headers = {"Authorization": f"Bearer {OANDA_API_KEY}"}

    # OANDA expects RFC3339 format
    params = {
        "from": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "granularity": granularity,
        "price": "MBA",  # Mid, Bid, Ask — we use Mid
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            return pd.DataFrame()

        data = resp.json()
        candles = data.get("candles", [])
        if not candles:
            return pd.DataFrame()

        rows = []
        for c in candles:
            if not c.get("complete", True):
                continue  # skip incomplete candles
            mid = c.get("mid", {})
            rows.append({
                "Open": float(mid.get("o", 0)),
                "High": float(mid.get("h", 0)),
                "Low": float(mid.get("l", 0)),
                "Close": float(mid.get("c", 0)),
                "Volume": int(c.get("volume", 0)),
                "_ts": c["time"],
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df.index = pd.to_datetime(df["_ts"])
        df.index = df.index.tz_localize(None)
        df = df.drop(columns=["_ts"])
        return df

    except Exception:
        return pd.DataFrame()


def fetch_oanda_prices(days: int = 60, interval: str = "1m") -> pd.DataFrame:
    """
    Fetch XAUUSD from OANDA with automatic chunking.
    OANDA limits to 5000 candles per request (~3.5 days for M1).

    Args:
        days: Number of days of history
        interval: '1m', '5m', '15m', '1h'

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
    """
    if not OANDA_API_KEY:
        return pd.DataFrame()

    granularity_map = {"1m": "M1", "5m": "M5", "15m": "M15", "1h": "H1"}
    oanda_gran = granularity_map.get(interval, "M1")

    # Chunk size in days based on granularity
    chunk_days_map = {"M1": 3, "M5": 15, "M15": 45, "H1": 180}
    chunk_days = chunk_days_map.get(oanda_gran, 3)

    now = datetime.utcnow()
    frames = []
    chunks_needed = (days + chunk_days - 1) // chunk_days

    for i in range(chunks_needed):
        chunk_end = now - timedelta(days=i * chunk_days)
        chunk_start = chunk_end - timedelta(days=chunk_days)

        df_chunk = _fetch_oanda_candles(chunk_start, chunk_end, oanda_gran)
        if not df_chunk.empty:
            frames.append(df_chunk)

        if i < chunks_needed - 1:
            time.sleep(0.3)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="first")]
    df = df.sort_index()
    return df


def _fetch_chunk(ticker: str, start_ts: int, end_ts: int, interval: str) -> pd.DataFrame:
    """Fetch a single chunk of OHLCV data from Yahoo Finance."""
    url = f"{YAHOO_API_URL.format(ticker=ticker)}?interval={interval}&period1={start_ts}&period2={end_ts}"
    resp = requests.get(url, timeout=15, headers=HEADERS)

    if resp.status_code != 200:
        return pd.DataFrame()

    data = resp.json()
    result = data.get("chart", {}).get("result", [None])[0]
    if not result:
        return pd.DataFrame()

    timestamps = result.get("timestamp", [])
    ohlcv = result.get("indicators", {}).get("quote", [{}])[0]

    if not timestamps or not ohlcv:
        return pd.DataFrame()

    df = pd.DataFrame({
        "Open": ohlcv.get("open", []),
        "High": ohlcv.get("high", []),
        "Low": ohlcv.get("low", []),
        "Close": ohlcv.get("close", []),
        "Volume": ohlcv.get("volume", []),
    }, index=pd.to_datetime(timestamps, unit="s"))

    # Drop rows with all NaN
    df = df.dropna(how="all")

    return df


def fetch_gold_prices(days: int = 30, interval: str = "1m") -> pd.DataFrame:
    """
    Fetch XAUUSD price data. Strategy:
    1. Yahoo Finance (spot XAUUSD=X, fallback GC=F) — fast, no key needed
    2. OANDA — fallback for extended 1min history (>28 days)

    Args:
        days: Number of days of history
        interval: '1m', '5m', '15m', '1h', '1d'

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
    """
    # Spot gold first (matches XAUUSD trading charts), then futures as fallback
    tickers = ["XAUUSD=X", "GC=F"]

    now = int(time.time())

    # For 1m data: chunk into 7-day blocks (Yahoo Finance limit)
    if interval == "1m":
        if days > CHUNK_DAYS_1M * MAX_CHUNKS:
            # Beyond Yahoo's 1min range — try OANDA first
            oanda_df = fetch_oanda_prices(days, "1m")
            if not oanda_df.empty:
                return oanda_df
            # OANDA failed, fall back to 5min via Yahoo
            return fetch_gold_prices(days, "5m")

        for ticker in tickers:
            frames = []
            chunks_needed = min(MAX_CHUNKS, (days + CHUNK_DAYS_1M - 1) // CHUNK_DAYS_1M)

            for i in range(chunks_needed):
                chunk_end = now - (i * CHUNK_DAYS_1M * 86400)
                chunk_start = chunk_end - (CHUNK_DAYS_1M * 86400)

                df_chunk = _fetch_chunk(ticker, chunk_start, chunk_end, "1m")
                if not df_chunk.empty:
                    frames.append(df_chunk)

                if i < chunks_needed - 1:
                    time.sleep(0.3)  # Rate limit protection

            if frames:
                df = pd.concat(frames)
                df = df[~df.index.duplicated(keep="first")]
                df = df.sort_index()
                return df

        # Neither ticker worked at 1m, try OANDA then 5m
        oanda_df = fetch_oanda_prices(days, "1m")
        if not oanda_df.empty:
            return oanda_df
        return fetch_gold_prices(days, "5m")

    elif interval == "5m":
        # 5m data: can fetch up to 60 days in one request
        for ticker in tickers:
            start_ts = now - (days * 86400)
            df = _fetch_chunk(ticker, start_ts, now, "5m")
            if not df.empty:
                return df
        return fetch_gold_prices(days, "15m")

    elif interval in ("15m", "30m"):
        for ticker in tickers:
            start_ts = now - (days * 86400)
            df = _fetch_chunk(ticker, start_ts, now, "15m")
            if not df.empty:
                return df
        return fetch_gold_prices(days, "1h")

    else:  # 1h, 1d
        for ticker in tickers:
            start_ts = now - (days * 86400)
            df = _fetch_chunk(ticker, start_ts, now, interval)
            if not df.empty:
                return df

    if df.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    # Normalize timezone
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    return df


def get_price_at(prices: pd.DataFrame, timestamp: datetime) -> Optional[dict]:
    """Get the price data closest to a given timestamp."""
    if prices.empty:
        return None

    idx = prices.index.get_indexer([timestamp], method="nearest")[0]
    if idx < 0 or idx >= len(prices):
        return None

    row = prices.iloc[idx]
    return {
        "open": float(row["Open"]),
        "high": float(row["High"]),
        "low": float(row["Low"]),
        "close": float(row["Close"]),
        "timestamp": prices.index[idx]
    }


def check_tp_sl_hit(prices: pd.DataFrame, signal_time: datetime,
                     direction: str, entry: float,
                     tps: Optional[List[float]] = None,
                     sl: Optional[float] = None,
                     max_hours: int = 48) -> dict:
    """
    Check if TP or SL was hit after a signal using precise candle data.
    Supports a dynamic number of take-profit levels.

    Handles the GC=F (futures) vs XAUUSD (spot) premium by computing
    a dynamic offset at signal time: premium = GC=F_price - signal_entry.
    Then TP/SL are adjusted by this premium so backtesting uses spot prices.

    Args:
        tps: List of TP prices [TP1, TP2, ..., TPn] — can be any length

    Returns:
        dict with: tp_hits (list of bool), sl_hit, tp_times (list),
                   max_move, result, pnl_pips, highest_tp_hit (int)
    """
    if tps is None:
        tps = []

    result = {
        "tp_hits": [False] * len(tps),      # one bool per TP
        "tp_times": [None] * len(tps),       # one time per TP
        "sl_hit": False,
        "sl_time": None,
        "max_move": 0.0,
        "result": "OPEN",
        "pnl_pips": 0.0,
        "highest_tp_hit": 0,                  # 0 = none, 1 = TP1, 2 = TP2, etc.
        "premium": 0.0                        # futures-spot premium applied
    }

    if prices.empty:
        return result

    # Get price data from signal time onwards
    mask = prices.index >= signal_time
    future_prices = prices[mask]

    if future_prices.empty:
        return result

    # Limit to max_hours
    end_time = signal_time + timedelta(hours=max_hours)
    future_prices = future_prices[future_prices.index <= end_time]

    if future_prices.empty:
        return result

    # Compute futures-spot premium at signal time
    # premium = GC=F price at signal - spot entry price from signal
    # Then: adjusted_price = GC=F candle price - premium
    first_candle = future_prices.iloc[0]
    gc_f_at_signal = float(first_candle["Open"])
    premium = gc_f_at_signal - entry
    result["premium"] = round(premium, 2)

    # Adjust TP/SL to futures-equivalent prices for comparison
    # (add premium so they match GC=F scale)
    adjusted_tps = [tp + premium for tp in tps]
    adjusted_sl = (sl + premium) if sl else None

    for idx, row in future_prices.iterrows():
        high = float(row["High"])
        low = float(row["Low"])

        if direction == "BUY":
            # Check ALL TPs — mark every TP whose level was reached
            for i, tp_adj in enumerate(adjusted_tps):
                if not result["tp_hits"][i] and high >= tp_adj:
                    result["tp_hits"][i] = True
                    result["tp_times"][i] = idx
                    result["highest_tp_hit"] = i + 1
                    result["pnl_pips"] = (tps[i] - entry) * 10
                    result["result"] = f"TP{i + 1}"

            # Check SL only if no TP has been hit yet
            if result["highest_tp_hit"] == 0:
                if adjusted_sl and not result["sl_hit"] and low <= adjusted_sl:
                    result["sl_hit"] = True
                    result["sl_time"] = idx
                    result["pnl_pips"] = (sl - entry) * 10
                    result["result"] = "SL"
                    break

            result["max_move"] = max(result["max_move"], high - gc_f_at_signal)

        else:  # SELL
            # Check ALL TPs — mark every TP whose level was reached
            for i, tp_adj in enumerate(adjusted_tps):
                if not result["tp_hits"][i] and low <= tp_adj:
                    result["tp_hits"][i] = True
                    result["tp_times"][i] = idx
                    result["highest_tp_hit"] = i + 1
                    result["pnl_pips"] = (entry - tps[i]) * 10
                    result["result"] = f"TP{i + 1}"

            # Check SL only if no TP has been hit yet
            if result["highest_tp_hit"] == 0:
                if adjusted_sl and not result["sl_hit"] and high >= adjusted_sl:
                    result["sl_hit"] = True
                    result["sl_time"] = idx
                    result["pnl_pips"] = (entry - sl) * 10
                    result["result"] = "SL"
                    break

            result["max_move"] = max(result["max_move"], gc_f_at_signal - low)

    return result
