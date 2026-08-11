#!/usr/bin/env python3.12
"""Fetch MoF Balance-of-Payments monthly release — securities flows by COUNTRY.

Source: MoF "Portfolio Investment Assets/Liabilities, Country Breakdown" in the
monthly BOP preliminary PDF (bppiYYYYMM.pdf). Two tables we parse:
  - LIABILITIES, Country Breakdown           -> foreigners' net buying of JAPANESE
                                                long-term bonds, by country (#3 inbound)
  - ASSETS, Country Breakdown of Sovereign Bonds -> Japan's net buying of FOREIGN
                                                sovereign bonds, by country (#2 outbound)

Each PDF is one month, so we loop months and accumulate a time series. Values are
億円; output ¥bn (÷100). + = net purchase. Country tables use full-width minus '－'
and '―' for missing.

Run: python3.12 fetch_mof_bop.py   (needs pdftotext / poppler-utils)
"""
import urllib.request, subprocess, os, re, json, datetime, tempfile

BASE = "https://www.mof.go.jp/policy/international_policy/reference/balance_of_payments/preliminary/bppi{ym}.pdf"
UA = {"User-Agent": "Mozilla/5.0"}
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "bop_source"); os.makedirs(SRC, exist_ok=True)
START = (2021, 4)                       # first month to try

# key countries to track (EN name substring -> output key + label); rest -> "others"
INBOUND_COUNTRIES = [
    ("P.R.China", "china",   "China"),
    ("U.S.A.",    "us",      "United States"),
    ("U.K.",      "uk",      "United Kingdom"),
    ("Germany",   "germany", "Germany"),
    ("France",    "france",  "France"),
]
OUTBOUND_COUNTRIES = [
    ("U.S.A.",       "us",          "United States"),
    ("Canada",       "canada",      "Canada"),
    ("Australia",    "australia",   "Australia"),
    ("Germany",      "germany",     "Germany"),
    ("France",       "france",      "France"),
    ("Italy",        "italy",       "Italy"),
    ("Netherlands",  "netherlands", "Netherlands"),
    ("U.K.",         "uk",          "United Kingdom"),
    ("Denmark",      "denmark",     "Denmark"),
    ("Switzerland",  "switzerland", "Switzerland"),
    ("Hong Kong",    "hongkong",    "Hong Kong"),
    ("Sweden",       "sweden",      "Sweden"),
]

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()

def usdjpy_monthly():
    """Monthly USDJPY close from Yahoo, {YYYY-MM: rate}. Empty dict on failure."""
    try:
        j = json.loads(get("https://query1.finance.yahoo.com/v8/finance/chart/JPY=X?interval=1mo&range=7y").decode())
        res = j["chart"]["result"][0]
        ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
        out = {}
        for t, c in zip(ts, cl):
            if c is None: continue
            d = datetime.datetime.fromtimestamp(t, datetime.UTC)
            out[f"{d.year}-{d.month:02d}"] = round(float(c), 3)
        return out
    except Exception as e:
        print("usdjpy fetch failed:", e); return {}

def to_text(pdf_bytes):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes); path = f.name
    try:
        out = subprocess.run(["pdftotext", "-layout", path, "-"],
                             capture_output=True, timeout=60)
        return out.stdout.decode("utf-8", "replace")
    finally:
        os.unlink(path)

def parse_row(line):
    """Return (english_name, [numbers]) for a country row. '－'→neg, '―'→None."""
    s = line.replace("－", "-").replace("―", " NA ")
    s = re.sub(r"-\s+(\d)", r"-\1", s).replace(",", "")
    toks = s.split()
    nums = []
    for t in toks:
        if t == "NA": nums.append(None)
        elif re.fullmatch(r"-?\d+", t): nums.append(int(t))
    en = " ".join(t for t in toks if re.search(r"[A-Za-z]", t)).strip()
    return en, nums

def table_block(lines, header, n=75):
    try:
        i = next(k for k, l in enumerate(lines) if header in l)
    except StopIteration:
        return []
    return lines[i:i + n]

def extract(lines, header, net_idx, countries):
    """Per-country value at column `net_idx` from a table; plus the 合計/Total row.

    Layout: English country name at the END of the numbers line (Liabilities /
    inbound table). Used for the by-country foreign demand for JGBs."""
    block = table_block(lines, header)
    out, total = {}, None
    for l in block:
        en, nums = parse_row(l)
        if len(nums) <= net_idx: continue
        if en == "Total" and total is None:
            total = nums[net_idx]
        for sub, key, _ in countries:
            if sub in en and key not in out:
                out[key] = nums[net_idx]
    return out, total

