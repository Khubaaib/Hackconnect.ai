# HackConnect.AI

**Find your hackathon. Build your dream team.**

HackConnect.AI brings hackathon discovery, skill-based teammate recommendations, and team collaboration into one platform. Students can build a profile, explore reviewed opportunities, form a complementary squad, and manage their work together.

**[Open the live application](https://hackconnect-ai.vercel.app/)** · **[Sign in](https://hackconnect-ai.vercel.app/auth)** · **[Report an issue](https://github.com/Khubaaib/Hackconnect.ai/issues)**

Maintained by [Khubaaib Iqbal](https://github.com/Khubaaib).

## Project status

The application is hosted on Vercel, with a FastAPI backend on Render and PostgreSQL, authentication, and realtime services on Supabase. The live homepage was checked on October 12, 2026; this check does not establish that every authenticated workflow or external integration has passed end-to-end verification.

The discovery page displays original announcements from one configured Telegram channel. The client reader imports recent posts and synchronizes new posts, edits, and recent removals. Live ingestion requires the operator’s saved Telegram session in the backend environment. Structured hackathon records still use the separate administrator-review pipeline. Grok planning requires a configured xAI key and model.

See [verification notes](docs/VERIFICATION.md) and the [deployment checklist](docs/DEPLOYMENT.md) for detailed validation requirements.

## Features

| Area | Capabilities |
| --- | --- |
| Student profiles | Resumable onboarding, technical and soft skills, interests, roles, availability, and privacy preferences |
| Hackathon discovery | Search and filters, registration deadlines, event lifecycle states, bookmarks, and source provenance |
| Team matching | Explainable skill-fit scores, complementary teammate ranking, and suggested squad composition |
| Squad formation | Invitations, acceptance and decline, capacity checks, role assignment, and leadership transfer |
| Team workspace | Persistent member-only chat, task boards, comments, milestones, resources, and progress tracking |
| AI assistance | Optional Grok planning and architecture suggestions with structured output validation and usage limits |
| Administration | CSV/Excel import previews, duplicate handling, private profile claims, event review, moderation, and audit logs |
| Telegram discovery | A single-channel announcement feed, read-only client synchronization, duplicate handling, source links, and attachment notices |

Recommendations do not automatically enroll students in a team. Members accept invitations, and AI-generated tasks are reviewed before they are saved.

## How it works

1. **Create a profile.** Add your skills, preferred roles, interests, and availability.
2. **Explore an opportunity.** Review the hackathon requirements, deadlines, and source.
3. **Find complementary teammates.** Inspect the reasons behind recommendations and send invitations.
4. **Build together.** Coordinate through the squad chat, tasks, resources, and milestones.

Imported student records remain private until the student verifies the matching email and claims their profile.

## Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js App Router, React, TypeScript, responsive CSS, Lucide icons |
| Backend | Python, FastAPI, Pydantic, psycopg, HTTPX |
| Database | PostgreSQL on Supabase, explicit SQL transactions, constraints, row-level security |
| Authentication and realtime | Supabase Auth and Realtime |
| AI provider | xAI / Grok, optional |
| Event integration | Telegram Bot API webhooks |
| Hosting | Vercel frontend, Render backend |
| Quality checks | pytest, PostgreSQL integration tests, Playwright, GitHub Actions |

## Repository structure

```text
frontend/                  Web application and browser tests
backend/
  app/                     API, authentication, matching, imports, AI, and worker
  tests/                   Unit, API, and database integration tests
database/
  001_initial.sql          Initial schema, constraints, indexes, and RLS
  002_imported_student_roll_number.sql
                           Additive roll-number field migration
  tests/                   Isolated test database bootstrap
fixtures/                  Synthetic development data
docs/                      Architecture, API, integrations, security, and deployment
.github/workflows/         Continuous integration
render.yaml                Backend hosting configuration
```

## Run locally

Prerequisites: Python 3.12+, Node.js 22+, and a Supabase project.

### 1. Clone and configure

```powershell
git clone https://github.com/Khubaaib/Hackconnect.ai.git
cd Hackconnect.ai
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

Fill the environment files using your own service configuration. Keep database, service-role, Telegram, scheduler, and xAI credentials on the backend. Only the intended public frontend configuration belongs in `NEXT_PUBLIC_*` variables.

### 2. Initialize the database and start the backend

Apply `database/001_initial.sql` once in Supabase SQL Editor, or run the initial migration command below. Apply `database/002_imported_student_roll_number.sql` and `database/003_telegram_feed.sql` separately in SQL Editor; the current migration runner handles the initial schema only.

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.migrate
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### 3. Start the frontend

In a second terminal, from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

- Application: `http://localhost:3000`
- API documentation: `http://localhost:8000/docs`
- Liveness: `/health`
- Readiness: `/ready`

Configure the Supabase Auth site URL and callback allowlist before testing registration. See [integration setup](docs/INTEGRATIONS.md) for email delivery, OAuth, Telegram, and Grok configuration.

## Validation

From the repository root:

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests/test_core.py tests/test_api.py -q
cd ..\frontend
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

Database integration tests require an isolated test database. The CI workflow provisions that environment. Never apply `database/tests/bootstrap.sql` to a production Supabase project.

The opt-in staging browser journey uses `TEST_BASE_URL`, `LIVE_USER_EMAIL`, `LIVE_USER_PASSWORD`, and `LIVE_EVENT_ID`. Use dedicated test accounts and events because it creates data.

## Deployment

- **Vercel:** use `frontend` as the project root and configure the public API origin and Supabase client settings.
- **Render:** use `backend/Dockerfile` with the repository root as the build context; keep server secrets in environment variables.
- **Supabase:** apply the schema migrations and configure authentication, callback URLs, and realtime.
- **Scheduled checks:** run `python -m app.worker` through a managed scheduler.

Detailed instructions are in [Deployment](docs/DEPLOYMENT.md). Hosting the frontend and backend is separate from publishing source code to GitHub.

## Data and integration boundaries

- Student datasets, phone numbers, email lists, and production credentials must not be committed to this public repository.
- Skill-fit scores explain matching criteria; they are not probabilities of winning or selection.
- Core matching works without an AI provider. Grok is used for optional planning assistance.
- Original Telegram announcements retain their source and appear in channel discovery without invented event metadata. Structured event records use an administrator review form; reviewed open events link directly from their announcement to skill matching and squad creation.
- Telegram posters and documents open through their original Telegram link. Text filtering is deterministic; image content is not analyzed.
- Synchronization imports the latest 200 posts initially, drains new posts in batches of 200, and reconciles edits and removals in the latest 200 stored posts.
- Polling runs while the web service is awake. A sleeping free hosting service needs scheduled wakeups or an always-on service for continuous updates.
- The imported-student roll-number field is database storage; automatic transfer to claimed profiles and a dedicated UI are not implemented.
- Squad file sharing currently uses resource links rather than direct chat uploads.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Matching algorithms](docs/MATCHING.md)
- [API reference](docs/API.md)
- [Integration setup](docs/INTEGRATIONS.md)
- [Telegram client setup](docs/TELEGRAM_CLIENT_SETUP.md)
- [Security](docs/SECURITY.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Progress checklist](docs/PROGRESS.md)
- [Verification notes](docs/VERIFICATION.md)

