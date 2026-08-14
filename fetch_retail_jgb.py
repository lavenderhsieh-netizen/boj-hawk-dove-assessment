#!/usr/bin/env python3.12
"""Retail JGB demand — MOF's monthly "個人向け国債の応募額" (Retail JGB subscription
amount) press releases, one of the two sources HanHan asked for (2026-08-14 Telegram:
"Where can I find retail JGB data and demand?" -> approved building this card).

Source: MOF's annual "What's New: JGBs" index pages
  https://www.mof.go.jp/public_relations/whats_new/{year}jgbs.html
list every monthly release as a link to
  https://www.mof.go.jp/jgbs/individual/kojinmuke/houdouhappyou/p{pub_YYYYMMDD}.htm
(publication date, not data month — e.g. p20260806.htm published 2026-08-06 covers
July 2026 data). Anchor text carries the Reiwa-era target month, e.g.
"個人向け国債の応募額（令和8年7月）" = Reiwa 8 = 2026, month 7. The release page itself
restates the target month/issue-date sentence plus 3 lines, one per retail product
(変動10年 floating-10yr / 固定5年 fixed-5yr / 固定3年 fixed-3yr), each with its bond
series number and subscription amount in 億円 (100mn yen).

This is genuinely different from the BOJ Flow of Funds "Households" JGB-holdings series
already on this dashboard (household_assets.json / jgb_holders_history.json) — that's a
quarterly STOCK of what households already hold; this is a monthly FLOW of what they're
subscribing to at each month's offering, MOF's own primary demand signal.

Output: retail_jgb.json — list of {date (YYYY-MM), pub_date, floating10_bn, fixed5_bn,
fixed3_bn, total_bn} in ¥bn (億円 / 10), sorted ascending by date; a dedup keeps the
newest pub_date's figure per data month (MOF republishes/revises occasionally per the
page's own disclaimer: "計数は、取扱機関からの報告を基に作成しています。報告の訂正等に
より計数に異同を生じることがあります").

Usage: python3.12 fetch_retail_jgb.py
"""
import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "retail_jgb.json")
UA = {"User-Agent": "Mozilla/5.0"}
INDEX_URL = "https://www.mof.go.jp/public_relations/whats_new/{year}jgbs.html"
YEARS = [2023, 2024, 2025, 2026]

LINK_RE = re.compile(
    r'href="([^"]*houdouhappyou/p(\d{8})\.htm)"[^>]*>\s*個人向け国債の応募額（令和(\d+)年(\d+)月）'
)
ROW_RE = re.compile(
    r'個人向け利付国庫債券（(変動10年|固定\s*5年|固定\s*3年)）\s*第(\d+)回債[&nbsp;\s]*([\d,]+)億円'
)


def fetch_text(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def reiwa_to_iso(reiwa_year, month):
    year = int(reiwa_year) + 2018
    return f"{year}-{int(month):02d}"


def parse_release(html):
    """Returns dict of product -> 億円 amount, or None if page didn't parse."""
    out = {}
    for m in ROW_RE.finditer(html):
        product_raw, series_no, amt_str = m.groups()
        product = re.sub(r"\s+", "", product_raw)
        amt = float(amt_str.replace(",", ""))
        key = {"変動10年": "floating10", "固定5年": "fixed5", "固定3年": "fixed3"}[product]
        out[key] = {"series": int(series_no), "oku_yen": amt}
    return out or None


def main():
    by_month = {}
    for year in YEARS:
        try:
            idx_html = fetch_text(INDEX_URL.format(year=year))
        except Exception as e:
            print(f"  index {year} failed: {e}")
            continue
        links = LINK_RE.findall(idx_html)
        print(f"  {year}: {len(links)} release links found")
        for href, pub_date, reiwa_year, month in links:
            data_month = reiwa_to_iso(reiwa_year, month)
            url = "https://www.mof.go.jp" + href[href.index("/jgbs"):] if href.startswith("../") else href
            if not url.startswith("http"):
                url = "https://www.mof.go.jp" + href.lstrip(".")
            try:
                page_html = fetch_text(url)
            except Exception as e:
                print(f"    {data_month} ({url}) failed: {e}")
                continue
            parsed = parse_release(page_html)
            if not parsed:
                print(f"    {data_month} ({url}) — no rows parsed, skipping")
                continue
            prev = by_month.get(data_month)
            if prev is None or pub_date > prev["pub_date"]:
                by_month[data_month] = {"pub_date": pub_date, **parsed}

    rows = []
    for data_month in sorted(by_month):
        d = by_month[data_month]
        f10 = d.get("floating10", {}).get("oku_yen", 0.0)
        f5 = d.get("fixed5", {}).get("oku_yen", 0.0)
        f3 = d.get("fixed3", {}).get("oku_yen", 0.0)
        rows.append({
            "date": data_month,
            "pub_date": d["pub_date"],
            "floating10_bn": round(f10 / 10, 2),
            "fixed5_bn": round(f5 / 10, 2),
            "fixed3_bn": round(f3 / 10, 2),
            "total_bn": round((f10 + f5 + f3) / 10, 2),
            "series": {
                "floating10": d.get("floating10", {}).get("series"),
                "fixed5": d.get("fixed5", {}).get("series"),
                "fixed3": d.get("fixed3", {}).get("series"),
            },
        })

    with open(OUT, "w") as f:
        json.dump({
            "meta": {
                "unit": "JPY bn",
                "source": "MOF 個人向け国債の応募額 (Retail JGB subscription amount), monthly press releases",
                "source_url": "https://www.mof.go.jp/jgbs/individual/kojinmuke/houdouhappyou/",
                "note": "Subscription (応募額) amounts by product for the month; issue date is mid-following-month. Figures may be revised by MOF; newest publication per month kept.",
            },
            "rows": rows,
        }, f, indent=2, ensure_ascii=False)

    print(f"wrote {OUT} — {len(rows)} months, {rows[0]['date']} to {rows[-1]['date']}")
    latest = rows[-1]
    print(f"  latest ({latest['date']}): floating10 ¥{latest['floating10_bn']}bn, "
          f"fixed5 ¥{latest['fixed5_bn']}bn, fixed3 ¥{latest['fixed3_bn']}bn, "
          f"total ¥{latest['total_bn']}bn")


if __name__ == "__main__":
    main()
