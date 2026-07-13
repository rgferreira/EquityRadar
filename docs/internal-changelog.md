# Internal changelog

Current checkpoint: **Phase 3.7 - Decision-aware learning**  
Latest release commit: `337926b` (`feat: add extended-hours market awareness`, 2026-07-14)

## Checkpoints and informal phases

| Phase / version | Outcome |
|---|---|
| 1.0 - Before Industry Feature | MVP watchlist, Dashboard, Company, Journal, yfinance prices, FMP fundamentals and transparent absolute scores |
| 2.0 - Before Trading | Portfolio lots, cost basis, P&L, FX, cash/dividends, benchmarks, allocation, targets and backups |
| 3 / 3.1 - Industry + UX foundations | Peer cohorts, analyst context, self-completing research and responsive Decision Dashboard / Company / Portfolio redesign |
| 3.2 - Market factoring-in | Official FINRA and market-positioning history became small reliability-gated Entry and Exit-review modifiers |
| 3.3 - UI polishing | Mobile-first tables, clearer score maps, navigation, FINRA chart pulse and compact decision views |
| 3.4 - Backtested learning | Time Machine, point-in-time reconstruction, persisted simulations, forward outcomes and per-ticker lessons |
| 3.5 - Position-aware decisions | Owned positions receive Add/Hold/Monitor/Trim/Exit actions; unowned securities remain initiation decisions |
| 3.6 - FINRA refinement | Watchlist-wide historical backfill, cutoff-safe score rebuilds and explicit coverage discipline |
| 3.7 - Decision-aware learning | Learning-value gate, smart cutoffs, confirmed episodes, accuracy views, simulation markers, model-v4 orthogonality and extended-hours awareness |

## Scoring-model lineage

1. **MVP absolute model:** Entry = 50% Technical + 30% Valuation + 20% Risk. Exit review = 60% technical deterioration + 40% risk deterioration.
2. **Industry-calibrated Entry:** 25% Business quality + 30% Peer value + 20% Technical timing + 15% Risk resilience + 10% Analyst sentiment.
3. **Positioning modifiers:** official FINRA and market evidence are reliability-gated and capped at +/-5 Entry points and +/-7 Exit-review points; missing evidence is neutral.
4. **Backtested learning v1-v3:** original decisions are evaluated against comparable monthly 1M/3M/6M outcomes weighted 50%/30%/20%; provisional evidence remains visible but cannot train scores.
5. **Current model - `backtested-learning-v4-orthogonal`:** duplicate drawdown evidence was removed from Technical, analyst actions were removed from Positioning, Technical weights were rescaled, and all saved cutoffs were rebuilt.
6. **Confirmed-episode rule:** only informative independent episodes with matured 3M outcomes train scores; at least three are required; the learning modifier is capped at +/-5 points.

## Operating principles

- Research only; no order execution.
- Missing or invalid data never becomes false conviction.
- Every score contribution is bounded, visible and reproducible.
- Historical simulations cannot use data published after their cutoff.
- Extended-hours quotes are advisory; official closes remain the scoring and backtesting input.
- Older model runs remain stored for audit/rollback while normal views select the newest model per ticker/cutoff.

The designed one-page PDF is available at [`../output/pdf/equity-radar-internal-changelog.pdf`](../output/pdf/equity-radar-internal-changelog.pdf).
