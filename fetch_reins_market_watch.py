#!/usr/bin/env python3.12
"""REINS Market Watch — monthly resale (existing/used) condominium & detached
house market data for the Greater Tokyo Area (首都圏: Tokyo/Kanagawa/Saitama/
Chiba), the closest Japan equivalent to Korea's KB breadth/resale series — a
demand-health gauge (contracts, price, inventory) distinct from MLIT's
transaction-price INDEX (fetch_mlit_property_index.py).

Source: 公益財団法人東日本不動産流通機構 (REINS, "East Japan Real Estate
  Information Network for East Japan"), 国土交通大臣指定 (MLIT-designated).
  Monthly "月例速報 Market Watch サマリーレポート" (Monthly Market Watch
  Summary Report), page 1, published ~10th-12th of the following month.
  URL pattern (stable, no login/key): https://www.reins.or.jp/pdf/trend/mw/mw_{YYYYMM}_summary.pdf
  Library index page: https://www.reins.or.jp/library/

Text-based PDF (confirmed via pdftotext -layout, no OCR needed). Two report
layouts found across the available history (earliest file that resolves is
2014-04 — 2014-01/02/03 and everything before 404s, REINS appears to only
host from 2014-04 onward at this URL pattern):

  ERA 1 "narrative" layout, 2014-04 through 2025-03 (confirmed stable across
    manual spot-checks in 2014/15/16/17/18/19/20/21/22/23/24/25): condo block
    gives 件数(count)+YoY%, m2単価(price/sqm)+YoY%, 価格(price)+YoY%, plus
    専有面積(floor area)+築(後)年数(age) — for 2014-04/2015-01 these last two
    have NO comparator at all (bare values only); from ~2016 onward they each
    carry their own comparator (専有面積 gets a YoY%, 築年数 gets an absolute
    prior-year/prior-month age, not a %). House block mirrors this with
    土地面積(land area)/建物面積(building area) in place of 専有面積. This era
    does NOT publish a clean inventory (在庫件数) number on page 1 — inventory
    trend is only mentioned qualitatively in prose ("24 ヶ月連続で増加" etc.)
    from ~2016 onward, with the exact figure buried in a later "○在庫件数"
    prose paragraph in inconsistent phrasing — not reliably regex-extractable
    across all months, so NOT captured here (left null) to avoid silent
    mis-parses; only the headline count/price/area/age fields are captured
    for this era.

  ERA 2 "table" layout, 2025-05 onward (format changed starting the May-2025
    data / Jun-2025-published report): condo AND house blocks both get a
    clean 2-column table — 成約状況 (contract side: count, price/sqm, price,
    area, age; count+price+sqm have YoY% AND MoM%) vs. 在庫状況 (inventory
    side: count + price/sqm + price + area + age, each with YoY% only) — this
    era DOES give a clean inventory count + YoY, captured here.

Both eras are merged into ONE continuous monthly series per field where the
field exists in both eras (count, price, price/sqm [condo], area, age);
MoM% and inventory fields are only populated from 2025-05 onward (null
before) — see each series' own "available_from" note. Do NOT re-derive MoM
or inventory for Era 1 months; it was not published in extractable form.

Usage: python3.12 fetch_reins_market_watch.py
"""
import datetime
import json
import os
import re
import subprocess
import unicodedata

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "property_data.json")
UA = {"User-Agent": "Mozilla/5.0"}
URL_TMPL = "https://www.reins.or.jp/pdf/trend/mw/mw_{ym}_summary.pdf"

EARLIEST = (2014, 4)
ERA2_START = (2025, 5)  # first month with the new table layout

