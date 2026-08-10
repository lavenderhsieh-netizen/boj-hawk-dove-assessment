#!/usr/bin/env python3.12
"""Fetch MoF 'International Transactions in Securities' (Weekly; based on reports
from designated major investors) — the weekly release HanHan asked to chart
alongside the existing monthly Cross-border flows panels, in the same 2-line
(Assets vs Liabilities, net) format.

Source: single historical CSV covering the full series since 2005-01:
  https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv
  (cp932-encoded; col 11 = Total Net, Portfolio Investment Assets [residents'
  net purchase of FOREIGN securities]; col 22 = Total Net, Portfolio Investment
  Liabilities [non-residents' net purchase of JAPANESE securities])

Sign convention (post-2014): + = net purchase / inflow of capital in that
direction, − = net sale / repatriation. Values are 億円 (100mn yen); we output
¥tn (÷10000), matching fetch_mof_flows.py's units.

Outputs mof_weekly.json with two net series (Assets = outward, Liabilities =
inward) from START, ¥tn and $bn.
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

    recs = []  # (end_date, period_label, assets_net_yen100mn, liab_net_yen100mn)
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
        label = f"{start.month}/{start.day}–{end.month}/{end.day}"
        recs.append((end, label, assets_net, liab_net))

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

    weeks = [r[0].isoformat() for r in recs]
    week_labels = [r[1] for r in recs]
    assets_net = [round(r[2] / 10000.0, 3) if r[2] is not None else None for r in recs]
    liab_net = [round(r[3] / 10000.0, 3) if r[3] is not None else None for r in recs]
    assets_net_usd = [usd(r[2] / 10000.0 if r[2] is not None else None, r[0]) for r in recs]
    liab_net_usd = [usd(r[3] / 10000.0 if r[3] is not None else None, r[0]) for r in recs]

    as_of = weeks[-1] if weeks else None
    doc = {
        "meta": {
            "as_of": as_of,
            "generated_at": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "unit": "JPY tn",
            "sign": "+ = net purchase (capital flow in that direction); − = net sale / repatriation",
            "source": "MoF International Transactions in Securities (Weekly; based on reports from designated major investors) — Total Net, Portfolio Investment Assets (residents' net purchase of foreign securities) vs Total Net, Portfolio Investment Liabilities (non-residents' net purchase of Japanese securities)",
            "source_url": "https://www.mof.go.jp/english/policy/international_policy/reference/itn_transactions_in_securities/index.htm",
        },
        "weeks": weeks,
        "week_labels": week_labels,
        "assets_net": assets_net,
        "assets_net_usd": assets_net_usd,
        "liab_net": liab_net,
        "liab_net_usd": liab_net_usd,
    }
    for dest in (os.path.join(HERE, "mof_weekly.json"),):
        json.dump(doc, open(dest, "w"), ensure_ascii=False, indent=1)
    print(f"as_of {as_of} · {len(weeks)} weeks -> mof_weekly.json")

if __name__ == "__main__":
    main()
