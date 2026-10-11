# API v1

FastAPI exposes `/docs` and `/openapi.json`. Requests use JSON except CSV/XLSX multipart import. Authenticate with `Authorization: Bearer <Supabase access token>`. Verified email is required. Unauthorized access returns 401/403, missing/private resources 404, stale versions/conflicts 409, invalid data 422, rate budget 429, and unavailable dependencies 503. Errors use FastAPI `detail`; request identifiers are returned in `X-Request-ID`.

| Domain | Routes |
|---|---|
| Health | `GET /health`, `GET /ready` |
| Profile | `GET/PUT/DELETE /api/v1/me`, `POST /me/claim-import` |
| Preferences | `GET/PUT /me/notification-preferences`, `DELETE /me/hidden-events` |
| Events | `GET /hackathons`, `GET /hackathons/{id}`, `PUT /hackathons/{id}/bookmark`, `POST /hackathons/{id}/hide` |
| Matching | `GET /hackathons/{id}/teammates?team_id=…&ideal=true` |
| Squads | `GET/POST /teams`, `GET/PUT /teams/{id}`, `DELETE /teams/{id}/members/{user_id}`, `PUT /teams/{id}/members/{user_id}/role` |
| Invitations | `POST /teams/{id}/invitations`, `GET /invitations`, `PATCH /invitations/{id}` |
| Chat | `GET/POST /teams/{id}/messages`, `PATCH/DELETE /teams/{id}/messages/{message_id}`, `POST /teams/{id}/messages/read` |
| Tasks | `POST /teams/{id}/tasks`, `PUT/DELETE /teams/{id}/tasks/{task_id}`, `GET/POST /teams/{id}/tasks/{task_id}/comments` |
| Milestones | `POST /teams/{id}/milestones`, `PUT /teams/{id}/milestones/{milestone_id}` |
| Resources | `POST /teams/{id}/resources`, `DELETE /teams/{id}/resources/{resource_id}` |
| Grok | `POST /teams/{id}/copilot` |
| Notifications | `GET /notifications`, `PATCH /notifications/{id}` |
| Safety | `POST /reports`, `GET /blocks`, `PUT/DELETE /blocks/{user_id}` |
| Administration | `GET /admin/overview`, `GET/POST /admin/hackathons`, `PUT /admin/hackathons/{id}`, `GET /admin/{section}` |
| Import | `POST /admin/import/preview`, `POST /admin/import/commit`, `POST /admin/import/invite/{record_id}` |
| Source review | `POST /admin/sources`, `POST /admin/ingestion/backfill`, `POST /admin/ingestion/{id}/publish` |
| Moderation | `PATCH /admin/reports/{id}`, `PUT /admin/students/{id}/hide` |
| Scheduler | `POST /admin/sync`, `POST /jobs/checks` with `X-Job-Secret` |
| Telegram | `POST /integrations/telegram` with `X-Telegram-Bot-Api-Secret-Token` |

All table writes use bound parameters. Client JSON cannot introduce a global role or arbitrary SQL field. The backend verifies task assignees against current membership. GET discovery defaults to 20 items with offset and caps scan breadth at 1000 records. Messages support a timestamp `before` cursor and page sizes up to 100.
