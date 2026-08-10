#!/usr/bin/env python3.12
"""Fetch MoF Balance-of-Payments headline series: Current account (SA, by
component) and Direct investment balance (outward vs inward).

New cards HanHan asked for after sharing Nomura research charts (Fig.10
current-account-balance-SA, Fig.11 direct-investment-balance), 2026-08-11.
Neither series existed on this dashboard before — the existing mof_bop.json
only covers securities (portfolio investment) flows by country.

Sources — MoF's own official time-series CSVs (revised/official, NOT the
preliminary press-release PDF used elsewhere; these are the actual
"国際収支の推移" trend-data downloads, static filenames, updated monthly):
  - https://www.mof.go.jp/policy/international_policy/reference/balance_of_payments/bp_trend/bpnet/sbp/s-a/6s-a-2.csv
    "季節調整済み国際収支の推移（月次）" — Seasonally-adjusted Current account, monthly,
    Jan 1996–present. Columns (0-indexed after the 4 label cols):
    4=Current account, 5=Goods&services, 6=Goods(trade balance), 7=Exports,
    8=Imports, 9=Services, 10=Primary income, 11=Secondary income.
  - .../bp_trend/bpnet/sbp/s-1/6s-1-4.csv  "国際収支総括表（月次）" — the SAME table,
    "Not seasonally adjusted" (原数値), same column layout. Added 2026-08-11
    (HanHan asked "possible to have NSA version?"). Found by reading bpnet.htm's
    own CSV list: 6s-1-* is the un-adjusted family (calendar/fiscal/quarter/month),
    6s-a-* is explicitly labelled "季節調整済" — the SA-only variant used above.
    There is no separate NSA URL for direct investment; that series is already
    NSA-only at the source (MoF doesn't seasonally adjust FDI), see below.
  - .../bp_trend/bpfdi/fdi/6d-0-4.csv  "対外直接投資総括表（月次）" — Outward FDI
    (Direct Investment Assets), monthly, NOT seasonally adjusted. Row[6] = Net total.
  - .../bp_trend/bpfdi/fdi/6d-1-4.csv  "対内直接投資総括表（月次）" — Inward FDI
    (Direct Investment Liabilities), same layout, row[6] = Net total.

Units: 億円 (100mn yen) in the source; output ¥tn (÷10000). "(P)" suffixes on
recent months (preliminary) are stripped from the label but not flagged
separately — matches this project's existing convention for MoF releases.

Sign: Current-account components use MoF's own sign (+ = surplus/receipts).
Outward FDI: + = net outflow (residents investing abroad). Inward FDI: sourced
as MoF's own + = net inflow (liabilities increase); plotted as a NEGATIVE bar
(opposite direction to outward) so the two visually net against each other,
matching Nomura's Fig.11 convention. direct_investment_balance = outward - inward.

USD conversion (added 2026-08-11): monthly USDJPY close from Yahoo Finance
(JPY=X, interval=1mo, range=max — same `usdjpy_monthly()` pattern already used
in fetch_mof_flows.py), $bn = ¥tn * 1000 / rate. Every ¥tn series above also
gets a `_usd` sibling with identical shape. Months with no Yahoo close use the
nearest earlier month's rate (same fallback as fetch_mof_flows.py).

Output: mof_bop_summary.json (root + streamlit_app/ copies), independent of
mof_bop.json (which has its own delicate outbound_sov-preservation logic —
see fetch_mof_bop.py's own comments; do not merge this into that file).

Run: python3.12 fetch_mof_bop_summary.py
"""
import urllib.request, csv, io, json, os, datetime

