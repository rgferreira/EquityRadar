# Phase 3.9 — User impact and simulation guidance

Date: 2026-07-14
Branch: `phase/3.9-coverage-aware-model`

This note records the Phase 3.9 live-model boundary. The coverage-aware shadow cleared all six readiness gates and was explicitly promoted as `coverage-aware-renormalized-v3-live` on 2026-07-14.

## How has the visible decision-accuracy level changed, and why?

Visible decision accuracy now selects additive simulations materialized under the active promoted version. Prior runs and outcomes were not rewritten. It will continue changing as new outcomes mature and new simulations add independent episodes.

## How have visible Entry and Exit scores changed, and why?

Entry scores now use the promoted coverage-aware policy: verified valuation keeps the 50/30/20 technical/valuation/risk composite, while unavailable valuation contributes nothing and technical/risk weights renormalize to 5/7 and 2/7. Industry-calibrated decisions and Exit-review scoring remain unchanged.

## How are scores expected to evolve?

Active scores continue to move with market prices, verified fundamentals, industry calibration, technical conditions, risk, analyst evidence and positioning. Prospective evidence will show whether the promotion advantage persists. There is no new shadow until a distinct next hypothesis is preregistered.

## How should simulations work, and are they still useful?

Suggested and custom simulations remain useful optional research actions. They now persist predictions under the promoted live version and later attach benchmark-relative outcomes. They no longer create comparisons for the already-promoted v1 shadow.

## Practical interpretation

- The UI now shows the promoted coverage-aware live model.
- Former shadow outputs remain immutable promotion evidence.
- Simulations enrich the evidence base but do not automatically validate or promote a model.
- Any live-model activation remains a separate, explicit, reversible decision.
