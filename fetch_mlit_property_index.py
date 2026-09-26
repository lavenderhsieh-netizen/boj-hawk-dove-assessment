#!/usr/bin/env python3.12
"""Japan residential (and commercial) property price index — MLIT's official
不動産価格指数 (Real Estate Property Price Index), the closest Japan equivalent
to China's NBS 70-city index / the US Case-Shiller index. This is the primary
spine of the new Property tab HanHan is building (2026-09-26 ask).

Source (no API key / registration needed — direct public Excel download):
  Ministry of Land, Infrastructure, Transport and Tourism (国土交通省 / MLIT)
  Page: 不動産価格指数 (Real Estate Price Index)
    https://www.mlit.go.jp/totikensangyo/totikensangyo_tk5_000085.html
  "最新データ" (Latest Data) section direct Excel links (re-checked live 2026-09-26):
    Residential  (不動産価格指数（住宅）):       https://www.mlit.go.jp/totikensangyo/content/001473668.xlsx
    Commercial   (不動産価格指数（商業用不動産）): https://www.mlit.go.jp/common/001465568.xlsx
  Both are monthly-refreshed "latest" links (same URL, content replaced in
  place by MLIT each release) — re-running this script always pulls whatever
  MLIT currently has live at that URL, exactly like fetch_retail_jgb.py fetches
  fresh HTML each run rather than caching a dated snapshot.

  Residential index: published monthly (transaction-based, ~300k transactions/
  year, repeat-sales/hedonic method), base 2010=100. Categories: 住宅総合
  (Residential Property composite), 住宅地 (Residential Land), 戸建住宅
  (Detached House), マンション（区分所有） (Condominiums). We take the
  季節調整 (seasonally-adjusted) sheets, which is what MLIT's own press
  releases headline (raw/原系列 sheets exist in the same workbook if ever
  needed later — not pulled here to keep scope to what HanHan asked for).
  Geography: 全国 (National), plus 3 major metro areas — 南関東圏 (Greater
  Tokyo Area incl. Tokyo/Kanagawa/Saitama/Chiba), 名古屋圏 (Greater Nagoya),
  京阪神圏 (Greater Osaka) — plus 東京都 (Tokyo prefecture alone) as a bonus
  single-prefecture cut (note: this sheet's history starts earlier, 1984, for
  住宅地/戸建住宅 only — 住宅総合/マンション are null before ~2008 in that
  one sheet specifically, see caveat in output).

  Commercial index: published quarterly, base 2010=100. Categories vary by
  sheet — national and 三大都市圏 (3 major metro areas combined) carry all 10
  MLIT commercial categories; 南関東圏 carries a 6-category subset (no 土地
  総合/商業地/工業地 land-only cuts published for that geography). Captured
  as a secondary, bonus series per HanHan's "(and commercial)" framing.

IMPORTANT DATA-QUALITY CAVEAT (found live 2026-09-26, must go in the HTML
note): MLIT posted a public notice on 令和8年8月27日 (2026-08-27) that
publication of the Real Estate Price Index has been POSTPONED due to a
program bug discovered during index calculation. This affects the index for
令和8年1月〜4月 (Jan-Apr 2026, monthly) and 令和8年5月・令和8年第1四半期
(May 2026 / Q1 2026, and the commercial Q4 2025 release originally due ~Apr
2026) onward — i.e. the "latest data" file's most recent point (Dec 2025
monthly / Q4 2025 quarterly as of this fetch) IS genuinely the latest MLIT
has published, not a stale pull on our end. No new publication date has been
announced yet. Re-run this script periodically; it will pick up newer data
automatically once MLIT lifts the postponement — check output as_of vs. this
note's Dec-2025/Q4-2025 baseline to see if it's moved.
  Notice source: https://www.mlit.go.jp/totikensangyo/totikensangyo_tk5_000085.html
  ("お知らせ：令和８年８月27日「不動産価格指数」の公表延期について")

Usage: python3.12 fetch_mlit_property_index.py
"""
import json
import os

import openpyxl
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(HERE, "source")
OUT = os.path.join(HERE, "property_data.json")
UA = {"User-Agent": "Mozilla/5.0"}

