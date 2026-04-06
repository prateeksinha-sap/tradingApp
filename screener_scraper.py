"""
Screener.in Scraper
Fetches Indian-specific fundamentals: ROCE, promoter holding, pledged %,
PEG ratio, interest coverage, 5Y growth rates, industry PE.
"""

import re
import time
import json
import sqlite3
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import CACHE_CONFIG


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Map yfinance ticker → screener symbol
def _ticker_to_screener(ticker: str) -> str:
    """Convert 'RELIANCE.NS' → 'RELIANCE', handle special cases."""
    symbol = ticker.replace(".NS", "")
    # Screener uses different symbols for some stocks
    mapping = {
        "M&M": "MM",
        "BAJAJ-AUTO": "BAJAJ-AUTO",
    }
    return mapping.get(symbol, symbol)


def _get_db():
    db_path = Path(CACHE_CONFIG["db_path"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=15)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS screener_cache (
            ticker TEXT PRIMARY KEY,
            data TEXT,
            fetched_at REAL
        )
    """)
    conn.commit()
    return conn


def _parse_number(text: str):
    """Parse a number from screener text like '18.5%' or '1,234' or '-5.2'."""
    if not text:
        return None
    text = text.strip().replace(",", "").replace("%", "").replace("₹", "")
    text = text.replace("\n", "").replace(" ", "")
    if text in ("", "-", "—", "NA", "N/A"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def scrape_screener_data(ticker: str) -> dict:
    """
    Scrape key data from screener.in for a single stock.
    Returns dict with ROCE, promoter holding, pledged %, PEG, etc.
    """
    symbol = _ticker_to_screener(ticker)
    url = f"https://www.screener.in/company/{symbol}/consolidated/"

    result = {
        "roce": None,
        "promoter_holding": None,
        "pledged_pct": None,
        "peg_ratio": None,
        "interest_coverage": None,
        "sales_growth_5y": None,
        "profit_growth_5y": None,
        "industry_pe": None,
        "screener_available": False,
    }

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        if resp.status_code == 404:
            # Try standalone (non-consolidated)
            url = f"https://www.screener.in/company/{symbol}/"
            resp = requests.get(url, headers=_HEADERS, timeout=15)

        if resp.status_code != 200:
            print(f"  ⚠ Screener: {symbol} returned status {resp.status_code}")
            return result

        soup = BeautifulSoup(resp.text, "lxml")
        result["screener_available"] = True

        # ── Parse the "ratios" list (top of page) ────────────────────────
        # Screener shows key ratios in <li> elements with <span class="name"> and <span class="number">
        ratio_list = soup.select("ul#top-ratios li, .company-ratios li, .ratios-table li")
        for li in ratio_list:
            name_el = li.select_one(".name, .tooltip")
            val_el = li.select_one(".number, .value")
            if not name_el or not val_el:
                continue
            name = name_el.get_text(strip=True).lower()
            val = val_el.get_text(strip=True)

            if "roce" in name:
                result["roce"] = _parse_number(val)
            elif "roe" in name and result.get("roe_screener") is None:
                result["roe_screener"] = _parse_number(val)
            elif "peg" in name:
                result["peg_ratio"] = _parse_number(val)
            elif "industry pe" in name or "sector pe" in name:
                result["industry_pe"] = _parse_number(val)
                # TODO: Screener.in does not expose "Industry Average ROCE" on the
                # individual company page — only the company's own ROCE is shown.
                # To score ROCE relative to industry peers, we would need to scrape
                # the corresponding sector screen page (screener.in/screens/<id>/)
                # and aggregate the ROCE column across all companies in that sector.
                # That requires a separate, non-trivial pipeline (pagination, sector
                # ID mapping, caching). Until implemented, scoring.py falls back to
                # the SECTOR_ROCE_BENCHMARKS config dict as an approximation.

        # ── Parse from the main data tables ──────────────────────────────
        # Look for ROCE, sales/profit growth in data rows
        all_text = soup.get_text()

        # ROCE from ratios section
        roce_match = re.search(r'ROCE[^0-9]*?(\d+\.?\d*)\s*%', all_text)
        if roce_match and result["roce"] is None:
            result["roce"] = float(roce_match.group(1))

        # PEG Ratio
        peg_match = re.search(r'PEG\s*Ratio[^0-9]*?(-?\d+\.?\d*)', all_text)
        if peg_match and result["peg_ratio"] is None:
            result["peg_ratio"] = float(peg_match.group(1))

        # Industry PE
        ipe_match = re.search(r'Industry\s*PE[^0-9]*?(\d+\.?\d*)', all_text)
        if ipe_match and result["industry_pe"] is None:
            result["industry_pe"] = float(ipe_match.group(1))

        # ── Shareholding pattern ─────────────────────────────────────────
        # Look for promoter holding percentage
        shareholding_section = soup.find("h2", string=re.compile(r"Shareholding", re.I))
        if shareholding_section:
            table = shareholding_section.find_next("table")
            if table:
                rows = table.select("tr")
                for row in rows:
                    cells = row.select("td, th")
                    if cells:
                        label = cells[0].get_text(strip=True).lower()
                        if "promoter" in label and len(cells) > 1:
                            # Get the most recent column (last td)
                            last_val = cells[-1].get_text(strip=True)
                            result["promoter_holding"] = _parse_number(last_val)
                            break

        # Promoter holding from ratios if not found in table
        if result["promoter_holding"] is None:
            promo_match = re.search(r'Promoter\s*holding[^0-9]*?(\d+\.?\d*)\s*%', all_text)
            if promo_match:
                result["promoter_holding"] = float(promo_match.group(1))

        # Pledged percentage
        pledge_match = re.search(r'Pledged[^0-9]*?(\d+\.?\d*)\s*%', all_text, re.I)
        if pledge_match:
            result["pledged_pct"] = float(pledge_match.group(1))
        else:
            # If no pledge mention, likely 0
            if result["promoter_holding"] is not None:
                result["pledged_pct"] = 0.0

        # ── Growth rates (from compounded growth tables) ─────────────────
        # Screener shows "Compounded Sales Growth" and "Compounded Profit Growth"
        growth_sections = soup.find_all("table", class_="ranges-table")
        for table in growth_sections:
            caption = table.find_previous(["h3", "h4", "p", "div"])
            if not caption:
                continue
            caption_text = caption.get_text(strip=True).lower()
            rows = table.select("tr")

            for row in rows:
                cells = row.select("td")
                if len(cells) >= 2:
                    period = cells[0].get_text(strip=True).lower()
                    value = _parse_number(cells[-1].get_text(strip=True))

                    if "5" in period or "five" in period:
                        if "sales" in caption_text or "revenue" in caption_text:
                            result["sales_growth_5y"] = value
                        elif "profit" in caption_text:
                            result["profit_growth_5y"] = value

        # ── Interest Coverage from profit & loss ─────────────────────────
        # This is harder to scrape directly; use approximation if available
        icr_match = re.search(r'Interest\s*Coverage[^0-9]*?(-?\d+\.?\d*)', all_text, re.I)
        if icr_match:
            result["interest_coverage"] = float(icr_match.group(1))

    except requests.exceptions.ConnectionError:
        print(f"  ⚠ Screener: Cannot connect (no internet or blocked)")
    except requests.exceptions.Timeout:
        print(f"  ⚠ Screener: Timeout for {symbol}")
    except Exception as e:
        print(f"  ⚠ Screener: Error scraping {symbol}: {e}")

    return result


def fetch_screener_data(tickers: list[str], progress_callback=None) -> dict[str, dict]:
    """
    Fetch screener data for all tickers, with caching.
    """
    conn = _get_db()
    results = {}
    to_fetch = []

    max_age_hours = CACHE_CONFIG.get("fundamental_cache_days", 7) * 24

    for ticker in tickers:
        row = conn.execute(
            "SELECT data, fetched_at FROM screener_cache WHERE ticker = ?", (ticker,)
        ).fetchone()

        if row:
            fetched_at = row[1]
            age_hours = (time.time() - fetched_at) / 3600
            if age_hours < max_age_hours:
                results[ticker] = json.loads(row[0])
                continue

        to_fetch.append(ticker)

    if to_fetch:
        total = len(to_fetch)
        for i, ticker in enumerate(to_fetch):
            if progress_callback:
                progress_callback(i / total, f"Screener: {ticker.replace('.NS', '')} ({i+1}/{total})")

            data = scrape_screener_data(ticker)
            results[ticker] = data

            conn.execute(
                "INSERT OR REPLACE INTO screener_cache (ticker, data, fetched_at) VALUES (?, ?, ?)",
                (ticker, json.dumps(data), time.time())
            )

            # Be polite to screener.in — don't hammer them
            if i < total - 1:
                time.sleep(1.5)

        conn.commit()
        if progress_callback:
            progress_callback(1.0, "Screener data loaded!")

    conn.close()
    return results


def merge_fundamentals(yf_data: dict, screener_data: dict) -> dict:
    """
    Merge yfinance fundamentals with screener.in data.
    Screener values override where available (they're more accurate for Indian stocks).
    """
    merged = {}
    for ticker in yf_data:
        base = dict(yf_data[ticker])  # Copy
        extra = screener_data.get(ticker, {})

        # Add screener-only fields
        base["roce"] = extra.get("roce")
        base["promoter_holding"] = extra.get("promoter_holding")
        base["pledged_pct"] = extra.get("pledged_pct")
        base["peg_ratio"] = extra.get("peg_ratio")
        base["interest_coverage"] = extra.get("interest_coverage")
        base["sales_growth_5y"] = extra.get("sales_growth_5y")
        base["profit_growth_5y"] = extra.get("profit_growth_5y")
        base["industry_pe"] = extra.get("industry_pe")
        base["screener_available"] = extra.get("screener_available", False)

        merged[ticker] = base

    return merged
