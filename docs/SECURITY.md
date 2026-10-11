# Security and launch review

Implemented controls: verified Supabase tokens checked server-side; administrator roles from the database; current team membership on every workspace endpoint; read-only browser grants and RLS; safe teammate projection; input schemas with forbidden extra fields; parameterized SQL; body/upload limits including chunked request bounds; allowed HTTPS links; React text rendering rather than raw HTML; CORS allowlist; per-user request counters; transactional membership/capacity constraints; task version checks; webhook/job shared-secret checks; auditable admin writes; Grok input/output/request budgets; no secret exposure in client code.

Authenticated user API requests default to 120 per minute. Supabase manages auth endpoint protections. Admin operations and webhook ingress also require infrastructure rate limits before production; deploy them at the hosting edge. Never trust proxy headers without configuring the host proxy chain.

The backend uses a privileged, server-only database connection. RLS protects Supabase browser reads; API authorization protects writes. Restrict access to the DB credential, rotate secrets, use SSL, use a dedicated limited write role when finalizing production, and validate every endpoint with a non-admin test account.

Privacy settings gate discovery; emails, exact availability windows and unclaimed student records do not appear in teammate cards. Blocking affects discovery and invitations, not existing squad-room history. Members can leave a room; administrators can review reports and hide offending profiles. Final account deletion calls Supabase Admin and relies on FK cleanup; shared message tombstones/anonymous attribution remain. Confirm legal retention and backup behavior before accepting real data.

Public privacy/terms pages are clearly marked launch drafts. Supply operator identity, contact, age/jurisdiction rules, retention/deletion procedures and policy review before launch. No claim of legal compliance is made.

Operational launch checks: configure edge throttling/WAF, TLS, error alerting, production secrets, backup restore rehearsal, SMTP, Google OAuth, staging tests, dependency scan and real-time privacy checks. Structured request logs omit authorization headers and payloads. Request IDs allow incident tracing; an external monitoring/alert sink still needs configuration.
