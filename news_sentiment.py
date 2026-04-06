"""
News Sentiment — NiftyScout v4
Fetches Indian market RSS headlines, filters per-stock, and scores sentiment
via a locally-running Ollama LLM. Results cached 24h in SQLite.
"""

import json
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests

from config import CACHE_CONFIG, OLLAMA_CONFIG

# ── In-memory RSS cache (refreshed every hour) ────────────────────────────────
_rss_cache: list[dict] = []
_rss_fetched_at: datetime | None = None

RSS_FEEDS = [
    ("Economic Times", "https://economictimes.indiatimes.com/markets/rss.cms"),
    ("Moneycontrol",   "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("Business Std",   "https://www.business-standard.com/rss/markets-106.rss"),
]

MACRO_KEYWORDS = [
    "rbi", "reserve bank", "fed", "federal reserve", "inflation", "crude", "oil",
    "nifty", "sensex", "gdp", "interest rate", "repo rate", "rupee", "dollar",
    "budget", "fiscal", "monsoon", "iip", "cpi", "wpi", "foreign investment", "fii", "fpi",
]

SECTOR_KEYWORDS = {
    "Technology":           ["it sector", "tech", "software", "infosys", "tcs", "wipro", "hcl"],
    "Energy":               ["oil", "gas", "energy", "petroleum", "ongc", "reliance"],
    "Healthcare":           ["pharma", "healthcare", "drug", "medicine", "hospital", "fda"],
    "Financial Services":   ["bank", "nbfc", "finance", "insurance", "credit", "npa", "loan"],
    "Consumer Defensive":   ["fmcg", "consumer", "retail", "staples"],
    "Basic Materials":      ["metal", "steel", "cement", "mining", "aluminium"],
    "Communication":        ["telecom", "5g", "broadband", "jio", "airtel"],
    "Utilities":            ["power", "electricity", "utility", "grid"],
    "Industrials":          ["manufacturing", "defence", "infrastructure", "rail"],
    "Consumer Cyclical":    ["auto", "automobile", "ev", "real estate"],
}

_NEUTRAL = {
    "score": 50, "signal": "neutral",
    "summary": "No relevant news found.",
    "key_risks": [], "key_catalysts": [], "headlines_used": [],
}
_UNAVAILABLE = {
    "score": 50, "signal": "neutral",
    "summary": "Ollama unavailable — sentiment not scored.",
    "key_risks": [], "key_catalysts": [], "headlines_used": [],
}


# ── SQLite helpers ────────────────────────────────────────────────────────────

def _db():
    conn = sqlite3.connect(CACHE_CONFIG["db_path"])
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_cache (
            ticker        TEXT PRIMARY KEY,
            score         REAL,
            signal        TEXT,
            summary       TEXT,
            key_risks     TEXT,
            key_catalysts TEXT,
            headlines_used TEXT,
            timestamp     TEXT
        )
    """)
    conn.commit()
    return conn


def get_sentiment_from_cache(ticker: str) -> dict | None:
    try:
        conn = _db()
        cutoff = (datetime.now() - timedelta(hours=OLLAMA_CONFIG["sentiment_cache_hours"])).isoformat()
        row = conn.execute(
            "SELECT score, signal, summary, key_risks, key_catalysts, headlines_used "
            "FROM sentiment_cache WHERE ticker=? AND timestamp>?",
            (ticker, cutoff)
        ).fetchone()
        conn.close()
        if row:
            return {
                "score": row[0], "signal": row[1], "summary": row[2],
                "key_risks": json.loads(row[3] or "[]"),
                "key_catalysts": json.loads(row[4] or "[]"),
                "headlines_used": json.loads(row[5] or "[]"),
            }
    except Exception:
        pass
    return None


def save_sentiment_to_cache(ticker: str, result: dict):
    try:
        conn = _db()
        conn.execute(
            "INSERT OR REPLACE INTO sentiment_cache "
            "(ticker, score, signal, summary, key_risks, key_catalysts, headlines_used, timestamp) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                ticker,
                result.get("score", 50),
                result.get("signal", "neutral"),
                result.get("summary", ""),
                json.dumps(result.get("key_risks", [])),
                json.dumps(result.get("key_catalysts", [])),
                json.dumps(result.get("headlines_used", [])),
                datetime.now().isoformat(),
            )
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def clear_sentiment_cache():
    try:
        conn = _db()
        conn.execute("DELETE FROM sentiment_cache")
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── RSS fetching ──────────────────────────────────────────────────────────────

def fetch_rss_headlines() -> list[dict]:
    """Fetch all RSS feeds, return merged headline list. Cached in memory 1h."""
    global _rss_cache, _rss_fetched_at

    if _rss_fetched_at and datetime.now() - _rss_fetched_at < timedelta(hours=1):
        return _rss_cache

    headlines = []
    for source, url in RSS_FEEDS:
        try:
            resp = requests.get(url, timeout=5, headers={"User-Agent": "NiftyScout/4.0"})
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                pub   = item.findtext("pubDate", "").strip()
                if title:
                    headlines.append({"title": title, "published": pub, "source": source})
        except Exception:
            continue

    # De-duplicate by title
    seen = set()
    unique = []
    for h in headlines:
        key = h["title"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(h)

    _rss_cache = unique
    _rss_fetched_at = datetime.now()
    return unique


def filter_headlines_for_stock(
    all_headlines: list[dict],
    ticker: str,
    company_name: str,
    sector: str,
) -> list[str]:
    """Return up to 5 headlines most relevant to this stock."""
    stub = ticker.replace(".NS", "").lower()

    # Build match tokens from company name (drop short words like Ltd, Co, etc.)
    name_tokens = [
        w.lower() for w in company_name.split()
        if len(w) > 3 and w.lower() not in {"ltd", "limited", "corp", "corporation", "india", "and", "the"}
    ]
    sector_kws = SECTOR_KEYWORDS.get(sector, [])

    scored = []
    for h in all_headlines:
        t = h["title"].lower()
        score = 0
        if stub in t:
            score += 3
        for tok in name_tokens:
            if tok in t:
                score += 2
                break
        for kw in sector_kws:
            if kw in t:
                score += 1
                break
        if score > 0:
            scored.append((score, h["title"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    specific = [t for _, t in scored[:OLLAMA_CONFIG["max_headlines_per_stock"]]]

    if not specific:
        # Fall back to top general market headlines
        specific = [h["title"] for h in all_headlines[:OLLAMA_CONFIG["max_headlines_per_stock"]]]

    return specific


def fetch_macro_headlines(all_headlines: list[dict]) -> list[str]:
    """Return up to 5 macro/market-wide headlines."""
    macro = [
        h["title"] for h in all_headlines
        if any(kw in h["title"].lower() for kw in MACRO_KEYWORDS)
    ]
    return macro[:5] or [h["title"] for h in all_headlines[:5]]


# ── Ollama integration ────────────────────────────────────────────────────────

def is_ollama_running() -> bool:
    if not OLLAMA_CONFIG.get("enabled", True):
        return False
    try:
        r = requests.get(OLLAMA_CONFIG["host"] + "/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _call_ollama(prompt: str) -> dict:
    try:
        resp = requests.post(
            OLLAMA_CONFIG["host"] + "/api/generate",
            json={
                "model": OLLAMA_CONFIG["model"],
                "prompt": prompt,
                "format": "json",
                "stream": False,
            },
            timeout=30,
        )
        raw = resp.json().get("response", "{}")
        result = json.loads(raw)
        # Normalise score
        result["score"] = max(0, min(100, int(result.get("score", 50))))
        result["signal"] = result.get("signal", "neutral").lower()
        if result["signal"] not in ("bullish", "bearish", "neutral"):
            result["signal"] = "neutral"
        return result
    except Exception:
        return _UNAVAILABLE.copy()


def analyze_stock_sentiment(
    ticker: str,
    company_name: str,
    sector: str,
    headlines: list[str],
) -> dict:
    if not headlines:
        return {**_NEUTRAL, "headlines_used": []}

    numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))
    prompt = (
        f"You are a financial analyst specialising in Indian equity markets.\n"
        f"Analyze these recent news headlines for {company_name} ({ticker.replace('.NS','')}), "
        f"a {sector} company listed on NSE India.\n\n"
        f"Headlines:\n{numbered}\n\n"
        f"Rate the overall news sentiment from 0 (extremely bearish) to 100 (extremely bullish). "
        f"Use 50 when news is neutral or not stock-specific.\n"
        f"Return ONLY valid JSON with these exact keys:\n"
        f'{{"score": <int 0-100>, "signal": "<bullish|neutral|bearish>", '
        f'"summary": "<one sentence>", "key_risks": ["..."], "key_catalysts": ["..."]}}'
    )

    result = _call_ollama(prompt)
    result["headlines_used"] = headlines
    return result


# ── Batch runner ──────────────────────────────────────────────────────────────

def fetch_sentiment_batch(
    tickers: list[str],
    fundamentals: dict,
    progress_callback=None,
) -> dict[str, dict]:
    """
    Run sentiment analysis for a list of tickers.
    Checks cache first; calls Ollama only for cache misses.
    Returns {ticker: sentiment_dict}.
    """
    all_headlines = fetch_rss_headlines()
    results = {}
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        if progress_callback:
            progress_callback(i / total, f"Sentiment: {ticker.replace('.NS', '')}")

        # Cache hit
        cached = get_sentiment_from_cache(ticker)
        if cached:
            results[ticker] = cached
            continue

        # Ollama call
        fund = fundamentals.get(ticker, {})
        company_name = fund.get("short_name", ticker.replace(".NS", ""))
        sector = fund.get("sector", "")
        headlines = filter_headlines_for_stock(all_headlines, ticker, company_name, sector)
        result = analyze_stock_sentiment(ticker, company_name, sector, headlines)
        save_sentiment_to_cache(ticker, result)
        results[ticker] = result

        # Polite delay between Ollama calls
        time.sleep(0.3)

    if progress_callback:
        progress_callback(1.0, "Sentiment complete!")

    return results


def get_cached_sentiment_all() -> dict[str, dict]:
    """Load all non-expired cached sentiment entries (for table display)."""
    try:
        conn = _db()
        cutoff = (datetime.now() - timedelta(hours=OLLAMA_CONFIG["sentiment_cache_hours"])).isoformat()
        rows = conn.execute(
            "SELECT ticker, score, signal, summary, key_risks, key_catalysts, headlines_used "
            "FROM sentiment_cache WHERE timestamp>?",
            (cutoff,)
        ).fetchall()
        conn.close()
        return {
            row[0]: {
                "score": row[1], "signal": row[2], "summary": row[3],
                "key_risks": json.loads(row[4] or "[]"),
                "key_catalysts": json.loads(row[5] or "[]"),
                "headlines_used": json.loads(row[6] or "[]"),
            }
            for row in rows
        }
    except Exception:
        return {}
