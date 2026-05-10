"""
Backtester - Analyse les signaux de trading contre les vrais prix gold.
Supporte un nombre dynamique de TP.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from telethon import TelegramClient
from telethon.tl.types import Channel

from signal_parser import TradeSignal, parse_signal, detect_channel_format
from gold_prices import fetch_gold_prices, check_tp_sl_hit
from scorer import ChannelScore, score_channels


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
    Quick scan of a channel (last 20 messages) to detect if it has trading signals.

    Returns: {"has_signals": bool, "format": str, "sample_count": int}
    """
    messages = []

    try:
        entity = await client.get_entity(channel_id)

        async for message in client.iter_messages(entity, limit=20):
            if message.text:
                messages.append((message.text, message.date.replace(tzinfo=None)))
    except Exception as e:
        return {"has_signals": False, "format": "error", "error": str(e), "sample_count": 0}

    signals = []
    for text, ts in messages:
        sig = parse_signal(text, ts)
        if sig:
            signals.append(sig)

    fmt = detect_channel_format(messages)

    return {
        "has_signals": len(signals) > 0,
        "format": fmt,
        "sample_count": len(signals),
        "total_messages": len(messages)
    }


async def analyze_channel_full(client: TelegramClient, channel_id: int,
                                channel_name: str, days: int = 30,
                                gold_prices=None) -> dict:
    """
    Full analysis of a channel: fetch messages, parse signals, backtest.

    Returns: {"name": str, "signals": list of signal+result dicts}
    """
    # Fetch messages
    messages = await fetch_channel_messages(client, channel_id, days)

    if not messages:
        return {"name": channel_name, "signals": [], "error": "No messages found"}

    # Parse signals
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


async def run_full_analysis(client: TelegramClient,
                             channel_ids: Dict[int, str],
                             days: int = 30,
                             progress_callback=None) -> List[ChannelScore]:
    """
    Run full analysis on multiple channels.

    Args:
        client: Authenticated Telethon client
        channel_ids: {channel_id: channel_name}
        days: Number of days to analyze
        progress_callback: Optional callback(current, total, channel_name)

    Returns:
        List of ChannelScore objects, sorted by score
    """
    # Fetch gold prices once
    gold_prices = fetch_gold_prices(days=days + 5, interval="1m")

    channel_results = {}
    total = len(channel_ids)

    for i, (ch_id, ch_name) in enumerate(channel_ids.items()):
        if progress_callback:
            progress_callback(i + 1, total, ch_name)

        result = await analyze_channel_full(
            client, ch_id, ch_name, days, gold_prices
        )
        channel_results[ch_id] = result

    return score_channels(channel_results)