RES_URL = "https://www.mlit.go.jp/totikensangyo/content/001473668.xlsx"
COM_URL = "https://www.mlit.go.jp/common/001465568.xlsx"
RES_LOCAL = os.path.join(SRC_DIR, "mlit_residential_price_index.xlsx")
COM_LOCAL = os.path.join(SRC_DIR, "mlit_commercial_price_index.xlsx")

INDEX_PAGE_URL = "https://www.mlit.go.jp/totikensangyo/totikensangyo_tk5_000085.html"

POSTPONEMENT_NOTE = (
    "MLIT announced on 2026-08-27 (令和8年8月27日) that publication of the "
    "不動産価格指数 (Real Estate Price Index) is POSTPONED due to a program "
    "bug discovered during index calculation, affecting Jan-Apr 2026 monthly "
    "data and the May 2026 / Q1 2026 release onward. No new publication date "
    "has been announced as of this fetch. The latest data below (residential "
    "through Dec 2025, commercial through Q4 2025) is genuinely MLIT's most "
    "recent published figure, not a stale pull — re-run this script by hand "
    "once MLIT lifts the postponement to pick up newer data automatically."
)

# Residential sheets: (json_key, display name, sheet name in workbook)
RES_SHEETS = [
    ("national", "National (全国)", "全国Japan季節調整"),
    ("tokyo_metro_area", "Greater Tokyo Area / 南関東圏 (Tokyo, Kanagawa, Saitama, Chiba)",
     "南関東圏Tokyo including季節調整"),
    ("nagoya_metro_area", "Greater Nagoya Area / 名古屋圏", "名古屋圏Nagoya including季節調整"),
    ("osaka_metro_area", "Greater Osaka Area / 京阪神圏", "京阪神圏Osaka including季節調整"),
    ("tokyo_prefecture", "Tokyo Prefecture only / 東京都 "
     "(NOTE: this sheet's own history starts 1984-04 for 住宅地/戸建住宅 only; "
     "住宅総合/マンション are null before they were first compiled, same "
     "~2008 start as the other geographies)", "東京都Tokyo季節調整"),
]
RES_CATEGORY_KEYS = {
    "住宅総合": "residential_composite",
    "住宅地": "residential_land",
    "戸建住宅": "detached_house",
    "マンション（区分所有）": "condominium",
}

# Commercial sheets
COM_SHEETS = [
    ("national", "National (全国)", "全国Japan季節調整"),
    ("three_major_metro_areas", "3 Major Metropolitan Areas combined / 三大都市圏",
     "三大都市圏Three Metropolitan季節調整"),
    ("tokyo_metro_area", "Greater Tokyo Area / 南関東圏", "南関東圏Tokyo including季節調整"),
]
COM_CATEGORY_KEYS = {
    "商業用不動産総合": "commercial_composite",
    "建物付土地総合": "land_with_structure",
    "店舗": "retail",
    "オフィス": "office",
    "倉庫": "warehouse",
    "工場": "factory",
    "ﾏﾝｼｮﾝ･ｱﾊﾟｰﾄ(一棟)": "apartment_building",
    "土地総合": "land_composite",
    "商業地": "commercial_land",
    "工業地": "industrial_land",
}


def download(url, local_path):
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(r.content)
    return local_path


def find_header_row_and_categories(ws, marker_labels):
    """Return (row_idx, [(col_idx, category_label), ...]) for the row that
    contains one of marker_labels (e.g. '住宅総合' or '商業用不動産総合')."""
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if any(v in marker_labels for v in row if isinstance(v, str)):
            cats = [(ci, v) for ci, v in enumerate(row) if isinstance(v, str) and v in marker_labels]
            return i, cats
    raise RuntimeError(f"could not find header row with any of {marker_labels}")


