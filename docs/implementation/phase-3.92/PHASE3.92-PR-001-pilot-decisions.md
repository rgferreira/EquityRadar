# Phase 3.92 PR-001 — Pilot Decisions

**Implementation status:** complete; automated verification passed on 2026-08-11.

## Audit finding status

The governance finding still applies: the active shadow has collected many observations, but no
changed-diagnostic observation has a mature three-month outcome yet. Product exposure may advance;
scientific promotion may not be inferred from evidence-pipeline progress.

## Scope

- Add an independent persisted deployment record for the existing active-shadow version.
- Add a runtime availability/kill switch, default enabled, with user exposure default off.
- Show an opt-in Live-versus-Pilot comparison on the current Decision dashboard.
- Reuse the exact registered Technology Potential and daily-short-flow shadow transformation.
- Show evidence maturity as progress, not probability of success.
- Add focused persistence, determinism, isolation and UI-contract tests.

## Out of scope

- No model promotion, registration change, score-weight change or threshold change.
- No rewrite or insertion into the active experiment's immutable shadow snapshots.
- No WhaleSeeker provider or congressional data ingestion; those begin in PR-002.
- No automatic trading, allocation or notification.

## Planned files

- `src/data/database.py`: additive deployment table and CRUD helpers.
- `src/pilot_deployment.py`: runtime policy, exact pilot calculation and read-only maturity summary.
- `pages/1_Dashboard.py`: opt-in toggle and compact comparison table.
- `tests/test_pilot_deployment.py`: focused isolation and persistence coverage.
- `tests/test_pilot_dashboard_contract.py`: source/UI boundary contract.

## Risks and controls

- **Live/Pilot confusion:** both decisions and provisional status remain visible together.
- **Experiment contamination:** pilot calculations do not call shadow persistence functions.
- **Kill-switch drift:** effective exposure requires both persisted opt-in and runtime availability.
- **Provider/evidence failure:** missing evidence yields the preregistered zero modifier and never
  blocks official Dashboard decisions.

## Acceptance criteria

1. Pilot opt-in persists independently of the champion and shadow registries.
2. Enabling Pilot leaves current model registration and shadow row counts unchanged.
3. Pilot output equals the registered active-shadow transformation for identical inputs.
4. Runtime disable overrides a persisted opt-in.
5. Dashboard official scores and actions are unchanged; Pilot appears only as a comparison.
6. Focused tests, full `python -m pytest -q`, compile/import checks and diff review pass.

## Rollback

Set `PILOT_DECISIONS_ENABLED=false`. The additive deployment row can remain; it has no scoring or
model-registry authority.
