# 🏆 Gold Trading Channel Analyzer

Analyse et classe tes channels Telegram de trading gold par rentabilité réelle.

## 🎯 Fonctionnalités

- **Scan automatique** — Détecte quels channels contiennent des signaux de trading
- **Multi-format** — Parse les signaux dans tous les formats (BUY/SELL, ENTRY/TP/SL, etc.)
- **Backtesting** — Vérifie chaque signal contre les vrais prix XAUUSD
- **Scoring** — Classe les channels par win rate, R:R, PnL total
- **Export** — Télécharge les résultats en Excel ou rapport texte

## 📊 Métriques par channel

| Métrique | Description |
|----------|-------------|
| **Score** | Note composite 0-100 (win rate, R:R, volume, consistance) |
| **Win Rate** | % de signaux gagnants |
| **R:R Ratio** | Risk/Reward moyen |
| **PnL Total** | Profit total en pips |
| **Temps moyen** | Durée moyenne pour atteindre TP/SL |

## 🚀 Installation

```bash
pip install -r requirements.txt
```

## 🏃 Lancement

```bash
streamlit run app.py
```

## 📋 Flow

1. **Connexion** — Entre tes identifiants Telegram (API_ID, API_HASH, téléphone)
2. **Scan** — L'app scanne tes channels pour détecter les signaux
3. **Sélection** — Choisis les channels à analyser
4. **Analyse** — Backtesting sur 1 mois de données
5. **Résultats** — Classement + détails + export

## 🔑 Prérequis

- Un compte Telegram avec des channels de trading gold
- API_ID et API_HASH de [my.telegram.org/apps](https://my.telegram.org/apps)

## 📁 Structure

```
onee-tech-app/
├── app.py              # Interface Streamlit principale
├── signal_parser.py    # Parse les signaux de trading
├── gold_prices.py      # Récupère les prix XAUUSD
├── backtester.py       # Backtest les signaux
├── scorer.py           # Score et classe les channels
├── bot.py              # Script original (list channels)
└── requirements.txt    # Dépendances
```

## ⚠️ Sécurité

- Ne partage jamais ton API_HASH ou session
- La session est sauvegardée localement dans `gold_session.session`
- L'app ne stocke aucun message Telegram
