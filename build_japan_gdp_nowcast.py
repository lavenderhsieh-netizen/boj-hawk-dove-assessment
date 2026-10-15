#!/usr/bin/env python3.12
"""Japan real-GDP nowcast (QoQ SA) -> japan_gdp_nowcast.json  (Nowcast tab).

Free official data only (no Wind): e-Stat Statistics Dashboard API (no key),
which republishes METI / Cabinet Office / MIC series.
  Target : real GDP, change from previous quarter, SA (Cabinet Office QE, latest vintage)
  Inputs : IIP (METI), tertiary-industry activity (METI), consumption trend index
           (real, Cabinet Office/ESRI), machinery orders ex-volatile (Cabinet Office),
           total hours worked (MHLW), all SA monthly.
Method  : bridge regressions of GDP QoQ on QoQ log-change of the quarterly average of each
          monthly indicator; months not yet published are projected with an AR(1) on monthly
          log growth. Models combined with inverse-MSE weights from a recursive
          out-of-sample test. 2020 excluded from fitting. Re-run when new data lands.
Usage   : python3.12 build_japan_gdp_nowcast.py
"""
import json, os, datetime
import numpy as np, requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "japan_gdp_nowcast.json")
API = "https://dashboard.e-stat.go.jp/api/1.0/Json/getData"
CODES = {
    "iip":   ("0502070301000090010", "2", "Industrial production"),
    "tert":  ("0603100300000090010", "2", "Tertiary industry activity"),
    "mach":  ("0701030000000010010", "2", "Machinery orders (ex-volatile)"),
    "hours": ("0302040201000090010", "2", "Total hours worked"),
    "cti":   ("0704050300000290000", "1", "Consumption trend index (real)"),
}
GDP_CODE = "0705020501000040000"
TARGET_Q = "2026Q3"
EXCLUDE = {"2020Q1", "2020Q2", "2020Q3", "2020Q4"}
FIT_FROM = "2010Q1"
OOS_FROM = "2016Q1"

MODELS = [
    ("J1 Industrial production", ["iip"]),
    ("J2 IP + Services", ["iip", "tert"]),
    ("J3 IP + Services + Consumption", ["iip", "tert", "cti"]),
    ("J4 IP + Services + Machinery orders", ["iip", "tert", "mach"]),
    ("J5 Services + Consumption + Hours", ["tert", "cti", "hours"]),
]


def pull(code):
    r = requests.get(API, params=dict(Lang="EN", IndicatorCode=code), timeout=90).json()
    return [x["VALUE"] for x in r["GET_STATS"]["STATISTICAL_DATA"]["DATA_INF"]["DATA_OBJ"]]


def monthly(code, seas):
    out = {}
    for v in pull(code):
        if v["@cycle"] == "1" and v["@isSeasonal"] == seas and v["$"] not in ("", "…", "-"):
            t = v["@time"]
            out[t[:4] + "-" + t[4:6]] = float(v["$"])
    return dict(sorted(out.items()))


def gdp_qoq():
    out = {}
    for v in pull(GDP_CODE):
        if v["@cycle"] == "2" and v["@isSeasonal"] == "2" and v["$"] not in ("", "…"):
            t = v["@time"]
            out[t[:4] + "Q" + t[4]] = float(v["$"])
    return dict(sorted(out.items()))


def qkey(ym):
    y, m = int(ym[:4]), int(ym[5:])
    return f"{y}Q{(m - 1) // 3 + 1}"


def prev_q(q):
    y, n = int(q[:4]), int(q[5])
    return f"{y - 1}Q4" if n == 1 else f"{y}Q{n - 1}"


def months_of(q):
    y, n = int(q[:4]), int(q[5])
    return [f"{y}-{m:02d}" for m in range(3 * n - 2, 3 * n + 1)]


def ar1_project(series, upto):
    """Extend a monthly level series to month `upto` using AR(1) on log growth (fit last ~10y)."""
    ks = sorted(series)
    lv = np.array([series[k] for k in ks])
    g = np.diff(np.log(lv))[-120:]
    x, y = g[:-1], g[1:]
    b = np.polyfit(x, y, 1) if len(x) > 10 else (0.0, 0.0)
    out = dict(series)
    last_g = g[-1]
    cur = ks[-1]
    while cur < upto:
        y_, m_ = int(cur[:4]), int(cur[5:])
        m_ += 1
        if m_ > 12:
            y_, m_ = y_ + 1, 1
        cur = f"{y_}-{m_:02d}"
        last_g = b[0] * last_g + b[1]
        out[cur] = out[sorted(out)[-1]] * float(np.exp(last_g))
    return out


def q_avg(series, q, need=3):
    ms = months_of(q)
    vals = [series[m] for m in ms if m in series]
    return float(np.mean(vals)) if len(vals) == need else None


def feature(series, q):
    a, b = q_avg(series, q), q_avg(series, prev_q(q))
    return None if a is None or b is None else float(np.log(a / b))


def ols(X, y):
    Xc = np.c_[np.ones(len(X)), X]
    beta = np.linalg.lstsq(Xc, y, rcond=None)[0]
    return beta


