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

def extract_sovereign(lines, net_idx, countries):
    """Outbound sovereign-bond table (Assets, Country Breakdown of Sovereign Bonds).

    Different layout from the inbound table: the Japanese label + numbers sit on
    one line and the English country name is on the FOLLOWING line by itself. So
    we pair each 9-column number row with the next english-only line. The table
    has no explicit Total row, so the total is the sum of ALL rows (every country
    plus その他/Others) at the long-term-net column."""
    block = table_block(lines, header="Country Breakdown of Sovereign Bonds", n=50)
    out, total, seen_any = {}, 0, False
    for i, l in enumerate(block):
        if "備考" in l or "(Notes)" in l or "Notes)" in l:
            break                                    # end of the sovereign table
        en, nums = parse_row(l)
        if len(nums) < 9:                            # not a data row (headers etc.)
            continue
        val = nums[net_idx]
        total += val if isinstance(val, int) else 0
        seen_any = True
        name = ""                                    # number-line `en` is ― placeholder
        for j in range(i + 1, min(i + 3, len(block))):   # english is on a following line
            en2, nums2 = parse_row(block[j])
            if en2 and not nums2:
                name = en2; break
        for sub, key, _ in countries:
            if sub in name and key not in out:
                out[key] = val
    return out, (total if seen_any else None)

def main():
    today = datetime.date.today()
    y, m = START
    months, inbound, outbound = [], [], []
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
            # outbound: Assets sovereign-bond country breakdown, Sovereign LT net = col index 5
            outb, outb_tot = extract_sovereign(lines, 5, OUTBOUND_COUNTRIES)
            if inb_tot is None and outb_tot is None:
                raise ValueError("no tables parsed")
            months.append(tag)
            inbound.append({"total": inb_tot, **inb})
            outbound.append({"total": outb_tot, **outb})
            print(f"{tag}: inbound tot {inb_tot}, outbound-sov tot {outb_tot}")
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

    # outbound_sov: DO NOT regenerate from the MoF preliminary PDF anymore (2026-08-10).
    # That PDF's by-country sovereign-bond table is a first-release snapshot that MoF/BOJ
    # revise later without ever updating the static PDF in place -- it drifted materially
    # from what Nomura/Mizuho/SMBC actually show (e.g. US Jan-2026: PDF=293.2 vs Mizuho=444,
    # a 34% gap). The authoritative, continuously-revised source is BOJ's Time-Series Data
    # Search site (stat-search.boj.or.jp, series BP01'BPPI6D1N{country}) -- confirmed via
    # MoF's own bppi.htm page, which explicitly says to use BOJ's site for this table. That
    # site is a legacy CGI system behind bot protection that blocks headless curl/requests,
    # so it can't be refreshed by this unattended script; it was pulled via interactive
    # browser automation on 2026-08-10 and gave US Jan-2026 = 450.6 (1.5% off Mizuho's 444,
    # vs the PDF's 34% miss). We keep whatever outbound_sov block is already in mof_bop.json
    # (from that manual pull) untouched here, rather than clobbering it with the worse PDF
    # data on every automated run. If it needs extending to newer months, redo the BOJ
    # browser pull (see boj-hawk-dove-assessment/AGENTS.md) -- don't just re-enable this
    # PDF-based path.
    existing_outbound_sov = None
    for src in (os.path.join(HERE, "mof_bop.json"),
                os.path.join(HERE, "streamlit_app", "mof_bop.json")):
        if os.path.exists(src):
            try:
                existing_outbound_sov = json.load(open(src))["outbound_sov"]
                break
            except Exception:
                pass

    doc = {
        "meta": {"as_of": months[-1] if months else None,
                 "generated_at": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat(),
                 "unit": "JPY bn", "unit_usd": "$mn", "sign": "+ = net purchase",
                 "source": "MoF Balance of Payments monthly (bppiYYYYMM.pdf) — Portfolio Investment Assets/Liabilities, Country Breakdown",
                 "source_url": "https://www.mof.go.jp/policy/international_policy/reference/balance_of_payments/bppi.htm",
                 "outbound_sov_source": "outbound_sov is frozen from a manual BOJ Time-Series Data Search pull (2026-08-10) — see comment above main()'s doc-building step; this script no longer regenerates it from the PDF."},
        "months": months,
        "inbound": {"order": [c[1] for c in INBOUND_COUNTRIES] + ["others"],
                    "labels": {c[1]: c[2] for c in INBOUND_COUNTRIES} | {"others": "Others"},
                    "series": series(inbound, INBOUND_COUNTRIES),
                    "series_usd": series(inbound, INBOUND_COUNTRIES, usd=True)},
        "outbound_sov": existing_outbound_sov if existing_outbound_sov is not None else {
                         "order": [c[1] for c in OUTBOUND_COUNTRIES] + ["others"],
                         "labels": {c[1]: c[2] for c in OUTBOUND_COUNTRIES} | {"others": "Others"},
                         "series": series(outbound, OUTBOUND_COUNTRIES),
                         "series_usd": series(outbound, OUTBOUND_COUNTRIES, usd=True)},
    }
    for dest in (os.path.join(HERE, "mof_bop.json"),
                 os.path.join(HERE, "streamlit_app", "mof_bop.json")):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        json.dump(doc, open(dest, "w"), ensure_ascii=False, indent=1)
    print(f"months {len(months)} ({months[0] if months else '-'}..{months[-1] if months else '-'}) -> mof_bop.json (outbound_sov preserved from manual BOJ pull, not regenerated)")

if __name__ == "__main__":
    main()
