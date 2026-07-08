"""
CSV Exporter — Exporte les signaux de trading par channel au format CSV pour MQ5/MT5.

Format CSV :
  datetime,direction,entry,zone_low,zone_high,sl,tp1,tp2,tp3,tp4,tp5,tp6

Chaque channel génère un fichier séparé nommé :
  {channel_name}_{channel_id}.csv
"""

import csv
import re
import io
import zipfile
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from signal_parser import TradeSignal


# Nombre max de TPs dans le CSV (colonnes tp1..tpN)
MAX_TPS = 6


def _sanitize_filename(name: str) -> str:
    """Nettoie un nom de channel pour l'utiliser comme nom de fichier."""
    # Garder alphanumériques, espaces, tirets, underscores
    clean = re.sub(r'[^\w\s\-]', '', name)
    clean = re.sub(r'\s+', '_', clean.strip())
    return clean[:50]  # Limiter la longueur


def signals_to_csv(signals: List[TradeSignal], channel_name: str,
                   channel_id: int, pair_filter: str = "XAUUSD") -> str:
    """
    Convertit une liste de signaux en contenu CSV.

    Args:
        signals: Liste de TradeSignal parsés
        channel_name: Nom du channel
        channel_id: ID Telegram du channel
        pair_filter: Filtrer sur cette paire (défaut XAUUSD)

    Returns:
        Contenu CSV sous forme de string
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    header = ["datetime", "direction", "entry", "zone_low", "zone_high", "sl"]
    for i in range(1, MAX_TPS + 1):
        header.append(f"tp{i}")
    writer.writerow(header)

    # Lignes
    for sig in signals:
        # Filtrer sur la paire
        if pair_filter and sig.pair.upper() != pair_filter.upper():
            continue

        # Filtrer les signaux non-TRADE (CLOSE, SL_MOVE)
        if sig.signal_type != "TRADE":
            continue

        # Date/heure
        dt_str = ""
        if sig.timestamp:
            dt_str = sig.timestamp.strftime("%Y-%m-%d %H:%M")

        # Direction
        direction = sig.direction or ""

        # Entry (milieu de zone)
        entry = ""
        if sig.entry is not None:
            entry = f"{sig.entry:.2f}"

        # Zone
        zone_low = ""
        zone_high = ""
        if sig.zone_low is not None:
            zone_low = f"{sig.zone_low:.2f}"
        if sig.zone_high is not None:
            zone_high = f"{sig.zone_high:.2f}"

        # SL
        sl = ""
        if sig.sl is not None:
            sl = f"{sig.sl:.2f}"

        # TPs (max 6)
        tp_values = []
        for i in range(MAX_TPS):
            if i < len(sig.tps):
                tp_values.append(f"{sig.tps[i]:.2f}")
            else:
                tp_values.append("")

        row = [dt_str, direction, entry, zone_low, zone_high, sl] + tp_values
        writer.writerow(row)

    return output.getvalue()


def export_channel_csv(signals: List[TradeSignal], channel_name: str,
                       channel_id: int, output_dir: str,
                       pair_filter: str = "XAUUSD") -> str:
    """
    Exporte les signaux d'un channel dans un fichier CSV.

    Args:
        signals: Liste de TradeSignal
        channel_name: Nom du channel
        channel_id: ID Telegram
        output_dir: Répertoire de sortie
        pair_filter: Filtrer sur cette paire

    Returns:
        Chemin du fichier CSV créé
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    filename = f"{_sanitize_filename(channel_name)}_{channel_id}.csv"
    filepath = Path(output_dir) / filename

    csv_content = signals_to_csv(signals, channel_name, channel_id, pair_filter)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        f.write(csv_content)

    return str(filepath)


def create_zip_from_channels(channel_signals: Dict[int, dict],
                              pair_filter: str = "XAUUSD") -> bytes:
    """
    Crée un ZIP contenant un CSV par channel.

    Args:
        channel_signals: {channel_id: {"name": str, "signals": [TradeSignal]}}
        pair_filter: Filtrer sur cette paire

    Returns:
        Contenu du ZIP en bytes
    """
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for ch_id, data in channel_signals.items():
            ch_name = data.get("name", f"channel_{ch_id}")
            signals = data.get("signals", [])

            if not signals:
                continue

            csv_content = signals_to_csv(signals, ch_name, ch_id, pair_filter)

            # Vérifier qu'il y a au moins une ligne de données (pas juste le header)
            lines = csv_content.strip().split("\n")
            if len(lines) <= 1:
                continue

            filename = f"{_sanitize_filename(ch_name)}_{ch_id}.csv"
            zf.writestr(filename, csv_content)

    return zip_buffer.getvalue()


def get_export_summary(channel_signals: Dict[int, dict],
                       pair_filter: str = "XAUUSD") -> List[dict]:
    """
    Retourne un résumé des exports (pour affichage UI).

    Returns:
        Liste de dicts avec: channel_name, channel_id, total_signals, filtered_signals, filename
    """
    summary = []

    for ch_id, data in channel_signals.items():
        ch_name = data.get("name", f"channel_{ch_id}")
        signals = data.get("signals", [])

        # Signaux TRADE uniquement + filtre paire
        filtered = [
            s for s in signals
            if s.signal_type == "TRADE"
            and (not pair_filter or s.pair.upper() == pair_filter.upper())
        ]

        filename = f"{_sanitize_filename(ch_name)}_{ch_id}.csv"

        summary.append({
            "channel_name": ch_name,
            "channel_id": ch_id,
            "total_signals": len(signals),
            "filtered_signals": len(filtered),
            "filename": filename,
        })

    summary.sort(key=lambda x: x["filtered_signals"], reverse=True)
    return summary
