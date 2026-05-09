# Context.md — Gold Trading Channel Analyzer

## 📋 Résumé du projet
Application Streamlit qui analyse et classe les channels Telegram de trading gold par rentabilité réelle.

## 🏗️ Architecture
```
onee-tech-app/
├── app.py              # UI Streamlit (6 étapes) + fix event loop
├── signal_parser.py    # Parse signaux multi-format
├── gold_prices.py      # Prix XAUUSD via yfinance
├── backtester.py       # Backtest vs vrais prix
├── scorer.py           # Score composite 0-100
├── bot.py              # Script original
├── requirements.txt    # Dépendances pinnées
├── runtime.txt         # Version Python (non utilisé par Streamlit Cloud)
└── README.md
```

## 🔧 Technologies
- Telegram: Telethon 1.36.0 (user account)
- Prix gold: yfinance (GC=F / XAUUSD=X)
- UI: Streamlit 1.45.0 + Plotly
- Export: openpyxl (Excel)
- Python: 3.12 (configuré via dashboard Streamlit Cloud)

## 🔑 Identifiants Telegram
- API_ID: `38469571`
- API_HASH: `4a7a530f07d7af72960787e5c53ea906`
- Téléphone: *(non fourni — à configurer dans l'app)*
- 2FA: Non activé
- ⚠️ Auth via Streamlit uniquement

## 📊 GitHub
- Repo: https://github.com/slh04ninja-cmyk/onee-tech-app
- Branche: main

## ✅ Bugs résolus

### 1. Event Loop Streamlit (RÉSOLU)
**Approche implémentée : Sync wrapper avec ThreadPoolExecutor**

`run_telethon(coro_func, *args)` crée un event loop frais dans un thread séparé pour chaque appel Telethon. Le fichier `gold_session.session` persiste l'auth entre les appels.

**Points clés du fix :**
- Le client Telethon n'est PAS stocké dans `st.session_state` (inaccessible depuis un thread séparé)
- `api_id`, `api_hash` et `selected_channels` sont capturés dans le thread principal puis passés en paramètres
- Les callbacks de progression (`update_progress`) sont wrappés en try/except pour éviter `NoSessionContext`
- Chaque opération async crée son propre client et le disconnect après usage

### 2. Python 3.14 sur Streamlit Cloud (RÉSOLU)
**Problème :** Streamlit Cloud utilisait Python 3.14 par défaut, ce qui causait un crash de `anyio` (weak reference to NoneType).

**Fix :** Changer la version Python via le **dashboard Streamlit Cloud** :
- share.streamlit.io → App → Settings → Advanced settings → Python version → **3.12**

**Note :** Le fichier `runtime.txt` n'est PAS pris en compte par Streamlit Cloud pour la version Python.

### 3. Streamlit 1.57.0 incompatible (RÉSOLU)
**Fix :** Pinner `streamlit==1.45.0` dans `requirements.txt`

## ⚠️ Sécurité
- Token GitHub exposé dans la conversation Telegram — **à révoquer** (`ghp_l86R...NIe`)
- API_ID/API_HASH dans le code — à déplacer vers les secrets Streamlit
- Repo GitHub **privé**
