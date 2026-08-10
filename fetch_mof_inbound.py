#!/usr/bin/env python3.12
"""Fetch MoF 'International Transactions in Securities (Monthly)' — non-residents'
net purchase of JAPANESE securities (Portfolio Investment Liabilities), by
instrument: equity & investment fund shares / long-term debt / short-term debt.

This is the INBOUND mirror of fetch_mof_flows.py (which covers residents' net
purchase of FOREIGN securities, outbound). Source is a single combined file
(montha1.csv) that carries both directions side by side — columns 14-24 are
the inbound (Liabilities) block; columns 3-13 are outbound (Assets), kept here
too for a same-source cross-check against fetch_mof_flows.py's monthb2/3/4 total.

Source: https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/montha1.csv
  (cp932-encoded; monthly since 2005-01)

Sign: + = net purchase (for inbound: foreign capital inflow to Japan),
      − = net sale / repatriation. Values are 億円; output ¥tn (÷10000).

Outputs mof_inbound.json with monthly net purchase (¥tn, $bn) for equity / LT
debt / ST debt / total, from START, non-residents buying Japanese securities.
Run: python3.12 fetch_mof_inbound.py
"""
import urllib.request, csv, io, json, os, datetime

URL = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/montha1.csv"
UA = {"User-Agent": "Mozilla/5.0"}
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "mof_source"); os.makedirs(SRC, exist_ok=True)
START = "2021-04"
MN = {"１月":1,"２月":2,"３月":3,"４月":4,"５月":5,"６月":6,
      "７月":7,"８月":8,"９月":9,"１０月":10,"１１月":11,"１２月":12}

# column indices (0-based) within a data row, confirmed against MoF's own
# Acquisition/Disposition/Net header rows:
#   3/4/5   = outbound equity Acq/Disp/Net      6/7/8   = outbound LT debt Acq/Disp/Net
#   10/11/12= outbound ST debt Acq/Disp/Net     13      = outbound total net
#   14/15/16= inbound equity Acq/Disp/Net       17/18/19= inbound LT debt Acq/Disp/Net
#   21/22/23= inbound ST debt Acq/Disp/Net      24      = inbound total net
COLS = {"out_equity": 5, "out_ltbonds": 8, "out_stbonds": 12, "out_total": 13,
        "in_equity": 16, "in_ltbonds": 19, "in_stbonds": 23, "in_total": 24}

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()

def num(x):
    x = (x or "").replace(",", "").strip()
    if x in ("", "-", "―"): return None
    try: return float(x)
    except ValueError: return None

def usdjpy_monthly():
    try:
        j = json.loads(get("https://query1.finance.yahoo.com/v8/finance/chart/JPY=X?interval=1mo&range=7y").decode())
        res = j["chart"]["result"][0]
        ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
        out = {}
        for t, c in zip(ts, cl):
            if c is None: continue
            d = datetime.datetime.utcfromtimestamp(t)
            out[f"{d.year}-{d.month:02d}"] = round(float(c), 3)
        return out
    except Exception as e:
        print("usdjpy fetch failed:", e); return {}

def main():
    raw = get(URL)
    open(os.path.join(SRC, "montha1.csv"), "wb").write(raw)
    rows = list(csv.reader(io.StringIO(raw.decode("cp932"))))

    recs = []
    yr = None
    for r in rows:
        if len(r) <= max(COLS.values()) or r[1].strip() not in MN:
            continue
        if r[0].strip():
            try: yr = int(r[0].strip())
            except ValueError: pass
        if yr is None or not r[3].strip():
            continue
        vals = {k: num(r[c]) for k, c in COLS.items()}
        if vals["in_total"] is None:
            continue
        recs.append((yr, MN[r[1].strip()], {k: (round(v/10000.0, 3) if v is not None else None) for k, v in vals.items()}))

    fx = usdjpy_monthly()
    def rate(tag):
        if tag in fx: return fx[tag]
        earlier = [v for k, v in sorted(fx.items()) if k <= tag]
        return earlier[-1] if earlier else (sorted(fx.values())[len(fx)//2] if fx else None)
    def usd(v, tag):
        r = rate(tag)
        return round(v * 1000.0 / r, 2) if (v is not None and r) else None

    months = sorted({f"{y}-{m:02d}" for y, m, _ in recs if f"{y}-{m:02d}" >= START})
    by_month = {(y, m): d for y, m, d in recs}
    keys = list(COLS.keys())
    monthly = {k: [] for k in keys}
    monthly_usd = {k: [] for k in keys}
    for tag in months:
        y, mo = int(tag[:4]), int(tag[5:7])
        d = by_month.get((y, mo), {})
        for k in keys:
            v = d.get(k)
            monthly[k].append(v)
            monthly_usd[k].append(usd(v, tag))

    out = {
        "meta": {
            "as_of": months[-1] if months else None,
            "generated_at": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "unit": "JPY tn",
            "sign": "+ = net purchase (inbound: foreign capital inflow to Japan); − = net sale / repatriation",
            "source": "MoF International Transactions in Securities (Monthly) — non-residents' net purchase of Japanese securities, by instrument (montha1.csv)",
            "source_url": "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/index.htm",
        },
        "labels": {"equity": "Equity & fund shares", "ltbonds": "Long-term debt", "stbonds": "Short-term debt", "total": "Total"},
        "months": months,
        "monthly": monthly,
        "monthly_usd": monthly_usd,
    }
    with open(os.path.join(HERE, "mof_inbound.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"as_of {out['meta']['as_of']} · {len(months)} months -> mof_inbound.json")

if __name__ == "__main__":
    main()