def parse_residential_sheet(ws):
    _, cats = find_header_row_and_categories(ws, set(RES_CATEGORY_KEYS))
    labels_out = []
    series = {RES_CATEGORY_KEYS[name]: [] for _, name in cats}
    for row in ws.iter_rows(values_only=True):
        date = row[0]
        if not hasattr(date, "year"):
            continue
        labels_out.append(f"{date.year:04d}-{date.month:02d}")
        for col_idx, name in cats:
            v = row[col_idx]
            series[RES_CATEGORY_KEYS[name]].append(round(v, 2) if isinstance(v, (int, float)) else None)
    return labels_out, series


def parse_commercial_sheet(ws):
    _, cats = find_header_row_and_categories(ws, set(COM_CATEGORY_KEYS))
    labels_out = []
    series = {COM_CATEGORY_KEYS[name]: [] for _, name in cats}
    for row in ws.iter_rows(values_only=True):
        year, q = row[0], row[1]
        if not isinstance(year, int) or not isinstance(q, int):
            continue
        labels_out.append(f"{year:04d}-Q{q}")
        for col_idx, name in cats:
            v = row[col_idx]
            series[COM_CATEGORY_KEYS[name]].append(round(v, 2) if isinstance(v, (int, float)) else None)
    return labels_out, series


def load_existing():
    if os.path.exists(OUT):
        with open(OUT) as f:
            return json.load(f)
    return {}


def main():
    download(RES_URL, RES_LOCAL)
    download(COM_URL, COM_LOCAL)

    wb_res = openpyxl.load_workbook(RES_LOCAL, data_only=True)
    wb_com = openpyxl.load_workbook(COM_LOCAL, data_only=True)

    res_geo = {}
    for key, name, sheet in RES_SHEETS:
        labels, series = parse_residential_sheet(wb_res[sheet])
        res_geo[key] = {"name": name, "labels": labels, "series": series}

    com_geo = {}
    for key, name, sheet in COM_SHEETS:
        labels, series = parse_commercial_sheet(wb_com[sheet])
        com_geo[key] = {"name": name, "labels": labels, "series": series}

    national_res_labels = res_geo["national"]["labels"]
    national_com_labels = com_geo["national"]["labels"]

    out = load_existing()
    out["mlit_price_index"] = {
        "residential": {
            "source": "Ministry of Land, Infrastructure, Transport and Tourism (国土交通省) — "
                       "不動産価格指数（住宅）/ Real Estate Property Price Index (Residential), "
                       "seasonally adjusted (季節調整値)",
            "source_url": RES_URL,
            "landing_page_url": INDEX_PAGE_URL,
            "freq": "monthly",
            "unit": "Index, average of 2010 = 100",
            "methodology": "Hedonic/repeat-transaction price index built from ~300,000 real "
                            "property transactions per year (registry-based), base year 2010=100.",
            "as_of": national_res_labels[-1] if national_res_labels else None,
            "as_of_range": f"{national_res_labels[0]} to {national_res_labels[-1]}" if national_res_labels else None,
            "postponement_notice": POSTPONEMENT_NOTE,
            "geography": res_geo,
        },
        "commercial": {
            "source": "Ministry of Land, Infrastructure, Transport and Tourism (国土交通省) — "
                       "不動産価格指数（商業用不動産）/ Real Estate Property Price Index (Commercial), "
                       "seasonally adjusted (季節調整値)",
            "source_url": COM_URL,
            "landing_page_url": INDEX_PAGE_URL,
            "freq": "quarterly",
            "unit": "Index, average of 2010 = 100",
            "as_of": national_com_labels[-1] if national_com_labels else None,
            "as_of_range": f"{national_com_labels[0]} to {national_com_labels[-1]}" if national_com_labels else None,
            "postponement_notice": POSTPONEMENT_NOTE,
            "geography": com_geo,
        },
    }

    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"wrote {OUT}")
    print(f"  residential: {len(RES_SHEETS)} geographies, national "
          f"{national_res_labels[0]} to {national_res_labels[-1]} ({len(national_res_labels)} months)")
    print(f"  commercial:  {len(COM_SHEETS)} geographies, national "
          f"{national_com_labels[0]} to {national_com_labels[-1]} ({len(national_com_labels)} quarters)")
    last = res_geo["national"]["series"]["residential_composite"][-1]
    print(f"  latest national residential composite index: {last}")


if __name__ == "__main__":
    main()
