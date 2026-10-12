"""Run locally to authorize Telegram and check one channel. Never run on a public server."""
import asyncio
import getpass
import os
from pathlib import Path
from urllib.parse import urlsplit
from telethon import TelegramClient, functions, types, utils
from telethon.sessions import StringSession

def invite_hash(reference):
    parsed = urlsplit(reference)
    if parsed.hostname not in ("t.me", "telegram.me"):
        return None
    path = parsed.path.strip("/")
    if path.startswith("+"):
        return path[1:]
    if path.startswith("joinchat/"):
        return path.split("/", 1)[1]
    return None

async def main():
    output = Path(".env.telegram").resolve()
    if output.exists():
        raise SystemExit(".env.telegram already exists. Move it to a private backup before creating another session.")
    api_id = int(input("Telegram API ID: ").strip())
    api_hash = getpass.getpass("Telegram API hash (hidden): ").strip()
    if api_id <= 0 or not api_hash:
        raise SystemExit("API ID and API hash are required.")
    reference = input("Channel username or invite link: ").strip()
    if not reference:
        raise SystemExit("A channel reference is required.")
    client = TelegramClient(StringSession(), api_id, api_hash, receive_updates=False)
    created = False
    saved = False
    try:
        await client.start(
            phone=lambda: getpass.getpass("Telegram phone number with country code (hidden): "),
            code_callback=lambda: getpass.getpass("Telegram login code (hidden): "),
            password=lambda: getpass.getpass("Telegram two-step password, if enabled (hidden): "),
        )
        created = True
        token = invite_hash(reference)
        if token:
            result = await client(functions.messages.CheckChatInviteRequest(token))
            if not isinstance(result, types.ChatInviteAlready):
                raise RuntimeError("This Telegram account has not joined the channel. Join it in Telegram first.")
            entity = result.chat
        else:
            entity = await client.get_entity(reference)
            if not isinstance(entity, types.Channel):
                raise RuntimeError("The reference must identify a Telegram channel or supergroup.")
            await client(functions.channels.GetParticipantRequest(entity, types.InputPeerSelf()))
        if not isinstance(entity, types.Channel):
            raise RuntimeError("This integration requires a Telegram channel or supergroup.")
        # Read permission check only: no join, send, or forwarding operations.
        messages = await client.get_messages(entity, limit=1)
        channel_id = utils.get_peer_id(entity)
        session = client.session.save()
        if not session:
            raise RuntimeError("Telegram did not create an authorized session.")
        values = (
            f"TELEGRAM_API_ID={api_id}\n"
            f"TELEGRAM_API_HASH={api_hash}\n"
            f"TELEGRAM_SESSION_STRING={session}\n"
            f"TELEGRAM_CHANNEL_ID={channel_id}\n"
        )
        # Exclusive create prevents accidental replacement of an existing secret.
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(values)
        saved = True
        print(f"Channel access verified: {entity.title}")
        print(f"Numeric channel ID: {channel_id}")
        print(f"Recent-message access checked: {'yes' if messages else 'channel has no accessible messages'}")
        print("Saved credentials to .env.telegram; no secret values were printed.")
        print("Keep this file private. Do not upload it to GitHub or send it in chat.")
        print("The app connection is not active yet; server collector setup is still required.")
    finally:
        if created and not saved:
            # Revoke an unused authorization rather than leaving it connected.
            await client.log_out()
        await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        raise SystemExit("Setup cancelled.")
    except Exception as exc:
        # Do not print arbitrary exception content that may include input secrets.
        raise SystemExit(f"Setup failed ({type(exc).__name__}). Check the account and channel access in Telegram.")
