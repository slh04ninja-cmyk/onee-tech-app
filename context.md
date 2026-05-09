# Context.md — Gold Trading Channel Analyzer

## 📋 Résumé du projet
Application Streamlit qui analyse et classe les channels Telegram de trading gold par rentabilité réelle.

## 🏗️ Architecture
```
onee-tech-app/
├── app.py              # UI Streamlit (6 étapes)
├── signal_parser.py    # Parse signaux multi-format
├── gold_prices.py      # Prix XAUUSD via yfinance
├── backtester.py       # Backtest vs vrais prix
├── scorer.py           # Score composite 0-100
├── bot.py              # Script original
├── requirements.txt
└── README.md
```

## 🔧 Technologies
- Telegram: Telethon (user account)
- Prix gold: yfinance (GC=F / XAUUSD=X)
- UI: Streamlit + Plotly
- Export: openpyxl (Excel)

## 🔑 Identifiants Telegram
- API_ID: `38469571`
- API_HASH: `4a7a530f07d7af72960787e5c53ea906`
- Téléphone: *(non fourni — à configurer dans l'app)*
- 2FA: Non activé
- ⚠️ Auth via Streamlit uniquement

## 📊 GitHub
- Repo: https://github.com/slh04ninja-cmyk/onee-tech-app
- Branche: main
- Dernier commit: `ea62004` (feat: Add gold trading channel analyzer with backtesting)

## 🐛 Bug connu : Event Loop Streamlit

### Symptôme
Erreur sur Streamlit Cloud : `There is no current event loop in thread 'ScriptRunner.scriptThread'`

### Cause
- Streamlit relance tout le script à chaque interaction (rerun)
- Chaque rerun peut être dans un **nouveau thread**
- `asyncio.new_event_loop()` ne persiste pas entre threads
- Le client Telethon perd sa connexion entre les reruns

### Tentatives échouées
1. **`nest_asyncio`** — Ajouté mais ne résout pas le crash du loop
2. **`runtime.txt` (Python 3.11/3.12)** — Streamlit Cloud utilise Python 3.14, `anyio` crash aussi
3. **Event loop global vs session_state** — Même problème, le thread change

### Solution recommandée (pas encore implémentée)
**Approche 1 — Sync wrapper :** Créer un wrapper synchrone autour de Telethon qui gère son propre event loop dans un thread séparé avec `concurrent.futures.ThreadPoolExecutor`.

**Approche 2 — Subprocess :** Lancer les appels Telethon dans un subprocess via `subprocess.run()` pour éviter complètement les problèmes d'event loop.

**Approche 3 — API REST :** Remplacer Telethon direct par une API Telegram (ex: via un bot) qui n'a pas besoin d'user account.

## 🚀 Prochaines étapes
1. Choisir et implémenter une des solutions ci-dessus
2. Tester sur Streamlit Cloud
3. Configurer le numéro de téléphone et l'auth Telegram
4. Révoquer le token GitHub exposé dans le chat (`ghp_l86R...NIe`)

## ⚠️ Sécurité
- Token GitHub exposé dans la conversation Telegram — **à révoquer**
- API_ID/API_HASH dans le code — à déplacer vers les secrets Streamlit
- Repo GitHub **privé**
