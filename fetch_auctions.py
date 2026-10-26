#!/usr/bin/env python3.12
"""JGB auction demand by tenor (2Y/5Y/10Y/20Y/30Y/40Y): bid-to-cover, tail (sen per ¥100, average
less lowest accepted price) and stop yield minus prior-business-day MOF constant-maturity yield (bp).
History from MOF's auction workbook (lags a month or two); later auctions from MOF's per-auction
result pages. Output: auctions.json (auctions since 2024-01)."""
import json, os, re, urllib.request, calendar
from datetime import datetime
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
XLS = os.path.join(HERE, "mof_source", "jgb_historical_data.xls")
UA = {"User-Agent": "Mozilla/5.0"}
SINCE = datetime(2024, 1, 1)
TENORS = {"2Y": ("2年債", 2, 2), "5Y": ("5年債", 5, 5), "10Y": ("10年債", 10, 10),
          "20Y": ("20年債", 20, 12), "30Y": ("30年債", 30, 14), "40Y": ("40年債", 40, 15)}
# column index in MOF's jgbcm csv: 基準日,1年,2年,3年,4年,5年,6年,7年,8年,9年,10年,15年,20年,25年,30年,40年

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()

def yields():
    out = {}
    for u in ("https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv",
              "https://www.mof.go.jp/jgbs/reference/interest_rate/jgbcm.csv"):
        for line in get(u).decode("cp932").splitlines():
            p = line.split(",")
            m = re.match(r"([RHS])(\d+)\.(\d+)\.(\d+)$", p[0].strip())
            if not m or len(p) < 16:
                continue
            base = {"R": 2018, "H": 1988, "S": 1925}[m.group(1)]
            d = datetime(base + int(m.group(2)), int(m.group(3)), int(m.group(4)))
            for t, (_, _, ci) in TENORS.items():
                try:
                    out.setdefault(t, {})[d] = float(p[{2: 2, 5: 5, 10: 10, 12: 12, 14: 14, 15: 15}.get(ci, ci)])
                except ValueError:
                    pass
    return out

def from_workbook(sheet):
    df = pd.read_excel(XLS, sheet, header=None)
    hi = next(i for i in range(8) if str(df.iloc[i, 0]).strip() == "回号")
    hdr = [str(v).strip() for v in df.iloc[hi].values]
    c = {n: hdr.index(n) for n in ["入札日", "応募額", "落札・割当額", "最低価格", "最高利回"]}
    c["平均価格"] = hdr.index("平均価格") if "平均価格" in hdr else None
    rows = []
    for _, r in df.iloc[hi + 3:].iterrows():
        d = r.iloc[c["入札日"]]
        if not hasattr(d, "year"):
            continue
        d = pd.Timestamp(d).to_pydatetime()
        if d < SINCE:
            continue
        try:
            rows.append(dict(date=d, issue=int(r.iloc[0]), bids=float(r.iloc[c["応募額"]]), acc=float(r.iloc[c["落札・割当額"]]),
                             avgp=(float(r.iloc[c["平均価格"]]) if c["平均価格"] is not None else None), lowp=float(r.iloc[c["最低価格"]]), stop=float(r.iloc[c["最高利回"]])))
        except (TypeError, ValueError):
            continue
    return rows

def yen(s):
    s = s.replace(",", "").replace("億円", "")
    if "兆" in s:
        a, b = s.split("兆")
        return float(a) * 10000 + (float(b) if b else 0)
    return float(s)

def from_pages(after):
    found = {t: [] for t in TENORS}
    y, m = after.year, after.month
    while True:
        try:
            t = get(f"https://www.mof.go.jp/jgbs/auction/calendar/{y % 100}{m:02d}.htm").decode("utf-8")
        except Exception:
            break
        for ds in sorted(set(re.findall(r"nyusatsu/resul(\d{8})\.htm", t))):
            d = datetime.strptime(ds, "%Y%m%d")
            if d <= after:
                continue
            try:
                h = get(f"https://www.mof.go.jp/jgbs/auction/calendar/nyusatsu/resul{ds}.htm").decode("utf-8")
            except Exception:
                continue
            title = h.split("<title>")[1].split("</title>")[0]
            mt = re.match(r"\s*(\d+)年利付国債（第(\d+)回）", title)
            if not mt or f"{mt.group(1)}Y" not in TENORS:
                continue
            tx = re.sub(r"<[^>]*>", "|", h); tx = re.sub(r"\|[\s|]*\|", "|", tx)
            try:
                low = re.search(r"募入最低価格\|(\d+)円(\d+)銭", tx); avg = re.search(r"募入平均価格\|(\d+)円(\d+)銭", tx)
                stop = re.search(r"（募入最高利回り）\|（([\d.]+)％", tx) or re.search(r"応募者利回り\|([\d.]+)％", tx)
                bids = re.search(r"応募額\|([^|]+)\|", tx).group(1); acc = re.search(r"募入決定額\|([^|]+)\|", tx).group(1)
                found[f"{mt.group(1)}Y"].append(dict(
                    date=d, issue=int(mt.group(2)), bids=yen(bids), acc=yen(acc),
                    avgp=(int(avg.group(1)) + int(avg.group(2)) / 100) if avg else None,
                    lowp=(int(low.group(1)) + int(low.group(2)) / 100) if low else None, stop=float(stop.group(1))))
            except Exception as e:
                print("parse fail", ds, title, e)
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return found

def main():
    Y = yields()
    out = {}
    for t, (sheet, _, _) in TENORS.items():
        rows = from_workbook(sheet)
        last = max(r["date"] for r in rows)
        out[t] = (rows, last)
    cutoff = min(l for _, l in out.values())
    pages = from_pages(cutoff.replace(day=1) if False else cutoff)
    res = {}
    for t, (rows, last) in out.items():
        rows = [r for r in rows] + [r for r in pages[t] if r["date"] > last]
        rows.sort(key=lambda r: r["date"])
        lst, prev = [], None
        for r in rows:
            ks = [k for k in Y[t] if k < r["date"]]
            prior = Y[t][max(ks)]
            lst.append(dict(date=r["date"].strftime("%Y-%m-%d"), issue=r["issue"], new=prev is not None and r["issue"] != prev,
                            btc=round(r["bids"] / r["acc"], 2), tail_sen=(round((r["avgp"] - r["lowp"]) * 100) if r["avgp"] is not None and r["lowp"] is not None else None),
                            stop_vs_prior_bp=round((r["stop"] - prior) * 100, 1), stop=r["stop"]))
            prev = r["issue"]
        res[t] = lst
        print(t, len(lst), lst[-1])
    json.dump({"meta": {"source": "MOF auction results (workbook + per-auction pages); MOF constant-maturity yields",
                        "method": "Cover = competitive bids / accepted; tail = average less lowest accepted price (sen per ¥100); stop vs prior close = highest accepted yield less prior business day's MOF CMT yield (bp)"},
               "tenors": res}, open(os.path.join(HERE, "auctions.json"), "w"), ensure_ascii=False)

main()
