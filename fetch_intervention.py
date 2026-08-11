#!/usr/bin/env python3.12
"""
Japan FX intervention tab — fetcher.

Builds intervention_data.json for the BOJ dashboard's Intervention tab:
  - long_history:   daily USD/JPY, 1985-present (FRED DEXJPUS) — for the
                     long-run chart with shaded intervention-episode bands.
  - recent_history:  same series, sliced to 2020-present, spliced with the
                     latest Yahoo Finance daily closes not yet in FRED
                     (FRED's H.10 series usually lags ~1 week).
  - episodes:        curated list of historical intervention episodes,
                     1985-2026 (digitized from a MUFG/Michael Wan chart,
                     cross-sourced against Japan MOF daily intervention
                     data, Ito & Yabu (2020), Bordo/Humpage/Schwartz (2015),
                     NY Fed, ECB). Static reference data — update by hand
                     when a new episode occurs or MOF issues a fresh
                     quarterly breakdown.
  - recent_ops:      individual operation-day estimates for the 2022-2026
                     cycle (also curated/static).

This is NOT on the daily auto-refresh loop (MOF's official day-by-day
intervention data is released quarterly with a ~3 month lag, so there is
nothing new to pull daily). Re-run by hand:
  - when a new intervention episode occurs (add a row to EPISODES / RECENT_OPS)
  - when MOF's quarterly release lands and confirms/revises an estimate
  - occasionally, to refresh the underlying long_history/recent_history FX line

Usage: python3.12 fetch_intervention.py
"""
import json
import os
from datetime import datetime, timedelta, timezone

import requests

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

FRED_KEY = os.environ.get("FRED_API_KEY", "")
UA = {"User-Agent": "Mozilla/5.0"}


def fred_series(series_id, start):
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={FRED_KEY}&file_type=json"
        f"&observation_start={start}"
    )
    r = requests.get(url, timeout=45)
    r.raise_for_status()
    hist = []
    for o in r.json().get("observations", []):
        if o["value"] in (".", "", None):
            continue
        hist.append({"date": o["date"], "value": float(o["value"])})
    return hist


def yahoo_jpy_history():
    """Full-history daily USD/JPY closes from Yahoo Finance (JPY=X).

    Yahoo's JPY=X only goes back to 1996-10-30 (FRED DEXJPUS is used for the
    1985-1996 stretch instead), but for every date it does cover it tracks
    live spot — unlike FRED DEXJPUS, which was found 2026-08-08 to be running
    several business days behind its FRED siblings (see fetch_market.py's
    fetch_fx() docstring). The intervention tab's per-round before/after
    snapshots (episode_snapshots) all fall in 2022-2026, squarely inside
    Yahoo's accurate range, so this replaces the old "FRED + crude last-30-day
    Yahoo splice" approach that could misidentify the peak/trough day right
    around a fresh operation if FRED's lag hadn't caught up yet.
    """
    if not HAS_YFINANCE:
        return []
    t = yf.Ticker("JPY=X")
    hist_df = t.history(period="max")
    out = [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 2)}
           for d, v in zip(hist_df.index, hist_df["Close"])]
    try:
        live = t.fast_info.get("last_price")
        if live and out:
            out[-1] = {"date": out[-1]["date"], "value": round(float(live), 2)}
    except Exception:
        pass
    return out


