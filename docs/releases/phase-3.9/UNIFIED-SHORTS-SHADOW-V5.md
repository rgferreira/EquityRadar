# Unified Shorts Shadow v5

Status: **preregistered inactive challenger; no live-model or official-accuracy change authorized**.

## Scope

`technology-unified-shorts-v5-shadow` keeps one Shorts Shadow with asset-specific adapters:

- equities use the unchanged FINRA daily short-sale-flow v1 modifier;
- `BTC-USD` uses Binance BTCUSDT perpetual short-account share, taker flow, and open interest.

These inputs are not economically interchangeable. They share a bounded Entry/Exit modifier contract,
but retain their source, state, confidence, freshness, and methodology.

## Preregistered BTC mapping

Only `verified_observed` rows known by the cutoff and completed UTC periods strictly before it are eligible.
The adapter requires 30 observations, uses up to 90 days, and becomes neutral when the latest period is more
than two days old.

1. Crowding combines 60% current short-account level above its rolling median-to-p90 range and 40% positive
   10-day short-account change, each bounded to 0–1.
2. Below-baseline 10-day taker selling confirms squeeze potential; above-baseline selling confirms downside
   pressure. Full strength is reached at a two-percentage-point difference.
3. Ten-day open-interest expansion scales magnitude from 50% at no expansion to 100% at +10%.
4. Net squeeze minus downside pressure is confidence-gated and capped at ±2 Entry points. Exit receives the
   exact opposite modifier.
5. Missing, stale, unverified, same-cutoff-day, or future evidence contributes exactly zero.

The mapping was fixed before prospective outcomes were evaluated. Retrospective overlays remain excluded.

## Evaluation boundary

- Existing v3 snapshots remain immutable and are treated as a retired FINRA-only experiment.
- v5 starts a new prospective evidence identity; evidence from earlier versions cannot silently authorize v5 promotion.
- The existing primary evaluator remains purged benchmark-relative 3M.
- Before BTC promotion, a secondary BTC-relative evaluator at 1/3/5/10 days and 1M must be implemented and
  pass adapter-specific gates. Until then the BTC modifier remains Shadow-only regardless of apparent charts.

## Rollback

Retire v5 and restore `technology-daily-short-flow-v3-shadow` as the candidate. No live prediction, saved
simulation, outcome, or historical snapshot needs to be rewritten.
