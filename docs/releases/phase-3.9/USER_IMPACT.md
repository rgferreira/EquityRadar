# Phase 3.9 — User impact and simulation guidance

Date: 2026-07-14
Branch: `phase/3.9-coverage-aware-model`

This note preserves the product-level explanation given at the Phase 3.9 live-model boundary. Phase 3.9 currently introduces an **inactive, coverage-aware shadow model** for observation and validation; it does not activate or promote that model into the live decision policy.

## How has the visible decision-accuracy level changed, and why?

Visible decision accuracy can change only when additional legacy simulation outcomes become available or existing outcomes mature. The Phase 3.8 purged evaluator and the Phase 3.9 shadow comparison do not feed their research results into the accuracy percentage shown in the UI. Their purpose is to evaluate the model independently without contaminating the live accuracy history or presenting unvalidated evidence as proven skill.

## How have visible Entry and Exit scores changed, and why?

The material live-score change occurred in Phase 3.8 PR-001, when backtested-learning modifiers were quarantined because their evidence was not sufficiently independent or reliable. That removed those modifiers from live Entry and Exit decisions. The subsequent Phase 3.8 hardening work and the current Phase 3.9 shadow foundation have not changed the active model's weights, thresholds, visible scores, or diagnostics. The coverage-aware challenger is being calculated and stored alongside the current model, but remains inactive.

## How are scores expected to evolve?

Active scores will continue to move with new market prices, fundamentals, industry calibration, technical conditions, risk, analyst evidence, and market-positioning inputs under the current live policy. Shadow scores will accumulate in parallel and will show how a coverage-aware policy would have behaved. They should affect visible decisions only after a preregistered evaluation demonstrates stable improvement across independent dates, relative outcomes, baselines, and downside checks, followed by an explicit promotion decision.

## How should simulations work, and are they still useful?

Suggested and custom simulations remain useful, but they are optional research actions rather than a requirement for operating the dashboard. A confirmed simulation should reconstruct only information known at its cutoff date, persist immutable model inputs and predictions, and later attach benchmark-relative outcomes when those horizons mature. Suggested dates help target informative regimes; custom dates support specific hypotheses. Users should avoid repeatedly choosing favorable or highly correlated dates, because that can inflate apparent accuracy. Under Phase 3.9, simulations also create shadow-model comparisons without changing the live decision shown to the user.

## Practical interpretation

- The UI continues to show the current active model.
- Phase 3.9 shadow outputs are research evidence, not live recommendations.
- Simulations enrich the evidence base but do not automatically validate or promote a model.
- Any live-model activation remains a separate, explicit, reversible decision.
