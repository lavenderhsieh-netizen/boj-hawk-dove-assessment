#!/usr/bin/env python3.12
"""Japan's net purchases of foreign portfolio securities, by EMERGING-MARKET country (monthly).

Source: BOJ Time-Series Data Search, DB BP01, "Portfolio Investment Assets / <instrument> /
<country> / Net" (series BPPI6D{1,2,3}N9{CC}; same MoF/BOJ balance-of-payments statistics, 45
partner economies, all securities -- NOT sovereign-only). Units: 100 million yen -> output ¥bn.
+ = Japan net buying. Classified by issuer country (funds domiciled in Cayman/Luxembourg etc. are
not counted under the underlying country). No API key needed.

Run: python3.12 fetch_boj_em_flows.py   ->  boj_em_flows.json
"""
import json, os, urllib.request, urllib.parse, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0"}
START = "202101"
COUNTRIES = [  # (BOJ code, key, label, region)
    ("BR", "brazil", "Brazil", "Latin America"),
    ("MX", "mexico", "Mexico", "Latin America"),
    ("IN", "india", "India", "Emerging Asia"),
    ("CN", "china", "China", "Emerging Asia"),
    ("ID", "indonesia", "Indonesia", "Emerging Asia"),
    ("MY", "malaysia", "Malaysia", "Emerging Asia"),
    ("TH", "thailand", "Thailand", "Emerging Asia"),
    ("PH", "philippines", "Philippines", "Emerging Asia"),
    ("VN", "vietnam", "Vietnam", "Emerging Asia"),
    ("ZA", "southafrica", "South Africa", "CEEMEA"),
    ("SA", "saudi", "Saudi Arabia", "CEEMEA"),
    ("AE", "uae", "UAE", "CEEMEA"),
]
INSTR = [("1", "total", "All securities"), ("2", "equity", "Equity & fund shares"), ("3", "ltdebt", "Long-term bonds")]

def pull(code):
    q = urllib.parse.urlencode({"format": "json", "lang": "en", "db": "BP01", "code": code, "startDate": START})
    r = json.load(urllib.request.urlopen(urllib.request.Request(
        "https://www.stat-search.boj.or.jp/api/v1/getDataCode?" + q, headers=UA), timeout=60))
    rs = r.get("RESULTSET")
    if not rs: raise RuntimeError(f"{code}: {r.get('MESSAGE')}")
    v = rs[0]["VALUES"]
    return {str(d): x for d, x in zip(v["SURVEY_DATES"], v["VALUES"])}

def main():
    raw = {}
    for ik, _, _ in INSTR:
        for cc, key, _, _ in COUNTRIES:
            raw[(ik, key)] = pull(f"BPPI6D{ik}N9{cc}")
    months = sorted(raw[("1", "brazil")])
    out = {"meta": {"as_of": f"{months[-1][:4]}-{months[-1][4:]}", "generated_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
                    "unit": "¥bn, net purchase (+ = Japan buying)", "source": "BOJ Time-Series Data Search, DB BP01 (Portfolio Investment Assets, Country Breakdown, Net)",
                    "source_url": "https://www.stat-search.boj.or.jp/index_en.html"},
           "months": [f"{m[:4]}-{m[4:]}" for m in months],
           "order": [k for _, k, _, _ in COUNTRIES],
           "labels": {k: l for _, k, l, _ in COUNTRIES}, "regions": {k: r for _, k, _, r in COUNTRIES},
           "instruments": {ik_name: lab for _, ik_name, lab in INSTR}, "series": {}}
    for ik, name, _ in INSTR:
        out["series"][name] = {key: [None if raw[(ik, key)].get(m) is None else round(raw[(ik, key)][m] / 10, 1) for m in months]
                               for _, key, _, _ in COUNTRIES}
    json.dump(out, open(os.path.join(HERE, "boj_em_flows.json"), "w"), ensure_ascii=False)
    print("wrote boj_em_flows.json, as_of", out["meta"]["as_of"], "months", len(months))

if __name__ == "__main__":
    main()
