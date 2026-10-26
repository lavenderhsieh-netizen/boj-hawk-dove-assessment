#!/usr/bin/env python3.12
"""Retail JGB issuance by issue date and type since 2003, from MOF kojin_suii.xls
(個人向け国債発行額の推移), plus rolling 12-month total. Output: retail_jgb_issuance.json (¥tn)."""
import json, os, urllib.request
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
XLS = os.path.join(HERE, "mof_source", "kojin_suii.xls")
try:
    req = urllib.request.Request("https://www.mof.go.jp/jgbs/reference/appendix/kojin_suii.xls", headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=60).read()
    if data[:4] == b"\xd0\xcf\x11\xe0":
        open(XLS, "wb").write(data)
except Exception as e:
    print("download failed, using cached file:", e)
df = pd.read_excel(XLS, header=None)
rows = {}
for dc, c3, c5, c10 in ((1, 3, 5, 7), (11, 13, 15, 17)):
    for _, r in df.iloc[5:].iterrows():
        d = r.iloc[dc]
        if not isinstance(d, (pd.Timestamp,)) and not hasattr(d, "year"):
            continue
        num = lambda v: float(v) if isinstance(v, (int, float)) else 0.0
        rows[pd.Timestamp(d)] = [num(r.iloc[c3]), num(r.iloc[c5]), num(r.iloc[c10])]
s = pd.DataFrame(rows, index=["fixed3", "fixed5", "float10"]).T.sort_index()
s = s[(s.sum(axis=1) > 0)]
s = s / 10000
m = s.copy(); m.index = m.index.to_period("M")
m = m.groupby(level=0).sum()
full = m.reindex(pd.period_range(m.index.min(), m.index.max(), freq="M"), fill_value=0)
roll = full.sum(axis=1).rolling(12).sum().dropna()
out = {"meta": {"source": "Ministry of Finance, 個人向け国債の発行額の推移 (kojin_suii.xls), issue-date basis",
                "unit": "¥tn", "last_issue": str(s.index.max().date())},
       "issues": [dict(date=str(d.date()), fixed3=round(r.fixed3, 4), fixed5=round(r.fixed5, 4), float10=round(r.float10, 4)) for d, r in s.iterrows()],
       "rolling12": [dict(month=str(p), v=round(v, 3)) for p, v in roll.items()]}
json.dump(out, open(os.path.join(HERE, "retail_jgb_issuance.json"), "w"))
print(s.tail(3)); print(roll.tail(2)); print(roll.max(), roll.idxmax(), roll.loc["2005-04"] if "2005-04" in roll.index.astype(str) else "")
