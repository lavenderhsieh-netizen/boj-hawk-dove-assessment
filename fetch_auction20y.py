#!/usr/bin/env python3.12
"""2026 20-year JGB auction quality (bid-to-cover, tail in sen per ¥100, stop yield minus
prior-business-day MOF constant-maturity 20y yield). Replicates a sell-side chart (2026-10-26).
Jan-Aug from MOF's auction workbook; later auctions from MOF's per-auction result pages
(workbook lags). Output: auction20y.json"""
import json, os, re, io, urllib.request
from datetime import datetime
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
XLS = os.path.join(HERE, "mof_source", "jgb_historical_data.xls")
UA = {"User-Agent": "Mozilla/5.0"}
YEAR = 2026

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()

def yields():
    raw = get("https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv").decode("cp932")
    cur = get("https://www.mof.go.jp/jgbs/reference/interest_rate/jgbcm.csv").decode("cp932")
    out = {}
    for txt in (raw, cur):
        for line in txt.splitlines():
            p = line.split(",")
            m = re.match(r"([RHS])(\d+)\.(\d+)\.(\d+)$", p[0].strip())
            if not m or len(p) < 13:
                continue
            base = {"R": 2018, "H": 1988, "S": 1925}[m.group(1)]
            d = datetime(base + int(m.group(2)), int(m.group(3)), int(m.group(4)))
            try:
                out[d] = float(p[12])
            except ValueError:
                pass
    return out

def prior_close(y, d):
    ks = [k for k in y if k < d]
    return y[max(ks)]

def from_workbook():
    df = pd.read_excel(XLS, "20年債", header=None)
    rows = []
    for _, r in df.iloc[5:].iterrows():
        d = r.iloc[1]
        if not isinstance(d, (datetime, pd.Timestamp)) or d.year != YEAR:
            continue
        rows.append(dict(date=pd.Timestamp(d).to_pydatetime(), issue=int(r.iloc[0]), bids=float(r.iloc[6]), acc=float(r.iloc[7]),
                         avgp=float(r.iloc[8]), lowp=float(r.iloc[10]), stop=float(r.iloc[11])))
    return rows

def from_pages(after):
    rows = []
    for mo in range(after.month, 13):
        try:
            t = get(f"https://www.mof.go.jp/jgbs/auction/calendar/{YEAR%100}{mo:02d}.htm").decode("utf-8")
        except Exception:
            continue
        for ds in sorted(set(re.findall(r"nyusatsu/resul(%d\d{4})\.htm" % YEAR, t))):
            d = datetime.strptime(ds, "%Y%m%d")
            if d <= after:
                continue
            try:
                h = get(f"https://www.mof.go.jp/jgbs/auction/calendar/nyusatsu/resul{ds}.htm").decode("utf-8")
            except Exception:
                continue
            if "20年利付国債" not in h.split("<title>")[1].split("</title>")[0]:
                continue
            tx = re.sub(r"<[^>]*>", "|", h); tx = re.sub(r"\|[\s|]*\|", "|", tx)
            num = lambda s: float(s.replace(",", ""))
            def oku(lbl):
                m = re.search(lbl + r"\|([\d,兆]+)億円", tx.replace("兆", "").replace(",", ",") ) 
                return None
            bids_s = re.search(r"\(1\)応募額\|([^|]+)\|", tx).group(1)
            acc_s = re.search(r"\(2\)募入決定額\|([^|]+)\|", tx).group(1)
            def yen(s):
                s = s.replace(",", "").replace("億円", "")
                if "兆" in s:
                    a, b = s.split("兆"); return float(a) * 10000 + (float(b) if b else 0)
                return float(s)
            low = re.search(r"募入最低価格\|(\d+)円(\d+)銭", tx); avg = re.search(r"募入平均価格\|(\d+)円(\d+)銭", tx)
            stop = re.search(r"募入最高利回り\）?\|?[^\d]*([\d.]+)％", tx) or re.search(r"（募入最高利回り）\|（([\d.]+)％", tx)
            iss = int(re.search(r"第(\d+)回", h.split("<title>")[1]).group(1))
            rows.append(dict(date=d, issue=iss, bids=yen(bids_s), acc=yen(acc_s),
                             avgp=int(avg.group(1)) + int(avg.group(2)) / 100, lowp=int(low.group(1)) + int(low.group(2)) / 100,
                             stop=float(stop.group(1))))
    return rows

def main():
    y = yields()
    rows = from_workbook()
    rows += from_pages(max(r["date"] for r in rows))
    out, prev_issue = [], None
    for r in sorted(rows, key=lambda r: r["date"]):
        out.append(dict(date=r["date"].strftime("%Y-%m-%d"), month=r["date"].strftime("%b"), issue=r["issue"],
                        new=r["issue"] != prev_issue and prev_issue is not None or (prev_issue is None and False),
                        btc=round(r["bids"] / r["acc"], 2), tail_sen=round((r["avgp"] - r["lowp"]) * 100),
                        stop_vs_prior_bp=round((r["stop"] - prior_close(y, r["date"])) * 100, 1), stop=r["stop"]))
        prev_issue = r["issue"]
    json.dump({"meta": {"source": "MOF auction results; MOF constant-maturity 20y yield (prior business day close)",
                        "method": "Cover = competitive bids / accepted; tail = average less lowest accepted price (sen per ¥100); stop vs prior close = highest accepted yield minus prior-day MOF 20y CMT yield (bp)"},
               "auctions": out}, open(os.path.join(HERE, "auction20y.json"), "w"), indent=1, ensure_ascii=False)
    for o in out: print(o)

main()
