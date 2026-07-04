#!/usr/bin/env python3
"""Schema guard for the dashboard's data files.

Usage: /usr/local/bin/python3 validate_data.py [data|market|all]
Exit 0 = valid, 1 = invalid (details on stderr).

Run after any update to data.json / market_data.json. If invalid, revert
the file to the last committed version (git checkout -- <file>).
"""

import json
import os
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.abspath(__file__))
ERRORS = []


def err(msg):
    ERRORS.append(msg)


def need(d, key, typ, name):
    if key not in d:
        err(f"{name}: missing key '{key}'")
        return None
    if typ is not None and not isinstance(d[key], typ):
        err(f"{name}: '{key}' should be {typ}, got {type(d[key]).__name__}")
        return None
    return d[key]


def validate_data_json():
    path = os.path.join(REPO, "streamlit_app", "data.json")
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception as e:
        err(f"data.json: unreadable/unparseable — {e}")
        return

    need(d, "as_of", str, "data.json")
    kpis = need(d, "kpis", list, "data.json")
    if kpis is not None and len(kpis) < 3:
        err("data.json: kpis suspiciously short")
    rp = need(d, "rate_path", dict, "data.json")
    if rp is not None:
        labels, values = rp.get("labels", []), rp.get("values", [])
        if len(labels) != len(values) or not values:
            err("data.json: rate_path labels/values mismatch or empty")
        elif not all(isinstance(v, (int, float)) and -1 <= v <= 5 for v in values):
            err("data.json: rate_path values out of plausible range")
    spectrum = need(d, "spectrum", list, "data.json")
    if spectrum:
        for s in spectrum:
            sc = s.get("score")
            if not isinstance(sc, (int, float)) or not -2 <= sc <= 2:
                err(f"data.json: spectrum score out of range for {s.get('name')}")
    periods = need(d, "periods", list, "data.json")
    tone = need(d, "tone", list, "data.json")
    if periods and tone:
        for s in tone:
            if len(s.get("scores", [])) != len(periods):
                err(f"data.json: tone series length mismatch for {s.get('name')}")
            for sc in s.get("scores", []):
                if sc is not None and (not isinstance(sc, (int, float)) or not -2 <= sc <= 2):
                    err(f"data.json: tone score out of range for {s.get('name')}")
    for key, typ in [("speakers", list), ("timeline", list), ("board", list),
                     ("mpm_calendar", list), ("auctions", dict), ("fiscal", list)]:
        v = need(d, key, typ, "data.json")
        if v is not None and len(v) == 0:
            err(f"data.json: '{key}' is empty")


def validate_market_json():
    path = os.path.join(REPO, "market_data.json")
    try:
        with open(path) as f:
            m = json.load(f)
    except Exception as e:
        err(f"market_data.json: unreadable/unparseable — {e}")
        return

    need(m, "updated_utc", str, "market_data.json")
    sources = need(m, "sources", dict, "market_data.json")
    if sources is None:
        return

    jgb = m.get("jgb")
    if jgb:
        curve = jgb.get("curve", {})
        if not curve.get("tenors") or len(curve.get("tenors", [])) != len(curve.get("yields", [])):
            err("market: jgb curve malformed")
        if not jgb.get("history"):
            err("market: jgb history empty")
    for key in ("fx", "nikkei", "us10y", "call_rate"):
        sec = m.get(key)
        if sec is not None:
            h = sec.get("history", [])
            if not h or not all(isinstance(p.get("value"), (int, float)) for p in h[-5:]):
                err(f"market: {key} history malformed")
    infl = m.get("inflation")
    if infl is not None:
        n = len(infl.get("months", []))
        if n == 0 or any(len(infl.get(k, [])) != n for k in ("ex_fresh", "ex_fresh_energy", "ex_food_energy")):
            err("market: inflation series length mismatch")
    news = m.get("news")
    if news is not None and (not isinstance(news, list) or len(news) < 1):
        err("market: news empty")

    # every declared source must be either ok or stale-with-data
    for key, meta in sources.items():
        if meta.get("status") == "ok" and m.get(key) is None:
            err(f"market: source '{key}' marked ok but section missing")


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("data", "all"):
        validate_data_json()
    if what in ("market", "all"):
        validate_market_json()
    if ERRORS:
        for e in ERRORS:
            print("INVALID:", e, file=sys.stderr)
        return 1
    print(f"valid ({what})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
