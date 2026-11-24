import sys, csv, glob; sys.path.insert(0,'/home/claude/racingtrends')
import pandas as pd, numpy as np
from trends.speed import prior
from trends import util as U
df=prior(pd.read_pickle('/tmp/speed_runners.pkl'))
# headgear (Aid) from the Duo files
aid={}
for p in glob.glob('/home/claude/rfbdata/*/*Details*.csv'):
    for r in csv.DictReader(open(p,encoding='cp1252',errors='replace')): aid[('rfb'+r['MainID'],U.norm_name(r['HorseName']))]=r.get('Aid','').strip()
df['aid']=[aid.get(k,'') for k in zip(df.race_id,df.horse_key)]
g=df.groupby('horse_key',sort=False)
df['prev_aid']=g['aid'].shift(1).fillna('')
df['first_hg']=(df.aid!='')&(df.prev_aid=='')&(g.cumcount()>0)
D=df[(df.date>='2019-01-01')&df.bsp.notna()&df.morning.notna()&(df.morning>1.01)&(df.bsp>1.01)].copy()
D=D[(D.morning<=50)]  # thin morning markets on outsiders aren't bettable
D['period']=np.where(D.date<'2024-01-01','2019-23','2024-26')
D['clv']=np.log(D.morning/D.bsp)           # >0: morning price was bigger than SP (you beat SP)
D['pl_m']=np.where(D.win==1,(D.morning-1)*.95,-1); D['pl_b']=np.where(D.win==1,(D.bsp-1)*.95,-1)
D['mfav']=D.groupby('race_id').morning.rank(method='min')==1
D['band']=pd.cut(D.morning,[1,2,3,5,8,13,21,51],labels=['<2','2-3','3-5','5-8','8-13','13-21','21-50'])
D['ire_in_gb']=False  # no trainer-country field; skip
def show(key,label,minn=300):
    t=D.groupby([key,'period']).agg(n=('clv','size'),clv=('clv','mean'),roi_m=('pl_m','mean'),roi_b=('pl_b','mean')).unstack('period')
    t=t[(t[('n','2019-23')]>=minn)&(t[('n','2024-26')]>=minn//2)]
    t=(t*[1,1,100,100,100,100,100,100]).round(1) if False else t
    print(f'\n== {label}')
    for idx,r in t.iterrows():
        print(f"  {str(idx)[:28]:28} 19-23 n{int(r[('n','2019-23')]):6} beatSP {100*r[('clv','2019-23')]:+5.1f}% morningROI {100*r[('roi_m','2019-23')]:+5.1f}% | 24-26 n{int(r[('n','2024-26')]):6} beatSP {100*r[('clv','2024-26')]:+5.1f}% morningROI {100*r[('roi_m','2024-26')]:+5.1f}%")
print('ALL: ', D.groupby('period').agg(n=('clv','size'),clv=('clv','mean'),roi_m=('pl_m','mean'),roi_b=('pl_b','mean')).round(3).to_string())
show('band','morning price band')
show('mfav','morning favourite')
show('typ','race type')
show('first_hg','first-time headgear')
D['spd_top']=D.best3_rank==1; show('spd_top','top on speed figure')
D['ran_b']=pd.cut(D.ran,[0,7,11,15,40]); show('ran_b','field size')
D['layoff']=pd.cut(D.lto_days,[0,14,60,180,2000]); show('layoff','days since last run')
D['region2']=D.region; show('region2','region')
# trainers: rank on 2019-23 'beat SP', check same trainers 2024-26
tr=D.groupby(['trainer','period']).agg(n=('clv','size'),clv=('clv','mean'),roi_m=('pl_m','mean')).unstack('period')
tr=tr[(tr[('n','2019-23')]>=400)&(tr[('n','2024-26')]>=150)]
q=tr[('clv','2019-23')]
for lab,sel in (('trainers whose horses DRIFTED most 2019-23 (top 20)',q.nsmallest(20).index),('trainers whose horses SHORTENED most 2019-23 (top 20)',q.nlargest(20).index)):
    s=tr.loc[sel]
    w=lambda c,p: (s[(c,p)]*s[('n',p)]).sum()/s[('n',p)].sum()
    print(f'\n{lab}: 19-23 beatSP {100*w("clv","2019-23"):+.1f}% morningROI {100*w("roi_m","2019-23"):+.1f}%  ->  24-26 beatSP {100*w("clv","2024-26"):+.1f}% morningROI {100*w("roi_m","2024-26"):+.1f}%')
print('\ncorrelation of trainer beatSP 19-23 vs 24-26:', round(tr[('clv','2019-23')].corr(tr[('clv','2024-26')]),3), 'trainers', len(tr))
# within-trainer: back the shorteners' horses at morning price in 24-26
sh=q.nlargest(20).index; s=D[(D.period=='2024-26')&D.trainer.isin(sh)]
print('back all runners of those 20 trainers at morning price 2024-26:', len(s),'bets, ROI', round(100*s.pl_m.mean(),1),'%  (at BSP', round(100*s.pl_b.mean(),1),'%)')
print('\n--- shortening trainers, backed at BSP, by year (trainers chosen on 2019-23 only)')
s=D[D.trainer.isin(sh)]
y=s.groupby(s.date.dt.year).agg(n=('pl_b','size'),bsp_roi=('pl_b','mean'),win=('win','mean'))
print((y*[1,100,100]).round(1).to_string())
t=s[s.period=='2024-26']; print('2024-26 SE', round(100*t.pl_b.std()/np.sqrt(len(t)),1))
# rolling version: each year pick top-20 shortening trainers from the previous 3 years only
out=[]
for yr in range(2022,2027):
    past=D[(D.date.dt.year>=yr-3)&(D.date.dt.year<yr)]
    c=past.groupby('trainer').agg(n=('clv','size'),clv=('clv','mean')); c=c[c.n>=250]
    pick=c.clv.nlargest(20).index
    cur=D[(D.date.dt.year==yr)&D.trainer.isin(pick)]
    out.append((yr,len(cur),round(100*cur.pl_b.mean(),1),round(100*cur.pl_m.mean(),1)))
print('rolling pick (previous 3 yrs): year, bets, BSP ROI, morning ROI'); [print(' ',o) for o in out]