def extract_sovereign_multi(lines, countries):
    """Outbound sovereign-bond table (Assets, Country Breakdown of Sovereign Bonds).

    Different layout from the inbound table: the Japanese label + numbers sit on
    one line and the English country name is on the FOLLOWING line by itself. So
    we pair each 9-column number row with the next english-only line. The table
    has no explicit Total row, so the total is the sum of ALL rows (every country
    plus その他/Others) at each net column.

    Row layout (9 numbers): [0]=TotalAcq [1]=TotalDisp [2]=TotalNet
    [3]=LTAcq [4]=LTDisp [5]=LTNet [6]=STAcq [7]=STDisp [8]=STNet.
    Returns two (out, total) pairs: one for Sovereign Total (LT+ST) net,
    one for Sovereign Long-term-only net -- same single pass over the PDF."""
    block = table_block(lines, header="Country Breakdown of Sovereign Bonds", n=50)
    out_tot, out_lt, total_tot, total_lt, seen_any = {}, {}, 0, 0, False
    for i, l in enumerate(block):
        if "備考" in l or "(Notes)" in l or "Notes)" in l:
            break                                    # end of the sovereign table
        en, nums = parse_row(l)
        if len(nums) < 9:                            # not a data row (headers etc.)
            continue
        val_tot, val_lt = nums[2], nums[5]
        total_tot += val_tot if isinstance(val_tot, int) else 0
        total_lt += val_lt if isinstance(val_lt, int) else 0
        seen_any = True
        name = ""                                    # number-line `en` is ― placeholder
        for j in range(i + 1, min(i + 3, len(block))):   # english is on a following line
            en2, nums2 = parse_row(block[j])
            if en2 and not nums2:
                name = en2; break
        for sub, key, _ in countries:
            if sub in name and key not in out_tot:
                out_tot[key] = val_tot
                out_lt[key] = val_lt
    if not seen_any:
        return out_tot, None, out_lt, None
    return out_tot, total_tot, out_lt, total_lt

