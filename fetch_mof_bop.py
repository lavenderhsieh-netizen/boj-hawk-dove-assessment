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
    ("U.S.A.",     "us",        "United States"),
    ("Germany",    "germany",   "Germany"),
    ("France",     "france",    "France"),
    ("Australia",  "australia", "Australia"),
    ("U.K.",       "uk",        "United Kingdom"),
]

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()

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
    """Per-country value at column `net_idx` from a table; plus the 合計/Total row."""
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
            outb, outb_tot = extract(lines, "Portfolio Investment Assets, Country Breakdown of Sovereign Bonds", 5, OUTBOUND_COUNTRIES)
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

    def series(recs, countries):
        keys = [c[1] for c in countries]
        out = {k: [] for k in keys + ["others", "total"]}
        for r in recs:
            tot = r.get("total")
            named = 0
            for k in keys:
                v = r.get(k)
                out[k].append(round(v/10, 1) if isinstance(v, int) else None)   # 億円 → ¥bn
                if isinstance(v, int): named += v
            out["total"].append(round(tot/10, 1) if isinstance(tot, int) else None)
            out["others"].append(round((tot-named)/10, 1) if isinstance(tot, int) else None)
        return out

    doc = {
        "meta": {"as_of": months[-1] if months else None,
                 "generated_at": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat(),
                 "unit": "JPY bn", "sign": "+ = net purchase",
                 "source": "MoF Balance of Payments monthly (bppiYYYYMM.pdf) — Portfolio Investment Assets/Liabilities, Country Breakdown",
                 "source_url": "https://www.mof.go.jp/policy/international_policy/reference/balance_of_payments/bppi.htm"},
        "months": months,
        "inbound": {"order": [c[1] for c in INBOUND_COUNTRIES] + ["others"],
                    "labels": {c[1]: c[2] for c in INBOUND_COUNTRIES} | {"others": "Others"},
                    "series": series(inbound, INBOUND_COUNTRIES)},
        "outbound_sov": {"order": [c[1] for c in OUTBOUND_COUNTRIES] + ["others"],
                         "labels": {c[1]: c[2] for c in OUTBOUND_COUNTRIES} | {"others": "Others"},
                         "series": series(outbound, OUTBOUND_COUNTRIES)},
    }
    for dest in (os.path.join(HERE, "mof_bop.json"),
                 os.path.join(HERE, "streamlit_app", "mof_bop.json")):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        json.dump(doc, open(dest, "w"), ensure_ascii=False, indent=1)
    print(f"months {len(months)} ({months[0] if months else '-'}..{months[-1] if months else '-'}) -> mof_bop.json")

if __name__ == "__main__":
    main()
