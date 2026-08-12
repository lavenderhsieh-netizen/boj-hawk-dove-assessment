#!/usr/bin/env python3.12
"""JGB (excl. T-Bills) holdings by holder sector — full quarterly time series.

Source: BOJ Time-Series Data Search API (official, no key required),
  https://www.stat-search.boj.or.jp/api/v1/getDataCode?db=FF&code=...
  DB=FF (Flow of Funds, Quarterly Data), item "Central government securities
  and FILP bonds" (BOJ's own "Db" item — i.e. JGBs + FILP bonds, EXCLUDING
  Treasury discount bills "Da"/T-Bills), Stock (levels), Assets side, one
  series per holder sector. Quarterly since 1997Q4 (199704) through the
  latest available quarter.

This supersedes the old jgb_holders_history.json, which was a sparse,
hand-curated set of 6 snapshots recovered from web.archive.org captures of
sjpre.xlsx (BOJ doesn't keep a stable download link for *past quarters* of
that "Preliminary Figures" file). The BOJ Time-Series Data Search API turns
out to carry the full history directly — no archive-scavenging needed. This
was discovered the same way fetch_boj_balance_sheet.py found DB=BS01/FM05/
MD06: browsing https://www.stat-search.boj.or.jp/api/v1/getMetadata?db=FF
for series whose name contains "Households" / "Central government
securities and FILP bonds" / "Stock".

Series codes (FOF_FFAS<sector><item>, item 311 = "Db"):
  Bank of Japan (central bank)         FOF_FFAS110A311
  Banks (depository corporations)      FOF_FFAS120A311
  Insurance companies                  FOF_FFAS131A311
  Public pensions (of which, w/in
    social security funds — incl GPIF) FOF_FFAS424A311
  Pension funds (corporate/other)      FOF_FFAS140A311
  Investment trusts (securities
    investment trusts)                 FOF_FFAS160A311
  Overseas (foreign investors)         FOF_FFAS500A311
  Households                           FOF_FFAS430A311
  Total (all sectors, incl. residual
    — nonfin. corp/gov't/local govt/
    PNPISH/other financial intermed.)  FOF_FFAS700A311

Same 8 named categories as jgb_holders.json's snapshot (fetch_jgb_holders.py)
— "Other" here is the residual (Total minus the 8 named sectors), matching
that file's own "Other (nonfin. corp, gov't, other financial intermediaries)"
bucket definition.

Usage: python3.12 fetch_jgb_holders_timeseries.py
"""
import json
import os

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "jgb_holders_history.json")
UA = {"User-Agent": "Mozilla/5.0"}
API = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"

CODES = {
    "Bank of Japan": "FOF_FFAS110A311",
    "Banks": "FOF_FFAS120A311",
    "Insurance companies": "FOF_FFAS131A311",
    "Public pensions (incl. GPIF)": "FOF_FFAS424A311",
    "Pension funds (corporate/other)": "FOF_FFAS140A311",
    "Investment trusts": "FOF_FFAS160A311",
    "Overseas (foreign investors)": "FOF_FFAS500A311",
    "Households": "FOF_FFAS430A311",
}
TOTAL_CODE = "FOF_FFAS700A311"


def fetch():
    code_list = ",".join(list(CODES.values()) + [TOTAL_CODE])
    url = f"{API}?format=json&lang=en&db=FF&code={code_list}"
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    j = r.json()
    if j.get("STATUS") != 200:
        raise RuntimeError(f"BOJ API error: {j}")
    series = {}
    for row in j["RESULTSET"]:
        dates = row["VALUES"]["SURVEY_DATES"]
        vals = row["VALUES"]["VALUES"]
        series[row["SERIES_CODE"]] = dict(zip(dates, vals))
    return series


def yyyymm_to_quarter_label(yyyymm):
    """BOJ FF survey dates encode calendar-quarter-end as YYYYQ, Q in 1-4.

    Q1=end of March, Q2=end of June, Q3=end of September, Q4=end of December,
    all within calendar year YYYY (verified: 202601 == "End of March 2026",
    matching jgb_holders.json's separately-fetched sjpre.xlsx snapshot).
    """
    y = yyyymm // 100
    q = yyyymm % 100
    end_month = {1: "March", 2: "June", 3: "September", 4: "December"}[q]
    return f"End of {end_month} {y}"


def main():
    series = fetch()
    all_dates = sorted(set(series[TOTAL_CODE].keys()))

    out = []
    for d in all_dates:
        total = series[TOTAL_CODE].get(d)
        if total is None:
            continue
        total_tn = round(total / 1e4, 2)
        row = {"date": d, "as_of": yyyymm_to_quarter_label(d), "total_jpy_tn": total_tn}
        named_sum = 0.0
        for name, code in CODES.items():
            v = series[code].get(d)
            if v is None:
                v_tn = None
            else:
                v_tn = round(v / 1e4, 2)
                named_sum += v_tn
            row[name] = v_tn
        row["Other (nonfin. corp, gov't, other financial intermediaries)"] = (
            round(total_tn - named_sum, 2) if total_tn is not None else None
        )
        out.append(row)

    OUT_PATH = OUT
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {OUT_PATH} — {len(out)} quarters, {out[0]['as_of']} to {out[-1]['as_of']}")
    print(f"  latest: total {out[-1]['total_jpy_tn']} tn, BOJ {out[-1]['Bank of Japan']} tn "
          f"({round(out[-1]['Bank of Japan']/out[-1]['total_jpy_tn']*100,1)}%)")


if __name__ == "__main__":
    main()
