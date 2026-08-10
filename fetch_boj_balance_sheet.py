#!/usr/bin/env python3.12
"""BOJ Balance Sheet / QT tab — fetcher.

Builds boj_balance_sheet.json for the BOJ dashboard's "BOJ Balance Sheet" tab
(added 2026-08-09 per HanHan's expert-review doc, Section B).

Primary source: BOJ Time-Series Data Search API (official, no key required),
  https://www.stat-search.boj.or.jp/api/v1/getDataCode
  DB=BS01 "Bank of Japan Accounts" — monthly, back to 1998/04. This is the
  same underlying data as the "Accounts of the Bank of Japan" page
  (https://www.boj.or.jp/en/statistics/boj/other/acmai/, released ~10th/
  20th/month-end) but the API gives a clean end-of-month series instead of
  scraping ~30 individual HTML releases/year. Cross-checked against the
  acmai HTML releases directly (see AGENTS.md) — matches to the yen.

Secondary sources for derived-metric denominators:
  - MOF/BOJ JGB amount-outstanding: BOJ Time-Series API DB=FM05 (Ordinary
    Government Securities + Treasury Discount Bills, Amount Outstanding,
    monthly since 1966/1986) — used for "BOJ JGB holdings / total JGB
    outstanding".
  - Japan nominal GDP: Cabinet Office ESRI "Quarterly Estimates of GDP"
    CSV (nominal, original series, quarterly level) — used for "BOJ total
    assets / nominal GDP". Quarterly value annualised (x4) for the ratio.

This is a STATIC/occasional-refresh series (BOJ Accounts data updates only
~3x/month), same treatment as fetch_intervention.py / fetch_natural_rate.py
— NOT wired into any daily orchestrator (this project has none; each
fetch_*.py is its own standalone script, run by hand or its own scheduled
job). Re-run monthly-ish, or after a fresh BOJ Accounts release, to extend
the series.

Usage: python3.12 fetch_boj_balance_sheet.py
"""
import io
import json
import os
import re
import csv
import datetime

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "boj_balance_sheet.json")
UA = {"User-Agent": "Mozilla/5.0"}
API = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"

# BS01 series codes (Bank of Japan Accounts, monthly, 100-million-yen units)
BS01_CODES = {
    "total_assets":        "MABJMTA",     # Assets/Total (= Liabilities+Net Assets total)
    "jgs":                 "MABJMA5",     # Japanese Government Securities (JGB + FBs/T-Bills)
    "corporate_bonds":     "MABJMA002",   # Corporate Bonds
    "etf":                 "MABJMA003",   # Pecuniary trusts (ETFs held as trust property)
    "jreit":               "MABJMA004",   # Pecuniary trusts (J-REITs held as trust property)
    "loans":               "MABJMA@01",   # Loans and Discounts (total)
    "fx_assets":           "MABJMA12",    # Foreign Currency Assets
    "banknotes":           "MABJML1",     # Banknotes
    "current_deposits":    "MABJML11",    # Current Deposits (reserves / current-account balances)
    "govt_deposits":       "MABJML3",     # Deposits of the Government
    "repo_liabilities":    "MABJML8",     # Payables under Repurchase Agreements
    "other_deposits":      "MABJML4",     # Other Deposits
}

# FM05 series codes (JGB amount outstanding, monthly, 100-million-yen units)
FM05_CODES = {
    "jgb_outstanding_ordinary": "SMBIT1OG",   # Ordinary Government Securities, Amount Outstanding
    "jgb_outstanding_tbills":   "SMBIT1TF1",  # Treasury Discount Bills, Amount Outstanding
}

# MD06 series codes ("Sources of Changes in Current Account Balances and Market
# Operations") — monthly gross JGB purchase operations, doc Section C's "BOJ JGB
# purchase operations" panel. Not broken out by maturity bucket (that level of detail
# is only in BOJ's daily operation-result releases, not this clean time series) but
# gives a genuine, official monthly gross-purchases series — the cleanest available
# read on the pace of the purchase taper.
MD06_CODES = {
    "jgb_purchases_outright": "MASDM58",   # Outright Purchases of JGBs (monthly, since 1960)
    "tbill_purchases_outright": "MASDM5A@",  # Outright Purchases of T-Bills (monthly, since 1999)
}

START = "2012-01"  # doc asks for "since 2012" charts; BOJ API actually carries back to 1998/04


