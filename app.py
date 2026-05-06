import streamlit as st
import asyncio
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

st.set_page_config(page_title="Telegram Channel Lister", page_icon="📢", layout="wide")

st.title("📢 Telegram Channel Lister")
st.markdown("Liste de tous les channels et groupes Telegram que tu as rejoint.")

# Session state init
if "step" not in st.session_state:
    st.session_state.step = "config"
if "phone" not in st.session_state:
    st.session_state.phone = ""


def get_loop():
    if "loop" not in st.session_state:
        st.session_state.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(st.session_state.loop)
    return st.session_state.loop


def get_client(api_id_val, api_hash_val):
    if "client" not in st.session_state:
        loop = get_loop()
        client = TelegramClient("session", int(api_id_val), api_hash_val)
        loop.run_until_complete(client.connect())
        st.session_state.client = client
    return st.session_state.client


# Sidebar - only API credentials
with st.sidebar:
    st.header("⚙️ Configuration")
    api_id = st.text_input("API_ID", type="password", help="Obtenu sur my.telegram.org/apps")
    api_hash = st.text_input("API_HASH", type="password", help="Obtenu sur my.telegram.org/apps")


# Step 1: Phone number
if st.session_state.step == "config":
    st.subheader("📱 Étape 1 : Connexion")
    phone = st.text_input("Numéro de téléphone", placeholder="+33612345678")

    if st.button("📨 Envoyer le code", type="primary"):
        if not api_id or not api_hash or not phone:
            st.error("❌ Remplis tous les champs.")
        else:
            with st.spinner("Connexion à Telegram..."):
                try:
                    client = get_client(api_id, api_hash)
                    loop = get_loop()
                    result = loop.run_until_complete(client.send_code_request(phone))
                    st.session_state.phone = phone
                    st.session_state.phone_code_hash = result.phone_code_hash
                    st.session_state.step = "code"
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erreur: {e}")

# Step 2: Verification code
elif st.session_state.step == "code":
    st.subheader("🔑 Étape 2 : Code de vérification")
    st.info(f"📲 Un code a été envoyé à **{st.session_state.phone}**")

    code = st.text_input("Entre le code reçu", placeholder="12345")

    if st.button("✅ Vérifier", type="primary"):
        if not code:
            st.error("❌ Entre le code.")
        else:
            with st.spinner("Vérification..."):
                try:
                    client = st.session_state.client
                    loop = get_loop()
                    loop.run_until_complete(client.sign_in(
                        phone=st.session_state.phone,
                        code=code,
                        phone_code_hash=st.session_state.phone_code_hash
                    ))
                    st.session_state.step = "done"
                    st.rerun()
                except Exception as e:
                    err = str(e)
                    if "password" in err.lower() or "2fa" in err.lower():
                        st.session_state.step = "password"
                        st.rerun()
                    else:
                        st.error(f"❌ Erreur: {e}")

# Step 2b: 2FA
elif st.session_state.step == "password":
    st.subheader("🔐 Mot de passe 2FA")
    st.warning("Telegram demande un mot de passe 2FA pour cet compte.")
    password = st.text_input("Mot de passe Telegram", type="password")

    if st.button("✅ Se connecter", type="primary"):
        with st.spinner("Vérification..."):
            try:
                client = st.session_state.client
                loop = get_loop()
                loop.run_until_complete(client.sign_in(password=password))
                st.session_state.step = "done"
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erreur: {e}")

# Step 3: Show results
elif st.session_state.step == "done":
    st.success("✅ Connecté !")

    client = st.session_state.client
    loop = get_loop()

    channels = []
    groups = []

    with st.spinner("Chargement des channels..."):
        async def fetch_dialogs():
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                if isinstance(entity, Channel):
                    if entity.megagroup:
                        groups.append({"id": entity.id, "title": entity.title, "type": "🔵 Supergroupe"})
                    else:
                        channels.append({"id": entity.id, "title": entity.title, "type": "📢 Channel"})
                elif isinstance(entity, Chat):
                    groups.append({"id": entity.id, "title": entity.title, "type": "💬 Groupe"})

        loop.run_until_complete(fetch_dialogs())

    # Stats
    col1, col2, col3 = st.columns(3)
    col1.metric("📢 Channels", len(channels))
    col2.metric("💬 Groupes", len(groups))
    col3.metric("📊 Total", len(channels) + len(groups))

    st.divider()

    if channels:
        st.subheader(f"📢 Channels ({len(channels)})")
        st.dataframe(channels, use_container_width=True, hide_index=True)

    if groups:
        st.subheader(f"💬 Groupes ({len(groups)})")
        st.dataframe(groups, use_container_width=True, hide_index=True)

    st.divider()
    all_items = channels + groups
    if all_items:
        import pandas as pd
        df = pd.DataFrame(all_items)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Télécharger en CSV", csv, "telegram_channels.csv", "text/csv")

    if st.button("🔌 Se déconnecter"):
        loop.run_until_complete(client.disconnect())
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
