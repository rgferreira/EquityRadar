from __future__ import annotations
import json, math, sqlite3, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path('/mnt/data/PersonalEquityRadar_AuditBundle/PersonalEquityRadar_AuditBundle')
OUT = Path('/mnt/data/per_audit_work')
# Local copies of the audited pure functions avoid importing network-provider modules.
LEARNING_WEIGHTS = {"1M": .50, "3M": .30, "6M": .20}
EPISODE_WINDOW_DAYS = 21
WATCH_UPSIDE_TOLERANCE = 3.0

def decision_outcome(run):
    monthly = {}
    for label, months in (("1M",1),("3M",3),("6M",6)):
        value = run.get(f"outcome_{label.lower()}")
        if value is not None:
            monthly[label] = float(value) / months
    available_weight = sum(LEARNING_WEIGHTS[label] for label in monthly)
    if not monthly:
        return {"composite":None,"decision_utility":None,"should_evaluate":False,"should_learn":False}
    composite = sum(monthly[label]*LEARNING_WEIGHTS[label] for label in monthly)/available_weight
    signal = str(run.get("entry_signal") or "Wait")
    if signal == "Buy candidate": utility = composite
    elif signal == "Watch": utility = WATCH_UPSIDE_TOLERANCE-composite if composite>=0 else -composite
    else: utility = -composite
    sufficient = available_weight >= .50
    confirmed = run.get("outcome_3m") is not None
    informative = abs(composite) >= .75
    return {"composite":round(composite,2),"decision_utility":round(utility,2),
            "should_evaluate":sufficient and informative,"should_learn":sufficient and informative and confirmed}

def _latest_runs_by_cutoff(runs):
    latest={}
    for i,run in enumerate(runs):
        cutoff=str(run.get("as_of_date") or run.get("created_at") or f"undated-{i}")
        existing=latest.get(cutoff)
        if existing is None or str(run.get("model_version") or "") > str(existing.get("model_version") or ""):
            latest[cutoff]=run
    return list(latest.values())

def select_learning_observations(runs, confirmed_only=True):
    selected=[]; signatures=[]
    for run in sorted(_latest_runs_by_cutoff(runs), key=lambda row:str(row.get("as_of_date") or "")):
        analysis=decision_outcome(run)
        enriched={**dict(run),**analysis}
        if not (analysis["should_learn"] if confirmed_only else analysis["should_evaluate"]): continue
        if selected:
            current_date=pd.Timestamp(str(run.get("as_of_date"))); previous_date=pd.Timestamp(str(selected[-1].get("as_of_date")))
            same_signal=str(run.get("entry_signal"))==str(selected[-1].get("entry_signal"))
            if same_signal and (current_date-previous_date).days < EPISODE_WINDOW_DAYS: continue
        signature=(str(run.get("entry_signal")),float(run.get("entry_score") or 0),float(analysis["composite"] or 0))
        duplicate=any(signature[0]==prev[0] and abs(signature[1]-prev[1])<3 and abs(signature[2]-prev[2])<.5 for prev in signatures)
        if duplicate: continue
        signatures.append(signature); selected.append(enriched)
    return selected

DB = ROOT / 'personal_equity_radar.db'
MODEL = 'backtested-learning-v4-orthogonal'
con = sqlite3.connect(DB)
df_all = pd.read_sql_query('select * from backtest_runs', con)

# Flatten stored inputs without printing securities/private fields beyond research records.
parsed = df_all['inputs_json'].map(json.loads)
metrics = pd.json_normalize(parsed.map(lambda x: x.get('metrics', {}))).add_prefix('metric_')
mods = pd.json_normalize(parsed.map(lambda x: x.get('positioning_modifier', {}))).add_prefix('pos_')
df_all = pd.concat([df_all.drop(columns=['inputs_json']), metrics, mods], axis=1)
df_all['fundamentals_used'] = parsed.map(lambda x: bool(x.get('fundamentals_used', False)))
df_all['finra_observations_used'] = parsed.map(lambda x: int(x.get('finra_observations_used') or 0))
df_all['as_of_date'] = pd.to_datetime(df_all['as_of_date'])
df = df_all[df_all.model_version.eq(MODEL)].copy()

