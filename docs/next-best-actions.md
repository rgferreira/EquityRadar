# Next best actions

Last reviewed: 2026-07-20. Current internal status: **Phase 3.9 engineering closed; daily-short-flow shadow monitoring continues**.

This is the live planning document. Completed work belongs in [`implemented-features.md`](implemented-features.md); design and source investigations remain in their dedicated documents. Phase 4 has **not started**.

## Phase 3.8 - completed implementation sequence

The forensic audit supersedes the former improvised implementation queue. PR-001 through PR-005 are complete on the Phase 3.8 branch. Continue accumulating immutable, verified-known-at predictions and versioned relative outcomes; run the offline evaluator only as a diagnostic and accept `insufficient_evidence` when independent dates are scarce. The ordered record remains in [`implementation/phase-3.8/ROADMAP-3.8.md`](implementation/phase-3.8/ROADMAP-3.8.md). Do not treat the evidence pack or evaluator output as evidence of alpha.

The first coverage-aware challenger later accumulated 378 matured paired observations and cleared all six readiness gates. It was explicitly promoted as `coverage-aware-renormalized-v3-live`; the former live version remains the rollback anchor. Next: monitor prospective post-promotion accuracy, utility and drift against the frozen promotion baseline. Define another shadow only for a distinct preregistered hypothesis.

## Phase 3.9 engineering release — completed

The post-promotion monitor, all-page AppTest and real desktop/phone Chromium regression suites,
full provider-state console, server-lifetime scheduler, verified daily backups and isolated restore drills,
options-continuity gate, material research alerts and non-executing Scenario lab
are implemented. The reconciled release boundary and latest acceptance evidence are recorded in
[`releases/phase-3.9/CLOSURE-2026-07-20.md`](releases/phase-3.9/CLOSURE-2026-07-20.md); the original
[`2026-07-14 acceptance`](releases/phase-3.9/ACCEPTANCE-2026-07-14.md) remains as a historical snapshot.

The next model-research action is to continue collecting genuinely prospective evidence. The
[`options-positioning-v1`](experiments/options-positioning-v1.md) hypothesis is preregistered, but no new
shadow model exists and no score change is authorized.

## Phase 3.9 post-release monitoring — implementation complete; outcomes maturing

1. **FINRA daily short-volume driver.** The consolidated FINRA short-sale-volume files now populate a
   separate daily flow-pressure input. Preserve twice-monthly consolidated short interest as the official
   position anchor: daily short-sale volume is trading flow, not outstanding short positions. Raw observations,
   point-in-time provenance, provider health, daily share and a 10-session visual baseline are implemented. The
   baseline slope is now a bounded component of `technology-daily-short-flow-v3-shadow`; prospective, incremental
   out-of-sample evidence remains required before authorizing any live score modifier. At closure the active
   shadow has 19 changed-diagnostic observations across six dates awaiting 3M outcomes; the full current cohort
   should be reviewed around 2026-10-20. This waiting period is evidence maturation, not unfinished engineering. See
   [`releases/phase-3.9/FINRA-DAILY-SHORT-VOLUME-NEXT.md`](releases/phase-3.9/FINRA-DAILY-SHORT-VOLUME-NEXT.md).

## Phase 3.91 — Credit Stress Feature (queued; not started)

Do **not** start this phase while `technology-daily-short-flow-v3-shadow` is still accumulating
prospective evidence. Phase 3.91 begins only after the current shadow experiment reaches a deliberate
evaluation boundary, so CDS evidence is not mixed into its hypothesis or historical comparison.

The proposed Phase 3.91 challenger will test whether credit-market stress adds information that is not
already captured by equity volatility, drawdown, technical momentum, options and short positioning:

1. Add a daily broad credit-regime layer using transparent investment-grade and high-yield spread data.
2. Audit public SEC security-based-swap transaction data for point-in-time, issuer-level CDS usability;
   compare its normalization and coverage burden with a licensed end-of-day single-name CDS provider.
3. Store source, issuer/reference entity, tenor, currency, seniority, spread, liquidity, `as_of` and verified
   `known_at`; missing or illiquid evidence must remain neutral.
4. Preregister a bounded, asymmetric **Credit stress modifier** in a new shadow model: widening stress may
   reduce Entry and increase Exit-review urgency; narrowing stress may become supportive only with confirming
   technical evidence. Market-only evidence must have a smaller cap than liquid issuer-specific evidence.
5. Run the score-overlap audit against volatility, drawdown and positioning, then evaluate incremental
   benchmark-relative accuracy and downside detection through the existing purged prospective gates.
6. Keep the live model unchanged unless the Phase 3.91 shadow clears the established promotion criteria and
   receives an explicit manual promotion decision.

Working name: **Credit Stress Feature**. Planned internal phase: **3.91**.

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
