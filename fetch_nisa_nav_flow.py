"""
Daily NAV-based composite flow estimate for top NISA funds.

Reads the daily-NAV CSVs already collected in japan-nisa-tracker/fund_nav_daily/
(one file per fund: date, base_price_jpy, [reinvest_base_price_jpy], [net_asset_value_100m_jpy]),
builds an AUM-weighted composite NAV index and a daily estimated net-flow series
(AUM change minus what the price return alone would explain), and writes
nisa_nav_flow.json for the BOJ dashboard's NISA tab.

This is a STATIC snapshot, not a live daily pull: the underlying fund_nav_daily
CSVs are each scraped one-off from a different asset manager's site (see that
project's own README) and are not on any automation. Re-run this script after
japan-nisa-tracker/fund_nav_daily/*.csv is refreshed to move the "as_of" date
forward; running it against unchanged CSVs is a no-op.
"""
import csv, glob, os, json
from datetime import datetime, timezone

SRC_DIR = "/home/workspace/japan-nisa-tracker/fund_nav_daily"
OUT = os.path.join(os.path.dirname(__file__), "nisa_nav_flow.json")
WINDOW_START = "2024-01-01"  # new-NISA era onward
ROLL_WINDOW = 20  # trading days


def load_funds():
    files = [f for f in glob.glob(os.path.join(SRC_DIR, "*.csv")) if "_combined_" not in f]
    funds = {}
    for f in files:
        name = os.path.basename(f).replace(".csv", "")
        rows = []
        with open(f, encoding="utf-8-sig") as fh:
            r = csv.DictReader(fh)
            cols = set(r.fieldnames or [])
            has_reinv = "reinvest_base_price_jpy" in cols
            has_aum = "net_asset_value_100m_jpy" in cols
            for row in r:
                try:
                    d = row["date"]
                    bp = float(row["base_price_jpy"])
                except (ValueError, KeyError, TypeError):
                    continue
                rbp = None
                if has_reinv:
                    try:
                        rbp = float(row["reinvest_base_price_jpy"])
                    except (ValueError, TypeError):
                        rbp = None
                if rbp is None:
                    rbp = bp
                aum = None
                if has_aum:
                    try:
                        aum = float(row["net_asset_value_100m_jpy"])
                    except (ValueError, TypeError):
                        aum = None
                rows.append((d, bp, rbp, aum))
        rows.sort(key=lambda x: x[0])
        funds[name] = rows
    return funds


def build_composite(funds):
    per_fund_daily = {}
    for name, rows in funds.items():
        out = []
        for i in range(1, len(rows)):
            d0, bp0, rbp0, aum0 = rows[i - 1]
            d1, bp1, rbp1, aum1 = rows[i]
            if bp0 == 0 or rbp0 == 0:
                continue
            price_ret = (bp1 / bp0) - 1
            reinv_ret = (rbp1 / rbp0) - 1
            rec = {"date": d1, "reinv_ret": reinv_ret}
            if aum0 is not None and aum1 is not None and aum0 > 0:
                implied_aum = aum0 * (1 + price_ret)
                rec["aum"] = aum1
                rec["aum_prev"] = aum0
                rec["est_flow_100m"] = aum1 - implied_aum
            out.append(rec)
        per_fund_daily[name] = out

    by_date = {}
    for name, rows in per_fund_daily.items():
        for r in rows:
            if "aum_prev" in r:
                by_date.setdefault(r["date"], []).append(r)

    dates_sorted = sorted(by_date.keys())
    composite = []
    idx = 100.0
    for d in dates_sorted:
        entries = by_date[d]
        total_prev_aum = sum(e["aum_prev"] for e in entries)
        if total_prev_aum <= 0:
            continue
        weighted_ret = sum(e["reinv_ret"] * (e["aum_prev"] / total_prev_aum) for e in entries)
        idx *= (1 + weighted_ret)
        total_aum = sum(e["aum"] for e in entries)
        total_flow = sum(e["est_flow_100m"] for e in entries)
        composite.append({
            "date": d, "n_funds": len(entries), "index": idx,
            "total_aum_100m": total_aum, "est_flow_100m": total_flow,
        })
    return composite


def main():
    funds = load_funds()
    composite = build_composite(funds)
    comp = [c for c in composite if c["date"] >= WINDOW_START]

    running = []
    series = []
    for c in comp:
        running.append(c["est_flow_100m"])
        if len(running) > ROLL_WINDOW:
            running.pop(0)
        series.append({
            "date": c["date"],
            "index": round(c["index"], 3),
            "flow_bn": round(c["est_flow_100m"] / 10, 2),          # 100mn JPY -> bn JPY
            "roll20_bn": round(sum(running) / 10, 2),
            "aum_tn": round(c["total_aum_100m"] / 10000, 3),        # 100mn JPY -> tn JPY
            "n_funds": c["n_funds"],
        })

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": series[-1]["date"] if series else None,
        "n_funds_latest": series[-1]["n_funds"] if series else 0,
        "n_funds_total": len(funds),
        "roll_window": ROLL_WINDOW,
        "latest_aum_tn": series[-1]["aum_tn"] if series else None,
        "latest_roll20_bn": series[-1]["roll20_bn"] if series else None,
        "series": series,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print(f"wrote {OUT}: {len(series)} points, {out['as_of']}, "
          f"latest AUM {out['latest_aum_tn']}tn, latest 20d roll {out['latest_roll20_bn']}bn")


if __name__ == "__main__":
    main()
