"""
Gold Price Fetcher - Récupère les données de prix XAUUSD via Yahoo Finance API directe.
Supporte les bougies 1min par blocs de 7 jours pour le scalping.
"""

import requests
import time
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional

YAHOO_API_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Yahoo Finance limits 1m data to 7 days per request
CHUNK_DAYS_1M = 7
MAX_CHUNKS = 4  # Max 4 chunks = 28 days of 1m data


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
    Fetch XAUUSD price data with automatic chunking for 1m candles.
    
    Args:
        days: Number of days of history
        interval: '1m', '5m', '15m', '1h', '1d'
    
    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
    """
    ticker = "GC=F"  # Gold futures
    
    now = int(time.time())
    
    # For 1m data: chunk into 7-day blocks (Yahoo Finance limit)
    if interval == "1m":
        if days > CHUNK_DAYS_1M * MAX_CHUNKS:
            # Too many days for 1m, fall back to 5m
            return fetch_gold_prices(days, "5m")
        
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
        
        if not frames:
            # Fallback to 5m
            return fetch_gold_prices(days, "5m")
        
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df.sort_index()
        
    elif interval == "5m":
        # 5m data: can fetch up to 60 days in one request
        start_ts = now - (days * 86400)
        df = _fetch_chunk(ticker, start_ts, now, "5m")
        
        if df.empty:
            return fetch_gold_prices(days, "15m")
    
    elif interval in ("15m", "30m"):
        start_ts = now - (days * 86400)
        df = _fetch_chunk(ticker, start_ts, now, "15m")
        
        if df.empty:
            return fetch_gold_prices(days, "1h")
    
    else:  # 1h, 1d
        start_ts = now - (days * 86400)
        df = _fetch_chunk(ticker, start_ts, now, interval)
        
        if df.empty:
            # Last resort: try XAUUSD forex ticker
            df = _fetch_chunk("XAUUSD=X", start_ts, now, interval)
    
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
                     tp1: Optional[float] = None, 
                     tp2: Optional[float] = None,
                     tp3: Optional[float] = None,
                     sl: Optional[float] = None,
                     max_hours: int = 48) -> dict:
    """
    Check if TP or SL was hit after a signal using precise candle data.
    
    Returns:
        dict with: tp1_hit, tp2_hit, tp3_hit, sl_hit, 
                   tp1_time, sl_time, max_move, result, pnl_pips
    """
    result = {
        "tp1_hit": False, "tp2_hit": False, "tp3_hit": False,
        "sl_hit": False, "tp1_time": None, "sl_time": None,
        "max_move": 0.0, "result": "OPEN", "pnl_pips": 0.0
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
    
    for idx, row in future_prices.iterrows():
        high = float(row["High"])
        low = float(row["Low"])
        
        if direction == "BUY":
            # Check SL first (more important for risk)
            if sl and not result["sl_hit"] and low <= sl:
                result["sl_hit"] = True
                result["sl_time"] = idx
                result["pnl_pips"] = (sl - entry) * 10
                result["result"] = "SL"
                break
            
            # Check TPs
            if tp1 and not result["tp1_hit"] and high >= tp1:
                result["tp1_hit"] = True
                result["tp1_time"] = idx
                if result["result"] == "OPEN":
                    result["pnl_pips"] = (tp1 - entry) * 10
                    result["result"] = "TP1"
            
            if tp2 and not result["tp2_hit"] and high >= tp2:
                result["tp2_hit"] = True
                result["pnl_pips"] = (tp2 - entry) * 10
                result["result"] = "TP2"
            
            if tp3 and not result["tp3_hit"] and high >= tp3:
                result["tp3_hit"] = True
                result["pnl_pips"] = (tp3 - entry) * 10
                result["result"] = "TP3"
            
            result["max_move"] = max(result["max_move"], high - entry)
        
        else:  # SELL
            # Check SL first
            if sl and not result["sl_hit"] and high >= sl:
                result["sl_hit"] = True
                result["sl_time"] = idx
                result["pnl_pips"] = (entry - sl) * 10
                result["result"] = "SL"
                break
            
            # Check TPs
            if tp1 and not result["tp1_hit"] and low <= tp1:
                result["tp1_hit"] = True
                result["tp1_time"] = idx
                if result["result"] == "OPEN":
                    result["pnl_pips"] = (entry - tp1) * 10
                    result["result"] = "TP1"
            
            if tp2 and not result["tp2_hit"] and low <= tp2:
                result["tp2_hit"] = True
                result["pnl_pips"] = (entry - tp2) * 10
                result["result"] = "TP2"
            
            if tp3 and not result["tp3_hit"] and low <= tp3:
                result["tp3_hit"] = True
                result["pnl_pips"] = (entry - tp3) * 10
                result["result"] = "TP3"
            
            result["max_move"] = max(result["max_move"], entry - low)
    
    return result
