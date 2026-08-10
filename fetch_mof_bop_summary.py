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

Output: mof_bop_summary.json (root + streamlit_app/ copies), independent of
mof_bop.json (which has its own delicate outbound_sov-preservation logic —
see fetch_mof_bop.py's own comments; do not merge this into that file).

Run: python3.12 fetch_mof_bop_summary.py
"""
import urllib.request, csv, io, json, os, datetime

BASE = "https://www.mof.go.jp/policy/international_policy/reference/balance_of_payments/bp_trend/{path}"
CA_URL = BASE.format(path="bpnet/sbp/s-a/6s-a-2.csv")
FDI_OUT_URL = BASE.format(path="bpfdi/fdi/6d-0-4.csv")
FDI_IN_URL = BASE.format(path="bpfdi/fdi/6d-1-4.csv")
UA = {"User-Agent": "Mozilla/5.0"}
HERE = os.path.dirname(os.path.abspath(__file__))
START = "2015-01"   # matches Nomura Fig.10's chart window; source goes back to 1996 if ever wanted

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


def fetch_current_account():
    global _last_year
    _last_year = None
    rows = rows_of(CA_URL)
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
    ca = fetch_current_account()
    fdi_out = fetch_fdi_net(FDI_OUT_URL)
    fdi_in = fetch_fdi_net(FDI_IN_URL)

    months = sorted(set(ca) | set(fdi_out) | set(fdi_in))
    TN = lambda v: round(v / 10000.0, 3) if v is not None else None  # 億円 -> ¥tn

    current_account = {k: [TN(ca.get(m, {}).get(k)) for m in months]
                        for k in ("current_account", "goods_services", "goods", "exports",
                                  "imports", "services", "primary_income", "secondary_income")}
    outward = [TN(fdi_out.get(m)) for m in months]
    inward = [TN(fdi_in.get(m)) for m in months]
    balance = [round(o - i, 3) if (o is not None and i is not None) else None
               for o, i in zip(outward, inward)]

    doc = {
        "meta": {
            "as_of": months[-1] if months else None,
            "generated_at": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat(),
            "unit": "JPY tn",
            "current_account_note": "Seasonally adjusted. + = current account surplus / net receipts.",
            "direct_investment_note": "Not seasonally adjusted. Outward: + = residents' net investment abroad "
                                       "(capital outflow). Inward is sourced as MoF's own + = net inflow, then "
                                       "sign-flipped for the chart so it plots as a negative bar (opposite "
                                       "direction to outward), matching Nomura's Fig.11 convention. "
                                       "direct_investment_balance = outward - inward (residents' outward minus non-residents' inward).",
            "source": "Ministry of Finance Japan — official Balance of Payments trend-data CSVs "
                      "(季節調整済み国際収支の推移 / 対外・対内直接投資総括表), monthly, revised basis "
                      "(not the preliminary press-release PDF)",
            "source_url": "https://www.mof.go.jp/policy/international_policy/reference/balance_of_payments/data.htm",
        },
        "months": months,
        "current_account": current_account,
        "direct_investment": {
            "outward": outward,
            "inward_flipped": [(-v if v is not None else None) for v in inward],
            "inward_raw": inward,
            "balance": balance,
        },
    }
    for dest in (os.path.join(HERE, "mof_bop_summary.json"),
                 os.path.join(HERE, "streamlit_app", "mof_bop_summary.json")):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        json.dump(doc, open(dest, "w"), ensure_ascii=False, indent=1)
    print(f"months {len(months)} ({months[0] if months else '-'}..{months[-1] if months else '-'}) "
          f"-> mof_bop_summary.json  CA latest={current_account['current_account'][-1] if months else None} "
          f"FDI bal latest={balance[-1] if months else None}")


if __name__ == "__main__":
    main()
