#!/usr/bin/env python3.12
"""Fetch MoF 'International Transactions in Securities' — Japanese residents' net
purchase of FOREIGN long-term debt securities, by type of investor.

Source: MoF 投資家部門別対外証券投資（中長期債） monthly CSV (cp932):
  https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/monthb3.csv

Sign: from Jan-2014 onward, + = net purchase of foreign bonds (yen outflow),
      − = net sale / repatriation. Values are 億円; we output ¥tn (÷10000).

Outputs mof_flows.json with:
  - monthly net purchase per investor bucket (¥tn), from 2021-04
  - cumulative fiscal-year-to-date (Apr-start) arrays, one per FY per bucket
Run: python3.12 fetch_mof_flows.py
"""
import urllib.request, csv, io, json, os, datetime

URL = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/monthb3.csv"
UA = {"User-Agent": "Mozilla/5.0"}
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "mof_source"); os.makedirs(SRC, exist_ok=True)
START = "2021-04"                       # monthly history window
MN = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
      "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
FYM = ["Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec","Jan","Feb","Mar"]

# JP label (start of an Acquisition/Disposition/Net triplet) -> output key + display label
BUCKETS = [
    ("各部門計",                       "total",         "All investors"),
    ("銀行等（銀行勘定）",             "banks",         "Banks (banking a/c)"),
    ("信託銀行（銀行勘定）",           "trust_bank",    "Trust banks (banking a/c)"),
    ("銀行等及び信託銀行（信託勘定）", "trust_pension", "Trust a/c (pension)"),
    ("生命保険会社",                   "life",          "Life insurers"),
    ("損害保険会社",                   "nonlife",       "Non-life insurers"),
    ("投資信託委託会社等",             "invtrust",      "Investment trusts"),
]

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()

def num(x):
    x = (x or "").replace(",", "").strip()
    if x in ("", "-", "―"): return None
    try: return float(x)
    except ValueError: return None

def usdjpy_monthly():
    """Monthly USDJPY close from Yahoo, {YYYY-MM: rate}. Empty dict on failure."""
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
    open(os.path.join(SRC, "monthb3.csv"), "wb").write(raw)
    rows = list(csv.reader(io.StringIO(raw.decode("cp932"))))
    # locate the Net column for each bucket (label col + 2)
    net = {}
    for jp, key, _ in BUCKETS:
        for r in range(0, 11):
            hit = next((c for c, v in enumerate(rows[r]) if (v or "").strip() == jp), None)
            if hit is not None:
                net[key] = hit + 2; break
    missing = [k for _, k, _ in BUCKETS if k not in net]
    if missing:
        raise RuntimeError(f"columns not found: {missing}")

    keys = [k for _, k, _ in BUCKETS]
    recs = []                              # (year, month, {key: ¥tn})
    yr = None
    for r in rows:
        if len(r) <= max(net.values()) or r[2].strip() not in MN:
            continue
        if r[0].strip():
            try: yr = int(r[0].strip())
            except ValueError: pass
        vals = {k: num(r[net[k]]) for k in keys}
        if vals["total"] is None or yr is None:
            continue
        recs.append((yr, MN[r[2].strip()], {k: (round(v/10000.0, 3) if v is not None else None) for k, v in vals.items()}))

    # USDJPY per month → convert ¥tn to $bn:  $bn = ¥tn * 1000 / rate
    fx = usdjpy_monthly()
    def rate(tag):
        if tag in fx: return fx[tag]
        earlier = [v for k, v in sorted(fx.items()) if k <= tag]
        return earlier[-1] if earlier else (sorted(fx.values())[len(fx)//2] if fx else None)
    def usd(v, tag):
        r = rate(tag)
        return round(v * 1000.0 / r, 2) if (v is not None and r) else None

    # monthly window (¥tn) + USD ($bn)
    months, monthly, monthly_usd = [], {k: [] for k in keys}, {k: [] for k in keys}
    for y, m, d in recs:
        tag = f"{y}-{m:02d}"
        if tag < START: continue
        months.append(tag)
        for k in keys:
            monthly[k].append(d[k])
            monthly_usd[k].append(usd(d[k], tag))

    # cumulative fiscal-year-to-date (Apr..Mar), one array per FY per bucket, both currencies
    by = {(y, m): d for y, m, d in recs}
    fys = sorted({(y if m >= 4 else y - 1) for y, m, d in recs})
    fys = [fy for fy in fys if fy >= 2021]
    fytd = {k: {} for k in keys}
    fytd_usd = {k: {} for k in keys}
    seasonal = {k: {} for k in keys}          # monthly (non-cumulative) net buying, Apr..Mar
    seasonal_usd = {k: {} for k in keys}
    for k in keys:
        for fy in fys:
            arr, run = [], 0.0
            arru, runu = [], 0.0
            sea, seau = [], []
            for mlabel in FYM:
                mnum = MN[mlabel]
                yy = fy if mnum >= 4 else fy + 1
                tag = f"{yy}-{mnum:02d}"
                v = by.get((yy, mnum), {}).get(k)
                if v is None:
                    arr.append(None); arru.append(None)      # month not yet published
                    sea.append(None); seau.append(None)
                else:
                    run += v; arr.append(round(run, 3)); sea.append(v)
                    uv = usd(v, tag)
                    seau.append(uv)
                    if uv is None: arru.append(None)
                    else: runu += uv; arru.append(round(runu, 2))
            fytd[k][str(fy)] = arr
            fytd_usd[k][str(fy)] = arru
            seasonal[k][str(fy)] = sea
            seasonal_usd[k][str(fy)] = seau

    as_of = f"{recs[-1][0]}-{recs[-1][1]:02d}"
    doc = {
        "meta": {
            "as_of": as_of,
            "generated_at": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "unit": "JPY tn",
            "sign": "+ = net purchase of foreign bonds (yen outflow); − = net sale / repatriation",
            "source": "MoF International Transactions in Securities — residents' net purchase of foreign long-term debt securities, by type of investor (monthb3.csv)",
            "source_url": "https://www.mof.go.jp/english/policy/international_policy/reference/itn_transactions_in_securities/index.htm",
        },
        "labels": {k: lab for _, k, lab in BUCKETS},
        "order": ["banks", "trust_bank", "trust_pension", "life"],
        "months": months,
        "monthly": monthly,
        "monthly_usd": monthly_usd,
        "fytd_months": FYM,
        "fytd": fytd,
        "fytd_usd": fytd_usd,
        "seasonal": seasonal,
        "seasonal_usd": seasonal_usd,
    }
    for dest in (os.path.join(HERE, "mof_flows.json"),
                 os.path.join(HERE, "streamlit_app", "mof_flows.json")):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        json.dump(doc, open(dest, "w"), ensure_ascii=False, indent=1)
    print(f"as_of {as_of} · {len(months)} months · buckets {keys} -> mof_flows.json")

if __name__ == "__main__":
    main()