# ── Historical intervention episodes, 1985-2026 ──────────────────────────────
# Digitized from a MUFG (Michael Wan) chart: "Japan FX Intervention — Major
# Episodes since 1973". Sign convention: positive = net buy-JPY (strengthen),
# negative = net sell-JPY (weaken). USD bn.
EPISODES = [
    dict(start="1985-09", end="1985-11", context="Plaza Accord",
         direction="buy", coordinated=True, total=10.2, japan=3.0, nonjapan=7.2, confirmed=True),
    dict(start="1987-01", end="1987-04", context="Louvre Accord",
         direction="sell", coordinated=True, total=-29.4, japan=-25.4, nonjapan=-4.0, confirmed=True),
    dict(start="1987-08", end="1988-04", context="Black Monday",
         direction="sell", coordinated=True, total=-14.4, japan=-11.6, nonjapan=-2.8, confirmed=True),
    dict(start="1989-05", end="1990-04", context="Coordinated Intervention",
         direction="buy", coordinated=True, total=47.7, japan=34.9, nonjapan=12.9, confirmed=True),
    dict(start="1993-04", end="1994-11", context="Japan Asset Bubble Burst",
         direction="sell", coordinated=False, total=-44.7, japan=-43.2, nonjapan=-1.5, confirmed=True),
    dict(start="1995-02", end="1995-09", context='"Reverse Plaza Accord"',
         direction="sell", coordinated=True, total=-53.9, japan=-52.8, nonjapan=-1.1, confirmed=True),
    dict(start="1997-12", end="1998-04", context="Yen support during Asian Financial Crisis",
         direction="buy", coordinated=False, total=30.2, japan=30.2, nonjapan=0.0, confirmed=True),
    dict(start="1998-06-17", end="1998-06-17", context="US-Japan Joint Intervention",
         direction="buy", coordinated=True, total=2.6, japan=1.8, nonjapan=0.8, confirmed=True),
    dict(start="1999-01", end="2000-04", context="Yen selling to support economy",
         direction="sell", coordinated=False, total=-95.3, japan=-95.3, nonjapan=0.0, confirmed=True),
    dict(start="2000-09-22", end="2000-09-22", context="Joint EUR/USD buying to support depreciating euro",
         direction="eur", coordinated=True, total=None, japan=None, nonjapan=None, confirmed=True,
         note="EUR intervention, not USD/JPY — no $ breakdown in source table."),
    dict(start="2001-09", end="2001-09", context="Post-9/11 yen selling",
         direction="sell", coordinated=False, total=-26.4, japan=-26.4, nonjapan=0.0, confirmed=True),
    dict(start="2003-05", end="2004-03", context='The "Great Intervention" — massive yen-selling campaign',
         direction="sell", coordinated=False, total=-292.7, japan=-292.7, nonjapan=0.0, confirmed=True),
    dict(start="2011-03-18", end="2011-03-18", context="Post-2011 Japan earthquake G7 coordinated intervention",
         direction="sell", coordinated=True, total=-11.0, japan=-8.7, nonjapan=-2.3, confirmed=True),
    dict(start="2011-10-31", end="2011-11-04", context="Record FX intervention after USD/JPY hit 75.31",
         direction="sell", coordinated=False, total=-114.1, japan=-114.1, nonjapan=0.0, confirmed=True),
    dict(start="2022-09-22", end="2022-10-24", context="First yen buying since 1998",
         direction="buy", coordinated=False, total=62.9, japan=62.9, nonjapan=0.0, confirmed=True,
         note="Corrected 2026-08-04: was $69.9bn (stale figure from original chart digitization); "
              "sum of the three MOF-confirmed daily ops (¥2.84tn+5.62tn+0.73tn=¥9.19tn) is $62.9bn, "
              "matching external estimates ($60.8-65.2bn range, Reuters/Nippon.com)."),
    dict(start="2024-04-29", end="2024-05-01", context="Golden Week yen support",
         direction="buy", coordinated=False, total=62.2, japan=62.2, nonjapan=0.0, confirmed=True,
         note="Corrected 2026-08-04: was $64.6bn; MOF officially confirmed ¥9.79tn = $62.23bn "
              "(Reuters, 31 May 2024), matching the sum of the two daily ops."),
    dict(start="2024-07-11", end="2024-07-12", context="Yen support",
         direction="buy", coordinated=False, total=36.5, japan=36.5, nonjapan=0.0, confirmed=True),
    dict(start="2026-01-23", end="2026-01-23", context="Suspected BOJ + NY Fed rate check — no actual FX spend",
         direction="buy", coordinated=True, total=0.0, japan=0.0, nonjapan=0.0, confirmed=True,
         note="Officials asked banks about USD/JPY levels after the pair hit ~159.2 — a preparatory step, not "
              "an actual operation. Desk research (Mizuho FI, financial wires) confirms $0 actual spend vs. an "
              "estimated ~¥370bn if executed."),
    dict(start="2026-04-28", end="2026-05-27", context="Golden Week 2026 yen support — record single-round intervention",
         direction="buy", coordinated=False, total=73.0, japan=73.0, nonjapan=0.0, confirmed=True,
         note="MOF-confirmed ¥11.7tn / $73bn (Nikkei Asia, 29 May 2026) — supersedes pre-confirmation "
              "chart estimate of $77.5bn."),
    dict(start="2026-07-30", end="2026-07-31", context="Joint US-Japan FX intervention to strengthen JPY — "
                                                          "first joint yen-buying intervention since 1998 "
                                                          "(first joint intervention of any kind since 2011)",
         direction="buy", coordinated=True, total=98.47, japan=90.97, nonjapan=7.5, confirmed="event",
         note="Event officially confirmed by Japan MOF and US Treasury Sec. Bessent on 3 Aug 2026 (Reuters, "
              "Nikkei, Business Times, Nippon.com). Japan-side figure is two separate daily market estimates "
              "summed: ~$58.97bn on 30 Jul (BOJ current-account residuals, Reuters) + ~$32bn on 31 Jul "
              "(separate ¥5tn residual reported by TBS/JNN, 3 Aug 2026, tied to the confirmed joint leg). "
              "Exact MOF-confirmed size (incl. US Treasury's own leg) is pending the next quarterly MOF "
              "disclosure — all $ figures here are market estimates, not yet official. The US Treasury leg "
              "was reportedly funded by selling EUR rather than USD (FT; independently corroborated by a "
              "desk US Treasury FX intervention table, sourced MRS/Congressional Research Service, which "
              "lists Jul-2026 as \"Bought JPY / Sold EUR\") — implying ECB coordination, though the exact "
              "US-side dollar size remains unconfirmed (\"?\" in that same source)."),
]

