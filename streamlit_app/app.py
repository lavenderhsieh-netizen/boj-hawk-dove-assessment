import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="BOJ Hawk–Dove Dashboard", page_icon="🏦", layout="wide")

DATA = json.loads((Path(__file__).parent / "data.json").read_text(encoding="utf-8"))

HAWK, DOVE, NEUTRAL, ACCENT = "#e2564a", "#4a90d9", "#8a93a6", "#d9a441"

st.title("Bank of Japan — Hawk–Dove Assessment")
st.caption(
    f"Speeches and reports from the BOJ website, July 2024 – June 2026 · data as of {DATA['as_of']} · "
    "Tone scale: −2 (strongly dovish) … +2 (strongly hawkish), scored per speaker per half-year. "
    "Analytical assessment, not investment advice."
)

cols = st.columns(len(DATA["kpis"]))
for c, k in zip(cols, DATA["kpis"]):
    c.metric(label=k["label"][:60] + ("…" if len(k["label"]) > 60 else ""), value=k["value"], help=k["label"])

tab_dash, tab_board, tab_cal, tab_auction, tab_method = st.tabs(
    ["Dashboard", "Board & votes", "BOJ calendar", "Auctions & fiscal", "Methodology"]
)

with tab_dash:
    left, right = st.columns([1.2, 1])

    with left:
        st.subheader("Policy rate path")
        rp = DATA["rate_path"]
        fig = go.Figure(go.Scatter(
            x=rp["labels"], y=rp["values"], mode="lines+markers",
            line={"shape": "hv", "color": ACCENT, "width": 3}, fill="tozeroy",
            fillcolor="rgba(217,164,65,0.12)", name="Policy rate",
        ))
        fig.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10),
                          yaxis=dict(range=[0, 1.2], ticksuffix="%"), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Current spectrum (latest tone)")
        sp = pd.DataFrame(DATA["spectrum"])
        colors = [HAWK if s > 0 else DOVE if s < 0 else NEUTRAL for s in sp["score"]]
        fig = go.Figure(go.Bar(x=sp["score"], y=sp["name"], orientation="h", marker_color=colors))
        fig.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10),
                          xaxis=dict(range=[-2, 2], title="← dove | hawk →"),
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Tone by speaker over time")
    fig = go.Figure()
    palette = [HAWK, "#f0876f", ACCENT, "#e8c26a", "#c97b4a", NEUTRAL,
               "#8fa3c0", "#7fb3e8", DOVE, "#3568a8", "#2c507e", "#6db1ff"]
    for i, s in enumerate(DATA["tone"]):
        fig.add_trace(go.Scatter(x=DATA["periods"], y=s["scores"], mode="lines+markers",
                                 name=s["name"], line={"color": palette[i % len(palette)], "width": 2},
                                 connectgaps=False))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10),
                      yaxis=dict(range=[-2.3, 2.3], title="−2 dove … +2 hawk"),
                      legend=dict(orientation="h", yanchor="bottom", y=-0.35))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Gaps = no speech in period or not on the board. Nakamura (to Jun '25) and Adachi (to Mar '25) "
               "departed; Koeda, Masu, Asada and Sato joined.")

    st.subheader("Key speakers — how their tone changed")
    cards = DATA["speakers"]
    for row_start in range(0, len(cards), 2):
        for col, spk in zip(st.columns(2), cards[row_start:row_start + 2]):
            with col:
                icon = {"hawk": "🟥", "dove": "🟦", "neutral": "⬜"}[spk["lean"]]
                with st.container(border=True):
                    st.markdown(f"**{spk['name']}** · {spk['role']}  \n{icon} *{spk['tag']}* — {spk['shift']}")
                    st.caption(spk["quote"])

    st.subheader("Timeline of key events")
    for ev in DATA["timeline"]:
        icon = {"hike": "🔺", "dove": "🔹", "event": "▪️"}[ev["kind"]]
        st.markdown(f"{icon} **{ev['date']}** — {ev['text']}")

