#!/usr/bin/env python3
"""Parse the BOJ natural-rate-of-interest workbook into natural_rate.json for the
Markets & bonds tab.

Source: BOJ Review 2026-E-4 "Developments in the Natural Rate of Interest and the
Assessment of the Degree of Monetary Accommodation" (27 Mar 2026), Chart 3.
  page:  https://www.boj.or.jp/en/research/wps_rev/rev_2026/rev26e04.htm
  data:  https://www.boj.or.jp/en/research/wps_rev/rev_2026/data/rev26e04b.xlsx

This is a STATIC series — the BOJ re-estimates r* only occasionally (roughly once a
year, after GDP benchmark revisions), so this is NOT on the daily fetch_market.py
refresh (same treatment as fetch_intervention.py). Re-run by hand when the BOJ
publishes a new r* review: drop the fresh workbook into source/ and update SRC below.
"""
import json
import os
import re
import sys

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source", "rev26e04b_natural_rate.xlsx")
OUT = os.path.join(HERE, "natural_rate.json")

# Column order in the workbook's "Chart 3" sheet (D..I), with display names.
MODELS = [
    ("m1", "Del Negro et al. (2017)"),
    ("m2", "Goy and Iwasaki (2024)"),
    ("m3", "Holston, Laubach, and Williams (2023)"),
    ("m4", "Imakubo, Kojima, and Nakajima (2015)"),
    ("m5", "Nakajima et al. (2023)"),
    ("m6", "Okazaki and Sudo (2018)"),
]
QPAT = re.compile(r"^\d{4}Q[1-4]$")


def main():
    if not os.path.exists(SRC):
        sys.exit(f"missing source workbook: {SRC}")
    wb = openpyxl.load_workbook(SRC, data_only=True)
    ws = wb["Chart 3"]
    labels, series = [], {k: [] for k, _ in MODELS}
    for row in ws.iter_rows(values_only=True):
        q = row[2]  # column C holds the CY Quarter label (e.g. 2025Q3)
        if isinstance(q, str) and QPAT.match(q):
            labels.append(q)
            for i, (k, _) in enumerate(MODELS):
                v = row[3 + i]  # columns D..I
                series[k].append(round(v, 4) if isinstance(v, (int, float)) else None)

    out = {
        "title": "Estimates of the Natural Rate of Interest",
        "source": "BOJ Review 2026-E-4 (Chart 3), 27 Mar 2026",
        "source_url": "https://www.boj.or.jp/en/research/wps_rev/rev_2026/rev26e04.htm",
        "unit": "%",
        "freq": "quarterly",
        "labels": labels,
        "models": [{"key": k, "name": n} for k, n in MODELS],
        "series": series,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)

    latest = {k: next((v for v in reversed(series[k]) if v is not None), None) for k, _ in MODELS}
    vals = [v for v in latest.values() if v is not None]
    print(f"wrote {OUT}: {len(labels)} quarters {labels[0]}–{labels[-1]}, "
          f"latest range {min(vals):.2f}% to {max(vals):+.2f}%")


if __name__ == "__main__":
    main()
