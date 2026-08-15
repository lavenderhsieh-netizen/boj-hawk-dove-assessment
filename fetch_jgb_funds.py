#!/usr/bin/env python3.12
"""Long-JGB mutual fund tracker — AUM and monthly net inflow for one flagship
long/super-long JGB fund per manager, per HanHan's ask (2026-08-15 Telegram:
"I would start tracking the AUM and monthly inflows of MUFG, Daiwa and Amova's
long-JGB funds").

Funds tracked (confirmed genuine long/super-long JGB holdings via web research):
- MUFG:  日本超長期国債インデックスファンド（ラップ向け）— fcode 0331320C.
         Wrap-channel only; MUFG has no comparably-sized retail long-JGB fund.
         Tracks NOMURA-BPI 国債超長期(11-). Est. 2020-12-28.
- Daiwa: iFreeHOLD 日本国債（JGB2056）— fcode 04311258. ~30yr target-maturity,
         NISA growth-quota eligible, est. 2025-08-21. Daiwa's lineup is the
         deepest of the three (also runs JGB2045, etc.) — this is its largest.
- Amova: Tracers 日本国債ウルトラロング（30年平均）年4回分配型 — fcode 0231225B.
         27-33yr residual-maturity JGBs, est. 2025-11-26 (Amova = the 2025
         rebrand of Nikko Asset Management's JV).

Source: Nikkei's per-fund page (nikkei.com/nkd/fund?fcode=...) — publicly
readable via curl_cffi Chrome impersonation (plain requests/urllib get
redirected to a login wall; Yahoo Finance Japan's equivalent pages are
geo-blocked from this sandbox's egress IP, "EEA/UK" notice, confirmed via
direct fetch — Nikkei has no such block). Gives 純資産総額 (AUM, ¥100mn) and
資金流出入（1ヶ月）(net 1-month flow, ¥100mn) as of Nikkei's own last-updated
date (nikkei refreshes the flow figure roughly monthly, per its own "as of"
line at the bottom of the stat block).

IMPORTANT CAVEAT, not a bug: no source publishes a HISTORICAL monthly-flow
series for individual funds — only the latest 1-month snapshot is ever shown
(confirmed via Nikkei, Minkabu, Yahoo Finance Japan, and each manager's own
site). So `history` in the output JSON can only be built prospectively, one
row per time this script runs — do not attempt to backfill flow. AUM itself
does have a real daily history on Nikkei's own /history sub-page, but is not
pulled here (out of scope for v1; flow is the harder/newer data point that
was actually asked for).

Output: jgb_funds.json — {meta, funds: [current snapshot x3], history: [one
row per run date]}. Not yet registered in fetch_market.py's SOURCES — this is
a slow-moving series (funds are all <1yr old, monthly cadence is plenty), so
it's fine to run manually / add to a monthly automation later.

Usage: python3.12 fetch_jgb_funds.py
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta

from curl_cffi import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "jgb_funds.json")

FUNDS = [
    {
        "key": "mufg",
        "manager": "MUFG",
        "name": "日本超長期国債インデックスファンド（ラップ向け）",
        "fcode": "0331320C",
        "note": "Wrap-channel only (sold via discretionary investment wrap accounts, not directly to retail); MUFG's lineup of genuine long-JGB funds is thinner than Daiwa's or Amova's.",
    },
    {
        "key": "daiwa",
        "manager": "Daiwa",
        "name": "iFreeHOLD 日本国債（JGB2056）",
        "fcode": "04311258",
        "note": "~30yr target-maturity (matures 2056-03-27), NISA growth-quota eligible. Daiwa runs the deepest long-JGB lineup of the three managers (also JGB2045 etc.).",
    },
    {
        "key": "amova",
        "manager": "Amova",
        "name": "Tracers 日本国債ウルトラロング（30年平均）年4回分配型",
        "fcode": "0231225B",
        "note": "27-33yr residual-maturity JGBs. Amova = the 2025 rebrand of Nikko Asset Management's asset-management JV.",
    },
]

VALUE_RE = re.compile(r"m-stockInfo_detail_value\">\s*([+\-−]?[\d,.]+)\s*<[^>]*>(億|百万)円")
ASOF_RE = re.compile(r"(20\d\d年\d+月末)")


def find_value_near(text, label, window=300):
    idx = text.find(label)
    if idx == -1:
        return None
    m = VALUE_RE.search(text, idx, idx + window)
    if not m:
        return None
    return m.group(1), m.group(2)


def to_100m(value, unit):
    v = float(value.replace("−", "-"))
    if unit == "百万":
        return v / 100.0
    return v


def fetch_fund(fcode):
    url = f"https://www.nikkei.com/nkd/fund?fcode={fcode}"
    r = requests.get(url, impersonate="chrome", timeout=20)
    r.raise_for_status()
    text = r.text
    aum = find_value_near(text, "純資産総額")
    flow = find_value_near(text, "資金流出入")
    asof_m = ASOF_RE.search(text)
    if not aum:
        raise ValueError(f"AUM not found for fcode {fcode}")
    return {
        "aum_100m_jpy": round(to_100m(aum[0].replace(",", ""), aum[1]), 2),
        "flow_1m_100m_jpy": round(to_100m(flow[0].replace(",", ""), flow[1]), 2) if flow else None,
        "flow_asof": asof_m.group(1) if asof_m else None,
    }


def main():
    today = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    snapshot = []
    for f in FUNDS:
        try:
            data = fetch_fund(f["fcode"])
        except Exception as e:
            print(f"  {f['key']} fetch failed: {e}")
            continue
        snapshot.append({**f, **data})
        print(f"  {f['key']}: AUM {data['aum_100m_jpy']}億円, flow(1mo) {data['flow_1m_100m_jpy']}億円 (as of {data['flow_asof']})")

    prev = {}
    if os.path.exists(OUT):
        with open(OUT) as fh:
            prev = json.load(fh)
    history = prev.get("history", [])

    hist_row = {"date": today}
    for s in snapshot:
        hist_row[f"{s['key']}_aum_100m"] = s["aum_100m_jpy"]
        hist_row[f"{s['key']}_flow_1m_100m"] = s["flow_1m_100m_jpy"]
        hist_row[f"{s['key']}_flow_asof"] = s["flow_asof"]

    history = [h for h in history if h["date"] != today]
    history.append(hist_row)
    history.sort(key=lambda h: h["date"])

    out = {
        "meta": {
            "as_of": today,
            "source": "Nikkei per-fund pages (nikkei.com/nkd/fund?fcode=...)",
            "note": "AUM (純資産総額) and monthly net flow (資金流出入1ヶ月) are both live snapshots — no historical flow series is published anywhere for individual funds. AUM history is genuinely available (Nikkei /history sub-page) but not pulled here; flow history builds prospectively from this script's own run dates only.",
        },
        "funds": snapshot,
        "history": history,
    }
    with open(OUT, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"Wrote {OUT} ({len(history)} history rows)")


if __name__ == "__main__":
    main()