# Research universe: remove benchmark and non-equity instrument for equity comparisons.
equity = df[~df.ticker.isin(['SPY','BTC-USD'])].copy()
spy = df[df.ticker.eq('SPY')].set_index('as_of_date')
for h in ['1m','3m','6m','12m']:
    mapping = spy[f'outcome_{h}'].to_dict()
    df[f'spy_{h}'] = df['as_of_date'].map(mapping)
    df[f'excess_{h}'] = df[f'outcome_{h}'] - df[f'spy_{h}']
    equity[f'spy_{h}'] = equity['as_of_date'].map(mapping)
    equity[f'excess_{h}'] = equity[f'outcome_{h}'] - equity[f'spy_{h}']

# Reconstructed transparent baseline scores.
for frame in (df, equity):
    frame['core_weighted'] = .5*frame.technical_score + .3*frame.valuation_score + .2*frame.risk_score
    frame['equal_factor'] = frame[['technical_score','valuation_score','risk_score']].mean(axis=1)
    frame['momentum_12m'] = frame['metric_return_12m']

rng = np.random.default_rng(20260713)
def ci_mean(values, cluster=None, reps=10000):
    x = pd.Series(values).dropna().astype(float)
    if x.empty:
        return {'n':0,'mean':None,'lo':None,'hi':None}
    if cluster is None:
        units = x.to_numpy()
        boots = rng.choice(units, size=(reps, len(units)), replace=True).mean(axis=1)
    else:
        tmp = pd.DataFrame({'x':values,'cluster':cluster}).dropna()
        means = tmp.groupby('cluster').x.mean().to_numpy()
        if len(means)==0:
            return {'n':0,'mean':None,'lo':None,'hi':None}
        boots = rng.choice(means, size=(reps, len(means)), replace=True).mean(axis=1)
        x = pd.Series(means)
    return {'n':int(len(x)), 'mean':round(float(x.mean()),3),
            'lo':round(float(np.quantile(boots,.025)),3), 'hi':round(float(np.quantile(boots,.975)),3)}

def wilson(k,n,z=1.959963984540054):
    if n==0: return {'n':0,'rate':None,'lo':None,'hi':None}
    p=k/n; den=1+z*z/n
    center=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return {'n':n,'rate':round(100*p,1),'lo':round(100*(center-half),1),'hi':round(100*(center+half),1)}

def bootstrap_date_stat(date_values, reps=10000):
    vals=np.asarray([v for v in date_values if pd.notna(v)], dtype=float)
    if len(vals)==0: return {'dates':0,'mean':None,'median':None,'positive_pct':None,'lo':None,'hi':None}
    boots=rng.choice(vals,size=(reps,len(vals)),replace=True).mean(axis=1)
    return {'dates':int(len(vals)),'mean':round(float(vals.mean()),3),'median':round(float(np.median(vals)),3),
            'positive_pct':round(float((vals>0).mean()*100),1),
            'lo':round(float(np.quantile(boots,.025)),3),'hi':round(float(np.quantile(boots,.975)),3)}

def per_date_spearman(frame, score, outcome):
    vals=[]
    for d,g in frame.dropna(subset=[score,outcome]).groupby('as_of_date'):
        if len(g)>=6 and g[score].nunique()>1 and g[outcome].nunique()>1:
            vals.append(spearmanr(g[score],g[outcome]).statistic)
    return bootstrap_date_stat(vals)

def per_date_spread(frame, score, outcome, topn=4):
    vals=[]; tops=[]
    for d,g in frame.dropna(subset=[score,outcome]).groupby('as_of_date'):
        if len(g) < topn*2: continue
        gs=g.sort_values(score)
        bottom=gs.head(topn)[outcome].mean(); top=gs.tail(topn)[outcome].mean()
        vals.append(top-bottom); tops.append(top)
    return {'top_minus_bottom':bootstrap_date_stat(vals), 'top_mean':bootstrap_date_stat(tops)}

