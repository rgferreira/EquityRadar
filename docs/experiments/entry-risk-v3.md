# Entry risk v3 — frozen development contract

Registered 2026-09-26 before evaluating C. Authorized scope: loss attribution,
risk sizing and score ordering, following the 24 September economic diagnosis.
Historical data already examined remain development diagnostics. No production
weights, labels, exits or v2 rules change; no automatic promotion.

## Fixed hypothesis and controls

C uses exactly the current-policy Buy candidate names. Compute sample standard
deviation of 60 completed daily log returns, annualized by sqrt(252), on 61 common
SPY sessions available at the decision cutoff. Normalize inverse volatilities,
then cap each initial allocation at 20%. Do not redistribute clipped allocations;
unused capital stays in zero-interest cash. Zero/nonfinite volatility, missing
sessions or stale prices make C unavailable, never remove a losing name silently.

The one prespecified sector extension, C-sector, proportionally scales sectors
above 40%, without redistribution. It is available only when every selected name
has an originally recorded sector ETF. Historical missing sectors are not filled
from current profiles. C remains separately visible when C-sector is unavailable.

Controls: current equal-weight buys, SPY, equal-weight buys scaled to C's exposure,
and SPY scaled to C's exposure. Evaluate C-sector on its own identical-date subset
with those same controls scaled to its exposure. This separates cash effects from
relative sizing. No covariance optimizer, target volatility, parameter sweep or
post-hoc exclusion of names. Thresholds are experimental design choices, not
estimated optimal allocations.

## Measurement

Reuse the v2 whole-universe complete paths, next-session close entry, fixed-share
holding, 21/63-session horizons, nonoverlapping windows, three purged prior dates,
five calendar days of embargo, 10/30/50 bps fees and cash treatment. C/control
curves use identical eligible dates within each comparison set. Report excess
against SPY, current policy and exposure-matched current policy, drawdown,
exposure and exploratory paired block intervals. Missing risk cohorts remain
explicit. No live promotion can be authorized by these reports.

Diagnostic loss statistics cover recorded current-policy buys: net unit return,
benchmark excess, mean wins/losses, payoff ratio and expectancy, net daily-close
MAE/MFE (including hypothetical exit fees), giveback from the best close, gross
loss contribution by name, and worst entries. These are descriptions; an ex-post
maximum is not an attainable exit rule. Name loss contributions are sums of
within-block percentage-point contributions, not compounded portfolio returns.

Score ordering uses all frozen input names on admitted v2 dates, fixed bands
[0,20), [20,40), [40,60), [60,80), [80,100], and both all-input and buy-only slices.
Within each band, first average within date, then across dates. Show observations,
dates, excess, hit rate, MAE and exploratory date-block intervals. Missing or
out-of-range scores are counted; scores are not probabilities. No calibration
mapping or thresholds are fitted to this sample. Versions remain visible.

Diagnostic clarification after the first historical read on 26 September: bands
can have different date coverage. Add adjacent-band differences on shared dates
only, and within-date rank correlation (at least five names and nonconstant ranks),
averaged equally over dates. These are exploratory checks, not a newly discovered
trading rule or an independent confirmation of the first historical read.

## Prospective lineage and implementation

V3 starts its own clock. Only a v2 parent captured on the current UTC day can
receive a new v3 snapshot, at the real observation time. Store parent, contract,
61-session price inputs, volatility and weights; replay before insert. The first
daily snapshot and first mature parent price path remain immutable. Earlier v2
captures cannot become prospective C observations retrospectively.

Files: add `src/entry_risk.py`, `scripts/run_entry_risk.py`, focused synthetic tests;
extend `src/research_pipeline.py` and `pages/9_Research_Lab.py`; reconcile planning
docs and publish aggregate evidence. Two additive research tables only. Page
rendering reads stored reports; provider access stays in existing background work.

Risks: few independent periods, watchlist selection, adjusted-price revisions,
missing historical sectors, and reduced exposure creating apparently better risk.
Success for this implementation means correct paired diagnostics and autonomous
capture, not a favorable strategy result. Independent prospective results and a
separate explicit promotion decision remain necessary.

Rollback: checkpoint `2dbb74c`, followed by a separate implementation commit;
revert that implementation and preserve additive tables. Private verified SQLite
backup: `~/Library/Application Support/EquityRadar/risk-research-backup-20260926/`.
Never restore an old database over later captures.
