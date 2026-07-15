# Internal changelog

Current checkpoint: **Phase 3.9 - Coverage-aware live model**
Latest release: `coverage-aware-renormalized-v4-finra-freshness-live` evidence-integrity correction, 2026-07-15

## Checkpoints and informal phases

| Phase / version | Outcome |
|---|---|
| 1.0 - Before Industry Feature | MVP watchlist, Dashboard, Company, Journal, yfinance prices, FMP fundamentals and transparent absolute scores |
| 2.0 - Before Trading | Portfolio lots, cost basis, P&L, FX, cash/dividends, benchmarks, allocation, targets and backups |
| 3.9 - Operational acceptance | Coverage-aware live promotion, prospective monitoring, operations/recovery console, meaningful alerts, options evidence gate and scenario laboratory |
| 3 / 3.1 - Industry + UX foundations | Peer cohorts, analyst context, self-completing research and responsive Decision Dashboard / Company / Portfolio redesign |
| 3.2 - Market factoring-in | Official FINRA and market-positioning history became small reliability-gated Entry and Exit-review modifiers |
| 3.3 - UI polishing | Mobile-first tables, clearer score maps, navigation, FINRA chart pulse and compact decision views |
| 3.4 - Backtested learning | Time Machine, point-in-time reconstruction, persisted simulations, forward outcomes and per-ticker lessons |
| 3.5 - Position-aware decisions | Owned positions receive Add/Hold/Monitor/Trim/Exit actions; unowned securities remain initiation decisions |
| 3.6 - FINRA refinement | Watchlist-wide historical backfill, cutoff-safe score rebuilds and explicit coverage discipline |
| 3.7 - Decision-aware learning | Learning-value gate, smart cutoffs, confirmed episodes, accuracy views, simulation markers, model-v4 orthogonality and extended-hours awareness |
| 3.8 - Scientific hardening | Learning quarantine, known-at semantics, immutable model registry, benchmark-relative outcomes and purged evaluation |
| 3.9 - Model tuning and promotion | Coverage-aware shadow evidence, six readiness gates, persisted gate universe, explicit promotion and reversible historical materialization |

## Scoring-model lineage

1. **MVP absolute model:** Entry = 50% Technical + 30% Valuation + 20% Risk. Exit review = 60% technical deterioration + 40% risk deterioration.
2. **Industry-calibrated Entry:** 25% Business quality + 30% Peer value + 20% Technical timing + 15% Risk resilience + 10% Analyst sentiment.
3. **Positioning modifiers:** official FINRA and market evidence are reliability-gated and capped at +/-5 Entry points and +/-7 Exit-review points; missing evidence is neutral.
4. **Backtested learning v1-v3:** original decisions are evaluated against comparable monthly 1M/3M/6M outcomes weighted 50%/30%/20%; provisional evidence remains visible but cannot train scores.
5. **Orthogonal model - `backtested-learning-v4-orthogonal`:** duplicate drawdown evidence was removed from Technical, analyst actions were removed from Positioning, Technical weights were rescaled, and all saved cutoffs were rebuilt.
6. **Phase 3.8 temporal variant - `backtested-learning-v4-orthogonal-known-at-v1`:** weights remain unchanged, but newly generated historical scores admit non-price evidence only with verified `known_at`; legacy v4 research remains preserved and quarantined.
7. **Phase 3.8 registered policy:** the temporal variant has a deterministic configuration hash and predictions freeze input references and outputs.
8. **Phase 3.9 champion - `coverage-aware-renormalized-v3-live`:** verified valuation preserves 50/30/20 Technical/Valuation/Risk; unavailable valuation contributes no placeholder and Technical/Risk renormalize to 5/7 and 2/7. Industry-calibrated and Exit-review policies remain unchanged.
9. **FINRA freshness correction - `coverage-aware-renormalized-v4-finra-freshness-live`:** short-interest age is measured from the official report date, never download time. Reports older than 28 days and missing/unverified evidence contribute no short-interest directionality. Saved simulations are restated append-only; v3 remains the immediate rollback anchor.
9. **Confirmed-episode rule:** only informative independent episodes with matured 3M outcomes contribute to visible accuracy; backtested-learning score modifiers remain quarantined.

## Operating principles

- Research only; no order execution.
- Missing or invalid data never becomes false conviction.
- Every score contribution is bounded, visible and reproducible.
- Historical simulations cannot use data published after their cutoff.
- Extended-hours quotes are advisory; official closes remain the scoring and backtesting input.
- Older model runs remain stored for audit/rollback while normal views select the newest model per ticker/cutoff.

The designed one-page PDF is available at [`../output/pdf/equity-radar-internal-changelog.pdf`](../output/pdf/equity-radar-internal-changelog.pdf).
