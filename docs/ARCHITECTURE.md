# Architecture

The browser uses Supabase Auth for identity and stores the managed session through Supabase JS. It sends the access token as a bearer header to FastAPI. FastAPI checks the token with the Supabase Auth user endpoint, requires verified email, and checks administrator roles from the database. It never trusts a role in browser state or user-editable profile metadata.

FastAPI owns writes and transactions. Its server-only PostgreSQL connection writes normalized records and checks resource ownership on each endpoint. Supabase client roles have read-only grants and RLS; private messages and team records require current membership. No client-visible table exposes the private imported-student records. Public teammate responses are explicitly projected to safe fields and honor profile visibility.

The database covers identity, preferences, availability, skill taxonomy and proficiency, event/source provenance, raw ingestion, bookmarks, feedback, recommendation cache/version, squad invitations and members, messages/read cursors, tasks/comments, resources, milestones, activity, notifications, imports, job/audit records, reports/blocks, request limits and AI usage/cache.

Invitation acceptance locks the team row first, then the invitation row. Capacity is checked inside the transaction. A unique constraint on `(hackathon_id,user_id)` prevents conflicting membership; a partial unique index prevents duplicate pending invitations. Task updates require the version read by the client to prevent lost updates.

Realtime subscriptions are scoped to the current squad. Supabase RLS authorizes row delivery; polling and tab-visibility refresh recover from missed notifications. Message deletion is a tombstone update to keep realtime behavior predictable. The authoritative conversation lives in PostgreSQL, not browser state.

Scheduled checks run transactionally under an advisory lock. Notification dedupe keys prevent repeated delivery. Stale events become `needs_correction`; closed/completed/cancelled events are excluded by a fresh lifecycle calculation on every discovery request. Workers do not silently scrape third-party websites.

Grok is behind a provider class. Only approved member skills and team tasks are sent; raw Telegram posts, chat messages, private contact data, and event descriptions are excluded. Every member and the leader must consent. The provider has bounded retries and structured output validation. A database reservation enforces user/platform request limits before the network call. A plan cannot mutate the task board; the user must approve each task.

Initial deliberate tradeoffs: one API deployment, direct SQL rather than SQLAlchemy/Alembic, CSS rather than Tailwind/shadcn, bounded candidate scans, Postgres Changes rather than Broadcast, resource links rather than object uploads. No unnecessary microservices. Add a restricted database write role, observability sink, retry queue for outbound email, and larger-dataset evaluation before growth beyond the initial community.
