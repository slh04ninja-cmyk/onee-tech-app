"""
Signal Parser - Extrait les signaux de trading gold depuis différents formats.
Supporte les formats courants des channels Telegram de trading.
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class TradeSignal:
    direction: str  # "BUY" or "SELL"
    entry: float
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    sl: Optional[float] = None
    pair: str = "XAUUSD"
    raw_text: str = ""
    timestamp: Optional[datetime] = None
    confidence: float = 0.0  # 0-1, how confident we are in the parse


def parse_signal(text: str, timestamp: Optional[datetime] = None) -> Optional[TradeSignal]:
    """Parse a trading signal from text. Returns None if not a signal."""
    text_upper = text.upper().strip()
    
    # Skip non-signal messages
    skip_words = ["GOOD MORNING", "GOOD NIGHT", "HELLO", "WELCOME", "THANK", 
                  "RECAP", "RESULT", "EDUCATION", "MOTIVATION", "PIPS",
                  "JOIN", "VIP", "SUBSCRIBE", "PREMIUM", "SIGNAL WILL",
                  "ANALYSIS ONLY", "NOT SIGNAL"]
    if any(w in text_upper for w in skip_words) and not any(w in text_upper for w in ["BUY", "SELL", "LONG", "SHORT"]):
        return None
    
    # Detect direction
    direction = None
    if re.search(r'\b(BUY|LONG|BULLISH)\b', text_upper):
        direction = "BUY"
    elif re.search(r'\b(SELL|SHORT|BEARISH)\b', text_upper):
        direction = "SELL"
    
    if not direction:
        return None
    
    # Extract prices - various formats
    # Format 1: Entry/TP/SL labels
    entry = _extract_price(text, [r'ENTRY[:\s]*(\d+\.?\d*)', r'OPEN[:\s]*(\d+\.?\d*)',
                                   r'@[:\s]*(\d+\.?\d*)', r'ZONE[:\s]*(\d+\.?\d*[-–]\d+\.?\d*)',
                                   r'BUY[:\s]*(\d+\.?\d*)', r'SELL[:\s]*(\d+\.?\d*)',
                                   r'LONG[:\s]*(\d+\.?\d*)', r'SHORT[:\s]*(\d+\.?\d*)'])
    
    # If no labeled entry, try to find a standalone price in gold range (1000-5000)
    if entry is None:
        entry = _extract_standalone_price(text)
    
    if entry is None:
        return None
    
    # Extract TP levels
    tp1 = _extract_price(text, [r'TP\s*1[:\s]*(\d+\.?\d*)', r'TP[:\s]*(\d+\.?\d*)',
                                 r'TAKE\s*PROFIT\s*1?[:\s]*(\d+\.?\d*)',
                                 r'TAKE\s*PROFIT\s*(?:1|ONE)?[:\s]*(\d+\.?\d*)'])
    tp2 = _extract_price(text, [r'TP\s*2[:\s]*(\d+\.?\d*)', r'TAKE\s*PROFIT\s*2[:\s]*(\d+\.?\d*)',
                                 r'TAKE\s*PROFIT\s*TWO[:\s]*(\d+\.?\d*)'])
    tp3 = _extract_price(text, [r'TP\s*3[:\s]*(\d+\.?\d*)', r'TAKE\s*PROFIT\s*3[:\s]*(\d+\.?\d*)',
                                 r'TAKE\s*PROFIT\s*THREE[:\s]*(\d+\.?\d*)'])
    
    # Extract SL
    sl = _extract_price(text, [r'SL[:\s]*(\d+\.?\d*)', r'STOP\s*LOSS[:\s]*(\d+\.?\d*)',
                                r'STOP[:\s]*(\d+\.?\d*)'])
    
    # Calculate confidence
    confidence = 0.3  # base for having direction + entry
    if tp1: confidence += 0.3
    if sl: confidence += 0.2
    if tp2: confidence += 0.1
    if tp3: confidence += 0.1
    
    # Validate gold price range (roughly 1000-5000)
    if entry < 1000 or entry > 5000:
        return None
    
    return TradeSignal(
        direction=direction,
        entry=entry,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        sl=sl,
        raw_text=text[:200],
        timestamp=timestamp,
        confidence=confidence
    )


def _extract_price(text: str, patterns: list) -> Optional[float]:
    """Extract a price from text using multiple regex patterns."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                val = match.group(1)
                # Handle range like "3250-3260" -> take midpoint
                if re.match(r'\d+\.?\d*[-–]\d+\.?\d*', val):
                    parts = re.split(r'[-–]', val)
                    return (float(parts[0]) + float(parts[1])) / 2
                return float(val)
            except (ValueError, IndexError):
                continue
    return None


def _extract_standalone_price(text: str) -> Optional[float]:
    """Extract a standalone gold price (1000-5000 range)."""
    # Look for prices like 3250.50, 2650, etc.
    prices = re.findall(r'\b(\d{4}\.?\d{0,2})\b', text)
    for p in prices:
        val = float(p)
        if 1000 <= val <= 5000:
            return val
    return None


def parse_messages(messages: list) -> list:
    """Parse a list of (text, timestamp) tuples and return signals."""
    signals = []
    for text, ts in messages:
        signal = parse_signal(text, ts)
        if signal:
            signals.append(signal)
    return signals


def detect_channel_format(messages: list) -> str:
    """Detect the signal format used by a channel."""
    formats = {
        "entry_tp_sl": 0,
        "buy_sell_price": 0,
        "emoji_based": 0,
        "free_text": 0
    }
    
    for text, _ in messages[:30]:
        text_upper = text.upper()
        if re.search(r'ENTRY|TP\s*\d|SL|TAKE PROFIT|STOP LOSS', text_upper):
            formats["entry_tp_sl"] += 1
        elif re.search(r'(BUY|SELL)\s*\d{4}', text_upper):
            formats["buy_sell_price"] += 1
        elif re.search(r'[🟢🔴📈📉💰🎯]', text):
            formats["emoji_based"] += 1
        elif re.search(r'(BUY|SELL|LONG|SHORT)', text_upper):
            formats["free_text"] += 1
    
    return max(formats, key=formats.get) if max(formats.values()) > 0 else "unknown"
