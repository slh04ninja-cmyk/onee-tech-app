"""
Gold Trading Channel Analyzer - App Streamlit
Analyse et classe les channels Telegram de trading gold par rentabilité.
"""

import asyncio
import concurrent.futures
import os
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
from telethon import TelegramClient
from telethon.tl.types import Channel
import plotly.express as px
import plotly.graph_objects as go

from signal_parser import parse_signal, TradeSignal
from gold_prices import fetch_gold_prices, check_tp_sl_hit
from backtester import scan_channel_quick, run_full_analysis
from scorer import ChannelScore, score_channels, format_score_report

# Charger les variables d'environnement depuis .env
load_dotenv()

# Lire les identifiants Telegram depuis les variables d'environnement
ENV_API_ID = os.getenv("API_ID", "")
ENV_API_HASH = os.getenv("API_HASH", "")


# === API_ID Validation ===

def validate_api_id(raw: str) -> int:
    """Valide et retourne l'API_ID Telegram (doit être un entier 32-bit signé)."""
    try:
        val = int(str(raw).strip())
    except (ValueError, TypeError):
        raise ValueError(
            "API_ID doit être un nombre entier (ex: 12345678). "
            "Tu as peut-être entré l'API_HASH à la place. "
            "Trouve-le sur my.telegram.org/apps"
        )
    if not (-2147483648 <= val <= 2147483647):
        raise ValueError(
            f"API_ID ({val}) est trop grand. Tu as probablement entré l'API_HASH "
            "(qui est un code hexadécimal) à la place de l'API_ID. "
            "L'API_ID est un nombre court comme 12345678."
        )
    if val == 0:
        raise ValueError("API_ID ne peut pas être 0. Obtien-le sur my.telegram.org/apps")
    return val


# === Sync Telethon Wrapper ===
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def run_telethon(coro_func, *args, **kwargs):
    """Exécute une coroutine Telethon dans un thread avec son propre event loop.

    Résilient aux déconnexions WebSocket (Chrome minimize/restore).
    """
    def _wrapper():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro_func(*args, **kwargs))
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass
    try:
        return _executor.submit(_wrapper).result(timeout=180)
    except concurrent.futures.TimeoutError:
        raise Exception("⏱️ Timeout: l'opération Telegram a pris trop de temps. Réessaie.")
    except Exception as e:
        # Re-raise with cleaner message for connection errors
        err = str(e)
        if "connection" in err.lower() or "websocket" in err.lower():
            raise Exception(f"🔌 Connexion perdue: {err}")
        raise


# === Async helpers ===

async def _send_code(api_id_val: int, api_hash_val: str, phone: str):
    client = TelegramClient("gold_session", api_id_val, api_hash_val)
    await client.connect()
    try:
        if await client.is_user_authorized():
            return None
        result = await client.send_code_request(phone)
        return result
    finally:
        await client.disconnect()


async def _sign_in_code(api_id_val: int, api_hash_val: str, phone: str, code: str, phone_code_hash: str):
    client = TelegramClient("gold_session", api_id_val, api_hash_val)
    await client.connect()
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
    finally:
        await client.disconnect()


async def _sign_in_password(api_id_val: int, api_hash_val: str, password: str):
    client = TelegramClient("gold_session", api_id_val, api_hash_val)
    await client.connect()
    try:
        await client.sign_in(password=password)
    finally:
        await client.disconnect()


