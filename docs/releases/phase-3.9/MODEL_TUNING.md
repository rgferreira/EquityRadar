# Phase 3.9 — Model tuning research console

The **Model tuning** page is a read-only comparison of the active model and the inactive coverage-aware shadow model. It does not change model registration, activation, weights, thresholds, visible scores or diagnostics.

## Evidence shown

- immutable shadow snapshot coverage and maturity;
- Entry-score deltas and live-to-shadow signal transitions;
- paired 3M benchmark-relative utility and decision-accuracy differences;
- date-clustered 95% confidence intervals;
- expanding live-versus-shadow utility curves;
- breakdowns by ticker, coverage mode, technical regime and simulation source;
- immutable evidence lineage and explicit missing/unavailable states.

## Review gate

The console labels evidence as **Collecting evidence**, **Inconclusive**, or **Eligible for human review**. Six mandatory binary indicators prepare a promotion decision:

1. at least ten matured independent cutoff dates;
2. at least five matured dates on which the signal changed;
3. a positive lower 95% confidence bound for paired changed-signal utility;
4. non-negative paired decision-accuracy improvement;
5. positive changed-signal utility on at least 60% of independent dates; and
6. evidence spanning at least three tickers, with no ticker contributing more than 35% of matured changed-signal observations.

This gate is deliberately conservative and never promotes a model. Activation remains a separate, explicit and reversible governance decision.

## Clearance notifications

When all six gates transition from red/inconclusive to green, the application persists a single clearance event, shows a modal on load until it is acknowledged, and attempts one email notification. A continuously green state does not generate repeated alerts as new observations arrive. If the gates later fall below the threshold and subsequently clear again, a new event is created.

Email delivery is optional infrastructure configured only through local environment variables. Missing or failed email configuration never blocks the application and never changes model activation.

## Persisted gate universe

The Model tuning page stores a default list of tickers excluded only from promotion-readiness calculations and clearance notifications. SPY, BTC-USD and SPCX are the initial defaults. Users can change and persist this universe without repeatedly applying exploratory filters.

Exclusion never removes or rewrites snapshots, simulations, predictions or outcomes. All-ticker exploration remains available; the gate panel explicitly reports the included and excluded counts. Transient chart filters do not alter the promotion gates.
