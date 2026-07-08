"""
Format Detector - Détecte automatiquement le format des signaux d'un channel Telegram.

Analyse un échantillon de messages et retourne un FormatProfile qui guide
le parser pour extraire les signaux correctement.

Architecture:
  1. Rule-based detection (rapide, offline, pas de dépendances)
  2. Extensible pour NLP (sentence-transformers) ou LLM (API) plus tard
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from collections import Counter
from datetime import datetime


# === Format Profiles ===

@dataclass
class FormatProfile:
    """Profil de format d'un channel de trading."""
    channel_id: Optional[int] = None
    channel_name: str = ""

    # Direction patterns
    direction_style: str = "text"  # "text" (BUY/SELL), "emoji" (🟢🔴), "arrow" (📈📉), "mixed"
    direction_keywords: List[str] = field(default_factory=lambda: ["BUY", "SELL"])

    # Entry patterns
    entry_style: str = "labeled"  # "labeled" (ENTRY:), "inline" (BUY 3240), "at" (@3240), "zone"
    entry_keywords: List[str] = field(default_factory=lambda: ["ENTRY", "OPEN", "@"])

    # TP patterns
    tp_style: str = "numbered"  # "numbered" (TP1, TP2), "unnumbered" (TP:), "emoji" (✅), "take_profit"
    tp_labels: List[str] = field(default_factory=lambda: ["TP"])
    has_superscripts: bool = False
    avg_tp_count: float = 1.0

    # SL patterns
    sl_style: str = "standard"  # "standard" (SL:), "stop_loss" (STOP LOSS), "emoji" (🛑)
    sl_labels: List[str] = field(default_factory=lambda: ["SL"])

    # Pair detection
    pair: str = "XAUUSD"
    pair_keywords: List[str] = field(default_factory=lambda: ["XAUUSD", "GOLD", "XAU"])

    # Quality metrics
    signal_density: float = 0.0  # % of messages that are signals (0-1)
    confidence: float = 0.0  # overall detection confidence (0-1)
    sample_size: int = 0
    detected_formats: Dict[str, int] = field(default_factory=dict)

    # Noise patterns to skip
    noise_patterns: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize for storage/transport."""
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "direction_style": self.direction_style,
            "entry_style": self.entry_style,
            "tp_style": self.tp_style,
            "sl_style": self.sl_style,
            "pair": self.pair,
            "signal_density": round(self.signal_density, 2),
            "confidence": round(self.confidence, 2),
            "sample_size": self.sample_size,
            "avg_tp_count": round(self.avg_tp_count, 1),
            "has_superscripts": self.has_superscripts,
        }


# === Detection Rules ===

# Direction patterns
DIRECTION_PATTERNS = {
    "text": [
        r'\b(BUY|SELL)\b',
        r'\b(LONG|SHORT)\b',
        r'\b(BULLISH|BEARISH)\b',
    ],
    "emoji": [
        r'[🟢🔴]',
        r'[📈📉]',
        r'(BUY|SELL).*[🟢🔴🎯💰]',
    ],
    "arrow": [
        r'[⬆️⬇️↗️↘️]',
        r'[🔺🔻]',
    ],
}

# Entry patterns
ENTRY_PATTERNS = {
    "labeled": [
        r'ENTRY[:\s]*\d',
        r'OPEN[:\s]*\d',
        r'ZONE[:\s]*\d',
        r'ENTER[:\s]*\d',
    ],
    "inline": [
        r'\b(BUY|SELL|LONG|SHORT)\s+\d{4}',
    ],
    "at": [
        r'@\s*\d{4}',
    ],
    "range": [
        r'\d{4}\s*[-–/]\s*\d{4}',
    ],
}

# TP patterns
TP_PATTERNS = {
    "numbered": [
        r'TP[\.\s]*\d+\s*[:\s]*\d{4}',
        r'TAKE\s*PROFIT\s*\d',
    ],
    "unnumbered": [
        r'\bTP[\.\s]*[:\s]+\d{4}',
    ],
    "emoji_check": [
        r'✅\s*TP',
        r'TP\s*✅',
    ],
    "take_profit": [
        r'TAKE\s*PROFIT',
    ],
    "superscript": [
        r'TP[\.\s]*[\u00b9\u00b2\u00b3\u2070-\u2079]',
    ],
    "target": [
        r'TARGET\s*\d',
        r'TGT\s*\d',
    ],
}

# SL patterns
SL_PATTERNS = {
    "standard": [
        r'\bSL[\.\s]*[:\s_]*\d',
        r'\bSL\b',
    ],
    "breakout": [
        r'SL\s+BREAKOUT',
    ],
    "stop_loss": [
        r'STOP\s*LOSS',
        r'STOP\s*[:\s\.]*\d{4}',
    ],
    "emoji_stop": [
        r'🛑\s*(SL|STOP)',
        r'(SL|STOP)\s*🛑',
    ],
}

# Noise patterns (non-signal messages)
NOISE_PATTERNS = [
    r'GOOD\s*(MORNING|NIGHT|EVENING)',
    r'(HELLO|WELCOME|THANK)',
    r'(RECAP|RESULT|EDUCATION|MOTIVATION)',
    r'(JOIN|VIP|SUBSCRIBE|PREMIUM)',
    r'SIGNAL\s*WILL',
    r'ANALYSIS\s*ONLY',
    r'NOT\s*SIGNAL',
    r'PIPS\s*(WIN|TOTAL|RESULT)',
]


def _count_pattern_matches(text: str, patterns: List[str]) -> int:
    """Count how many patterns match in text."""
    count = 0
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            count += 1
    return count


def _detect_direction_style(messages: List[Tuple[str, datetime]]) -> Tuple[str, List[str]]:
    """Detect how direction (BUY/SELL) is expressed."""
    style_counts = Counter()
    keywords_found = set()

    for text, _ in messages:
        text_upper = text.upper()
        for style, patterns in DIRECTION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    style_counts[style] += 1
                    # Extract the actual keyword
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        keywords_found.add(match.group(0).strip())
                    break

    if not style_counts:
        return "text", ["BUY", "SELL"]

    best_style = style_counts.most_common(1)[0][0]
    return best_style, list(keywords_found) if keywords_found else ["BUY", "SELL"]


def _detect_entry_style(messages: List[Tuple[str, datetime]]) -> Tuple[str, List[str]]:
    """Detect how entry prices are labeled."""
    style_counts = Counter()
    keywords_found = set()

    for text, _ in messages:
        for style, patterns in ENTRY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    style_counts[style] += 1
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        kw = re.match(r'([A-Z@]+)', match.group(0), re.IGNORECASE)
                        if kw:
                            keywords_found.add(kw.group(0).upper())
                    break

    if not style_counts:
        return "inline", ["ENTRY", "OPEN", "@"]

    best_style = style_counts.most_common(1)[0][0]
    return best_style, list(keywords_found) if keywords_found else ["ENTRY"]


def _detect_tp_style(messages: List[Tuple[str, datetime]]) -> Tuple[str, List[str], bool, float]:
    """Detect TP format: numbered, unnumbered, emoji, etc."""
    style_counts = Counter()
    keywords_found = set()
    has_superscripts = False
    tp_counts = []

    for text, _ in messages:
        text_for_check = text

        # Check superscripts
        if re.search(r'TP[\u00b9\u00b2\u00b3\u2070-\u2079]', text):
            has_superscripts = True

        # Count TPs in this message
        tp_matches = re.findall(r'TP\s*\d+', text, re.IGNORECASE)
        if tp_matches:
            tp_counts.append(len(tp_matches))
        elif re.search(r'\bTP\b', text, re.IGNORECASE):
            tp_counts.append(1)

        for style, patterns in TP_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    style_counts[style] += 1
                    keywords_found.add("TP")
                    break

    avg_tp = sum(tp_counts) / len(tp_counts) if tp_counts else 1.0

    if not style_counts:
        return "numbered", ["TP"], False, 1.0

    best_style = style_counts.most_common(1)[0][0]
    return best_style, list(keywords_found), has_superscripts, avg_tp


def _detect_sl_style(messages: List[Tuple[str, datetime]]) -> Tuple[str, List[str]]:
    """Detect SL format."""
    style_counts = Counter()
    keywords_found = set()

    for text, _ in messages:
        for style, patterns in SL_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    style_counts[style] += 1
                    keywords_found.add("SL")
                    break

    if not style_counts:
        return "standard", ["SL"]

    best_style = style_counts.most_common(1)[0][0]
    return best_style, list(keywords_found) if keywords_found else ["SL"]


def _detect_pair(messages: List[Tuple[str, datetime]]) -> Tuple[str, List[str]]:
    """Detect trading pair."""
    pair_keywords = {
        "XAUUSD": [r'XAUUSD', r'XAU\s*/?\s*USD', r'GOLD', r'🪙'],
        "EURUSD": [r'EUR\s*/?\s*USD', r'EURUSD'],
        "GBPUSD": [r'GBP\s*/?\s*USD', r'GBPUSD'],
        "BTCUSD": [r'BTC\s*/?\s*USD', r'BITCOIN', r'₿'],
    }

    pair_counts = Counter()
    for text, _ in messages:
        text_upper = text.upper()
        for pair, patterns in pair_keywords.items():
            for pattern in patterns:
                if re.search(pattern, text_upper):
                    pair_counts[pair] += 1
                    break

    if not pair_counts:
        return "XAUUSD", ["XAUUSD", "GOLD"]

    best_pair = pair_counts.most_common(1)[0][0]
    return best_pair, pair_keywords.get(best_pair, [best_pair])


def _detect_noise_patterns(messages: List[Tuple[str, datetime]]) -> List[str]:
    """Detect common noise patterns to skip."""
    noise = []
    for pattern in NOISE_PATTERNS:
        count = sum(1 for text, _ in messages if re.search(pattern, text, re.IGNORECASE))
        if count >= 2:  # Pattern appears multiple times = likely noise
            noise.append(pattern)
    return noise


def _has_signal_content(text: str) -> bool:
    """Quick check if a message looks like it could be a trading signal."""
    text_upper = text.upper()

    # Must have a direction keyword
    has_direction = bool(re.search(r'\b(BUY|SELL|LONG|SHORT|BULLISH|BEARISH)\b', text_upper))
    if not has_direction:
        # Check emoji direction
        has_direction = bool(re.search(r'[🟢🔴]', text))

    # Must have a 4-digit number (gold price)
    has_price = bool(re.search(r'\b\d{4}\b', text))

    return has_direction and has_price


def _count_signals(messages: List[Tuple[str, datetime]]) -> int:
    """Count messages that look like signals."""
    return sum(1 for text, _ in messages if _has_signal_content(text))


# === Main Detection Function ===

def detect_format(messages: List[Tuple[str, datetime]],
                   channel_id: Optional[int] = None,
                   channel_name: str = "") -> FormatProfile:
    """
    Analyse un échantillon de messages et retourne un FormatProfile.

    Args:
        messages: List of (text, timestamp) tuples
        channel_id: Telegram channel ID
        channel_name: Channel name

    Returns:
        FormatProfile with detected format characteristics
    """
    if not messages:
        return FormatProfile(
            channel_id=channel_id,
            channel_name=channel_name,
            confidence=0.0,
            sample_size=0,
        )

    # Filter to signal-like messages for analysis
    signal_messages = [(text, ts) for text, ts in messages if _has_signal_content(text)]
    total_messages = len(messages)
    signal_count = len(signal_messages)

    # Use signal messages for format detection, fallback to all messages
    analysis_msgs = signal_messages if signal_messages else messages

    # Detect each aspect
    direction_style, direction_kw = _detect_direction_style(analysis_msgs)
    entry_style, entry_kw = _detect_entry_style(analysis_msgs)
    tp_style, tp_kw, has_supers, avg_tp = _detect_tp_style(analysis_msgs)
    sl_style, sl_kw = _detect_sl_style(analysis_msgs)
    pair, pair_kw = _detect_pair(messages)
    noise = _detect_noise_patterns(messages)

    # Calculate signal density and confidence
    signal_density = signal_count / total_messages if total_messages > 0 else 0

    # Confidence based on:
    # - Number of signal messages found
    # - Consistency of format detection
    # - Sample size
    confidence = 0.0
    if signal_count >= 3:
        confidence += 0.3
    if signal_count >= 10:
        confidence += 0.2
    if direction_style != "text" or entry_style != "inline":
        confidence += 0.2  # Strong format indicators
    if tp_style in ("numbered", "emoji_check"):
        confidence += 0.15
    if sl_style in ("standard", "stop_loss"):
        confidence += 0.15

    # Cap confidence based on sample size
    if total_messages < 5:
        confidence = min(confidence, 0.4)
    elif total_messages < 15:
        confidence = min(confidence, 0.7)

    return FormatProfile(
        channel_id=channel_id,
        channel_name=channel_name,
        direction_style=direction_style,
        direction_keywords=direction_kw,
        entry_style=entry_style,
        entry_keywords=entry_kw,
        tp_style=tp_style,
        tp_labels=tp_kw,
        has_superscripts=has_supers,
        avg_tp_count=avg_tp,
        sl_style=sl_style,
        sl_labels=sl_kw,
        pair=pair,
        pair_keywords=pair_kw,
        signal_density=signal_density,
        confidence=confidence,
        sample_size=total_messages,
        detected_formats={
            "direction": direction_style,
            "entry": entry_style,
            "tp": tp_style,
            "sl": sl_style,
        },
        noise_patterns=noise,
    )


def detect_format_from_scan(messages: list,
                             channel_id: Optional[int] = None,
                             channel_name: str = "") -> FormatProfile:
    """
    Convenience wrapper for scan results (list of (text, timestamp) tuples
    from Telethon).

    Same as detect_format() but handles the Telethon message format.
    """
    return detect_format(messages, channel_id=channel_id, channel_name=channel_name)


# === Format-aware parsing hints ===

def get_parsing_hints(profile: FormatProfile) -> dict:
    """
    Retourne des indices de parsing basés sur le profil détecté.
    Utilisé par signal_parser.py pour adapter son extraction.
    """
    hints = {
        "direction_patterns": [],
        "entry_patterns": [],
        "tp_patterns": [],
        "sl_patterns": [],
        "skip_patterns": profile.noise_patterns,
        "pair": profile.pair,
    }

    # Direction patterns based on detected style
    if profile.direction_style == "emoji":
        hints["direction_patterns"] = [
            r'[🟢].*?(BUY|LONG)',
            r'[🔴].*?(SELL|SHORT)',
            r'(BUY|LONG).*?[🟢]',
            r'(SELL|SHORT).*?[🔴]',
        ]
    elif profile.direction_style == "arrow":
        hints["direction_patterns"] = [
            r'[⬆️↗️].*?(BUY|LONG)',
            r'[⬇️↘️].*?(SELL|SHORT)',
        ]
    else:
        hints["direction_patterns"] = [
            r'\b(BUY|LONG|BULLISH)\b',
            r'\b(SELL|SHORT|BEARISH)\b',
        ]

    # Entry patterns
    if profile.entry_style == "labeled":
        hints["entry_patterns"] = [
            r'ENTRY[:\s]*(\d+\.?\d*\s*[-–/]?\s*\d*\.?\d*)',
            r'OPEN[:\s]*(\d+\.?\d*\s*[-–/]?\s*\d*\.?\d*)',
            r'@[:\s]*(\d+\.?\d*\s*[-–/]?\s*\d*\.?\d*)',
        ]
    elif profile.entry_style == "inline":
        hints["entry_patterns"] = [
            r'(?:BUY|SELL|LONG|SHORT)\s+(\d{4}\.?\d*)',
        ]
    elif profile.entry_style == "at":
        hints["entry_patterns"] = [
            r'@\s*(\d{4}\.?\d*)',
        ]

    # TP patterns
    if profile.tp_style == "numbered":
        hints["tp_patterns"] = [
            r'TP[\.\s]*(\d+)\s*[:\s\-]*\(?(\d+\.?\d*)\)?',
        ]
    elif profile.tp_style == "unnumbered":
        hints["tp_patterns"] = [
            r'\bTP[\.\s]*[:\s]+\(?(\d+\.?\d*)\)?',
        ]
    elif profile.tp_style == "emoji_check":
        hints["tp_patterns"] = [
            r'✅\s*TP[\.\s]*(\d+)\s*[:\s]*\(?(\d+\.?\d*)\)?',
            r'TP[\.\s]*(\d+)\s*✅\s*[:\s]*\(?(\d+\.?\d*)\)?',
        ]
    elif profile.tp_style == "take_profit":
        hints["tp_patterns"] = [
            r'TAKE\s*PROFIT\s*(\d+)?\s*[:\s\-]*\(?(\d+\.?\d*)\)?',
        ]

    if profile.has_superscripts:
        hints["tp_patterns"].insert(0,
            r'TP[\.\s]*[\u00b9\u00b2\u00b3\u2070-\u2079]\s*[:\s\-]*\(?(\d+\.?\d*)\)?'
        )

    # SL patterns
    if profile.sl_style == "standard":
        hints["sl_patterns"] = [
            r'[\(]?SL[\)]?[:\s\-_\.]*\(?(\d+\.?\d*)\)?',
        ]
    elif profile.sl_style == "breakout":
        hints["sl_patterns"] = [
            r'SL\s+BREAKOUT\s*[:\s\.]*\(?(\d+\.?\d*)\)?',
            r'SL\s+[A-Z]+\s*[:\s\.]*\(?(\d+\.?\d*)\)?',
            r'[\(]?SL[\)]?[:\s\-_\.]*\(?(\d+\.?\d*)\)?',
        ]
    elif profile.sl_style == "stop_loss":
        hints["sl_patterns"] = [
            r'STOP\s*LOSS[:\s\-\.]*\(?(\d+\.?\d*)\)?',
            r'STOP[:\s\-\.]*\(?(\d+\.?\d*)\)?',
        ]
    elif profile.sl_style == "emoji_stop":
        hints["sl_patterns"] = [
            r'🛑\s*(?:SL|STOP)[:\s\-]*(\d+\.?\d*)',
            r'(?:SL|STOP)[:\s\-]*(\d+\.?\d*)\s*🛑',
        ]

    return hints
