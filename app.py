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

import unicodedata as _ud
from signal_parser import SignalParser, TradeSignal, FormatProfile, normalize_text, is_spam
from csv_exporter import signals_to_csv, create_zip_from_channels, get_export_summary
from format_detector import detect_format, FormatProfile as DetectedFormatProfile


def normalize_unicode_text(text: str) -> str:
    """Convertit TOUS les caractères Unicode non-ASCII en texte normal.
    Couvre : Mathematical Alphanumeric, exposants, indices, symboles, etc."""
    RANGES = [
        (0x1D400, 0x1D419, 0x41), (0x1D41A, 0x1D433, 0x61),
        (0x1D434, 0x1D44D, 0x41), (0x1D44E, 0x1D467, 0x61),
        (0x1D468, 0x1D481, 0x41), (0x1D482, 0x1D49B, 0x61),
        (0x1D49C, 0x1D4B5, 0x41), (0x1D4B6, 0x1D4CF, 0x61),
        (0x1D4D0, 0x1D4E9, 0x41), (0x1D4EA, 0x1D503, 0x61),
        (0x1D504, 0x1D51D, 0x41), (0x1D51E, 0x1D537, 0x61),
        (0x1D538, 0x1D551, 0x41), (0x1D552, 0x1D56B, 0x61),
        (0x1D56C, 0x1D585, 0x41), (0x1D586, 0x1D59F, 0x61),
        (0x1D5A0, 0x1D5B9, 0x41), (0x1D5BA, 0x1D5D3, 0x61),
        (0x1D5D4, 0x1D5ED, 0x41), (0x1D5EE, 0x1D607, 0x61),
        (0x1D608, 0x1D621, 0x41), (0x1D622, 0x1D63B, 0x61),
        (0x1D63C, 0x1D655, 0x41), (0x1D656, 0x1D66F, 0x61),
        (0x1D670, 0x1D689, 0x41), (0x1D68A, 0x1D6A3, 0x61),
    ]
    SUPERSCRIPT = {'⁰':'0','¹':'1','²':'2','³':'3','⁴':'4','⁵':'5','⁶':'6','⁷':'7','⁸':'8','⁹':'9',
                   '⁺':'+','⁻':'-','⁼':'=','⁽':'(','⁾':')','ⁿ':'n','ⁱ':'i'}
    SUBSCRIPT = {'₀':'0','₁':'1','₂':'2','₃':'3','₄':'4','₅':'5','₆':'6','₇':'7','₈':'8','₉':'9',
                 '₊':'+','₋':'-','₌':'=','₍':'(','₎':')','ₐ':'a','ₑ':'e','ₒ':'o','ₓ':'x'}
    SYMBOLS = {
        '✖':'X','✓':'v','✔':'v','✗':'x','✘':'x',
        '▲':'+','▼':'-','▶':'>','◀':'<','△':'+','▽':'-',
        '⬆':'^','⬇':'v','➡':'>','⬅':'<','⬆️':'^','⬇️':'v',
        '🔴':'[R]','🟢':'[G]','🔵':'[B]','🟡':'[Y]','⚫':'[B]','⚪':'[W]',
        '📉':'v','📈':'^','💹':'^','📊':'#','💎':'#','🏆':'#','🥇':'#1',
        '💰':'$','💵':'$','💲':'$','🔥':'!','⚡':'!','💥':'!',
        '📌':'>','📍':'>','🎯':'@','🚩':'SL','🛡':'SL','⛔':'X',
        '❌':'X','✅':'v','❎':'x','❗':'!','‼':'!!','❓':'?','❔':'?',
        '➡️':'>','⬅️':'<','⬆️':'^','⬇️':'v','↪':'>','↩':'<',
        '⭐':'*','🌟':'*','✨':'*','💫':'*','🔔':'!','📢':'!',
        '🚀':'','⚠':'!','💡':'!','🔑':'K','📱':'P',
    }
    result = []
    for ch in text:
        cp = ord(ch)
        if 0x20 <= cp < 0x7F:
            result.append(ch)
            continue
        if ch in ('\n', '\r', '\t'):
            result.append(ch)
            continue
        if ch in SUPERSCRIPT:
            result.append(SUPERSCRIPT[ch])
            continue
        if ch in SUBSCRIPT:
            result.append(SUBSCRIPT[ch])
            continue
        if ch in SYMBOLS:
            result.append(SYMBOLS[ch])
            continue
        mapped = False
        for start, end, base in RANGES:
            if start <= cp <= end:
                result.append(chr(base + (cp - start)))
                mapped = True
                break
        if mapped:
            continue
        nfkd = _ud.normalize('NFKD', ch)
        ascii_char = nfkd.encode('ascii', 'ignore').decode('ascii')
        if ascii_char:
            result.append(ascii_char)
    return ''.join(result)