SOURCE_META = {
    "source": "公益財団法人東日本不動産流通機構 (REINS — Real Estate Information Network "
               "for East Japan), MOLIT-designated (国土交通大臣指定) — "
               "月例速報 Market Watch サマリーレポート (Monthly Market Watch Summary Report), "
               "page 1 headline table, Greater Tokyo Area (首都圏: Tokyo/Kanagawa/Saitama/Chiba)",
    "source_url_pattern": "https://www.reins.or.jp/pdf/trend/mw/mw_{YYYYMM}_summary.pdf",
    "library_url": "https://www.reins.or.jp/library/",
    "freq": "monthly",
    "publication_lag": "published ~10th-12th of the month following the data month",
    "format_note": (
        "Report layout changed starting the 2025-05 data month: pre-2025-05 ('Era 1') "
        "gives count/price/price-per-sqm/area/age with YoY% only, no clean inventory "
        "figure on page 1; 2025-05 onward ('Era 2') adds a clean inventory (在庫) count "
        "+ YoY% and MoM% for count/price/price-per-sqm. Series below are a single merged "
        "monthly time series per field; MoM% and inventory fields are null before 2025-05 "
        "(not published in a reliably-extractable form pre-2025-05 — left null rather than "
        "guessed). Earliest available report at this URL pattern is 2014-04 (2014-01/02/03 "
        "and earlier all 404)."
    ),
}


def month_range(start, end):
    y, m = start
    while (y, m) <= end:
        yield y, m
        m += 1
        if m == 13:
            m = 1
            y += 1


def fetch_pdf_text(ym):
    url = URL_TMPL.format(ym=ym)
    r = requests.get(url, headers=UA, timeout=30, verify=False)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return None
    tmp_path = f"/tmp/_reins_{ym}.pdf"
    with open(tmp_path, "wb") as f:
        f.write(r.content)
    try:
        txt = subprocess.run(["pdftotext", "-layout", tmp_path, "-"],
                              capture_output=True, text=True, timeout=30).stdout
    finally:
        os.remove(tmp_path)
    return unicodedata.normalize("NFKC", txt).replace("(", "").replace(")", "")


# ---------------------------------------------------------------------------
# Era 2 (2025-05+) table-layout regexes
# ---------------------------------------------------------------------------
E2_COUNT = re.compile(r'件数\s+([\d,]+)\s*件\s+([+-]?[\d.]+)%\s+[-−―]\s+([\d,]+)\s*件\s+([+-]?[\d.]+)%')
E2_SQM = re.compile(r'm2単価\s+([\d.]+)\s*万円/m2\s+([+-]?[\d.]+)%\s+([+-]?[\d.]+)%\s+([\d.]+)\s*万円/m2\s+([+-]?[\d.]+)%')
E2_PRICE = re.compile(r'価格\s+([\d,]+)\s*万円\s+([+-]?[\d.]+)%\s+([+-]?[\d.]+)%\s+([\d,]+)\s*万円\s+([+-]?[\d.]+)%')
E2_AREA = re.compile(r'専有面積\s+([\d.]+)\s*m2\s+([+-]?[\d.]+)%\s+([+-]?[\d.]+)%\s+([\d.]+)\s*m2\s+([+-]?[\d.]+)%')
E2_LAND = re.compile(r'土地面積\s+([\d.]+)\s*m2\s+([+-]?[\d.]+)%\s+([+-]?[\d.]+)%\s+([\d.]+)\s*m2\s+([+-]?[\d.]+)%')
E2_BUILD = re.compile(r'建物面積\s+([\d.]+)\s*m2\s+([+-]?[\d.]+)%\s+([+-]?[\d.]+)%\s+([\d.]+)\s*m2\s+([+-]?[\d.]+)%')
E2_AGE = re.compile(r'築年数\s+([\d.]+)\s*年\s+([\d.]+)\s*年\s+([\d.]+)\s*年\s+([\d.]+)\s*年\s+([\d.]+)\s*年')