# Counts and maturity.
summary={}
summary['rows']={
    'total':int(len(df_all)), 'unique_ticker_dates_all_versions':int(df_all[['ticker','as_of_date']].drop_duplicates().shape[0]),
    'latest_model':int(len(df)), 'tickers_latest':int(df.ticker.nunique()), 'equities_ex_benchmark_crypto':int(equity.ticker.nunique()),
    'dates_latest':int(df.as_of_date.nunique()), 'model_versions':int(df_all.model_version.nunique()),
    'duplicate_model_rows_same_outcomes':int(len(df_all)-df_all[['ticker','as_of_date']].drop_duplicates().shape[0]),
}
summary['model_versions']={str(k):int(v) for k,v in df_all.model_version.value_counts().items()}
summary['date_range']={'min':df.as_of_date.min().date().isoformat(),'max':df.as_of_date.max().date().isoformat()}
summary['source']={str(k):int(v) for k,v in df.simulation_source.value_counts().items()}
summary['entry_balance']={str(k):int(v) for k,v in df.entry_signal.value_counts().items()}
summary['exit_balance']={str(k):int(v) for k,v in df.exit_signal.value_counts().items()}
summary['coverage']={str(k):int(v) for k,v in df.coverage.value_counts().items()}
summary['evidence_flags']={
    'fundamentals_flagged_rows':int(df.fundamentals_used.sum()),
    'fundamentals_flagged_pct':round(100*df.fundamentals_used.mean(),1),
    'finra_any_rows':int((df.finra_observations_used>0).sum()),
    'finra_any_pct':round(100*(df.finra_observations_used>0).mean(),1),
    'price_only_rows':int(df.coverage.eq('Price-only reconstruction').sum()),
    'industry_peer_analyst_fields_in_backtest_inputs':0,
}
summary['maturity']={h:{'rows':int(df[f'outcome_{h}'].notna().sum()),'pct':round(100*df[f'outcome_{h}'].notna().mean(),1),
                         'dates':int(df.loc[df[f'outcome_{h}'].notna(),'as_of_date'].nunique())} for h in ['1m','3m','6m','12m']}

# Date/ticker dependence and purged counts.
dates=sorted(df.as_of_date.unique())
bdays=[int(np.busday_count(pd.Timestamp(a).date(),pd.Timestamp(b).date())) for a,b in zip(dates[:-1],dates[1:])]
summary['clustering']={
    'rows_per_date_min':int(df.groupby('as_of_date').size().min()),'rows_per_date_max':int(df.groupby('as_of_date').size().max()),
    'median_business_day_gap':float(np.median(bdays)),
    'adjacent_gaps_lt_21bd':int(sum(x<21 for x in bdays)),
    'adjacent_gaps_lt_63bd':int(sum(x<63 for x in bdays)),
    'adjacent_gaps_lt_126bd':int(sum(x<126 for x in bdays)),
    'adjacent_gaps_total':int(len(bdays)),
}
def greedy_purge(ds,min_bd):
    kept=[]
    for d in sorted(pd.Timestamp(x) for x in ds):
        if not kept or np.busday_count(kept[-1].date(),d.date())>=min_bd:
            kept.append(d)
    return kept
for h,bd in [('1m',21),('3m',63),('6m',126),('12m',252)]:
    mature=sorted(df.loc[df[f'outcome_{h}'].notna(),'as_of_date'].unique())
    summary['clustering'][f'greedy_nonoverlap_dates_{h}']=len(greedy_purge(mature,bd))

# Independent episode gate used by app, applied correctly per ticker.
episode_rows=[]
for ticker,g in df.groupby('ticker'):
    records=[]
    for _,r in g.sort_values('as_of_date').iterrows():
        rec=r.where(pd.notna(r),None).to_dict()
        rec['as_of_date']=r.as_of_date.date().isoformat()
        records.append(rec)
    selected=select_learning_observations(records)
    episode_rows.append({'ticker':ticker,'episodes':len(selected),
                         'dates':[str(x.get('as_of_date')) for x in selected]})