# ── Recent-cycle individual operation days, 2022-2026 ────────────────────────
# "official": MOF has confirmed this specific date via its monthly/quarterly
# intervention data. "estimate": inferred from BOJ current-account residuals /
# market reporting, pending official confirmation.
RECENT_OPS = [
    dict(date="2022-09-22", jpy_tn=2.84, usd_bn=19.9, official=True),
    dict(date="2022-10-21", jpy_tn=5.62, usd_bn=38.1, official=True),
    dict(date="2022-10-24", jpy_tn=0.73, usd_bn=4.9, official=True),
    dict(date="2024-04-29", jpy_tn=5.92, usd_bn=37.9, official=True),
    dict(date="2024-05-01", jpy_tn=3.87, usd_bn=25.0, official=True),
    dict(date="2024-07-11", jpy_tn=3.17, usd_bn=19.9, official=True),
    dict(date="2024-07-12", jpy_tn=2.37, usd_bn=15.0, official=True),
    dict(date="2026-01-23", jpy_tn=0.0, usd_bn=0.0, official=False,
         label="Rate check ($0 spend)",
         note="Suspected BOJ + NY Fed rate check (USD-selling) after USD/JPY hit ~159.2; "
              "no actual FX spend — desk research (Mizuho FI, financial wires) confirms $0 actual "
              "vs. an estimated ~¥370bn if executed. Included for completeness, not a real operation."),
    dict(date="2026-04-30", jpy_tn=6.2787, usd_bn=40.1, official=True,
         label="MOF-confirmed", note="Official day-by-day breakdown released 7 Aug 2026 (Apr-Jun 2026 quarter); "
                                  "USD figure is a derived conversion at that day's FX close (¥156.66), not "
                                  "MOF-published. Within the ¥11.7349tn/$73bn Apr28-May27 round."),
    dict(date="2026-05-04", jpy_tn=0.7802, usd_bn=5.0, official=True,
         label="MOF-confirmed", note="Official day-by-day breakdown released 7 Aug 2026 (Apr-Jun 2026 quarter); "
                                  "previously not broken out as a separate operation day. USD figure is a "
                                  "derived conversion at that day's FX close (¥157.21). Within the ¥11.7349tn/"
                                  "$73bn Apr28-May27 round."),
    dict(date="2026-05-06", jpy_tn=4.6759, usd_bn=29.9, official=True,
         label="MOF-confirmed", note="Official day-by-day breakdown released 7 Aug 2026 (Apr-Jun 2026 quarter); "
                                  "USD figure is a derived conversion at that day's FX close (¥156.44). Within "
                                  "the ¥11.7349tn/$73bn Apr28-May27 round."),
    dict(date="2026-07-30", jpy_tn=8.45, usd_bn=58.97, official=False,
         label="Market est. (Thu)", note="Solo Japan operation ahead of the BOJ meeting; exact size pending "
                                    "MOF's official disclosure. Derived from BOJ current-account residuals "
                                    "vs. money-broker forecasts (Reuters, 31 Jul 2026)."),
    dict(date="2026-07-31", jpy_tn=5.0, usd_bn=32.0, official=False,
         label="Market est. (Fri, joint)", note="Second, separate day of intervention — the confirmed joint "
                                    "US-Japan leg (NY trading Fri, first since 1998). Sized from a distinct "
                                    "~¥5tn BOJ current-account residual for this settlement date (TBS/JNN, "
                                    "3 Aug 2026); $ conversion approximate (~¥156-160 range that day). "
                                    "Separately, the US Treasury's own leg is estimated at $5-10bn (Bessent's "
                                    "handwritten note, Reuters photo)."),
]

