"""
MOF gross JGB issuance (coupon-bearing bonds), monthly, from the auction-results
historical workbook: mof.go.jp/jgbs/reference/appendix/jgb_historical_data.xls

This is the "Net JGB supply to private sector" / "BOJ absorption ratio" data source
flagged as the highest-leverage missing item (unlocks 3 top-priority items at once)
in the 2026-08-09 BOJ-Balance-Sheet-tab upgrade doc — see boj-hawk-dove-assessment/AGENTS.md.

The workbook has one worksheet per tenor/instrument (14 sheets). Each sheet has the
same header block (Japanese header row, English header row, units row, then data),
though column order/count vary slightly per sheet, so columns are located by their
Japanese header name rather than fixed position.

Per-auction total issuance uses the "Offering Amount" (発行予定額) column rather than
summing the accepted-competitive + non-competitive-tranche columns: those columns are
positioned inconsistently across sheets, and spot-checking recent 10Y auctions shows
their sum tracks the offering amount to within ~0.1%, so offering amount is used
directly as the auction's total issuance size.

Treasury Discount Bills (sheet 'TB ') are excluded from "gross JGB issuance" — BOJ's
own MD06 series tracks T-Bill outright purchases separately from JGB purchases
(tbill_purchases_outright vs jgb_purchases_outright in boj_balance_sheet.json), so an
apples-to-apples absorption-ratio/net-supply comparison must also exclude T-Bills here.
GX Bonds (climate-transition JGBs) and retail JGBs (4Y/6Y fixed, 15Y floating) ARE
included — they are still coupon-bearing government bonds MOF issues and BOJ's JGB
purchase series does not exclude them.
"""
import json
import os
from datetime import datetime, timezone

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(HERE, "mof_source")
SRC_XLS = os.path.join(SRC_DIR, "jgb_historical_data.xls")
OUT = os.path.join(HERE, "mof_issuance.json")
UA = {"User-Agent": "Mozilla/5.0"}
URL = "https://www.mof.go.jp/jgbs/reference/appendix/jgb_historical_data.xls"

# Sheets that represent coupon-bearing JGBs (excludes 'TB ' = Treasury Discount Bills)
COUPON_SHEETS = [
    "2年債", "4年債", "5年債", "6年債", "割3年", "15変動",
    "10年債", "10年物価連動", "20年債", "30年債", "40年債",
    "GX5年債", "GX10年債",
]

TENOR_LABEL = {
    "2年債": "2Y", "4年債": "4Y (retail)", "5年債": "5Y", "6年債": "6Y (retail)",
    "割3年": "3Y (discount)", "15変動": "15Y (floating, retail)",
    "10年債": "10Y", "10年物価連動": "10Y (inflation-linked)",
    "20年債": "20Y", "30年債": "30Y", "40年債": "40Y",
    "GX5年債": "GX 5Y", "GX10年債": "GX 10Y",
}


def download():
    os.makedirs(SRC_DIR, exist_ok=True)
    r = requests.get(URL, headers=UA, timeout=60)
    r.raise_for_status()
    with open(SRC_XLS, "wb") as f:
        f.write(r.content)


def parse_sheet(xls_path, sheet_name):
    """Returns list of (issue_month 'YYYY-MM', offering_amount_100mn_yen)."""
    df = pd.read_excel(xls_path, sheet_name=sheet_name, header=None)
    hdr_idx = None
    for i in range(min(6, len(df))):
        if str(df.iloc[i, 0]).strip() == "回号":
            hdr_idx = i
            break
    if hdr_idx is None:
        raise RuntimeError(f"header row not found in sheet {sheet_name!r}")
    header = [str(v).strip() for v in df.iloc[hdr_idx].values]
    col_issue_date = header.index("発行日")
    col_offer_amt = header.index("発行予定額")
    data = df.iloc[hdr_idx + 3:]

    out = []
    for _, row in data.iterrows():
        issue_date = row.iloc[col_issue_date]
        amt = row.iloc[col_offer_amt]
        if pd.isna(issue_date) or pd.isna(amt):
            continue
        if not isinstance(issue_date, (datetime, pd.Timestamp)):
            continue
        try:
            amt = float(amt)
        except (TypeError, ValueError):
            continue
        out.append((issue_date.strftime("%Y-%m"), amt))
    return out


def build():
    download()  # always pull the latest workbook MOF has published

    by_month_total = {}
    by_month_tenor = {}
    for sheet in COUPON_SHEETS:
        rows = parse_sheet(SRC_XLS, sheet)
        label = TENOR_LABEL[sheet]
        for month, amt_100mn in rows:
            by_month_total[month] = by_month_total.get(month, 0.0) + amt_100mn
            by_month_tenor.setdefault(month, {})
            by_month_tenor[month][label] = by_month_tenor[month].get(label, 0.0) + amt_100mn

    months = sorted(by_month_total.keys())
    # source amounts are in 億円 (100-million-yen) units; 1 兆円 (tn yen) = 10,000 億円
    gross_issuance_jpy_tn = [round(by_month_total[m] / 10000.0, 3) for m in months]

    # This workbook is a periodically-republished MOF snapshot (not real-time) — its
    # own internal save timestamp typically trails "today" by several weeks, and
    # different tenor sheets stop at different auction dates within that trailing
    # window. Rather than show a misleadingly-low final month (only some tenors'
    # auctions captured before the snapshot was taken), drop trailing months whose
    # total is under half the prior 6-month average — a partial-month, not a real dip.
    trim = 0
    while len(months) > 6:
        recent = gross_issuance_jpy_tn[-7:-1]
        avg_recent = sum(recent) / len(recent)
        if gross_issuance_jpy_tn[-1] < 0.5 * avg_recent:
            months.pop()
            gross_issuance_jpy_tn.pop()
            trim += 1
        else:
            break

    tenor_labels = [TENOR_LABEL[s] for s in COUPON_SHEETS]
    by_tenor_jpy_tn = {
        lbl: [round(by_month_tenor.get(m, {}).get(lbl, 0.0) / 10000.0, 3) for m in months]
        for lbl in tenor_labels
    }

    out = {
        "meta": {
            "source": "Ministry of Finance Japan, JGB auction historical data workbook",
            "source_url": "https://www.mof.go.jp/jgbs/reference/appendix/jgb_historical_data.xls",
            "reference_page": "https://www.mof.go.jp/jgbs/reference/appendix/index.htm",
            "method": (
                "Per-auction total issuance = 'Offering Amount' (発行予定額) column, summed by "
                "issue-date ('発行日') calendar month across all coupon-bearing-JGB tenor "
                "worksheets. Treasury Discount Bills (sheet 'TB ') are excluded to match "
                "BOJ's own MD06 series, which tracks JGB and T-Bill outright purchases "
                "separately (see boj_balance_sheet.json 'operations')."
            ),
            "tenors_included": tenor_labels,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "as_of_month": months[-1] if months else None,
            "partial_trailing_months_dropped": trim,
            "workbook_last_saved_note": (
                "MOF republishes this workbook periodically, not in real time — its "
                "internal save date typically trails the current date by several weeks, "
                "so the most recent 1-3 months here reflect whatever auctions had "
                "occurred by that snapshot, not the full calendar month."
            ),
        },
        "months": months,
        "gross_issuance_jpy_tn": gross_issuance_jpy_tn,
        "by_tenor_jpy_tn": by_tenor_jpy_tn,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {OUT}: {len(months)} months, {months[0]}..{months[-1]}, "
          f"latest gross issuance ¥{gross_issuance_jpy_tn[-1]:.2f}tn")


if __name__ == "__main__":
    build()
