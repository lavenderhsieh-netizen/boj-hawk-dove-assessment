"""
Line-level (by issue number) JGB issuance history + rule-based forecast of future auctions.

Sources (all MOF, public):
  - mof_source/jgb_historical_data.xls       per-auction history by issue number (回号), lags ~1 month
  - Auction Calendar pages (.../calendar/YYMMe.htm) -> Sep results (gap-fill) and scheduled Oct-Dec dates
  - Announcement pages (.../calendar/announcement/auctYYYYMMDDe.htm) -> known offering amounts

MOF does not publish ISINs in these sources; the issue number (回号) + tenor identifies the line
(each issue number maps to one ISIN). Outstanding per line = cumulative auction offering amounts
(excludes buy-backs, Liquidity Enhancement Auctions, BOJ direct underwriting and Non-price Auction II
top-ups, so it is a *gross offered* figure, not MOF's official outstanding).

Forecast rules (derived from the last ~15 months of issuance):
  10Y/20Y/30Y: new line in first auction of Jan/Apr/Jul/Oct (maturity 20th of the 9th month ahead),
               reopened the next two months.
  5Y:          new maturity date each Jan/Apr/Jul/Oct, reopened afterwards (issue no. may step if coupon resets).
  2Y:          a new line every month, maturing the 1st of the month 25 months after the auction month.
  40Y:         reopening of the current line until MOF opens a new one (not forecastable).
  Size:        latest announced amount if the announcement exists, else the latest auction size per tenor.
"""
import html
import json
import os
import re
import sys
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_XLS = os.path.join(HERE, "mof_source", "jgb_historical_data.xls")
OUT_JSON = os.path.join(HERE, "mof_issuance_lines.json")
BASE = "https://www.mof.go.jp/english/policy/jgbs/auction/calendar"
UA = {"User-Agent": "Mozilla/5.0"}

SHEETS = {"2Y": "2年債", "5Y": "5年債", "10Y": "10年債", "20Y": "20年債", "30Y": "30年債", "40Y": "40年債"}
YEARS = {"2Y": 2, "5Y": 5, "10Y": 10, "20Y": 20, "30Y": 30, "40Y": 40}
FORECAST_MONTHS = [(2026, 10), (2026, 11), (2026, 12)]


def get(url):
    r = requests.get(url, headers=UA, timeout=30)
    return r.text if r.status_code == 200 else ""


def text_of(raw):
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", "", raw, flags=re.S)
    tx = html.unescape(re.sub(r"<[^>]+>", "|", raw))
    return re.sub(r"\|\s*(\|\s*)+", "|", tx)


def load_history():
    x = pd.ExcelFile(SRC_XLS)
    rows = []
    for tenor, sheet in SHEETS.items():
        df = pd.read_excel(x, sheet, header=None).iloc[5:, :6]
        df.columns = ["no", "auc", "iss", "mat", "cpn", "amt"]
        df = df[pd.to_datetime(df.auc, errors="coerce").notna()]
        for _, r in df.iterrows():
            rows.append(dict(tenor=tenor, issue_no=int(r.no), auction=pd.to_datetime(r.auc).date(),
                             issue_date=pd.to_datetime(r.iss).date(), maturity=pd.to_datetime(r.mat).date(),
                             coupon=float(r.cpn), offering_jpy_bn=float(r.amt) / 10, source="MOF workbook"))
    return rows


def calendar_links(yymm):
    page = get(f"{BASE}/{yymm}e.htm")
    return sorted(set(re.findall(r'href="(https://www\.mof\.go\.jp/english/policy/jgbs/auction/calendar/(?:announcement/auct\d{8}e[a-z]?|eresul/eresul\d{8}[a-z]?)\.htm)"', page)))


