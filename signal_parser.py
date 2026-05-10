"""
Signal Parser - Extrait les signaux de trading gold depuis différents formats.
Supporte les formats courants des channels Telegram de trading.
Supporte un nombre dynamique de TP (TP1, TP2, ..., TPn).
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class TradeSignal:
    direction: str  # "BUY" or "SELL"
    entry: float
    tps: List[float] = field(default_factory=list)  # [TP1, TP2, ..., TPn]
    sl: Optional[float] = None
    pair: str = "XAUUSD"
    raw_text: str = ""
    timestamp: Optional[datetime] = None
    confidence: float = 0.0  # 0-1, how confident we are in the parse

    @property
    def tp1(self) -> Optional[float]:
        return self.tps[0] if len(self.tps) >= 1 else None

    @property
    def tp2(self) -> Optional[float]:
        return self.tps[1] if len(self.tps) >= 2 else None

    @property
    def tp3(self) -> Optional[float]:
        return self.tps[2] if len(self.tps) >= 3 else None


def _extract_all_tps(text: str) -> List[float]:
    """
    Extract ALL take-profit levels from text dynamically.
    Matches TP1, TP2, ..., TP99, TAKE PROFIT 1, etc.
    Returns sorted list by TP number.
    """
    tps = {}

    # Pattern 1: TP followed by number (TP1, TP2, TP10, etc.)
    for match in re.finditer(r'TP\s*(\d+)\s*[:\s]*(\d+\.?\d*)', text, re.IGNORECASE):
        tp_num = int(match.group(1))
        tp_val = float(match.group(2))
        if 1000 <= tp_val <= 5000:  # gold price range
            tps[tp_num] = tp_val

    # Pattern 2: TAKE PROFIT followed by number
    for match in re.finditer(r'TAKE\s*PROFIT\s*(\d+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)?\s*[:\s]*(\d+\.?\d*)', text, re.IGNORECASE):
        word_to_num = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5,
                       "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10}
        num_str = match.group(1)
        if num_str:
            tp_num = word_to_num.get(num_str.upper(), int(num_str) if num_str.isdigit() else 1)
        else:
            tp_num = 1
        tp_val = float(match.group(2))
        if 1000 <= tp_val <= 5000:
            tps[tp_num] = tp_val

    # Pattern 3: ✅ followed by TP (common in signal channels)
    for match in re.finditer(r'✅\s*TP\s*(\d+)\s*[:\s]*(\d+\.?\d*)', text, re.IGNORECASE):
        tp_num = int(match.group(1))
        tp_val = float(match.group(2))
        if 1000 <= tp_val <= 5000:
            tps[tp_num] = tp_val

    # Pattern 4: Just "TP:" without number (single TP) — only if no numbered TPs found
    if not tps:
        match = re.search(r'TP[:\s]*(\d+\.?\d*)', text, re.IGNORECASE)
        if match:
            tp_val = float(match.group(1))
            if 1000 <= tp_val <= 5000:
                tps[1] = tp_val

    # Return sorted by TP number
    return [tps[k] for k in sorted(tps.keys())]


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
    entry = _extract_price(text, [r'ENTRY[:\s]*(\d+\.?\d*)', r'OPEN[:\s]*(\d+\.?\d*)',
                                   r'@[:\s]*(\d+\.?\d*)', r'ZONE[:\s]*(\d+\.?\d*[-–]\d+\.?\d*)',
                                   r'BUY[:\s]*(\d+\.?\d*)', r'SELL[:\s]*(\d+\.?\d*)',
                                   r'LONG[:\s]*(\d+\.?\d*)', r'SHORT[:\s]*(\d+\.?\d*)'])

    # If no labeled entry, try to find a standalone price in gold range (1000-5000)
    if entry is None:
        entry = _extract_standalone_price(text)

    if entry is None:
        return None

    # Extract ALL TP levels dynamically
    tps = _extract_all_tps(text)

    # Extract SL — handle "(SL):", "SL:", "SL ", "Stop Loss:", etc.
    sl = _extract_price(text, [r'[\(]?SL[\)]?[:\s\-]*(\d+\.?\d*)',
                                r'STOP\s*LOSS[:\s\-]*(\d+\.?\d*)',
                                r'STOP[:\s\-]*(\d+\.?\d*)'])

    # Calculate confidence
    confidence = 0.3  # base for having direction + entry
    if tps:
        confidence += 0.3
    if sl:
        confidence += 0.2
    if len(tps) >= 2:
        confidence += 0.1
    if len(tps) >= 3:
        confidence += 0.1

    # Validate gold price range (roughly 1000-5000)
    if entry < 1000 or entry > 5000:
        return None

    return TradeSignal(
        direction=direction,
        entry=entry,
        tps=tps,
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
