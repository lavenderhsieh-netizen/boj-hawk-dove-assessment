#!/usr/bin/env python3.12
"""Japanese household financial assets by type — full quarterly time series.

Source: BOJ Time-Series Data Search API (official, no key required),
  https://www.stat-search.boj.or.jp/api/v1/getDataCode?db=FF&code=...
  DB=FF (Flow of Funds, Quarterly Data), sector "Households" (FFAS430),
  Stock (levels), Assets side. Quarterly since 1997Q4 (199704) through the
  latest available quarter. Same discovery method / same DB as
  fetch_jgb_holders_timeseries.py — see that script's docstring.

Six buckets shown (matches the standard MOF/BOJ household-asset-mix framing,
e.g. MOF's own "現金・預金/保険・年金・定型保証/株式等/投資信託受益証券/
債務証券/その他" split cited in "国の財務書類" appendices):
  Currency and deposits                     FOF_FFAS430A100
  Insurance, pensions & standardized
    guarantees (life insurance + annuity/
    pension entitlements + non-life
    reserves)                               FOF_FFAS430A400
  Equity (listed + unlisted + other)        FOF_FFAS430A330
  Investment trust beneficiary certificates FOF_FFAS430A318
  Debt securities (JGBs, munis, corp
    bonds, bank debentures, etc.)           FOF_FFAS430A300
  Other (residual: loans as creditor,
    financial derivatives, deposits money,
    trade credits, accounts receivable,
    outward securities investment)          Total minus the 5 above
  Total financial assets                    FOF_FFAS430A900

Usage: python3.12 fetch_household_assets.py
"""
import json
import os

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "household_assets.json")
UA = {"User-Agent": "Mozilla/5.0"}
API = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"

CODES = {
    "Currency and deposits": "FOF_FFAS430A100",
    "Insurance, pensions & standardized guarantees": "FOF_FFAS430A400",
    "Equity": "FOF_FFAS430A330",
    "Investment trust beneficiary certificates": "FOF_FFAS430A318",
    "Debt securities": "FOF_FFAS430A300",
}
TOTAL_CODE = "FOF_FFAS430A900"
JGB_CODE = "FOF_FFAS430A311"  # sub-item of Debt securities, for the note/KPI only


def fetch():
    code_list = ",".join(list(CODES.values()) + [TOTAL_CODE, JGB_CODE])
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
    """See fetch_jgb_holders_timeseries.py — Q1=Mar-end, Q2=Jun-end, Q3=Sep-end, Q4=Dec-end."""
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
            v_tn = round(v / 1e4, 2) if v is not None else None
            row[name] = v_tn
            if v_tn is not None:
                named_sum += v_tn
        row["Other"] = round(total_tn - named_sum, 2)
        jgb = series[JGB_CODE].get(d)
        row["of which: JGBs (excl. T-Bills)"] = round(jgb / 1e4, 2) if jgb is not None else None
        out.append(row)

    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {OUT} — {len(out)} quarters, {out[0]['as_of']} to {out[-1]['as_of']}")
    latest = out[-1]
    print(f"  latest ({latest['as_of']}): total {latest['total_jpy_tn']} tn")
    for k in list(CODES.keys()) + ["Other"]:
        print(f"    {k:<50} {latest[k]:>9.1f} tn  ({round(latest[k]/latest['total_jpy_tn']*100,1)}%)")


if __name__ == "__main__":
    main()
