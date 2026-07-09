#!/usr/bin/env python3
"""
Scrape latest Nomura research reports for target Japan analysts.
Uses agent-browser CLI (must already be authenticated or will re-login).
Run: python3 scrape_nomura.py
"""
import subprocess, json, re, time, os, sys
from datetime import datetime

USERNAME = os.environ.get("Nomura", "")
PASSWORD = os.environ.get("Nomura_password", "")
OUTPUT   = os.path.join(os.path.dirname(__file__), "nomura_reports.json")
SERVED   = os.path.join(os.path.dirname(__file__), "streamlit_app", "nomura_reports.json")

ANALYSTS = [
    "Kyohei Morita",
    "Tomoaki Shishido",
    "Yujiro Goto",
    "Masaki Kuwahara",
    "Mari Iwashita",
    "Uichiro Nozaki",
]
COVERAGE = {
    "Kyohei Morita":    "Japan Macro / BOJ",
    "Tomoaki Shishido": "Japan Rates",
    "Yujiro Goto":      "Japan FX",
    "Masaki Kuwahara":  "Japan Macro",
    "Mari Iwashita":    "BOJ / Rates",
    "Uichiro Nozaki":   "Japan Macro / Fiscal",
}

# Reports whose titles contain any of these keywords are clearly not Japan macro/rates/FX
EXCLUDE_TITLE_KEYWORDS = [
    # Tech/semi
    "AI Semi", "Asia Semi", "semiconductor", "Asia AI",
    "China Tech", "Korea Tech", "DRAM", "NAND",
    # Autos/energy
    "Global Autos", "crude oil", "naphtha",
    # Admin noise
    "Notice of change in analyst", "Japan Research Pack",
    # Non-Japan geographies
    "India", " HK)", "(HK)", "Hong Kong", "Taiwan",
    "Korea", "China", "France", "Germany", "Europe",
    "Singapore", "Indonesia", "Philippines", "Thailand",
    "Vietnam", "Malaysia", "Mexico", "Brazil", "Middle East",
    "Africa", "Australia", "UK)", "(UK)", "United Kingdom",
    "ASEAN", "EM ", " EM)", "Asia ex",
    # Equity/sector research clearly unrelated to Japan macro
    "Quick Note -", "pharma", "Pharma", "insurance", "Insurance",
    "AMC", "electric vehicle", "Sinobio", "AstraZeneca",
    "Ather Energy",
]

# For macro-focused analysts, titles must contain at least one Japan-related keyword
# (Goto/Shishido are FX/rates so they're allowed broader global macro context)
JAPAN_MACRO_ANALYSTS = {
    "Kyohei Morita", "Masaki Kuwahara", "Mari Iwashita", "Uichiro Nozaki"
}
JAPAN_KEYWORDS = [
    "Japan", "BOJ", "Bank of Japan", "JGB", "JPY", "Yen", "yen",
    "Nikkei", "Tokyo", "Abenomics", "Kishida", "Takaichi", "Ueda",
    "monetary policy", "Fiscal Insight", "BOJ Watch",
]

EVAL_JS = r"""(function() {
  const MON = {Jan:'JAN',Feb:'FEB',Mar:'MAR',Apr:'APR',May:'MAY',Jun:'JUN',
               Jul:'JUL',Aug:'AUG',Sep:'SEP',Oct:'OCT',Nov:'NOV',Dec:'DEC'};
  function titleDate(t) {
    // "Yen Rates Daily Monitor - 07 Jul 2026" -> "JUL 7, 2026"
    const m = t.match(/[-–]\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(20\d\d)/);
    if (m) return MON[m[2]] + ' ' + parseInt(m[1]) + ', ' + m[3];
    return null;
  }
  const results = [];
  const seen = new Set();
  document.querySelectorAll('a[href*="publication"]').forEach(a => {
    const title = a.innerText.trim();
    if (title.length < 20 || seen.has(title)) return;
    seen.add(title);
    let el = a;
    let found = false;
    for (let i = 0; i < 8; i++) {
      el = el.parentElement;
      if (!el) break;
      const txt = el.innerText || '';
      if (txt.includes(' READ | ')) {
        const dm = txt.match(/([A-Z]{3}\s+\d{1,2},\s+202\d)/);
        const lines = txt.split('\n').map(s => s.trim())
          .filter(s => s.length > 30 && !s.includes('READ |') && !s.includes('Subscribe') && s !== title);
        const date = titleDate(title) || (dm ? dm[1] : '');
        results.push({
          title: title.substring(0, 150),
          url: a.href,
          date: date,
          summary: lines[0] ? lines[0].substring(0, 300) : ''
        });
        found = true;
        break;
      }
    }
    // Daily monitors often lack "READ |" card structure — extract from title
    if (!found) {
      const d = titleDate(title);
      if (d) {
        results.push({title: title.substring(0, 150), url: a.href, date: d, summary: ''});
      }
    }
  });
  return JSON.stringify(results.slice(0, 8));
})()"""


