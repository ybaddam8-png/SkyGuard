from __future__ import annotations
import json, math, time, warnings
from pathlib import Path
from collections import defaultdict
import numpy as np, pandas as pd, yaml
warnings.filterwarnings('ignore')
from sklearn.metrics import precision_recall_fscore_support, f1_score, precision_score, recall_score, confusion_matrix, average_precision_score, roc_auc_score
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import GroupKFold
from lightgbm import LGBMClassifier, LGBMRegressor
import matplotlib.pyplot as plt
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from skyguard_inject import inject_faults, VARS, CLASSES

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'outputs'; BENCH=ROOT/'data/bench'; CFG=yaml.safe_load(open(ROOT/'config/cadence_3h.yaml'))
OUT.mkdir(exist_ok=True); (OUT/'figures').mkdir(exist_ok=True); BENCH.mkdir(exist_ok=True)
SEED=42; rng=np.random.default_rng(SEED)
clean=pd.read_parquet(ROOT/'data/clean/observations_clean.parquet').sort_values(['station_id','time_utc']).reset_index(drop=True)
clean['station_id']=clean.station_id.astype(str); clean['time_utc']=pd.to_datetime(clean.time_utc,utc=True)
stations=pd.read_csv(ROOT/'stations.csv'); stations['station_id']=stations.station_id.astype(str)
# exact protected windows, cluster-specific
windows=[('heatwave_a','a',pd.Timestamp('2024-05-16T18:30Z'),pd.Timestamp('2024-06-19T18:29:59Z')),('biparjoy_a','a',pd.Timestamp('2023-06-16T18:00Z'),pd.Timestamp('2023-06-21T00:00Z')),('monsoon_c','c',pd.Timestamp('2024-07-23T00:00Z'),pd.Timestamp('2024-07-30T00:00Z'))]
protected=np.zeros(len(clean),bool)
window_name=np.full(len(clean),'',dtype=object)
for name,c,a,b in windows:
 m=(clean.cluster==c)&clean.time_utc.between(a,b,inclusive='both'); protected|=m; window_name[m.to_numpy()]=name
inj,labels=inject_faults(clean,protected,seed=SEED)
if labels.empty: raise RuntimeError('injector produced no labels')
labels.to_parquet(BENCH/'labels.parquet',index=False); inj.to_parquet(BENCH/'observations_injected.parquet',index=False)
# per variable labels, row-level class is first injected class; preserve multi-faults
label_map={(str(r.station_id),pd.Timestamp(r.time_utc),str(r.variable)):r['class'] for _,r in labels.iterrows()}
# ---------- learned limits, climatology, neighbours ----------
limits={}; clim={}
for sid,g in clean.groupby('station_id'):
 for v in VARS:
  x=g[v].diff().abs().dropna(); limits[(sid,v)]=float(x.quantile(.999)) if len(x) else 1.0
  q=g.groupby([g.time_utc.dt.month,g.time_utc.dt.hour])[v].agg(['median','std']).rename(columns={'median':'mu','std':'sd'}); clim[(sid,v)]=q
# neighbour map: primary first, sparse fallback if <2
coords=stations.set_index('station_id')
def hav(a,b):
 r=6371.0088;p1,p2=np.radians([a.lat,b.lat]);dp=np.radians(b.lat-a.lat);dl=np.radians(b.lon-a.lon);z=np.sin(dp/2)**2+np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2;return float(2*r*np.arcsin(np.sqrt(z)))
neigh={}; neigh_kind={}
for sid,a in coords.iterrows():
 cand=[]
 for oid,b in coords.iterrows():
  if sid==oid or a.cluster!=b.cluster: continue
  cand.append((hav(a,b),abs(a.elevation_m-b.elevation_m),oid))
 prim=[x for x in cand if x[0]<=200 and x[1]<=500]
 use=prim; kind='primary'
 if len(use)<2:
  use=[x for x in cand if x[0]<=300 and x[1]<=800]; kind='sparse'
 neigh[sid]=sorted(use)[:8]; neigh_kind[sid]=kind if use else 'none'
