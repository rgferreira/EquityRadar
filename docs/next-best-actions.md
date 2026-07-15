# Next best actions

Last reviewed: 2026-07-15. Current internal phase: **3.9 - coverage-aware model promoted**.

This is the live planning document. Completed work belongs in [`implemented-features.md`](implemented-features.md); design and source investigations remain in their dedicated documents. Phase 4 has **not started**.

## Phase 3.8 - completed implementation sequence

The forensic audit supersedes the former improvised implementation queue. PR-001 through PR-005 are complete on the Phase 3.8 branch. Continue accumulating immutable, verified-known-at predictions and versioned relative outcomes; run the offline evaluator only as a diagnostic and accept `insufficient_evidence` when independent dates are scarce. The ordered record remains in [`implementation/phase-3.8/ROADMAP-3.8.md`](implementation/phase-3.8/ROADMAP-3.8.md). Do not treat the evidence pack or evaluator output as evidence of alpha.

The first coverage-aware challenger later accumulated 378 matured paired observations and cleared all six readiness gates. It was explicitly promoted as `coverage-aware-renormalized-v3-live`; the former live version remains the rollback anchor. Next: monitor prospective post-promotion accuracy, utility and drift against the frozen promotion baseline. Define another shadow only for a distinct preregistered hypothesis.

## Phase 3.9 operational acceptance — completed

The post-promotion monitor, all-page AppTest and real desktop/phone Chromium regression suites,
full provider-state console, server-lifetime scheduler, verified daily backups and isolated restore drills,
options-continuity gate, material research alerts and non-executing Scenario lab
are implemented. See [`releases/phase-3.9/ACCEPTANCE-2026-07-14.md`](releases/phase-3.9/ACCEPTANCE-2026-07-14.md).

The next model-research action is to continue collecting genuinely prospective evidence. The
[`options-positioning-v1`](experiments/options-positioning-v1.md) hypothesis is preregistered, but no new
shadow model exists and no score change is authorized.

## Phase 3.9 next step — saved, not implemented

1. **FINRA daily short-volume driver.** Add the same-day consolidated FINRA short-sale-volume files as a
   separate daily flow-pressure input. Preserve twice-monthly consolidated short interest as the official
   position anchor: daily short-sale volume is trading flow, not outstanding short positions. Persist raw
   observations with trade date and acquisition timestamp, expose source freshness and coverage, and build
   a transparent rolling pressure/z-score feature in shadow mode only. Require a preregistered evaluation
   window and incremental out-of-sample evidence before authorizing any live score modifier. See
   [`releases/phase-3.9/FINRA-DAILY-SHORT-VOLUME-NEXT.md`](releases/phase-3.9/FINRA-DAILY-SHORT-VOLUME-NEXT.md).

## Phase 4 - saved, not started

The original Phase 4 list has largely been delivered early through Portfolio and Phase 3 work. The remaining product-level candidates are reordered below; implementation requires an explicit decision to enter Phase 4.

1. **Dividend intelligence.** Build projected income, payment calendar, trailing/forward yield and dividend-growth history on top of the already implemented dividend/cash ledger.
2. **Portfolio policy alerts.** Research alerts and scenario analysis are implemented; configurable concentration/target-weight policies and snooze history remain future work.
3. **Decision review workflow.** Connect Journal theses and conviction to subsequent score changes, simulations and portfolio actions, producing an auditable pre/post decision review.
4. **Cross-ticker opportunity ranking.** Add confidence-aware capital-allocation comparisons that respect ownership, target weights, evidence coverage and model uncertainty rather than ranking Entry scores alone.
5. **Historical model comparison.** Extend the current promotion archive to future approved model versions and rolling prospective cohorts.
6. **Recovery drill hardening.** Verified backups are implemented; a guarded restore command and clean-machine drill remain future work.
7. **Multi-user / remote deployment assessment.** Evaluate authentication, secrets, database concurrency and privacy only if the app moves beyond its current local single-user boundary.
8. **Broker connectivity boundary review.** Keep execution out of scope by default. Reassess read-only account import separately from order placement; the Revolut Exchange FIX API remains unsuitable for the equity product (see [`revolut-fix-assessment.md`](revolut-fix-assessment.md)).

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
| Scheduled refresh and provider health | Server-lifetime scheduling and Operations health view implemented in Phase 3.9 |
| Automated end-to-end UI tests | All-page AppTest plus repeatable 16-route/viewport Chromium acceptance implemented |

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
- **3.8 - Scientific hardening:** forensic-audit intake, learning quarantine, point-in-time semantics, model registry/snapshots, relative outcomes and purged evaluation.
- **3.9 - Coverage-aware promotion and operational acceptance:** explicit reversible promotion, prospective monitor, provider/recovery operations, meaningful alerts, options coverage gate and scenario laboratory.

See [`implemented-features.md`](implemented-features.md) for the detailed implementation record and [`internal-changelog.md`](internal-changelog.md) for the compact release narrative.
