# Context.md — Gold Signal Extractor

> **Commande `/maj`** : mettre à jour ce fichier avec les derniers changements du projet.

## 📋 Résumé du projet
Application Streamlit qui extrait les signaux de trading depuis Telegram et les exporte en CSV pour backtesting MQ5/MT5. Un fichier CSV par channel.

## 🏗️ Architecture
```
onee-tech-app/
├── app.py              # UI Streamlit (4 étapes: config, code, scanning, select/export)
├── signal_parser.py    # Parser v8 — extraction robuste des signaux (BUY/SELL, zones, SL auto, multi-TP)
├── csv_exporter.py     # Export CSV par channel + ZIP global
├── bot.py              # Script original (conservé)
├── .env                # Identifiants Telegram (gitignored)
├── .streamlit/config.toml  # Config Streamlit
├── requirements.txt    # Dépendances (telethon, streamlit, pandas, python-dotenv)
├── runtime.txt         # Version Python
├── README.md           # Documentation
├── context.md          # Ce fichier
└── archived/           # Anciens fichiers (v1 parser, backtester, scorer, gold_prices, format_detector)
```

## 🔧 Technologies
- Telegram: Telethon 1.36.0 (user account)
- UI: Streamlit 1.45.0
- Export: CSV natif + zipfile
- Config: python-dotenv
- Python: 3.12

## 📊 CSV Format (pour MQ5)
```csv
datetime,direction,entry,zone_low,zone_high,sl,tp1,tp2,tp3,tp4,tp5,tp6
```
- `entry` : prix unique ou milieu de zone
- `zone_low`/`zone_high` : bornes de zone (identiques si prix unique)
- `tp1`..`tp6` : dynamique (max 6 TPs)
- Filtrage par paire possible (défaut: XAUUSD uniquement)

## 🔍 Signal Parser v8
- **Normalisation agressive** : superscripts, emojis, caractères invisibles, parenthèses
- **Détection de symbole** : XAUUSD, GOLD, XAGUSD, BTCUSD, EURUSD, GBPUSD, etc.
- **Extraction d'entrée** : 12 méthodes (mots-clés, zone, prix collés, séparateurs, etc.)
- **SL auto-généré** si absent (basé sur distance aux TPs)
- **TP auto-généré** si absent (basé sur R:R ratio configurable)
- **Quick alert** : signaux sans TP ni SL → SL/TP provisoires
- **Spam filter** : exclusion des messages de résultat, éducation, etc.
- **Types de signaux** : TRADE, CLOSE, SL_MOVE

## 🔑 Identifiants Telegram
- API_ID / API_HASH : chargés depuis le fichier `.env`
- Téléphone : entré dans l'interface Streamlit
- Code de vérification : entré dans l'interface Streamlit
- 2FA: Supporté

## 📊 GitHub
- Repo: https://github.com/slh04ninja-cmyk/onee-tech-app
- Branche: main

## ✅ Changements récents
- **Refonte complète** : suppression du backtesting Python (gold_prices, backtester, scorer)
- **Nouvel objectif** : extraction CSV pour backtesting MQ5/MT5
- **Parser v8** : remplacement du parser v1 par la version v8 (plus robuste)
- **csv_exporter.py** : nouveau module d'export CSV + ZIP
- **App simplifié** : 4 étapes au lieu de 7
- **Archivage** : anciens fichiers conservés dans `archived/`