def ab(*args, timeout=15):
    r = subprocess.run(["agent-browser"] + list(args), capture_output=True, text=True, timeout=timeout)
    return r.stdout


def snapshot():
    return ab("snapshot", "-i", timeout=20)


def login():
    print("  Logging in...")
    ab("open", "https://www.nomuranow.com/research/m/public/login")
    time.sleep(3)
    snap = snapshot()
    er = re.search(r'textbox "Enter email".*?ref=(e\d+)', snap)
    pr = re.search(r'textbox "Enter password".*?ref=(e\d+)', snap)
    lr = re.search(r'button "Log In".*?ref=(e\d+)', snap)
    if er: ab("fill", f"@{er.group(1)}", USERNAME)
    if pr: ab("fill", f"@{pr.group(1)}", PASSWORD)
    if lr: ab("click", f"@{lr.group(1)}")
    time.sleep(4)


def scrape_analyst(name):
    print(f"  → {name}")
    ab("open", "https://www.nomuranow.com/research/m/Home")
    time.sleep(3.5)
    snap = snapshot()

    # Re-login if needed
    if "Enter email" in snap:
        login()
        ab("open", "https://www.nomuranow.com/research/m/Home")
        time.sleep(3.5)
        snap = snapshot()

    # Dismiss modals
    for word in ['"Accept"', '"I Agree"', '"OK"']:
        m = re.search(rf'button {word}.*?ref=(e\d+)', snap)
        if m:
            ab("click", f"@{m.group(1)}")
            time.sleep(0.5)
            snap = snapshot()

    # Wait for the Analyst filter searchbox (up to 12s — cold start takes longer)
    searchbox_pat = r'(?:searchbox|textbox)[^"]*"Analyst name[^"]*".*?ref=(e\d+)'
    m = re.search(searchbox_pat, snap)
    for _ in range(4):
        if m:
            break
        time.sleep(3)
        snap = snapshot()
        m = re.search(searchbox_pat, snap)
    if not m:
        # Section may be collapsed — click header once to expand, then retry
        mh = re.search(r'sectionheader "Analyst".*?ref=(e\d+)', snap)
        if mh:
            ab("click", f"@{mh.group(1)}")
            time.sleep(1.5)
            snap = snapshot()
            m = re.search(searchbox_pat, snap)
    if not m:
        print(f"    WARNING: no analyst search box found")
        return []
    ab("fill", f"@{m.group(1)}", name)
    time.sleep(2.5)

    # Use JS to click the analyst suggestion — snapshot ref matching is unreliable
    # because the dropdown item appears as unlabelled `generic [ref=eN] clickable`
    js_click = (
        "(function(name){"
        "const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);"
        "let node;"
        "while(node=walker.nextNode()){"
        "if(node.nodeValue&&node.nodeValue.trim()===name){"
        "let el=node.parentElement;"
        "while(el&&el!==document.body){"
        "if(el.onclick||el.getAttribute('onclick')||el.style.cursor==='pointer'){"
        "el.click();return 'clicked:'+el.tagName;"
        "}"
        "el=el.parentElement;"
        "}"
        "}"
        "}"
        "return 'not found';"
        f"}})(\"{name}\")"
    )
    # Retry up to 5x for slow dropdowns
    clicked = False
    for _ in range(5):
        result = ab("eval", js_click, timeout=8)
        if "clicked" in str(result):
            clicked = True
            break
        time.sleep(2)
    if not clicked:
        print(f"    WARNING: could not click suggestion for {name}")
        return []

    time.sleep(3.5)

    # Extract via JS eval
    raw = ab("eval", EVAL_JS, timeout=15)
    raw = raw.strip()
    # eval output is a JSON string (sometimes double-encoded)
    try:
        data = json.loads(raw)
        if isinstance(data, str):
            data = json.loads(data)
        for r in data:
            r["analyst"]  = name
            r["coverage"] = COVERAGE.get(name, "")
        print(f"    {len(data)} reports")
        return data
    except Exception as e:
        print(f"    ERROR parsing eval output: {e}\n    Raw: {raw[:200]}")
        return []


