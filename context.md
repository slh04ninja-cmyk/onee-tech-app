# Context.md — Gold Trading Channel Analyzer

## 📋 Résumé du projet
Application Streamlit qui analyse et classe les channels Telegram de trading gold par rentabilité réelle. Backtest les signaux contre les vrais prix gold en bougies 1min pour le scalping.

## 🏗️ Architecture
```
onee-tech-app/
├── app.py              # UI Streamlit (6 étapes) + fix event loop
├── signal_parser.py    # Parse signaux multi-format
├── gold_prices.py      # Prix XAUUSD via Yahoo Finance API directe (chunked 1m)
├── backtester.py       # Backtest vs vrais prix
├── scorer.py           # Score composite 0-100 (PnL sur signaux complétés seulement)
├── bot.py              # Script original
├── requirements.txt    # Dépendances pinnées
├── runtime.txt         # Version Python (non utilisé par Streamlit Cloud)
└── README.md
```

## 🔧 Technologies
- Telegram: Telethon 1.36.0 (user account)
- Prix gold: **Yahoo Finance API directe** (GC=F) — chunking 7 jours pour données 1min
- UI: Streamlit 1.45.0 + Plotly
- Export: openpyxl (Excel)
- HTTP: requests (appels API directs)
- Python: 3.12 (configuré via dashboard Streamlit Cloud)

## 📊 Données prix gold — Stratégie de chunking
Yahoo Finance limite les données 1min à 7 jours par requête. Le code utilise le chunking :
- **1min** : jusqu'à 28 jours (4 blocs × 7 jours)
- **5min** : jusqu'à 60 jours (fallback auto)
- **15min/1h** : au-delà (fallback auto)

L'ancienne approche `yfinance` est remplacée par des appels directs à l'API v8 de Yahoo Finance.

## 🔑 Identifiants Telegram
- API_ID: *(à configurer dans l'app — déplacé hors du code)*
- API_HASH: *(à configurer dans l'app — déplacé hors du code)*
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

### 4. API_ID validation — erreur struct pack (RÉSOLU)
**Problème :** `'i' format requires -2147483648 ≤ number ≤ 2147483647` — l'API_ID dépassait la limite 32-bit signé de Telethon.

**Fix :** Ajout de `validate_api_id()` qui vérifie le range 32-bit et distingue API_ID (nombre court) de API_HASH (hex 32 chars).

### 5. Session Telegram persistante après déconnexion (RÉSOLU)
**Problème :** Le fichier `gold_session.session` n'était pas supprimé à la déconnexion, donc la connexion automatique sautait la demande de code.

**Fix :** Suppression du fichier `.session` au clic sur "Se déconnecter".

### 6. PnL et R:R ratio incorrects (RÉSOLU)
**Problème :** Le PnL incluait les signaux OPEN (non résolus), et le R:R ratio pouvait atteindre 2107 (absurde).

**Fix dans `scorer.py` :**
- PnL calculé **seulement** sur les signaux complétés (TP1/TP2/TP3/SL)
- R:R ratio **capé à 50** max
- Best/worst pips seulement sur signaux complétés

### 7. Données 1min limitées à 7 jours (RÉSOLU)
**Problème :** `yfinance` limitait les données 1min à 7 jours d'historique.

**Fix :** Remplacement par appels directs à l'API Yahoo Finance avec chunking (blocs de 7 jours). Permet jusqu'à 28 jours de données 1min.

## ⚠️ Sécurité
- ~~Token GitHub exposé dans la conversation Telegram~~ — **à révoquer** (tokens `ghp_l86R...NIe` et `ghp_oA1...bgi`)
- API_ID/API_HASH ne doivent plus être dans le code — à configurer via les secrets Streamlit
- Repo GitHub **privé**
