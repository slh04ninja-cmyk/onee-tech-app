"""
Channel Scorer - Classe les channels de trading par performance.
"""

import pandas as pd
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
    best_signal_pips: float
    worst_signal_pips: float
    avg_time_to_result_hours: float
    score: float  # composite score 0-100
    signals: list = None


def score_channels(channel_results: Dict[int, dict]) -> List[ChannelScore]:
    """
    Score and rank channels based on backtest results.
    
    Args:
        channel_results: {channel_id: {"name": str, "signals": list of signal+result dicts}}
    
    Returns:
        Sorted list of ChannelScore objects (best first)
    """
    scores = []
    
    for ch_id, data in channel_results.items():
        signals = data.get("signals", [])
        if not signals:
            continue
        
        wins = sum(1 for s in signals if s.get("result", "").startswith("TP"))
        losses = sum(1 for s in signals if s.get("result") == "SL")
        opens = sum(1 for s in signals if s.get("result") == "OPEN")
        total = wins + losses  # only completed signals count
        
        win_rate = (wins / total * 100) if total > 0 else 0
        
        pnl_values = [s.get("pnl_pips", 0) for s in signals if s.get("result") != "OPEN"]
        avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0
        total_pnl = sum(pnl_values)
        
        best = max(pnl_values) if pnl_values else 0
        worst = min(pnl_values) if pnl_values else 0
        
        # Risk/Reward ratio
        avg_win = sum(p for p in pnl_values if p > 0) / max(wins, 1)
        avg_loss = abs(sum(p for p in pnl_values if p < 0)) / max(losses, 1)
        rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        
        # Average time to result
        times = []
        for s in signals:
            if s.get("tp1_time") and s.get("timestamp"):
                diff = (s["tp1_time"] - s["timestamp"]).total_seconds() / 3600
                times.append(diff)
            elif s.get("sl_time") and s.get("timestamp"):
                diff = (s["sl_time"] - s["timestamp"]).total_seconds() / 3600
                times.append(diff)
        avg_time = sum(times) / len(times) if times else 0
        
        # Composite score (0-100)
        # Weighting: win_rate (40%), R:R (25%), volume (15%), consistency (20%)
        volume_bonus = min(total / 10, 1) * 15  # max 15 pts for 10+ signals
        consistency = 100 - (abs(best - abs(worst)) / max(abs(best), 1) * 100) if best != 0 else 50
        consistency_bonus = consistency * 0.2
        
        composite = (win_rate * 0.4) + (min(rr_ratio * 10, 25)) + volume_bonus + consistency_bonus
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
