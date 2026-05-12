# Context.md — Gold Trading Channel Analyzer

> **Commande `/maj`** : mettre à jour ce fichier avec les derniers changements du projet.

## 📋 Résumé du projet
Application Streamlit qui analyse et classe les channels Telegram de trading gold par rentabilité réelle. Backtest les signaux contre les vrais prix gold en bougies 1min pour le scalping.

## 🏗️ Architecture
```
onee-tech-app/
├── app.py              # UI Streamlit (7 étapes) + responsive CSS + page détail channel
├── signal_parser.py    # Parse signaux multi-format (superscripts, ranges, parenthèses, dots)
├── format_detector.py  # Détection automatique du format des signaux par channel
├── gold_prices.py      # Prix XAUUSD via Yahoo Finance API directe (chunked 1m) + debug
├── backtester.py       # Backtest vs vrais prix + format-aware parsing
├── scorer.py           # Score composite 0-100 + Sharpe Ratio
├── bot.py              # Script original
├── .env                # Identifiants Telegram (gitignored)
├── .streamlit/config.toml  # Config Streamlit (poll file watcher)
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
- Config: python-dotenv (chargement .env)
- Python: 3.12 (configuré via dashboard Streamlit Cloud)

## 🔍 Format Detector — Détection automatique des formats
`format_detector.py` analyse un échantillon de messages d'un channel et retourne un `FormatProfile` :

**Champs détectés :**
- `direction_style` : text (BUY/SELL), emoji (🟢🔴), arrow (⬆️⬇️)
- `entry_style` : labeled (ENTRY:), inline (BUY 3240), at (@3240), range
- `tp_style` : numbered (TP1/TP2), unnumbered (TP:), emoji (✅), take_profit, superscript (TP¹)
- `sl_style` : standard (SL:), stop_loss, breakout (SL BREAKOUT), emoji (🛑)
- `pair` : XAUUSD, EURUSD, GBPUSD, BTCUSD
- `has_superscripts` : booléen pour les chiffres Unicode
- `signal_density` : % de messages qui sont des signaux
- `confidence` : score de confiance global (0-1)

**Intégration :**
1. `scan_channel_quick()` → scan 50 messages + détection format → retourne `FormatProfile`
2. Format stocké en session_state (converti en dict pour sérialisation)
3. Affiché dans l'UI lors de la sélection (expandable par channel)
4. `analyze_channel_full()` → utilise le profil pour un parsing format-aware (si confiance > 0.3)

**Extensible :** peut être enrichi avec NLP (sentence-transformers) ou LLM (API) pour les formats complexes.

## 📝 Formats de signaux supportés

### Formats TP (22 patterns)
| Format | Exemple |
|---|---|
| `TP{n}: {prix}` | `TP1: 3245` |
| `TP{n} {prix}` | `TP2 3250` |
| `TP{n}-{prix}` | `TP1-3245` |
| `TP{n} (2+ chiffres)` | `TP10: 3300` |
| `(TP{n}): {prix}` | `(TP1): 3245` |
| `TAKE PROFIT {n} {prix}` | `TAKE PROFIT 1 3245` |
| `TAKE PROFIT {mot} {prix}` | `TAKE PROFIT ONE 3245` |
| `✅ TP{n}: {prix}` | `✅ TP1: 3245` |
| `TP: {prix}` (sans numéro) | `TP: 3245` |
| `TP {prix}` (sans numéro) | `TP 3245` |
| `TP¹ {prix}` (superscript) | `TP¹ 3245` |
| `TP.³ {prix}` (superscript+point) | `TP.³ 3260` |
| `TP.{n}: {prix}` (point) | `TP.1: 3245` |
| `TP. {n}: {prix}` (point+espace) | `TP. 1: 3245` |
| `TP {n}: ({prix})` (parenthèses) | `TP1: (3245)` |
| `TAKE PROFIT {n} ({prix})` | `TAKE PROFIT 1 (3245)` |
| Multi TP numérotés | `TP1: 3245 TP2: 3250 TP3: 3260` |
| Minuscule | `tp1: 3245` |
| Emoji + TP | `🎯 TP1: 3245` |

### Formats SL (19 patterns)
| Format | Exemple |
|---|---|
| `SL: {prix}` | `SL: 4565` |
| `SL {prix}` | `SL 4565` |
| `SL_{prix}` | `SL_4565` |
| `SL_ {prix}` | `SL_ 4565` |
| `SL-{prix}` | `SL-4565` |
| `(SL): {prix}` | `(SL): 4565` |
| `SL. {prix}` (point) | `SL. 4565` |
| `SL.{prix}` (point) | `SL.4565` |
| `SL BREAKOUT {prix}` | `SL BREAKOUT 4565` |
| `STOP LOSS {prix}` | `STOP LOSS 4565` |
| `STOP LOSS. {prix}` | `STOP LOSS. 4565` |
| `STOP LOSS: ({prix})` (parenthèses) | `STOP LOSS: (4565)` |
| `SL: ({prix})` (parenthèses) | `SL: (4565)` |
| `SL ({prix})` | `SL (4565)` |
| `Stop Loss (SL): {prix}` | `Stop Loss (SL): 4565` |
| `🛑 SL {prix}` | `🛑 SL 4565` |
| `STOP: {prix}` | `STOP: 4565` |
| Minuscule | `sl: 4565` |

## 📊 Données prix gold — Stratégie de chunking
Yahoo Finance limite les données 1min à 7 jours par requête. Le code utilise le chunking :
- **1min** : jusqu'à 28 jours (4 blocs × 7 jours)
- **5min** : jusqu'à 60 jours (fallback auto)
- **15min/1h** : au-delà (fallback auto)

L'ancienne approche `yfinance` est remplacée par des appels directs à l'API v8 de Yahoo Finance.

### Source de données — Spot vs Futures
- **XAUUSD=X** (spot gold) — essayé en priorité, correspond aux prix affichés sur les charts de trading (MT5 Exness, TradingView)
- **GC=F** (gold futures) — fallback si spot indisponible
- ⚠️ Yahoo Finance a delisté `XAUUSD=X` — le code utilise actuellement `GC=F` avec **ajustement dynamique du premium** (voir bug #8)
- Le premium futures-spot est calculé au moment du signal : `premium = GC=F_open - entry_spot`
- Les TP/SL sont ajustés par ce premium avant comparaison avec les bougies GC=F
- **Canaux de trading** : les signaux utilisent des prix spot (comme sur MT5 Exness), le backtester les compare aux prix futures via l'ajustement premium

## 🔍 Debug — Signaux OPEN avec TP
`check_tp_sl_hit()` retourne des champs debug pour diagnostiquer les signaux restés OPEN :
- `debug_candles_checked` : nombre de bougies examinées
- `debug_price_range` : `(lowest_low, highest_high)` vu pendant le backtest
- `debug_adjusted_tps` : valeurs TP ajustées (après correction premium)
- `debug_adjusted_sl` : valeur SL ajustée
- `premium` : premium futures-spot appliqué

Ces infos s'affichent dans l'UI quand un signal a le résultat "OPEN".

## 🔑 Identifiants Telegram
- API_ID / API_HASH : chargés depuis le fichier `.env` (racine du projet)
- Téléphone : entré dans l'interface Streamlit
- Code de vérification : entré dans l'interface Streamlit
- 2FA: Supporté
- ⚠️ Le fichier `.env` est dans `.gitignore` — jamais commité

## 📊 GitHub
- Repo: https://github.com/slh04ninja-cmyk/onee-tech-app
- Branche: main

## 📈 Métriques de scoring
- **Win Rate** : % de signaux gagnants (TP touché)
- **R:R Ratio** : Risk/Reward moyen (capé à 50)
- **Sharpe Ratio** : rendement ajusté au risque (moyenne PnL / écart-type PnL)
- **PnL Total** : profit total en pips (signaux complétés seulement)
- **Score Composite** : 0-100 (35% WR, 20% R:R, 15% Sharpe, 10% volume, 20% consistance)

## ✅ Fonctionnalités récentes
- **Crash protection complète** : chaque étape (config, code, password, scanning, select, analyzing, detail, results) est wrappée dans try/except avec UI de récupération. Flag `_processing` empêche le re-run pendant les opérations longues (scan, analyse). `run_telethon` gère les timeouts et erreurs de connexion WebSocket.
- **Formats TP/SL étendus** : support pour points (`TP.1: 3245`), parenthèses autour du prix (`SL: (4565)`), SL BREAKOUT, Stop Loss compound (`Stop Loss (SL): 4565`). 22 formats TP + 19 formats SL.
- **Debug OPEN signals** : champs debug dans `check_tp_sl_hit()` (candles_checked, price_range, adjusted_tps, premium) affichés dans l'UI pour les signaux restés OPEN.
- **Format Detector** : détection automatique du format des signaux par channel (direction style, entry style, TP style, SL style, paire, superscripts). Retourne un `FormatProfile` avec score de confiance et parsing hints.
- **Signaux sans TP ignorés** : les signaux incomplets (pas de TP) sont filtrés avant le backtest
- **Sharpe Ratio** : métrique de rendement ajusté au risque ajoutée au scoring
- **Config .env** : API_ID/API_HASH chargés depuis .env, plus besoin de les entrer à chaque test
- **Superscripts Unicode** : TP¹, TP², etc. parsés correctement (conversion en chiffres ASCII)
- **Entry ranges** : `4720/4723` parsé comme midpoint 4721.5
- **Channel IDs affichés** : ID Telegram visible dans la sélection, les résultats, et l'export Excel
- **UI responsive** : CSS mobile-first, métriques empilées, tableaux scrollables
- **Indicateurs de chargement** : progress bars par channel (scan) et par phase (analyse)
- **Page détail channel** : dédiée avec courbe PnL cumulé, répartition W/L, heatmap jour×heure, bar chart PnL/signal

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
**Problème :** Dans `check_tp_sl_hit()`, le SL était vérifié **avant** les TP dans chaque bougie. Si dans la même minute le prix touchait le TP puis le SL, le résultat était "SL" au lieu du TP.

**Fix dans `gold_prices.py` :**
- TP vérifié **en premier** dans chaque bougie
- SL vérifié **seulement** si aucun TP n'a été touché avant ce point

### 11. TP sans numéro non parsé (RÉSOLU)
**Problème :** Le channel écrit `TP 4535` (sans numéro), mais le regex exigeait un chiffre après "TP".

**Fix dans `signal_parser.py` :** Ajout du Pattern 4 (`\bTP\s*[:\s]*(\d+\.?\d*)`) avec attribution séquentielle.

### 12. Plage de prix gold trop restrictive (RÉSOLU)
**Problème :** La validation `1000 ≤ price ≤ 5000` rejetait les prix au-dessus de $5000.

**Fix :** Plage élargie à `1000 ≤ price ≤ 9999`.

### 13. TPs traversés en une bougie non marqués (RÉSOLU)
**Problème :** Pour un SELL avec TPs [4535, 4530, 4525], si le prix descendait à 4528 en une bougie, seul TP1 était marqué.

**Fix :** Suppression du `break` — tous les TPs traversés sont marqués.

### 14. R:R ratio à 0 quand aucune perte (RÉSOLU)
**Fix :** Quand `avg_loss == 0` et `avg_win > 0` → `rr_ratio = MAX_REALISTIC_RR` (50).

### 15. Superscripts Unicode non parsés (RÉSOLU)
**Fix :** `_normalize_superscripts()` convertit `¹²³⁴⁵⁶⁷⁸⁹⁰` en `1234567890`.

### 16. Entry ranges avec `/` non parsés (RÉSOLU)
**Fix :** `_extract_price()` split sur `/`, `-`, `–` → midpoint.

### 17. Parenthèses dans TP patterns (RÉSOLU)
**Fix :** Pattern gère le `)` optionnel après le label TP.

### 18. set_page_config doit être première commande (RÉSOLU)
**Fix :** CSS déplacé après `set_page_config()`.

### 19. Arrow type error sur colonnes TP/SL (RÉSOLU)
**Fix :** Conversion de toutes les valeurs TP/SL en `str()`.

### 20. inotify instance limit sur Streamlit Cloud (RÉSOLU)
**Fix :** `fileWatcherType = "poll"` dans `.streamlit/config.toml`.

### 21. Crash Chrome minimize/restore (RÉSOLU)
**Problème :** Quand Chrome est minimisé puis rouvert, Streamlit perd la connexion WebSocket et relance le script. Si une opération Telethon (scan, analyse) était en cours, le script crashait.

**Fix dans `app.py` :**
- Flag `_processing` dans `session_state` empêche le re-run pendant les opérations longues
- Chaque étape wrappée dans `try/except` avec `show_crash_recovery()` (bouton réinitialisation)
- `run_telethon` amélioré : gère `TimeoutError` et erreurs de connexion proprement, ferme l'event loop même si `shutdown_asyncgens()` échoue

### 22. SL non détecté — formats cassés (RÉSOLU)
**Problème :** Les formats `SL_4565`, `SL BREAKOUT 4565`, `SL. 4565`, `SL.4565`, `STOP LOSS. 4565` n'étaient pas parsés.

**Fix dans `signal_parser.py` :**
- Pattern SL principal : `[\(]?SL[\)]?[:\s\-_\.]*\(?(\d+\.?\d*)\)?`
- Ajout pattern `SL\s+BREAKOUT` et `SL\s+[A-Z]+\s*`
- Ajout support `.` (point) comme séparateur dans tous les patterns SL/TP
- Ajout support parenthèses autour du prix : `SL: (4565)`, `TP1: (3245)`

## ⚠️ Bugs non résolus

### 1. SL PnL positif quand SL du mauvais côté (IDENTIFIÉ)
**Problème :** Quand un signal a le SL en dessous du entry pour un SELL (ou au-dessus pour un BUY), le PnL du SL est positif au lieu de négatif. Exemple : SELL entry=4660, SL=4615 → `(4660-4615)*10 = +450` au lieu de `-450`.

**Cause :** La formule `(entry - sl) * 10` donne un nombre positif quand `entry > sl`. Le code ne vérifie pas que le SL est du bon côté par rapport au entry.

**Fix en attente :** Utiliser `-abs(entry - sl) * 10` pour forcer le PnL du SL à être toujours négatif.

## ⚠️ Sécurité
- API_ID/API_HASH dans `.env` (gitignore) — jamais dans le code
- Repo GitHub **privé**
- ⚠️ Ne jamais partager de tokens/mots de passe dans les messages
