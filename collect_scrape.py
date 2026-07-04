#!/usr/bin/env python3
"""
BOJ scraper — pure data fetcher, no LLM.
Writes fresh BOJ content to scraped.json for the automation agent to analyse.
"""

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO_DIR = Path("/home/workspace/boj-hawk-dove-assessment")
DATA_FILE = REPO_DIR / "streamlit_app" / "data.json"
SCRAPED_FILE = REPO_DIR / "scraped.json"
BOJ_BASE = "https://www.boj.or.jp"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BOJ-monitor/1.0)"}


def fetch(url, max_chars=5000):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav", "footer", "script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:max_chars]
    except Exception as e:
        print(f"  [warn] {url}: {e}", file=sys.stderr)
        return ""


def fetch_links(url, href_must_contain=""):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href_must_contain and href_must_contain not in href:
                continue
            if href.startswith("/"):
                href = BOJ_BASE + href
            text = a.get_text(strip=True)
            if text:
                results.append({"href": href, "text": text})
        return results
    except Exception as e:
        print(f"  [warn] links from {url}: {e}", file=sys.stderr)
        return []


def scrape_new_speeches(since_date_str, year):
    since_dt = datetime.strptime(since_date_str, "%Y-%m-%d").date()
    listing_url = f"{BOJ_BASE}/en/about/press/koen_{year}/index.htm"
    print(f"  Speech listing: {listing_url}")
    links = fetch_links(listing_url, href_must_contain=f"koen_{year}")

    results = []
    total_chars = 0
    for link in links:
        if total_chars >= 12000:
            break
        m = re.search(r"ko(\d{2})(\d{2})(\d{2})", link["href"])
        if not m:
            continue
        yy, mm, dd = m.groups()
        try:
            speech_date = date(2000 + int(yy), int(mm), int(dd))
        except ValueError:
            continue
        if speech_date <= since_dt:
            continue
        print(f"    Fetching {speech_date}: {link['text'][:60]}")
        text = fetch(link["href"], max_chars=3500)
        results.append({
            "date": str(speech_date),
            "title": link["text"],
            "url": link["href"],
            "text": text,
        })
        total_chars += len(text)

    return results


def main():
    today = date.today().isoformat()
    year = today[:4]

    current_data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    last = current_data.get("as_of", f"{year}-01-01")
    print(f"Scraping BOJ content (new since {last})…")

    scraped = {
        "scraped_at": today,
        "last_as_of": last,
        "mpm_decisions": fetch(
            f"{BOJ_BASE}/en/mopo/mpmdeci/mpr_{year}/index.htm", max_chars=5000
        ),
        "mpm_statements": fetch(
            f"{BOJ_BASE}/en/mopo/mpmdeci/state_{year}/index.htm", max_chars=5000
        ),
        "opinions": fetch(
            f"{BOJ_BASE}/en/mopo/mpmsche_minu/opinion_{year}/index.htm", max_chars=4000
        ),
        "speeches": scrape_new_speeches(last, year),
    }

    SCRAPED_FILE.write_text(json.dumps(scraped, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved scraped.json ({len(scraped['speeches'])} new speeches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