SOURCES = [
    "Japan MOF Daily Intervention data",
    "Ito & Yabu (2020)",
    "Bordo, Humpage & Schwartz (2015)",
    "NY Fed, ECB",
    "MUFG / Michael Wan (chart digitization, historical episodes table + recent-cycle chart)",
    "Nikkei Asia (29 May 2026) — MOF-confirmed $73bn Apr-May 2026 round",
    "Japan MOF official day-by-day intervention CSV (released 7 Aug 2026, Apr-Jun 2026 quarter) — "
    "confirms Apr 30 (¥6.2787tn), May 4 (¥0.7802tn), May 6 (¥4.6759tn), totaling ¥11.7349tn",
    "Reuters, Nippon.com, Business Times, Yahoo Finance (3 Aug 2026) — MOF/Bessent confirmation of "
    "30-31 Jul 2026 joint intervention",
    "FRED DEXJPUS (daily USD/JPY history)",
]

# IMF's AREAER "free floating" classification rule + how MOF has been running against it
# in the current cycle. Hand-maintained (not derivable from RECENT_OPS' broader disclosure
# windows) — update instances_used when a new operation occurs or MOF/press cites a fresh count.
IMF_RULE = dict(
    text=(
        "Under the IMF's AREAER exchange-rate classification methodology, a floating currency "
        "keeps its ‘free floating’ status only if official intervention occurs exceptionally, "
        "to address disorderly market conditions, and is limited to at most 3 instances in the "
        "trailing six months, each lasting no more than 3 consecutive business days. Exceeding "
        "that, the IMF reclassifies the regime down from ‘free floating’ to ‘floating’ — no "
        "formal penalty, but a credibility marker watched by G7/G20 counterparts."
    ),
    source="IMF Working Paper 09/211 (Habermeier et al., 2009); IMF AREAER Annual Reports 2018-2023",
    operational_note=(
        "Japan's MOF has explicitly invoked this rule: on 4-5 May 2026, an MOF official traveling with "
        "FinMin Katayama in Samarkand said the IMF counts intervention on up to 3 consecutive business "
        "days (holidays count if major markets abroad are open) as a single ‘instance’ — and that "
        "the Apr 30-May 4 2026 Golden Week operation counted as just one instance, leaving ‘two more "
        "windows’ before November 2026 (financial press)."
    ),
    as_of="2026-08-03",
    instances_trailing_6mo=[
        dict(label="Golden Week 2026 round", dates="30 Apr – 4 May 2026",
             note="MOF's own stated instance #1 under the 3-day rule (financial press, 4-5 May 2026)."),
        dict(label="Joint US-Japan operation", dates="30-31 Jul 2026",
             note="New instance — confirmed 3 Aug 2026; 2 consecutive business days (Thu-Fri), within the 3-day cap."),
    ],
    used=2,
    quota=3,
    window_note=(
        "2 of 3 permitted instances used within the trailing six months (since ~3 Feb 2026) as of 3 Aug 2026. "
        "The Jan 23 2026 rate-check doesn't count — $0 actual spend, not a real operation. The Golden Week "
        "instance ages out of the 6-month lookback around early Nov 2026, restoring headroom to 2 of 3 absent "
        "a further operation before then. One more instance is available before Japan risks an IMF "
        "reclassification from ‘free floating’ to ‘floating’."
    ),
)