with tab_board:
    st.subheader("Policy Board: tenure & voting record (dissents, Jul 2024 – Jun 2026)")
    bd = pd.DataFrame(DATA["board"])
    bd["Status"] = bd["active"].map({True: "Current", False: "Departed"})
    show = bd[["member", "role", "tenure", "dissents", "record", "lean", "Status"]]
    show.columns = ["Member", "Role", "Tenure", "Dissents", "Voting record in window", "Leaning", "Status"]
    st.dataframe(show, use_container_width=True, hide_index=True, height=500)
    st.caption("Dissent counts cover MPM votes July 2024 – June 2026 (rate decisions plus the June 2025 "
               "JGB-taper vote). December 2025's hike to 0.75% was unanimous.")

with tab_cal:
    st.subheader("2026 calendar: MPMs & key releases")
    cal = pd.DataFrame(DATA["mpm_calendar"])
    cal["Next"] = cal["next"].map({True: "◀ next", False: ""})
    show = cal[["date", "type", "event", "relates", "notes", "Next"]]
    show.columns = ["Date", "Type", "Event", "Relates to", "Notes", ""]
    st.dataframe(show, use_container_width=True, hide_index=True, height=500)
    st.caption("Source: BOJ Monetary Policy Meetings schedule (boj.or.jp). Outlook Reports accompany the "
               "Jan / Apr / Jul / Oct meetings. Summaries of Opinions and Minutes release at 8:50am JST.")

with tab_auction:
    st.subheader("MOF JGB auction calendar")
    for month, rows in DATA["auctions"].items():
        st.markdown(f"**{month}**")
        df = pd.DataFrame(rows)
        df.columns = ["Date", "Type", "Issue", "Context"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("Rows noting 'MPM' coincide with BOJ meeting dates. Issue amounts are announced about one week "
               "before each auction; the calendar may be altered by MOF. Source: mof.go.jp auction calendar.")

    st.subheader("Japan fiscal watchlist")
    fw = pd.DataFrame(DATA["fiscal"])
    fw["Watch"] = fw["hot"].map({True: "★", False: ""})
    show = fw[["timing", "event", "relevance", "Watch"]]
    show.columns = ["Timing", "Event", "Relevance", ""]
    st.dataframe(show, use_container_width=True, hide_index=True, height=430)
    st.caption("Japan's fiscal year runs April–March. ★ = nearest / most market-sensitive items.")

with tab_method:
    st.subheader("Method & sources")
    st.markdown(
        """
Scores are qualitative judgments (−2 strong dove … +2 strong hawk) assigned per half-year from each
speaker's official BOJ speeches, MPM proposals and dissents, and Outlook Report framing, corroborated
with press coverage for events after the latest speeches.

**Primary sources:** BOJ Speeches and Statements listings 2024–2026 (boj.or.jp), including Ueda
(Keidanren, Dec 25, 2025), Tamura (Kanagawa, Feb 13, 2026), Takata (Kyoto, Feb 26, 2026), Noguchi
(Oita, Nov 27, 2025), Koeda (Niigata, Nov 20, 2025), Masu (Ehime, Feb 6, 2026), Himino (Wakayama,
Mar 2, 2026), Uchida (Kochi, Jul 23, 2025); BOJ MPM statements and Summaries of Opinions; the BOJ
meeting schedule; MOF auction calendars (Jul & Aug 2026).

**Press:** CNBC (Dec 19, 2025; Jun 16, 2026), The Japan Times (Jun 2026), Bloomberg (Jun 21, 2026),
Reuters (Sep–Oct 2025 dissents), Nippon.com/JIJI (Asada appointment). Voting records from BOJ policy
statements and press reports; press-only claims are marked "reported."

Summary-of-Opinions attributions are analytical inferences (the BOJ publishes them unattributed).
This is an analytical assessment of central-bank communication, not investment advice.
        """
    )
