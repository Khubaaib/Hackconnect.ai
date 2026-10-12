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

## Server activation

1. Apply `database/003_telegram_feed.sql` in the production Supabase SQL Editor.
2. Open Render → the HackConnect.AI backend → Environment. Add the four values
   from your local `.env.telegram` file, preserving every other existing setting.
   Use `TELEGRAM_CHANNEL_ID=-1003919421009` for the channel verified in local setup.
3. Save, rebuild, and deploy the backend. Never copy these values into Vercel or GitHub.
4. After deployment, sign in and open Discover. The reader starts automatically
   when all four values are present. The first run imports the latest 200 posts;
   later runs drain new posts in batches of 200 and reconcile recent edits/removals.

The feed refreshes every minute while the browser page is open. The backend polls
at least once a minute while its hosting service is awake. A free Render service
may sleep: continuous delivery requires an always-on instance or a configured
scheduler that calls the existing secret-protected jobs endpoint. No paid service
is created automatically.

Only the configured channel is displayed. Hackathon/project-competition text and
photo/document announcements are included. Other plain conversation is filtered
using deterministic keywords. Poster contents are not OCR-analyzed: students open
the original Telegram attachment. Posting dates are not treated as event deadlines.

Private-channel source links require channel membership. The app exposes saved
announcements only to authenticated app users; database client roles cannot read
the tables directly. Confirm that the operator has authority to redistribute
channel announcements to that audience before activating the session.

## Verification

- `GET /api/v1/telegram/announcements` requires an authenticated account.
- `POST /api/v1/admin/telegram/sync` requires an administrator.
- `POST /api/v1/jobs/checks` uses the existing job secret and also syncs Telegram.
- A healthy feed reports the actual channel title and last successful sync time.
- Expired sessions do not erase saved announcements. Error responses never expose
  Telegram sessions or raw RPC exceptions. Reauthorize locally when needed.

## From announcements to squads

The client queues relevant posts in Admin → ingestion. Repeated polling preserves
reviewed events. Material edits return linked events to review; detected source
removals cancel the linked event and hide its team-formation link.

Open Review as event, confirm the title, official registration link, dates, team
size, eligibility, and requirements, then choose Confirmed — enable team formation.
Only reviewed events with current registration show Find teammates / build squad
on their original Telegram announcement. Past deadlines and unknown dates never
become active opportunities automatically.

Students use their own verified email to claim imported skills, complete onboarding,
and opt into discovery/invitations. They create a squad and invite recommended
teammates; acceptance creates membership and access to private chat. Login alone
does not create a squad.

The operator account needs an explicitly assigned admin role. Never choose that
account from a display name or give students an administrator role automatically.
The complete announcement → review → complementary matching → invitation →
acceptance → private chat workflow is exercised with disposable synthetic accounts
in the database integration suite.
