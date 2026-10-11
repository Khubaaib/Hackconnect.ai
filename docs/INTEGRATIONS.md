# Integration setup

## Supabase

Create a project owned by the project operator. Apply the migration, configure Auth email verification, password policy, email SMTP, and Google provider if desired. Set Site URL and callback redirect allowlist for local, staging and production origins. Set `SUPABASE_URL`, anon/publishable key, server-only service-role key and PostgreSQL connection URI. For transaction pooling, prepared statements are disabled in psycopg.

Realtime: the migration adds team_messages/project_tasks/milestones/notifications to an existing `supabase_realtime` publication. Confirm publication membership and SELECT grants. RLS gates client row visibility. The frontend falls back to polling and refresh-on-tab-focus. Test two accounts and a removed member against the actual Supabase project; native PostgreSQL fixtures alone do not test Supabase realtime or Auth.

## Authorized student import

Use Admin → imports. Upload UTF-8 CSV or `.xlsx` under 5 MB, with at most 1000 rows. Supported mappings: email, display_name, institution, skills, nontechnical. Inferred header aliases include Full Name, Email Address, College, Technical Skills and Nontechnical Skills. Supply a mapping JSON if needed. Skill lists accept commas/semicolons. Excel is read in read-only/data-only mode and expanded size is bounded.

Preview shows valid, invalid and duplicate rows. Confirm authority to import and commit valid rows. An email uniqueness constraint and file+mapping digest enforce safe re-import. Proficiency is unspecified when absent in the source; students review levels. Unclaimed records have no public profile and cannot appear as teammates.

For invitation email, configure Supabase SMTP and click Send account-claim invitation for a private imported record. The student verifies their own email, opens onboarding, and clicks Claim imported profile. The email must match the preloaded record. Repeated claims and claims over a completed profile are rejected. Students can correct details, opt out, or delete their account. Do not commit the real 71-student file to GitHub.

## Telegram

Use an operator-authorized channel integration. Create a Telegram bot, add it to the authorized channel with the necessary privileges, and configure a webhook to `https://YOUR-API/api/v1/integrations/telegram` with a strong Telegram secret token. Set `TELEGRAM_CHANNEL_ID` to the numeric channel id, and the same secret as `TELEGRAM_WEBHOOK_SECRET`. The secret header and exact channel id are checked server-side.

In Admin → sources, create an authorized source whose reference is `telegram:<numeric channel id>`. New/edited channel posts enter the review queue. Identical retries do not invalidate reviewed events. A materially edited post invalidates the published event until an administrator checks its metadata. In Admin → ingestion, select Review as event, add confirmed dates, URLs, requirements and rules, then save with `verification_status=verified`.

Historical backfill requires an authorized owner-provided export/feed. Admin → sources supports a backfill JSON with `source_id` and `announcements` containing stable references. The Bot API webhook is not a historical channel scraper. Deletions/cancellations are not reliably inferred: administrators must mark them based on an authoritative update. No unauthorized scraping, automatic rights assumptions, or external AI processing of raw Telegram posts is implemented.

## Grok / xAI

Set backend-only `XAI_API_KEY` and an available `XAI_MODEL` from your account. The provider uses `https://api.x.ai/v1/chat/completions` with JSON response mode and a Pydantic output contract. No model availability, billing credit or free quota is assumed. This integration requires a live key/model test before launch.

Retries: at most three attempts with exponential backoff. Timeout: 25 seconds per attempt. Output: at most 1500 requested tokens. Input context is bounded. Daily logical-request caps: user 20, platform 200 by default. Retries may consume additional billable provider requests; set an account-level spend limit too. Usage records count returned input/output tokens, not monetary cost, and a reserved logical request remains consumed when a call fails. Core matching does not invoke Grok.

Every current member must opt into AI sharing, and the leader must enable team consent. The context contains skills/roles, task descriptions/status and event timing/requirements; it excludes private contacts, chat history, event titles/descriptions and raw announcements. Do not place confidential information in tasks/prompts. AI results are cached for one hour, scoped to user/team and actual context. Approval buttons save selected suggested tasks through the ordinary API.
