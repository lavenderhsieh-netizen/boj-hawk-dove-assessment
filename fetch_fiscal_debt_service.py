#!/usr/bin/env python3.12
"""Japan central-government debt service: interest/GDP scenarios, FY2026 debt-service split,
maturity wall. Rough bottom-up roll-forward of the marketable JGB book (NOT an MOF figure).
Inputs (./source): jgb_lines_forecast.xlsx ('Lines (live)': issue, maturity, coupon, outstanding),
jgb_coupon_distribution.xlsx (Summary: total book / T-bills). Curve from market_data.json.
Reference: MOF 後年度影響試算 (Feb 2026): interest 13.0/15.5/18.5/21.6 tn FY26-29, debt service 31.3 -> 41.3."""
import json, datetime as dt, collections, openpyxl, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
HERE = pathlib.Path(__file__).parent
MOF_INT = [13.0, 15.5, 18.5, 21.6]
DEFICIT = [29.6, 31.8, 34.0, 36.3]
MIX = {'2Y': 33.6, '5Y': 30.0, '10Y': 31.0, '20Y': 8.4, '30Y': 7.2, '40Y': 1.2}
TEN = ['1Y','2Y','3Y','4Y','5Y','6Y','7Y','8Y','9Y','10Y','15Y','20Y','25Y','30Y','40Y']

def fy(d): return d.year if d.month >= 4 else d.year - 1

def gdp_base():
    try:
        from fetch_boj_balance_sheet import gdp_nominal_quarterly
        g = gdp_nominal_quarterly(); ks = sorted(g)[-4:]
        return sum(g[k] for k in ks), ks[-1]
    except Exception as e:
        print('gdp fallback', e); return 660.0, 'fallback'

def main():
    wb = openpyxl.load_workbook(HERE/'source/jgb_lines_forecast.xlsx', data_only=True)
    L = [r for r in wb['Lines (live)'].iter_rows(min_row=2, values_only=True) if r[0] and r[9] and r[3] is not None]
    book = [(r[2], r[3], r[9]/1000.0) for r in L]
    listed = sum(b[2] for b in book)
    cd = openpyxl.load_workbook(HERE/'source/jgb_coupon_distribution.xlsx', data_only=True)['Summary']
    rows = {r[0]: r for r in cd.iter_rows(values_only=True) if r[0]}
    bills = float(rows['T-bills*'][1]); total = float(rows['All marketable'][1]); bond_total = total - bills
    scale = bond_total / listed
    md = json.load(open(HERE/'market_data.json')); Y = md['jgb']['curve']['yields']
    yy = {k: Y[TEN.index(k)] for k in MIX}
    new0 = sum(MIX[k]*yy[k] for k in MIX)/sum(MIX.values())
    gdp4, gq = gdp_base()
    gdp = [gdp4*1.03**(i+0.75) for i in range(4)]  # FY2026..29 (latest 4Q ~ mid-2026 level), 3% nominal growth as in MOF trial
    mats = [(L[i][2], L[i][3], L[i][9]/1000.0) for i in range(len(L))]   # (maturity, coupon, outstanding)
    def run(shift):
        new = new0 + shift/100.0; billy = 1.5 + shift/100.0
        newcpn = 0.0; res = []
        for i, y in enumerate(range(2026, 2030)):
            intr = newcpn/100.0; refi = 0.0
            for m, c, o in mats:
                f = fy(m); a = o*scale
                if f > y: intr += a*c/100.0
                elif f == y: intr += a*c/100.0*0.5; refi += a
            bavg = 0.9 + (billy-0.9)*min(1.0, (i+0.5))
            intr += bills*bavg/100.0
            intr += (refi + DEFICIT[i])*new/100.0*0.5
            newcpn += (refi + DEFICIT[i])*new
            res.append(round(intr, 2))
        return res
    scen = {k: run(s) for k, s in (('minus100', -100), ('curve', 0), ('plus100', 100))}
    wall = collections.defaultdict(float)
    for m, c, o in mats: wall[fy(m)] += o*scale
    fy26_bonds_h2 = wall[2026]
    out = {
      'meta': {'generated': dt.date.today().isoformat(), 'gdp_last4q_tn': round(gdp4, 1), 'gdp_last_quarter': gq,
               'book_total_tn': total, 'bills_tn': bills, 'avg_coupon_pct': 1.05, 'new_issue_yield_pct': round(new0, 2),
               'curve_date': md['jgb']['curve']['date'], 'listed_scale': round(scale, 3),
               'note': 'Rough bottom-up roll-forward of the marketable JGB book at the current curve (+/-100bp parallel shift applied at once). Not an MOF figure.'},
      'years': ['FY2026', 'FY2027', 'FY2028', 'FY2029'],
      'gdp_tn': [round(g, 1) for g in gdp],
      'interest_tn': scen,
      'interest_pct_gdp': {k: [round(v/g*100, 2) for v, g in zip(vs, gdp)] for k, vs in scen.items()},
      'mof_interest_tn': MOF_INT,
      'mof_interest_pct_gdp': [round(v/g*100, 2) for v, g in zip(MOF_INT, gdp)],
      'maturity_wall_pct_gdp': {str(y): round(wall[y]/gdp[min(3, y-2026)]*100, 2) for y in range(2027, 2036)},
      'maturity_wall_tn': {str(y): round(wall[y], 1) for y in range(2026, 2036)},
    }
    out['fy2026_split_pct_gdp'] = {'interest': round(scen['curve'][0]/gdp[0]*100, 2)}
    json.dump(out, open(HERE/'fiscal_debt_service.json', 'w'), indent=1)
    print(json.dumps(out, indent=1)[:2500])
main()
