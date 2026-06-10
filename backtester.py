"""
Backtester - Analyse les signaux de trading contre les vrais prix gold.
Supporte un nombre dynamique de TP.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from telethon import TelegramClient
from telethon.tl.types import Channel

from signal_parser import TradeSignal, parse_signal, detect_channel_format
from gold_prices import fetch_gold_prices, check_tp_sl_hit
from scorer import ChannelScore, score_channels
from format_detector import detect_format, FormatProfile, get_parsing_hints


async def fetch_channel_messages(client: TelegramClient, channel_id: int,
                                  days: int = 30) -> list:
    """
    Fetch messages from a Telegram channel.

    Returns: list of (text, timestamp) tuples
    """
    messages = []
    offset_date = datetime.now()
    min_date = datetime.now() - timedelta(days=days)

    try:
        entity = await client.get_entity(channel_id)

        async for message in client.iter_messages(
            entity,
            offset_date=offset_date,
            reverse=False
        ):
            if message.date.replace(tzinfo=None) < min_date:
                break

            if message.text:
                messages.append((message.text, message.date.replace(tzinfo=None)))
    except Exception as e:
        print(f"Error fetching messages from {channel_id}: {e}")

    return messages


async def scan_channel_quick(client: TelegramClient, channel_id: int) -> dict:
    """
    Quick scan of a channel (last 50 messages) to detect if it has trading signals.
    Also runs format detection to build a FormatProfile.

    Returns: {"has_signals": bool, "format": str, "sample_count": int,
             "format_profile": FormatProfile}
    """
    messages = []

    try:
        entity = await client.get_entity(channel_id)

        async for message in client.iter_messages(entity, limit=50):
            if message.text:
                messages.append((message.text, message.date.replace(tzinfo=None)))
    except Exception as e:
        return {"has_signals": False, "format": "error", "error": str(e),
                "sample_count": 0, "format_profile": None}

    signals = []
    for text, ts in messages:
        sig = parse_signal(text, ts)
        if sig:
            signals.append(sig)

    fmt = detect_channel_format(messages)

    # Run format detection for detailed profile
    format_profile = detect_format(
        messages, channel_id=channel_id,
        channel_name=getattr(entity, "title", str(channel_id))
    )

    return {
        "has_signals": len(signals) > 0,
        "format": fmt,
        "sample_count": len(signals),
        "total_messages": len(messages),
        "format_profile": format_profile,
    }


async def analyze_channel_full(client: TelegramClient, channel_id: int,
                                channel_name: str, days: int = 30,
                                gold_prices=None,
                                format_profile: Optional[FormatProfile] = None) -> dict:
    """
    Full analysis of a channel: fetch messages, parse signals, backtest.
    Uses FormatProfile if provided for more accurate signal extraction.

    Returns: {"name": str, "signals": list of signal+result dicts}
    """
    # Fetch messages
    messages = await fetch_channel_messages(client, channel_id, days)

    if not messages:
        return {"name": channel_name, "signals": [], "error": "No messages found"}

    # Parse signals — use format-aware parsing if profile available
    if format_profile and format_profile.confidence > 0.3:
        signals = _parse_with_format(messages, format_profile)
    else:
        signals = parse_signal_list(messages)

    # Ignorer les signaux sans TP (signaux ouverts/incomplets)
    signals = [s for s in signals if s.tps]

    if not signals:
        return {"name": channel_name, "signals": [], "error": "No signals found"}

    # Fetch gold prices if not provided
    if gold_prices is None:
        gold_prices = fetch_gold_prices(days=days + 5, interval="1m")

    # Backtest each signal
    results = []
    for sig in signals:
        if sig.timestamp is None:
            continue

        backtest = check_tp_sl_hit(
            prices=gold_prices,
            signal_time=sig.timestamp,
            direction=sig.direction,
            entry=sig.entry,
            tps=sig.tps,       # dynamic list of TPs
            sl=sig.sl,
            max_hours=48
        )

        result = {
            "direction": sig.direction,
            "entry": sig.entry,
            "tps": sig.tps,               # full list of TPs from signal
            "tp_count": len(sig.tps),      # how many TPs
            "sl": sig.sl,
            "timestamp": sig.timestamp,
            "confidence": sig.confidence,
            "raw_text": sig.raw_text,
            **backtest
        }
        results.append(result)

    return {"name": channel_name, "signals": results}


def parse_signal_list(messages: list) -> List[TradeSignal]:
    """Parse signals from a list of (text, timestamp) tuples."""
    signals = []
    for text, ts in messages:
        sig = parse_signal(text, ts)
        if sig:
            signals.append(sig)
    return signals


def _parse_with_format(messages: list, profile: FormatProfile) -> List[TradeSignal]:
    """
    Parse signals using format profile hints for better accuracy.
    Falls back to standard parsing if format-aware parsing fails.
    """
    hints = get_parsing_hints(profile)
    signals = []

    for text, ts in messages:
        # Skip known noise patterns
        skip = False
        for pattern in hints.get("skip_patterns", []):
            if re.search(pattern, text, re.IGNORECASE):
                skip = True
                break
        if skip:
            continue

        # Try standard parsing first (handles most cases)
        sig = parse_signal(text, ts)
        if sig:
            signals.append(sig)
            continue

        # If format-aware hints suggest this could be a signal, try harder
        if _has_signal_content(text):
            # Retry with relaxed parsing using hints
            sig = _parse_with_hints(text, ts, hints)
            if sig:
                signals.append(sig)

    return signals


def _has_signal_content(text: str) -> bool:
    """Quick check if text looks like a trading signal."""
    text_upper = text.upper()
    has_direction = bool(re.search(r'\b(BUY|SELL|LONG|SHORT|BULLISH|BEARISH)\b', text_upper))
    if not has_direction:
        has_direction = bool(re.search(r'[🟢🔴]', text))
    has_price = bool(re.search(r'\b\d{4}\b', text))
    return has_direction and has_price


def _parse_with_hints(text: str, ts, hints: dict) -> Optional[TradeSignal]:
    """
    Parse a signal using format hints when standard parsing fails.
    This handles edge cases and non-standard formats.
    """
    text_upper = text.upper().strip()

    # Detect direction
    direction = None
    for pattern in hints.get("direction_patterns", []):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            matched_text = match.group(0).upper()
            if any(kw in matched_text for kw in ["BUY", "LONG", "BULLISH", "🟢", "⬆️", "↗️"]):
                direction = "BUY"
            elif any(kw in matched_text for kw in ["SELL", "SHORT", "BEARISH", "🔴", "⬇️", "↘️"]):
                direction = "SELL"
            break

    if not direction:
        return None

    # Extract entry using hints
    entry = None
    for pattern in hints.get("entry_patterns", []):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                val = match.group(1)
                if re.match(r'\d+\.?\d*\s*[-–/]\s*\d+\.?\d*', val):
                    parts = re.split(r'\s*[-–/]\s*', val)
                    entry = (float(parts[0]) + float(parts[1])) / 2
                else:
                    entry = float(val)
                break
            except (ValueError, IndexError):
                continue

    # Fallback: standalone price
    if entry is None:
        prices = re.findall(r'\b(\d{4}\.?\d{0,2})\b', text)
        for p in prices:
            val = float(p)
            if 1000 <= val <= 9999:
                entry = val
                break

    if entry is None or entry < 1000 or entry > 9999:
        return None

    # Extract TPs using hints
    from signal_parser import _extract_all_tps
    tps = _extract_all_tps(text)

    # Extract SL using hints
    sl = None
    for pattern in hints.get("sl_patterns", []):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                sl = float(match.group(1))
                break
            except (ValueError, IndexError):
                continue

    # Confidence
    confidence = 0.3
    if tps:
        confidence += 0.3
    if sl:
        confidence += 0.2

    return TradeSignal(
        direction=direction,
        entry=entry,
        tps=tps,
        sl=sl,
        raw_text=text[:200],
        timestamp=ts,
        confidence=confidence,
    )


async def run_full_analysis(client: TelegramClient,
                             channel_ids: Dict[int, str],
                             days: int = 30,
                             progress_callback=None,
                             format_profiles: Optional[Dict[int, FormatProfile]] = None) -> List[ChannelScore]:
    """
    Run full analysis on multiple channels.

    Args:
        client: Authenticated Telethon client
        channel_ids: {channel_id: channel_name}
        days: Number of days to analyze
        progress_callback: Optional callback(current, total, channel_name)
        format_profiles: Optional {channel_id: FormatProfile} from scan phase

    Returns:
        List of ChannelScore objects, sorted by score
    """
    # Fetch gold prices once (in executor to not block event loop)
    loop = asyncio.get_event_loop()
    gold_prices = await loop.run_in_executor(
        None, lambda: fetch_gold_prices(days=days + 5, interval="1m")
    )

    channel_results = {}
    total = len(channel_ids)

    for i, (ch_id, ch_name) in enumerate(channel_ids.items()):
        if progress_callback:
            try:
                progress_callback(i + 1, total, ch_name)
            except Exception:
                pass

        # Get format profile if available
        profile = format_profiles.get(ch_id) if format_profiles else None

        try:
            result = await analyze_channel_full(
                client, ch_id, ch_name, days, gold_prices,
                format_profile=profile
            )
            channel_results[ch_id] = result
        except Exception as e:
            print(f"Error analyzing channel {ch_name}: {e}")
            channel_results[ch_id] = {"name": ch_name, "signals": [], "error": str(e)}

    return score_channels(channel_results)
