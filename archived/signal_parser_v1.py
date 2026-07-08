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


def _superscript_to_int(s: str) -> Optional[int]:
    """Convert Unicode superscript digits to an integer. Returns None if not a superscript number."""
    sup_map = {'⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
               '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'}
    result = ''
    for ch in s:
        if ch in sup_map:
            result += sup_map[ch]
        else:
            return None
    return int(result) if result else None


def _normalize_superscripts(text: str) -> str:
    """Replace Unicode superscript digits with ASCII digits in TP patterns.

    Converts patterns like 'TP¹ 4716' or 'TP.² 4712' into 'TP1 4716', 'TP2 4712'
    so that standard regex can match them.
    """
    sup_map = {'⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
               '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'}

    def _replace_tp_sup(match):
        prefix = match.group(1)  # 'TP' or 'tp'
        dots = match.group(2) or ''  # optional dots/spaces between TP and superscript
        sup_digits = match.group(3)  # superscript characters
        rest = match.group(4)  # everything after (space + price, etc.)
        ascii_digits = ''.join(sup_map.get(ch, ch) for ch in sup_digits)
        return f'{prefix}{ascii_digits}{rest}'

    # Match TP (case-insensitive) followed by optional dots/spaces, then superscript chars
    # Superscript Unicode range: \u00b9 (¹), \u00b2 (²), \u00b3 (³), \u2070-\u2079 (⁰-⁹)
    pattern = r'(?i)(TP)([.\s]*)([\u00b9\u00b2\u00b3\u2070-\u2079]+)(.*?)(?=\n|TP|$)'
    return re.sub(pattern, _replace_tp_sup, text)


def _extract_all_tps(text: str) -> List[float]:
    """
    Extract ALL take-profit levels from text dynamically.
    Matches TP1, TP2, ..., TP99, TAKE PROFIT 1, TP without number, etc.
    Also handles Unicode superscripts (TP¹, TP², etc.).
    Returns sorted list by TP number.
    """
    # Normalize superscripts first so all subsequent patterns work
    text = _normalize_superscripts(text)

    tps = {}

    # Pattern 1: TP followed by number (TP1, TP2, TP10, etc.)
    # Handles optional parentheses around TP label like "(TP1): 4671.00"
    # Handles optional parentheses around price like "TP1: (3245)"
    # Handles dot separator: "TP.1: 3245"
    for match in re.finditer(r'TP[\.\s]*(\d+)\s*\)?\s*[:\s\-]*\(?(\d+\.?\d*)\)?', text, re.IGNORECASE):
        tp_num = int(match.group(1))
        tp_val = float(match.group(2))
        if 1000 <= tp_val <= 9999:  # gold price range
            tps[tp_num] = tp_val

    # Pattern 2: TAKE PROFIT followed by number
    # Handles both "TAKE PROFIT ONE 4510" and "Take Profit 1 (TP1): 4671.00"
    # Handles optional parentheses around price like "TAKE PROFIT 1 (3245)"
    for match in re.finditer(r'TAKE\s*PROFIT\s*(\d+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)?\s*(?:\(.*?\))?\s*[:\s\-]*\(?(\d+\.?\d*)\)?', text, re.IGNORECASE):
        word_to_num = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5,
                       "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10}
        num_str = match.group(1)
        if num_str:
            tp_num = word_to_num.get(num_str.upper(), int(num_str) if num_str.isdigit() else 1)
        else:
            tp_num = 1
        tp_val = float(match.group(2))
        if 1000 <= tp_val <= 9999:
            tps[tp_num] = tp_val

    # Pattern 3: ✅ followed by TP (common in signal channels)
    for match in re.finditer(r'✅\s*TP[\.\s]*(\d+)\s*[:\s]*\(?(\d+\.?\d*)\)?', text, re.IGNORECASE):
        tp_num = int(match.group(1))
        tp_val = float(match.group(2))
        if 1000 <= tp_val <= 9999:
            tps[tp_num] = tp_val

    # Pattern 4: "TP" without number — assign sequential numbers by order of appearance
    # Only used if no numbered TPs were found (avoids conflicts with TP1/TP2/etc.)
    # Handles dot: "TP. 3245", "TP: 3245", "TP 3245", "TP: (3245)"
    if not tps:
        for match in re.finditer(r'\bTP[\.\s]*[:\s]*\(?(\d+\.?\d*)\)?', text, re.IGNORECASE):
            tp_val = float(match.group(1))
            if 1000 <= tp_val <= 9999:
                tp_num = len(tps) + 1
                tps[tp_num] = tp_val

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
    # BUY/SELL patterns must capture optional range (e.g. "4720/4723", "3250-3260")
    entry = _extract_price(text, [r'ENTRY[:\s]*(\d+\.?\d*\s*[-–/]?\s*\d*\.?\d*)', r'OPEN[:\s]*(\d+\.?\d*\s*[-–/]?\s*\d*\.?\d*)',
                                   r'@[:\s]*(\d+\.?\d*\s*[-–/]?\s*\d*\.?\d*)', r'ZONE[:\s]*(\d+\.?\d*[-–]\d+\.?\d*)',
                                   r'BUY[:\s]*(\d+\.?\d*\s*[-–/]?\s*\d*\.?\d*)', r'SELL[:\s]*(\d+\.?\d*\s*[-–/]?\s*\d*\.?\d*)',
                                   r'LONG[:\s]*(\d+\.?\d*\s*[-–/]?\s*\d*\.?\d*)', r'SHORT[:\s]*(\d+\.?\d*\s*[-–/]?\s*\d*\.?\d*)'])

    # If no labeled entry, try to find a standalone price in gold range (1000-5000)
    if entry is None:
        entry = _extract_standalone_price(text)

    if entry is None:
        return None

    # Extract ALL TP levels dynamically
    tps = _extract_all_tps(text)

    # Extract SL — handle "(SL):", "SL:", "SL_", "SL_ ", "SL.", "SL BREAKOUT", "Stop Loss:", "SL: (4565)", etc.
    sl = _extract_price(text, [r'[\(]?SL[\)]?[:\s\-_\.]*\(?(\d+\.?\d*)\)?',
                                r'SL\s+BREAKOUT\s*[:\s\.]*\(?(\d+\.?\d*)\)?',
                                r'SL\s+[A-Z]+\s*[:\s\.]*\(?(\d+\.?\d*)\)?',
                                r'STOP\s*LOSS[:\s\-\.]*\(?(\d+\.?\d*)\)?',
                                r'STOP[:\s\-\.]*\(?(\d+\.?\d*)\)?'])

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

    # Validate gold price range (roughly 1000-9999)
    if entry < 1000 or entry > 9999:
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
    """Extract a price from text using multiple regex patterns.
    Handles ranges like '4720/4723', '3250-3260', '3250–3260' -> midpoint.
    """
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                val = match.group(1)
                # Handle range like "3250-3260", "4720/4723" -> take midpoint
                if re.match(r'\d+\.?\d*\s*[-–/]\s*\d+\.?\d*', val):
                    parts = re.split(r'\s*[-–/]\s*', val)
                    return (float(parts[0]) + float(parts[1])) / 2
                return float(val)
            except (ValueError, IndexError):
                continue
    return None


def _extract_standalone_price(text: str) -> Optional[float]:
    """Extract a standalone gold price (1000-9999 range)."""
    prices = re.findall(r'\b(\d{4}\.?\d{0,2})\b', text)
    for p in prices:
        val = float(p)
        if 1000 <= val <= 9999:
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