MONTH_ORDER = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

def parse_date_key(date_str: str):
    """Parse 'JUL 7, 2026' → (2026, 7, 7) for sorting. Returns (0,0,0) on failure."""
    m = re.match(r"([A-Z]{3})\s+(\d{1,2}),\s+(\d{4})", date_str or "")
    if not m:
        return (0, 0, 0)
    return (int(m.group(3)), MONTH_ORDER.get(m.group(1), 0), int(m.group(2)))


def is_relevant(report: dict) -> bool:
    """Return False for reports that are clearly not Japan macro/rates/FX."""
    title = report.get("title", "")
    analyst = report.get("analyst", "")
    if any(kw.lower() in title.lower() for kw in EXCLUDE_TITLE_KEYWORDS):
        return False
    # For Japan macro analysts, require at least one Japan-related keyword in the title
    if analyst in JAPAN_MACRO_ANALYSTS:
        if not any(kw.lower() in title.lower() for kw in JAPAN_KEYWORDS):
            return False
    return True


def load_existing() -> dict:
    """Load existing reports so we can fall back to them if an analyst fails."""
    for path in [OUTPUT, SERVED]:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "reports" in data:
                return data["reports"]
        except Exception:
            pass
    return {}


def main():
    existing = load_existing()
    all_reports = {}

    for analyst in ANALYSTS:
        try:
            reports = scrape_analyst(analyst)
            filtered = [r for r in reports if is_relevant(r)]
            if len(filtered) < len(reports):
                print(f"    Filtered {len(reports) - len(filtered)} non-Japan report(s)")

            # Sort by date descending so latest reports appear first in the UI
            deduped = filtered
            deduped.sort(key=lambda r: parse_date_key(r.get("date", "")), reverse=True)

            # Quality gate: if the analyst filter silently failed, Nomura returns
            # unfiltered homepage content — many reports will be non-Japan noise.
            # If >60% of raw results were irrelevant, treat it as a filter failure
            # and fall back to existing data rather than saving junk.
            raw_count = len(reports)
            pass_rate = len(filtered) / raw_count if raw_count else 1.0
            filter_failed = raw_count >= 3 and pass_rate < 0.4

            if filter_failed:
                kept = existing.get(analyst, [])
                all_reports[analyst] = kept
                print(f"    QUALITY GATE: {len(filtered)}/{raw_count} passed ({pass_rate:.0%}) — likely filter failure, kept {len(kept)} existing reports")
            elif deduped:
                all_reports[analyst] = deduped
            else:
                # Keep existing data rather than blanking on scrape failure
                kept = existing.get(analyst, [])
                all_reports[analyst] = kept
                if kept:
                    print(f"    (kept {len(kept)} existing reports — scrape returned 0)")
        except Exception as e:
            print(f"    EXCEPTION: {e}")
            kept = existing.get(analyst, [])
            all_reports[analyst] = kept
            if kept:
                print(f"    (kept {len(kept)} existing reports)")

    result = {
        "scraped_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "analysts":   ANALYSTS,
        "coverage":   COVERAGE,
        "reports":    all_reports,
        "total":      sum(len(v) for v in all_reports.values()),
    }

    for path in [OUTPUT, SERVED]:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"✓ Saved {result['total']} reports → {path}")
        except Exception as e:
            print(f"  ERROR saving to {path}: {e}")


if __name__ == "__main__":
    main()