def fill_gap(hist):
    """Sep (and any post-workbook) regular auctions from MOF result pages."""
    last = {}
    for r in hist:
        last[r["tenor"]] = max(last.get(r["tenor"], date.min), r["auction"])
    have = {(r["tenor"], r["auction"]) for r in hist}
    ann_amt = {}
    for yymm in ("2608", "2609", "2610"):
        for u in calendar_links(yymm):
            if "/announcement/" in u:
                tx = text_of(get(u))
                m = re.search(r"Announcement of (\d+)-Year JGBs to Be Issued", tx, re.I)
                a = re.search(r"Offering Amount:?\|About ([\d,]+) billion yen", tx)
                d = re.search(r"Auction Date:?\|([A-Za-z]+ \d+, \d{4})", tx)
                if m and a and d:
                    ann_amt[(int(m.group(1)), datetime.strptime(d.group(1), "%B %d, %Y").date())] = float(a.group(1).replace(",", ""))
    added = []
    for u in calendar_links("2609"):
        if "/eresul/" not in u or u.endswith("a.htm"):
            continue
        tx = text_of(get(u))
        m = re.search(r"Auction Result of (\d+)-Year JGBs", tx)
        if not m:
            continue
        yrs = int(m.group(1))
        tenor = f"{yrs}Y"
        if tenor not in SHEETS:
            continue
        f = re.search(rf"{yrs}-Year\|(\d+)\|(\d+/\d+/\d{{4}})\|(\d+/\d+/\d{{4}})\|(\d+/\d+/\d{{4}})\|([\d.]+)%", tx)
        if not f:
            continue
        p = lambda s: datetime.strptime(s, "%m/%d/%Y").date()
        auc = p(f.group(2))
        if (tenor, auc) in have:
            continue
        amt = ann_amt.get((yrs, auc))
        rec = dict(tenor=tenor, issue_no=int(f.group(1)), auction=auc, issue_date=p(f.group(3)), maturity=p(f.group(4)),
                   coupon=float(f.group(5)), offering_jpy_bn=amt, source="MOF result page (not yet in workbook)")
        added.append(rec)
    return added


def add_months(y, m, k):
    t = y * 12 + (m - 1) + k
    return t // 12, t % 12 + 1


