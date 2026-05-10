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
- Prix gold: **Yahoo Finance API directe** — XAUUSD=X (spot) priorité, GC=F (futures) fallback avec ajustement premium
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

### Source de données — Spot vs Futures
- **XAUUSD=X** (spot gold) — essayé en priorité, correspond aux prix affichés sur les charts de trading
- **GC=F** (gold futures) — fallback si spot indisponible
- ⚠️ Yahoo Finance a delisté `XAUUSD=X` — le code utilise actuellement `GC=F` avec **ajustement dynamique du premium** (voir bug #8)
- Le premium futures-spot est calculé au moment du signal : `premium = GC=F_open - entry_spot`
- Les TP/SL sont ajustés par ce premium avant comparaison avec les bougies GC=F

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

### 8. GC=F (futures) ≠ XAUUSD (spot) — prix décalés (RÉSOLU)
**Problème :** Le backtester utilisait `GC=F` (gold futures) qui trade à ~$20-40 de premium vs le spot gold (XAUUSD). Les signaux Telegram référencent les prix spot, donc les TP/SL étaient comparés aux mauvais prix → résultats de backtest complètement faux.

**Fix dans `gold_prices.py` :**
- `fetch_gold_prices()` essaie `XAUUSD=X` (spot) en premier, fallback `GC=F` (futures)
- `check_tp_sl_hit()` calcule le premium dynamiquement : `premium = GC=F_open - entry_spot`
- Les TP/SL sont ajustés par ce premium avant comparaison avec les bougies
- Le PnL utilise les valeurs spot originales (pas les prix ajustés)

### 9. SL non parsé — regex cassé (RÉSOLU)
**Problème :** Le pattern regex SL `[\(]?SL[\)][:\s\-]*` exigeait un `)` après SL. Donc `SL: 4619` ou `SL 4619` ne matchaient pas — seul `(SL): 4619` marchait.

**Fix dans `signal_parser.py` :** `[\)]` → `[\)]?` (parenthèse fermante optionnelle)

### 10. Ordre SL/TP inversé dans le backtester (RÉSOLU)
**Problème :** Dans `check_tp_sl_hit()`, le SL était vérifié **avant** les TP dans chaque bougie. Si dans la même minute le prix touchait le TP puis le SL, le résultat était "SL" au lieu du TP. De plus, le code vérifiait tous les TP dans chaque bougie sans s'arrêter, ce qui marquait TP1 à TP7 comme touchés simultanément.

**Fix dans `gold_prices.py` :**
- TP vérifié **en premier** dans chaque bougie (stop au premier TP touché)
- SL vérifié **seulement** si aucun TP n'a été touché avant ce point
- Logique : une fois un TP touché, le trade est gagnant — pas de retour arrière vers le SL

## ⚠️ Sécurité
- ~~Token GitHub exposé dans la conversation Telegram~~ — **à révoquer** (tokens `ghp_l86R...NIe`, `ghp_oA1...bgi` et `ghp_FZq...MLF`)
- API_ID/API_HASH ne doivent plus être dans le code — à configurer via les secrets Streamlit
- Repo GitHub **privé**
