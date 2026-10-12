import json, numpy as np, pandas as pd, yfinance as yf
df = yf.download("JPY=X", start="2003-12-01", progress=False, auto_adjust=False)
s = df["Close"].squeeze().dropna()
s = s[(s > 70) & (s < 170)]
s = s[~((s / s.rolling(5, center=True, min_periods=1).median() - 1).abs() > 0.05)]
cur = 1 / s
me = cur.resample("ME").last()
me = me[me.index <= pd.Timestamp.today().normalize()]
ret = (me.pct_change() * 100).dropna()
last_full = ret.index.max()
M = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
years = sorted({d.year for d in ret.index if d.year >= 2004})
ret = ret[ret.index.year >= 2004]
cal, grid = [], {}
for i, m in enumerate(M, 1):
    r = ret[ret.index.month == m] if False else ret[ret.index.month == i]
    v = r.values
    t = v.mean() / (v.std(ddof=1) / np.sqrt(len(v))) if len(v) > 2 else 0
    a = r[r.index.year <= 2014].mean(); b = r[r.index.year >= 2015].mean()
    l10 = r[r.index.year >= last_full.year - 9]
    r10 = l10[l10.index.year <= last_full.year]
    cal.append(dict(month=M[i-1], avg=round(v.mean(),3), median=round(float(np.median(v)),3),
        hit_up=round(float((v>0).mean()*100),2), t=round(float(t),3), avg_2004_14=round(float(a),3),
        avg_2015_26=round(float(b),3), avg_last10y=round(float(r10.mean()),3),
        hit_last10y=round(float((r10>0).mean()*100),3)))
    grid[M[i-1]] = [round(float(r[r.index.year==y].iloc[0]),2) if (r.index.year==y).any() else None for y in years]
json.dump(dict(note="Yen expressed as 1/USDJPY (Yahoo JPY=X daily, bad ticks removed): month-end to month-end % change, so positive = yen STRONGER vs the dollar, negative = weaker.",
    JPY=dict(calendar=cal, years=years, grid=grid), last=str(last_full.date())), open("fx_seasonality.json","w"), indent=1)
print(last_full, [(c['month'],c['avg'],c['hit_up'],c['t']) for c in cal])
