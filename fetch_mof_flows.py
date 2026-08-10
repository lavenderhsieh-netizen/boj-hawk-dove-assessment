#!/usr/bin/env python3.12
"""Fetch MoF 'International Transactions in Securities' — Japanese residents' net
purchase of FOREIGN securities, by type of investor, split by instrument
(equity & fund shares / long-term debt / short-term debt).

Source: MoF 投資家部門別対外証券投資 monthly CSVs (cp932), same layout, three files:
  monthb2.csv — Equity and investment fund shares
  monthb3.csv — Long-term debt securities
  monthb4.csv — Short-term debt securities
  https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/{file}

Sign: from Jan-2014 onward, + = net purchase of foreign securities (yen outflow),
      − = net sale / repatriation. Values are 億円; we output ¥tn (÷10000).

Outputs mof_flows.json with:
  - monthly net purchase per investor bucket (¥tn), from 2021-04, for each
    instrument (equity / stbonds / ltbonds) plus their sum ("monthly", the
    original all-instrument LT-bond-era field kept for the seasonal/FYTD charts)
  - cumulative fiscal-year-to-date (Apr-start) arrays, one per FY per bucket
    (LT bonds only, unchanged — matches the existing seasonality/FYTD tiles)
Run: python3.12 fetch_mof_flows.py
"""
import urllib.request, csv, io, json, os, datetime

BASE = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/{f}"
INSTRUMENTS = [
    ("equity",   "monthb2.csv", "Equity & fund shares"),
    ("ltbonds",  "monthb3.csv", "Long-term bonds"),
    ("stbonds",  "monthb4.csv", "Short-term bonds"),
]
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
    ("金融商品取引業者",               "secfirms",      "Securities firms"),
    ("生命保険会社",                   "life",          "Life insurers"),
    ("損害保険会社",                   "nonlife",       "Non-life insurers"),
    ("投資信託委託会社等",             "invtrust",      "Investment trusts"),
    ("その他",                         "others",        "Others"),
    ("中央銀行",                       "central_bank",  "Central bank"),
    ("一般政府",                       "govt",          "General government"),
]
KEYS = [k for _, k, _ in BUCKETS]

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

def fetch_recs(fname):
    """Download one monthb*.csv and return recs: list of (year, month, {key: ¥tn})."""
    raw = get(BASE.format(f=fname))
    open(os.path.join(SRC, fname), "wb").write(raw)
    rows = list(csv.reader(io.StringIO(raw.decode("cp932"))))
    # locate the Net column for each bucket (label col + 2, an Acq/Disp/Net triplet)
    net = {}
    for jp, key, _ in BUCKETS:
        for r in range(0, 11):
            hit = next((c for c, v in enumerate(rows[r]) if (v or "").strip() == jp), None)
            if hit is not None:
                net[key] = hit + 2; break
    missing = [k for _, k, _ in BUCKETS if k not in net]
    if missing:
        raise RuntimeError(f"{fname}: columns not found: {missing}")

    recs = []
    yr = None
    for r in rows:
        if len(r) <= max(net.values()) or r[2].strip() not in MN:
            continue
        if r[0].strip():
            try: yr = int(r[0].strip())
            except ValueError: pass
        vals = {k: num(r[net[k]]) for k in KEYS}
        if vals["total"] is None or yr is None:
            continue
        recs.append((yr, MN[r[2].strip()], {k: (round(v/10000.0, 3) if v is not None else None) for k, v in vals.items()}))
    return recs