# climatology lookup fallback station global median
clim_lookup={}
for sid,g in clean.assign(_month=clean.time_utc.dt.month,_hour=clean.time_utc.dt.hour).groupby('station_id'):
 for v in VARS:
  q=g.groupby(['_month','_hour'])[v].agg(['median','std'])
  fallback=(float(g[v].median()) if g[v].notna().any() else 0.0,float(g[v].std() or 1.0))
  for m in range(1,13):
   for h in range(24):
    if (m,h) in q.index and pd.notna(q.loc[(m,h),'median']): clim_lookup[(str(sid),v,m,h)]=(float(q.loc[(m,h),'median']),float(q.loc[(m,h),'std'] or 1.0))
    else: clim_lookup[(str(sid),v,m,h)]=fallback
# ---------- features ----------
def make_features(frame):
 x=frame.copy().sort_values(['station_id','time_utc']).reset_index(drop=True); out=pd.DataFrame(index=x.index)
 lookup={v: {(str(s),t): val for s,t,val in zip(x.station_id,x.time_utc,x[v])} for v in VARS}
 mu_by_var={}; sd_by_var={}
 for v in VARS:
  pairs=[clim_lookup[(str(s),v,int(t.month),int(t.hour))] for s,t in zip(x.station_id,x.time_utc)]
  mu_by_var[v]=np.array([p[0] for p in pairs]); sd_by_var[v]=np.maximum(np.array([p[1] for p in pairs]),1e-3)
 for v in VARS:
  x[v]=pd.to_numeric(x[v],errors='coerce').astype('float64')
  out[v]=x[v].astype(float)
  out[v+'_missing']=x[v].isna().astype(int)
  grp=x.groupby('station_id',sort=False)[v]
  for lag in [1,2,4,8]: out[f'{v}_lag{lag}']=grp.shift(lag)
  for w in [1,8]: out[f'{v}_roll{w}_mean']=grp.transform(lambda z:z.rolling(w,min_periods=1).mean()); out[f'{v}_roll{w}_std']=grp.transform(lambda z:z.rolling(w,min_periods=1).std())
  out[v+'_diff1']=x.groupby('station_id',sort=False)[v].diff()
  out[v+'_absdiff1']=out[v+'_diff1'].abs()
  # learned step z and persistence run
  out[v+'_step_limit']=[limits.get((str(s),v),1.0) for s in x.station_id]
  out[v+'_step_flag']=((out[v+'_absdiff1'].fillna(0)>out[v+'_step_limit'].fillna(1.0))).astype(int)
  out[v+'_range_flag']=((x[v] < {'temp_c':-80,'mslp_hpa':870,'rh_pct':0}[v])|(x[v] > {'temp_c':60,'mslp_hpa':1085,'rh_pct':100}[v])).astype(int)
  out[v+'_zero4']=grp.transform(lambda z:z.diff().abs().rolling(4,min_periods=4).sum()).fillna(999).lt({'temp_c':.1,'mslp_hpa':.1,'rh_pct':1}[v]).astype(int)
  out[v+'_clim_z']=(x[v].to_numpy()-mu_by_var[v])/sd_by_var[v]
 # T2 vapour pressure and cross-variable residuals
 T=x.temp_c; RH=x.rh_pct
 out['vapour_pressure']=(RH/100)*6.112*np.exp(17.62*T/(243.12+T)); out['e_jump']=out.groupby(x.station_id)['vapour_pressure'].diff().abs(); out['e_jump']=out.e_jump.fillna(0)
 out['dewpoint_excess']=(243.12*(np.log(np.clip(RH,1e-3,100)/100)+17.62*T/(243.12+T))/(17.62-(np.log(np.clip(RH,1e-3,100)/100)+17.62*T/(243.12+T)))-T).fillna(0)
 # T3 weighted neighbour deviation, tendency 1 step; sparse confidence
 for v in VARS:
  z3=[]; agr=[]; conf=[]
  dev_map={(str(s),t): (float(val-mu) if pd.notna(val) else np.nan) for s,t,val,mu in zip(x.station_id,x.time_utc,x[v],mu_by_var[v])}
  for sid,t,val in zip(x.station_id,x.time_utc,x[v]):
   sid=str(sid); d0=float(val-mu_by_var[v][len(z3)]) if pd.notna(val) else 0.0; vals=[]; ws=[]
   for dist,elev,oid in neigh.get(sid,[]):
    ov=dev_map.get((str(oid),t),np.nan)
    if pd.notna(ov): vals.append(float(ov)); ws.append(np.exp(-dist/75)*np.exp(-elev/300))
   if vals:
    med=float(np.average(vals,weights=ws)); mad=float(np.median(np.abs(np.array(vals)-med))); z3.append((d0-med)/(1.4826*mad+max(limits.get((sid,v),1),1e-3)))
    agr.append(float(np.mean([np.sign(q)==np.sign(d0) and abs(q)>=.5*abs(d0) for q in vals])) if d0 else 1.0); conf.append(.7 if neigh_kind.get(sid)=='sparse' else 1.0)
   else: z3.append(0.0); agr.append(0.0); conf.append(0.0)
  out['z3_'+v]=z3; out['neighbour_agreement_'+v]=agr; out['neighbour_confidence_'+v]=conf
 out['hour_sin']=np.sin(2*np.pi*x.time_utc.dt.hour/24); out['hour_cos']=np.cos(2*np.pi*x.time_utc.dt.hour/24); out['doy_sin']=np.sin(2*np.pi*x.time_utc.dt.dayofyear/365.25); out['doy_cos']=np.cos(2*np.pi*x.time_utc.dt.dayofyear/365.25)
 out['station_code']=pd.factorize(x.station_id)[0]; out['elevation_m']=[float(coords.loc[str(s),'elevation_m']) for s in x.station_id]; out['lat']=[float(coords.loc[str(s),'lat']) for s in x.station_id]
 return x,out.replace([np.inf,-np.inf],np.nan).fillna(0)
