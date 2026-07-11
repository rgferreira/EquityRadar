# Market Positioning Source Audit

Audited 2026-07-11 against the configured FMP Basic account, the installed yfinance adapter, and the current 11-symbol watchlist.

## Coverage result

| Signal | MVP source | Live coverage | History | Refresh | Decision use |
|---|---|---:|---|---|---|
| Short float, shares short, prior-month shares, days to cover | Yahoo `Ticker.info` | 9/11 complete; 11/11 partial | No provider history | Daily cache; underlying report is periodic | Short pressure and direction, with moderate confidence |
| Public float | FMP `shares-float`, Yahoo fallback | FMP accessible | Snapshot only | Daily | Denominator / validation |
| Option volume, open interest, IV by strike and expiry | Yahoo `option_chain` | 11/11 have listed expiries | No history unless we begin storing snapshots | During market day, cache | Put/call balance, concentration, IV and squeeze evidence |
| Institutional ownership percentage | Yahoo `Ticker.info` | 11/11 | No reliable series | Daily cache | Context only |
| Top institutional holders | Yahoo `institutional_holders` | Available in sampled equity | Latest filing snapshot | Daily cache; filings lag | Concentration/context, not a live signal |
| Insider transactions | Yahoo `insider_transactions` | Available in sampled equity | Transaction table | Daily cache | Net open-market buying/selling with transaction filtering |
| Analyst recommendations and changes | Yahoo recommendations/upgrades-downgrades | Available in sampled equity | Yes | Daily cache | Revision momentum and confirmation |
| Institutional position changes / put-call filings | FMP institutional summary | Blocked (HTTP 402) | Potentially yes on paid plan | Filing cadence | Excluded from Basic MVP |
| FMP insider statistics/search | FMP | Blocked (HTTP 402) | Potentially yes on paid plan | Near filing time | Yahoo fallback only |
| Fails to deliver | SEC files | Public, separate ingestion required | Yes, twice-monthly files | Twice monthly | Squeeze-risk context only; never treated as proof of naked shorting |
| Daily short-sale volume | FINRA | Public | Yes | Daily | Optional context; explicitly not equivalent to short interest |

## Watchlist observations

All 11 current instruments expose Yahoo ownership fields and listed option expiries. Nine expose all four audited short fields; GOOG and SPCX expose three of four. Expiry counts ranged from 9 to 23. AAPL's sampled chain included volume, open interest and implied volatility for calls and puts.

## Reliability rules

- Never label option volume or open interest as a directional long/short position without qualifications; calls and puts can be bought or written and can hedge another position.
- Never substitute daily short-sale volume for open short interest.
- Short-interest change is periodic rather than real-time and must display its reporting date.
- Institutional holdings are filing data and therefore lag actual positioning.
- Fails to deliver are not synonymous with naked short selling.
- Yahoo is an unofficial operational source. Persist raw inputs, provider, reporting date and fetched-at timestamp, and degrade confidence when dates or fields are missing.
- Historical option sentiment becomes trustworthy only after this app starts accumulating consistent daily snapshots.

## Recommended MVP boundary

Implement a provider-neutral positioning snapshot using Yahoo for short-interest, option-chain, ownership, insider and analyst fields; use FMP Basic only for accessible float validation. Persist daily snapshots so the app builds its own change history. Start with advisory scores—Long positioning, Short pressure, Squeeze potential and Confidence—without changing Entry or Exit-review scores. Defer paid institutional-flow data and any strong claims about options directionality.

Score integration is implemented as **Phase 3.2 — Market factoring-in**. Official FINRA history establishes short-interest direction and reliability; the exact capped modifier remains visible and missing evidence cannot move a score.

## NVDA historical backfill experiment

On 2026-07-12, the official FINRA Consolidated Short Interest API returned and persisted 205 dated NVDA observations from 2017-12-29 through 2026-06-30. Each record contains reported shares short, the previous reported position, percentage change, average daily volume, days to cover, and any revision flag. Records are explicitly marked `historical_short_interest`; they do not invent historical options, ownership, insider, or analyst values and do not replace the current daily positioning cache.