episodes=pd.DataFrame(episode_rows)
summary['learning_episodes']={
    'sum_per_ticker':int(episodes.episodes.sum()),'median_per_ticker':float(episodes.episodes.median()),
    'min_per_ticker':int(episodes.episodes.min()),'max_per_ticker':int(episodes.episodes.max()),
    'unique_calendar_dates_across_selected':int(len(set(d for ds in episodes.dates for d in ds))),
    'tickers_at_or_above_3':int((episodes.episodes>=3).sum()),
    'tickers_at_or_above_15':int((episodes.episodes>=15).sum()),
}

# Factor distributions and discontinuities.
summary['factor_distribution']={}
for col in ['technical_score','valuation_score','risk_score','entry_score','exit_score','core_weighted','equal_factor','pos_entry_adjustment','pos_exit_adjustment']:
    s=df[col].dropna().astype(float)
    summary['factor_distribution'][col]={
        'n':int(len(s)),'mean':round(float(s.mean()),2),'std':round(float(s.std()),2),
        'min':round(float(s.min()),2),'p25':round(float(s.quantile(.25)),2),'median':round(float(s.median()),2),
        'p75':round(float(s.quantile(.75)),2),'max':round(float(s.max()),2),'unique':int(s.nunique()),
        'most_common':[(round(float(v),2),int(n)) for v,n in s.value_counts().head(8).items()]
    }
summary['threshold_sensitivity']={
    'within_2_of_55_or_70':int(df.entry_score.apply(lambda x:min(abs(x-55),abs(x-70))<=2).sum()),
    'pct_within_2':round(100*df.entry_score.apply(lambda x:min(abs(x-55),abs(x-70))<=2).mean(),1),
    'within_5_of_55_or_70':int(df.entry_score.apply(lambda x:min(abs(x-55),abs(x-70))<=5).sum()),
    'pct_within_5':round(100*df.entry_score.apply(lambda x:min(abs(x-55),abs(x-70))<=5).mean(),1),
}
# Exact neutral valuation and positioning adjustment rates.
summary['neutrality']={
    'valuation_exact_50_rows':int(df.valuation_score.eq(50).sum()),
    'valuation_exact_50_pct':round(100*df.valuation_score.eq(50).mean(),1),
    'positioning_entry_zero_rows':int(df.pos_entry_adjustment.fillna(0).eq(0).sum()),
    'positioning_entry_zero_pct':round(100*df.pos_entry_adjustment.fillna(0).eq(0).mean(),1),
}

# Pairwise Spearman on rows; explicitly descriptive and clustered.
factor_cols=['technical_score','valuation_score','risk_score','entry_score','core_weighted','equal_factor','momentum_12m']
summary['row_spearman']=df[factor_cols].corr(method='spearman').round(3).to_dict()

# Predictive diagnostics by horizon and benchmark-relative outcomes.
summary['rank_ic']={}
summary['spreads']={}
for outcome in ['outcome_3m','excess_3m','outcome_6m','excess_6m']:
    summary['rank_ic'][outcome]={score:per_date_spearman(equity,score,outcome) for score in factor_cols}
    summary['spreads'][outcome]={score:per_date_spread(equity,score,outcome) for score in ['entry_score','core_weighted','equal_factor','momentum_12m','technical_score','valuation_score','risk_score']}

# Entry signal performance by horizon: date-cluster CI, median/positive/loss severity.
summary['signal_performance']={}
for h in ['1m','3m','6m']:
    for outcome in [f'outcome_{h}',f'excess_{h}']:
        bucket={}
        for sig,g in equity.dropna(subset=[outcome]).groupby('entry_signal'):
            bucket[sig]={
                'rows':int(len(g)),'dates':int(g.as_of_date.nunique()),
                'mean':round(float(g[outcome].mean()),2),'median':round(float(g[outcome].median()),2),
                'positive_rate':wilson(int((g[outcome]>0).sum()),len(g)),
                'p10':round(float(g[outcome].quantile(.1)),2),
                'mean_loss':round(float(g.loc[g[outcome]<0,outcome].mean()),2) if (g[outcome]<0).any() else None,
                'clustered_mean_ci':ci_mean(g[outcome],g.as_of_date),
            }
        summary['signal_performance'][outcome]=bucket

