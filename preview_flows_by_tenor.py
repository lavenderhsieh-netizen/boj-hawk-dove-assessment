"""
Professional, report-ready version: Medium-Term / Long-Term / Super-Long (>10y)
JGB net buying by the biggest players, side by side. Same JSDA source/pipeline as
the live BOJ dashboard's super-long chart (fetch_jsda_superlong.py's byplayer_tenor
object) -- no new data pull. "Biggest buyers" = top 3 by cumulative net buying over
the full history, per bucket (consistent with how the live super-long chart already
picks Trust/Foreign/Life).
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

d = json.load(open("/home/workspace/boj-hawk-dove-assessment/superlong_data.json"))
bt = d["byplayer_tenor"]
months_all = bt["months"]
players = bt["players"]

start = "2023-01"
idx0 = next(i for i, m in enumerate(months_all) if m >= start)
months = months_all[idx0:]
dates = [datetime.strptime(m, "%Y-%m") for m in months]
as_of = bt["months"][-1]

# consistent color per institution across all 3 panels
STYLE = {
    "trust":    ("Trust banks (pension)",  "#2f5aa0", "-"),
    "foreign":  ("Foreigners",             "#b5342a", "--"),
    "life":     ("Insurance companies",    "#4a7d4a", "-"),
    "mega":     ("City (mega) banks",      "#c98a2c", "-"),
    "regional": ("Regional banks",         "#7a5aa0", "--"),
}

PANELS = [
    {"bucket": "medium",    "title": "Medium-Term (1-5y)",  "picks": ["foreign", "trust", "regional"]},
    {"bucket": "long",      "title": "Long-Term (5-10y)",   "picks": ["trust", "mega", "regional"]},
    {"bucket": "superlong", "title": "Super-Long (>10y)",   "picks": ["trust", "foreign", "life"]},
]

plt.rcParams["font.family"] = "DejaVu Sans"
fig, axes = plt.subplots(1, 3, figsize=(18, 6.2), sharex=True)
fig.patch.set_facecolor("white")

for ax, spec in zip(axes, PANELS):
    ax.set_facecolor("white")
    bucket = spec["bucket"]
    for key in spec["picks"]:
        label, color, ls = STYLE[key]
        arr = players[key][bucket][idx0:]
        vals = [v if v is not None else float("nan") for v in arr]
        ax.plot(dates, vals, color=color, linewidth=1.7, linestyle=ls, label=label)
    ax.axhline(0, color="#999999", linewidth=0.7)
    ax.set_title(spec["title"], fontsize=12, fontweight="bold", loc="left")
    ax.tick_params(axis="x", labelsize=8, rotation=45)
    ax.tick_params(axis="y", labelsize=9)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.8)

axes[0].set_ylabel("JPY tn, monthly net buying", fontsize=10)

# shared legend across all 5 institutions that appear anywhere
handles, labels_seen = [], []
for ax in axes:
    h, l = ax.get_legend_handles_labels()
    for hh, ll in zip(h, l):
        if ll not in labels_seen:
            handles.append(hh); labels_seen.append(ll)
fig.legend(handles, labels_seen, loc="lower center", ncol=5, fontsize=9.5, frameon=False, bbox_to_anchor=(0.5, -0.02))

fig.suptitle(f"JGB Net Buying by Investor Type — by Maturity Bucket   (data to {as_of})",
             fontsize=15, fontweight="bold", x=0.06, ha="left", y=1.03)
fig.text(0.06, 0.965, "Monthly net purchases (purchases minus sales, outright basis), by the three largest net buyers in each maturity bucket",
         fontsize=10, color="#555555", ha="left")
fig.text(0.06, -0.09, "Source: Japan Securities Dealers Association, investor-type bond trading statistics.",
         fontsize=8, color="#777777", ha="left")

fig.tight_layout(rect=[0, 0.03, 1, 0.94])
out_path = "/home/.z/workspaces/con_ytzBmZJW6wnr4Y0E/jgb_decomp/jgb_flows_by_players_3panel.png"
fig.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"Saved {out_path}")