def build():
    ind = {k: monthly(c, s) for k, (c, s, _) in CODES.items()}
    gdp = gdp_qoq()
    last_gdp_q = sorted(gdp)[-1]
    qs = sorted(set(qkey(m) for m in ind["iip"]))
    feats = {q: {k: feature(ind[k], q) for k in ind} for q in qs}

    # ---- backtest / fit ----
    def rows(cols, upto, start=FIT_FROM):
        X, y, qq = [], [], []
        for q in sorted(gdp):
            if q < start or q >= upto or q in EXCLUDE or q not in feats:
                continue
            f = [feats[q][c] for c in cols]
            if any(v is None for v in f):
                continue
            X.append(f); y.append(gdp[q]); qq.append(q)
        return np.array(X), np.array(y), qq

    bt = {m[0]: [] for m in MODELS}
    bt["Benchmark: mean growth"] = []
    test_qs = [q for q in sorted(gdp) if q >= OOS_FROM and q not in EXCLUDE]
    for q in test_qs:
        for name, cols in MODELS:
            X, y, _ = rows(cols, q)
            f = [feats[q][c] for c in cols] if q in feats else [None]
            if len(y) < 25 or any(v is None for v in f):
                continue
            beta = ols(X, y)
            p = beta[0] + np.dot(beta[1:], f)
            bt[name].append((q, p, gdp[q], gdp[prev_q(q)] if prev_q(q) in gdp else None))
        X, y, _ = rows([], q) if False else (None, None, None)
        ys = [gdp[k] for k in sorted(gdp) if FIT_FROM <= k < q and k not in EXCLUDE]
        bt["Benchmark: mean growth"].append((q, float(np.mean(ys)), gdp[q], gdp.get(prev_q(q))))
    stats = {}
    for name, r in bt.items():
        e = np.array([p - a for _, p, a, _ in r])
        stats[name] = dict(n=len(e), mae=float(np.abs(e).mean()), rmse=float(np.sqrt((e ** 2).mean())),
                           hit03=float((np.abs(e) <= 0.3).mean() * 100), hit05=float((np.abs(e) <= 0.5).mean() * 100),
                           sign=float(np.mean([(p > 0) == (a > 0) for _, p, a, _ in r]) * 100))

    # ---- live fit for target quarter ----
    last_month = max(ind["iip"])
    target_months = months_of(TARGET_Q)
    proj = {k: ar1_project(ind[k], target_months[-1]) for k in ind}
    inputs = {k: feature(proj[k], TARGET_Q) for k in ind}
    avail = {k: max(ind[k]) for k in ind}
    models_out = []
    for name, cols in MODELS:
        X, y, _ = rows(cols, TARGET_Q)
        beta = ols(X, y)
        f = [inputs[c] for c in cols]
        pred = float(beta[0] + np.dot(beta[1:], f))
        resid = y - np.c_[np.ones(len(X)), X] @ beta
        r2 = 1 - resid.var() / y.var()
        models_out.append(dict(name=name, cols=cols, coef=[float(b) for b in beta], r2=float(r2),
                               oos_rmse=stats[name]["rmse"], pred=pred))
    w = np.array([1 / m["oos_rmse"] ** 2 for m in models_out])
    comb = float(sum(wi * m["pred"] for wi, m in zip(w, models_out)) / w.sum())

    hist = [dict(q=q, qoq=gdp[q]) for q in sorted(gdp) if q >= "2022Q1"]
    carry_qs = []
    q = last_gdp_q
    # YoY chain: Q4-prev, Q1, Q2 published + Q3 nowcast
    yq = [f"{int(TARGET_Q[:4]) - 1}Q4", f"{TARGET_Q[:4]}Q1", f"{TARGET_Q[:4]}Q2"]
    carry = {k.replace(str(int(TARGET_Q[:4]) - 1), "").replace(TARGET_Q[:4], ""): gdp[k] for k in yq if k in gdp}

    data = dict(
        asof=datetime.date.today().isoformat(), target=TARGET_Q, last_published=last_gdp_q,
        inputs=inputs, models=models_out, combined_qoq=comb, hist=hist,
        carry=dict(q4=gdp[yq[0]], q1=gdp[yq[1]], q2=gdp[yq[2]]),
        weights=[float(x) for x in (w / w.sum())],
        indicator_latest_month=avail,
        indicator_names={k: v[2] for k, v in CODES.items()},
        backtest=[dict(model=n, **s) for n, s in stats.items()],
        backtest_window=f"{OOS_FROM}-{last_gdp_q} (excl. 2020)",
        backtest_rows={n: [dict(q=q, pred=p, actual=a) for q, p, a, _ in r] for n, r in bt.items()},
        monthly={k: {m: round(v, 2) for m, v in list(proj[k].items())[-9:]} for k in proj},
        projected_months={k: [m for m in target_months if m not in ind[k]] for k in ind},
    )
    json.dump(data, open(OUT, "w"), separators=(",", ":"))
    return data


if __name__ == "__main__":
    d = build()
    print("target", d["target"], "combined QoQ %.2f%%" % d["combined_qoq"], "(annualised %.1f%%)" % (((1 + d["combined_qoq"] / 100) ** 4 - 1) * 100))
    for m in d["models"]:
        print("  %-38s pred %.2f  r2 %.2f  oos_rmse %.2f" % (m["name"], m["pred"], m["r2"], m["oos_rmse"]))
    for b in d["backtest"]:
        print("  BT %-34s n=%d MAE %.2f RMSE %.2f hit03 %.0f hit05 %.0f" % (b["model"], b["n"], b["mae"], b["rmse"], b["hit03"], b["hit05"]))
    print("latest months:", d["indicator_latest_month"])
    print("projected:", d["projected_months"])
    print("inputs:", {k: round(v, 4) for k, v in d["inputs"].items()})
    print("carry:", d["carry"], "hist tail:", d["hist"][-4:])
