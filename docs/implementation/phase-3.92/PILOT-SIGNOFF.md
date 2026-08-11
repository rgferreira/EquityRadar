# Phase 3.92 pilot sign-off

**Release identity:** `3.92.0-pilot.1`

**Signed scope:** Pilot Decisions comparison and WhaleSeeker public-disclosure research.

**Scientific status:** research pilot; no champion promotion and no validated investment advice.

## Release boundary

- The live champion remains `coverage-aware-renormalized-v4-finra-freshness-live`.
- Pilot Decisions remains comparison-only and independently reversible.
- WhaleSeeker evidence retains 0% applied Entry/Exit weight.
- No factor weights, thresholds, labels, model registry authority or shadow observations change.
- No brokerage execution, allocation or copy-trading action exists.

## Security hardening

- Runtime dependencies move to `pyarrow==25.0.1` and `GitPython==3.1.59`, with no known
  vulnerabilities returned by the release audit.
- The FMP adapter accepts only credential-free HTTPS base URLs, bounds direct responses to 2 MiB
  and sanitizes provider exceptions before they can expose an API-key-bearing URL.
- Provider document links are retained only when they use credential-free HTTPS.
- The macOS launcher binds Streamlit to `127.0.0.1`, preventing unauthenticated LAN access to
  holdings, Journal and research surfaces.
- `.env`, `.env.alerts` and SQLite databases remain excluded from version control.

## Acceptance evidence required at commit

- Full `python -m pytest -q` passes.
- Python source compile/import check passes.
- `pip check`, `pip-audit`, Bandit and `git diff --check` pass or have documented, reviewed
  false positives with no high-severity finding.
- The real local service renders Dashboard and WhaleSeeker without browser-console errors.
- The commit contains only Phase 3.92 implementation, tests, documentation and release hardening.

## Known limits

- The initial live FMP bootstrap attempt returned HTTP 429; no partial payload was persisted and
  both chamber cursors remain retryable.
- Historical imports are retrospective and use the application's first observation as conservative
  `known_at`; they do not prove earlier public availability.
- Politician copyable returns remain pending a preregistered next-session outcome policy and are not
  shown as established performance.

## Reviewed static-analysis exceptions

- Bandit reports no high-severity finding.
- Its SQL-expression warnings refer to constant, source-defined column tuples and a fixed optional
  `WHERE ticker=?` clause; all values remain bound SQLite parameters. No provider or UI value can
  become an identifier or SQL fragment.
- Its low-severity fail-open warning is the pre-existing active-shadow persistence guard on the
  Dashboard. That research-only write is intentionally prevented from changing or blocking the
  official decision surface.

## Rollback

- Revert the single Phase 3.92 commit to remove the product and hardening code.
- Set `PILOT_DECISIONS_ENABLED=false` or `WHALESEEKER_ENABLED=false` for immediate presentation
  rollback while retaining immutable evidence.
- Additive SQLite tables may remain safely; no legacy research record requires rewriting.
