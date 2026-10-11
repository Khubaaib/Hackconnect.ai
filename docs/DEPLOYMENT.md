# Production deployment

## 1. Identity and database

Use an operator-owned Supabase project separate from staging. Apply `database/001_initial.sql` once. It is transactional; `python -m app.migrate` skips an already-created migration record. Fresh migration is tested in CI; upgrades beyond v001 require new numbered migrations, never destructive reapplication.

Set verified email/password policy, production Site URL, explicit `/auth/callback` redirect allowlists, SMTP and Google OAuth. Register the intended administrator, then grant their role using the trusted SQL Editor:

```sql
-- Replace the UUID with the verified intended user's auth.users.id.
INSERT INTO public.user_roles(user_id,role) VALUES('YOUR-VERIFIED-USER-UUID','admin') ON CONFLICT DO NOTHING;
```

Only a trusted operator can do this. Do not use frontend state, display name or user-editable metadata to grant admin.

## 2. Backend on Render (or Railway)

Connect **Khubaaib/Hackconnect.ai** to the intended brother/operator account. Use the root Docker context and `backend/Dockerfile`. `render.yaml` declares a web service and environment placeholders; applying it may allocate billed hosting resources, so select the intended plan in the provider. Startup is `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

Set the backend variables in `backend/.env.example` with `ENVIRONMENT=production` and exact HTTPS frontend CORS origins. Required production fields are validated at startup. Set health check `/ready`. The API never embeds Grok, Telegram, database or service-role secrets into the browser.

Run migration as an operator/release job before starting web workers. Configure platform JSON logging and error alerts. Choose infrastructure limits appropriate for the small initial community; do not expose reload/dev servers.

## 3. Frontend on Vercel

Import only `Khubaaib/Hackconnect.ai`. Set root directory `frontend`, framework Next.js, build `npm run build`, package install `npm ci`. Add the three `NEXT_PUBLIC_*` values from `.env.example`; the API origin must be the deployed HTTPS backend. The Supabase anon/publishable key is intentionally browser-visible, unlike the service-role key.

Use distinct staging and production environments and Auth callback allowlists. Preview URLs must not receive unrestricted production credentials.

## 4. Worker and Telegram

Configure an hourly managed scheduled process running `python -m app.worker` in the backend image with the same backend environment, or call `POST /api/v1/jobs/checks` with `X-Job-Secret`. Verify schedule history in Admin → jobs. An advisory transaction lock and notification dedupe keys make successful repeated checks safe.

Follow INTEGRATIONS.md to authorize the Telegram source and configure bot webhook delivery. Observe a new post, a duplicate delivery, an edited post and a reviewed event. Historical ingestion requires an owner-authorized export.

## 5. Launch verification

- [ ] `/health` and `/ready` return 200 on deployed API.
- [ ] Ordinary user cannot open admin APIs.
- [ ] Email signup/verification, Google sign-in and reset work with actual emails.
- [ ] Two real staging users complete onboarding.
- [ ] One current authoritative event passes admin review and appears in discovery.
- [ ] Closed/expired/cancelled/stale event does not appear as an active opportunity.
- [x] Native PostgreSQL CI confirms persistence and simultaneous acceptance capacity. Repeat with deployed staging users.
- [ ] Squad chat survives refresh/logout and realtime updates reach another account.
- [ ] A stranger/former member cannot retrieve or subscribe to private messages.
- [ ] Tasks, comments, milestones and calculated progress persist.
- [ ] Dataset import preview/commit/claim is verified using authorized data.
- [ ] Grok returns a valid plan, quota/outage states recover, and suggestions require approval.
- [ ] Scheduler runs and sends deduplicated notifications.
- [ ] Account deletion, moderation and block behavior are verified.
- [ ] Backups, restore rehearsal, incident alerts, edge rate limits and policy/contact information are configured.

The implementation cannot be called production-ready until this checklist passes in the configured deployment. No deployment was attempted without the required service accounts and secrets.
