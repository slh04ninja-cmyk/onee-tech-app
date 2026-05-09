"""
Gold Trading Channel Analyzer - App Streamlit
Analyse et classe les channels Telegram de trading gold par rentabilité.
"""

import asyncio
import concurrent.futures
import os
import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
from telethon import TelegramClient
from telethon.tl.types import Channel

from signal_parser import parse_signal, TradeSignal
from gold_prices import fetch_gold_prices, check_tp_sl_hit
from backtester import scan_channel_quick, run_full_analysis
from scorer import ChannelScore, score_channels, format_score_report


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
# Chaque appel crée son propre event loop dans un thread séparé.
# Le fichier gold_session.session persiste l'auth entre les appels.

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def run_telethon(coro_func, *args, **kwargs):
    """Exécute une coroutine Telethon dans un thread avec son propre event loop."""
    def _wrapper():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro_func(*args, **kwargs))
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
    return _executor.submit(_wrapper).result(timeout=180)


# === Async helpers (all Telethon calls go through here) ===

async def _send_code(api_id_val: int, api_hash_val: str, phone: str):
    client = TelegramClient("gold_session", api_id_val, api_hash_val)
    await client.connect()
    try:
        if await client.is_user_authorized():
            # Already logged in from previous session
            return None  # signals "already authorized"
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



# === Page Config ===
st.set_page_config(
    page_title="Gold Channel Analyzer",
    page_icon="🏆",
    layout="wide"
)

st.title("🏆 Gold Trading Channel Analyzer")
st.markdown("Analyse et classe tes channels Telegram de trading gold par rentabilité réelle.")

# === Session State ===
defaults = {
    "step": "config",
    "phone": "",
    "api_id": "",
    "api_hash": "",
    "channels": [],
    "trading_channels": [],
    "selected_channels": {},
    "analysis_results": None,
    "phone_code_hash": "",
    "logged_in": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# === Sidebar ===
with st.sidebar:
    st.header("⚙️ Configuration")
    api_id = st.text_input("API_ID", type="password",
                           value=st.session_state.get("api_id", ""),
                           help="Nombre entier (ex: 12345678). Obtu sur my.telegram.org/apps")
    api_hash = st.text_input("API_HASH", type="password",
                             value=st.session_state.get("api_hash", ""),
                             help="Code hexadécimal (ex: a1b2c3d4...). Obtu sur my.telegram.org/apps")
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
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("📱 Connexion Telegram")
        phone = st.text_input("Numéro de téléphone", placeholder="+212XXXXXXXXX")
        if st.button("📨 Envoyer le code", type="primary"):
            if not api_id or not api_hash or not phone:
                st.error("Remplis tous les champs dans la sidebar.")
            else:
                try:
                    _api_id = validate_api_id(api_id)
                except ValueError as e:
                    st.error(str(e))
                    st.stop()
                with st.spinner("Connexion à Telegram..."):
                    try:
                        result = run_telethon(_send_code, _api_id, api_hash, phone)
                        st.session_state.phone = phone
                        st.session_state.api_id = api_id
                        st.session_state.api_hash = api_hash
                        if result is None:
                            # Already authorized from previous session
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
                                f"Vérifie que tu as bien copié les bonnes valeurs sur "
                                f"[my.telegram.org/apps](https://my.telegram.org/apps):\n"
                                f"- **API_ID** = un nombre entier court (ex: `12345678`)\n"
                                f"- **API_HASH** = un code hexadécimal de 32 caractères (ex: `a1b2c3d4e5f6...`)\n\n"
                                f"⚠️ Ne les inverse pas !"
                            )
                        else:
                            st.error(f"Erreur: {e}")
    with col2:
        st.info("""
        **Comment obtenir API_ID?**
        1. Va sur my.telegram.org/apps
        2. Connecte-toi avec ton numéro
        3. Crée une application
        4. Copie API_ID et API_HASH
        """)