def boj_api_fetch(db, codes):
    """Call BOJ Time-Series Data Search API getDataCode; returns {out_key: {yyyymm: value_100mn_yen}}."""
    code_list = ",".join(codes.values())
    url = f"{API}?db={db}&code={code_list}&format=json"
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    j = r.json()
    if j.get("STATUS") != 200:
        raise RuntimeError(f"BOJ API error for db={db}: {j.get('MESSAGE')}")
    by_series_code = {s["SERIES_CODE"]: s for s in j["RESULTSET"]}
    out = {}
    for out_key, series_code in codes.items():
        s = by_series_code.get(series_code)
        if s is None:
            raise RuntimeError(f"BOJ API: series {series_code} ({out_key}) not returned")
        dates = s["VALUES"]["SURVEY_DATES"]
        vals = s["VALUES"]["VALUES"]
        out[out_key] = {str(d): v for d, v in zip(dates, vals) if v is not None}
    return out


def gdp_nominal_quarterly():
    """Japan nominal GDP, quarterly level (original series), ¥tn — from Cabinet Office ESRI.
    Returns {yyyy-Qn: value_jpy_tn}. Best-effort; returns {} on failure (ratio just omitted)."""
    try:
        # Discover the current release folder (e.g. "2026/qe261_2") from the EN landing page's
        # own link, rather than guessing the CSV path — ESRI's folder-naming suffix (plain
        # "qe261" 1st-preliminary vs "qe261_2" 2nd-preliminary) changes each release.
        r = requests.get("https://www.esri.cao.go.jp/en/sna/sokuhou/sokuhou_top.html", headers=UA, timeout=30)
        m = re.search(r'(/en/sna/data/sokuhou/files/\d{4}/qe\d+(?:_\d+)?/gdemenuea\.html)', r.text)
        if not m:
            return {}
        # Fetch the release's own EN menu page and pull its actual "gaku-mg*.csv" (nominal
        # original-series level table) link — the CSV filename suffix doesn't map predictably
        # from the folder name (e.g. folder "qe261_2" -> file "gaku-mg2612.csv"), so scrape it.
        menu = requests.get("https://www.esri.cao.go.jp" + m.group(1), headers=UA, timeout=30)
        m2 = re.search(r'href="(/jp/sna/data/data_list/sokuhou/files/[^"]*gaku-mg\d+\.csv)"', menu.text)
        if not m2:
            return {}
        url = "https://www.esri.cao.go.jp" + m2.group(1)
        resp = requests.get(url, headers=UA, timeout=30)
        if resp.status_code != 200 or len(resp.content) < 500:
            return {}
        rows = list(csv.reader(io.StringIO(resp.content.decode("cp932", errors="replace"))))
        out = {}
        yr = None
        for row in rows:
            if not row or not row[0].strip():
                continue
            label = row[0].strip()
            m2 = re.match(r"^(\d{4})/\s*(\d{1,2})-\s*\d{1,2}\.?$", label)
            m3 = re.match(r"^(\d{1,2})-\s*\d{1,2}\.?$", label)
            if m2:
                yr, mo = int(m2.group(1)), int(m2.group(2))
            elif m3 and yr is not None:
                mo = int(m3.group(1))
                if mo == 1 and out:
                    yr += 1
            else:
                continue
            try:
                val = float(row[1].replace(",", "").strip())
            except (ValueError, IndexError):
                continue
            q = (mo - 1) // 3 + 1
            out[f"{yr}-Q{q}"] = round(val / 1000.0, 2)  # billion yen -> tn yen
        return out
    except Exception as e:
        print("gdp fetch failed:", e)
        return {}


def to_monthly_series(months, raw, scale=1.0):
    """raw: {yyyymm: value_100mn_yen} -> list aligned to `months` (¥tn, None if missing)."""
    out = []
    for m in months:
        key = m.replace("-", "")
        v = raw.get(key)
        out.append(round(v / 10000.0 * scale, 3) if v is not None else None)
    return out


