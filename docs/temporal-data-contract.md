# Point-in-time temporal data contract

Phase 3.8 PR-002 separates economic dates from provable availability. Historical reconstruction may use non-price evidence only when `known_at_status` is verified and `known_at` is no later than the simulation cutoff.

## Fields

- `period_end`: economic/reference period; never proves publication.
- `published_at`: provider-supplied public release time, only when explicitly verified.
- `known_at`: earliest timestamp the application can safely prove for historical use.
- `fetched_at`: retrieval/cache timestamp; operational freshness only.
- `known_at_status`: `verified_published`, `verified_observed`, or absent/`unverified_legacy`.

For a newly captured response without a verified publication timestamp, the application may set `known_at` to the contemporaneous fetch time with `verified_observed`: this proves only that the system observed the data then and never backdates it to `period_end`. Existing legacy rows are not promoted from `reporting_date` or `fetched_at`.

## Source rules

| Source | Period/reference field | Safe `known_at` rule | Historical behavior |
|---|---|---|---|
| FMP fundamentals | Statement/growth `date` → `period_end` | Verified provider publication time when available; otherwise first new application observation | Legacy cache rows excluded; new rows usable only at/after observation |
| Yahoo fundamentals | `mostRecentQuarter`/fiscal end → `period_end` | First new application observation | Never backdated to fiscal period end |
| Yahoo industry, peers and analysts | No common reliable publication timestamp | First new application observation for the normalized snapshot | Current display preserved; historical use requires captured verified metadata |
| Yahoo/FMP positioning | Short-interest reference date → `period_end`; other components are snapshot values | First new application observation | Mixed snapshot becomes available only from capture time |
| FINRA consolidated short interest | Settlement date → `period_end` | Verified dissemination time if added later; currently first API observation | Historical backfill is not treated as known on settlement date |
| Daily prices | Trading-session date | Bar is available at session close; date-only Time Machine cutoffs are end-of-day | `history_as_of` excludes all later bars |

## Conservative failure behavior

Missing, malformed, or unverified `known_at` means unavailable for historical scoring—not neutral/bullish/bearish evidence. Live price and current research displays continue independently. The additive migration leaves all legacy values untouched and nullable.