BASE = "https://www.mof.go.jp/policy/international_policy/reference/balance_of_payments/bp_trend/{path}"
CA_URL = BASE.format(path="bpnet/sbp/s-a/6s-a-2.csv")
CA_NSA_URL = BASE.format(path="bpnet/sbp/s-1/6s-1-4.csv")
FDI_OUT_URL = BASE.format(path="bpfdi/fdi/6d-0-4.csv")
FDI_IN_URL = BASE.format(path="bpfdi/fdi/6d-1-4.csv")
UA = {"User-Agent": "Mozilla/5.0"}
HERE = os.path.dirname(os.path.abspath(__file__))
START = "2015-01"   # matches Nomura Fig.10's chart window; source goes back to 1996 if ever wanted
CA_KEYS = ("current_account", "goods_services", "goods", "exports",
           "imports", "services", "primary_income", "secondary_income")

MN = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
      "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def num(s):
    s = s.strip()
    if not s or s == "--":
        return None
    return float(s.replace(",", ""))


def rows_of(url):
    data = get(url)
    return list(csv.reader(io.StringIO(data.decode("cp932", errors="ignore"))))


def month_tag(row):
    """row[2]=EN year (only on Jan rows), row[3]=EN month e.g. 'Jun(P)'."""
    global _last_year
    if row[2]:
        _last_year = int(row[2])
    mon = row[3].replace("(P)", "").strip()
    if mon not in MN or _last_year is None:
        return None
    return f"{_last_year}-{MN[mon]:02d}"


def fetch_current_account(url):
    global _last_year
    _last_year = None
    rows = rows_of(url)
    out = {}
    for row in rows:
        if len(row) < 12 or not row[3]:
            continue
        tag = month_tag(row)
        if not tag or tag < START:
            continue
        try:
            out[tag] = {
                "current_account": num(row[4]),
                "goods_services": num(row[5]),
                "goods": num(row[6]),
                "exports": num(row[7]),
                "imports": num(row[8]),
                "services": num(row[9]),
                "primary_income": num(row[10]),
                "secondary_income": num(row[11]),
            }
        except (ValueError, IndexError):
            continue
    return out


def usdjpy_monthly():
    """Monthly USDJPY close from Yahoo, {YYYY-MM: rate}. Empty dict on failure.
    Same pattern as fetch_mof_flows.py's usdjpy_monthly(), but range=max since
    this series needs to cover the full 2015-present window (flows only needs
    ~4y)."""
    try:
        j = json.loads(get("https://query1.finance.yahoo.com/v8/finance/chart/JPY=X?interval=1mo&range=max").decode())
        res = j["chart"]["result"][0]
        ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
        out = {}
        for t, c in zip(ts, cl):
            if c is None:
                continue
            d = datetime.datetime.fromtimestamp(t, datetime.UTC)
            out[f"{d.year}-{d.month:02d}"] = round(float(c), 3)
        return out
    except Exception as e:
        print("usdjpy fetch failed:", e)
        return {}


def fetch_fdi_net(url):
    global _last_year
    _last_year = None
    rows = rows_of(url)
    out = {}
    for row in rows:
        if len(row) < 16 or not row[3]:
            continue
        tag = month_tag(row)
        if not tag or tag < START:
            continue
        try:
            out[tag] = num(row[6])   # Total, Net
        except (ValueError, IndexError):
            continue
    return out


