# Phase 3.92 PR-004 — WhaleSeeker surfaces

**Implementation status:** complete; automated verification passed on 2026-08-11.

## Scope

- Insert a WhaleSeeker disclosure panel between Portfolio actions and Watchlist opportunities.
- Show only locally persisted public disclosures, delay and first-observed timestamps.
- Add a dedicated WhaleSeeker page with Recent disclosures, Politicians and Data status views.
- Provide an explicit, rate-conscious historical-import control.
- Link WhaleSeeker in the application navigation.

## Scientific and product controls

- Whale evidence has zero applied Entry/Exit weight.
- Transaction date is never presented as alert availability.
- Politician profiles describe sample size and disclosure delay; they do not show invented returns.
- Empty, partial and provider-failure states explain their effect and recovery path.
- No brokerage execution or copy-trading action is offered.

## Acceptance criteria

1. Dashboard order is Portfolio → WhaleSeeker → Pilot → Watchlist.
2. Dedicated page renders safely with an empty synthetic database.
3. Relevant-ticker feed and politician summaries are deterministic.
4. Import button performs bounded work and surfaces a secret-safe result.
5. Existing pages, navigation and model decisions remain unchanged.

## Rollback

Set `WHALESEEKER_ENABLED=false` to hide the Dashboard panel, page content and import control while
retaining lineage. Remove the page from `app.py` for a presentation-only rollback.
