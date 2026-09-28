from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import numpy as np
import pandas as pd
from meteostat import Stations, Hourly

ROOT=Path('/home/ubuntu/skyguard')
START=pd.Timestamp('2023-01-01T00:00:00Z')
END=pd.Timestamp('2025-12-31T23:00:00Z')
SYN=pd.date_range(START,END,freq='3h')

def dist(lat,lon,lat0,lon0):
    r=6371.0088;p1=np.radians(lat);p2=np.radians(lat0);dp=np.radians(lat-lat0);dl=np.radians(lon-lon0)
    a=np.sin(dp/2)**2+np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
    return 2*r*np.arcsin(np.sqrt(a))

catalog=Stations().fetch()
areas=[('a',28.61,77.21),('c',18.52,73.86)]
parts=[]
for cluster,lat,lon in areas:
    x=catalog.copy()
    x['distance_km']=dist(x.latitude.astype(float),x.longitude.astype(float),lat,lon)
    x=x[(x.country=='IN')&(x.distance_km<=250)].copy()
    x['cluster']=cluster
    x['station_id']=x.index.astype(str)
    x['station_kind']=np.where(x.icao.notna(),'airport/ICAO',np.where(x.wmo.notna(),'WMO','other'))
    parts.append(x)
candidates=pd.concat(parts).reset_index(drop=True)


def one(row):
    sid=row.station_id
    result={
      'station_id':sid,'name':str(row['name']),'cluster':row.cluster,
      'latitude':float(row.latitude),'longitude':float(row.longitude),'elevation_m':None if pd.isna(row.elevation) else float(row.elevation),
      'distance_km':round(float(row.distance_km),2),'station_kind':row.station_kind,
      'wmo':None if pd.isna(row.wmo) else str(row.wmo),'icao':None if pd.isna(row.icao) else str(row.icao),
      'status':'ok'
    }
    try:
        df=Hourly(sid,START.to_pydatetime().replace(tzinfo=None),END.to_pydatetime().replace(tzinfo=None),model=False).fetch()
        df.index=pd.to_datetime(df.index,utc=True)
        df=df.rename(columns={'temp':'temp_c','pres':'mslp_hpa','rhum':'rh_pct'})
        df=df[[c for c in ['temp_c','mslp_hpa','rh_pct'] if c in df.columns]]
        syn=df.reindex(SYN)
        for c in ['temp_c','mslp_hpa','rh_pct']:
            if c not in syn: syn[c]=np.nan
            result[c+'_synoptic_coverage_pct']=round(100*syn[c].notna().mean(),4)
        result['complete_triplet_synoptic_coverage_pct']=round(100*syn[['temp_c','mslp_hpa','rh_pct']].notna().all(axis=1).mean(),4)
        result['raw_rows_returned']=int(len(df))
        result['raw_complete_rows']=int(df[['temp_c','mslp_hpa','rh_pct']].notna().all(axis=1).sum())
        deltas=df.index.to_series().diff().dt.total_seconds().div(3600).dropna()
        counts=deltas[deltas>0].round().astype(int).value_counts()
        if len(counts):
            mode=int(counts.index[0]); share=float(counts.iloc[0]/len(deltas))
            result['modal_interval_hours']=mode; result['modal_interval_share_pct']=round(100*share,4)
            result['native_reporting_interval']='hourly' if mode==1 and share>=.75 else ('3-hourly' if mode==3 and share>=.75 else 'mixed')
        else:
            result['modal_interval_hours']=None; result['modal_interval_share_pct']=0; result['native_reporting_interval']='unknown'
        result['first_raw_observation']=None if df.empty else df.index.min().isoformat()
        result['last_raw_observation']=None if df.empty else df.index.max().isoformat()
    except Exception as e:
        result['status']='error'; result['error']=repr(e)
    return result

results=[]
with ThreadPoolExecutor(max_workers=6) as pool:
    futures={pool.submit(one,row):i for i,(_,row) in enumerate(candidates.iterrows())}
    for n,f in enumerate(as_completed(futures),1):
        results.append(f.result())
        print(f'completed {n}/{len(futures)}',flush=True)
results=sorted(results,key=lambda x:(x['cluster'],-float(x.get('complete_triplet_synoptic_coverage_pct',-1)),x['distance_km']))
out=pd.DataFrame(results)
out.to_csv(ROOT/'data/clean/candidate_synoptic_coverage.csv',index=False)
with open(ROOT/'data/clean/candidate_scan_summary.json','w') as f:
    json.dump({'candidate_count':len(results),'by_cluster':out.groupby('cluster').size().to_dict(),'source':'Meteostat Python 1.7.6 model=False','interpolation_applied':False,'synoptic_grid_start':START.isoformat(),'synoptic_grid_end':END.isoformat(),'synoptic_hours':'00,03,...,21 UTC'},f,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else str(x))
print(out[['cluster','station_id','name','station_kind','distance_km','temp_c_synoptic_coverage_pct','mslp_hpa_synoptic_coverage_pct','rh_pct_synoptic_coverage_pct','complete_triplet_synoptic_coverage_pct','native_reporting_interval']].to_string(index=False))
