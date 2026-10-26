#!/usr/bin/env python3.12
"""Extend the dashboard's JGB auction calendar (data.json + streamlit_app/data.json -> auctions)
with every month MOF has published at mof.go.jp/jgbs/auction/calendar/YYMM.htm. Existing months
(hand-written context) are kept untouched; only missing months are added. Run monthly."""
import json, re, urllib.request, calendar, sys
from datetime import date
FILES = ["data.json", "streamlit_app/data.json"]
WD = {"月": "Mon", "火": "Tue", "水": "Wed", "木": "Thu", "金": "Fri"}

def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read().decode("utf-8")

def classify(n):
    n = n.strip()
    m = re.match(r"国庫短期証券（(\d+)ヶ月）", n)
    if m: return "T-bill", f"Treasury Discount Bills ({m.group(1)}-month)"
    if n.startswith("国庫短期証券（1年）"): return "T-bill", "Treasury Discount Bills (1-year)"
    m = re.match(r"(\d+)年クライメート・トランジション利付国債", n)
    if m: return "GX", f"{m.group(1)}-year Japan Climate Transition Bonds"
    m = re.match(r"(\d+)年物価連動国債", n)
    if m: return "Linker", f"{m.group(1)}-year Inflation-Indexed Bonds"
    m = re.match(r"(\d+)年利付国債", n)
    if m: return "Coupon", f"{m.group(1)}-year"
    m = re.match(r"流動性供給入札（残存期間(\d+)年超(\d+)年以下）", n)
    if m: return "Liquidity", f"Liquidity Enhancement Auction ({m.group(1)}–{m.group(2)}y remaining)" if m.group(1) != "11" else "Liquidity Enhancement Auction (11–39y remaining)"
    return None, None

def month_rows(yy, mm):
    try:
        h = get(f"https://www.mof.go.jp/jgbs/auction/calendar/{yy:02d}{mm:02d}.htm")
    except Exception:
        return None
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        tds = [re.sub(r"<[^>]*>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) < 2: continue
        d = re.match(r"(\d+)月(\d+)日（(.)）", tds[0])
        if not d: continue
        typ, issue = classify(tds[1])
        if not typ: continue
        rows.append({"date": f"{calendar.month_abbr[int(d.group(1))]} {int(d.group(2))} ({WD.get(d.group(3), d.group(3))})", "type": typ, "issue": issue, "context": ""})
    return rows

today = date.today()
new = {}
y, m = 26, 9
while True:
    r = month_rows(y, m)
    if r is None or not r: break
    new[f"{calendar.month_name[m]} 20{y}"] = r
    m += 1
    if m > 12: m, y = 1, y + 1
for f in FILES:
    d = json.load(open(f))
    added = [k for k in new if k not in d["auctions"]]
    for k in added: d["auctions"][k] = new[k]
    json.dump(d, open(f, "w"), indent=2, ensure_ascii=False)
    print(f, "added", added)
