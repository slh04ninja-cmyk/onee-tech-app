"""
Gold Trading Signal Extractor — App Streamlit
Extrait les signaux de trading depuis Telegram et exporte en CSV pour backtesting MQ5/MT5.
"""

import asyncio
import concurrent.futures
import os
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.types import Channel

from signal_parser import SignalParser, TradeSignal, FormatProfile, normalize_text, is_spam
from csv_exporter import signals_to_csv, create_zip_from_channels, get_export_summary

# Charger les variables d'environnement depuis .env
load_dotenv()
ENV_API_ID = os.getenv("API_ID", "")
ENV_API_HASH = os.getenv("API_HASH", "")


# === API_ID Validation ===
def validate_api_id(raw: str) -> int:
    try:
        val = int(str(raw).strip())
    except (ValueError, TypeError):
        raise ValueError(
            "API_ID doit être un nombre entier (ex: 12345678). "
            "Tu as peut-être entré l'API_HASH à la place."
        )
    if not (-2147483648 <= val <= 2147483647):
        raise ValueError(f"API_ID ({val}) est trop grand. Tu as probablement entré l'API_HASH.")
    if val == 0:
        raise ValueError("API_ID ne peut pas être 0.")
    return val


# === Sync Telethon Wrapper ===
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def run_telethon(coro_func, *args, **kwargs):
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
        return _executor.submit(_wrapper).result(timeout=600)
    except concurrent.futures.TimeoutError:
        raise Exception("⏱️ Timeout (10 min): l'opération a pris trop de temps.")
    except Exception as e:
        raise


# === Async helpers ===
async def _send_code(api_id_val, api_hash_val, phone):
    client = TelegramClient("gold_session", api_id_val, api_hash_val)
    await client.connect()
    try:
        if await client.is_user_authorized():
            return None
        return await client.send_code_request(phone)
    finally:
        await client.disconnect()


async def _sign_in_code(api_id_val, api_hash_val, phone, code, phone_code_hash):
    client = TelegramClient("gold_session", api_id_val, api_hash_val)
    await client.connect()
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
    finally:
        await client.disconnect()


async def _sign_in_password(api_id_val, api_hash_val, password):
    client = TelegramClient("gold_session", api_id_val, api_hash_val)
    await client.connect()
    try:
        await client.sign_in(password=password)
    finally:
        await client.disconnect()


# === Page Config ===
st.set_page_config(
    page_title="Gold Signal Extractor",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="auto"
)

# === CSS ===
st.markdown("""
<style>
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(30px); }
    to { opacity: 1; transform: translateY(0); }
}
.metric-card {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 1px solid rgba(255, 215, 0, 0.15);
    border-radius: 14px;
    padding: 18px;
    text-align: center;
    animation: fadeInUp 0.5s ease-out;
}
.metric-card .metric-value {
    font-size: 1.8rem;
    font-weight: 800;
    background: linear-gradient(135deg, #FFD700, #FFA500);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
@media (max-width: 768px) {
    .block-container { padding: 0.8rem 0.4rem !important; }
    h1 { font-size: 1.3rem !important; }
    .stButton > button { width: 100%; }
}
</style>
""", unsafe_allow_html=True)

st.title("🏆 Gold Signal Extractor")
st.markdown("Extrait les signaux de trading depuis Telegram → CSV pour backtesting MT5.")


