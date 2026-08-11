# Phase 3.92 PR-003 — Historical bootstrap

**Implementation status:** complete; automated verification passed on 2026-08-11. The initial
live FMP attempt returned HTTP 429 for both chambers; cursors remain safely at page 0.

## Scope

- Persist independent House and Senate pagination cursors.
- Import at most one 25-row page per chamber and user action.
- Advance a cursor only after its raw payload and normalized observations commit atomically.
- Stop a chamber on an empty page and retain the failed page for a safe retry.
- Keep every historical row marked `known_at_status=observed_by_app` at import time.

## Out of scope

- No unattended quota-draining loop.
- No Quiver scraping or paid API dependency.
- No claim that retrospective filing dates were observed prospectively.
- No copyable-return calculation; outcome policy remains a separate preregistered task.

## Acceptance criteria

1. House and Senate cursors advance independently and persist across sessions.
2. Identical retries do not duplicate normalized observations.
3. Failure does not advance the cursor.
4. Empty pages mark the chamber complete.
5. API keys never enter database metadata, errors or UI.

## Rollback

Disable the importer or reset only its cursor rows. Raw and normalized observations remain intact.
