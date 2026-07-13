# AGENTS.md

## Product purpose

PersonalEquityRadar is a local-first personal equity research and decision-support application. It is not an automated trading system and must not present unvalidated research outputs as proven investment advice.

## Authoritative context

- Current code and tests are the implementation source of truth.
- `docs/audit/2026-07-13/FORENSIC_REVIEW_ES.md` is the current audit, roadmap, and risk register.
- Evidence under `docs/audit/2026-07-13/evidence/` describes the audited snapshot; it is not proof of predictive skill.
- Phase 3.8 execution specifications live under `docs/implementation/phase-3.8/`.
- Verify every audit finding against the current HEAD before implementing it.

## Non-negotiable scientific rules

- Do not change factor weights, thresholds, labels, or decision policy unless the active task explicitly requires it and defines an evaluation method.
- Do not claim point-in-time validity without a verified `known_at`.
- `period_end`, settlement date, and `fetched_at` are not substitutes for public availability time.
- Legacy research records are read-only. Never rewrite historical outcomes or invent missing timestamps.
- Missing evidence must not silently become directional evidence.
- Preserve benchmark and baseline comparisons; do not optimize against the sanitized legacy sample.

## Engineering constraints

- Preserve a local-first modular monolith using Python, Streamlit, and SQLite.
- Prefer additive, reversible database migrations.
- Do not introduce cloud infrastructure, microservices, broker execution, leverage, or opaque machine-learning models.
- Keep each task PR-sized. Do not include unrelated cleanup or UI redesign.
- Preserve application behavior outside the explicitly approved scope.

## Privacy and security

- Never print, commit, or expose `.env` values, API keys, Journal text, holdings, quantities, transactions, cost bases, or personal cash flows.
- Tests must use synthetic or sanitized fixtures.
- Do not access external providers unless the task expressly needs them.

## Required workflow

Before editing:

1. Read the active task specification and relevant audit sections.
2. Inspect the current implementation and tests.
3. State whether the audit finding still applies.
4. Produce a file-level plan, risks, assumptions, and rollback approach.

After editing:

1. Add or update focused tests.
2. Run `python -m pytest -q`.
3. Run a Python compile/import check appropriate to the repository.
4. Review the diff for scope creep, leakage, destructive migrations, privacy issues, and undocumented behavior changes.
5. Report changed files, tests run, migrations, residual risks, and rollback.

## Definition of done

A task is complete only when its acceptance criteria are demonstrated, relevant tests pass, no unrelated behavior has changed, and the diff remains small enough to review confidently.
