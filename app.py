import streamlit as st
import asyncio
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

st.set_page_config(page_title="Telegram Channel Lister", page_icon="📢", layout="wide")

st.title("📢 Telegram Channel Lister")
st.markdown("Liste de tous les channels et groupes Telegram que tu as rejoint.")

# Sidebar for config
with st.sidebar:
    st.header("⚙️ Configuration")
    api_id = st.text_input("API_ID", type="password", help="Obtenu sur my.telegram.org/apps")
    api_hash = st.text_input("API_HASH", type="password", help="Obtenu sur my.telegram.org/apps")
    phone = st.text_input("Numéro de téléphone", placeholder="+33612345678")
    connect_btn = st.button("🔗 Se connecter", type="primary")


async def get_dialogs(api_id_val, api_hash_val):
    """Fetch all dialogs (channels + groups) using Telethon."""
    client = TelegramClient("session", int(api_id_val), api_hash_val)
    await client.start()

    channels = []
    groups = []

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, Channel):
            if entity.megagroup:
                groups.append({
                    "id": entity.id,
                    "title": entity.title,
                    "members": getattr(dialog, "unread_count", "N/A"),
                    "type": "🔵 Supergroupe"
                })
            else:
                channels.append({
                    "id": entity.id,
                    "title": entity.title,
                    "members": getattr(dialog, "unread_count", "N/A"),
                    "type": "📢 Channel"
                })
        elif isinstance(entity, Chat):
            groups.append({
                "id": entity.id,
                "title": entity.title,
                "members": getattr(dialog, "unread_count", "N/A"),
                "type": "💬 Groupe"
            })

    await client.disconnect()
    return channels, groups


if connect_btn:
    if not api_id or not api_hash:
        st.error("❌ Remplis API_ID et API_HASH dans la barre latérale.")
    else:
        with st.spinner("Connexion en cours..."):
            try:
                channels, groups = asyncio.run(get_dialogs(api_id, api_hash))

                # Stats
                col1, col2, col3 = st.columns(3)
                col1.metric("📢 Channels", len(channels))
                col2.metric("💬 Groupes", len(groups))
                col3.metric("📊 Total", len(channels) + len(groups))

                st.divider()

                # Channels table
                if channels:
                    st.subheader(f"📢 Channels ({len(channels)})")
                    st.dataframe(
                        channels,
                        column_config={
                            "id": st.column_config.NumberColumn("ID", width="medium"),
                            "title": st.column_config.TextColumn("Nom", width="large"),
                            "type": st.column_config.TextColumn("Type", width="small"),
                        },
                        use_container_width=True,
                        hide_index=True,
                    )

                # Groups table
                if groups:
                    st.subheader(f"💬 Groupes ({len(groups)})")
                    st.dataframe(
                        groups,
                        column_config={
                            "id": st.column_config.NumberColumn("ID", width="medium"),
                            "title": st.column_config.TextColumn("Nom", width="large"),
                            "type": st.column_config.TextColumn("Type", width="small"),
                        },
                        use_container_width=True,
                        hide_index=True,
                    )

                # Download as CSV
                st.divider()
                all_items = channels + groups
                if all_items:
                    import pandas as pd
                    df = pd.DataFrame(all_items)
                    csv = df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "📥 Télécharger en CSV",
                        csv,
                        "telegram_channels.csv",
                        "text/csv",
                        type="secondary",
                    )

            except Exception as e:
                st.error(f"❌ Erreur: {e}")
                st.info("💡 Assure-toi que ton API_ID et API_HASH sont corrects.")
