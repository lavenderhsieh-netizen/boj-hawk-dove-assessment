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

# Reports whose titles contain any of these keywords are not Japan macro/rates/FX
# and should be excluded (e.g. Asia tech/semiconductor reports that appear cross-listed)
EXCLUDE_TITLE_KEYWORDS = [
    "AI Semi", "Asia Semi", "semiconductor", "Asia AI",
    "China Tech", "Korea Tech", "Taiwan", "DRAM", "NAND",
    "Global Autos", "Notice of change in analyst",
    "Japan Research Pack", "crude oil", "naphtha",
]

EVAL_JS = r"""(function() {
  const results = [];
  const seen = new Set();
  document.querySelectorAll('a[href*="publication"]').forEach(a => {
    const title = a.innerText.trim();
    if (title.length < 20 || seen.has(title)) return;
    seen.add(title);
    let el = a;
    for (let i = 0; i < 8; i++) {
      el = el.parentElement;
      if (!el) break;
      const txt = el.innerText || '';
      if (txt.includes(' READ | ')) {
        const dm = txt.match(/([A-Z]{3}\s+\d{1,2},\s+202\d)/);
        const lines = txt.split('\n').map(s => s.trim())
          .filter(s => s.length > 30 && !s.includes('READ |') && !s.includes('Subscribe') && s !== title);
        results.push({
          title: title.substring(0, 150),
          url: a.href,
          date: dm ? dm[1] : '',
          summary: lines[0] ? lines[0].substring(0, 300) : ''
        });
        break;
      }
    }
  });
  return JSON.stringify(results.slice(0, 6));
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
    snap = snapshot()

    # Click the generic analyst name option (retry up to 3x for slow dropdowns)
    pattern = rf'generic "{re.escape(name)}".*?ref=(e\d+)'
    m = re.search(pattern, snap)
    for _ in range(3):
        if m:
            break
        time.sleep(2)
        snap = snapshot()
        m = re.search(pattern, snap)
    if not m:
        # Fallback: any line with the analyst name
        for line in snap.splitlines():
            if name in line and 'sectionheader' not in line and 'searchbox' not in line:
                m2 = re.search(r'ref=(e\d+)', line)
                if m2:
                    ab("click", f"@{m2.group(1)}")
                    break
        else:
            print(f"    WARNING: no option found for {name}")
            return []
    else:
        ab("click", f"@{m.group(1)}")

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


def is_relevant(report: dict) -> bool:
    """Return False for reports that are clearly not Japan macro/rates/FX."""
    title = report.get("title", "")
    return not any(kw.lower() in title.lower() for kw in EXCLUDE_TITLE_KEYWORDS)


def main():
    all_reports = {}
    for analyst in ANALYSTS:
        try:
            reports = scrape_analyst(analyst)
            filtered = [r for r in reports if is_relevant(r)]
            if len(filtered) < len(reports):
                print(f"    Filtered {len(reports) - len(filtered)} non-Japan report(s)")
            all_reports[analyst] = filtered
        except Exception as e:
            print(f"    EXCEPTION: {e}")
            all_reports[analyst] = []

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
