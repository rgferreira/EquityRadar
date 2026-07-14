# Pre-registration: coverage-aware challenger v1

Status: **offline research only**. This document freezes the hypothesis and confirmation dates before their outcomes are retrieved. It does not authorize a live-model change.

## Hypothesis

The discovery cohort showed that historical valuation was unavailable and represented as 50/100. Because that placeholder retained a 30% weight, it diluted verified price evidence and changed Entry labels. Missing evidence must not silently become directional evidence.

`coverage-aware-renormalized-v1` therefore:

- preserves the existing 50% technical / 30% valuation / 20% risk composite when valuation is `verified_known_at`;
- when valuation is unavailable or unverified, removes its weight and transparently renormalizes the verified technical/risk weights to 5/7 and 2/7;
- preserves the frozen market-positioning adjustment and existing 55/70 thresholds;
- changes no live score, model registry status, factor definition, or historical prediction.

## Frozen confirmation design

- Benchmark-relative 3M outcome label: `benchmark-relative-v1`.
- Confirmation cutoffs, selected by calendar spacing before outcome retrieval: **2025-02-14, 2025-06-16, 2025-10-16, 2026-02-16**.
- Unit of independence: cutoff date; tickers within a date are clustered.
- Primary statistic: paired challenger-minus-current decision utility, with a date-clustered 95% interval.
- Secondary statistic: paired decision-accuracy difference.
- Minimum evidence: three available independent dates.
- No threshold search, alternate date substitution, ticker removal, or repeated challenger variants after viewing results.

An encouraging point estimate is not sufficient for deployment. Any live-model proposal requires an explicit user decision, review of missing-data semantics in the UI, and evidence that is not wholly derived from this historically selected watchlist.

## Frozen confirmation result — 2026-07-14

The preregistration above was committed as `2778398` before the four confirmation cutoffs were retrieved. Experiment `20534e21…e91e2b` was then run and persisted without modifying the model registry.

- 76 eligible observations across four independent cutoff dates; all used the predeclared valuation-unavailable branch.
- Current-policy utility: **+2.21%** (date-clustered 95% interval **−1.55% to +5.97%**).
- Challenger utility: **+4.49%** (95% interval **−1.18% to +10.15%**).
- Paired utility improvement: **+2.27 percentage points** (95% interval **−0.88 to +5.43**).
- Paired accuracy improvement: **+3.95 percentage points** (95% interval **−4.86 to +12.76**).
- Decisions changed in nine cases: eight Watch→Buy candidate and one Wait→Watch. The eight upgraded candidates produced an average 3M benchmark-relative return of +8.56%.
- Improvement occurred on two of four dates and was zero on the other two; it was not uniformly distributed.

Conclusion: directionally encouraging but **not promotion-grade** because both paired intervals cross zero, the effective sample is four dates, valuation was unavailable in every confirmation row, and the universe is the historically selected watchlist. The live model remains unchanged. Further confirmation must come from prospectively accumulated dates or a separately governed external universe—not substituted historical dates selected after viewing this result.