# Crude binary diagnostics, only as a diagnostic not a claim of target fit.
for outcome in ['excess_3m','excess_6m']:
    g=equity.dropna(subset=[outcome]).copy()
    y=g[outcome]>0; pred=g.entry_signal.eq('Buy candidate')
    tp=int((y&pred).sum()); tn=int((~y&~pred).sum()); fp=int((~y&pred).sum()); fn=int((y&~pred).sum())
    summary.setdefault('binary_diagnostics',{})[outcome]={
        'n':int(len(g)),'tp':tp,'tn':tn,'fp':fp,'fn':fn,
        'precision_buy':round(tp/(tp+fp),3) if tp+fp else None,
        'recall_outperformance':round(tp/(tp+fn),3) if tp+fn else None,
        'specificity':round(tn/(tn+fp),3) if tn+fp else None,
        'balanced_accuracy':round(.5*(tp/(tp+fn)+tn/(tn+fp)),3) if tp+fn and tn+fp else None,
    }

# Recommendation stability: consecutive signals per ticker.
changes=[]
for ticker,g in df.sort_values('as_of_date').groupby('ticker'):
    rows=list(g[['as_of_date','entry_signal','entry_score']].itertuples(index=False,name=None))
    for a,b in zip(rows[:-1],rows[1:]):
        gap=int(np.busday_count(a[0].date(),b[0].date()))
        changes.append({'ticker':ticker,'gap_bd':gap,'flip':a[1]!=b[1],'score_delta':b[2]-a[2],
                        'rapid_flip':a[1]!=b[1] and gap<21})
chg=pd.DataFrame(changes)
summary['stability']={
    'transitions':int(len(chg)),'flips':int(chg.flip.sum()),'flip_rate_pct':round(100*chg.flip.mean(),1),
    'rapid_flips_lt_21bd':int(chg.rapid_flip.sum()),
    'median_abs_score_change':round(float(chg.score_delta.abs().median()),2),
    'p90_abs_score_change':round(float(chg.score_delta.abs().quantile(.9)),2),
}

# Current utility system as implemented, not endorsed.
implemented=[]
for _,r in df.iterrows():
    rec=r.where(pd.notna(r),None).to_dict(); rec['as_of_date']=r.as_of_date.date().isoformat()
    a=decision_outcome(rec)
    implemented.append(a)
impl=pd.DataFrame(implemented)
summary['implemented_utility']={
    'evaluated_rows':int(impl.should_evaluate.sum()),'learnable_rows':int(impl.should_learn.sum()),
    'positive_utility_pct_all_evaluated':round(100*(impl.loc[impl.should_evaluate,'decision_utility']>0).mean(),1) if impl.should_evaluate.any() else None,
    'confirmed_positive_utility_pct':round(100*(impl.loc[impl.should_learn,'decision_utility']>0).mean(),1) if impl.should_learn.any() else None,
}

# Save detailed date-level tables for audit reproducibility.
summary_path=OUT/'empirical_summary.json'
summary_path.write_text(json.dumps(summary,indent=2,default=str),encoding='utf-8')
episodes.drop(columns=['dates']).to_csv(OUT/'learning_episodes_by_ticker.csv',index=False)
# No personal financial data; these are research/backtest aggregate rows.
df[['ticker','as_of_date','entry_score','entry_signal','technical_score','valuation_score','risk_score',
    'outcome_1m','outcome_3m','outcome_6m','outcome_12m','excess_1m','excess_3m','excess_6m','simulation_source',
    'fundamentals_used','finra_observations_used']].to_csv(OUT/'latest_model_research_rows.csv',index=False)
print(json.dumps(summary,indent=2,default=str))
