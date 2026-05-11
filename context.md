# Context.md — Gold Trading Channel Analyzer

## 📋 Résumé du projet
Application Streamlit qui analyse et classe les channels Telegram de trading gold par rentabilité réelle. Backtest les signaux contre les vrais prix gold en bougies 1min pour le scalping.

## 🏗️ Architecture
```
onee-tech-app/
├── app.py              # UI Streamlit (7 étapes) + responsive CSS + page détail channel
├── signal_parser.py    # Parse signaux multi-format (superscripts, ranges, parenthèses)
├── gold_prices.py      # Prix XAUUSD via Yahoo Finance API directe (chunked 1m)
├── backtester.py       # Backtest vs vrais prix
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
**Problème :** Dans `check_tp_sl_hit()`, le SL était vérifié **avant** les TP dans chaque bougie. Si dans la même minute le prix touchait le TP puis le SL, le résultat était "SL" au lieu du TP. De plus, le code vérifiait tous les TP dans chaque bougie sans s'arrêter, ce qui marquait TP1 à TP7 comme touchés simultanément.

**Fix dans `gold_prices.py` :**
- TP vérifié **en premier** dans chaque bougie (stop au premier TP touché)
- SL vérifié **seulement** si aucun TP n'a été touché avant ce point
- Logique : une fois un TP touché, le trade est gagnant — pas de retour arrière vers le SL

### 11. TP sans numéro non parsé (RÉSOLU)
**Problème :** Le channel écrit `TP 4535` (sans numéro), mais le regex `TP\s*(\d+)\s*[:\s]*(\d+\.?\d*)` exigeait un chiffre après "TP" (TP**1**, TP**2**, etc.). Seul le pattern fallback "TP:" matchait, et ne captait qu'**un seul** TP → TP2-TP5 étaient ignorés.

**Impact :** Le backtester ne vérifiait que TP1. Si TP2 était touché 16 min plus tard, il était ignoré → PnL sous-estimé.

**Fix dans `signal_parser.py` :**
- Ajout d'un Pattern 4 qui matche `TP` sans numéro (`\bTP\s*[:\s]*(\d+\.?\d*)`)
- Attribution séquentielle des numéros par ordre d'apparition (TP1, TP2, TP3...)
- Pattern 4 activé **seulement** si aucun TP numéroté (TP1/TP2/...) n'a été trouvé

### 12. Plage de prix gold trop restrictive (RÉSOLU)
**Problème :** La validation `1000 ≤ price ≤ 5000` rejetait les prix au-dessus de $5000. L'or étant à ~$4730 en mai 2026 et en hausse, cette limite allait casser prochainement.

**Fix dans `signal_parser.py` :** Plage élargie à `1000 ≤ price ≤ 9999` (entry, TP, standalone price).

### 13. TPs traversés en une bougie non marqués (RÉSOLU)
**Problème :** Pour un SELL avec TPs [4535, 4530, 4525], si le prix descendait à 4528 en une bougie, seul TP1 (4535) était marqué. TP2 (4530) était ignoré même si le prix l'avait traversé. Le code utilisait `break` après le premier TP touché dans une bougie.

**Fix dans `gold_prices.py` :**
- Suppression du `break` après détection d'un TP dans une bougie
- Tous les TPs dont le niveau est traversé sont marqués (pas juste le premier)
- Le SL est vérifié **seulement** si aucun TP n'a été touché au préalable

### 14. R:R ratio à 0 quand aucune perte (RÉSOLU)
**Problème :** Si tous les trades sont gagnants (aucun SL touché), `avg_loss = 0` → `rr_ratio = 0`. Le score composite était pénalisé pour un bon résultat.

**Fix dans `scorer.py` :** Quand `avg_loss == 0` et `avg_win > 0` → `rr_ratio = MAX_REALISTIC_RR` (50).

### 15. Superscripts Unicode non parsés (RÉSOLU)
**Problème :** Les TPs écrits en chiffres Unicode superscripts (`TP¹ 4716`, `TP.² 4712`) n'étaient pas parsés — `\d+` ne matche que les chiffres ASCII.

**Fix dans `signal_parser.py` :** Ajout de `_normalize_superscripts()` qui convertit `¹²³⁴⁵⁶⁷⁸⁹⁰` en `1234567890` avant le parsing.

### 16. Entry ranges avec `/` non parsés (RÉSOLU)
**Problème :** `SELL 4720/4723` — seul `4720` était capturé, le range était perdu.

**Fix dans `signal_parser.py` :** Les patterns BUY/SELL/ENTRY capturent maintenant les ranges (`4720/4723` → midpoint `4721.5`). `_extract_price()` split sur `/`, `-`, `–`.

### 17. Parenthèses dans TP patterns (RÉSOLU)
**Problème :** `Take Profit 1 (TP1): 4671.00` — le `)` entre `TP1` et `:` cassait le regex.

**Fix dans `signal_parser.py` :** Pattern 1 (`TP\s*(\d+)\s*\)?\s*[:\s\-]*`) gère le `)` optionnel. Pattern 2 (`(?:\(.*?\))?`) saute les parenthèles.

### 18. set_page_config doit être première commande (RÉSOLU)
**Problème :** `st.markdown()` (CSS responsive) était appelé avant `st.set_page_config()` → `StreamlitSetPageConfigMustBeFirstCommandError`.

**Fix dans `app.py` :** Déplacer le CSS après `set_page_config()`.

### 19. Arrow type error sur colonnes TP/SL (RÉSOLU)
**Problème :** Les colonnes TP mélangaient `float` (valeurs) et `str` (`"—"` pour les TPs manquants) → `ArrowTypeError` / `ArrowInvalid` à la sérialisation.

**Fix dans `app.py` :** Conversion de toutes les valeurs TP et SL en `str()` avant insertion dans le DataFrame.

### 20. inotify instance limit sur Streamlit Cloud (RÉSOLU)
**Problème :** `OSError: [Errno 24] inotify instance limit reached` — le file watcher de Streamlit atteignait la limite système sur le cloud.

**Fix dans `.streamlit/config.toml` :** `fileWatcherType = "poll"` pour utiliser le polling au lieu d'inotify.

## ⚠️ Bugs non résolus

### 1. Erreur pendant le scan Telegram (EN COURS)
**Problème :** Après connexion Telegram (entrée du code de vérification), l'étape de scan s'arrête avec "Erreur pendant le scan" sans détail.

**Statut :** Diagnostic en cours — traceback complet ajouté pour identifier la cause. Potentiellement lié à :
- Persistance du fichier `gold_session.session` sur Streamlit Cloud (filesystem éphémère)
- Erreur Telethon lors de `client.start()` ou `iter_dialogs()`
- Timeout lors du scan de nombreux channels

**Environnement :** Streamlit Cloud, Python 3.12, Telethon 1.36.0

## ⚠️ Sécurité
- API_ID/API_HASH dans `.env` (gitignore) — jamais dans le code
- Repo GitHub **privé**
- ⚠️ Ne jamais partager de tokens/mots de passe dans les messages