# === STEP 2: Verification Code ===
elif st.session_state.step == "code":
    st.subheader("🔑 Code de vérification")
    st.info(f"Code envoyé à **{st.session_state.phone}**")
    code = st.text_input("Entre le code reçu", placeholder="12345")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Vérifier", type="primary"):
            if not code:
                st.error("Entre le code.")
            else:
                with st.spinner("Vérification..."):
                    try:
                        run_telethon(
                            _sign_in_code,
                            validate_api_id(st.session_state.api_id),
                            st.session_state.api_hash,
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


# === STEP 2b: 2FA ===
elif st.session_state.step == "password":
    st.subheader("🔐 Mot de passe 2FA")
    password = st.text_input("Mot de passe Telegram", type="password")
    if st.button("✅ Se connecter", type="primary"):
        with st.spinner("Vérification..."):
            try:
                run_telethon(
                    _sign_in_password,
                    validate_api_id(st.session_state.api_id),
                    st.session_state.api_hash,
                    password
                )
                st.session_state.logged_in = True
                st.session_state.step = "scanning"
                st.rerun()
            except Exception as e:
                st.error(f"Erreur: {e}")


# === STEP 3: Scan Channels ===
elif st.session_state.step == "scanning":
    st.subheader("🔍 Scan de tes channels...")

    if "api_id" not in st.session_state or "api_hash" not in st.session_state:
        st.error("Session expirée. Retour à la configuration...")
        st.session_state.step = "config"
        st.rerun()
        st.stop()

    _api_id = validate_api_id(st.session_state.api_id)
    _api_hash = st.session_state.api_hash

    async def _scan_all_channels(api_id_val, api_hash_val):
        """Tout le scan dans une seule coroutine — un seul event loop, un seul client."""
        client = TelegramClient("gold_session", api_id_val, api_hash_val)
        await client.start()
        try:
            # 1) Récupérer tous les channels
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

            # 2) Scanner chaque channel pour les signaux
            trading_channels = []
            for ch in channels:
                scan = await scan_channel_quick(client, ch["id"])
                if scan.get("has_signals"):
                    trading_channels.append({
                        **ch,
                        "signal_count": scan["sample_count"],
                        "format": scan["format"],
                        "total_messages": scan.get("total_messages", 0)
                    })

            return channels, trading_channels
        finally:
            await client.disconnect()

    with st.spinner("Connexion et scan des channels..."):
        channels, trading_channels = run_telethon(_scan_all_channels, _api_id, _api_hash)

    st.session_state.channels = channels
    st.session_state.trading_channels = trading_channels
    st.session_state.step = "select"
    st.rerun()


# === STEP 4: Select Channels ===
elif st.session_state.step == "select":
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
            f"{len(trading)} channels avec signaux trouvés sur {len(all_channels)} total"
        )
        df = pd.DataFrame(trading).rename(columns={
            "title": "Channel", "signal_count": "Signaux détectés",
            "format": "Format", "username": "Username"
        })
        selected = st.multiselect(
            "Sélectionne les channels à analyser en profondeur :",
            options=[ch["title"] for ch in trading],
            default=[ch["title"] for ch in trading]
        )
        selected_ids = {ch["id"]: ch["title"] for ch in trading if ch["title"] in selected}
        st.session_state.selected_channels = selected_ids
        st.dataframe(
            df[["Channel", "Username", "Signaux détectés", "Format"]],
            use_container_width=True, hide_index=True
        )
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Lancer l'analyse complète", type="primary",
                         disabled=len(selected_ids) == 0):
                st.session_state.step = "analyzing"
                st.rerun()
        with col2:
            if st.button("🔌 Se déconnecter"):
                # Supprimer la session Telegram pour forcer la reconnexion
                for sess_file in ["gold_session.session", "gold_session.session-journal"]:
                    if os.path.exists(sess_file):
                        os.remove(sess_file)
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()


