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
