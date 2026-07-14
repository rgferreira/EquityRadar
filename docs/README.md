# Documentation map

The documents in this folder have distinct roles so planning, implementation history and research evidence do not drift into one another.

| Document | Purpose | Status |
|---|---|---|
| [`releases/phase-3.9/USER_IMPACT.md`](releases/phase-3.9/USER_IMPACT.md) | Phase 3.9 user-visible impact, score evolution and simulation guidance | Current release note |
| [`implementation/AUDIT_TRIAGE.md`](implementation/AUDIT_TRIAGE.md) | Phase 3.8 audit findings reconciled against current HEAD | Current |
| [`implementation/phase-3.8/ROADMAP-3.8.md`](implementation/phase-3.8/ROADMAP-3.8.md) | Ordered scientific-hardening slices and delivery gates | Current |
| [`temporal-data-contract.md`](temporal-data-contract.md) | Source-specific point-in-time fields and conservative availability rules | Current |
| [`model-governance.md`](model-governance.md) | Explicit registry, immutable prediction lineage, legacy separation and replay | Current |
| [`audit/2026-07-13/FORENSIC_REVIEW_ES.md`](audit/2026-07-13/FORENSIC_REVIEW_ES.md) | Independent forensic review and scientific risk register | Authoritative audit |
| [`next-best-actions.md`](next-best-actions.md) | Phase 3.8 pointer, deferred Phase 3.7 operations, and saved Phase 4 candidates | Current |
| [`implemented-features.md`](implemented-features.md) | Detailed record of behavior already present in the application | Current |
| [`internal-changelog.md`](internal-changelog.md) | Compact internal phase/checkpoint and scoring-model narrative | Current |
| [`industry-feature.md`](industry-feature.md) | Industry cohort architecture, calibration and refresh rules | Reference |
| [`market-positioning-source-audit.md`](market-positioning-source-audit.md) | Provider/source audit and reliability constraints for positioning | Reference |
| [`revolut-fix-assessment.md`](revolut-fix-assessment.md) | Revolut Exchange FIX product-fit investigation | Closed assessment |

Rules:

- Phase 3.8 implementation work follows the reconciled audit roadmap and its PR specifications; other planned work goes into `next-best-actions.md`.
- Completed behavior moves to `implemented-features.md`.
- Architectural/source investigations stay in dedicated reference documents and are linked rather than copied.
- Internal phase names and model checkpoints are summarized in `internal-changelog.md`.
