# HackConnect AI

**Find Your Hackathon. Build Your Dream Team.**

A hackathon discovery and collaboration platform with transparent skill matching, consent-based teammate discovery, transactional squad invitations, and persistent team workspaces.

> **Launch status:** implementation and local checks are in progress. This repository is not a verified live production deployment. Read [the task checklist](docs/PROGRESS.md), [test results](docs/VERIFICATION.md), and [launch requirements](docs/DEPLOYMENT.md) before enabling public access.

## What is implemented

- Supabase email/password and Google sign-in flows, email verification, reset, protected app navigation, logout, and account deletion integration.
- Six-step resumable onboarding with technical/nontechnical skills, custom skill normalization, proficiency, roles, interests, timezone-aware availability, privacy settings, and consent.
- Administrator-only CSV/Excel preview, column mapping, validation, duplicate handling, transactional imports, safe re-imports, invitation emails, and verified-email profile claiming. Imported records stay private and undiscoverable.
- Authorized Telegram webhook ingestion and export backfill; human-reviewed events retain provenance. Duplicate deliveries are idempotent; edited source posts return their event to review. Raw Telegram content is never sent to Grok.
- Independent event and registration lifecycle states, stale-source exclusion, cancellation handling, bookmarks, feedback, searchable/filterable discovery, and configurable scheduled checks.
- Transparent deterministic hackathon matching and complementary teammate ranking. A bounded team optimizer proposes a skill mix; it never silently confirms members.
- Squad invitations, accept/decline, leader permissions, role assignment, leadership transfer, capacity enforcement, and one squad per user per hackathon.
- Persistent member-only chat with pagination, read cursors, own-message edits/deletion, realtime updates and polling recovery; task board, comments, activity, milestones, resource links, and calculated progress.
- Optional Grok planning with Pydantic output validation, timeouts, retries, token limits, per-user/platform daily request budgets, usage records, and one-hour caching. Saving suggested tasks requires explicit approval.
- In-app notifications, user preferences, profile blocking, abuse reports, protected admin operations, and audit logs.

## Stack and structure

```text
frontend/                  Next.js App Router, TypeScript, React, Supabase JS
  app/                     Landing, auth, onboarding, discovery, squad and admin routes
  components/              Shared navigation, fields, loading/error/empty states
  lib/                     API client and Supabase client
  tests/                   Playwright public regression and opt-in staging journey
backend/                   FastAPI, Pydantic, psycopg, HTTPX, openpyxl
  app/                     API, auth, schemas, matching, importer, Grok, worker, migration
  tests/                   Unit, API guard, database journey, RLS and race tests
database/001_initial.sql   Versioned PostgreSQL schema, indexes, constraints and RLS
fixtures/                  Clearly labeled synthetic development records
docs/                      Architecture, algorithm, API, integration and deployment guides
.github/workflows/ci.yml   PostgreSQL-backed backend and browser/build CI
```

The backend uses explicit SQL and psycopg transactions rather than an ORM. Styling is responsive CSS with Lucide icons; Tailwind/shadcn were recommended in the brief, but are not dependencies. This keeps the initial implementation smaller while retaining the requested App Router and Python architecture.

## Quick start — Windows PowerShell

Requires Python 3.12+, Node.js 22+, and your own Supabase project.

```powershell
git clone https://github.com/Khubaaib/Hackconnect.ai.git
cd Hackconnect.ai
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

Fill the environment files. Never put service-role, database, Telegram, scheduler, or Grok secrets in `NEXT_PUBLIC_*` variables. Apply `database/001_initial.sql` once in Supabase SQL Editor, or run the migration command with a configured database connection.

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.migrate
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

In another terminal:

```powershell
cd Hackconnect.ai\frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. API documentation is at `http://localhost:8000/docs`. `/health` is process liveness; `/ready` checks schema and authentication configuration.

Configure Supabase Auth email verification, your Site URL, redirect allowlist for `/auth/callback`, Google OAuth if needed, and an email provider before testing the real registration journey. Register your own account first, then assign admin privileges with the SQL in [deployment instructions](docs/DEPLOYMENT.md). Never allow a browser to self-assign an admin role.

## Tests

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests/test_core.py tests/test_api.py -q
cd ..\frontend
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

Database tests require an isolated PostgreSQL test database, the test-only bootstrap and the migration. The CI workflow creates it automatically. **Never run `database/tests/bootstrap.sql` against your real Supabase project.**

The staging Playwright journey is opt-in via `TEST_BASE_URL`, `LIVE_USER_EMAIL`, `LIVE_USER_PASSWORD`, and `LIVE_EVENT_ID`. It creates real test data; use a dedicated staging account and hackathon. Browser smoke tests do not substitute for live Supabase, Telegram, Grok, email, and hosting verification.

## Deployment

Frontend: Vercel with root directory `frontend`. Backend: Render Docker service using `render.yaml`, or equivalent Railway deployment. Database/auth/realtime: Supabase. Run `python -m app.worker` hourly using a managed scheduler. Set separate staging/production environments; complete the [deployment checklist](docs/DEPLOYMENT.md).

There is no payment integration and no fake event or student dataset presented as real. The actual 71-student dataset, Telegram ownership/configuration, Grok key/model, Supabase project, and hosting accounts must be supplied and verified before launch.

## Design and safety notes

- Scores are profile-fit metrics, not probabilities of acceptance or team success.
- Missing facts remain unknown. Imported skill proficiency stays unspecified until the student reviews it.
- Supabase client roles can read only RLS-authorized rows; all application writes go through authorized FastAPI endpoints.
- The API database credential is server-only and privileged. Compromise of this credential bypasses RLS; use a dedicated service account, secret rotation, access restrictions, and staging validation.
- Current discovery bounds scans to 1,000 events and 500 candidates, and ideal-squad search to 15 candidates and four extra seats. These are explicit initial scale limits.
- Existing squad communication is unaffected by profile blocking; blocking prevents discovery/invitations. Leave the squad or report abuse to revoke shared-room access.
- Direct file upload to squad chat is not implemented; approved HTTPS resource links support file sharing.
- Legal/operator contact, exact retention/backup periods, monitoring/alerts, and live launch verification remain operator setup items.

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [Matching](docs/MATCHING.md) · [API](docs/API.md) · [Integrations](docs/INTEGRATIONS.md) · [Security](docs/SECURITY.md) · [Deployment](docs/DEPLOYMENT.md) · [Task checklist](docs/PROGRESS.md) · [Verification](docs/VERIFICATION.md)
