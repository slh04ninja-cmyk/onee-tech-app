# 🏆 Gold Signal Extractor

Extrait les signaux de trading gold depuis Telegram et exporte en CSV pour backtesting MQ5/MT5.

## 🎯 Fonctionnalités

- **Scan automatique** — Détecte les channels Telegram avec signaux de trading
- **Parser robuste** — Supporte BUY/SELL, zones d'entrée, SL auto-généré, multi-TP
- **Export CSV** — Un fichier par channel, format prêt pour MQ5
- **Export ZIP** — Télécharge tous les channels d'un coup
- **Prévisualisation** — Vérifie le CSV avant de télécharger

## 📊 Format CSV

```csv
datetime,direction,entry,zone_low,zone_high,sl,tp1,tp2,tp3,tp4,tp5,tp6
2026-06-15 14:30,BUY,3245.00,3245.00,3245.00,3230.00,3255.00,3265.00,3275.00,,,
2026-06-15 16:00,SELL,3260.00,3255.00,3265.00,3280.00,3240.00,3230.00,,,,,
```

| Colonne | Description |
|---------|-------------|
| `datetime` | Date et heure du signal (YYYY-MM-DD HH:MM) |
| `direction` | BUY ou SELL |
| `entry` | Prix d'entrée (milieu de zone) |
| `zone_low` | Basse de la zone d'entrée |
| `zone_high` | Haute de la zone d'entrée |
| `sl` | Stop Loss |
| `tp1`..`tp6` | Take Profits (1 à 6) |

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
3. **Sélection** — Choisis les channels à exporter
4. **Export** — Télécharge le CSV ou le ZIP

## 🔑 Prérequis

- Un compte Telegram avec des channels de trading gold
- API_ID et API_HASH de [my.telegram.org/apps](https://my.telegram.org/apps)

## 📁 Structure

```
onee-tech-app/
├── app.py              # Interface Streamlit
├── signal_parser.py    # Parse les signaux de trading (v8)
├── csv_exporter.py     # Export CSV pour MQ5
├── bot.py              # Script original (conservé)
├── .env                # Identifiants Telegram (gitignored)
├── requirements.txt    # Dépendances
└── archived/           # Anciens fichiers (backtester, scorer, etc.)
```

## 📂 Pour le backtesting MQ5

1. Exporte le ZIP depuis l'app
2. Place les CSV dans le dossier `Files` de MT5
3. Lance le script MQ5 qui lit le CSV et exécute le backtesting

## ⚠️ Sécurité

- Ne partage jamais ton API_HASH ou session
- La session est sauvegardée localement dans `gold_session.session`
- Le fichier `.env` est dans `.gitignore`
