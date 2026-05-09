"""
Gold Price Fetcher - Récupère les données de prix XAUUSD via yfinance.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


def fetch_gold_prices(days: int = 30, interval: str = "1m") -> pd.DataFrame:
    """
    Fetch XAUUSD price data.
    
    Args:
        days: Number of days of history
        interval: Price interval ('1m','5m','15m','1h','1d')
    
    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
        
    Note: yfinance limits intraday data:
        - 1m: max 7 days
        - 5m: max 60 days
        - 15m/30m: max 60 days
        - 1h: max 730 days
    """
    # Auto-select interval based on days requested
    if interval == "1m" and days > 7:
        interval = "5m"  # fallback for longer periods
    if interval == "5m" and days > 60:
        interval = "15m"
    if interval in ("1m", "5m", "15m") and days > 60:
        interval = "1h"
    
    ticker = yf.Ticker("GC=F")  # Gold futures
    
    end = datetime.now()
    start = end - timedelta(days=days)
    
    df = ticker.history(start=start, end=end, interval=interval)
    
    if df.empty:
        # Fallback: try with different ticker
        ticker = yf.Ticker("XAUUSD=X")
        df = ticker.history(start=start, end=end, interval=interval)
    
    if df.empty:
        # Fallback: try with longer interval
        if interval == "1m":
            return fetch_gold_prices(days, "5m")
        elif interval == "5m":
            return fetch_gold_prices(days, "15m")
        elif interval in ("15m", "30m"):
            return fetch_gold_prices(days, "1h")
    
    # Normalize columns
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = df.index.tz_localize(None) if df.index.tz else df.index
    
    return df


def get_price_at(prices: pd.DataFrame, timestamp: datetime) -> Optional[dict]:
    """Get the price data closest to a given timestamp."""
    if prices.empty:
        return None
    
    # Find closest timestamp
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
    Check if TP or SL was hit after a signal.
    
    Returns:
        dict with: tp1_hit, tp2_hit, tp3_hit, sl_hit, 
                   tp1_time, sl_time, max_move, result
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
            # Check SL first (more important)
            if sl and not result["sl_hit"] and low <= sl:
                result["sl_hit"] = True
                result["sl_time"] = idx
                result["pnl_pips"] = (sl - entry) * 10  # gold pips
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
