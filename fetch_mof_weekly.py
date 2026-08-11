#!/usr/bin/env python3.12
"""Fetch MoF 'International Transactions in Securities' (Weekly; based on reports
from designated major investors) — the weekly release HanHan asked to chart
alongside the existing monthly Cross-border flows panels, in the same 2-line
(Assets vs Liabilities, net) format. Also pulls the Equities-vs-Long-term-debt
sub-breakdown for each side, to match Nomura's own Fig 16/17 weekly-flow chart
layout (two side-by-side panels, each an Equities/Long-term-debt 2-line chart).

Source: single historical CSV covering the full series since 2005-01:
  https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv
  (cp932-encoded columns, 0-indexed:
   Section 1 = Portfolio Investment Assets [residents' net purchase of FOREIGN
   securities]: col 3 = Equity Net, col 6 = Long-term debt Net, col 11 = Total Net.
   Section 2 = Portfolio Investment Liabilities [non-residents' net purchase of
   JAPANESE securities]: col 14 = Equity Net, col 17 = Long-term debt Net, col 22 = Total Net.)

Sign convention (post-2014): + = net purchase / inflow of capital in that
direction, − = net sale / repatriation. Values are 億円 (100mn yen); we output
¥tn (÷10000), matching fetch_mof_flows.py's units.

Outputs mof_weekly.json with net series (Assets/Liabilities = outward/inward,
each split into equity/ltdebt/total) from START, ¥tn and $bn.
Run: python3.12 fetch_mof_weekly.py
"""
import urllib.request, csv, io, json, os, re, datetime

URL = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv"
UA = {"User-Agent": "Mozilla/5.0"}
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "mof_source"); os.makedirs(SRC, exist_ok=True)
START = "2021-04-01"   # match fetch_mof_flows.py's monthly window for visual consistency

PERIOD_RE = re.compile(r"^(\d+)．(\d+)．(\d+)〜\s*(?:(\d+)．)?(\d+)．(\d+)$")

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()

def num(x):
    x = (x or "").replace(",", "").strip()
    if x in ("", "-", "―"): return None
    try: return float(x)
    except ValueError: return None

def parse_period(s):
    s = s.replace("～", "〜").strip()
    m = PERIOD_RE.match(s)
    if not m: return None
    sy, sm, sd, ey, em, ed = m.groups()
    sy, sm, sd, em, ed = int(sy), int(sm), int(sd), int(em), int(ed)
    ey = int(ey) if ey else sy
    try:
        start = datetime.date(sy, sm, sd)
        end = datetime.date(ey, em, ed)
    except ValueError:
        return None
    return start, end

def usdjpy_daily():
    """Daily USDJPY close from Yahoo, {date: rate}. Empty dict on failure."""
    try:
        j = json.loads(get("https://query1.finance.yahoo.com/v8/finance/chart/JPY=X?interval=1d&range=6y").decode())
        res = j["chart"]["result"][0]
        ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
        out = {}
        for t, c in zip(ts, cl):
            if c is None: continue
            d = datetime.datetime.utcfromtimestamp(t).date()
            out[d] = round(float(c), 3)
        return out
    except Exception as e:
        print("usdjpy fetch failed:", e); return {}

def main():
    raw = get(URL)
    open(os.path.join(SRC, "week.csv"), "wb").write(raw)
    rows = list(csv.reader(io.StringIO(raw.decode("cp932"))))

    recs = []  # (end_date, period_label, assets_net, assets_eq, assets_ltd, liab_net, liab_eq, liab_ltd) — yen100mn
    for r in rows:
        if not r or not r[0].strip():
            continue
        parsed = parse_period(r[0].strip())
        if not parsed:
            continue
        if len(r) <= 22:
            continue
        start, end = parsed
        assets_net = num(r[11])
        liab_net = num(r[22])
        if assets_net is None and liab_net is None:
            continue
        assets_eq, assets_ltd = num(r[3]), num(r[6])
        liab_eq, liab_ltd = num(r[14]), num(r[17])
        label = f"{start.month}/{start.day}–{end.month}/{end.day}"
        recs.append((end, label, assets_net, assets_eq, assets_ltd, liab_net, liab_eq, liab_ltd))

    recs.sort(key=lambda x: x[0])
    start_cutoff = datetime.date.fromisoformat(START)
    recs = [r for r in recs if r[0] >= start_cutoff]

    fx = usdjpy_daily()
    fx_dates = sorted(fx)
    def rate(d):
        if d in fx: return fx[d]
        earlier = [dd for dd in fx_dates if dd <= d]
        if earlier: return fx[earlier[-1]]
        return fx[fx_dates[0]] if fx_dates else None
    def usd(v, d):
        r = rate(d)
        return round(v * 1000.0 / r, 2) if (v is not None and r) else None

    def tn(v):
        return round(v / 10000.0, 3) if v is not None else None

    weeks = [r[0].isoformat() for r in recs]
    week_labels = [r[1] for r in recs]
    assets_net = [tn(r[2]) for r in recs]
    assets_eq = [tn(r[3]) for r in recs]
    assets_ltd = [tn(r[4]) for r in recs]
    liab_net = [tn(r[5]) for r in recs]
    liab_eq = [tn(r[6]) for r in recs]
    liab_ltd = [tn(r[7]) for r in recs]
    assets_net_usd = [usd(tn(r[2]), r[0]) for r in recs]
    assets_eq_usd = [usd(tn(r[3]), r[0]) for r in recs]
    assets_ltd_usd = [usd(tn(r[4]), r[0]) for r in recs]
    liab_net_usd = [usd(tn(r[5]), r[0]) for r in recs]
    liab_eq_usd = [usd(tn(r[6]), r[0]) for r in recs]
    liab_ltd_usd = [usd(tn(r[7]), r[0]) for r in recs]

    as_of = weeks[-1] if weeks else None
    doc = {
        "meta": {
            "as_of": as_of,
            "generated_at": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "unit": "JPY tn",
            "sign": "+ = net purchase (capital flow in that direction); − = net sale / repatriation",
            "source": "MoF International Transactions in Securities (Weekly; based on reports from designated major investors) — Portfolio Investment Assets (residents' net purchase of foreign securities) vs Portfolio Investment Liabilities (non-residents' net purchase of Japanese securities), each split into Equity & investment fund shares vs Long-term debt securities",
            "source_url": "https://www.mof.go.jp/english/policy/international_policy/reference/itn_transactions_in_securities/index.htm",
        },
        "weeks": weeks,
        "week_labels": week_labels,
        "assets_net": assets_net,
        "assets_net_usd": assets_net_usd,
        "assets_eq": assets_eq,
        "assets_eq_usd": assets_eq_usd,
        "assets_ltd": assets_ltd,
        "assets_ltd_usd": assets_ltd_usd,
        "liab_net": liab_net,
        "liab_net_usd": liab_net_usd,
        "liab_eq": liab_eq,
        "liab_eq_usd": liab_eq_usd,
        "liab_ltd": liab_ltd,
        "liab_ltd_usd": liab_ltd_usd,
    }
    for dest in (os.path.join(HERE, "mof_weekly.json"),):
        json.dump(doc, open(dest, "w"), ensure_ascii=False, indent=1)
    print(f"as_of {as_of} · {len(weeks)} weeks -> mof_weekly.json")

if __name__ == "__main__":
    main()