# === Helper: Build PnL curve data ===
def build_pnl_curve(signals: list) -> pd.DataFrame:
    """Build cumulative PnL curve from signal list."""
    if not signals:
        return pd.DataFrame()

    rows = []
    cumulative = 0.0
    for sig in signals:
        pnl = sig.get("pnl_pips", 0)
        result = sig.get("result", "OPEN")
        if result in ("TP1", "TP2", "TP3", "TP4", "TP5", "TP6", "TP7", "SL"):
            cumulative += pnl
        ts = sig.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.strptime(ts, "%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                ts = None
        rows.append({
            "Date": ts,
            "PnL": pnl,
            "Cumulé": cumulative,
            "Résultat": result,
            "Direction": sig.get("direction", "?"),
            "Entry": sig.get("entry", 0),
        })
    return pd.DataFrame(rows)


# === Page Config ===
st.set_page_config(
    page_title="Gold Channel Analyzer",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="auto"
)

# === Responsive CSS (must be after set_page_config) ===
st.markdown("""
<style>
/* Mobile-first responsive tweaks */
@media (max-width: 768px) {
    .block-container { padding: 1rem 0.5rem !important; }
    [data-testid="stMetric"] { padding: 0.4rem 0.6rem; }
    [data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
    [data-testid="stMetricValue"] { font-size: 1.1rem !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 0.25rem; }
    .stTabs [data-baseweb="tab"] { padding: 0.4rem 0.6rem; font-size: 0.8rem; }
    .stDataFrame { font-size: 0.8rem; }
    h1 { font-size: 1.4rem !important; }
    h2, h3 { font-size: 1.1rem !important; }
}

/* Tablet tweaks */
@media (min-width: 769px) and (max-width: 1024px) {
    .block-container { padding: 1rem 1.5rem !important; }
}

/* Scrollable dataframe on mobile */
[data-testid="stDataFrame"] > div {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}

/* PnL colors */
.pnl-positive { color: #00c853; font-weight: bold; }
.pnl-negative { color: #ff1744; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.title("🏆 Gold Trading Channel Analyzer")
st.markdown("Analyse et classe tes channels Telegram de trading gold par rentabilité réelle.")

# === Crash Protection ===
# When Chrome is minimized/restored, Streamlit loses the WebSocket connection
# and reruns the script from the top. If a long operation (scan, analyze) was
# in progress, this causes a crash. We protect against this by:
# 1. Wrapping every step in try/except with a recovery UI
# 2. Using a processing flag to skip re-execution during long operations
# 3. Catching telethon/connection errors globally

def show_crash_recovery(error_msg: str = ""):
    """Show a recovery UI when a step crashes."""
    st.error("⚠️ Une erreur est survenue (connexion perdue ?).")
    if error_msg:
        with st.expander("Détails de l'erreur"):
            st.code(str(error_msg), language="python")
    st.info("Clique ci-dessous pour réinitialiser et recommencer.")
    if st.button("🔄 Réinitialiser", key=f"reset_crash_{st.session_state.get('step', 'unknown')}"):
        # Clean up session files
        for sess_file in ["gold_session.session", "gold_session.session-journal"]:
            if os.path.exists(sess_file):
                try:
                    os.remove(sess_file)
                except OSError:
                    pass
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# === Session State ===
defaults = {
    "step": "config",
    "phone": "",
    "channels": [],
    "trading_channels": [],
    "selected_channels": {},
    "analysis_results": None,
    "phone_code_hash": "",
    "logged_in": False,
    "detail_channel": None,  # channel_id for detail view
    "format_profiles": {},  # {channel_id: dict}
    "_processing": False,  # anti-re-run guard during long operations
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def safe_reset():
    """Reset session state to defaults if data is corrupted."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    for k, v in defaults.items():
        st.session_state[k] = v
    st.rerun()


# === Sidebar ===
with st.sidebar:
    st.header("⚙️ Configuration")
    if ENV_API_ID and ENV_API_HASH:
        st.success("✅ Identifiants Telegram chargés depuis .env")
    else:
        st.error("❌ API_ID / API_HASH manquants dans .env")
        st.info("Ajoute-les dans le fichier `.env` à la racine du projet")
    st.divider()
    st.header("📊 Paramètres d'analyse")
    analysis_days = st.slider("Jours d'historique", 7, 90, 30)
    max_hours = st.slider("Max heures pour TP/SL", 1, 72, 48)


def is_likely_trading_channel(title: str) -> bool:
    keywords = [
        "gold", "xauusd", "trading", "signal", "forex", "trade",
        "pips", "scalp", "invest", "crypto", "fx", "market",
        "analyse", "analysis", "vip", "premium"
    ]
    return any(kw in title.lower() for kw in keywords)


# === STEP 1: Config & Login ===
if st.session_state.step == "config":
    try:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("📱 Connexion Telegram")
            phone = st.text_input("Numéro de téléphone", placeholder="+212XXXXXXXXX")
            if st.button("📨 Envoyer le code", type="primary"):
                if not ENV_API_ID or not ENV_API_HASH:
                    st.error("API_ID et API_HASH doivent être configurés dans le fichier `.env`")
                elif not phone:
                    st.error("Entre ton numéro de téléphone.")
                else:
                    try:
                        _api_id = validate_api_id(ENV_API_ID)
                    except ValueError as e:
                        st.error(str(e))
                        st.stop()
                    with st.spinner("🔄 Connexion à Telegram..."):
                        try:
                            result = run_telethon(_send_code, _api_id, ENV_API_HASH, phone)
                            st.session_state.phone = phone
                            if result is None:
                                st.session_state.logged_in = True
                                st.session_state.step = "scanning"
                                st.toast("✅ Session Telegram existante — connexion automatique", icon="🔑")
                            else:
                                st.session_state.phone_code_hash = result.phone_code_hash
                                st.session_state.step = "code"
                            st.rerun()
                        except Exception as e:
                            err_msg = str(e)
                            if "api_id" in err_msg.lower() or "api_hash" in err_msg.lower() or "invalid" in err_msg.lower():
                                st.error(
                                    f"❌ **API_ID/API_HASH invalide**\n\n"
                                    f"Vérifie les valeurs dans le fichier `.env` :\n"
                                    f"- **API_ID** = un nombre entier court (ex: `12345678`)\n"
                                    f"- **API_HASH** = un code hexadécimal de 32 caractères (ex: `a1b2c3d4e5f6...`)\n\n"
                                    f"⚠️ Ne les inverse pas !"
                                )
                            else:
                                st.error(f"Erreur: {e}")
        with col2:
            st.info("""
            **Configuration requise**
            Les identifiants Telegram doivent être dans le fichier `.env` :
            ```
            API_ID=12345678
            API_HASH=a1b2c3d4...
            ```
            Obtén-les sur [my.telegram.org/apps](https://my.telegram.org/apps)
            """)
    except Exception as e:
        show_crash_recovery(e)


# === STEP 2: Verification Code ===
elif st.session_state.step == "code":
    try:
        st.subheader("🔑 Code de vérification")
        st.info(f"Code envoyé à **{st.session_state.phone}**")
        code = st.text_input("Entre le code reçu", placeholder="12345")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Vérifier", type="primary"):
                if not code:
                    st.error("Entre le code.")
                else:
                    with st.spinner("🔄 Vérification..."):
                        try:
                            run_telethon(
                                _sign_in_code,
                                validate_api_id(ENV_API_ID),
                                ENV_API_HASH,
                                st.session_state.phone,
                                code,
                                st.session_state.phone_code_hash
                            )
                            st.session_state.logged_in = True
                            st.session_state.step = "scanning"
                            st.rerun()
                        except Exception as e:
                            err = str(e).lower()
                            if "password" in err or "2fa" in err:
                                st.session_state.step = "password"
                                st.rerun()
                            else:
                                st.error(f"Erreur: {e}")
        with col2:
            if st.button("↩️ Retour"):
                st.session_state.step = "config"
                st.rerun()
    except Exception as e:
        show_crash_recovery(e)


# === STEP 2b: 2FA ===
elif st.session_state.step == "password":
    try:
        st.subheader("🔐 Mot de passe 2FA")
        password = st.text_input("Mot de passe Telegram", type="password")
        if st.button("✅ Se connecter", type="primary"):
            with st.spinner("🔄 Vérification du mot de passe..."):
                try:
                    run_telethon(
                        _sign_in_password,
                        validate_api_id(ENV_API_ID),
                        ENV_API_HASH,
                        password
                    )
                    st.session_state.logged_in = True
                    st.session_state.step = "scanning"
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur: {e}")
    except Exception as e:
        show_crash_recovery(e)


# === STEP 3: Scan Channels ===
elif st.session_state.step == "scanning":
    # Anti-re-run guard: if we're already processing, skip execution
    if st.session_state._processing:
        st.info("⏳ Scan en cours... Merci de patienter.")
        st.stop()

    try:
        st.session_state._processing = True
        st.subheader("🔍 Scan de tes channels Telegram")

        if not ENV_API_ID or not ENV_API_HASH:
            st.error("API_ID/API_HASH manquants. Vérifie le fichier `.env`.")
            st.session_state.step = "config"
            st.session_state._processing = False
            st.rerun()
            st.stop()

        _api_id = validate_api_id(ENV_API_ID)
        _api_hash = ENV_API_HASH

        scan_progress = st.progress(0, text="🔄 Connexion à Telegram...")
        scan_status = st.empty()

        async def _get_all_channels(api_id_val, api_hash_val):
            """Récupère la liste des channels."""
            client = TelegramClient("gold_session", api_id_val, api_hash_val)
            await client.start()
            try:
                channels = []
                async for dialog in client.iter_dialogs():
                    entity = dialog.entity
                    if isinstance(entity, Channel):
                        username = getattr(entity, "username", None)
                        channels.append({
                            "id": entity.id,
                            "title": entity.title,
                            "username": f"@{username}" if username else "—",
                            "megagroup": entity.megagroup,
                            "likely_trading": is_likely_trading_channel(entity.title)
                        })
                return channels
            finally:
                await client.disconnect()

        async def _scan_one_channel(api_id_val, api_hash_val, channel_id):
            """Scan un seul channel pour les signaux."""
            client = TelegramClient("gold_session", api_id_val, api_hash_val)
            await client.start()
            try:
                return await scan_channel_quick(client, channel_id)
            finally:
                await client.disconnect()

        # Phase 1: récupérer la liste des channels
        scan_progress.progress(0.05, text="🔄 Connexion à Telegram...")
        channels = run_telethon(_get_all_channels, _api_id, _api_hash)
        scan_status.text(f"📋 {len(channels)} channels trouvés — scan en cours...")

        # Phase 2: scanner chaque channel (UI updates dans le thread principal)
        trading_channels = []
        total = len(channels)
        for i, ch in enumerate(channels):
            scan_progress.progress(
                0.05 + 0.95 * ((i + 1) / total),
                text=f"🔍 Scan {i+1}/{total} — {ch['title'][:30]}..."
            )
            try:
                scan = run_telethon(_scan_one_channel, _api_id, _api_hash, ch["id"])
                if scan.get("has_signals"):
                    # Convert format_profile to dict for safe session_state storage
                    fp = scan.get("format_profile")
                    fp_dict = fp.to_dict() if fp and hasattr(fp, 'to_dict') else None
                    trading_channels.append({
                        **ch,
                        "signal_count": scan["sample_count"],
                        "format": scan["format"],
                        "total_messages": scan.get("total_messages", 0),
                        "format_profile": fp_dict,
                    })
            except Exception as e:
                # Skip channel on error, continue scanning
                print(f"Error scanning channel {ch['title']}: {e}")
                continue

        scan_progress.progress(1.0, text="✅ Scan terminé !")
        scan_status.success(f"✅ {len(trading_channels)} channels avec signaux trouvés sur {total} scannés")

        st.session_state.channels = channels
        st.session_state.trading_channels = trading_channels

        # Store format info as simple dicts (not FormatProfile objects)
        format_profiles = {}
        for ch in trading_channels:
            fp = ch.get("format_profile")
            if fp:
                format_profiles[ch["id"]] = fp.to_dict() if hasattr(fp, 'to_dict') else {}
        st.session_state.format_profiles = format_profiles

        st.session_state._processing = False
        st.session_state.step = "select"
        st.rerun()

    except Exception as e:
        st.session_state._processing = False
        scan_progress.empty()
        scan_status.error(f"❌ Erreur pendant le scan : {e}")
        import traceback
        st.code(traceback.format_exc(), language="python")
        if st.button("🔄 Réinitialiser", key="reset_scan"):
            safe_reset()


# === STEP 4: Select Channels ===
elif st.session_state.step == "select":
    try:
        st.subheader("📊 Channels avec signaux de trading détectés")
        trading = st.session_state.trading_channels
        all_channels = st.session_state.channels

        if not trading:
            st.warning("Aucun channel avec des signaux de trading détecté.")
            st.info("Vérifie que tu es bien dans des channels de trading gold.")
            if st.button("🔄 Rescan"):
                st.session_state.step = "scanning"
                st.rerun()
        else:
            st.success(
                f"🎯 {len(trading)} channels avec signaux trouvés sur {len(all_channels)} total"
            )

            # Show format detection info
            for ch in trading:
                fp = ch.get("format_profile")
                if fp and fp.get("confidence", 0) > 0.3:
                    with st.expander(f"🔍 Format détecté — {ch['title'][:30]}", expanded=False):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Direction", fp.get("direction_style", "—").title())
                        c2.metric("Entry", fp.get("entry_style", "—").title())
                        c3.metric("TP", fp.get("tp_style", "—").title())
                        c4.metric("SL", fp.get("sl_style", "—").title())
                        st.caption(
                            f"📊 {fp.get('sample_size', 0)} messages analysés · "
                            f"Densité signaux: {fp.get('signal_density', 0):.0%} · "
                            f"Confiance: {fp.get('confidence', 0):.0%} · "
                            f"TP moyen: {fp.get('avg_tp_count', 1):.1f} · "
                            f"Paire: {fp.get('pair', 'XAUUSD')}"
                        )

            selected = st.multiselect(
                "Sélectionne les channels à analyser en profondeur :",
                options=[ch["title"] for ch in trading],
                default=[ch["title"] for ch in trading]
            )
            selected_ids = {ch["id"]: ch["title"] for ch in trading if ch["title"] in selected}
            st.session_state.selected_channels = selected_ids

            # Build display dataframe with format info
            display_data = []
            for ch in trading:
                fp = ch.get("format_profile")
                display_data.append({
                    "ID": ch["id"],
                    "Channel": ch["title"],
                    "Username": ch["username"],
                    "Signaux": ch["signal_count"],
                    "Format": ch["format"],
                    "Direction": fp.get("direction_style", "—").title() if fp else "—",
                    "TP Style": fp.get("tp_style", "—").title() if fp else "—",
                    "Confiance": f"{fp.get('confidence', 0):.0%}" if fp else "—",
                })
            st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🚀 Lancer l'analyse complète", type="primary",
                             disabled=len(selected_ids) == 0):
                    st.session_state.step = "analyzing"
                    st.rerun()
            with col2:
                if st.button("🔌 Se déconnecter"):
                    for sess_file in ["gold_session.session", "gold_session.session-journal"]:
                        if os.path.exists(sess_file):
                            try:
                                os.remove(sess_file)
                            except OSError:
                                pass
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()
    except Exception as e:
        show_crash_recovery(e)


# === STEP 5: Full Analysis ===
elif st.session_state.step == "analyzing":
    # Anti-re-run guard
    if st.session_state._processing:
        # Auto-reset after 10 minutes to prevent permanent lock
        import time
        _proc_start = st.session_state.get("_processing_start", 0)
        if _proc_start and (time.time() - _proc_start) > 600:
            st.session_state._processing = False
            st.warning("⏱️ L'analyse a pris trop de temps — réinitialisation automatique.")
            st.rerun()
        else:
            st.info("⏳ Analyse en cours... Merci de patienter.")
            st.info("💡 Si Chrome se bloque, attends 10 min ou réinitialise ci-dessous.")
            if st.button("🔄 Forcer la réinitialisation", key="force_reset_proc"):
                st.session_state._processing = False
                st.rerun()
            st.stop()

    try:
        import time
        st.session_state._processing = True
        st.session_state._processing_start = time.time()
        st.subheader("🔬 Analyse en cours...")
        days = analysis_days

        # Phase 1: Récupération des prix
        price_progress = st.progress(0, text="📈 Récupération des prix gold...")
        price_status = st.empty()

        price_status.text("⏳ Chargement des données Yahoo Finance (jusqu'à 28 jours en 1min)...")
        price_progress.progress(0.1)

        with st.spinner(""):
            gold_prices = fetch_gold_prices(days=days + 5, interval="1m")

        price_progress.progress(0.3, text="✅ Prix gold récupérés")
        price_status.success(f"✅ {len(gold_prices)} bougies chargées")

        # Phase 2: Analyse des channels
        analysis_progress = st.progress(0, text="🔬 Analyse des channels...")
        analysis_status = st.empty()

        def update_progress(current, total, name):
            try:
                pct = 0.3 + 0.7 * (current / total)
                analysis_progress.progress(pct, text=f"🔬 Analyse: {name[:30]}... ({current}/{total})")
                analysis_status.text(f"📊 {current}/{total} — {name}")
            except Exception:
                pass

        _api_id = validate_api_id(ENV_API_ID)
        _api_hash = ENV_API_HASH
        selected = st.session_state.selected_channels

        async def _run_full(api_id_val, api_hash_val, channel_ids):
            client = TelegramClient("gold_session", api_id_val, api_hash_val)
            await client.start()
            try:
                return await run_full_analysis(
                    client, channel_ids, days, progress_callback=update_progress,
                    format_profiles=None  # TODO: reconstruct FormatProfile from dicts
                )
            finally:
                await client.disconnect()

        results = run_telethon(_run_full, _api_id, _api_hash, selected)
        analysis_progress.progress(1.0, text="✅ Analyse terminée !")
        analysis_status.success(f"✅ {len(results)} channels analysés")

        st.session_state.analysis_results = results
        st.session_state._processing = False
        st.session_state.step = "results"
        st.rerun()

    except Exception as e:
        st.session_state._processing = False
        show_crash_recovery(e)


# === STEP 5b: Channel Detail ===
elif st.session_state.step == "detail":
    try:
        ch_id = st.session_state.detail_channel
        results = st.session_state.analysis_results

        if not results or ch_id is None:
            st.warning("Aucun détail disponible.")
            if st.button("↩️ Retour aux résultats"):
                st.session_state.step = "results"
                st.rerun()
            st.stop()

        # Find the channel score
        score = next((s for s in results if s.channel_id == ch_id), None)
        if not score:
            st.error("Channel introuvable.")
            if st.button("↩️ Retour aux résultats"):
                st.session_state.step = "results"
                st.rerun()
            st.stop()

        # Header
        st.subheader(f"📈 {score.channel_name}")
        st.caption(f"Channel ID: `{score.channel_id}`")

        # Back button
        if st.button("↩️ Retour au classement"):
            st.session_state.step = "results"
            st.rerun()

        st.divider()

        # === KPIs ===
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("🏆 Score", f"{score.score}/100")
        k2.metric("🎯 Win Rate", f"{score.win_rate}%")
        k3.metric("📊 Signaux", score.total_signals)
        k4.metric("💰 PnL Total", f"{score.total_pnl_pips:+.0f} pips")
        k5.metric("📐 R:R", score.risk_reward_ratio)

        k6, k7, k8, k9, k10 = st.columns(5)
        k6.metric("✅ Wins", score.wins)
        k7.metric("❌ Losses", score.losses)
        k8.metric("⏳ Open", score.open_signals)
        k9.metric("📈 Sharpe", score.sharpe_ratio)
        k10.metric("⏱️ Temps moyen", f"{score.avg_time_to_result_hours:.1f}h")

        st.divider()

        # === Charts ===
        if score.signals:
            pnl_df = build_pnl_curve(score.signals)

            chart1, chart2 = st.columns([2, 1])

            with chart1:
                st.subheader("📉 Courbe de PnL cumulé")
                if not pnl_df.empty and "Date" in pnl_df.columns:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=pnl_df["Date"], y=pnl_df["Cumulé"],
                        mode="lines+markers",
                        name="PnL cumulé",
                        line=dict(color="#1976D2", width=2),
                        marker=dict(size=5),
                        fill="tozeroy",
                        fillcolor="rgba(25, 118, 210, 0.1)",
                        hovertemplate="<b>%{x}</b><br>PnL cumulé: %{y:+.1f} pips<extra></extra>"
                    ))
                    fig.update_layout(
                        xaxis_title="Date", yaxis_title="PnL cumulé (pips)",
                        height=400, margin=dict(l=0, r=0, t=30, b=0),
                        hovermode="x unified"
                    )
                    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Pas assez de données pour la courbe de PnL")

            with chart2:
                st.subheader("🎯 Répartition")
                result_counts = {}
                for sig in score.signals:
                    r = sig.get("result", "OPEN")
                    result_counts[r] = result_counts.get(r, 0) + 1

                if result_counts:
                    colors = {"TP1": "#4CAF50", "TP2": "#66BB6A", "TP3": "#81C784",
                              "TP4": "#A5D6A7", "TP5": "#C8E6C9", "TP6": "#E8F5E9",
                              "SL": "#EF5350", "OPEN": "#90A4AE"}
                    fig_pie = go.Figure(data=[go.Pie(
                        labels=list(result_counts.keys()),
                        values=list(result_counts.values()),
                        marker_colors=[colors.get(k, "#90A4AE") for k in result_counts.keys()],
                        hole=0.4,
                        textinfo="label+percent",
                        textposition="outside"
                    )])
                    fig_pie.update_layout(
                        height=400, margin=dict(l=0, r=0, t=30, b=0),
                        showlegend=False
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)

            # PnL par signal
            st.subheader("📊 PnL par signal")
            if not pnl_df.empty:
                bar_colors = ["#4CAF50" if p >= 0 else "#EF5350" for p in pnl_df["PnL"]]
                fig_bar = go.Figure(data=[go.Bar(
                    x=list(range(1, len(pnl_df) + 1)),
                    y=pnl_df["PnL"],
                    marker_color=bar_colors,
                    hovertemplate="Signal #%{x}<br>PnL: %{y:+.1f} pips<extra></extra>"
                )])
                fig_bar.update_layout(
                    xaxis_title="Signal #", yaxis_title="PnL (pips)",
                    height=300, margin=dict(l=0, r=0, t=30, b=0)
                )
                fig_bar.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
                st.plotly_chart(fig_bar, use_container_width=True)

            # Heatmap jour/heure
            st.subheader("🗓️ Performance par jour et heure")
            heatmap_data = []
            for sig in score.signals:
                ts = sig.get("timestamp")
                if isinstance(ts, str):
                    try:
                        ts = datetime.strptime(ts, "%Y-%m-%d %H:%M")
                    except (ValueError, TypeError):
                        continue
                if ts and sig.get("result") in ("TP1", "TP2", "TP3", "TP4", "TP5", "TP6", "SL"):
                    _day_fr = {"Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
                               "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche"}
                    heatmap_data.append({
                        "Jour": _day_fr.get(ts.strftime("%A"), ts.strftime("%A")),
                        "Heure": ts.hour,
                        "PnL": sig.get("pnl_pips", 0)
                    })

            if heatmap_data:
                hm_df = pd.DataFrame(heatmap_data)
                day_order = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                hm_pivot = hm_df.groupby(["Jour", "Heure"])["PnL"].mean().reset_index()
                hm_pivot["Jour"] = pd.Categorical(hm_pivot["Jour"], categories=day_order, ordered=True)
                hm_pivot = hm_pivot.pivot(index="Jour", columns="Heure", values="PnL").fillna(0)

                fig_hm = px.imshow(
                    hm_pivot, color_continuous_scale="RdYlGn", aspect="auto",
                    title="PnL moyen par jour × heure (pips)",
                    labels=dict(x="Heure", y="Jour", color="PnL")
                )
                fig_hm.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(fig_hm, use_container_width=True)

            # Tableau détaillé
            st.subheader("📋 Détail des signaux")
            max_tps = max((len(sig.get("tps", [])) for sig in score.signals), default=0)
            sig_data = []
            for sig in score.signals:
                row = {
                    "Date": sig.get("timestamp", "N/A"),
                    "Direction": sig.get("direction", "?"),
                    "Entry": sig.get("entry", 0),
                }
                tps = sig.get("tps", [])
                for i in range(max_tps):
                    row[f"TP{i+1}"] = str(tps[i]) if i < len(tps) else "—"
                row["SL"] = str(sig.get("sl", "—")) if sig.get("sl") is not None else "—"
                row["Résultat"] = sig.get("result", "?")
                pnl = sig.get("pnl_pips", 0)
                row["PnL (pips)"] = f"{pnl:+.0f}"
                row["Confiance"] = f"{sig.get('confidence', 0):.0%}"
                # Debug info for OPEN signals
                if sig.get("result") == "OPEN":
                    row["Debug Bougies"] = sig.get("debug_candles_checked", "?")
                    row["Debug Prix Range"] = f"{sig.get('debug_price_range', ('?','?'))[0]}–{sig.get('debug_price_range', ('?','?'))[1]}"
                    row["Debug Premium"] = sig.get("premium", "?")
                sig_data.append(row)
            st.dataframe(pd.DataFrame(sig_data), use_container_width=True, hide_index=True)

        else:
            st.info("Aucun signal dans ce channel.")

    except Exception as e:
        st.error(f"❌ Erreur lors de l'affichage du détail : {e}")
        if st.button("↩️ Retour aux résultats", key="reset_detail"):
            st.session_state.step = "results"
            st.rerun()