# Bessent-Japan diplomatic timeline for the 2026 cycle: bilateral meetings/calls plus
# Mimura's on-the-record remarks. Hand-maintained (not derivable from RECENT_OPS/EPISODES) —
# append a row when a new meeting occurs or Mimura/Katayama/Bessent says something notable.
DIPLOMATIC_EVENTS = [
    dict(date="2026-01-12", actor="Bessent × Katayama", kind="meeting",
         event="Bilateral meeting, Washington D.C. (G7 sidelines)",
         detail="Katayama: “I expressed my concerns about the one-way weakening of the yen. "
                "Secretary Bessent shares those concerns.”"),
    dict(date="2026-01-26", actor="Mimura", kind="statement",
         event="Remarks to reporters, Tokyo",
         detail="“We will continue to closely coordinate with the U.S. authorities as needed... "
                "and will respond appropriately.”"),
    dict(date="2026-04-15", actor="Bessent × Katayama", kind="meeting",
         event="Bilateral meeting, US Treasury, Washington D.C. (IMF/World Bank Spring Meetings)",
         detail="Agreed to strengthen FX communication; Katayama announced Bessent would visit Tokyo in May."),
    dict(date="2026-05-07", actor="Mimura", kind="statement",
         event="Press conference, Tokyo (post Golden Week intervention)",
         detail="Mimura said the IMF's “free floating” classification “does not limit” how often Japan "
                "can intervene — pushing back on the idea that the rule caps further action."),
    dict(date="2026-05-11/13", actor="Bessent", kind="meeting",
         event="3-day Japan visit, Tokyo — met PM Takaichi, FinMin Katayama and METI's Akazawa",
         detail="Bessent said he has “great confidence” Ueda will guide BOJ policy successfully. Ueda "
                "did NOT meet Bessent this trip — he was in Switzerland for a BIS meeting."),
    dict(date="2026-05-19", actor="Bessent × Ueda", kind="meeting",
         event="Met BOJ Gov. Ueda on sidelines of G7 finance chiefs' meeting, Paris",
         detail="Bessent on X: “I am confident that Governor Ueda will successfully guide Japan's monetary "
                "policy” — their first in-person meeting of the cycle."),
    dict(date="2026-06-22", actor="Bessent × Katayama", kind="meeting",
         event="~1hr online call, described as a G7-summit follow-up",
         detail="Discussed global financial markets and the Iran conflict; declined to comment on the yen "
                "itself."),
    dict(date="2026-07-31", actor="Mimura", kind="statement",
         event="Remarks to reporters, Tokyo (day after the joint operation)",
         detail="Declined to confirm intervention, but said “we have received support from U.S. "
                "authorities that goes beyond mere moral support.”"),
    dict(date="2026-08-03", actor="Mimura", kind="statement",
         event="Joint Japan-US statement issued on the 30-31 Jul operation",
         detail="Mimura: the joint intervention “could mark the peak of the US-Japan currency "
                "partnership.”"),
    # ── Scheduled / expected — not yet occurred as of this file's last update ──
    dict(date="2026-08-31", actor="Bessent × Ueda (expected)", kind="scheduled",
         event="G20 Finance Ministers & Central Bank Governors Meeting, Asheville, NC (31 Aug – 1 Sep)",
         detail="Bessent: looks forward to seeing his “longtime friend” Ueda there — their first "
                "face-to-face since the 19-May Paris G7 sidelines meeting."),
    dict(date="2026-10-12", actor="Bessent × Katayama (expected)", kind="scheduled",
         event="G7/IMFC Finance Ministers' meeting on sidelines of IMF-World Bank Annual Meetings, Bangkok "
              "(week of 12 Oct)",
         detail="A Bessent-Katayama bilateral is typical at these sidelines — not yet confirmed for this "
              "specific date."),
]

