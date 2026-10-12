# Telegram client authorization

Use this path for API ID + API hash credentials from Telegram API development tools.
It is separate from the existing Bot API webhook integration.

## One-time local setup

Run these commands in PowerShell on your own computer:

```powershell
git clone https://github.com/Khubaaib/Hackconnect.ai.git
cd Hackconnect.ai
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-telegram.txt
.\.venv\Scripts\python.exe backend\scripts\telegram_login.py
```

If you already have a clone, use `git pull` inside that repository instead of cloning again.

The helper asks for the API ID, hidden API hash, channel reference, hidden phone number,
login code, and two-step password when required. Enter credentials only in that local
terminal. Use the private invite link in the prompt rather than committing it to code.

The helper checks that the authenticated account has joined the channel and can read
its messages. It does not join channels, send messages, forward posts, or print post
contents. Successful setup creates `.env.telegram` in your current directory with:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_STRING`
- `TELEGRAM_CHANNEL_ID`

The file is ignored by Git. It grants account access and must remain private. On a shared
Windows computer, restrict file access to your Windows account. Never paste its contents
or a screenshot into chat. Telegram Settings → Devices can revoke the saved authorization.

## Deployment status

This helper prepares authorization only. It does **not** activate automatic ingestion
or publication. The current production app still uses the bot webhook and admin-review
pipeline described in [INTEGRATIONS.md](INTEGRATIONS.md).

After local access is confirmed, the next implementation work is a single-channel
server collector, bounded historical import, new/edited post synchronization,
duplicate handling, and channel-only display with original post references.
A session must be supplied through the server's private environment settings before
that collector can be tested against the actual channel.
