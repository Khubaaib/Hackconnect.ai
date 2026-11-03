# Deterministic matching v1

## Hackathon fit

First exclude non-verified, stale, cancelled, completed, registration-closed and deadline-unknown listings from active discovery. Scores cannot override country eligibility, required student status, practical offline location/travel, explicit availability incompatibility, or unreviewed additional eligibility requirements.

Initial weights: skill fit .30, domain interests .25, role preferences .15, availability .10, experience .10, attendance format .10. Experience is intentionally excluded without real event experience constraints; unspecified skills, domains, roles and schedule are omitted and explicitly marked unknown. The denominator contains only evaluated dimensions.

Skill fit is the average `min(user_proficiency / required_proficiency,1)` over required skills. Unknown imported proficiency contributes zero. Domain and role scores are overlap fractions over event requirements. Schedule is evaluated only with explicit user windows and event start/end. Format checks an exact or `any` preference.

A score is a transparent product heuristic, not a validated probability. The API returns evaluated components, matching/missing skills, unknowns, blockers and version. Input hashes bind cached scores to the actual profile and event. Profile or event updates invalidate cached entries; lifecycle and verification checks still run fresh.

## Teammates

Remove blocked profiles, opted-out/unclaimed/incomplete/unavailable profiles, existing same-event members and ineligible candidates. Assess their skills against the user's and existing team's covered requirements. Weight additional skill coverage at 80%; explicit pairwise availability overlap and relevant domain interest each add up to 10%. Unknown availability never becomes a fabricated compatibility claim.

A candidate with React/UI/UX can outrank another Python developer for an AI/backend user if React/design are missing. Each response gives contributed skills and gaps remaining. Contact email and raw availability windows are not in the response.

The ideal-squad search explores combinations over the first 15 ranked candidates and at most four available seats. It maximizes distinct additional skill coverage, then total candidate scores, and rejects known pairwise schedule incompatibility. It is a bounded initial heuristic; it does not claim a globally optimal squad for a larger population. All resulting members still require invitations and explicit acceptance.

Candidate consent, event availability, eligibility, existing membership and capacity are checked again when sending/accepting invitations. Test examples include no skills, aliases/custom skills, missing dates, closed registration during an ongoing event, unknown schedules, complementary roles, country ineligibility, declined/duplicate invitations and full teams.

## Direct teammate search

Dashboard → Teammates works independently of hackathon publication and registration dates. `POST /api/v1/teammates/search` accepts `query`, `use_ai`, `offset`, and `limit`. It reads the latest completed, discoverable, consenting profiles accepting invitations and excludes blocks in both directions. Search covers up to 1,000 recently updated profiles, explicitly disclosed if bounded. The directory also searches operator-authorized unclaimed imported names, institutions, and skills. These rows are marked imported and cannot receive invitations. Claimed imports and imports whose email matches a registered account are represented only by the account, subject to its privacy and block settings. Private contact information and roll numbers are excluded.

With AI enabled, Grok extracts skills, roles and interests from the search text using a validated JSON schema. No student profiles or contact details are sent to xAI. The server ranks actual eligible database profiles against those criteria and returns the supporting evidence. AI requests use the existing daily quotas and cache; availability/configuration/budget failures fall back to keyword search with a visible notice. Proficiency is not inferred from skill mentions. Relevance is not an acceptance probability.

Event-specific recommendations still enforce event eligibility, availability and membership rules. When the current team already covers all required skills, relevance is scored against the event requirements rather than an empty gap set. Events without skill/domain requirements use complementary profile relevance. Squad creation and invitations continue to require a reviewed, open event.