# === STEP 5: Full Analysis ===
elif st.session_state.step == "analyzing":
    st.subheader("🔬 Analyse en cours...")
    days = analysis_days
    progress = st.progress(0)
    status = st.empty()

    def update_progress(current, total, name):
        try:
            progress.progress(current / total, text=f"Analyse: {name[:30]}...")
            status.text(f"{current}/{total} — {name}")
        except Exception:
            pass  # NoSessionContext when called from thread worker

    with st.spinner("Récupération des prix gold..."):
        gold_prices = fetch_gold_prices(days=days + 5, interval="1m")

    _api_id = validate_api_id(st.session_state.api_id)
    _api_hash = st.session_state.api_hash
    selected = st.session_state.selected_channels

    async def _run_full(api_id_val, api_hash_val, channel_ids):
        """Analyse complète dans une seule coroutine."""
        client = TelegramClient("gold_session", api_id_val, api_hash_val)
        await client.start()
        try:
            return await run_full_analysis(
                client, channel_ids, days, progress_callback=update_progress
            )
        finally:
            await client.disconnect()

    results = run_telethon(_run_full, _api_id, _api_hash, selected)

    progress.empty()
    status.empty()
    st.session_state.analysis_results = results
    st.session_state.step = "results"
    st.rerun()


# === STEP 6: Results ===
elif st.session_state.step == "results":
    results = st.session_state.analysis_results
    if not results:
        st.warning("Aucun résultat. Réessaie avec d'autres channels.")
        if st.button("🔄 Recommencer"):
            st.session_state.step = "select"
            st.rerun()
    else:
        st.subheader("🏆 Classement des Channels")
        cols = st.columns(min(len(results), 4))
        for i, score in enumerate(results[:4]):
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
                "Channel": s.channel_name,
                "Score": s.score,
                "Win Rate": f"{s.win_rate}%",
                "Signaux": s.total_signals,
                "Wins": s.wins,
                "Losses": s.losses,
                "Open": s.open_signals,
                "R:R": s.risk_reward_ratio,
                "PnL Total (pips)": f"{s.total_pnl_pips:+.0f}",
                "PnL Moyen (pips)": f"{s.avg_pnl_pips:+.0f}",
                "Meilleur": f"{s.best_signal_pips:+.0f}",
                "Pire": f"{s.worst_signal_pips:+.0f}",
                "Temps moyen": f"{s.avg_time_to_result_hours:.1f}h"
            } for s in results]
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

            if len(results) > 1:
                import plotly.express as px
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
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Win Rate", f"{s.win_rate}%")
                    c2.metric("Signaux", s.total_signals)
                    c3.metric("PnL Total", f"{s.total_pnl_pips:+.0f} pips")
                    c4.metric("R:R", s.risk_reward_ratio)
                    if s.signals:
                        # Dynamically detect max TPs across all signals
                        max_tps = max((len(sig.get("tps", [])) for sig in s.signals), default=0)
                        sig_data = []
                        for sig in s.signals:
                            row = {
                                "Date": sig.get("timestamp", "N/A"),
                                "Direction": sig.get("direction", "?"),
                                "Entry": sig.get("entry", 0),
                            }
                            # Add all TP columns dynamically
                            tps = sig.get("tps", [])
                            for i in range(max_tps):
                                row[f"TP{i+1}"] = tps[i] if i < len(tps) else "—"
                            row["SL"] = sig.get("sl", "—")
                            row["Résultat"] = sig.get("result", "?")
                            row["PnL (pips)"] = f"{sig.get('pnl_pips', 0):+.0f}"
                            row["Confiance"] = f"{sig.get('confidence', 0):.0%}"
                            sig_data.append(row)
                        st.dataframe(pd.DataFrame(sig_data),
                                     use_container_width=True, hide_index=True)

        with tab3:
            st.subheader("📥 Export des résultats")
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                pd.DataFrame([{
                    "Channel": s.channel_name, "Score": s.score,
                    "Win Rate": s.win_rate, "Total Signals": s.total_signals,
                    "Wins": s.wins, "Losses": s.losses,
                    "R:R Ratio": s.risk_reward_ratio,
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
                        os.remove(sess_file)
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
