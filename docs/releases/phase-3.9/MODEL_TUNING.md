# Phase 3.9 — Model tuning decision center

The **Model tuning** page is the read-only governance center for comparing the current live model with one active shadow hypothesis. It never changes model registration, weights, thresholds, visible scores or diagnostics, and it never promotes a model automatically.

## Current model lineage

- Current live: `coverage-aware-renormalized-v4-finra-freshness-live`.
- Immediate rollback: `coverage-aware-renormalized-v3-live`.
- Active shadow: `technology-daily-short-flow-v3-shadow`.
- Original promotion archive: coverage-aware v1 versus `backtested-learning-v4-orthogonal-known-at-v1`.

The v4 live model was activated as a documented FINRA evidence-policy correction. It was not a second 6/6 challenger promotion, so the original promotion archive remains immutable and visually separate from the active shadow experiment.

## What the page shows

- clear live, active-shadow and rollback identities;
- genuinely prospective live monitoring after activation;
- immutable snapshot coverage and three-month outcome maturity;
- paired benchmark-relative utility and decision-accuracy deltas;
- expanding date-clustered live and shadow utility curves;
- breakdowns by ticker, coverage mode, technical regime and simulation source;
- six binary promotion-readiness gates, with progress while evidence matures;
- persisted gate-universe exclusions without deleting any research rows;
- model lineage plus archived and retired experiments.

Only dates—not ticker rows—are treated as independent observations. Promotion-relevant evidence must both change a diagnostic and later receive the same point-in-time-valid three-month outcome for live and shadow.

## Active-shadow checkpoint at engineering closure

As of 2026-07-20, after applying the persisted promotion universe exclusions:

- 178 comparable rows span 21 included tickers and 33 decision dates;
- 46 paired observations across 23 dates have mature outcomes;
- those mature rows produce identical live and shadow diagnostics, so the utility curves overlap exactly;
- 19 changed-diagnostic observations across six dates are captured but not yet mature;
- readiness is **Collecting evidence**, with 1/6 gates green;
- the shared evidence-pipeline indicator is 52%: date capture is complete, while three-month aging has only begun.

The progress indicator is deliberately not a refresh counter. Repeated Dashboard refreshes preserve immutable evidence but cannot make a three-month outcome mature faster. The first current changed-decision cohort can begin maturing around 2026-10-15; the present batch should be reviewable around 2026-10-20.

## Review gates

The page labels the experiment **Collecting evidence**, **Inconclusive**, or **Eligible for human review**. Six mandatory indicators prepare—not execute—a promotion decision:

1. at least ten matured independent cutoff dates;
2. at least five matured dates on which the diagnostic changed;
3. a positive lower 95% confidence bound for paired changed-signal utility;
4. non-negative paired decision-accuracy improvement;
5. positive changed-signal utility on at least 60% of independent dates; and
6. evidence spanning at least three tickers, with no ticker contributing more than 35% of matured changed-signal observations.

When a new shadow begins, performance-dependent gates correctly return to grey/awaiting evidence. Historical 6/6 clearance belongs to its archived experiment and must never appear as current shadow readiness.

## Notifications and gate universe

When all six active gates transition to green, the application persists one clearance event, shows a modal until acknowledged and attempts an optional locally configured email. Missing email configuration never blocks the app or changes model activation.

SPY, BTC-USD and SPCX are the initial persisted exclusions from promotion-readiness calculations. Exclusion does not remove or rewrite snapshots, simulations, predictions or outcomes; it only controls which rows contribute to the six active gates. Exploratory filters do not alter that persisted universe.

## Scientific boundary

Readiness is not evidence of durable alpha and is not permission to alter the live model. Any promotion requires an explicit human decision, a new immutable model version, recalculated predictions under that version and a retained rollback anchor. Phase 3.91 must remain separate until the daily-short-flow shadow reaches its deliberate evaluation boundary.
