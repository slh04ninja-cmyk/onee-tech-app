"""
Channel Scorer - Classe les channels de trading par performance.
Supporte un nombre dynamique de TP (TP1, TP2, ..., TPn).
"""

import re
import math
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class ChannelScore:
    channel_id: int
    channel_name: str
    total_signals: int
    wins: int
    losses: int
    open_signals: int
    win_rate: float  # 0-100
    avg_pnl_pips: float
    total_pnl_pips: float
    risk_reward_ratio: float
    sharpe_ratio: float  # risk-adjusted return
    best_signal_pips: float
    worst_signal_pips: float
    avg_time_to_result_hours: float
    score: float  # composite score 0-100
    signals: list = None


def _is_tp_result(result: str) -> bool:
    """Check if a result string is any TP hit (TP1, TP2, ..., TP99)."""
    return bool(re.match(r'^TP\d+$', result or ''))


def _tp_number(result: str) -> int:
    """Extract TP number from result string. Returns 0 if not a TP."""
    m = re.match(r'^TP(\d+)$', result or '')
    return int(m.group(1)) if m else 0


def score_channels(channel_results: Dict[int, dict]) -> List[ChannelScore]:
    """
    Score and rank channels based on backtest results.

    Args:
        channel_results: {channel_id: {"name": str, "signals": list of signal+result dicts}}

    Returns:
        Sorted list of ChannelScore objects (best first)
    """
    MAX_REALISTIC_RR = 50  # Cap R:R ratio to realistic max for gold scalping

    scores = []

    for ch_id, data in channel_results.items():
        signals = data.get("signals", [])
        if not signals:
            continue

        # Only count completed signals (any TP or SL), exclude OPEN
        completed = [s for s in signals if s.get("result", "") == "SL" or _is_tp_result(s.get("result", ""))]
        wins = sum(1 for s in completed if _is_tp_result(s.get("result", "")))
        losses = sum(1 for s in completed if s.get("result") == "SL")
        opens = sum(1 for s in signals if s.get("result") == "OPEN")
        total = wins + losses

        win_rate = (wins / total * 100) if total > 0 else 0

        # PnL only from completed signals
        pnl_values = [s.get("pnl_pips", 0) for s in completed]
        avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0
        total_pnl = sum(pnl_values)

        best = max(pnl_values) if pnl_values else 0
        worst = min(pnl_values) if pnl_values else 0

        # Risk/Reward ratio — capped to avoid absurd values
        avg_win = sum(p for p in pnl_values if p > 0) / max(wins, 1)
        avg_loss = abs(sum(p for p in pnl_values if p < 0)) / max(losses, 1)
        if avg_loss > 0:
            rr_ratio = min(avg_win / avg_loss, MAX_REALISTIC_RR)
        elif avg_win > 0:
            rr_ratio = MAX_REALISTIC_RR  # No losses = max R:R
        else:
            rr_ratio = 0

        # Sharpe Ratio — risk-adjusted return
        # Sharpe = (mean_return - risk_free) / std_return
        # risk_free = 0 (no meaningful risk-free rate per signal)
        if len(pnl_values) >= 2:
            mean_ret = avg_pnl
            variance = sum((p - mean_ret) ** 2 for p in pnl_values) / (len(pnl_values) - 1)
            std_ret = math.sqrt(variance)
            if std_ret > 0:
                sharpe = round(mean_ret / std_ret, 2)
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0

        # Average time to result
        times = []
        for s in completed:
            # Try to get the time of the highest TP hit or SL
            result = s.get("result", "")
            if _is_tp_result(result):
                tp_idx = _tp_number(result) - 1
                tp_times = s.get("tp_times", [])
                if tp_idx < len(tp_times) and tp_times[tp_idx] and s.get("timestamp"):
                    diff = (tp_times[tp_idx] - s["timestamp"]).total_seconds() / 3600
                    times.append(diff)
            elif s.get("sl_time") and s.get("timestamp"):
                diff = (s["sl_time"] - s["timestamp"]).total_seconds() / 3600
                times.append(diff)
        avg_time = sum(times) / len(times) if times else 0

        # Composite score (0-100)
        # Weighting: win_rate (35%), R:R (20%), Sharpe (15%), volume (10%), consistency (20%)
        volume_bonus = min(total / 10, 1) * 10  # max 10 pts for 10+ signals
        consistency = max(0, 100 - (abs(best - abs(worst)) / max(abs(best), 1) * 100)) if best != 0 else 50
        consistency_bonus = consistency * 0.2
        sharpe_bonus = min(max(sharpe, 0), 3) * 5  # 0-15 pts, cap at Sharpe 3

        composite = (win_rate * 0.35) + (min(rr_ratio * 10, 20)) + sharpe_bonus + volume_bonus + consistency_bonus
        composite = min(composite, 100)

        scores.append(ChannelScore(
            channel_id=ch_id,
            channel_name=data.get("name", "Unknown"),
            total_signals=len(signals),
            wins=wins,
            losses=losses,
            open_signals=opens,
            win_rate=round(win_rate, 1),
            avg_pnl_pips=round(avg_pnl, 1),
            total_pnl_pips=round(total_pnl, 1),
            risk_reward_ratio=round(rr_ratio, 2),
            sharpe_ratio=sharpe,
            best_signal_pips=round(best, 1),
            worst_signal_pips=round(worst, 1),
            avg_time_to_result_hours=round(avg_time, 1),
            score=round(composite, 1),
            signals=signals
        ))

    # Sort by score descending
    scores.sort(key=lambda x: x.score, reverse=True)
    return scores


def format_score_report(scores: List[ChannelScore]) -> str:
    """Format a human-readable report of channel scores."""
    if not scores:
        return "Aucun channel à analyser."

    lines = ["🏆 CLASSEMENT DES CHANNELS TRADING GOLD\n"]
    lines.append("=" * 60)

    for i, s in enumerate(scores, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"

        lines.append(f"\n{medal} {s.channel_name}")
        lines.append(f"   Score: {s.score}/100")
        lines.append(f"   Signaux: {s.total_signals} | ✅ {s.wins} | ❌ {s.losses} | ⏳ {s.open_signals}")
        lines.append(f"   Win Rate: {s.win_rate}%")
        lines.append(f"   R:R Moyen: {s.risk_reward_ratio}")
        lines.append(f"   Sharpe Ratio: {s.sharpe_ratio}")
        lines.append(f"   PnL Total: {s.total_pnl_pips:+.0f} pips")
        lines.append(f"   PnL Moyen: {s.avg_pnl_pips:+.0f} pips/signal")
        lines.append(f"   Meilleur: {s.best_signal_pips:+.0f} pips | Pire: {s.worst_signal_pips:+.0f} pips")
        lines.append(f"   Temps moyen: {s.avg_time_to_result_hours:.1f}h")

    lines.append("\n" + "=" * 60)

    # Summary
    total_wins = sum(s.wins for s in scores)
    total_losses = sum(s.losses for s in scores)
    overall_wr = (total_wins / (total_wins + total_losses) * 100) if (total_wins + total_losses) > 0 else 0

    lines.append(f"\n📊 RÉSUMÉ GLOBAL:")
    lines.append(f"   Channels analysés: {len(scores)}")
    lines.append(f"   Win Rate global: {overall_wr:.1f}%")
    lines.append(f"   Total pips: {sum(s.total_pnl_pips for s in scores):+.0f}")

    best = scores[0] if scores else None
    if best:
        lines.append(f"\n🏆 MEILLEUR CHANNEL: {best.channel_name} ({best.score}/100)")

    return "\n".join(lines)