def normalize_channel_name(name: str) -> str:
    return normalize_unicode_text(name)

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
    "channel_formats": {},  # {ch_id: FormatProfile}
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
                            "title": normalize_channel_name(entity.title),
                            "username": f"@{username}" if username else "—",
                            "megagroup": entity.megagroup,
                            "likely_trading": is_likely_trading_channel(entity.title)
                        })
                return channels
            finally:
                await client.disconnect()

        # Scanner un channel pour les signaux
        async def _scan_one_channel(api_id_val, api_hash_val, channel_id, days):
            from datetime import timedelta
            import signal_parser as sp_module
            client = TelegramClient("gold_session", api_id_val, api_hash_val)
            await client.start()
            try:
                messages = []
                entity = await client.get_entity(channel_id)
                min_date = datetime.now() - timedelta(days=days)
                async for message in client.iter_messages(entity, limit=200):
                    if message.date.replace(tzinfo=None) < min_date:
                        break
                    if message.text:
                        messages.append((message.text, message.date.replace(tzinfo=None)))

                if not messages:
                    return {"has_signals": False, "signals": [], "count": 0, "debug": "0 messages fetched"}

                parser = sp_module.SignalParser()
                all_parsed = []
                trade_signals = []
                signal_texts = []  # raw text of each parsed signal
                spam_count = 0
                no_symbol = 0
                no_action = 0
                no_entry = 0
                no_tp = 0
                for text, ts in messages:
                    if sp_module.is_spam(text):
                        spam_count += 1
                        continue
                    norm = sp_module.normalize_text(text)
                    sym = sp_module._extract_symbol(norm)
                    act = sp_module._extract_action(norm)
                    sig = parser.parse(text, ts)
                    if sig:
                        all_parsed.append(sig)
                        if sig.signal_type == "TRADE" and sig.tps:
                            trade_signals.append(sig)
                            signal_texts.append(normalize_unicode_text(text))
                        elif sig.signal_type == "TRADE" and not sig.tps:
                            no_tp += 1
                    else:
                        if not sym:
                            no_symbol += 1
                        elif not act:
                            no_action += 1
                        else:
                            no_entry += 1

                return {
                    "has_signals": len(trade_signals) > 0,
                    "signals": trade_signals,
                    "signal_texts": signal_texts,
                    "count": len(trade_signals),
                    "total_messages": len(messages),
                    "all_parsed": len(all_parsed),
                    "spam": spam_count,
                    "no_symbol": no_symbol,
                    "no_action": no_action,
                    "no_entry": no_entry,
                    "no_tp": no_tp,
                    "raw_messages": messages,
                }
            except Exception as e:
                return {"has_signals": False, "signals": [], "count": 0, "error": str(e)}
            finally:
                await client.disconnect()

        # Phase 1 : récupérer les channels
        scan_progress.progress(0.05, text="📋 Récupération des channels...")
        channels = run_telethon(_get_all_channels, _api_id, _api_hash)
        scan_log.info(f"📋 **{len(channels)}** channels trouvés")

        # Phase 2 : scanner chaque channel
        trading_channels = []
        channel_signals = {}
        channel_formats = {}
        total = len(channels)

        for i, ch in enumerate(channels):
            scan_progress.progress(
                0.1 + 0.85 * ((i + 1) / total),
                text=f"🔍 {i+1}/{total} — {ch['title'][:30]}"
            )
            try:
                scan = run_telethon(_scan_one_channel, _api_id, _api_hash, ch["id"], analysis_days)
                total_msgs = scan.get("total_messages", 0)
                all_parsed = scan.get("all_parsed", 0)
                spam = scan.get("spam", 0)
                err = scan.get("error", "")
                if err:
                    scan_log.error(f"❌ **{ch['title'][:30]}** — Erreur: {err}")
                    continue
                if scan["has_signals"]:
                    trading_channels.append({
                        **ch,
                        "signal_count": scan["count"],
                    })
                    channel_signals[ch["id"]] = {
                        "name": ch["title"],
                        "signals": scan["signals"],
                        "signal_texts": scan.get("signal_texts", []),
                    }
                    # Detect signal format
                    raw_msgs = scan.get("raw_messages", [])
                    if raw_msgs:
                        fmt = detect_format(raw_msgs, channel_id=ch["id"], channel_name=ch["title"])
                        channel_formats[ch["id"]] = fmt
                    scan_log.success(f"🎯 **{ch['title'][:30]}** — {scan['count']} signaux ({total_msgs} msgs, {all_parsed} parsés, {spam} spam)")
                else:
                    no_sym = scan.get("no_symbol", 0)
                    no_act = scan.get("no_action", 0)
                    no_ent = scan.get("no_entry", 0)
                    no_tp = scan.get("no_tp", 0)
                    debug = f"{total_msgs} msgs | {spam} spam | {all_parsed} parsés | 0 TRADE+TP"
                    if no_sym: debug += f" | {no_sym} sans symbole"
                    if no_act: debug += f" | {no_act} sans action"
                    if no_ent: debug += f" | {no_ent} sans entry"
                    if no_tp: debug += f" | {no_tp} sans TP"
                    scan_log.warning(f"⚠️ **{ch['title'][:30]}** — {debug}")
            except Exception as e:
                scan_log.error(f"❌ **{ch['title'][:30]}** — Exception: {e}")
                continue

        scan_progress.progress(1.0, text="✅ Scan terminé !")
        scan_log.success(f"✅ **{len(trading_channels)}** channels avec signaux sur **{total}** scannés")

        st.session_state.channels = channels
        st.session_state.trading_channels = trading_channels
        st.session_state.channel_signals = channel_signals
        st.session_state.channel_formats = channel_formats
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

            # Tableau avec bouton télécharger par channel
            for s in summary:
                if s["channel_id"] not in selected_ids:
                    continue
                ch_id = s["channel_id"]
                ch_name = s["channel_name"]
                count = s["filtered_signals"]
                filename = s["filename"]

                data = channel_signals.get(ch_id, {})
                signals = data.get("signals", [])
                csv_content = signals_to_csv(signals, ch_name, ch_id, pair_filter=pf)

                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(f"**{ch_name}** · `{ch_id}` · 📊 {count} signaux · `{filename}`")
                with col_btn:
                    st.download_button(
                        "📥 Télécharger",
                        data=csv_content,
                        file_name=filename,
                        mime="text/csv",
                        key=f"dl_{ch_id}",
                    )

            total_signals = sum(
                s["filtered_signals"] for s in summary
                if s["channel_id"] in selected_ids
            )
            st.metric("📊 Total signaux à exporter", total_signals)

        # === SIGNALS RAW CSV DOWNLOAD ===
        st.divider()
        st.subheader("📋 Signaux bruts par channel")

        import csv as _csv
        import io as _io

        sig_csv_rows = []
        for ch_id in selected_ids:
            data = channel_signals.get(ch_id, {})
            ch_name = data.get("name", "")
            sig_texts = data.get("signal_texts", [])
            for raw_text in sig_texts:
                sig_csv_rows.append({
                    "channel_name": ch_name,
                    "channel_id": ch_id,
                    "signal": raw_text,  # signal brut, tel quel
                })

        if sig_csv_rows:
            st.info(f"📊 {len(sig_csv_rows)} signaux bruts à exporter")

            # Preview: show first 5 signals
            with st.expander("👁️ Aperçu (5 premiers signaux)"):
                for i, row in enumerate(sig_csv_rows[:5]):
                    st.markdown(f"**{row['channel_name']}** · `{row['channel_id']}`")
                    st.text(row['signal'])
                    if i < 4:
                        st.divider()

            # CSV download — UTF-8 with BOM for Excel, QUOTE_ALL for multi-line
            sig_csv_buf = _io.StringIO()
            sig_csv_buf.write('\xEF\xBB\xBF')  # UTF-8 BOM
            writer = _csv.writer(sig_csv_buf, quoting=_csv.QUOTE_ALL, lineterminator='\n')
            writer.writerow(["channel_name", "channel_id", "signal"])
            for row in sig_csv_rows:
                writer.writerow([row["channel_name"], row["channel_id"], row["signal"]])
            sig_csv_content = sig_csv_buf.getvalue()

            st.download_button(
                "📥 Télécharger CSV des signaux bruts",
                data=sig_csv_content,
                file_name="signals_raw.csv",
                mime="text/csv",
                key="dl_signals_raw_csv",
            )
        else:
            st.warning("Aucun signal brut à exporter.")

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