Xraw,X=make_features(inj)
# labels at row level: any fault and primary class
row_classes=[]; y=[]
for _,r in Xraw.iterrows():
 cs=[label_map.get((str(r.station_id),pd.Timestamp(r.time_utc),v)) for v in VARS]
 cs.append(label_map.get((str(r.station_id),pd.Timestamp(r.time_utc),'all')))
 cs=[c for c in cs if c]
 row_classes.append(cs[0] if cs else 'weather'); y.append(int(bool(cs)))
y=np.array(y); row_classes=np.array(row_classes); groups=Xraw.station_id.values; feature_cols=list(X.columns)
# Train T1 quantile models on clean features (global; models capped 200 trees). Predictions/residuals are features.
_,Xclean=make_features(clean); Xclean=Xclean[feature_cols]
models={};
for v in VARS:
 target=clean[v].fillna(clean[v].median())
 # use compact feature set to keep training robust
 cols=[c for c in feature_cols if c.startswith(v+'_lag') or c.startswith(v+'_roll') or c in ['hour_sin','hour_cos','doy_sin','doy_cos','elevation_m','lat']]
 models[v]={}
 for q in [.1,.5,.9]:
  m=LGBMRegressor(objective='quantile',alpha=q,n_estimators=200,max_depth=7,num_leaves=31,learning_rate=.05,verbosity=-1,random_state=SEED)
  m.fit(Xclean[cols],target); models[v][q]=(m,cols)
  X[f't1_q{int(q*100)}_{v}']=m.predict(X[cols])
 X['z1_'+v]=(Xraw[v]-X[f't1_q50_{v}'])/((X[f't1_q90_{v}']-X[f't1_q10_{v}'])/2.563+1e-3)
# T2 simple residual proxy from cross-variable climatological expected values
for v in VARS:
 other=[q for q in VARS if q!=v]; X['z2_'+v]=(X[v+'_clim_z']-X[other[0]+'_clim_z'].fillna(0)*0.15-X[other[1]+'_clim_z'].fillna(0)*0.15)
