#!/usr/bin/env python3.12
"""Build seasonality_data.json for the dashboard's Seasonality tab from the
japan-jgb-seasonality project's extended backtest results (JGB outright 2Y-40Y
+ curve spreads 2s10s/2s30s/5s30s/10s30s/20s30s). ASW/OIS excluded — no
reliable free swap-curve source. STATIC data, not on daily refresh; rerun by
hand (after rerunning japan-jgb-seasonality/curve/seasonality_full.py) if the
underlying yield history is extended with fresh years."""
import pandas as pd
import ast
import json

SRC = "/home/workspace/japan-jgb-seasonality/curve"
OUT = "/home/workspace/boj-hawk-dove-assessment/seasonality_data.json"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
OUTRIGHT_ORDER = ["2y", "5y", "10y", "20y", "30y", "40y"]
CURVE_ORDER = ["2s10s", "2s30s", "5s30s", "10s30s", "20s30s"]

bt = pd.read_csv(f"{SRC}/result_seasonality_extended_backtest.csv")
tab = pd.read_csv(f"{SRC}/result_seasonality_extended_tables.csv")

bt["key"] = bt["series"].apply(lambda s: s.split()[0].lower())
bt_by_key = {row["key"]: row for _, row in bt.iterrows()}


def month_table(key):
    sub = tab[tab["series"] == key].set_index("month").reindex(MONTHS)
    years = [c for c in tab.columns if c.isdigit()]
    rows = []
    for m in MONTHS:
        r = sub.loc[m]
        rows.append({
            "month": m,
            "years": {y: (None if pd.isna(r[y]) else round(float(r[y]), 1)) for y in years},
            "avg": None if pd.isna(r["Avg"]) else round(float(r["Avg"]), 1),
            "hit_rate": r["Hit rate"],
            "n": int(r["n"]) if not pd.isna(r["n"]) else 0,
        })
    return {"years": years, "rows": rows}


def bt_row(key, kind):
    r = bt_by_key[key]
    yearly = ast.literal_eval(r["yearly_pnl_bp"])
    return {
        "key": key, "kind": kind,
        "long_months": [MONTHS[m - 1] for m in ast.literal_eval(r["long_months"])],
        "short_months": [MONTHS[m - 1] for m in ast.literal_eval(r["short_months"])],
        "ann_bp": r["ann_bp"], "ann_vol_bp": r["ann_vol_bp"], "sharpe": r["sharpe"],
        "max_dd_bp": r["max_dd_bp"], "daily_win_rate": r["daily_win_rate"],
        "annual_hit_rate": r["annual_hit_rate"], "n_years": int(r["n_years"]),
        "yearly_pnl_bp": {str(k): v for k, v in yearly.items()},
    }


out = {
    "generated_note": "5y JGB, 2y CGB (China auction results) excluded — n/a here; scope is JGB outright "
                       "2Y-40Y + JGB curve spreads only. ASW/OIS-based trades excluded (no reliable free "
                       "swap-curve data source).",
    "outright": {
        "tenors": OUTRIGHT_ORDER,
        "backtest": [bt_row(k, "outright") for k in OUTRIGHT_ORDER],
        "calendar": {k: month_table(k) for k in OUTRIGHT_ORDER},
    },
    "curve": {
        "spreads": CURVE_ORDER,
        "backtest": [bt_row(k, "curve") for k in CURVE_ORDER],
        "calendar": {k: month_table(k) for k in CURVE_ORDER},
    },
}
with open(OUT, "w") as f:
    json.dump(out, f, indent=1)
print(f"Wrote {OUT}")