# === STEP 6: Results ===
elif st.session_state.step == "results":
    try:
        results = st.session_state.analysis_results
        if not results:
            st.warning("Aucun résultat. Réessaie avec d'autres channels.")
            if st.button("🔄 Recommencer"):
                st.session_state.step = "select"
                st.rerun()
        else:
            st.subheader("🏆 Classement des Channels")

            # Top cards — responsive: 4 cols on desktop, 2 on tablet, 1 on mobile
            num_cards = min(len(results), 4)
            cols = st.columns(num_cards)
            for i, score in enumerate(results[:num_cards]):
                with cols[i]:
                    medal = ["🥇", "🥈", "🥉", "4️⃣"][min(i, 3)]
                    st.metric(
                        f"{medal} {score.channel_name[:20]}",
                        f"{score.score}/100",
                        f"WR: {score.win_rate}%"
                    )
            st.divider()

            tab1, tab2, tab3 = st.tabs(["📊 Classement", "📈 Détails", "📥 Export"])

            with tab1:
                data = [{
                    "ID": s.channel_id,
                    "Channel": s.channel_name,
                    "Score": s.score,
                    "Win Rate": f"{s.win_rate}%",
                    "Signaux": s.total_signals,
                    "Wins": s.wins,
                    "Losses": s.losses,
                    "Open": s.open_signals,
                    "R:R": s.risk_reward_ratio,
                    "Sharpe": s.sharpe_ratio,
                    "PnL Total (pips)": f"{s.total_pnl_pips:+.0f}",
                    "PnL Moyen (pips)": f"{s.avg_pnl_pips:+.0f}",
                    "Meilleur": f"{s.best_signal_pips:+.0f}",
                    "Pire": f"{s.worst_signal_pips:+.0f}",
                    "Temps moyen": f"{s.avg_time_to_result_hours:.1f}h"
                } for s in results]
                st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

                if len(results) > 1:
                    chart_data = pd.DataFrame([{
                        "Channel": s.channel_name, "Score": s.score,
                        "Win Rate": s.win_rate, "PnL Total": s.total_pnl_pips
                    } for s in results])
                    fig = px.bar(chart_data, x="Channel", y="Score",
                                 color="Win Rate", color_continuous_scale="RdYlGn",
                                 title="Score par Channel")
                    st.plotly_chart(fig, use_container_width=True)

            with tab2:
                for idx, s in enumerate(results):
                    medal = "🥇" if idx == 0 else "📊"
                    with st.expander(f"{medal} {s.channel_name} — {s.score}/100"):
                        st.caption(f"Channel ID: `{s.channel_id}`")
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Win Rate", f"{s.win_rate}%")
                        c2.metric("Signaux", s.total_signals)
                        c3.metric("PnL Total", f"{s.total_pnl_pips:+.0f} pips")
                        c4.metric("R:R", s.risk_reward_ratio)
                        st.metric("Sharpe Ratio", s.sharpe_ratio)

                        # Mini PnL preview
                        if s.signals:
                            pnl_df = build_pnl_curve(s.signals)
                            if not pnl_df.empty and len(pnl_df) > 1:
                                fig_mini = go.Figure()
                                fig_mini.add_trace(go.Scatter(
                                    y=pnl_df["Cumulé"], mode="lines",
                                    line=dict(color="#1976D2", width=1.5),
                                    fill="tozeroy", fillcolor="rgba(25, 118, 210, 0.08)",
                                    hovertemplate="Signal #%{x}<br>PnL: %{y:+.1f}<extra></extra>"
                                ))
                                fig_mini.update_layout(
                                    height=150, margin=dict(l=0, r=0, t=5, b=0),
                                    xaxis_title="", yaxis_title="",
                                    showlegend=False
                                )
                                st.plotly_chart(fig_mini, use_container_width=True)

                        # Detail button
                        if st.button(f"🔍 Voir le détail complet", key=f"detail_{s.channel_id}"):
                            st.session_state.detail_channel = s.channel_id
                            st.session_state.step = "detail"
                            st.rerun()

                        if s.signals:
                            max_tps = max((len(sig.get("tps", [])) for sig in s.signals), default=0)
                            sig_data = []
                            for sig in s.signals:
                                row = {
                                    "Date": sig.get("timestamp", "N/A"),
                                    "Direction": sig.get("direction", "?"),
                                    "Entry": sig.get("entry", 0),
                                }
                                tps = sig.get("tps", [])
                                for i in range(max_tps):
                                    row[f"TP{i+1}"] = str(tps[i]) if i < len(tps) else "—"
                                row["SL"] = str(sig.get("sl", "—")) if sig.get("sl") is not None else "—"
                                row["Résultat"] = sig.get("result", "?")
                                row["PnL (pips)"] = f"{sig.get('pnl_pips', 0):+.0f}"
                                row["Confiance"] = f"{sig.get('confidence', 0):.0%}"
                                if sig.get("result") == "OPEN":
                                    row["Bougies"] = sig.get("debug_candles_checked", "?")
                                    _dpr = sig.get("debug_price_range", ("?", "?"))
                                    row["Prix Range"] = f"{_dpr[0]}–{_dpr[1]}" if len(_dpr) >= 2 else "?"
                                    row["Premium"] = sig.get("premium", "?")
                                sig_data.append(row)
                            st.dataframe(pd.DataFrame(sig_data),
                                         use_container_width=True, hide_index=True)

            with tab3:
                st.subheader("📥 Export des résultats")
                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    pd.DataFrame([{
                        "Channel ID": s.channel_id,
                        "Channel": s.channel_name, "Score": s.score,
                        "Win Rate": s.win_rate, "Total Signals": s.total_signals,
                        "Wins": s.wins, "Losses": s.losses,
                        "R:R Ratio": s.risk_reward_ratio,
                        "Sharpe Ratio": s.sharpe_ratio,
                        "Total PnL (pips)": s.total_pnl_pips,
                        "Avg PnL (pips)": s.avg_pnl_pips
                    } for s in results]).to_excel(writer, index=False, sheet_name="Résumé")
                    all_sigs = [{"Channel": s.channel_name, **sig}
                                for s in results for sig in (s.signals or [])]
                    if all_sigs:
                        pd.DataFrame(all_sigs).to_excel(writer, index=False, sheet_name="Signaux")

                st.download_button("📥 Télécharger Excel (XLSX)", buffer.getvalue(),
                                   "gold_channel_analysis.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                report = format_score_report(results)
                st.download_button("📄 Télécharger le rapport (TXT)", report,
                                   "gold_channel_report.txt", "text/plain")

            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Nouvelle analyse"):
                    st.session_state.step = "select"
                    st.session_state.analysis_results = None
                    st.rerun()
            with col2:
                if st.button("🔌 Se déconnecter"):
                    for sess_file in ["gold_session.session", "gold_session.session-journal"]:
                        if os.path.exists(sess_file):
                            try:
                                os.remove(sess_file)
                            except OSError:
                                pass
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()

    except Exception as e:
        st.error(f"❌ Erreur lors de l'affichage des résultats : {e}")
        st.info("Les données peuvent être corrompues. Réinitialise pour continuer.")
        if st.button("🔄 Réinitialiser", key="reset_results"):
            safe_reset()