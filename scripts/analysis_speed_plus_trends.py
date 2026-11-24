import sys; sys.path.insert(0,'/home/claude/racingtrends')
import pandas as pd, numpy as np
from trends.speed import prior
from trends.model import fit_clogit, race_softmax
ex=pd.read_pickle('/tmp/extras_runners.pkl')[['race_id','horse_key']]
ren=pd.read_pickle('/tmp/extras_renewals.pkl')
sc={}; mc={}
for rid,s,m in zip(ren.race_id,ren.scores,ren.max_core):
    for row,v in s.items(): sc[row]=v
    mc[rid]=m
ex['score']=ex.index.map(sc); ex=ex[ex.score.notna()]
ex['max']=ex.race_id.map(mc)+4
sp=prior(pd.read_pickle('/tmp/speed_runners.pkl'))
D=sp.merge(ex.drop_duplicates(['race_id','horse_key']),on=['race_id','horse_key'],how='inner')
D=D[(D.date>='2019-01-01')&D.bsp.notna()&(D.cover>=0.7)].copy()
D['period']=np.where(D.date<'2024-01-01','2019-23','2024-26')
D['pl_b']=np.where(D.win==1,(D.bsp-1)*.95,-1); D['pl_m']=np.where(D.morning.notna()&(D.morning>1),np.where(D.win==1,(D.morning-1)*.95,-1),np.nan)
def rep(mask,label):
    out=[]
    for p in ('2019-23','2024-26'):
        q=D[mask&(D.period==p)]
        out.append(f"{p}: {len(q):5} bets, win {100*q.win.mean():4.1f}%, BSP {100*q.pl_b.mean():+5.1f}%, morning {100*q.pl_m.mean():+5.1f}%")
    print(f"{label:58} "+' | '.join(out))
g=D.groupby('race_id')['score']; top=D.score==g.transform('max'); uniq=top&(D[top].groupby('race_id')['score'].transform('size').reindex(D.index)==1)
pick=uniq&(D.score>=5)
print('A) Trend top pick filtered by speed')
rep(pick,'trend top pick (current, score >=5)')
rep(pick&(D.best3_rank==1),'  + top on speed (best of last 3)')
rep(pick&(D.best3_rank<=2),'  + top 2 on speed')
rep(pick&(D.best3_rank>=4),'  but 4th or worse on speed')
rep(pick&(D.best3_rank==1)&(D.last_fig_rank<=2),'  + top on best3 and top 2 last time')
print('B) Combined score: trend score + speed points (3 top, 2 second, 1 third on best-of-3)')
D['spd']=np.select([D.best3_rank==1,D.best3_rank==2,D.best3_rank==3],[3,2,1],0)
D['comb']=D.score+D.spd
gc=D.groupby('race_id')['comb']; t2=D.comb==gc.transform('max'); u2=t2&(D[t2].groupby('race_id')['comb'].transform('size').reindex(D.index)==1)
for th in (6,7,8,9): rep(u2&(D.comb>=th),f'combined clear top, >= {th}')
print('C) Speed top pick when it also fits the trends')
sp1=D.best3_rank==1
for th in (3,4,5): rep(sp1&(D.score>=th),f'top on speed and trend score >= {th}')
print('D) Model: morning market + speed + trend score')
M=D[D.morning.notna()&(D.morning>1)].copy(); M=M[M.groupby('race_id').race_id.transform('size')>=4].sort_values('race_id').reset_index(drop=True)
p=1/M.morning; M['lp']=np.log(p/p.groupby(M.race_id).transform('sum'))
for c in ('best3_gap','avg3_gap'): M[c+'_z']=M[c].fillna(M[c].groupby(M.race_id).transform('min')).fillna(-40).clip(-40,0)/10
M['sc']=M.score-M.groupby('race_id').score.transform('mean'); M['nof']=M.best3.isna().astype(float)
tr,te=M[M.period=='2019-23'],M[M.period=='2024-26']
lls={}
for name,cols in (('market',['lp']),('market+speed',['lp','best3_gap_z','avg3_gap_z','nof']),('market+speed+trends',['lp','best3_gap_z','avg3_gap_z','nof','sc'])):
    b=fit_clogit(tr[cols].to_numpy(),tr.win.to_numpy(),tr.race_id.to_numpy(),l2=0.1)
    pr=race_softmax(te[cols].to_numpy()@b,te.race_id.to_numpy()); lls[name]=np.log(pr[te.win.to_numpy()==1]).sum()
    print(f'  {name:22} coef {dict(zip(cols,np.round(b,3)))}  test loglik {lls[name]:.1f}')
    if name=='market+speed+trends':
        te=te.assign(p=pr)
        for e in (1.1,1.2,1.3):
            s=te[te.p*te.morning>e]; print(f'    bet when model x morning > {e}: {len(s)} bets, BSP {100*s.pl_b.mean():+.1f}%, morning {100*s.pl_m.mean():+.1f}%')
print('  races in test', te.race_id.nunique(), ' gain vs market', round((lls['market+speed+trends']-lls['market'])/-lls['market'],5))