def main():
    recs_by_instr = {instr: fetch_recs(fname) for instr, fname, _ in INSTRUMENTS}

    # USDJPY per month → convert ¥tn to $bn:  $bn = ¥tn * 1000 / rate
    fx = usdjpy_monthly()
    def rate(tag):
        if tag in fx: return fx[tag]
        earlier = [v for k, v in sorted(fx.items()) if k <= tag]
        return earlier[-1] if earlier else (sorted(fx.values())[len(fx)//2] if fx else None)
    def usd(v, tag):
        r = rate(tag)
        return round(v * 1000.0 / r, 2) if (v is not None and r) else None

    # union of months across the three instrument files
    months = sorted({f"{y}-{m:02d}" for recs in recs_by_instr.values() for y, m, _ in recs
                      if f"{y}-{m:02d}" >= START})

    by_instr = {instr: {(y, m): d for y, m, d in recs} for instr, recs in recs_by_instr.items()}

    def instr_monthly(instr):
        m_, u_ = {k: [] for k in KEYS}, {k: [] for k in KEYS}
        for tag in months:
            y, mo = int(tag[:4]), int(tag[5:7])
            d = by_instr[instr].get((y, mo), {})
            for k in KEYS:
                v = d.get(k)
                m_[k].append(v)
                u_[k].append(usd(v, tag))
        return m_, u_

    monthly_by_instrument, monthly_by_instrument_usd = {}, {}
    for instr, _, _ in INSTRUMENTS:
        m_, u_ = instr_monthly(instr)
        monthly_by_instrument[instr] = m_
        monthly_by_instrument_usd[instr] = u_

    # combined all-instrument monthly total (equity + LT bonds + ST bonds), for the stacked/net-line charts
    monthly_total, monthly_total_usd = {k: [] for k in KEYS}, {k: [] for k in KEYS}
    for i, tag in enumerate(months):
        for k in KEYS:
            parts = [monthly_by_instrument[instr][k][i] for instr, _, _ in INSTRUMENTS]
            if all(p is None for p in parts):
                monthly_total[k].append(None); monthly_total_usd[k].append(None)
            else:
                v = round(sum(p for p in parts if p is not None), 3)
                monthly_total[k].append(v)
                monthly_total_usd[k].append(usd(v, tag))

    # --- LT bonds only (unchanged legacy series) drives the seasonal / cumulative-FYTD tiles ---
    ltbonds_recs = recs_by_instr["ltbonds"]
    by = {(y, m): d for y, m, d in ltbonds_recs}
    monthly, monthly_usd = {k: [] for k in KEYS}, {k: [] for k in KEYS}
    for tag in months:
        y, mo = int(tag[:4]), int(tag[5:7])
        d = by.get((y, mo), {})
        for k in KEYS:
            v = d.get(k)
            monthly[k].append(v)
            monthly_usd[k].append(usd(v, tag))

    fys = sorted({(y if m >= 4 else y - 1) for y, m, d in ltbonds_recs})
    fys = [fy for fy in fys if fy >= 2021]
    fytd = {k: {} for k in KEYS}
    fytd_usd = {k: {} for k in KEYS}
    seasonal = {k: {} for k in KEYS}          # monthly (non-cumulative) net buying, Apr..Mar
    seasonal_usd = {k: {} for k in KEYS}
    for k in KEYS:
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

    as_of = max(months)
    doc = {
        "meta": {
            "as_of": as_of,
            "generated_at": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "unit": "JPY tn",
            "sign": "+ = net purchase of foreign securities (yen outflow); − = net sale / repatriation",
            "source": "MoF International Transactions in Securities — residents' net purchase of foreign securities by type of investor, split equity / LT bonds / ST bonds (monthb2/3/4.csv)",
            "source_url": "https://www.mof.go.jp/english/policy/international_policy/reference/itn_transactions_in_securities/index.htm",
        },
        "labels": {k: lab for _, k, lab in BUCKETS},
        "instrument_labels": {instr: lab for instr, _, lab in INSTRUMENTS},
        "order": ["banks", "trust_bank", "trust_pension", "life"],
        "months": months,
        # legacy LT-bond-only series — still drive the seasonal / cumulative-FYTD tiles
        "monthly": monthly,
        "monthly_usd": monthly_usd,
        # new: per-instrument monthly breakdown (equity / ltbonds / stbonds) + combined total, for the stacked/net-line charts
        "monthly_by_instrument": monthly_by_instrument,
        "monthly_by_instrument_usd": monthly_by_instrument_usd,
        "monthly_total": monthly_total,
        "monthly_total_usd": monthly_total_usd,
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
    print(f"as_of {as_of} · {len(months)} months · instruments {[i for i,_,_ in INSTRUMENTS]} -> mof_flows.json")

if __name__ == "__main__":
    main()
