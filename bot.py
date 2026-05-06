"""
Telegram Bot - List Joined Channels
Uses a user account (Telethon) to fetch all channels/supergroups you've joined.
"""

import asyncio
import os
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

# === CONFIG ===
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_NAME = os.environ.get("SESSION_NAME", "channel_lister")


async def main():
    if not API_ID or not API_HASH:
        print("❌ Set API_ID and API_HASH environment variables first.")
        print("   Get them at https://my.telegram.org/apps")
        return

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    print("🔍 Fetching your dialogs...\n")

    channels = []
    groups = []

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, Channel):
            if entity.megagroup:
                groups.append((entity.id, entity.title))
            else:
                channels.append((entity.id, entity.title))
        elif isinstance(entity, Chat):
            groups.append((entity.id, entity.title))

    # Display channels
    print(f"📢 CHANNELS ({len(channels)}):")
    print("-" * 50)
    for cid, title in sorted(channels, key=lambda x: x[1].lower()):
        print(f"  ID: {cid:<15} | {title}")

    # Display groups
    print(f"\n💬 GROUPS ({len(groups)}):")
    print("-" * 50)
    for gid, title in sorted(groups, key=lambda x: x[1].lower()):
        print(f"  ID: {gid:<15} | {title}")

    print(f"\n✅ Total: {len(channels)} channels, {len(groups)} groups")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