def parse_era2(text):
    counts = E2_COUNT.findall(text)
    prices = E2_PRICE.findall(text)
    ages = E2_AGE.findall(text)
    sqm = E2_SQM.findall(text)
    area = E2_AREA.findall(text)
    land = E2_LAND.findall(text)
    build = E2_BUILD.findall(text)
    if len(counts) != 2 or len(prices) != 2 or len(ages) != 2 or len(sqm) != 1 \
       or len(area) != 1 or len(land) != 1 or len(build) != 1:
        return None
    condo = {
        "contract_count": int(counts[0][0].replace(",", "")), "contract_count_yoy_pct": float(counts[0][1]),
        "inventory_count": int(counts[0][2].replace(",", "")), "inventory_count_yoy_pct": float(counts[0][3]),
        "price_per_sqm_manyen": float(sqm[0][0]), "price_per_sqm_yoy_pct": float(sqm[0][1]),
        "price_per_sqm_mom_pct": float(sqm[0][2]),
        "inventory_price_per_sqm_manyen": float(sqm[0][3]), "inventory_price_per_sqm_yoy_pct": float(sqm[0][4]),
        "price_manyen": float(prices[0][0].replace(",", "")), "price_yoy_pct": float(prices[0][1]),
        "price_mom_pct": float(prices[0][2]),
        "inventory_price_manyen": float(prices[0][3].replace(",", "")), "inventory_price_yoy_pct": float(prices[0][4]),
        "floor_area_sqm": float(area[0][0]), "floor_area_yoy_pct": float(area[0][1]),
        "floor_area_mom_pct": float(area[0][2]),
        "inventory_floor_area_sqm": float(area[0][3]), "inventory_floor_area_yoy_pct": float(area[0][4]),
        "age_years": float(ages[0][0]), "age_years_yoy": float(ages[0][1]), "age_years_mom": float(ages[0][2]),
        "inventory_age_years": float(ages[0][3]), "inventory_age_years_yoy": float(ages[0][4]),
    }
    house = {
        "contract_count": int(counts[1][0].replace(",", "")), "contract_count_yoy_pct": float(counts[1][1]),
        "inventory_count": int(counts[1][2].replace(",", "")), "inventory_count_yoy_pct": float(counts[1][3]),
        "price_manyen": float(prices[1][0].replace(",", "")), "price_yoy_pct": float(prices[1][1]),
        "price_mom_pct": float(prices[1][2]),
        "inventory_price_manyen": float(prices[1][3].replace(",", "")), "inventory_price_yoy_pct": float(prices[1][4]),
        "land_area_sqm": float(land[0][0]), "land_area_yoy_pct": float(land[0][1]),
        "land_area_mom_pct": float(land[0][2]),
        "inventory_land_area_sqm": float(land[0][3]), "inventory_land_area_yoy_pct": float(land[0][4]),
        "building_area_sqm": float(build[0][0]), "building_area_yoy_pct": float(build[0][1]),
        "building_area_mom_pct": float(build[0][2]),
        "inventory_building_area_sqm": float(build[0][3]), "inventory_building_area_yoy_pct": float(build[0][4]),
        "age_years": float(ages[1][0]), "age_years_yoy": float(ages[1][1]), "age_years_mom": float(ages[1][2]),
        "inventory_age_years": float(ages[1][3]), "inventory_age_years_yoy": float(ages[1][4]),
    }
    return condo, house


# ---------------------------------------------------------------------------
# Era 1 (2014-04 .. 2025-04) narrative-layout regexes
# ---------------------------------------------------------------------------
E1_COUNT = re.compile(r'(?:成約)?件\s*数\s+([\d,]+)\s*件\s+前年同月比\s*([+-]?[\d.]+)%')
E1_SQM = re.compile(r'm2単価\s+([\d.]+)\s*万円/m2\s+前年同月比\s*([+-]?[\d.]+)%')
E1_PRICE = re.compile(r'(?:成約)?価\s*格\s+([\d,]+)\s*万円\s+前年同月比\s*([+-]?[\d.]+)%')
E1_AREA_WITH_CMP = re.compile(r'専有面積\s+([\d.]+)\s*m2\s+前年同月比\s*([+-]?[\d.]+)%')
E1_AREA_BARE = re.compile(r'専有面積\s+([\d.]+)\s*m2\s+築(?:後)?年数\s+([\d.]+)\s*年')
E1_LAND_WITH_CMP = re.compile(r'土地面積\s+([\d.]+)\s*m2\s+前年同月比\s*([+-]?[\d.]+)%')
E1_BUILD_WITH_CMP = re.compile(r'建物面積\s+([\d.]+)\s*m2\s+前年同月比\s*([+-]?[\d.]+)%')
E1_LAND_BUILD_BARE = re.compile(r'土地面積\s+([\d.]+)\s*m2\s+建物面積\s+([\d.]+)\s*m2')
E1_AGE_WITH_CMP = re.compile(r'築(?:後)?年数\s+([\d.]+)\s*年\s+前年同月\s+([\d.]+)\s*年')
E1_AGE_BARE = re.compile(r'築(?:後)?年数\s+([\d.]+)\s*年')


