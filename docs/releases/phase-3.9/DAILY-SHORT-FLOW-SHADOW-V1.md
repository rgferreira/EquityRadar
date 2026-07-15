# Daily short-flow slope shadow component — 2026-07-15

## Decision boundary

`technology-daily-short-flow-v3-shadow` is an inactive challenger. The live model remains
`coverage-aware-renormalized-v4-finra-freshness-live`; live Entry/Exit scores and diagnostics are unchanged.
Prior shadow snapshots remain immutable and are archived under their original model versions.

## Preregistered hypothesis

A persistent rise in the slope of the 10-session FINRA daily short-volume-share average may provide entry
caution and exit-deterioration evidence; a persistent decline may indicate easing pressure. Daily short volume
is transaction flow, not outstanding short interest, covering volume, or proof of bearish positioning.

## Frozen transformation

- Metric: ordinary-least-squares slope of the latest ten values of the 10-session daily short-volume-share mean.
- Eligibility: at least 20 observations, `verified_observed` known-at evidence, and latest trade date no more than
  seven calendar days old.
- Noise control: slopes inside +/-0.05 percentage points per session have no directional effect.
- Full strength: +/-0.25 percentage points per session.
- Confidence: observation coverage, freshness and directional persistence.
- Caps: +/-2 shadow Entry points and the opposite +/-2 shadow Exit-review points.
- Missing, stale, after-cutoff or unverified evidence: exactly zero contribution.

## Evaluation

The new version starts with no inherited green gates. Primary evaluation remains prospective, purged,
benchmark-relative 3M utility and accuracy using only snapshots created under this exact configuration.
Backfilled daily files retain their observed `known_at`; they are not treated as data available at historical
cutoffs. Promotion requires matured evidence, cleared gates and an explicit human decision.

## Rollback

Deactivate/archive `technology-daily-short-flow-v3-shadow` and restore the previous inactive challenger
registration. No live-model rollback or legacy-row rewrite is required.
