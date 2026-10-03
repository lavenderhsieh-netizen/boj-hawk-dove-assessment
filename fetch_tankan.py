#!/usr/bin/env python3.12
"""Tankan tab data. Sector x firm-size DI table is parsed live from the BOJ Tankan Summary PDF.
The summary / by-size / capex-sales-profit tables are curated (STATIC) from the same PDF -- update by hand each quarter.
Usage: python3.12 fetch_tankan.py [YYMM]   e.g. 2609 (Sep 2026)"""
import json, re, subprocess, sys, urllib.request, datetime
CODE = sys.argv[1] if len(sys.argv) > 1 else "2609"
YEAR = "20" + CODE[:2]
URL = f"https://www.boj.or.jp/en/statistics/tk/gaiyo/{YEAR}/tka{CODE}.pdf"
req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
open("/tmp/tka.pdf", "wb").write(urllib.request.urlopen(req, timeout=60).read())
txt = subprocess.run(["pdftotext", "-layout", "/tmp/tka.pdf", "-"], capture_output=True, text=True).stdout
lines = txt.splitlines()
start = next(i for i, l in enumerate(lines) if l.startswith("Manufacturing") and "22" in l)
MFG_GROUPS = {"Basic materials", "Processing"}
rows, group = [], "Manufacturing"
for l in lines[start:start + 40]:
    m = re.match(r"^(\s*)([A-Za-z][A-Za-z &,\-\.]+?)\s{2,}(-?\d+(?:\s+-?\d+){17})\s*$", l)
    if not m:
        if l.startswith("All industries"): break
        continue
    name, nums = m.group(2).strip(), [int(x) for x in m.group(3).split()]
    if name == "Nonmanufacturing": group = "Non-manufacturing"
    if name == "All industries": group = "All"
    r = {"name": name, "group": group, "indent": bool(m.group(1))}
    for k, o in zip("LMS", (0, 6, 12)):
        r[k] = {"jun": nums[o], "jun_fc": nums[o+1], "sep": nums[o+2], "chg": nums[o+3], "dec": nums[o+4], "fc": nums[o+5]}
    rows.append(r)
    if name == "All industries": break
assert len(rows) >= 33, len(rows)
for r in rows:
    for k in "LMS":
        d = r[k]; assert d["sep"] - d["jun"] == d["chg"] and d["dec"] - d["sep"] == d["fc"], (r["name"], k, d)

SIZE_DI = [  # label, jun, sep, chg, dec_fcst, fcst_vs_sep
 ("Large: Manufacturing",22,24,2,21,-3),("Large: Non-manufacturing",37,35,-2,30,-5),("Large: All industries",29,30,1,25,-5),
 ("Medium: Manufacturing",17,23,6,18,-5),("Medium: Non-manufacturing",26,24,-2,19,-5),("Medium: All industries",22,24,2,18,-6),
 ("Small: Manufacturing",9,14,5,12,-2),("Small: Non-manufacturing",15,15,0,10,-5),("Small: All industries",13,15,2,11,-4)]
PLANS = {  # FY2026 plans, % y/y: (label, jun, sep)
 "Capex": [("Large mfg",10.1,11.6),("Large non-mfg",12.3,11.2),("Large all",11.5,11.3),("Medium mfg",3.6,1.9),("Medium non-mfg",7.8,11.4),("Medium all",6.0,7.3),("Small mfg",2.6,4.0),("Small non-mfg",-13.0,-8.4),("Small all",-8.3,-4.7)],
 "Sales": [("Large mfg",4.0,7.6),("Large non-mfg",3.5,4.3),("Large all",3.7,5.7),("Medium mfg",1.6,3.4),("Medium non-mfg",3.0,4.4),("Medium all",2.6,4.1),("Small mfg",1.3,2.8),("Small non-mfg",-0.1,0.9),("Small all",0.2,1.3)],
 "Current profit": [("Large mfg",-6.7,13.6),("Large non-mfg",-6.3,-4.7),("Large all",-6.5,4.3),("Medium mfg",-0.4,10.6),("Medium non-mfg",-5.1,-2.2),("Medium all",-3.6,1.8),("Small mfg",-11.1,-3.6),("Small non-mfg",-8.8,-6.3),("Small all",-9.4,-5.6)],
 "Employment DI (neg = shortage)": [("Large all",-28,-29),("Medium all",-38,-38),("Small all",-39,-42)]}
# label, jun, sep, tone: +1 good when up, -1 good when down (inflation/labour shown amber)
SUMMARY = {
 "Business conditions DI": [("Large manufacturers",22,24),("Large non-manufacturers",37,35),("Large, all industries",29,30),("All enterprises, all industries",18,21),("3M-ahead forecast: large mfg",17,21),("3M-ahead forecast: large non-mfg",28,30)],
 "Dec forecast vs Sep actual (columns = Sep actual | Dec forecast)": [("Large manufacturers",24,21),("Large non-manufacturers",35,30),("All enterprises, all industries",21,15)],
 "Profits, sales & FX (FY2026, % y/y)": [("Sales, large manufacturers",4.0,7.6),("Profit, large manufacturers",-6.7,13.6),("Profit, large manufacturers, 2H only",-6.4,-3.1),("Profit, large non-manufacturers",-6.3,-4.7),("Profit, all enterprises",-6.5,2.2),("Assumed USD/JPY, FY2026",152.57,154.23)],
 "Prices, labour, credit": [("Inflation outlook, 1 yr ahead (%)",2.7,2.6),("Inflation outlook, 3 yrs ahead (%)",2.6,2.6),("Inflation outlook, 5 yrs ahead (%)",2.6,2.5),("Output price outlook, 1 yr (%)",3.7,3.5),("Large mfg output-price DI",40,40),("Large mfg input-price DI",62,59),("Employment DI, all enterprises (neg = shortage)",-37,-38),("Employment DI, small enterprises",-39,-42),("Loan interest-rate DI (rise minus fall)",61,68),("Financial position DI, large (easy minus tight)",12,13),("Lending attitude DI, large",13,12),("Domestic supply/demand DI, large mfg",-4,-1)]}
out = {"meta": {"survey": f"{['Mar','Jun','Sep','Dec'][int(CODE[2:])//3-1]} {YEAR}", "prev": "Jun 2026", "source_url": URL,
        "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
        "note": "Sector table parsed from the BOJ PDF; other tables curated from the same PDF (static, update quarterly)."},
       "sectors": rows, "size_di": SIZE_DI, "plans": PLANS, "summary": SUMMARY}
json.dump(out, open("tankan_data.json", "w"), ensure_ascii=False, indent=1)
print("ok", len(rows), "sector rows ->", out["meta"]["survey"])
