from __future__ import annotations
import json, math, time, warnings
from pathlib import Path
from collections import defaultdict
import numpy as np, pandas as pd, yaml
warnings.filterwarnings('ignore')
from sklearn.metrics import precision_recall_fscore_support, f1_score, precision_score, recall_score, confusion_matrix, average_precision_score, roc_auc_score
from sklearn.ensemble import IsolationForest
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold
from lightgbm import LGBMClassifier, LGBMRegressor
import matplotlib.pyplot as plt
import shap
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from skyguard_inject import inject_faults, VARS, CLASSES

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'outputs'; BENCH=ROOT/'data/bench'; CFG=yaml.safe_load(open(ROOT/'config/cadence_3h.yaml'))
OUT.mkdir(exist_ok=True); (OUT/'figures').mkdir(exist_ok=True); BENCH.mkdir(exist_ok=True)
SEED=42; rng=np.random.default_rng(SEED)
clean=pd.read_parquet(ROOT/'data/clean/observations_clean.parquet').sort_values(['station_id','time_utc']).reset_index(drop=True)
clean['station_id']=clean.station_id.astype(str); clean['time_utc']=pd.to_datetime(clean.time_utc,utc=True)
stations=pd.read_csv(ROOT/'stations.csv'); stations['station_id']=stations.station_id.astype(str)
# default benchmark = in_default_set stations (>= 50 % complete-triplet synoptic coverage; 15 stations).
# SKYGUARD_ALL_STATIONS=1 adds the low_coverage stations (35 % floor) and writes to separate folders (comparison only).
import os
if os.environ.get('SKYGUARD_ALL_STATIONS')=='1':
 OUT=ROOT/'outputs/all_stations'; BENCH=ROOT/'data/bench/all_stations'; OUT.mkdir(exist_ok=True); (OUT/'figures').mkdir(exist_ok=True); BENCH.mkdir(exist_ok=True)
else:
 stations=stations[stations.in_default_set.astype(bool)]
clean=clean[clean.station_id.isin(stations.station_id)].reset_index(drop=True)
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
placebo=np.zeros(len(clean),bool); placebo_name=np.full(len(clean),'',dtype=object)
for name,_,a,b in windows:
 for c in ('a','c'):
  m=((clean.cluster==c)&clean.time_utc.between(a+pd.Timedelta(days=182),b+pd.Timedelta(days=182),inclusive='both')).to_numpy(); placebo|=m; placebo_name[m]=f'placebo_{name}_{c}'
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
  out[v+'_clim_z']=(x[v].to_numpy()-mu_by_var[v])/sd_by_var[v]; out[v+'_clim_mu']=mu_by_var[v]
 # missing expected timestamp (all three variables absent) and length of the gap just before this row
 miss=x[VARS].isna().all(axis=1).astype(int); out['is_missing']=miss
 run=miss.groupby([x.station_id,(miss==0).cumsum()]).cumsum(); out['gap_length_before']=run.groupby(x.station_id).shift(1).fillna(0)
 # T2 vapour pressure and cross-variable residuals
 T=x.temp_c; RH=x.rh_pct
 out['vapour_pressure']=(RH/100)*6.112*np.exp(17.62*T/(243.12+T)); out['e_jump']=out.groupby(x.station_id)['vapour_pressure'].diff().abs(); out['e_jump']=out.e_jump.fillna(0)
 out['dewpoint_excess']=(243.12*(np.log(np.clip(RH,1e-3,100)/100)+17.62*T/(243.12+T))/(17.62-(np.log(np.clip(RH,1e-3,100)/100)+17.62*T/(243.12+T)))-T).fillna(0)
 # T3 weighted neighbour deviation, tendency 1 step; sparse confidence
 for v in VARS:
  z3=[]; agr=[]; conf=[]; r3=[]
  dev_map={(str(s),t): (float(val-mu) if pd.notna(val) else np.nan) for s,t,val,mu in zip(x.station_id,x.time_utc,x[v],mu_by_var[v])}
  for sid,t,val in zip(x.station_id,x.time_utc,x[v]):
   sid=str(sid); d0=float(val-mu_by_var[v][len(z3)]) if pd.notna(val) else 0.0; vals=[]; ws=[]
   for dist,elev,oid in neigh.get(sid,[]):
    ov=dev_map.get((str(oid),t),np.nan)
    if pd.notna(ov): vals.append(float(ov)); ws.append(np.exp(-dist/75)*np.exp(-elev/300))
   if vals:
    med=float(np.average(vals,weights=ws)); r3.append(d0-med if pd.notna(val) else np.nan); mad=float(np.median(np.abs(np.array(vals)-med))); z3.append((d0-med)/(1.4826*mad+max(limits.get((sid,v),1),1e-3)))
    agr.append(float(np.mean([np.sign(q)==np.sign(d0) and abs(q)>=.5*abs(d0) for q in vals])) if d0 else 1.0); conf.append(.7 if neigh_kind.get(sid)=='sparse' else 1.0)
   else: z3.append(0.0); agr.append(0.0); conf.append(0.0); r3.append(np.nan)
  out['r3_'+v]=r3; out['z3_'+v]=z3; out['neighbour_agreement_'+v]=agr; out['neighbour_confidence_'+v]=conf
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
# evaluation definitions (README "Evaluation definitions"):
# - F3 drift rows are "pre-detectable" until the injected error reaches the tolerance: weight 0 in training, not scored.
# - native gaps (whole timestamp missing in the source) are comms faults of unknown origin: weight 0, not scored.
# - any missing expected timestamp is flagged F7 by a deterministic T0 gap rule.
TOL={'temp_c':.5,'rh_pct':5.,'mslp_hpa':.5}; PRD={'temp_c':1.,'rh_pct':5.,'mslp_hpa':1.}
assert (Xraw.time_utc.values==clean.time_utc.values).all() and (Xraw.station_id.astype(str).values==clean.station_id.values).all()
native_gap=clean[VARS].isna().all(axis=1).to_numpy(); gap_rule=Xraw[VARS].isna().all(axis=1).to_numpy()
f3err=np.zeros(len(y)); predet=np.zeros(len(y),bool); key_row={(str(s),t.value):i for i,(s,t) in enumerate(zip(Xraw.station_id,Xraw.time_utc))}
for r in labels[labels['class']=='F3'].itertuples():
 i=key_row[(str(r.station_id),pd.Timestamp(r.time_utc).value)]; frac=(r.time_utc-r.start)/(r.end-r.start) if r.end>r.start else 1.0
 f3err[i]=r.magnitude*frac; predet[i]=row_classes[i]=='F3' and f3err[i]<TOL[r.variable]
scored=~predet&~native_gap; weight=scored.astype(float)
print('pre-detectable F3 rows',int(predet.sum()),'of',int((row_classes=='F3').sum()),'; native-gap rows',int(native_gap.sum()),flush=True)
# Train T1 quantile models on clean features (global; models capped 200 trees). Predictions/residuals are features.
_,Xclean=make_features(clean); Xclean=Xclean[feature_cols]
models={}
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
# healthy-period baseline: per station-variable stats of the raw T3 residual on the clean base only
def healthy_stats(res,valid):
 k=clean.station_id.values; r=pd.Series(np.where(valid,res,np.nan))
 return pd.DataFrame({'mean':r.groupby(k).mean(),'std':r.groupby(k).std(),'std56':r.groupby(k).transform(lambda z:z.rolling(56,min_periods=28).mean()).groupby(k).std()})
