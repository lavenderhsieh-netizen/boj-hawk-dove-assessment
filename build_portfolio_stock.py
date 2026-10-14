#!/usr/bin/env python3.12
"""Japanese holdings (stock, year-end) of foreign securities by issuer country, 2024 vs 2025.
Source workbook: Documents/japan-portfolio-stock-by-country/Japan_stock_2025_EM_DM_tables.xlsx
(MOF/BOJ regional portfolio investment position, assets, end-2025 release). Writes portfolio_stock.json.
Run: python3.12 build_portfolio_stock.py
"""
import json, os, openpyxl
HERE = os.path.dirname(os.path.abspath(__file__))
XLSX = os.path.join(HERE, "..", "Documents", "japan-portfolio-stock-by-country", "Japan_stock_2025_EM_DM_tables.xlsx")
SHEETS = {"total": "Total equity & LT bonds", "equity": "Equity incl. fund shares", "ltdebt": "Long-term bonds"}
GROUPS = {"Developed (DM)": "dm", "Emerging & frontier (EM)": "em", "Offshore / fund centres": "off"}

def fx_at(hist, date):
    prior = [h for h in hist if h["date"] <= date]
    return prior[-1]["value"], prior[-1]["date"]

def main():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    out = {"meta": {"unit": "¥bn, market value of Japanese holdings at year-end",
                    "source": "MOF/BOJ Regional Portfolio Investment Position (Assets), end-2025 release (26 May 2026)",
                    "source_url": "https://www.mof.go.jp/policy/international_policy/reference/iip/data/index.htm",
                    "note": "Classified by issuer country. YoY change includes price and FX moves, not only net buying. Cayman/Luxembourg/Ireland etc. are fund domiciles (shown as Offshore)."},
           "measures": {}}
    hist = json.load(open(os.path.join(HERE, "market_data.json")))["fx"]["history"]
    r24, d24 = fx_at(hist, "2024-12-31"); r25, d25 = fx_at(hist, "2025-12-31")
    out["fx"] = {"2024": r24, "2025": r25, "dates": [d24, d25]}
    for key, sh in SHEETS.items():
        m = {"dm": [], "em": [], "off": [], "totals": {}}
        for g, name, v24, v25, d, share, yoy in wb[sh].iter_rows(min_row=2, values_only=True):
            if g not in GROUPS or name is None: continue
            gk = GROUPS[g]
            if name.startswith("**"):
                m["totals"][gk] = {"s24": v24, "s25": v25}; continue
            if (v24 or 0) == 0 and (v25 or 0) == 0: continue
            m[gk].append({"name": name, "s24": round(v24 or 0, 1), "s25": round(v25 or 0, 1)})
        out["measures"][key] = m
    json.dump(out, open(os.path.join(HERE, "portfolio_stock.json"), "w"), ensure_ascii=False)
    print("wrote portfolio_stock.json", {k: {g: len(v[g]) for g in ("dm", "em", "off")} for k, v in out["measures"].items()}, out["fx"])

if __name__ == "__main__":
    main()
