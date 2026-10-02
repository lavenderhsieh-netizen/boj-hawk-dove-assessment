"""Builds Documents/Japan_JGB_Issuance_by_Line_Forecast_<date>.xlsx (v2: + LEAs, buy-backs, redemptions, net)."""
import collections, json, os, sys
from datetime import date
import pandas as pd
import fetch_mof_issuance_lines as m

OUT = f"/home/workspace/Documents/Japan_JGB_Issuance_by_Line_Forecast_{date.today()}.xlsx"

# MOF JGB Monthly Newsletter Sep 2026 (p.8): LEA results (accepted, JPY bn); Sep results from MOF result pages
LEA_ACTUAL = [("2026-06-04", "n/a", 249.8), ("2026-06-19", "n/a", 648.9), ("2026-07-16", "n/a", 699.0), ("2026-07-28", "n/a", 649.0),
              ("2026-08-14", "11-39y", 248.9), ("2026-08-26", "5-11y", 649.4), ("2026-09-10", "1-5y", 697.9), ("2026-09-25", "5-11y", 649.1)]
# Typical accepted size by zone (Apr-Sep 2026 results): 1-5y ~698, 5-11y ~649, 11-39y ~249
ZONE_SIZE = {"1-5y": 698.0, "5-11y": 649.0, "11-39y": 249.0}
LEA_SCHED = [("2026-10-22", "5-11y"), ("2026-10-27", "11-39y"), ("2026-11-20", "1-5y"), ("2026-11-27", "5-11y"),
             ("2026-12-15", "5-11y"), ("2026-12-22", "11-39y")]
# Sep 2026 scheduled redemption per MOF newsletter vs. sum of auction offering amounts in workbook (calibration)
SEP_ACTUAL = {"2Y": 2910.7, "5Y": 8260.8, "10Y": 8846.2, "20Y": 3233.6}
IL_BUYBACK = [("2026-04-08", 15.2), ("2026-06-11", 15.0), ("2026-07-08", 15.0)]


def main():
    hist, fc, live = m.main()
    hist = hist + []
    tot = collections.defaultdict(float)
    for r in m.load_history():
        tot[(r["tenor"], r["maturity"])] += r["offering_jpy_bn"]
    calib = {t: SEP_ACTUAL[t] / tot[(t, date(2026, 9, 1 if t == "2Y" else 20))] for t in SEP_ACTUAL}

    red = []
    for (t, mat), v in sorted(tot.items(), key=lambda kv: kv[0][1]):
        if t in calib and date(2026, 10, 1) <= mat <= date(2026, 12, 31):
            red.append(dict(tenor=t, maturity=str(mat), workbook_offered_JPYbn=v, calibration=round(calib[t], 3), est_redemption_JPYbn=round(v * calib[t], 1)))
    red = pd.DataFrame(red)

    fcd = pd.DataFrame(fc)
    fcd["month"] = fcd.auction.astype(str).str[:7]
    gross = fcd.groupby("month").offering_jpy_bn.sum()
    lea = pd.DataFrame([dict(date=d, zone=z, accepted_JPYbn=ZONE_SIZE[z], basis="scheduled; size = typical for zone (assumed)") for d, z in LEA_SCHED])
    lea_a = pd.DataFrame([dict(date=d, zone=z, accepted_JPYbn=a, basis="actual (MOF)") for d, z, a in LEA_ACTUAL])
    lea_all = pd.concat([lea_a, lea])
    lea_all["month"] = lea_all.date.str[:7]
    red["month"] = red.maturity.str[:7]

    months = ["2026-10", "2026-11", "2026-12"]
    net = pd.DataFrame(dict(
        gross_core_auctions=[gross.get(x, 0) for x in months],
        liquidity_enhancement=[lea[lea.date.str[:7] == x].accepted_JPYbn.sum() for x in months],
        est_redemptions_2Y_5Y_10Y_20Y=[red[red.month == x].est_redemption_JPYbn.sum() for x in months],
    ), index=months)
    net["gross_total"] = net.gross_core_auctions + net.liquidity_enhancement
    net["net_issuance_est"] = net.gross_total - net.est_redemptions_2Y_5Y_10Y_20Y
    net.loc["Q4 total"] = net.sum()
    net = net.round(1).reset_index().rename(columns={"index": "month"})

    piv = fcd.pivot_table(index="tenor", columns="month", values="offering_jpy_bn", aggfunc="sum", margins=True, margins_name="Total").fillna(0).reset_index()
    ilb = pd.DataFrame(IL_BUYBACK, columns=["date", "accepted_JPYbn"])
    ilb["note"] = "10Y inflation-indexed buy-back, MOF newsletter"
    meth = pd.DataFrame({"Method / caveats": [
        "Sources: MOF JGB auction historical workbook (by issue number), MOF Sep 2026 auction result pages, MOF JGB Monthly Newsletter (Sep 2026), MOF Oct-Dec auction calendar.",
        "MOF does not publish ISINs in these files; issue number + tenor identifies a line (one ISIN per issue number).",
        "Core gross = 2Y/5Y/10Y/20Y/30Y/40Y auctions. Dates per MOF calendar; sizes per MOF announcement (10Y Oct 6, 30Y Oct 8, 2Y Sep 30, 40Y Sep 29), otherwise latest size.",
        "New lines: 10Y/20Y/30Y/5Y new line/maturity in Jan/Apr/Jul/Oct then reopened; 2Y new monthly; 40Y reopens #19. Issue numbers/coupons for new lines are projections.",
        "Liquidity Enhancement Auctions (LEAs) re-open off-the-run issues by remaining-maturity zone. Oct-Dec dates are from MOF's calendar; sizes assume the typical accepted size for each zone.",
        "Buy-backs: the only buy-back series MOF reports in its newsletter is the 10Y inflation-indexed (about JPY15bn per operation) - immaterial. Sep/Oct results not in public sources yet.",
        "Redemptions: estimated from workbook lines maturing Oct-Dec 2026, scaled by Sep 2026 calibration (MOF actual Sep redemption / workbook offered). Calibration ratios are 1.10-1.35x; the gap likely reflects BOJ refunding/other add-ons not in the offering amount (not verified).",
        "Net issuance estimate covers 2Y/5Y/10Y/20Y/30Y/40Y + LEAs only. Excludes T-bills, retail JGBs, GX, inflation-linked, 15Y floating, FILP, BOJ direct underwriting.",
        "Lines sheet: 'offered to date' = cumulative auction offering amounts; it understates MOF outstanding (see calibration) and ignores buy-backs/LEAs.",
        "Not modelled: any MOF change to Q4 auction sizes, supplementary budget issuance, exchange/switch operations."]})
    sheets = {
        "Summary Q4 (JPYbn)": net, "Gross core by tenor": piv, "Forecast auctions": fcd.drop(columns="month"),
        "LEAs": lea_all.drop(columns="month"), "Redemptions est": red.drop(columns="month"), "IL buy-backs": ilb,
        "Lines (live)": pd.DataFrame(live), "Method": meth}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        for n, d in sheets.items():
            d.to_excel(w, sheet_name=n[:31], index=False)
        for ws in w.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(80, max(12, max(len(str(c.value or "")) for c in col) + 2))
    print(OUT)
    print(net.to_string()); print(red.to_string()); print(calib)

if __name__ == "__main__":
    main()
