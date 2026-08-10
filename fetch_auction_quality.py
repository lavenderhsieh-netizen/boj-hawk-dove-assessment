"""
JGB auction-quality metrics (tail, bid-to-cover) from MOF's auction-history workbook —
the same source as fetch_mof_issuance.py (mof_source/jgb_historical_data.xls). Built for
the Balance Sheet tab's "market-impact panel" ask (2026-08-10 review doc): does BOJ QT
show up in auction quality, not just yields?

Tail (yield terms, bp) = yield at lowest accepted price - yield at weighted average price.
Wider tail = weaker demand at the margin (more spread between the average and worst
accepted bid). Bid-to-cover = competitive bids submitted / competitive bids accepted.

Currently covers 30Y (the tenor named in the review doc) and 10Y (the benchmark tenor,
cheap to add from the same sheet-parsing code).
"""
import json
import os
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_XLS = os.path.join(HERE, "mof_source", "jgb_historical_data.xls")
OUT = os.path.join(HERE, "auction_quality.json")

TENOR_SHEETS = {"30Y": "30年債", "10Y": "10年債"}


def parse_sheet(sheet_name):
    df = pd.read_excel(SRC_XLS, sheet_name=sheet_name, header=None)
    hdr_idx = next(i for i in range(6) if str(df.iloc[i, 0]).strip() == "回号")
    header = [str(v).strip() for v in df.iloc[hdr_idx].values]
    col = {name: header.index(name) for name in
           ["入札日", "応募額", "落札・割当額", "平均利回", "最高利回"]}
    data = df.iloc[hdr_idx + 3:]

    out = []
    for _, row in data.iterrows():
        auction_date = row.iloc[col["入札日"]]
        if pd.isna(auction_date) or not isinstance(auction_date, (datetime, pd.Timestamp)):
            continue
        try:
            bids = float(row.iloc[col["応募額"]])
            accepted = float(row.iloc[col["落札・割当額"]])
            avg_yield = float(row.iloc[col["平均利回"]])
            tail_yield = float(row.iloc[col["最高利回"]])
        except (TypeError, ValueError):
            continue
        if accepted <= 0:
            continue
        out.append({
            "date": auction_date.strftime("%Y-%m-%d"),
            "month": auction_date.strftime("%Y-%m"),
            "bid_to_cover": round(bids / accepted, 2),
            "tail_bp": round((tail_yield - avg_yield) * 100, 1),
        })
    return out


def build():
    result = {"meta": {
        "source": "MOF JGB auction historical data workbook",
        "source_url": "https://www.mof.go.jp/jgbs/reference/appendix/jgb_historical_data.xls",
        "method": "Per auction: bid-to-cover = competitive bids submitted / competitive bids accepted. "
                  "Tail (bp) = (yield at lowest accepted price - yield at weighted average price) x 100.",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }, "tenors": {}}

    for label, sheet in TENOR_SHEETS.items():
        auctions = parse_sheet(sheet)
        result["tenors"][label] = auctions
        print(f"{label}: {len(auctions)} auctions, latest {auctions[-1]['date']} "
              f"tail={auctions[-1]['tail_bp']}bp btc={auctions[-1]['bid_to_cover']}")

    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