# score columns
zcols=[c for c in X if c.startswith(('z1_','z2_','z3_'))]; t0cols=[c for c in X if c.endswith(('_range_flag','_step_flag','_zero4'))]
X['t0_hard']=X[[c for c in X if c.endswith('_range_flag')]].max(axis=1); X['t0_soft']=X[[c for c in X if c.endswith(('_step_flag','_zero4'))]].max(axis=1); X['z_max']=X[zcols].abs().max(axis=1)
# avoid nonnumeric raw station id/time; all X numeric
# ---------- grouped 5-fold CV ----------
folds=list(GroupKFold(n_splits=5).split(X,y,groups=groups)); fold_metrics=[]; all_pred=np.zeros(len(y)); all_cls=np.full(len(y),'weather',object); cm_total=np.zeros((10,10),int); fold_feature_importance=[]
# baseline T0 and isolation forest per fold; ablations train fusion with selected evidence blocks
blocks={'all':None,'no_T1':[c for c in X.columns if not c.startswith('z1_') and not c.startswith('t1_q')],'no_T2':[c for c in X.columns if not c.startswith('z2_')],'no_T3':[c for c in X.columns if not c.startswith(('z3_','neighbour_'))]}
base_cols=[c for c in X.columns if c not in ['station_code']]
for fi,(tr,te) in enumerate(folds):
 # use training only for classifier; labels include weather as negative
 model=LGBMClassifier(n_estimators=200,max_depth=7,num_leaves=31,learning_rate=.05,class_weight='balanced',verbosity=-1,random_state=SEED+fi)
 model.fit(X.iloc[tr][base_cols],y[tr]); p=model.predict_proba(X.iloc[te][base_cols])[:,1]; pred=(p>=.5).astype(int); all_pred[te]=p
 # multiclass over fault classes, excluding weather if no data in train
 mc=LGBMClassifier(n_estimators=200,max_depth=7,num_leaves=31,learning_rate=.05,class_weight='balanced',verbosity=-1,random_state=SEED+fi)
 mc.fit(X.iloc[tr][base_cols],row_classes[tr]); cp=mc.predict(X.iloc[te][base_cols]); all_cls[te]=cp
 # baselines
 t0=(X.iloc[te]['t0_hard'].to_numpy()>0)|(X.iloc[te]['t0_soft'].to_numpy()>0)|(X.iloc[te]['z_max'].to_numpy()>6)
 iso=IsolationForest(n_estimators=100,random_state=SEED+fi,contamination=0.03,n_jobs=-1).fit(X.iloc[tr][[c for c in base_cols if c not in ['t0_hard','t0_soft']].copy()])
 ip=iso.predict(X.iloc[te][[c for c in base_cols if c not in ['t0_hard','t0_soft']]])==-1
 def met(a,b): return {'precision':float(precision_score(a,b,zero_division=0)),'recall':float(recall_score(a,b,zero_division=0)),'f1':float(f1_score(a,b,zero_division=0))}
 fm=met(y[te],pred); fm.update({'fold':fi+1,'n_test':int(len(te)),'t0_f1':met(y[te],t0)['f1'],'iforest_f1':met(y[te],ip)['f1']}); fold_metrics.append(fm)
 # ablation quick models
 for name,drop in blocks.items():
  if name=='all': continue
  cols=[c for c in base_cols if c not in (drop or [])]
  am=LGBMClassifier(n_estimators=200,max_depth=7,num_leaves=31,learning_rate=.05,class_weight='balanced',verbosity=-1,random_state=SEED+fi)
  am.fit(X.iloc[tr][cols],y[tr]); ap=am.predict(X.iloc[te][cols]); fold_metrics[-1][name+'_f1']=float(f1_score(y[te],ap,zero_division=0))
  if name=='no_T1': pass
  if name=='no_T2': pass
  if name=='no_T3': pass
 # confusion fault classes for test rows; weather as tenth
 labs=CLASSES+['weather']; cm_total += confusion_matrix(row_classes[te],all_cls[te],labels=labs)
 fold_feature_importance.append(pd.Series(model.feature_importances_,index=base_cols))
 print('fold',fi+1,'f1',round(fm['f1'],4),flush=True)
# per-class metrics across folds using out-of-fold predictions (reported as one OOF estimate + fold spread for binary)
metric_names=['precision','recall','f1','t0_f1','iforest_f1','no_T1_f1','no_T2_f1','no_T3_f1']
metrics={'config':CFG,'dataset':{'rows':int(len(inj)),'stations':int(inj.station_id.nunique()),'labels':int(len(labels)),'protected_rows':int(protected.sum())},'cv':{'folds':5,'grouped_by':'station','fold_station_counts':[int(len(np.unique(groups[te]))) for _,te in folds]},'metrics':{}}
for n in metric_names:
 vals=[r[n] for r in fold_metrics if n in r]; metrics['metrics'][n]={'mean':float(np.mean(vals)),'std':float(np.std(vals,ddof=1) if len(vals)>1 else 0),'folds':vals}
