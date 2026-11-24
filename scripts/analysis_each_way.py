import sys; sys.path.insert(0,'/home/claude/racingtrends')
import pandas as pd, numpy as np
rng=np.random.default_rng(1)
df=pd.read_pickle('/tmp/speed_runners.pkl')[['race_id','date','typ','hcap','ran','pos_n','win','bsp','horse']]
df=df[df.date>='2019-01-01']
ok=df.groupby('race_id').bsp.transform(lambda s:s.notna().all())
df=df[ok & (df.bsp>1.0)].copy()
df['n']=df.groupby('race_id').race_id.transform('size')
df=df[(df.n>=5)&(df.n<=20)]
df['p']=1/df.bsp; df['p']=df.p/df.groupby('race_id').p.transform('sum')
def terms(n,h):
    if n<=7: return 2,0.25
    if h and n>=16: return 4,0.25
    if h and n>=12: return 3,0.25
    return 3,0.2
def sim(sub, lam, S=3000):
    """top-k chances (k=1..5) per runner: winner drawn on p, the rest ordered on p**lam (Plackett-Luce)."""
    out=np.zeros((len(sub),5))
    for n,g in sub.groupby('n'):
        ids=g.race_id.to_numpy(); P=g.p.to_numpy().reshape(-1,n); R=P.shape[0]
        res=np.zeros((R,n,5))
        for b in range(0,R,max(1,200000//(S*n))):
            p=P[b:b+max(1,200000//(S*n))]; r=p.shape[0]
            u=rng.random((r,S,1)); cw=np.cumsum(p,1)[:,None,:]
            w=(u>cw).sum(2)                      # winner index
            key=lam*np.log(p)[:,None,:]+rng.gumbel(size=(r,S,n))
            np.put_along_axis(key, w[...,None], np.inf, 2)
            order=np.argsort(-key,2)
            rank=np.empty_like(order); np.put_along_axis(rank,order,np.arange(n)[None,None,:].repeat(r,0).repeat(S,1),2)
            for k in range(5): res[b:b+r,:,k]=(rank<=k).mean(1)
        out[np.flatnonzero(sub.index.isin(g.index))]=0  # placeholder
        sub.loc[g.index,[f'top{k+1}' for k in range(5)]]=res.reshape(-1,5)
    return sub
df=df.sort_values(['race_id']).reset_index(drop=True)
for c in range(1,6): df[f'top{c}']=np.nan
# fit lambda on a sample of 2019-23 races
races=df[df.date<'2024-01-01'].race_id.unique(); samp=rng.choice(races,6000,replace=False)
S0=df[df.race_id.isin(samp)].copy()
for lam in ():
    s=sim(S0.copy(),lam,1500); y=(s.pos_n<=3).astype(float); q=s.top3.clip(1e-4,1-1e-4)
    m=s.n>=8; print('lambda',lam,'logloss top3', round(-(y*np.log(q)+(1-y)*np.log(1-q))[m].mean(),5), ' fav top3 pred/actual', round(s[m&(s.p==s.groupby('race_id').p.transform('max'))].top3.mean(),3), round(y[m&(s.p==s.groupby('race_id').p.transform('max'))].mean(),3))

print('\n=== 2024-26, lambda 0.7')
T=sim(df[df.date>='2024-01-01'].copy(),0.7,2000)
tk=[terms(n,h) for n,h in zip(T.n,T.hcap)]
T['k']=[t[0] for t in tk]; T['f']=[t[1] for t in tk]
def pk(T,k): return np.choose(np.clip(k,1,5)-1, [T[f'top{i}'].to_numpy() for i in range(1,6)])
T['pstd']=pk(T,T.k); T['pext']=pk(T,T.k+1)
def ev(D,pw,pp,f):  # EV per £1 of the £2 each-way stake
    return 0.5*(pw*D-1)+0.5*(pp*((D-1)*f+1)-1)
def breakeven(pw,pp,f):  # decimal price where EW EV = 0: solve 0.5(pw D -1)+0.5(pp((D-1)f+1)-1)=0
    return (2-pp+pp*f)/(pw+pp*f)
T['be_std']=breakeven(T.p,T.pstd,T.f); T['be_ext']=breakeven(T.p,T.pext,T.f)
T['ratio_std']=T.be_std/T.bsp; T['ratio_ext']=T.be_ext/T.bsp
T['band']=pd.cut(T.bsp,[1,3,6,11,21,1000],labels=['evens-2/1','2/1-5/1','5/1-10/1','10/1-20/1','20/1+'])
T['field']=np.where(T.n<=7,'5-7 runners (2 pl 1/4)',np.where((T.hcap==1)&(T.n>=16),'16+ handicap (4 pl 1/4)',np.where((T.hcap==1)&(T.n>=12),'12-15 handicap (3 pl 1/4)',np.where(T.n<=8,'8 runners (3 pl 1/5)','9-15 non-h/c or 8-11 h/c (3 pl 1/5)'))))
print('Bookmaker price needed for a fair (0 EV) each-way bet, as % of Betfair SP (below 100% = each-way is value even at a price shorter than the exchange)')
tab=T.groupby(['field','band'],observed=True).agg(n=('p','size'),std=('ratio_std','median'),extra=('ratio_ext','median'))
print((tab.assign(std=lambda t:(100*t['std']).round(0),extra=lambda t:(100*t.extra).round(0))).to_string())
# realised check: each-way bets struck at Betfair SP when model says EV>+5% at that price
for lab,pp,kcol in (('standard terms','pstd','k'),('one extra place','pext',None)):
    k=T.k if kcol else T.k+1
    e=ev(T.bsp,T.p,T[pp],T.f); sel=e>0.05
    s=T[sel]; kk=k[sel]
    placed=(s.pos_n<=kk); won=s.win==1
    ret=np.where(won,s.bsp,0)+np.where(placed,(s.bsp-1)*s.f+1,0)
    print(f'{lab}: EW bets with model EV>+5% at SP-equivalent price: {len(s)} bets, predicted EV {100*e[sel].mean():+.1f}%, actual return {100*(ret.sum()/(2*len(s))-1):+.1f}%  (SE ~{100*np.std(ret/2)/np.sqrt(len(s)):.1f}%)')
T[['race_id','field','band','p','pstd','pext','f','k','bsp','ratio_std','ratio_ext','pos_n','win']].to_pickle('/tmp/ew_test.pkl')
