# PHASE3.8-PR-004 — Relative outcomes

## Objective

Introduce a versioned decision-evaluation label that separates security selection from general market movement and reflects executable timing.

## Finding status

F-06 still applies: current 1M/3M/6M outcomes are absolute close-to-close returns with no benchmark, execution delay, costs, or downside measure.

## Scope

- Define and freeze a new label version with next-tradable-session entry, benchmark-relative 1M/3M/6M returns, explicit costs/slippage convention, and at least one downside-risk outcome.
- Add a minimal, deterministic benchmark mapping policy (broad market first; sector benchmark only when verified).
- Persist benchmark identity, prices, timing convention, costs, and label version with each outcome.
- Keep legacy absolute outcomes readable as a separately named legacy label.

## Non-goals

- No factor/threshold tuning, portfolio performance rewrite, live execution, or claim that relative return alone proves a good decision.
- No evaluator/promotion logic from PR-005.

## Probable files

`src/backtesting.py`, a focused outcome-label module, `src/data/database.py`, historical price adapter/cache code, migrations, label tests, documentation.

## Data and migration

Add append-only outcome-label tables keyed by prediction ID and label version. Never overwrite the legacy outcome columns. Benchmark mapping and cost assumptions must be versioned.

## Tests

- Synthetic rising/falling market cases distinguish absolute from relative performance.
- Weekend/holiday cutoffs execute on the next tradable session without future leakage.
- Costs are applied once and missing benchmark data yields unavailable—not directional—evidence.
- Horizon and downside calculations have boundary tests.

## Acceptance criteria

- Every new evaluable prediction has an explicit label version and benchmark/timing provenance.
- Legacy and new labels cannot be silently mixed.
- Outcome computation is deterministic from frozen prices and assumptions.

## Risks and rollback

Risk: benchmark mapping can introduce a new hidden modelling choice. Keep mappings minimal, explicit, and versioned. Roll back consumers to legacy labels; preserve append-only outcomes.