# T2: pure cross-variable model (spec section 7). Inputs are the OTHER two variables (values, lags, rolling stats,
# climatology anomaly), time, site and the target's station climatology; never the target's own lags or rolling stats.
t2_models={}
for v in VARS:
 other=[q for q in VARS if q!=v]
 cols=[o+sfx for o in other for sfx in ('','_lag1','_lag2','_lag4','_lag8','_roll8_mean','_roll8_std','_diff1','_clim_z','_missing')]+['hour_sin','hour_cos','doy_sin','doy_cos','elevation_m','lat',v+'_clim_mu']
 ok=clean[v].notna().to_numpy()
 for q in [.1,.5,.9]:
  m=LGBMRegressor(objective='quantile',alpha=q,n_estimators=200,max_depth=7,num_leaves=31,learning_rate=.05,verbosity=-1,random_state=SEED)
  m.fit(Xclean.loc[ok,cols],clean.loc[ok,v]); t2_models[(v,q)]=(m,cols); X[f't2_q{int(q*100)}_{v}']=m.predict(X[cols])
 X['z2_'+v]=(Xraw[v]-X[f't2_q50_{v}'])/((X[f't2_q90_{v}']-X[f't2_q10_{v}'])/2.563+1e-3)
# ---------- healthy-period baseline + slow-signal evidence (spec section 8) ----------
# Each station-variable residual (T1: obs - q50, T2: obs - q50, T3: raw neighbour residual) is centred and scaled by that
# station's own mean and std on the clean base (never neighbours', labels or injected values). All windows are causal.
st_key=Xraw.station_id.astype(str).values; st_pos={sid:np.flatnonzero(st_key==sid) for sid in np.unique(st_key)}
kpos=np.zeros(len(X))
for idx in st_pos.values(): kpos[idx]=np.arange(len(idx))
def _grp(a): return pd.Series(a).groupby(st_key,sort=False)
def _roll(a,w,fn='mean',mp=None): return _grp(a).transform(lambda z:getattr(z.rolling(w,min_periods=mp or max(2,w//2)),fn)()).to_numpy()
def _slope(a,w):
 ok=~np.isnan(a); n=_roll(ok.astype(float),w,'sum',1); k=np.where(ok,kpos,0.); r=np.where(ok,a,0.)
 sk,sr,skr,skk=(_roll(q,w,'sum',1) for q in (k,r,k*r,k*k)); den=n*skk-sk*sk
 return np.where((n>=w//2)&(den>0),(n*skr-sk*sr)/np.where(den>0,den,1),np.nan)
def _cusum(a,k=.5,h=5.):
 zc=np.clip(a,-5,5); cp=np.zeros(len(a)); cn=np.zeros(len(a)); alarm=np.zeros(len(a))
 for idx in st_pos.values():
  sp=sn=0.
  for i in idx:
   z=zc[i]
   if z==z: sp=max(0.,sp+z-k); sn=min(0.,sn+z+k)
   cp[i]=sp; cn[i]=sn
   if sp>h: sp=0.; alarm[i]=1  # decision interval h: alarm, then reset
   if sn<-h: sn=0.; alarm[i]=1
 return cp,cn,alarm
def _shape(a,W=56):
 # drift vs offset over the last W steps (causal): R^2 of a straight-line fit vs R^2 of the best single-step fit (split 8..W-8)
 from numpy.lib.stride_tricks import sliding_window_view
 lin=np.zeros(len(a)); stp=np.zeros(len(a)); a0=np.nan_to_num(a); t=np.arange(W)-(W-1)/2; stt=float((t*t).sum()); ks=np.arange(8,W-7)
 for idx in st_pos.values():
  if len(idx)<W: continue
  M=sliding_window_view(a0[idx],W); S=M.sum(1); SS=(M*M).sum(1); sst=SS-S*S/W; ok=sst>1e-9; den=np.where(ok,sst,1)
  b=(M@t)/stt; cs=np.cumsum(M,1)[:,ks-1]; sse=SS[:,None]-cs**2/ks-(S[:,None]-cs)**2/(W-ks)
  lin[idx[W-1:]]=np.where(ok,b*b*stt/den,0); stp[idx[W-1:]]=np.where(ok,1-sse.min(1)/den,0)
 return lin,stp
def _residuals(tier,v,frame,feat):
 if tier in ('t1','t2'):
  m,c=models[v][.5] if tier=='t1' else t2_models[(v,.5)]
  return (frame[v]-m.predict(feat[c])).to_numpy(dtype=float)
 return np.where((feat[v+'_missing']==0)&(feat['neighbour_confidence_'+v]>0),feat['r3_'+v],np.nan).astype(float)
healthy={(tier,v):healthy_stats(_residuals(tier,v,clean,Xclean),clean[v].notna().to_numpy()) for tier in ('t1','t2','t3') for v in VARS}
healthy_t3={v:healthy[('t3',v)] for v in VARS}
for v in VARS:
 for tier in ('t1','t2','t3'):
  hs=healthy[(tier,v)]; mu=pd.Series(st_key).map(hs['mean']).fillna(0).to_numpy(); sd=pd.Series(st_key).map(hs['std']).fillna(hs['std'].median()).clip(lower=1e-3).to_numpy()
  zn=(_residuals(tier,v,Xraw,X)-mu)/sd; pre=f'slow_{tier}_{v}_'
  X[pre+'res']=np.nan_to_num(zn); X[pre+'varratio']=np.nan_to_num(_roll(zn,8,'std',4),nan=1.0)
  if tier=='t2': continue
  for w in (8,24,56): X[pre+f'rmean{w}']=np.nan_to_num(_roll(zn,w))
  X[pre+'level_change']=np.nan_to_num(_roll(zn,8)-_grp(_roll(zn,24)).shift(16).to_numpy())  # mean of last 8 minus mean of steps t-39..t-16
  zc_=(_residuals(tier,v,clean,Xclean)-mu)/sd  # same row order as X (asserted above): healthy-period spread of the slope
  for w in (24,56): X[pre+f'slope{w}_z']=np.nan_to_num(_slope(zn,w)/pd.Series(st_key).map(pd.Series(_slope(zc_,w)).groupby(st_key).std()).clip(lower=1e-6).to_numpy())
  X[pre+'r2lin56'],X[pre+'r2step56']=_shape(zn)
  cp,cn,al=_cusum(zn); X[pre+'cusum_pos']=cp; X[pre+'cusum_neg']=cn; X[pre+'cusum_alarms56']=_roll(al,56,'sum',1)
# score columns
zcols=[c for c in X if c.startswith(('z1_','z2_','z3_'))]; t0cols=[c for c in X if c.endswith(('_range_flag','_step_flag','_zero4'))]
X['t0_hard']=X[[c for c in X if c.endswith('_range_flag')]].max(axis=1); X['t0_soft']=X[[c for c in X if c.endswith(('_step_flag','_zero4'))]].max(axis=1); X['z_max']=X[zcols].abs().max(axis=1)
# avoid nonnumeric raw station id/time; all X numeric
# ---------- grouped 5-fold CV ----------
folds=list(GroupKFold(n_splits=5).split(X,y,groups=groups)); fold_metrics=[]; all_pred=np.zeros(len(y)); all_cls=np.full(len(y),'weather',object); cm_total=np.zeros((10,10),int); fold_feature_importance=[]; fold_of_row=np.zeros(len(y),int); fold_models=[]
# baseline T0 and isolation forest per fold; ablations train fusion with selected evidence blocks
blocks={'no_T1':[c for c in X.columns if c.startswith(('z1_','t1_q','slow_t1_'))],'no_T2':[c for c in X.columns if c.startswith(('z2_','t2_q','slow_t2_'))],'no_T3':[c for c in X.columns if c.startswith(('z3_','neighbour_','slow_t3_'))]}
# fusion heads get no raw calendar features (spec section 8 lists none): protected windows sit at fixed times of year and never
# hold injected faults, so time of year is a shortcut. T1/T2 keep time features as forecasters. *_clim_mu is a month-hour lookup.
CAL_COLS=['hour_sin','hour_cos','doy_sin','doy_cos']+[v+'_clim_mu' for v in VARS]
base_cols=[c for c in X.columns if c not in ['station_code']+CAL_COLS and not c.startswith('r3_')]
def ece(probs,truth,n_bins=10):
 probs=np.asarray(probs,dtype=float); truth=np.asarray(truth,dtype=float); edges=np.linspace(0,1,n_bins+1); total=len(probs); e=0.0
 for i in range(n_bins):
  lo,hi=edges[i],edges[i+1]; m=(probs>=lo)&(probs<hi if i<n_bins-1 else probs<=hi)
  if m.sum()==0: continue
  e+=(m.sum()/total)*abs(probs[m].mean()-truth[m].mean())
 return float(e)
all_pred_raw=np.zeros(len(y)); all_cls_raw=np.full(len(y),'weather',object); cal_flag=np.zeros(len(y),bool); abl_flag={n:np.zeros(len(y),bool) for n in blocks}; abl_cls={n:np.full(len(y),'weather',object) for n in blocks}
# event table (one row per injected event) and per-fold test/train event counts, printed before any training
time_ns=Xraw.time_utc.map(lambda t:t.value).to_numpy(); events=[]
for (sid,var,cls,a,b),_ in labels.groupby(['station_id','variable','class','start','end']):
 pos=st_pos[str(sid)]; rows=pos[(time_ns[pos]>=a.value)&(time_ns[pos]<=b.value)]; rows=rows[~native_gap[rows]]; mag=float(_.magnitude.iloc[0])
 e={'class':cls,'sid':str(sid),'var':var,'mag':mag,'start':a,'rows':rows,'det_rows':rows,'t_det':a.value,'t_prd':a.value}
 if cls=='F3':
  e['det_rows']=rows[~predet[rows]]; e['t_det']=int(time_ns[e['det_rows'][0]]) if len(e['det_rows']) else None
  cross=rows[f3err[rows]>=PRD[var]]; e['t_prd']=int(time_ns[cross[0]]) if len(cross) else None
 h=healthy_t3[var] if var in VARS else None
 if cls=='F3': e['snr_final']=mag/h.at[str(sid),'std56']; e['snr']=float(np.mean(f3err[rows]))/h.at[str(sid),'std56'] if len(rows) else np.nan  # snr = mean-error SNR
 elif cls=='F4': e['snr']=e['snr_final']=mag/h.at[str(sid),'std56']
 elif cls=='F5': e['snr']=e['snr_final']=mag*float(clean.loc[clean.station_id==str(sid),var].std())/h.at[str(sid),'std']
 events.append(e)
fold_of_sid={s:fi for fi,(_,te) in enumerate(folds) for s in np.unique(groups[te])}
ev_counts=pd.DataFrame([{'fold':fold_of_sid[e['sid']]+1,'class':e['class']} for e in events]).value_counts().unstack('class').reindex(columns=CLASSES).fillna(0).astype(int).reindex(range(1,6),fill_value=0)
print('per-fold TEST event counts:\n',ev_counts.to_string(),flush=True)
print('min/max test events per class:',{c:(int(ev_counts[c].min()),int(ev_counts[c].max())) for c in CLASSES},flush=True)
train_min={c:int((ev_counts[c].sum()-ev_counts[c]).min()) for c in CLASSES}; print('min TRAIN events per class:',train_min,flush=True)
if (ev_counts.min()==0).any() or min(train_min.values())<5: raise RuntimeError('fold assignment leaves a class with zero test or <5 train events; reassign stations by event counts')
fold0_model=None; fold0_te=None
for fi,(tr,te) in enumerate(folds):
 # use training only for classifier; labels include weather as negative
 model=LGBMClassifier(n_estimators=200,max_depth=7,num_leaves=31,learning_rate=.05,class_weight='balanced',verbosity=-1,random_state=SEED+fi)
 w_tr=weight[tr]; s=scored[te]; ts=te[s]
 model.fit(X.iloc[tr][base_cols],y[tr],sample_weight=w_tr); p_train=model.predict_proba(X.iloc[tr][base_cols])[:,1]; p=model.predict_proba(X.iloc[te][base_cols])[:,1]
 p_raw=p; all_pred_raw[te]=p_raw  # model output before the deterministic F7 gap rule
 p=np.where(gap_rule[te],1.0,p); p_train=np.where(gap_rule[tr],1.0,p_train); pred=(p>=.5).astype(int); all_pred[te]=p
 if fi==0: fold0_model=model; fold0_te=te
 p_cal=IsotonicRegression(out_of_bounds='clip').fit(p_train[w_tr>0],y[tr][w_tr>0]).predict(p)
 # multiclass over fault classes, excluding weather if no data in train
 mc=LGBMClassifier(n_estimators=200,max_depth=7,num_leaves=31,learning_rate=.05,class_weight='balanced',verbosity=-1,random_state=SEED+fi)
 rc_sel=tr[((y[tr]==1)|((row_classes[tr]=='weather')&protected[tr]))&(w_tr>0)]  # spec section 8: injector-labelled rows + protected-window weather only
 mc.fit(X.iloc[rc_sel][base_cols],row_classes[rc_sel]); mc_pred=mc.predict(X.iloc[te][base_cols]); cp=np.where(gap_rule[te],'F7',np.where(p>=.5,mc_pred,'weather')); all_cls[te]=cp; all_cls_raw[te]=np.where(p_raw>=.5,mc_pred,'weather')  # root cause only given a fault verdict
 print('fold',fi+1,'multiclass train rows',pd.Series(row_classes[rc_sel]).value_counts().to_dict(),flush=True)
 # baselines
 t0_nogap=(X.iloc[te]['t0_hard'].to_numpy()>0)|(X.iloc[te]['t0_soft'].to_numpy()>0)|(X.iloc[te]['z_max'].to_numpy()>6); t0=gap_rule[te]|(X.iloc[te]['t0_hard'].to_numpy()>0)|(X.iloc[te]['t0_soft'].to_numpy()>0)|(X.iloc[te]['z_max'].to_numpy()>6)
 train_prevalence=float(np.clip(y[tr].mean(),1e-3,0.5))
 iso=IsolationForest(n_estimators=100,random_state=SEED+fi,contamination=train_prevalence,n_jobs=-1).fit(X.iloc[tr][[c for c in base_cols if c not in ['t0_hard','t0_soft']].copy()])
 ip=iso.predict(X.iloc[te][[c for c in base_cols if c not in ['t0_hard','t0_soft']]])==-1
 trivial=np.ones(len(te),bool)
 def met(a,b): return {'precision':float(precision_score(a,b,zero_division=0)),'recall':float(recall_score(a,b,zero_division=0)),'f1':float(f1_score(a,b,zero_division=0))}
 fm=met(y[ts],pred[s]); fm.update({'fold':fi+1,'n_test':int(len(ts)),'t0_f1':met(y[ts],t0[s])['f1'],'t0_no_gap_rule_f1':met(y[ts],t0_nogap[s])['f1'],'f1_no_gap_rule':met(y[ts],(p_raw>=.5)[s])['f1'],'iforest_f1':met(y[ts],ip[s])['f1'],'trivial_f1':met(y[ts],trivial[s])['f1'],'ece_raw':ece(p[s],y[ts]),'ece_calibrated':ece(p_cal[s],y[ts])}); fold_metrics.append(fm)
 # per-fold macro-F1 across F1-F9
 fold_class_f1=[f1_score((row_classes[ts]==cls).astype(int),(cp[s]==cls).astype(int),zero_division=0) for cls in CLASSES]
 fold_metrics[-1]['macro_f1']=float(np.mean(fold_class_f1))
 # shortcut check: same binary head WITH raw calendar features, for paired comparison only
 cm_=LGBMClassifier(n_estimators=200,max_depth=7,num_leaves=31,learning_rate=.05,class_weight='balanced',verbosity=-1,random_state=SEED+fi).fit(X.iloc[tr][base_cols+CAL_COLS],y[tr],sample_weight=w_tr)
 cal_flag[te]=gap_rule[te]|(cm_.predict_proba(X.iloc[te][base_cols+CAL_COLS])[:,1]>=.5); fold_metrics[-1]['with_calendar_f1']=float(f1_score(y[ts],cal_flag[ts],zero_division=0))
 # ablation quick models: cols drop the named tier's own feature columns
 for name,drop in blocks.items():
  cols=[c for c in base_cols if c not in drop]
  am=LGBMClassifier(n_estimators=200,max_depth=7,num_leaves=31,learning_rate=.05,class_weight='balanced',verbosity=-1,random_state=SEED+fi)
  am.fit(X.iloc[tr][cols],y[tr],sample_weight=w_tr); ap=np.where(gap_rule[te],1,am.predict(X.iloc[te][cols])); fold_metrics[-1][name+'_f1']=float(f1_score(y[ts],ap[s],zero_division=0))
  amc=LGBMClassifier(n_estimators=200,max_depth=7,num_leaves=31,learning_rate=.05,class_weight='balanced',verbosity=-1,random_state=SEED+fi).fit(X.iloc[rc_sel][cols],row_classes[rc_sel])
  abl_flag[name][te]=ap.astype(bool); abl_cls[name][te]=np.where(gap_rule[te],'F7',np.where(ap==1,amc.predict(X.iloc[te][cols]),'weather'))
 # confusion fault classes for test rows; weather as tenth
 labs=CLASSES+['weather']; cm_total += confusion_matrix(row_classes[ts],all_cls[ts],labels=labs)
 fold_feature_importance.append(pd.Series(model.feature_importances_,index=base_cols)); fold_of_row[te]=fi; fold_models.append(model)
 print('fold',fi+1,'f1',round(fm['f1'],4),flush=True)
# p50/p95 per-observation scoring latency: time predict_proba row by row on fold 0's test set
lat_rows=fold0_te[:500]; lat_times=[]
for idx in lat_rows:
 row=X.iloc[[idx]][base_cols]; t_start=time.perf_counter(); fold0_model.predict_proba(row); lat_times.append((time.perf_counter()-t_start)*1000)
# per-class metrics across folds using out-of-fold predictions (reported as one OOF estimate + fold spread for binary)
metric_names=['f1_no_gap_rule','t0_no_gap_rule_f1','with_calendar_f1','precision','recall','f1','macro_f1','t0_f1','iforest_f1','trivial_f1','ece_raw','ece_calibrated','no_T1_f1','no_T2_f1','no_T3_f1']
metrics={'config':CFG,'dataset':{'rows':int(len(inj)),'stations':int(inj.station_id.nunique()),'labels':int(len(labels)),'protected_rows':int(protected.sum())},'cv':{'folds':5,'grouped_by':'station','fold_station_counts':[int(len(np.unique(groups[te]))) for _,te in folds]},'metrics':{}}
for n in metric_names:
 vals=[r[n] for r in fold_metrics if n in r]; metrics['metrics'][n]={'mean':float(np.mean(vals)),'std':float(np.std(vals,ddof=1) if len(vals)>1 else 0),'folds':vals}
metrics['per_class']={}
for cls in CLASSES:
 yt=(row_classes[scored]==cls).astype(int); yp=(all_cls[scored]==cls).astype(int); metrics['per_class'][cls]={'precision':float(precision_score(yt,yp,zero_division=0)),'recall':float(recall_score(yt,yp,zero_division=0)),'f1':float(f1_score(yt,yp,zero_division=0))}
metrics['macro_f1_faults']=float(np.mean([metrics['per_class'][c]['f1'] for c in CLASSES])); metrics['label_counts']=pd.Series(row_classes).value_counts().to_dict(); metrics['neighbours']={'primary_rule':'<=200 km / <=500 m','sparse_rule':'<=300 km / <=800 m','sparse_stations':[s for s in neigh if neigh_kind[s]=='sparse'],'abstain_stations':[s for s in neigh if not neigh[s]],'links':{s:[{'station_id':o,'distance_km':round(d,1),'elevation_diff_m':round(e,1),'kind':neigh_kind[s]} for d,e,o in neigh[s]] for s in neigh}}
def event_eval(flag,cls_pred):
 res={}
 for c in CLASSES:
  evs=[e for e in events if e['class']==c]; dete=[e for e in evs if len(e['det_rows'])]; det=[]; det_c=[]; delays=[]; delays_prd=[]
  for e in dete:
   r=e['det_rows']; f=flag[r]; det.append(bool(f.any())); det_c.append(bool((f&(cls_pred[r]==c)).any()))
   if f.any():
    t=time_ns[r[np.argmax(f)]]; delays.append((t-e['t_det'])/3.6e12)
    if e['t_prd'] is not None: delays_prd.append((t-e['t_prd'])/3.6e12)
  res[c]={'n_events':len(evs),'n_detectable':len(dete),'recall':float(np.mean(det)) if det else None,'recall_class_correct':float(np.mean(det_c)) if det else None,'median_delay_h':float(np.median(delays)) if delays else None}
  if c=='F3': res[c].update({'median_delay_from_prd_h':float(np.median(delays_prd)) if delays_prd else None,'n_detected_crossing_prd':len(delays_prd)})
 outside=(row_classes=='weather')&~protected&~native_gap
 fl=flag&~native_gap  # native-gap rows are gap-rule F7 alerts of unknown origin: left out of alert counts
 return {'per_class':res,'n_alerts':int(fl.sum()),'alerts_per_1000_outside_events_and_protected':float(1000*fl[outside].sum()/outside.sum()),'share_alerts_inside_event':float(fl[row_classes!='weather'].sum()/max(int(fl.sum()),1))}
variants={'full':(all_pred>=.5,all_cls),**{n:(abl_flag[n],abl_cls[n]) for n in blocks}}
metrics['event_level']={n:event_eval(fl,cl) for n,(fl,cl) in variants.items()}
SNR_BINS=[('<1',0,1),('1-2',1,2),('2-4',2,4),('>4',4,np.inf),('>=3',3,np.inf)]
def snr_curve(flag,cls_pred,key='snr'):
 out={}
 for c in ('F3','F4','F5'):
  out[c]={}
  for b,lo,hi in SNR_BINS:
   evs=[e for e in events if e['class']==c and len(e['det_rows']) and lo<=e.get(key,np.nan)<hi]
   if not evs: out[c][b]={'n_events':0}; continue
   rows=np.concatenate([e['det_rows'] for e in evs])
   out[c][b]={'n_events':len(evs),'event_recall_any':float(np.mean([flag[e['det_rows']].any() for e in evs])),'event_recall_class':float(np.mean([(flag[e['det_rows']]&(cls_pred[e['det_rows']]==c)).any() for e in evs])),
    'row_recall_any':float(flag[rows].mean()),'row_recall_class':float((flag[rows]&(cls_pred[rows]==c)).mean())}
 return out
metrics['snr_curve']={n:snr_curve(fl,cl) for n,(fl,cl) in variants.items()}; metrics['snr_curve_final_magnitude']={'full':snr_curve(*variants['full'],key='snr_final')}
metrics['noise_floor_t3']={v:{'median_std1':float(healthy_t3[v]['std'].median()),'median_std56':float(healthy_t3[v]['std56'].median()),'median_mdb56':float(3*healthy_t3[v]['std56'].median()),'per_station_std56':healthy_t3[v]['std56'].round(4).to_dict()} for v in VARS}
metrics['evaluation_definitions']={'predetectable_f3_rows':int(predet.sum()),'native_gap_rows_excluded':int(native_gap.sum()),'scored_rows':int(scored.sum()),'tolerance':TOL,'prd_threshold':PRD}
metrics['per_class_f1_by_variant']={n:{c:float(f1_score((row_classes[scored]==c).astype(int),(cl[scored]==c).astype(int),zero_division=0)) for c in CLASSES} for n,(fl,cl) in variants.items()}
metrics['ablation_paired']={n:{'diffs_full_minus_ablated':[a-b for a,b in zip(metrics['metrics']['f1']['folds'],metrics['metrics'][n+'_f1']['folds'])]} for n in blocks}
for n,r in metrics['ablation_paired'].items(): d=np.array(r['diffs_full_minus_ablated']); r.update({'mean':float(d.mean()),'std':float(d.std(ddof=1)),'folds_ablated_ge_full':int((d<=0).sum())})
metrics['fold_test_events']={'per_fold':ev_counts.to_dict('index'),'min_max_per_class':{c:[int(ev_counts[c].min()),int(ev_counts[c].max())] for c in CLASSES},'min_train_events_per_class':train_min,'fold_stations':{str(fi+1):sorted(str(s) for s in np.unique(groups[te])) for fi,(_,te) in enumerate(folds)}}
def window_rates(flag):
 clean_rows=(row_classes=='weather')&~native_gap; out={}
 for nm in sorted(set(window_name[window_name!='']))+sorted(set(placebo_name[placebo_name!=''])):
  wm=((window_name==nm)|(placebo_name==nm))&~native_gap; cw=wm&clean_rows; fr=wm&(y==1)&scored
  out[nm]={'n_obs':int(wm.sum()),'clean_alerts_per_1000':float(1000*flag[cw].sum()/max(cw.sum(),1)),'n_fault_rows':int(fr.sum()),'fault_row_recall':float(flag[fr].mean()) if fr.any() else None}
 outside=clean_rows&~protected&~placebo; out['all_other_clean']={'n_obs':int(outside.sum()),'clean_alerts_per_1000':float(1000*flag[outside].sum()/outside.sum())}
 return out
metrics['calendar_check']={'fusion_excludes':CAL_COLS,'placebo_rule':'each protected window shifted +182 days, applied in both clusters; faults are injected there as anywhere else',
 'no_calendar':window_rates(all_pred>=.5),'with_calendar':window_rates(cal_flag),'with_calendar_alerts_per_1000_clean':event_eval(cal_flag,all_cls)['alerts_per_1000_outside_events_and_protected']}
inj_f7=(row_classes=='F7')&~native_gap  # an F7 event can span a native gap; those rows are native gaps, not injected ones
def f7_check(cl):
 pr=cl=='F7'; tp=int((pr&inj_f7).sum())
 return {'injected_gap_recall':float(pr[inj_f7].mean()),'precision_excluding_native_gaps':float(tp/max(int(pr[scored].sum()),1)),'precision_including_native_gaps':float(tp/max(int(pr[scored|native_gap].sum()),1)),'native_gap_rows_called_f7':int(pr[native_gap].sum()),'native_gap_rows':int(native_gap.sum())}
metrics['f7_check']={'with_gap_rule':f7_check(all_cls),'without_gap_rule':f7_check(all_cls_raw)}
# natural extremes on the clean base (rows with no injected fault, not native gaps; inside and outside protected windows).
# Per-station thresholds on clean values; nothing is tuned on these rows.
cb=clean.groupby('station_id'); clean_base=(row_classes=='weather')&~native_gap
ext={'temp_top0.5pct':(clean.temp_c>=cb.temp_c.transform(lambda z:z.quantile(.995))).fillna(False).to_numpy(dtype=bool),'mslp_bottom0.5pct':(clean.mslp_hpa<=cb.mslp_hpa.transform(lambda z:z.quantile(.005))).fillna(False).to_numpy(dtype=bool)}
ch_top=np.zeros(len(clean),bool); ch_bot=np.zeros(len(clean),bool)
for v in VARS:
 d3=cb[v].diff(3); g3=d3.groupby(clean.station_id)
 ch_top|=(d3>=g3.transform(lambda z:z.quantile(.995))).fillna(False).to_numpy(dtype=bool); ch_bot|=(d3<=g3.transform(lambda z:z.quantile(.005))).fillna(False).to_numpy(dtype=bool)
ext['change3_top0.5pct_any_var']=ch_top; ext['change3_bottom0.5pct_any_var']=ch_bot
ext['any_extreme']=ext['temp_top0.5pct']|ext['mslp_bottom0.5pct']|ch_top|ch_bot; ext['all_clean']=np.ones(len(clean),bool)
def ext_rates(flag):
 out={}
 for k,m in ext.items():
  m=m&clean_base; r=[1000*flag[te][m[te]].mean() for _,te in folds if m[te].any()]
  out[k]={'n_rows':int(m.sum()),'alerts_per_1000_fold_mean':float(np.mean(r)),'fold_std':float(np.std(r,ddof=1))}
 for k in out: out[k]['ratio_to_clean']=out[k]['alerts_per_1000_fold_mean']/max(out['all_clean']['alerts_per_1000_fold_mean'],1e-9)
 return out
metrics['natural_extremes']={'no_calendar':ext_rates(all_pred>=.5),'with_calendar':ext_rates(cal_flag),**{n:ext_rates(abl_flag[n]) for n in blocks}}
metrics['confusion_matrix']={'labels':CLASSES+['weather'],'counts':cm_total.tolist()}
metrics['latency_ms']={'p50':float(np.percentile(lat_times,50)),'p95':float(np.percentile(lat_times,95)),'n_timed':len(lat_times)}
metrics['false_alarms_per_1000_by_window']={}
for wname in ['heatwave_a','biparjoy_a','monsoon_c']:
 wm=(window_name==wname)&~native_gap; n_obs=int(wm.sum())
 metrics['false_alarms_per_1000_by_window'][wname]={'n_obs':n_obs,'per_1000':float(1000*np.sum(all_pred[wm]>=.5)/n_obs) if n_obs else None}
with open(OUT/'metrics.json','w') as f: json.dump(metrics,f,indent=2,allow_nan=False,default=lambda x: x.item() if isinstance(x,np.generic) else str(x))
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
fig,ax=plt.subplots(figsize=(12,4)); pwin=inj[protected]; ax.plot(pwin.time_utc,pwin.temp_c,'.',ms=1,color='#1677b8',label='temp_c')
alert_mask=protected&(all_pred>=.5); n_alerts=int(alert_mask.sum())
if n_alerts: ax.plot(inj.loc[alert_mask,'time_utc'],inj.loc[alert_mask,'temp_c'],'x',ms=7,color='#e15759',label='alert (P(fault)≥0.5)')
ax.legend(loc='upper right',fontsize=8); ax.set_title(f'Protected real-event window sample (no injection) — {n_alerts} alerts overlaid'); fig.tight_layout(); fig.savefig(OUT/'figures/heatwave_no_injection.png',dpi=160); plt.close(fig)
# benchmark report
lines=['# SkyGuard AI benchmark report','', '## Run configuration','', '- 3-hourly cadence; 1 step = 3 h; lags 1/2/4/8; rolling windows 1/8.', '- Grouped 5-fold cross-validation by station; mean and standard deviation reported.', '- LightGBM models capped at 200 trees; LSTM and edge skipped under free-plan scope.', '- Faults injected outside cluster-specific protected windows; native source gaps are not F7 labels.', '', '## Data and injector','', f"- Injected rows: {len(inj):,}; labelled fault observations: {len(labels):,}; stations: {inj.station_id.nunique()}; protected rows: {protected.sum():,}.", f"- Label counts: {metrics['label_counts']}.", '- Injector samples by event count (min per class: F1 60, F2 40, F3 24, F4 30, F5 30, F6 30, F7 30, F8 60, F9 30; spread over >=8 stations). Durations in steps (1 step = 3 h): F1/F8 1, F2 4–24, F3 56–112, F4 8–80, F5 4–80, F6 4–80, F7 1–8, F9 1–16.', '- **Documented deviation:** F3 drift lasts 7–14 days (56–112 steps), shorter than the spec\'s 7–45 days, so 24 drift events fit in the coverage budget. F9 is back to spec (1–16 steps = 1–48 h). F3 final error follows spec section 6: 0.5–3 °C, 3–15 % RH, 0.5–3 hPa, variable T 45 % / RH 45 % / P 10 % (RH was 0.5–3 % before fix/detectability).', '- Root-cause head is trained only on injector-labelled rows plus protected-window weather rows (spec section 8); a row receives a root cause only if the binary head flags it (P(fault) >= 0.5), otherwise "weather".', '', '## Metrics (fold mean ± std)','', '| Metric | Mean | Std | |\n|---|---:|---:|']
for n in ['precision','recall','f1','macro_f1','t0_f1','iforest_f1','trivial_f1','ece_raw','ece_calibrated','no_T1_f1','no_T2_f1','no_T3_f1']:
 r=metrics['metrics'][n]; lines.append(f"| {n} | {r['mean']:.4f} | {r['std']:.4f} |")
lines += ['', '## Per-class root-cause F1 (OOF)', '', '| Class | Precision | Recall | F1 |','|---|---:|---:|---:|']
for c in CLASSES: r=metrics['per_class'][c]; lines.append(f"| {c} | {r['precision']:.4f} | {r['recall']:.4f} | {r['f1']:.4f} |")
lines += ['', f"Macro-F1 across F1–F9 (OOF): **{metrics['macro_f1_faults']:.4f}**.", '', '## Scoring latency', '', f"- p50: {metrics['latency_ms']['p50']:.3f} ms; p95: {metrics['latency_ms']['p95']:.3f} ms (timed row-by-row on fold 0's test set, n={metrics['latency_ms']['n_timed']}).", '', '## False alarms in protected windows (P(fault) >= 0.5)', '', '| Window | Observations | False alarms / 1,000 |', '|---|---:|---:|']
for wname,wr in metrics['false_alarms_per_1000_by_window'].items():
 lines.append(f"| {wname} | {wr['n_obs']:,} | {wr['per_1000']:.2f} |" if wr['per_1000'] is not None else f"| {wname} | 0 | n/a |")
ev=metrics['event_level']
fmt=lambda x,f='.3f': 'n/a' if x is None else format(x,f)
lines += ['', '## Evaluation definitions', '', f"- **F3 pre-detectable rows.** A drift row counts as a fault (training positive and scored row) only from the first step where the injected error reaches the tolerance (0.5 °C, 5 % RH, 0.5 hPa). Earlier rows ({predet.sum():,}) get sample weight 0 and are excluded from row-level scoring; the event stays in the event table. F3 event detection only counts flags from the tolerance crossing onward. Delay is reported from the tolerance crossing and from the PRD crossing (1 °C, 5 % RH, 1 hPa); a negative PRD delay means the drift was flagged before it reached the PRD threshold.", f"- **F7 and native gaps.** A missing expected timestamp is a comms fault whatever its cause, and the label file cannot separate injected from native gaps. A deterministic T0 gap rule flags every missing timestamp as F7 (P(fault) = 1). F7 recall is measured on injected gaps; the {native_gap.sum():,} native-gap rows are excluded from all row-level scoring (so from the F7 precision denominator), from the clean-step alert rate and from the protected-window false-alarm rates. F7 recall is therefore 1.0 by construction and says nothing about the learned model.", '- **SNR.** Detectability tables use MEAN-ERROR SNR: F3 = mean injected error over the event (about half the final magnitude for a ramp) / std of the 56-step mean of the station-variable healthy T3 residual; F4 = offset / same std. A second table uses final-magnitude SNR for F3. F5: injected noise std / 1-step std of the healthy T3 residual.']
lines += ['', '## Event-level detection (alongside row-level metrics)', '', 'An event counts as detected if any row inside its detectable window has P(fault) >= 0.5. Delay = hours from the start of the detectable window to the first flagged row (detected events only).', '', '| Class | Events | Detectable | Recall | Recall (class correct) | Median delay (h) |', '|---|---:|---:|---:|---:|---:|']
for c in CLASSES: r=ev['full']['per_class'][c]; lines.append(f"| {c} | {r['n_events']} | {r['n_detectable']} | {fmt(r['recall'])} | {fmt(r['recall_class_correct'])} | {fmt(r['median_delay_h'],'.1f')} |")
r=ev['full']['per_class']['F3']; lines.append(f"\nF3 median delay from PRD crossing: {fmt(r['median_delay_from_prd_h'],'.1f')} h over {r['n_detected_crossing_prd']} detected events that reach the PRD threshold.")
lines += ['', '## Detectability curve (recall by MEAN-ERROR SNR bin, full model)', '', '| Class | SNR bin | Events | Event recall (any class) | Event recall (class correct) | Row recall (any class) | Row recall (class correct) |', '|---|---|---:|---:|---:|---:|---:|']
for c,bins in metrics['snr_curve']['full'].items():
 for b,r in bins.items(): lines.append(f"| {c} | {b} | {r['n_events']} | {fmt(r.get('event_recall_any'))} | {fmt(r.get('event_recall_class'))} | {fmt(r.get('row_recall_any'))} | {fmt(r.get('row_recall_class'))} |")
lines += ['', '### Same, F3 by FINAL-MAGNITUDE SNR', '', '| Class | SNR bin | Events | Event recall (any class) | Event recall (class correct) | Row recall (any class) | Row recall (class correct) |', '|---|---|---:|---:|---:|---:|---:|']
for b,r in metrics['snr_curve_final_magnitude']['full']['F3'].items(): lines.append(f"| F3 | {b} | {r['n_events']} | {fmt(r.get('event_recall_any'))} | {fmt(r.get('event_recall_class'))} | {fmt(r.get('row_recall_any'))} | {fmt(r.get('row_recall_class'))} |")
nf=metrics['noise_floor_t3']; lines += ['', 'Healthy T3 noise floor (median over stations; 3 sigma of the 56-step mean): '+'; '.join(f"{v} {nf[v]['median_mdb56']:.2f}" for v in VARS)+'.']
lines += ['', '| Variant | Alerts | Alerts / 1,000 clean steps (outside events, protected windows and native gaps) | Share of alerts inside an injected event |', '|---|---:|---:|---:|']
for n,r in ev.items(): lines.append(f"| {n} | {r['n_alerts']:,} | {r['alerts_per_1000_outside_events_and_protected']:.2f} | {r['share_alerts_inside_event']:.3f} |")
lines += ['', '## Ablation (tier columns removed, heads retrained)', '', '| Tier removed | Paired per-fold F1 diff (full − ablated) | Mean | Std | Folds ablated >= full |', '|---|---|---:|---:|---:|']
for n,r in metrics['ablation_paired'].items(): lines.append(f"| {n} | {', '.join(format(x,'+.4f') for x in r['diffs_full_minus_ablated'])} | {r['mean']:+.4f} | {r['std']:.4f} | {r['folds_ablated_ge_full']}/5 |")
lines += ['', '| Variant | '+' | '.join(CLASSES)+' |','|---|'+'---:|'*len(CLASSES)]
for n,r in metrics['per_class_f1_by_variant'].items(): lines.append(f"| {n} F1 | "+' | '.join(f'{r[c]:.3f}' for c in CLASSES)+' |')
for n,r in ev.items(): lines.append(f"| {n} event recall | "+' | '.join(fmt(r['per_class'][c]['recall']) for c in CLASSES)+' |')
for n,r in ev.items(): lines.append(f"| {n} class-correct event recall | "+' | '.join(fmt(r['per_class'][c]['recall_class_correct']) for c in CLASSES)+' |')
M=metrics['metrics']; ms=lambda k:f"{M[k]['mean']:.4f} ± {M[k]['std']:.4f}"
lines += ['', '## Baselines on the current benchmark (same evaluation definitions, fold mean ± std)', '', 'All rows below are scored on the same rows: pre-detectable F3 rows and native gaps excluded.', '', '| Detector | Binary F1 |', '|---|---:|',
 f"| Fusion (with F7 gap rule) | {ms('f1')} |", f"| Fusion without the F7 gap rule | {ms('f1_no_gap_rule')} |", f"| WMO rules only (T0, incl. gap rule) | {ms('t0_f1')} |", f"| WMO rules only (T0, no gap rule) | {ms('t0_no_gap_rule_f1')} |",
 f"| Isolation Forest (contamination = training-fold prevalence) | {ms('iforest_f1')} |", f"| Always fault | {ms('trivial_f1')} |"]
lines += ['', '| F7 | Injected-gap recall | Precision (native gaps excluded) | Precision (native gaps counted as negatives) | Native-gap rows called F7 |', '|---|---:|---:|---:|---:|']
for k,r in metrics['f7_check'].items(): lines.append(f"| {k} | {r['injected_gap_recall']:.3f} | {r['precision_excluding_native_gaps']:.3f} | {r['precision_including_native_gaps']:.3f} | {r['native_gap_rows_called_f7']:,} / {r['native_gap_rows']:,} |")
lines += ['', '## Calendar shortcut check and placebo windows', '', f"Fusion heads exclude {CAL_COLS}. The with-calendar binary head is refit per fold for comparison only. Placebo windows = each protected window shifted +182 days, in both clusters (faults occur there).", '', '| Window | Obs | Clean alerts/1,000 (no calendar) | Clean alerts/1,000 (with calendar) | Fault rows | Fault-row recall (no calendar) | Fault-row recall (with calendar) |', '|---|---:|---:|---:|---:|---:|---:|']
cc=metrics['calendar_check']
for nm,r in cc['no_calendar'].items(): r2=cc['with_calendar'][nm]; lines.append(f"| {nm} | {r['n_obs']:,} | {r['clean_alerts_per_1000']:.2f} | {r2['clean_alerts_per_1000']:.2f} | {r.get('n_fault_rows','')} | {fmt(r.get('fault_row_recall'))} | {fmt(r2.get('fault_row_recall'))} |")
lines += ['', '## Natural extremes on clean rows (test folds, fold mean ± std, alerts per 1,000)', '', 'Per-station top 0.5 % temp, bottom 0.5 % MSLP, top/bottom 0.5 % 3-step change in any variable; rows with no injected fault and no native gap. Tier columns show the rate when that tier is removed (which tier drives extreme alerts).', '', '| Group | Rows | No calendar (default) | With calendar | Ratio to clean (default) | No T1 | No T2 | No T3 |', '|---|---:|---:|---:|---:|---:|---:|---:|']
ne=metrics['natural_extremes']
for k,r in ne['no_calendar'].items(): lines.append(f"| {k} | {r['n_rows']:,} | {r['alerts_per_1000_fold_mean']:.1f} ± {r['fold_std']:.1f} | {ne['with_calendar'][k]['alerts_per_1000_fold_mean']:.1f} | {r['ratio_to_clean']:.2f} | "+' | '.join(f"{ne[n][k]['alerts_per_1000_fold_mean']:.1f}" for n in blocks)+' |')
ft=metrics['fold_test_events']; lines += ['', '## Fold event counts', '', f"Min/max test events per class across folds: {ft['min_max_per_class']}. Min train events per class: {ft['min_train_events_per_class']}. Fold stations (GroupKFold default assignment, no reassignment needed): {ft['fold_stations']}."]
lines += ['', '## Neighbour policy', '', 'Primary links use 200 km / 500 m. Stations with fewer than two primary neighbours use sparse links widened to 300 km / 800 m and a 0.7 T3 confidence multiplier. A station with zero links makes T3 abstain and fusion treats T3 as missing.', '', '## Honest limitations', '', f'The benchmark is an injected-data estimate over a small station network ({inj.station_id.nunique()} stations) with substantial native gaps. Results below specification targets, if any, are reported without tuning them away.', '', '## Figures', '', '- `outputs/figures/per_class_f1.png`', '- `outputs/figures/ablation.png`', '- `outputs/figures/confusion_matrix.png`', '- `outputs/figures/example_fault_spans.png`', '- `outputs/figures/heatwave_no_injection.png`']
(OUT/'benchmark_report.md').write_text('\n'.join(lines)+'\n')
# scored stream sample / alerts examples
# ---------- explanations (SHAP) and imputation (T2/T3 blend, T1 fallback) ----------
inj_lookup={v:{(str(s),t): val for s,t,val in zip(Xraw.station_id,Xraw.time_utc,Xraw[v])} for v in VARS}
row_idx_by_key={(str(s),t): i for i,(s,t) in enumerate(zip(Xraw.station_id,Xraw.time_utc))}
FEATURE_TEMPLATES=[
 (lambda f: f=='t0_hard', lambda f,val,v: 'a hard physical-range or persistence rule fired'),
 (lambda f: f=='t0_soft', lambda f,val,v: 'a soft step-limit or frozen-value rule fired'),
 (lambda f: f.startswith('z1_'), lambda f,val,v: f"{f[3:]} deviates {val:.1f} sigma from this station's own recent history"),
 (lambda f: f.startswith('z2_'), lambda f,val,v: f"{f[3:]} is inconsistent with the station's other variables (z={val:.1f})"),
 (lambda f: f.startswith('z3_'), lambda f,val,v: f"{f[3:]} disagrees with neighbouring stations (z={val:.1f})"),
 (lambda f: f.startswith('neighbour_agreement_'), lambda f,val,v: f"neighbours mostly disagree on {f[len('neighbour_agreement_'):]}"),
 (lambda f: f.endswith('_zero4'), lambda f,val,v: f"{f[:-6]} has been unchanged for 4+ steps"),
 (lambda f: f.startswith('slow_'), lambda f,val,v: f"{f[5:]} shows a sustained bias, drift or variance change ({val:.2f})"),
 (lambda f: f=='is_missing', lambda f,val,v: 'the expected timestamp is missing (gap rule, F7)'),
 (lambda f: f=='gap_length_before', lambda f,val,v: f'a {val:.0f}-step gap just ended'),
 (lambda f: f.endswith('_missing'), lambda f,val,v: f"{f[:-8]} is missing"),
]
def describe_feature(f,val):
 for cond,tmpl in FEATURE_TEMPLATES:
  if cond(f): return tmpl(f,val,None)
 return f"{f}={val:.2f} contributed"
explainer_cache={}
def get_explainer(fi):
 if fi not in explainer_cache: explainer_cache[fi]=shap.TreeExplainer(fold_models[fi])
 return explainer_cache[fi]
def explain_rows(idxs):
 out={}
 idxs=np.asarray(idxs)
 for fi in np.unique(fold_of_row[idxs]):
  sub=idxs[fold_of_row[idxs]==fi]; ex=get_explainer(int(fi)); rows=X.iloc[sub][base_cols]
  sv=ex.shap_values(rows)
  if isinstance(sv,list): sv=sv[1] if len(sv)>1 else sv[0]
  sv=np.asarray(sv)
  for k,i in enumerate(sub):
   order=np.argsort(sv[k])[::-1]; top=[]
   for oi in order:
    if sv[k,oi]<=0 or len(top)>=3: break
    f=base_cols[oi]; top.append({'feature':f,'shap':float(sv[k,oi])})
   phrases=[describe_feature(t['feature'],float(rows.iloc[k][t['feature']])) for t in top]
   explanation=('; '.join(phrases)+f'. Root cause: {all_cls[i]}.') if phrases else f'Fusion model flagged this row (root cause: {all_cls[i]}); no single dominant positive factor.'
   out[i]=(explanation,top)
 return out
def impute_value(sid,t,v):
 sid=str(sid); month=int(t.month); hour=int(t.hour)
 mu,sd=clim_lookup.get((sid,v,month,hour),(0.0,1.0)); v2,var2=mu,max(sd**2,1e-6)
 vals=[]; ws=[]
 for dist,elev,oid in neigh.get(sid,[]):
  ov=inj_lookup[v].get((str(oid),t))
  if ov is not None and pd.notna(ov):
   om,osd=clim_lookup.get((str(oid),v,month,hour),(0.0,1.0)); vals.append(ov-om); ws.append(np.exp(-dist/75)*np.exp(-elev/300))
 idx=row_idx_by_key.get((sid,t))
 q10=q50=q90=None
 if idx is not None:
  q10=float(X.at[idx,f't1_q10_{v}']); q50=float(X.at[idx,f't1_q50_{v}']); q90=float(X.at[idx,f't1_q90_{v}'])
 if vals:
  med=float(np.average(vals,weights=ws)); mad=float(np.median(np.abs(np.array(vals)-med))); v3=mu+med; var3=max((1.4826*mad)**2,1e-6)
  wsum=1/var2+1/var3; value=(v2/var2+v3/var3)/wsum; sd_b=math.sqrt(1/wsum)
  return {'value':round(value,3),'low':round(value-1.2816*sd_b,3),'high':round(value+1.2816*sd_b,3),'method':'blend_t2_t3'}
 if q50 is not None:
  return {'value':round(q50,3),'low':round(q10,3),'high':round(q90,3),'method':'t1_fallback'}
 return {'value':round(v2,3),'low':round(v2-1.2816*math.sqrt(var2),3),'high':round(v2+1.2816*math.sqrt(var2),3),'method':'t2_fallback'}
def _safe_round(x,nd=3):
 x=float(x); return None if (math.isnan(x) or math.isinf(x)) else round(x,nd)
def tier_scores_for(i):
 return {'t0':['hard'] if X.at[i,'t0_hard']>0 else (['soft'] if X.at[i,'t0_soft']>0 else []),
         **{f'z1_{v}':_safe_round(X.at[i,f'z1_{v}']) for v in VARS},
         **{f'z2_{v}':_safe_round(X.at[i,f'z2_{v}']) for v in VARS},
         **{f'z3_{v}':_safe_round(X.at[i,f'z3_{v}']) for v in VARS}}

sample_out=Xraw[['station_id','time_utc']+VARS].copy(); sample_out['p_fault']=all_pred; sample_out['root_cause']=all_cls; sample_out['severity']=pd.cut(sample_out.p_fault,[-1,.3,.5,.75,.9,2],labels=['low','low','medium','high','critical'],ordered=False).astype(str); sample_out['model_version']='fusion-3h-0.1'
stream=sample_out[sample_out.time_utc>=sample_out.time_utc.max()-pd.Timedelta(days=14)].copy()
stream_idx=stream.index.to_numpy()
expl_by_idx=explain_rows(stream_idx)
stream['explanation']=[expl_by_idx[i][0] for i in stream_idx]
stream['top_factors']=[expl_by_idx[i][1] for i in stream_idx]
stream['tier_scores']=[tier_scores_for(i) for i in stream_idx]
def _primary_var(rc,i):
 if rc=='weather': return None
 best_v,best_z=VARS[0],-1.0
 for v in VARS:
  z=max(abs(float(X.at[i,f'z1_{v}'])),abs(float(X.at[i,f'z2_{v}'])),abs(float(X.at[i,f'z3_{v}'])))
  if z>best_z: best_z=z; best_v=v
 return best_v
def _imputed_or_none(i):
 v=_primary_var(stream.at[i,'root_cause'],i)
 return impute_value(stream.at[i,'station_id'],stream.at[i,'time_utc'],v) if v else None
stream['imputed']=[_imputed_or_none(i) for i in stream_idx]
stream.to_parquet(OUT/'scored_stream.parquet',index=False)
stream.head(100).to_json(OUT/'scored_stream_sample.json',orient='records',date_format='iso')

# alerts: pick diverse examples from the FULL dataset (not just the 14-day stream
# tail, which is too short to contain most fault classes), one per available
# predicted class first, then fill remaining slots by highest p_fault.
def pick_diverse_alerts(pool,n=10):
 selected=[]; seen=set()
 for c in CLASSES:
  if len(selected)>=n: break
  cand=pool[pool.root_cause==c].sort_values('p_fault',ascending=False).head(1)
  if len(cand) and cand.index[0] not in seen: selected.append(cand.index[0]); seen.add(cand.index[0])
 for idx in pool.sort_values('p_fault',ascending=False).index:
  if len(selected)>=n: break
  if idx not in seen: selected.append(idx); seen.add(idx)
 return pool.loc[selected]
alert_rows=pick_diverse_alerts(sample_out,n=10)
alert_idx=alert_rows.index.to_numpy()
expl_alert=explain_rows(alert_idx)
alerts=[]
for i in alert_idx:
 r=sample_out.loc[i]; v=_primary_var(r.root_cause,i); imputed=impute_value(r.station_id,r.time_utc,v) if v else None
 explanation,top_factors=expl_alert[i]
 alerts.append({'station_id':r.station_id,'time_utc':r.time_utc.isoformat(),'variable':v or 'all','observed':{vv:None if pd.isna(r[vv]) else float(r[vv]) for vv in VARS},'p_fault':float(r.p_fault),'severity':r.severity,'root_cause':r.root_cause,'explanation':explanation,'top_factors':top_factors,'imputed':imputed,'tier_scores':tier_scores_for(i),'model_version':'fusion-3h-0.1'})
json.dump(alerts,open(OUT/'alerts_examples.json','w'),indent=2,allow_nan=False)
print('DONE',len(labels),'labels',metrics['metrics']['f1'])