metrics['per_class']={}
for cls in CLASSES:
 yt=(row_classes==cls).astype(int); yp=(all_cls==cls).astype(int); metrics['per_class'][cls]={'precision':float(precision_score(yt,yp,zero_division=0)),'recall':float(recall_score(yt,yp,zero_division=0)),'f1':float(f1_score(yt,yp,zero_division=0))}
metrics['macro_f1_faults']=float(np.mean([metrics['per_class'][c]['f1'] for c in CLASSES])); metrics['label_counts']=pd.Series(row_classes).value_counts().to_dict(); metrics['neighbours']={'primary_rule':'<=200 km / <=500 m','sparse_rule':'<=300 km / <=800 m','sparse_stations':[s for s in neigh if neigh_kind[s]=='sparse'],'abstain_stations':[s for s in neigh if not neigh[s]],'links':{s:[{'station_id':o,'distance_km':round(d,1),'elevation_diff_m':round(e,1),'kind':neigh_kind[s]} for d,e,o in neigh[s]] for s in neigh}}
metrics['latency_ms']={'p50':None,'p95':None}
with open(OUT/'metrics.json','w') as f: json.dump(metrics,f,indent=2,default=lambda x: x.item() if isinstance(x,np.generic) else str(x))
# figures
plt.style.use('seaborn-v0_8-whitegrid')
# per-class F1 chart with baselines approximated from T0/IF overall
fig,ax=plt.subplots(figsize=(10,5)); vals=[metrics['per_class'][c]['f1'] for c in CLASSES]; ax.bar(CLASSES,vals,color='#1677b8'); ax.set_ylim(0,1); ax.set_ylabel('OOF F1'); ax.set_title('SkyGuard per-fault F1 (grouped station CV)'); fig.tight_layout(); fig.savefig(OUT/'figures/per_class_f1.png',dpi=160); plt.close(fig)
fig,ax=plt.subplots(figsize=(7,4)); names=['Full','No T1','No T2','No T3']; vals=[metrics['metrics']['f1']['mean'],metrics['metrics']['no_T1_f1']['mean'],metrics['metrics']['no_T2_f1']['mean'],metrics['metrics']['no_T3_f1']['mean']]; ax.bar(names,vals,color=['#1677b8','#f28e2b','#59a14f','#e15759']); ax.set_ylim(0,1); ax.set_ylabel('F1'); ax.set_title('Ablation: evidence-tier removal'); fig.tight_layout(); fig.savefig(OUT/'figures/ablation.png',dpi=160); plt.close(fig)
fig,ax=plt.subplots(figsize=(8,7)); im=ax.imshow(cm_total, cmap='Blues'); ax.set_xticks(range(10),CLASSES+['weather'],rotation=45,ha='right'); ax.set_yticks(range(10),CLASSES+['weather']); ax.set_title('Out-of-fold root-cause confusion matrix'); fig.colorbar(im,ax=ax); fig.tight_layout(); fig.savefig(OUT/'figures/confusion_matrix.png',dpi=160); plt.close(fig)
# example and protected window figures
sample=inj[inj.injected_faults.str.len()>0].head(1).station_id.iloc[0]; eg=inj[inj.station_id==sample].head(300); fig,ax=plt.subplots(3,1,figsize=(12,7),sharex=True); 
for a,v in zip(ax,VARS): a.plot(eg.time_utc,eg[v],lw=.8); a.set_ylabel(v)
fig.suptitle(f'Example injected station {sample}'); fig.tight_layout(); fig.savefig(OUT/'figures/example_fault_spans.png',dpi=160); plt.close(fig)
fig,ax=plt.subplots(figsize=(12,4)); pwin=inj[protected]; ax.plot(pwin.time_utc,pwin.temp_c,'.',ms=1); ax.set_title('Protected real-event window sample (no injection)'); fig.tight_layout(); fig.savefig(OUT/'figures/heatwave_no_injection.png',dpi=160); plt.close(fig)
# benchmark report
lines=['# SkyGuard AI benchmark report','', '## Run configuration','', '- 3-hourly cadence; 1 step = 3 h; lags 1/2/4/8; rolling windows 1/8.', '- Grouped 5-fold cross-validation by station; mean and standard deviation reported.', '- LightGBM models capped at 200 trees; LSTM and edge skipped under free-plan scope.', '- Faults injected outside cluster-specific protected windows; native source gaps are not F7 labels.', '', '## Data and injector','', f"- Injected rows: {len(inj):,}; labelled fault observations: {len(labels):,}; stations: {inj.station_id.nunique()}; protected rows: {protected.sum():,}.", f"- Label counts: {metrics['label_counts']}.", f"- F2 duration: 4–24 steps (12–72 h); F5: 4–80 steps (12 h–10 days); F7: 1–8 steps.", '', '## Metrics (fold mean ± std)','', '| Metric | Mean | Std | |\n|---|---:|---:|']
for n in ['precision','recall','f1','t0_f1','iforest_f1','no_T1_f1','no_T2_f1','no_T3_f1']:
 r=metrics['metrics'][n]; lines.append(f"| {n} | {r['mean']:.4f} | {r['std']:.4f} |")