import re


def episode_before_after(ep, long_hist, tail_days=5):
    """USD/JPY level immediately before an episode started vs. shortly after it
    ended, plus the % change — the "before/after" framing HanHan asked for in
    place of the old (always-blank — 'effects' was never populated) 1d/5d/20d
    'effect' columns. Simple and literal, deliberately distinct from the
    peak/trough search build_episode_snapshots() does for the snapshot cards
    above: 'before' = last close strictly before the episode's first
    operation date; 'after' = the close `tail_days` trading days after the
    episode's last operation date (or the last available close if the window
    runs past the end of history).

    Only computable for episodes with an exact start/end date (YYYY-MM-DD) —
    most of the pre-2022 episodes are recorded as YYYY-MM month ranges (multi-
    month campaigns with no single before/after anchor day), so those
    correctly return None rather than a fabricated before/after pair.
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", ep["start"]) or not re.match(r"^\d{4}-\d{2}-\d{2}$", ep["end"]):
        return None
    dates = [p["date"] for p in long_hist]
    by_date = {p["date"]: p["value"] for p in long_hist}

    before_candidates = [d for d in dates if d < ep["start"]]
    if not before_candidates:
        return None
    before_date = before_candidates[-1]

    after_candidates = [d for d in dates if d >= ep["end"]]
    if not after_candidates:
        return None
    after_idx = min(tail_days, len(after_candidates) - 1)
    after_date = after_candidates[after_idx]

    before_val, after_val = by_date[before_date], by_date[after_date]
    return {
        "before": {"date": before_date, "value": before_val},
        "after": {"date": after_date, "value": after_val},
        "change_yen": round(after_val - before_val, 2),
        "change_pct": round((after_val - before_val) / before_val * 100, 2),
    }


def build_episode_snapshots(recent_hist, recent_ops, gap_days=14, lead_days=5, tail_days=12):
    """Group RECENT_OPS into intervention rounds (ops within `gap_days` of each
    other) and, for each round, slice a zoomed daily USD/JPY window around it
    with the pre-op high / post-op low and the resulting yen drop — a daily-data
    stand-in for a zoomed intraday-tick "snapshot" view."""
    by_date = {p["date"]: p["value"] for p in recent_hist}
    dates_sorted = sorted(by_date)

    real_ops = [o for o in recent_ops if o.get("jpy_tn", 0) or o.get("usd_bn", 0)]
    groups = []
    for op in sorted(real_ops, key=lambda o: o["date"]):
        if groups and (datetime.strptime(op["date"], "%Y-%m-%d")
                       - datetime.strptime(groups[-1][-1]["date"], "%Y-%m-%d")).days <= gap_days:
            groups[-1].append(op)
        else:
            groups.append([op])

    snapshots = []
    for g in groups:
        first_date = datetime.strptime(g[0]["date"], "%Y-%m-%d")
        last_date = datetime.strptime(g[-1]["date"], "%Y-%m-%d")
        win_start = (first_date - timedelta(days=lead_days)).strftime("%Y-%m-%d")
        win_end = (last_date + timedelta(days=tail_days)).strftime("%Y-%m-%d")
        win_dates = [d for d in dates_sorted if win_start <= d <= win_end]
        if not win_dates:
            continue
        points = [{"date": d, "value": by_date[d]} for d in win_dates]

        pre = [p for p in points if p["date"] <= g[0]["date"]]
        post = [p for p in points if p["date"] >= g[0]["date"]]
        peak = max(pre, key=lambda p: p["value"]) if pre else max(points, key=lambda p: p["value"])
        trough = min(post, key=lambda p: p["value"]) if post else min(points, key=lambda p: p["value"])

        total_jpy = round(sum(o.get("jpy_tn", 0) for o in g), 2)
        total_usd = round(sum(o.get("usd_bn", 0) for o in g), 1)
        snapshots.append({
            "label": f"{g[0]['date']}" + (f" – {g[-1]['date']}" if len(g) > 1 else ""),
            "ops": g,
            "window_start": win_dates[0],
            "window_end": win_dates[-1],
            "points": points,
            "peak": peak,
            "trough": trough,
            "drop_yen": round(peak["value"] - trough["value"], 2),
            "drop_pct": round((peak["value"] - trough["value"]) / peak["value"] * 100, 2),
            "total_jpy_tn": total_jpy,
            "total_usd_bn": total_usd,
        })
    return snapshots


def main():
    print("Fetching long-run USD/JPY history (FRED DEXJPUS, 1985-1996-10-29)...")
    fred_hist = fred_series("DEXJPUS", "1985-01-01")
    if len(fred_hist) < 2000:
        raise ValueError(f"FRED history too short: {len(fred_hist)} points")
    print(f"  {len(fred_hist)} points, {fred_hist[0]['date']} to {fred_hist[-1]['date']}")

    print("Fetching accurate 1996-present USD/JPY history (Yahoo Finance JPY=X)...")
    yahoo_hist = yahoo_jpy_history()
    if len(yahoo_hist) < 2000:
        raise ValueError(f"Yahoo history too short ({len(yahoo_hist)} points) — "
                          "refusing to build episode_snapshots off a stale/incomplete FX series.")
    print(f"  {len(yahoo_hist)} points, {yahoo_hist[0]['date']} to {yahoo_hist[-1]['date']}")

    yahoo_start = yahoo_hist[0]["date"]
    long_hist = [p for p in fred_hist if p["date"] < yahoo_start] + yahoo_hist
    long_hist.sort(key=lambda p: p["date"])
    print(f"  spliced long_history: {len(long_hist)} points, {long_hist[0]['date']} to {long_hist[-1]['date']} "
          f"(FRED before {yahoo_start}, Yahoo from {yahoo_start} on)")

    recent_hist = [p for p in long_hist if p["date"] >= "2020-01-01"]

    print("Building per-episode intervention snapshots...")
    episode_snapshots = build_episode_snapshots(recent_hist, RECENT_OPS)
    print(f"  {len(episode_snapshots)} snapshot(s)")

    print("Computing before/after USD/JPY level + % change per episode (exact-date episodes only)...")
    episodes_out = []
    n_with_ba = 0
    for ep in EPISODES:
        ep = dict(ep)
        ba = episode_before_after(ep, long_hist)
        ep["before_after"] = ba
        if ba:
            n_with_ba += 1
        episodes_out.append(ep)
    print(f"  {n_with_ba}/{len(episodes_out)} episodes have an exact-date before/after")

    out = {
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": SOURCES,
        "long_history": long_hist,
        "recent_history": recent_hist,
        "episodes": episodes_out,
        "recent_ops": RECENT_OPS,
        "episode_snapshots": episode_snapshots,
        "imf_rule": IMF_RULE,
        "diplomatic_events": DIPLOMATIC_EVENTS,
    }

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intervention_data.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