def main():
    today = datetime.date.today()
    y, m = START
    months, inbound, outbound_tot, outbound_lt = [], [], [], []
    while (y, m) <= (today.year, today.month):
        ym = f"{y}{m:02d}"; tag = f"{y}-{m:02d}"
        pdf_path = os.path.join(SRC, f"bppi{ym}.pdf")
        try:
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 50000:
                data = open(pdf_path, "rb").read()          # cached (historical files are static)
            else:
                data = get(BASE.format(ym=ym))
                if data[:4] != b"%PDF":
                    raise ValueError("not a PDF (not yet published)")
                open(pdf_path, "wb").write(data)
            lines = to_text(data).splitlines()
            # inbound: Liabilities country breakdown, LT-debt net = col index 8
            inb, inb_tot = extract(lines, "Portfolio Investment Liabilities, Country Breakdown", 8, INBOUND_COUNTRIES)
            # outbound: Assets sovereign-bond country breakdown -- both Sovereign(Total) and
            # Sovereign(Long-term-only) net, one pass (see extract_sovereign_multi's docstring)
            outb_tot_d, outb_tot_tot, outb_lt_d, outb_lt_tot = extract_sovereign_multi(lines, OUTBOUND_COUNTRIES)
            if inb_tot is None and outb_tot_tot is None:
                raise ValueError("no tables parsed")
            months.append(tag)
            inbound.append({"total": inb_tot, **inb})
            outbound_tot.append({"total": outb_tot_tot, **outb_tot_d})
            outbound_lt.append({"total": outb_lt_tot, **outb_lt_d})
            print(f"{tag}: inbound tot {inb_tot}, outbound-sov tot(LT+ST) {outb_tot_tot}, outbound-sov tot(LT-only) {outb_lt_tot}")
        except Exception as e:
            print(f"{tag}: skip ({e})")
        m += 1
        if m > 12: m = 1; y += 1

    fx = usdjpy_monthly()
    def rate(tag):
        if tag in fx: return fx[tag]
        earlier = [v for k, v in sorted(fx.items()) if k <= tag]
        return earlier[-1] if earlier else (sorted(fx.values())[len(fx)//2] if fx else None)

    def series(recs, countries, usd=False):
        keys = [c[1] for c in countries]
        out = {k: [] for k in keys + ["others", "total"]}
        for tag, r in zip(months, recs):
            tot = r.get("total")
            named = 0
            conv = (lambda v: round(v/10 * 1000.0 / rate(tag), 2)) if usd else (lambda v: round(v/10, 1))
            for k in keys:
                v = r.get(k)
                out[k].append(conv(v) if isinstance(v, int) else None)   # 億円 → ¥bn or $mn
                if isinstance(v, int): named += v
            out["total"].append(conv(tot) if isinstance(tot, int) else None)
            out["others"].append(conv(tot-named) if isinstance(tot, int) else None)
        return out

    # outbound_sov[_total]: regenerated straight from the MoF preliminary PDF (both LT-only
    # and LT+ST columns of the same "Country Breakdown of Sovereign Bonds" table, see
    # extract_sovereign_multi). This REPLACES the 2026-08-10 manual-BOJ-pull freeze (that
    # approach only ever captured one metric -- Sovereign Total -- while the dashboard's own
    # label claimed "long-term"; HanHan's 2026-08-11 Macrobond cross-check (US Jun-2026
    # -883.0bn) confirmed the frozen number was actually Total, not LT, a real label/data
    # mismatch). Cross-checked Feb-Jun 2026: the PDF's Total column matches the frozen BOJ
    # values almost exactly (e.g. Jun US -967.4bn PDF vs -967.36bn frozen), so PDF-Total is a
    # reliable stand-in for the BOJ-revised series in recent months -- the one prior outlier
    # (Jan-2026, PDF=293.2/300.4 vs Mizuho=444 vs BOJ=450.6) is a real risk of this being
    # preliminary/unrevised data, flagged in the card's own footnote rather than hidden.
    doc = {
        "meta": {"as_of": months[-1] if months else None,
                 "generated_at": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat(),
                 "unit": "JPY bn", "unit_usd": "$mn", "sign": "+ = net purchase",
                 "source": "MoF Balance of Payments monthly (bppiYYYYMM.pdf) — Portfolio Investment Assets/Liabilities, Country Breakdown",
                 "source_url": "https://www.mof.go.jp/policy/international_policy/reference/balance_of_payments/bppi.htm",
                 "outbound_sov_source": "outbound_sov = Sovereign (Long-term only) net; outbound_sov_total = Sovereign (Long-term + Short-term) net. Both parsed from MoF's own preliminary PDF, same table, auto-refreshed on every run (2026-08-11) -- see comment above main()'s doc-building step. Preliminary/unrevised basis: MoF/BOJ occasionally revise these figures later without updating the static PDF in place, so a given month can drift from continuously-revised sell-side sources (Mizuho/Nomura/SMBC) -- seen once (Jan-2026, ~30-35% gap), otherwise tracked closely in spot checks since."},
        "months": months,
        "inbound": {"order": [c[1] for c in INBOUND_COUNTRIES] + ["others"],
                    "labels": {c[1]: c[2] for c in INBOUND_COUNTRIES} | {"others": "Others"},
                    "series": series(inbound, INBOUND_COUNTRIES),
                    "series_usd": series(inbound, INBOUND_COUNTRIES, usd=True)},
        "outbound_sov": {"order": [c[1] for c in OUTBOUND_COUNTRIES] + ["others"],
                         "labels": {c[1]: c[2] for c in OUTBOUND_COUNTRIES} | {"others": "Others"},
                         "series": series(outbound_lt, OUTBOUND_COUNTRIES),
                         "series_usd": series(outbound_lt, OUTBOUND_COUNTRIES, usd=True)},
        "outbound_sov_total": {"order": [c[1] for c in OUTBOUND_COUNTRIES] + ["others"],
                         "labels": {c[1]: c[2] for c in OUTBOUND_COUNTRIES} | {"others": "Others"},
                         "series": series(outbound_tot, OUTBOUND_COUNTRIES),
                         "series_usd": series(outbound_tot, OUTBOUND_COUNTRIES, usd=True)},
    }
    for dest in (os.path.join(HERE, "mof_bop.json"),
                 os.path.join(HERE, "streamlit_app", "mof_bop.json")):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        json.dump(doc, open(dest, "w"), ensure_ascii=False, indent=1)
    print(f"months {len(months)} ({months[0] if months else '-'}..{months[-1] if months else '-'}) -> mof_bop.json (outbound_sov = LT-only, outbound_sov_total = LT+ST, both regenerated from PDF)")

if __name__ == "__main__":
    main()
