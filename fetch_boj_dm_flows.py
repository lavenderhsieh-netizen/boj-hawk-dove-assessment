#!/usr/bin/env python3.12
"""Japan's net purchases of foreign portfolio securities, by DEVELOPED-MARKET country (monthly).
Same BOJ BP01 source/method as fetch_boj_em_flows.py (reuses its pull/FX helpers).
Run: python3.12 fetch_boj_dm_flows.py   ->  boj_dm_flows.json
"""
import json, os, datetime
import fetch_boj_em_flows as em

HERE = os.path.dirname(os.path.abspath(__file__))
COUNTRIES = [
    ("US", "us", "United States", "North America"),
    ("CA", "canada", "Canada", "North America"),
    ("GB", "uk", "United Kingdom", "Europe"),
    ("DE", "germany", "Germany", "Europe"),
    ("FR", "france", "France", "Europe"),
    ("IT", "italy", "Italy", "Europe"),
    ("ES", "spain", "Spain", "Europe"),
    ("NL", "netherlands", "Netherlands", "Europe"),
    ("BE", "belgium", "Belgium", "Europe"),
    ("AT", "austria", "Austria", "Europe"),
    ("FI", "finland", "Finland", "Europe"),
    ("PT", "portugal", "Portugal", "Europe"),
    ("IE", "ireland", "Ireland", "Europe"),
    ("CH", "switzerland", "Switzerland", "Europe"),
    ("SE", "sweden", "Sweden", "Europe"),
    ("DK", "denmark", "Denmark", "Europe"),
    ("NO", "norway", "Norway", "Europe"),
    ("AU", "australia", "Australia", "Asia-Pacific DM"),
    ("NZ", "newzealand", "New Zealand", "Asia-Pacific DM"),
    ("HK", "hongkong", "Hong Kong", "Asia-Pacific DM"),
    ("SG", "singapore", "Singapore", "Asia-Pacific DM"),
]

def main():
    raw = {}
    for ik, _, _ in em.INSTR:
        for cc, key, _, _ in COUNTRIES:
            raw[(ik, key)] = em.pull(f"BPPI6D{ik}N9{cc}")
    months = sorted(raw[("1", "us")])
    out = {"meta": {"as_of": f"{months[-1][:4]}-{months[-1][4:]}", "generated_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
                    "unit": "¥bn, net purchase (+ = Japan buying)", "source": "BOJ Time-Series Data Search, DB BP01 (Portfolio Investment Assets, Country Breakdown, Net)",
                    "source_url": "https://www.stat-search.boj.or.jp/index_en.html"},
           "months": [f"{m[:4]}-{m[4:]}" for m in months],
           "order": [k for _, k, _, _ in COUNTRIES],
           "labels": {k: l for _, k, l, _ in COUNTRIES}, "regions": {k: r for _, k, _, r in COUNTRIES},
           "instruments": {n: lab for _, n, lab in em.INSTR}, "series": {}}
    for ik, name, _ in em.INSTR:
        out["series"][name] = {key: [None if raw[(ik, key)].get(m) is None else round(raw[(ik, key)][m] / 10, 1) for m in months]
                               for _, key, _, _ in COUNTRIES}
    fx = em.usdjpy_monthly()
    def rate(tag):
        if tag in fx: return fx[tag]
        earlier = [v for k, v in sorted(fx.items()) if k <= tag]
        return earlier[-1] if earlier else (sorted(fx.values())[len(fx)//2] if fx else None)
    rates = [rate(m) for m in out["months"]]
    out["usdjpy"] = rates
    out["unit_usd"] = "$mn, net purchase (+ = Japan buying); ¥ converted at each month's USD/JPY (Yahoo monthly close)"
    out["series_usd"] = {nm: {k: [None if (v is None or r is None) else round(v * 1000.0 / r, 1) for v, r in zip(arr, rates)]
                              for k, arr in sers.items()} for nm, sers in out["series"].items()}
    json.dump(out, open(os.path.join(HERE, "boj_dm_flows.json"), "w"), ensure_ascii=False)
    print("wrote boj_dm_flows.json, as_of", out["meta"]["as_of"], "months", len(months))

if __name__ == "__main__":
    main()
