# Phase 3.8 — Scientific hardening roadmap

Phase 3.8 converts the forensic audit into five small, reversible implementation slices. It does not add trading execution, redesign the UI, or claim predictive skill.

## Ordered delivery

1. **PR-001 — Quarantine learning — complete.** Unvalidated backtested learning no longer changes live Entry/Exit scores and remains clearly labelled diagnostic evidence.
2. **PR-002 — Known-at semantics — complete.** Source-specific point-in-time rules now exclude unverified legacy timestamps without rewriting them.
3. **PR-003 — Model registry and immutable snapshots — complete.** Model selection is explicit and new predictions are immutable and replayable.
4. **PR-004 — Relative outcomes — next.** Version evaluation labels around benchmark-relative, delayed, cost-aware outcomes.
5. **PR-005 — Purged evaluator.** Evaluate frozen predictions with rolling-origin splits, purge/embargo, baselines, and uncertainty.

Dependency chain: PR-001 → PR-002 → PR-003 → PR-004 → PR-005. PR-001 is deliberately first because it reduces current scientific risk without waiting for the full evaluation platform.

## Phase gates

- One focused commit/PR per slice; push after its focused tests and full suite pass.
- Additive migrations only; legacy research records remain read-only.
- No score-weight or threshold changes unless a later explicitly approved task defines the evaluation method.
- No promotion of a candidate model without immutable predictions, verified temporal semantics, frozen labels, and a purged out-of-sample comparison against baselines.
- Each slice reports changed files, tests, migration behavior, residual risks, and rollback.

## Intake status

- Audit and evidence imported: complete.
- Findings reconciled with current HEAD: complete; see `../AUDIT_TRIAGE.md`.
- PR-sized specifications: complete.
- PR-001 production implementation: complete; no migration and no historical-row rewrite.
- PR-002 production implementation: complete; additive nullable migration, conservative new-snapshot capture, and no legacy-row promotion.
- PR-003 production implementation: complete; additive registry/snapshot migration and no conversion of legacy rows.
- PR-004 and PR-005 production implementation: not started.