def main():
    ca = fetch_current_account(CA_URL)
    ca_nsa = fetch_current_account(CA_NSA_URL)
    fdi_out = fetch_fdi_net(FDI_OUT_URL)
    fdi_in = fetch_fdi_net(FDI_IN_URL)

    months = sorted(set(ca) | set(ca_nsa) | set(fdi_out) | set(fdi_in))
    TN = lambda v: round(v / 10000.0, 3) if v is not None else None  # 億円 -> ¥tn

    fx = usdjpy_monthly()
    def rate(tag):
        if tag in fx:
            return fx[tag]
        earlier = [v for k, v in sorted(fx.items()) if k <= tag]
        return earlier[-1] if earlier else (sorted(fx.values())[len(fx) // 2] if fx else None)
    def usd(v, tag):
        r = rate(tag)
        return round(v * 1000.0 / r, 2) if (v is not None and r) else None

    def ca_block(src):
        jpy = {k: [TN(src.get(m, {}).get(k)) for m in months] for k in CA_KEYS}
        usdv = {k: [usd(v, m) for v, m in zip(jpy[k], months)] for k in CA_KEYS}
        return jpy, usdv

    current_account, current_account_usd = ca_block(ca)
    current_account_nsa, current_account_nsa_usd = ca_block(ca_nsa)

    outward = [TN(fdi_out.get(m)) for m in months]
    inward = [TN(fdi_in.get(m)) for m in months]
    # Flow-consistent sign convention (2026-08-11, HanHan): residents' outward FDI is a capital
    # OUTFLOW -> negative; non-residents' inward FDI is a capital INFLOW -> positive (already the
    # raw sign from source). balance = inward - outward, + = net capital inflow to Japan.
    outward_flipped = [(-v if v is not None else None) for v in outward]
    balance = [round(i - o, 3) if (o is not None and i is not None) else None
               for o, i in zip(outward, inward)]
    outward_flipped_usd = [usd(v, m) for v, m in zip(outward_flipped, months)]
    outward_raw_usd = [usd(v, m) for v, m in zip(outward, months)]
    inward_usd = [usd(v, m) for v, m in zip(inward, months)]
    balance_usd = [usd(v, m) for v, m in zip(balance, months)]

    doc = {
        "meta": {
            "as_of": months[-1] if months else None,
            "generated_at": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat(),
            "unit": "JPY tn (or USD bn in the _usd fields)",
            "current_account_note": "current_account = seasonally adjusted; current_account_nsa = not "
                                     "seasonally adjusted (原数値), same MoF table family, added 2026-08-11 "
                                     "at HanHan's request. + = current account surplus / net receipts.",
            "direct_investment_note": "Not seasonally adjusted (MoF does not publish an SA version of FDI). "
                                       "Flow-consistent sign convention (updated 2026-08-11): residents' outward "
                                       "FDI is a capital outflow, sign-flipped to plot as a negative bar; "
                                       "non-residents' inward FDI is a capital inflow, plotted as-is (positive), "
                                       "matching the sign convention used elsewhere on this dashboard (outflow = "
                                       "negative, inflow = positive). direct_investment_balance = inward - outward "
                                       "(+ = net capital inflow to Japan).",
            "usd_note": "_usd fields converted at each month's own USDJPY close (Yahoo Finance JPY=X, monthly), "
                        "$bn = ¥tn * 1000 / rate — same conversion convention as mof_flows.json.",
            "source": "Ministry of Finance Japan — official Balance of Payments trend-data CSVs "
                      "(国際収支総括表 SA + NSA / 対外・対内直接投資総括表), monthly, revised basis "
                      "(not the preliminary press-release PDF)",
            "source_url": "https://www.mof.go.jp/policy/international_policy/reference/balance_of_payments/data.htm",
        },
        "months": months,
        "current_account": current_account,
        "current_account_usd": current_account_usd,
        "current_account_nsa": current_account_nsa,
        "current_account_nsa_usd": current_account_nsa_usd,
        "direct_investment": {
            "outward": outward,
            "outward_flipped": outward_flipped,
            "inward": inward,
            "balance": balance,
            "outward_usd": outward_raw_usd,
            "outward_flipped_usd": outward_flipped_usd,
            "inward_usd": inward_usd,
            "balance_usd": balance_usd,
        },
    }
    for dest in (os.path.join(HERE, "mof_bop_summary.json"),
                 os.path.join(HERE, "streamlit_app", "mof_bop_summary.json")):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        json.dump(doc, open(dest, "w"), ensure_ascii=False, indent=1)
    print(f"months {len(months)} ({months[0] if months else '-'}..{months[-1] if months else '-'}) "
          f"-> mof_bop_summary.json  CA(SA) latest={current_account['current_account'][-1] if months else None} "
          f"CA(NSA) latest={current_account_nsa['current_account'][-1] if months else None} "
          f"FDI bal latest={balance[-1] if months else None}")


if __name__ == "__main__":
    main()
