"""
Official industry-wide monthly net fund flow for Japanese public stock investment
trusts (ex-ETF), from the Investment Trusts Association, Japan (投資信託協会).

This is the ground-truth confirmation series for the NISA tab's fund-flow charts
(Top-20 snapshot/time-series, NAV-flow proxy): it's the only one of the four that
covers the WHOLE public fund universe (~5,300+ funds) rather than a subset, is an
official industry-body release (not a private aggregator or a narrower FX-flow
series), and is published monthly with only a ~1-2 week lag.

Source: https://www.toushin.or.jp/statistics/statistics/index.html, row B-1
(資産増減状況 / "Changes in Assets of Publicly Offered Investment Trusts of
Contractual Type"), monthly time-series file. Sheet "株式 除ＥＴＦ" (Stock
Investment Trusts, Excluding ETFs) is used since that's the closest match to what
the NISA growth-quota funds actually are. Column D, "資金増減額 / Amount of Assets
Flows" = setup(sales) - (repurchases + redemptions) = net subscription flow,
¥ million, going back to 2001-07.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

import openpyxl

URL = "https://www.toushin.or.jp/tws/toukei_dw/I0112B_pub_m.xlsx"
SHEET = "株式 除ＥＴＦ"
OUT = os.path.join(os.path.dirname(__file__), "toushin_flows.json")
WINDOW_START = "2024-01"  # keep the JSON small; new-NISA era onward

JMON = {f"{n}月": n for n in range(1, 13)}


def fetch_xlsx():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    tmp = "/tmp/toushin_b1_monthly.xlsx"
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        f.write(r.read())
    return tmp


def parse_month(label):
    # e.g. "2026年6月" -> "2026-06"
    y, rest = label.split("年")
    m = rest.replace("月", "")
    return f"{int(y):04d}-{int(m):02d}"


def main():
    path = fetch_xlsx()
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[SHEET]

    series = []
    for row in ws.iter_rows(values_only=True):
        label = row[1]
        if not isinstance(label, str) or "年" not in label or "月" not in label:
            continue
        flow_mn_jpy = row[5]  # column F (0-indexed 5) = 資金増減額 (D)
        nav_mn_jpy = row[9]   # column J = 純資産総額 (Total Net Assets)
        if flow_mn_jpy is None:
            continue
        m = parse_month(label)
        series.append({
            "date": m,
            "flow_bn": round(flow_mn_jpy / 1000, 1),   # ¥mn -> ¥bn
            "aum_tn": round(nav_mn_jpy / 1_000_000, 2) if nav_mn_jpy else None,  # ¥mn -> ¥tn
        })

    series.sort(key=lambda r: r["date"])
    windowed = [r for r in series if r["date"] >= WINDOW_START]

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Investment Trusts Association, Japan (投資信託協会) — B-1, 株式投信（除ETF）",
        "source_url": "https://www.toushin.or.jp/statistics/statistics/index.html",
        "as_of": windowed[-1]["date"] if windowed else None,
        "full_history_start": series[0]["date"] if series else None,
        "series": windowed,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print(f"wrote {OUT}: {len(windowed)} points ({WINDOW_START}+), "
          f"as_of {out['as_of']}, full history since {out['full_history_start']}")
    if windowed:
        last = windowed[-1]
        print(f"latest: {last['date']} flow=¥{last['flow_bn']}bn aum=¥{last['aum_tn']}tn")


if __name__ == "__main__":
    main()