# === Crash Recovery ===
def show_crash_recovery(error_msg=""):
    st.error("⚠️ Une erreur est survenue.")
    if error_msg:
        with st.expander("Détails"):
            st.code(str(error_msg), language="python")
    if st.button("🔄 Réinitialiser", key=f"reset_{st.session_state.get('step', 'x')}"):
        for f in ["gold_session.session", "gold_session.session-journal"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()


# === Session State ===
defaults = {
    "step": "config",
    "phone": "",
    "channels": [],
    "trading_channels": [],
    "selected_channels": {},
    "channel_signals": {},  # {ch_id: {"name": str, "signals": [TradeSignal]}}
    "phone_code_hash": "",
    "logged_in": False,
    "_processing": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def is_likely_trading_channel(title: str) -> bool:
    keywords = [
        "gold", "xauusd", "trading", "signal", "forex", "trade",
        "pips", "scalp", "invest", "crypto", "fx", "market",
        "analyse", "analysis", "vip", "premium"
    ]
    return any(kw in title.lower() for kw in keywords)


# === Sidebar ===
with st.sidebar:
    st.header("⚙️ Configuration")
    if ENV_API_ID and ENV_API_HASH:
        st.success("✅ Identifiants Telegram chargés depuis .env")
    else:
        st.error("❌ API_ID / API_HASH manquants dans .env")
    st.divider()
    st.header("📊 Paramètres")
    analysis_days = st.slider("Jours d'historique", 7, 90, 30)
    pair_filter = st.selectbox("Paire à exporter", ["XAUUSD", "ALL"], index=0)


# =====================================================================
# STEP 1: CONFIG & LOGIN
# =====================================================================
if st.session_state.step == "config":
    try:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("📱 Connexion Telegram")
            phone = st.text_input("Numéro de téléphone", placeholder="+212XXXXXXXXX")
            if st.button("📨 Envoyer le code", type="primary"):
                if not ENV_API_ID or not ENV_API_HASH:
                    st.error("API_ID et API_HASH doivent être dans le fichier `.env`")
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
                                st.toast("✅ Session existante — connexion auto", icon="🔑")
                            else:
                                st.session_state.phone_code_hash = result.phone_code_hash
                                st.session_state.step = "code"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur: {e}")
        with col2:
            st.info("""
            **Configuration requise**
            Les identifiants Telegram doivent être dans `.env` :
            ```
            API_ID=12345678
            API_HASH=a1b2c3d4...
            ```
            Obtén-les sur [my.telegram.org/apps](https://my.telegram.org/apps)
            """)
    except Exception as e:
        show_crash_recovery(e)


# =====================================================================
# STEP 2: VERIFICATION CODE
# =====================================================================
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


# =====================================================================
# STEP 2b: 2FA
# =====================================================================
elif st.session_state.step == "password":
    try:
        st.subheader("🔐 Mot de passe 2FA")
        password = st.text_input("Mot de passe Telegram", type="password")
        if st.button("✅ Se connecter", type="primary"):
            with st.spinner("🔄 Vérification..."):
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


# =====================================================================
# STEP 3: SCAN CHANNELS
# =====================================================================
elif st.session_state.step == "scanning":
    if st.session_state._processing:
        st.info("⏳ Scan en cours... Merci de patienter.")
        st.stop()

    try:
        st.session_state._processing = True
        st.subheader("🔍 Scan de tes channels Telegram")

        if not ENV_API_ID or not ENV_API_HASH:
            st.error("API_ID/API_HASH manquants.")
            st.session_state.step = "config"
            st.session_state._processing = False
            st.rerun()
            st.stop()

        _api_id = validate_api_id(ENV_API_ID)
        _api_hash = ENV_API_HASH

        scan_progress = st.progress(0, text="🔄 Démarrage...")
        scan_log = st.empty()

        # Récupérer tous les channels
        async def _get_all_channels(api_id_val, api_hash_val):
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

        # Scanner un channel pour les signaux
        async def _scan_one_channel(api_id_val, api_hash_val, channel_id, days):
            client = TelegramClient("gold_session", api_id_val, api_hash_val)
            await client.start()
            try:
                from datetime import timedelta
                messages = []
                entity = await client.get_entity(channel_id)
                min_date = datetime.now() - timedelta(days=days)
                async for message in client.iter_messages(entity, limit=200):
                    if message.date.replace(tzinfo=None) < min_date:
                        break
                    if message.text:
                        messages.append((message.text, message.date.replace(tzinfo=None)))

                if not messages:
                    return {"has_signals": False, "signals": [], "count": 0}

                parser = SignalParser()
                signals = parser.parse_messages(messages)
                # Garder uniquement les signaux TRADE avec au moins un TP
                trade_signals = [s for s in signals if s.signal_type == "TRADE" and s.tps]

                return {
                    "has_signals": len(trade_signals) > 0,
                    "signals": trade_signals,
                    "count": len(trade_signals),
                    "total_messages": len(messages),
                }
            finally:
                await client.disconnect()

        # Phase 1 : récupérer les channels
        scan_progress.progress(0.05, text="📋 Récupération des channels...")
        channels = run_telethon(_get_all_channels, _api_id, _api_hash)
        scan_log.info(f"📋 **{len(channels)}** channels trouvés")

        # Phase 2 : scanner chaque channel
        trading_channels = []
        channel_signals = {}
        total = len(channels)

        for i, ch in enumerate(channels):
            scan_progress.progress(
                0.1 + 0.85 * ((i + 1) / total),
                text=f"🔍 {i+1}/{total} — {ch['title'][:30]}"
            )
            try:
                scan = run_telethon(_scan_one_channel, _api_id, _api_hash, ch["id"], analysis_days)
                if scan["has_signals"]:
                    trading_channels.append({
                        **ch,
                        "signal_count": scan["count"],
                    })
                    channel_signals[ch["id"]] = {
                        "name": ch["title"],
                        "signals": scan["signals"],
                    }
                    scan_log.success(f"🎯 **{ch['title'][:30]}** — {scan['count']} signaux")
            except Exception as e:
                print(f"Error scanning {ch['title']}: {e}")
                continue

        scan_progress.progress(1.0, text="✅ Scan terminé !")
        scan_log.success(f"✅ **{len(trading_channels)}** channels avec signaux sur **{total}** scannés")

        st.session_state.channels = channels
        st.session_state.trading_channels = trading_channels
        st.session_state.channel_signals = channel_signals
        st.session_state._processing = False
        st.session_state.step = "select"
        st.rerun()

    except Exception as e:
        st.session_state._processing = False
        show_crash_recovery(e)


# =====================================================================
# STEP 4: SELECT & EXPORT
# =====================================================================
elif st.session_state.step == "select":
    try:
        st.subheader("📊 Channels avec signaux détectés")
        trading = st.session_state.trading_channels
        channel_signals = st.session_state.channel_signals

        if not trading:
            st.warning("Aucun channel avec des signaux détecté.")
            if st.button("🔄 Rescan"):
                st.session_state.step = "scanning"
                st.rerun()
            st.stop()

        st.success(f"🎯 {len(trading)} channels avec signaux trouvés")

        # Multiselect
        selected = st.multiselect(
            "Sélectionne les channels à exporter :",
            options=[ch["title"] for ch in trading],
            default=[ch["title"] for ch in trading]
        )
        selected_ids = {ch["id"]: ch["title"] for ch in trading if ch["title"] in selected}

        # Résumé
        pf = pair_filter if pair_filter != "ALL" else ""
        summary = get_export_summary(channel_signals, pair_filter=pf)

        if summary:
            st.divider()
            st.subheader("📋 Résumé des exports")

            df_summary = pd.DataFrame([
                {
                    "Channel": s["channel_name"],
                    "ID": s["channel_id"],
                    "Signaux extraits": s["filtered_signals"],
                    "Fichier": s["filename"],
                }
                for s in summary
                if s["channel_id"] in selected_ids
            ])
            st.dataframe(df_summary, use_container_width=True, hide_index=True)

            total_signals = sum(
                s["filtered_signals"] for s in summary
                if s["channel_id"] in selected_ids
            )
            st.metric("📊 Total signaux à exporter", total_signals)

        # Export
        st.divider()
        col1, col2, col3 = st.columns(3)

        with col1:
            # ZIP download
            if st.button("📦 Télécharger ZIP (tous les channels)", type="primary",
                         disabled=not selected_ids):
                filtered_signals = {
                    ch_id: data for ch_id, data in channel_signals.items()
                    if ch_id in selected_ids
                }
                zip_bytes = create_zip_from_channels(filtered_signals, pair_filter=pf)
                st.download_button(
                    "📥 Télécharger le ZIP",
                    data=zip_bytes,
                    file_name="gold_signals_export.zip",
                    mime="application/zip",
                )

        with col2:
            # CSV individuel
            if selected_ids and len(selected_ids) == 1:
                ch_id = list(selected_ids.keys())[0]
                ch_name = selected_ids[ch_id]
                data = channel_signals.get(ch_id, {})
                signals = data.get("signals", [])
                csv_content = signals_to_csv(signals, ch_name, ch_id, pair_filter=pf)
                st.download_button(
                    "📄 Télécharger CSV unique",
                    data=csv_content,
                    file_name=f"{ch_name}_{ch_id}.csv",
                    mime="text/csv",
                )

        with col3:
            if st.button("🔌 Se déconnecter"):
                for f in ["gold_session.session", "gold_session.session-journal"]:
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except OSError:
                            pass
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.rerun()

        # Prévisualisation d'un channel
        if selected_ids:
            st.divider()
            st.subheader("👁️ Prévisualisation")
            preview_ch = st.selectbox(
                "Choisir un channel à prévisualiser :",
                options=list(selected_ids.values())
            )
            preview_id = [k for k, v in selected_ids.items() if v == preview_ch][0]
            preview_data = channel_signals.get(preview_id, {})
            preview_signals = preview_data.get("signals", [])

            if preview_signals:
                csv_preview = signals_to_csv(preview_signals, preview_ch, preview_id, pair_filter=pf)
                lines = csv_preview.strip().split("\n")
                # Afficher les 20 premières lignes
                preview_text = "\n".join(lines[:21])
                st.code(preview_text, language="csv")
                if len(lines) > 21:
                    st.caption(f"... et {len(lines) - 21} autres lignes")
            else:
                st.info("Aucun signal dans ce channel.")

    except Exception as e:
        show_crash_recovery(e)
