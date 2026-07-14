# Versioned benchmark-relative outcome labels

Phase 3.8 PR-004 adds `benchmark-relative-v1` as a separate, append-only evaluation label. It does not rewrite or reinterpret legacy absolute outcomes.

## Frozen policy

- Equities use `SPY`; `SPY` itself uses `^GSPC`. Assets without a verified broad benchmark, including crypto in v1, are explicitly unavailable.
- Entry is the closing price on the first common tradable session strictly after the decision cutoff.
- 1M, 3M, and 6M exits are 21, 63, and 126 common trading sessions after entry.
- Relative return is security return minus benchmark return, with one explicit 10 bps round-trip cost subtraction per horizon.
- Six-month maximum peak-to-trough drawdown is stored as a separate downside observation.
- Missing benchmark/history produces unavailable evidence, never a directional value.

The append-only `outcome_label_observations` table stores label version, benchmark and mapping version, execution date and prices, cost/timing conventions, horizon end dates and returns, downside, and a content hash. A prediction/label-version pair is immutable.

## Rollback

Consumers can ignore the additive table and continue reading named legacy absolute outcomes. Rows should remain preserved for audit.
