# Next best actions

Last reviewed: 2026-07-14. Current internal phase: **3.8 - Scientific hardening (PR-001 through PR-005 complete)**.

This is the live planning document. Completed work belongs in [`implemented-features.md`](implemented-features.md); design and source investigations remain in their dedicated documents. Phase 4 has **not started**.

## Phase 3.8 - completed implementation sequence

The forensic audit supersedes the former improvised implementation queue. PR-001 through PR-005 are complete on the Phase 3.8 branch. Continue accumulating immutable, verified-known-at predictions and versioned relative outcomes; run the offline evaluator only as a diagnostic and accept `insufficient_evidence` when independent dates are scarce. The ordered record remains in [`implementation/phase-3.8/ROADMAP-3.8.md`](implementation/phase-3.8/ROADMAP-3.8.md). Do not treat the evidence pack or evaluator output as evidence of alpha.

The first pre-registered coverage-aware challenger was directionally positive but did not clear the live-model gate: its paired utility and accuracy intervals cross zero on four independent confirmation dates. Do not substitute more favorable historical dates or change thresholds. The next scientific action is prospective evidence accumulation (or a separately governed external-universe validation) before any live-model proposal.

## Deferred operational work from Phase 3.7

1. **Automated end-to-end UI regression tests - pending.** Cover the critical Dashboard, Portfolio, Company, Journal, Watchlist, deep-link, simulation and mobile-width flows. The Python suite is extensive, but it does not yet replace browser-level regression coverage.
2. **Provider-health diagnostics - pending.** Add a compact operational view for price, fundamentals, peer/analyst, FINRA, positioning and extended-hours providers: last success, stale age, active cooldown and most recent isolated error.
3. **True scheduled refresh - pending design.** Current bounded background jobs are triggered by page loads and watchlist changes. Decide whether a local scheduler should refresh due data while no browser session is active, without turning normal usage into a manual-refresh workflow.
4. **Options-history calibration gate - accumulating evidence.** Continue storing dated option-chain snapshots. Do not add an options-change score until continuity and overlap tests show it contributes independent information.
5. **Phase 3.7 acceptance pass - pending.** Run a final desktop/mobile walkthrough, verify current and historical score consistency, confirm background recovery after restart, and close the phase with a named checkpoint.

## Phase 4 - saved, not started

The original Phase 4 list has largely been delivered early through Portfolio and Phase 3 work. The remaining product-level candidates are reordered below; implementation requires an explicit decision to enter Phase 4.

1. **Dividend intelligence.** Build projected income, payment calendar, trailing/forward yield and dividend-growth history on top of the already implemented dividend/cash ledger.
2. **Portfolio policy and alerts.** Turn existing concentration and target-weight analytics into configurable portfolio rules with visible, non-executing alerts and snooze/acknowledgement history.
3. **Research alerting.** Notify on meaningful diagnostic changes, score-boundary crossings, FINRA reversals, provider recovery and matured backtest lessons; avoid alerts for ordinary price noise.
4. **Scenario and allocation laboratory.** Explore proposed buys/sells, cash additions and target-weight changes before recording a transaction; show concentration, risk and decision impact without execution.
5. **Decision review workflow.** Connect Journal theses and conviction to subsequent score changes, simulations and portfolio actions, producing an auditable pre/post decision review.
6. **Cross-ticker opportunity ranking.** Add confidence-aware capital-allocation comparisons that respect ownership, target weights, evidence coverage and model uncertainty rather than ranking Entry scores alone.
7. **Historical model comparison.** Productize the existing accuracy-audit utilities so approved model versions can be compared across tickers, cohorts and rolling learning curves before promotion.
8. **Data portability and recovery hardening.** Add scheduled local backups, restore verification, schema/version manifests and a documented clean-machine recovery test.
9. **Multi-user / remote deployment assessment.** Evaluate authentication, secrets, database concurrency and privacy only if the app moves beyond its current local single-user boundary.
10. **Broker connectivity boundary review.** Keep execution out of scope by default. Reassess read-only account import separately from order placement; the Revolut Exchange FIX API remains unsuitable for the equity product (see [`revolut-fix-assessment.md`](revolut-fix-assessment.md)).

## Original Phase 4 list - reconciled

| Original item | Current status |
|---|---|
| Purchase dates and cost basis | Implemented before Phase 4 |
| Realized/unrealized gains and returns | Implemented before Phase 4 |
| Buys, sells, dividends, fees and cash | Implemented before Phase 4 |
| Transaction-aware portfolio history | Implemented before Phase 4 |
| Benchmarks and time-weighted returns | Implemented before Phase 4 |
| Sector/country/currency/position concentration | Implemented before Phase 4; configurable policy alerts remain future work |
| Dividend tracking | Ledger implemented; forecasting/calendar/growth remain Phase 4 |
| Target allocations and rebalancing | Implemented before Phase 4 |
| Scheduled refresh and provider health | Page-triggered background refresh implemented; independent scheduling/health view remain pending |
| Automated end-to-end UI tests | Pending as Phase 3.7 closure |

## Completed internal phases

- **1.0 - Before Industry Feature:** MVP watchlist, prices, fundamentals, Company research, Journal and transparent absolute scores.
- **2.0 - Before Trading:** portfolio lots, P&L, cash/dividends, FX, benchmarks, allocation, targets, imports/exports and backups.
- **3 / 3.1 - Industry and UI foundations:** direct-peer calibration, analyst context, self-completing cohorts and responsive page redesign.
- **3.2 - Market factoring-in:** reliability-gated FINRA/positioning modifiers.
- **3.3 - UI polishing:** mobile-first decision tables, score maps, navigation and FINRA visualization.
- **3.4 - Backtested learning:** Time Machine, persisted point-in-time simulations, outcomes and ticker lessons.
- **3.5 - Position-aware decisions:** separate portfolio actions and watchlist opportunities.
- **3.6 - FINRA refinement:** watchlist-wide historical coverage and point-in-time score rebuilds.
- **3.7 - Decision-aware learning (completed product checkpoint; scientifically quarantined in Phase 3.8):** confirmed episodes, intelligent cutoffs, model-v4 orthogonality, diagnostic accuracy, learning curves, simulation markers and extended-hours awareness.
- **3.8 - Scientific hardening (active):** forensic-audit intake, learning quarantine, point-in-time semantics, model registry/snapshots, relative outcomes and purged evaluation.

See [`implemented-features.md`](implemented-features.md) for the detailed implementation record and [`internal-changelog.md`](internal-changelog.md) for the compact release narrative.