def _split_condo_house(text):
    """Era-1 reports repeat '中古戸建住宅' many times — first as a table-of-
    contents entry (immediately followed by 件数/価格/成約, no whitespace),
    then as the real house-block data header (followed by many spaces before
    件   数). Splitting on the first bare occurrence (as an earlier version
    of this function did) grabs the ToC instead of the real header, which
    truncates condo_txt before the real condo data and never isolates a
    real house_txt — silently failing to parse every Era-1 month. Require
    several spaces after the marker to land on the real header instead."""
    m = re.search(r'中古戸建住宅\s{5,}件', text)
    if not m:
        return text, ""
    idx = m.start()
    return text[:idx], text[idx:]


def _first(rx, text):
    m = rx.search(text)
    return m.groups() if m else None


def parse_era1(text):
    condo_txt, house_txt = _split_condo_house(text)
    if not condo_txt.strip() or not house_txt.strip():
        return None

    c_count = _first(E1_COUNT, condo_txt)
    c_price = _first(E1_PRICE, condo_txt)
    c_sqm = _first(E1_SQM, condo_txt)
    if not (c_count and c_price and c_sqm):
        return None
    c_age_cmp = _first(E1_AGE_WITH_CMP, condo_txt)
    c_area_cmp = _first(E1_AREA_WITH_CMP, condo_txt)
    c_area_bare = _first(E1_AREA_BARE, condo_txt)

    condo = {
        "contract_count": int(c_count[0].replace(",", "")), "contract_count_yoy_pct": float(c_count[1]),
        "price_per_sqm_manyen": float(c_sqm[0]), "price_per_sqm_yoy_pct": float(c_sqm[1]),
        "price_manyen": float(c_price[0].replace(",", "")), "price_yoy_pct": float(c_price[1]),
    }
    if c_area_cmp:
        condo["floor_area_sqm"] = float(c_area_cmp[0])
        condo["floor_area_yoy_pct"] = float(c_area_cmp[1])
    elif c_area_bare:
        condo["floor_area_sqm"] = float(c_area_bare[0])
        condo["floor_area_yoy_pct"] = None
        if c_age_cmp is None:
            condo["age_years"] = float(c_area_bare[1])
    if c_age_cmp:
        condo["age_years"] = float(c_age_cmp[0])
        condo["age_years_prior_year"] = float(c_age_cmp[1])
    elif "age_years" not in condo:
        a = _first(E1_AGE_BARE, condo_txt)
        if a:
            condo["age_years"] = float(a[0])

    h_count = _first(E1_COUNT, house_txt)
    h_price = _first(E1_PRICE, house_txt)
    if not (h_count and h_price):
        return None
    house = {
        "contract_count": int(h_count[0].replace(",", "")), "contract_count_yoy_pct": float(h_count[1]),
        "price_manyen": float(h_price[0].replace(",", "")), "price_yoy_pct": float(h_price[1]),
    }
    h_land_cmp = _first(E1_LAND_WITH_CMP, house_txt)
    h_build_cmp = _first(E1_BUILD_WITH_CMP, house_txt)
    h_land_build_bare = _first(E1_LAND_BUILD_BARE, house_txt)
    if h_land_cmp:
        house["land_area_sqm"] = float(h_land_cmp[0])
        house["land_area_yoy_pct"] = float(h_land_cmp[1])
    elif h_land_build_bare:
        house["land_area_sqm"] = float(h_land_build_bare[0])
        house["land_area_yoy_pct"] = None
    if h_build_cmp:
        house["building_area_sqm"] = float(h_build_cmp[0])
        house["building_area_yoy_pct"] = float(h_build_cmp[1])
    elif h_land_build_bare:
        house["building_area_sqm"] = float(h_land_build_bare[1])
        house["building_area_yoy_pct"] = None
    h_age_cmp = _first(E1_AGE_WITH_CMP, house_txt)
    if h_age_cmp:
        house["age_years"] = float(h_age_cmp[0])
        house["age_years_prior_year"] = float(h_age_cmp[1])
    else:
        a = _first(E1_AGE_BARE, house_txt)
        if a:
            house["age_years"] = float(a[0])

    return condo, house


