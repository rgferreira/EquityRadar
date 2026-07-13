# PHASE3.8-PR-001 — Quarantine learning

## Objective

Prevent unvalidated backtested learning from changing live Entry/Exit scores while preserving it as transparent diagnostic research.

## Finding status

F-07 still applies. `learned_score_adjustments` is currently applied after only three selected observations in both Dashboard and Company views.

## Scope

- Add a single explicit runtime policy for whether learning modifiers may affect operational scores; default it to off.
- Continue calculating and displaying the modifier, sample count, confidence, and historical accuracy as diagnostic evidence.
- Label the modifier as quarantined/not applied wherever it appears.
- Preserve the underlying legacy research rows unchanged.

## Non-goals

- No factor weights, thresholds, labels, outcome formulas, or learning algorithms change.
- No model registry, timestamp repair, or evaluator work from later slices.
- No broad UI redesign.

## Probable files

`src/backtesting.py`, a small policy/config module, `pages/1_Dashboard.py`, `pages/3_Company.py`, focused backtesting/page tests, README/implemented-features documentation.

## Data and migration

No database migration is expected. Do not rewrite historical scores or outcomes.

## Tests

- Operational Entry/Exit scores equal their pre-learning base when quarantine is enabled.
- Diagnostic modifier remains calculated and visible.
- Missing/weak learning evidence remains neutral.
- Full suite, compile, and import checks.

## Acceptance criteria

- Default live scores receive exactly zero learning adjustment.
- UI cannot imply that quarantined evidence changed the score.
- A future explicit policy switch is testable, centralized, and not controlled by incidental UI state.

## Risks and rollback

Risk: users may interpret lower/restated scores as a regression. Mitigate with explicit labels and retained evidence. Rollback is the single policy change plus its presentation text; no data rollback is required.