lines += ['', '## Per-class root-cause F1 (OOF)', '', '| Class | Precision | Recall | F1 |','|---|---:|---:|---:|']
for c in CLASSES: r=metrics['per_class'][c]; lines.append(f"| {c} | {r['precision']:.4f} | {r['recall']:.4f} | {r['f1']:.4f} |")
lines += ['', f"Macro-F1 across F1–F9: **{metrics['macro_f1_faults']:.4f}**.", '', '## Neighbour policy', '', 'Primary links use 200 km / 500 m. Stations with fewer than two primary neighbours use sparse links widened to 300 km / 800 m and a 0.7 T3 confidence multiplier. A station with zero links makes T3 abstain and fusion treats T3 as missing.', '', '## Honest limitations', '', 'The benchmark is an injected-data estimate over a small 12-station network with substantial native gaps. Results below specification targets, if any, are reported without tuning them away. The current implementation provides auditable tier features, fusion predictions, and benchmark artifacts; production calibration and SHAP explanations remain follow-on hardening tasks.', '', '## Figures', '', '- `outputs/figures/per_class_f1.png`', '- `outputs/figures/ablation.png`', '- `outputs/figures/confusion_matrix.png`', '- `outputs/figures/example_fault_spans.png`', '- `outputs/figures/heatwave_no_injection.png`']
(OUT/'benchmark_report.md').write_text('\n'.join(lines)+'\n')
# scored stream sample / alerts examples
sample_out=Xraw[['station_id','time_utc']+VARS].copy(); sample_out['p_fault']=all_pred; sample_out['root_cause']=all_cls; sample_out['severity']=pd.cut(sample_out.p_fault,[-1,.3,.5,.75,.9,2],labels=['low','low','medium','high','critical'],ordered=False).astype(str); sample_out['model_version']='fusion-3h-0.1'; sample_out[sample_out.time_utc>=sample_out.time_utc.max()-pd.Timedelta(days=14)].to_parquet(OUT/'scored_stream.parquet',index=False); sample_out.head(100).to_json(OUT/'scored_stream_sample.json',orient='records',date_format='iso')
alerts=[]
for _,r in sample_out.sort_values('p_fault',ascending=False).head(10).iterrows(): alerts.append({'station_id':r.station_id,'time_utc':r.time_utc.isoformat(),'variable':'all','observed':{v:None if pd.isna(r[v]) else float(r[v]) for v in VARS},'p_fault':float(r.p_fault),'severity':r.severity,'root_cause':r.root_cause,'explanation':f"Tier fusion assigned {r.p_fault:.2f} fault probability; inspect {r.root_cause} evidence.",'top_factors':[],'imputed':None,'tier_scores':{},'model_version':'fusion-3h-0.1'})
json.dump(alerts,open(OUT/'alerts_examples.json','w'),indent=2)
print('DONE',len(labels),'labels',metrics['metrics']['f1'])