ALL_FIELDS_CONDO = [
    "contract_count", "contract_count_yoy_pct", "inventory_count", "inventory_count_yoy_pct",
    "price_per_sqm_manyen", "price_per_sqm_yoy_pct", "price_per_sqm_mom_pct",
    "inventory_price_per_sqm_manyen", "inventory_price_per_sqm_yoy_pct",
    "price_manyen", "price_yoy_pct", "price_mom_pct", "inventory_price_manyen", "inventory_price_yoy_pct",
    "floor_area_sqm", "floor_area_yoy_pct", "floor_area_mom_pct",
    "inventory_floor_area_sqm", "inventory_floor_area_yoy_pct",
    "age_years", "age_years_yoy", "age_years_mom", "age_years_prior_year",
    "inventory_age_years", "inventory_age_years_yoy",
]
ALL_FIELDS_HOUSE = [
    "contract_count", "contract_count_yoy_pct", "inventory_count", "inventory_count_yoy_pct",
    "price_manyen", "price_yoy_pct", "price_mom_pct", "inventory_price_manyen", "inventory_price_yoy_pct",
    "land_area_sqm", "land_area_yoy_pct", "land_area_mom_pct",
    "inventory_land_area_sqm", "inventory_land_area_yoy_pct",
    "building_area_sqm", "building_area_yoy_pct", "building_area_mom_pct",
    "inventory_building_area_sqm", "inventory_building_area_yoy_pct",
    "age_years", "age_years_yoy", "age_years_mom", "age_years_prior_year",
    "inventory_age_years", "inventory_age_years_yoy",
]


def load_existing():
    if os.path.exists(OUT):
        with open(OUT) as f:
            return json.load(f)
    return {}


def main():
    today = datetime.date.today()
    # data lags ~1-1.5 months; start probing from 2 months ago and walk
    # forward, but the loop below just tries every month and skips misses.
    end = (today.year, today.month)

    rows = []  # list of (label, condo_dict_or_None, house_dict_or_None)
    misses = 0
    for y, m in month_range(EARLIEST, end):
        ym = f"{y:04d}{m:02d}"
        text = fetch_pdf_text(ym)
        if text is None:
            misses += 1
            continue
        era2 = (y, m) >= ERA2_START
        parsed = parse_era2(text) if era2 else parse_era1(text)
        if parsed is None and era2:
            # format may have shifted a bit right at the boundary; fall back
            parsed = parse_era1(text)
        if parsed is None:
            print(f"  {ym}: could not parse (skipped)")
            continue
        condo, house = parsed
        rows.append((f"{y:04d}-{m:02d}", condo, house))

    if not rows:
        raise SystemExit("no REINS months parsed — aborting without touching property_data.json")

    labels = [r[0] for r in rows]
    condo_series = {f: [r[1].get(f) for r in rows] for f in ALL_FIELDS_CONDO}
    house_series = {f: [r[2].get(f) for r in rows] for f in ALL_FIELDS_HOUSE}

    out = load_existing()
    out["reins_market_watch"] = {
        **SOURCE_META,
        "as_of": labels[-1],
        "as_of_range": f"{labels[0]} to {labels[-1]}",
        "labels": labels,
        "condo": condo_series,
        "house": house_series,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"wrote {OUT}")
    print(f"  REINS Market Watch: {len(labels)} months, {labels[0]} to {labels[-1]}")
    print(f"  latest condo: {rows[-1][1]}")
    print(f"  latest house: {rows[-1][2]}")


if __name__ == "__main__":
    main()