def calendar_dates():
    out = []
    for yy, mm in FORECAST_MONTHS:
        tx = text_of(get(f"{BASE}/{str(yy)[2:]}{mm:02d}e.htm"))
        for m in re.finditer(r"([A-Z][a-z]{2})\. (\d+), (\d{4})\|(\d+)-year\|", tx):
            out.append((int(m.group(4)), datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").date()))
    return out


def announced():
    amts = {}
    for yymm in ("2610", "2611", "2612"):
        for u in calendar_links(yymm):
            if "/announcement/" in u:
                tx = text_of(get(u))
                m = re.search(r"Announcement of (\d+)-Year JGBs to Be Issued", tx, re.I)
                a = re.search(r"Offering Amount:?\|About ([\d,]+) billion yen", tx)
                d = re.search(r"Auction Date:?\|([A-Za-z]+ \d+, \d{4})", tx)
                mt = re.search(r"Maturity Date:?\|([A-Za-z]+ \d+, \d{4})", tx)
                if m and a and d:
                    amts[(int(m.group(1)), datetime.strptime(d.group(1), "%B %d, %Y").date())] = (
                        float(a.group(1).replace(",", "")),
                        datetime.strptime(mt.group(1), "%B %d, %Y").date() if mt else None)
    return amts


def forecast(hist):
    cal = calendar_dates()
    ann = announced()
    by_t = {t: sorted([r for r in hist if r["tenor"] == t], key=lambda r: r["auction"]) for t in SHEETS}
    fc = []
    state = {}
    for t, rows in by_t.items():
        last = rows[-1]
        state[t] = dict(no=last["issue_no"], mat=last["maturity"], cpn=last["coupon"], size=last["offering_jpy_bn"] or rows[-2]["offering_jpy_bn"])
    for yrs, d in sorted(cal, key=lambda x: x[1]):
        t = f"{yrs}Y"
        if t not in SHEETS:
            continue
        s = state[t]
        a = ann.get((yrs, d))
        size, size_basis = (a[0], "MOF announcement") if a else (s["size"], "latest auction size (assumed)")
        new_quarter = d.month in (1, 4, 7, 10)
        note = ""
        if t in ("10Y", "20Y", "30Y"):
            if new_quarter:
                y2, m2 = add_months(d.year + YEARS[t], d.month, -1)
                mat = date(y2, m2, 20)
                s["no"] += 1
                note = "New line (issue no. forecast; coupon TBD)"
            else:
                mat = s["mat"]
                note = "Reopening"
        elif t == "5Y":
            if new_quarter:
                y2, m2 = add_months(d.year + 5, d.month, -1)
                mat = date(y2, m2, 20)
                s["no"] += 1
                note = "New maturity (issue no. may step again if coupon resets)"
            else:
                mat = s["mat"]
                note = "Reopening"
        elif t == "2Y":
            y2, m2 = add_months(d.year, d.month, 25)
            mat = date(y2, m2, 1)
            s["no"] += 1
            note = "New monthly line"
        else:
            mat = s["mat"]
            note = "Reopening (MOF may open a new 40Y line; not forecastable)"
        if a and a[1] and a[1] != mat:
            mat = a[1]
            note += " [maturity per MOF announcement]"
        s["mat"], s["size"] = mat, size
        fc.append(dict(tenor=t, issue_no=s["no"], auction=d, maturity=mat, offering_jpy_bn=size,
                       size_basis=size_basis, note=note))
    return fc


def main():
    hist = load_history()
    added = fill_gap(hist)
    hist_all = hist + added
    fc = forecast(hist_all)

    lines = {}
    for r in hist_all:
        k = (r["tenor"], r["issue_no"])
        L = lines.setdefault(k, dict(tenor=r["tenor"], issue_no=r["issue_no"], maturity=r["maturity"], coupon=r["coupon"],
                                     first_auction=r["auction"], last_auction=r["auction"], n_auctions=0, offered_jpy_bn=0.0, forecast_bn=0.0))
        L["n_auctions"] += 1
        L["offered_jpy_bn"] += r["offering_jpy_bn"] or 0
        L["first_auction"] = min(L["first_auction"], r["auction"])
        L["last_auction"] = max(L["last_auction"], r["auction"])
    for f in fc:
        k = (f["tenor"], f["issue_no"])
        L = lines.setdefault(k, dict(tenor=f["tenor"], issue_no=f["issue_no"], maturity=f["maturity"], coupon=None,
                                     first_auction=f["auction"], last_auction=f["auction"], n_auctions=0, offered_jpy_bn=0.0, forecast_bn=0.0))
        L["forecast_bn"] += f["offering_jpy_bn"]
        L["last_auction"] = max(L["last_auction"], f["auction"])

    today = date.today()
    live = [dict(L, outstanding_after_forecast_bn=L["offered_jpy_bn"] + L["forecast_bn"]) for L in lines.values()
            if L["maturity"] > today]
    live.sort(key=lambda L: (L["tenor"], L["issue_no"]))

    def ser(o):
        return o.isoformat() if isinstance(o, date) else o
    out = dict(meta=dict(generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
                         gap_filled=[dict(tenor=a["tenor"], issue_no=a["issue_no"], auction=ser(a["auction"])) for a in added],
                         note="Offered amounts only: excludes buy-backs, liquidity-enhancement auctions, BOJ direct underwriting, Non-price Auction II."),
               forecast=[{k: ser(v) for k, v in f.items()} for f in fc],
               lines=[{k: ser(v) for k, v in L.items()} for L in live])
    json.dump(out, open(OUT_JSON, "w"), indent=1, ensure_ascii=False)
    print("gap-filled:", [(a["tenor"], a["issue_no"], str(a["auction"]), a["offering_jpy_bn"]) for a in added])
    print("forecast auctions:", len(fc))
    for f in fc:
        print(f["tenor"], f["issue_no"], f["auction"], f["maturity"], f["offering_jpy_bn"], f["size_basis"], "|", f["note"])
    return hist_all, fc, live


if __name__ == "__main__":
    main()