def main():
    bs01 = boj_api_fetch("BS01", BS01_CODES)
    fm05 = boj_api_fetch("FM05", FM05_CODES)
    md06 = boj_api_fetch("MD06", MD06_CODES)

    all_months = sorted(set().union(*[set(d.keys()) for d in bs01.values()]))
    months = [f"{m[:4]}-{m[4:]}" for m in all_months if m >= START.replace("-", "")]

    series = {k: to_monthly_series(months, v) for k, v in bs01.items()}
    fm05_series = {k: to_monthly_series(months, v) for k, v in fm05.items()}
    md06_series = {k: to_monthly_series(months, v) for k, v in md06.items()}

    # derived: JGS share of total assets
    jgs_share = [round(j / t * 100, 2) if (j is not None and t) else None
                 for j, t in zip(series["jgs"], series["total_assets"])]

    # derived: total JGB outstanding (ordinary bonds + T-bills), and BOJ JGS / that total
    jgb_outstanding = [round(a + b, 3) if (a is not None and b is not None) else None
                        for a, b in zip(fm05_series["jgb_outstanding_ordinary"], fm05_series["jgb_outstanding_tbills"])]
    boj_share_of_jgb = [round(j / o * 100, 2) if (j is not None and o) else None
                         for j, o in zip(series["jgs"], jgb_outstanding)]

    # derived: monthly change in JGB holdings (¥tn)
    jgs_mom = [None] + [round(series["jgs"][i] - series["jgs"][i - 1], 3)
                          if (series["jgs"][i] is not None and series["jgs"][i - 1] is not None) else None
                          for i in range(1, len(series["jgs"]))]

    # derived: 12-month change in JGB holdings (¥tn)
    jgs_yoy = [None] * 12 + [round(series["jgs"][i] - series["jgs"][i - 12], 3)
                               if (series["jgs"][i] is not None and series["jgs"][i - 12] is not None) else None
                               for i in range(12, len(series["jgs"]))]

    # derived: 3-month and 6-month cumulative change in JGB holdings (¥tn) — per HanHan's own
    # feedback doc Section 13: cumulative-change windows read the contraction pace more honestly
    # than an annualised %, since a single lumpy redemption quarter (see jgb_redemptions_implied_jpy_tn)
    # would otherwise get blown up 4x by the annualisation.
    def cumulative_change(window):
        return [None] * window + [
            round(series["jgs"][i] - series["jgs"][i - window], 3)
            if (series["jgs"][i] is not None and series["jgs"][i - window] is not None) else None
            for i in range(window, len(series["jgs"]))
        ]
    jgs_change_3m = cumulative_change(3)
    jgs_change_6m = cumulative_change(6)

    # derived: 3-month annualised balance-sheet contraction rate, % — total assets basis
    ta_3m_ann = [None, None, None] + [
        round(((series["total_assets"][i] / series["total_assets"][i - 3]) ** 4 - 1) * 100, 2)
        if (series["total_assets"][i] not in (None, 0) and series["total_assets"][i - 3] not in (None, 0))
        else None
        for i in range(3, len(series["total_assets"]))
    ]

    # derived: total assets as % of nominal GDP (annualised quarterly GDP)
    gdp_q = gdp_nominal_quarterly()
    def gdp_for_month(m):
        y, mo = int(m[:4]), int(m[5:7])
        q = (mo - 1) // 3 + 1
        return gdp_q.get(f"{y}-Q{q}")
    assets_pct_gdp = []
    for m, ta in zip(months, series["total_assets"]):
        g = gdp_for_month(m)
        assets_pct_gdp.append(round(ta / (g * 4) * 100, 2) if (ta is not None and g) else None)

    # derived: QT decomposition — gross purchases minus net change in holdings approximates
    # redemptions/maturities absorbed that month (doc's Section 2: "gross purchases − maturities
    # ≈ net change in holdings"). Both series are already aligned to the same `months` index.
    purchases_series = md06_series["jgb_purchases_outright"]
    redemptions_implied = [
        round(purchases_series[i] - jgs_mom[i], 3)
        if (purchases_series[i] is not None and jgs_mom[i] is not None) else None
        for i in range(len(months))
    ]

    def last_non_null(arr):
        for i in range(len(arr) - 1, -1, -1):
            if arr[i] is not None:
                return arr[i], months[i]
        return None, None

    latest_idx = len(months) - 1
    boj_share_latest, boj_share_month = last_non_null(boj_share_of_jgb)
    gdp_pct_latest, gdp_pct_month = last_non_null(assets_pct_gdp)
    purchases_latest, purchases_month = last_non_null(md06_series["jgb_purchases_outright"])
    latest = {
        "month": months[latest_idx],
        "total_assets_jpy_tn": series["total_assets"][latest_idx],
        "jgs_jpy_tn": series["jgs"][latest_idx],
        "jgs_share_pct": jgs_share[latest_idx],
        "current_deposits_jpy_tn": series["current_deposits"][latest_idx],
        "boj_share_of_jgb_pct": boj_share_latest,
        "boj_share_of_jgb_pct_asof": boj_share_month,
        "assets_pct_gdp": gdp_pct_latest,
        "assets_pct_gdp_asof": gdp_pct_month,
        "jgb_purchases_jpy_tn": purchases_latest,
        "jgb_purchases_asof": purchases_month,
    }

    doc = {
        "meta": {
            "as_of": months[latest_idx],
            "generated_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
            "unit": "JPY tn",
            "frequency": "monthly (end-of-month snapshot; BOJ also publishes every-10-days on the acmai page)",
            "source": "BOJ Time-Series Data Search API (DB=BS01, Bank of Japan Accounts); DB=FM05 (JGB amount outstanding) for the BOJ-ownership-share denominator; Cabinet Office ESRI Quarterly Estimates of GDP (nominal, original series) for the assets/GDP denominator",
            "source_url": "https://www.boj.or.jp/en/statistics/boj/other/acmai/",
            "api_url": "https://www.stat-search.boj.or.jp/api/v1/getDataCode",
            "cross_check": "10 Mar 2026 JGS holdings verified directly against the acmai HTML release (ac260310.htm): ¥545.58tn, matching the doc's ~¥545.6tn spot-check to the tn.",
        },
        "months": months,
        "assets": {
            "total_assets": series["total_assets"],
            "jgs": series["jgs"],
            "jgs_share_of_total_pct": jgs_share,
            "corporate_bonds": series["corporate_bonds"],
            "etf": series["etf"],
            "jreit": series["jreit"],
            "loans": series["loans"],
            "fx_assets": series["fx_assets"],
        },
        "liabilities": {
            "banknotes": series["banknotes"],
            "current_deposits": series["current_deposits"],
            "govt_deposits": series["govt_deposits"],
            "repo_liabilities": series["repo_liabilities"],
            "other_deposits": series["other_deposits"],
        },
        "derived": {
            "jgs_change_mom_jpy_tn": jgs_mom,
            "jgs_change_3m_jpy_tn": jgs_change_3m,
            "jgs_change_6m_jpy_tn": jgs_change_6m,
            "jgs_change_yoy_jpy_tn": jgs_yoy,
            "total_assets_3m_annualised_pct": ta_3m_ann,
            "total_assets_pct_gdp": assets_pct_gdp,
            "jgb_outstanding_total_jpy_tn": jgb_outstanding,
            "boj_share_of_jgb_outstanding_pct": boj_share_of_jgb,
            "jgb_redemptions_implied_jpy_tn": redemptions_implied,
            "redemptions_note": "Implied, not directly published: gross outright purchases (DB=MD06) minus the month's net change in JGS holdings (DB=BS01). Positive = that much redeemed/matured off the BOJ's book that month. This is an approximation — it also nets out any other reclassifications in the JGS balance-sheet line — but the pattern lines up cleanly with Japan's quarterly JGB redemption calendar (large negative net-change months recur every Mar/Jun/Sep/Dec), which is the strongest check available without BOJ publishing a redemptions series directly.",
        },
        "operations": {
            "jgb_purchases_outright_jpy_tn": md06_series["jgb_purchases_outright"],
            "tbill_purchases_outright_jpy_tn": md06_series["tbill_purchases_outright"],
            "note": "Gross monthly outright purchases (BOJ Time-Series API, DB=MD06, 'Sources of Changes in Current Account Balances and Market Operations'). Not broken out by maturity bucket — that level of detail is only in BOJ's daily operation-result releases (boj.or.jp/en/statistics/boj/fm/ope/), not this clean time series. This is the cleanest available official read on the pace of the purchase taper.",
        },
        "latest": latest,
    }

    with open(OUT, "w") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)

    print(f"wrote {OUT}: {len(months)} months {months[0]}..{months[-1]}")
    print(f"latest ({latest['month']}): total assets ¥{latest['total_assets_jpy_tn']}tn, "
          f"JGS ¥{latest['jgs_jpy_tn']}tn ({latest['jgs_share_pct']}% of assets), "
          f"current deposits ¥{latest['current_deposits_jpy_tn']}tn, "
          f"BOJ/total JGB {latest['boj_share_of_jgb_pct']}%, assets/GDP {latest['assets_pct_gdp']}%, "
          f"gross JGB purchases ({latest['jgb_purchases_asof']}) ¥{latest['jgb_purchases_jpy_tn']}tn/mo")


if __name__ == "__main__":
    main()
