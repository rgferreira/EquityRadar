# Prospective nonstationarity monitor

## Source and product lesson

The design is informed by E.env's *Long-Horizon Planning in Nonstationary Environments*:
<https://edotenv.com/blog/long-horizon-planning>. A local PDF capture is stored at
`output/pdf/long-horizon-planning-nonstationary-environments.pdf`.

The benchmark's useful product lesson is that aggregate performance can hide whether a policy keeps
working after conditions change. Its agents must learn changing forecaster quality, and the analysis
inspects update lag, strategy duration, risk behavior, and history use. PersonalEquityRadar does not
recreate that controlled environment and cannot observe a true regime-change timestamp. It therefore
uses the idea only as a conservative trajectory diagnostic.

## Implemented method

The Model tuning page extends the existing post-promotion monitor without changing its outcome
contract:

1. Include only immutable predictions for the active model that were created after activation and have
   a decision date on or after activation.
2. Require an available, versioned 3M benchmark-relative outcome.
3. Reduce all security rows from one decision cutoff to one mean utility and one mean accuracy. This
   prevents a large cross-section from being treated as many independent market regimes.
4. Wait for ten independent dates, then compare the immediately prior five-date block with the most
   recent five-date block. Each date receives equal weight.
5. Display prior level, recent level, and level change. If mean utility crosses zero, show an inspection
   cue rather than a causal drift declaration.

The five-date window is a descriptive display cadence, not a promotion threshold. It does not enter the
six shadow-model readiness gates and cannot activate, promote, demote, or roll back a model.

## Limitations

- Real regime changes are latent and gradual; this is not a change-point detector.
- Adjacent 3M outcomes can overlap and remain serially correlated even after date clustering.
- Ten dates are enough to render the comparison, not enough to establish durable performance.
- A zero crossing can be noise, composition change, or a market-regime effect. It identifies a trajectory
  for review and never authorizes a policy change.
- The frozen promotion baseline remains visible separately. It is not silently recomputed from mutable
  data or mixed into the adjacent-window calculation.

## Rollback

Remove the `temporal_evidence` summary from `src/model_tuning.py` and its read-only block from
`pages/5_Model_Tuning.py`. No database migration, stored evidence, factor weight, score threshold, or
model-registry state needs reversal.
