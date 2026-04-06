"""
Data Fetcher
Downloads price data via yfinance, caches in SQLite.
"""

import sqlite3
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from config import NIFTY_50_TICKERS, TECH_CONFIG, CACHE_CONFIG


def _get_db():
    """Get SQLite connection, create tables if needed."""
    db_path = Path(CACHE_CONFIG["db_path"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_cache (
            ticker TEXT PRIMARY KEY,
            data TEXT,
            fetched_at REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fundamental_cache (
            ticker TEXT PRIMARY KEY,
            data TEXT,
            fetched_at REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS picks_log (
            date TEXT,
            rank INTEGER,
            ticker TEXT,
            composite_score REAL,
            technical_score REAL,
            fundamental_score REAL,
            institutional_score REAL,
            risk_score REAL,
            PRIMARY KEY (date, rank)
        )
    """)
    conn.commit()
    return conn


def _is_cache_valid(fetched_at: float, max_age_hours: float) -> bool:
    if fetched_at is None:
        return False
    age_hours = (time.time() - fetched_at) / 3600
    return age_hours < max_age_hours


def fetch_price_data(tickers: list[str] = None, progress_callback=None) -> dict[str, pd.DataFrame]:
    """
    Fetch OHLCV data for all tickers. Uses cache if fresh enough.
    Returns dict of {ticker: DataFrame}.
    """
    tickers = tickers or NIFTY_50_TICKERS
    conn = _get_db()
    results = {}
    to_fetch = []

    # Check cache
    for ticker in tickers:
        row = conn.execute(
            "SELECT data, fetched_at FROM price_cache WHERE ticker = ?", (ticker,)
        ).fetchone()
        if row and _is_cache_valid(row[1], CACHE_CONFIG["price_cache_hours"]):
            df = pd.read_json(row[0], orient="split")
            df.index = pd.to_datetime(df.index)
            results[ticker] = df
        else:
            to_fetch.append(ticker)

    # Fetch missing tickers
    if to_fetch:
        lookback = TECH_CONFIG["lookback_days"]
        end_date = datetime.now()
        start_date = end_date - timedelta(days=int(lookback * 1.6))  # Extra buffer for weekends/holidays

        total = len(to_fetch)
        for i, ticker in enumerate(to_fetch):
            if progress_callback:
                progress_callback(i / total, f"Fetching {ticker.replace('.NS', '')} ({i+1}/{total})")
            try:
                stock = yf.Ticker(ticker)
                df = stock.history(start=start_date.strftime("%Y-%m-%d"),
                                   end=end_date.strftime("%Y-%m-%d"))
                if df is not None and len(df) > 20:
                    # Clean columns
                    df = df[["Open", "High", "Low", "Close", "Volume"]]
                    results[ticker] = df

                    # Cache it
                    conn.execute(
                        "INSERT OR REPLACE INTO price_cache (ticker, data, fetched_at) VALUES (?, ?, ?)",
                        (ticker, df.to_json(orient="split", date_format="iso"), time.time())
                    )
            except Exception as e:
                print(f"  ⚠ Failed to fetch {ticker}: {e}")

        conn.commit()
        if progress_callback:
            progress_callback(1.0, "Price data loaded!")

    conn.close()
    return results


def fetch_fundamentals(tickers: list[str] = None, progress_callback=None) -> dict[str, dict]:
    """
    Fetch fundamental data via yfinance .info.
    Cached for CACHE_CONFIG['fundamental_cache_days'] days.
    """
    tickers = tickers or NIFTY_50_TICKERS
    conn = _get_db()
    results = {}
    to_fetch = []

    max_age_hours = CACHE_CONFIG["fundamental_cache_days"] * 24

    for ticker in tickers:
        row = conn.execute(
            "SELECT data, fetched_at FROM fundamental_cache WHERE ticker = ?", (ticker,)
        ).fetchone()
        if row and _is_cache_valid(row[1], max_age_hours):
            results[ticker] = json.loads(row[0])
        else:
            to_fetch.append(ticker)

    if to_fetch:
        total = len(to_fetch)
        for i, ticker in enumerate(to_fetch):
            if progress_callback:
                progress_callback(i / total, f"Fundamentals: {ticker.replace('.NS', '')} ({i+1}/{total})")
            try:
                stock = yf.Ticker(ticker)
                info = stock.info or {}

                fundamentals = {
                    "pe_trailing":      info.get("trailingPE"),
                    "pe_forward":       info.get("forwardPE"),
                    "pb_ratio":         info.get("priceToBook"),
                    "debt_to_equity":   info.get("debtToEquity"),
                    "roe":              info.get("returnOnEquity"),
                    "revenue_growth":   info.get("revenueGrowth"),
                    "earnings_growth":  info.get("earningsGrowth"),
                    "market_cap":       info.get("marketCap"),
                    "dividend_yield":   info.get("dividendYield"),
                    "52w_high":         info.get("fiftyTwoWeekHigh"),
                    "52w_low":          info.get("fiftyTwoWeekLow"),
                    "beta":             info.get("beta"),
                    "sector":           info.get("sector"),
                    "industry":         info.get("industry"),
                    "short_name":       info.get("shortName", ticker.replace(".NS", "")),
                }
                results[ticker] = fundamentals

                conn.execute(
                    "INSERT OR REPLACE INTO fundamental_cache (ticker, data, fetched_at) VALUES (?, ?, ?)",
                    (ticker, json.dumps(fundamentals), time.time())
                )
            except Exception as e:
                print(f"  ⚠ Failed fundamentals for {ticker}: {e}")
                results[ticker] = {"short_name": ticker.replace(".NS", "")}

        conn.commit()
        if progress_callback:
            progress_callback(1.0, "Fundamentals loaded!")

    conn.close()
    return results


def fetch_nifty_index() -> pd.DataFrame:
    """Fetch Nifty 50 index data for market context.
    Uses fast_info for the latest price to avoid yfinance history() lag."""
    try:
        nifty = yf.Ticker("^NSEI")
        df = nifty.history(period="3mo")
        df = df[["Open", "High", "Low", "Close", "Volume"]]

        # Patch: yfinance history() sometimes lags by a day for Indian indices.
        # Use fast_info/info to get the real latest price and append it if missing.
        try:
            info = nifty.info
            live_price = info.get("regularMarketPrice")
            prev_close = info.get("previousClose") or info.get("chartPreviousClose")
            market_time = info.get("regularMarketTime")

            if live_price and len(df) > 0:
                last_hist_close = df["Close"].iloc[-1]
                # If the API has a newer price than history(), patch it in
                if abs(live_price - last_hist_close) > 10:
                    # Build a row for the latest trading day
                    from datetime import datetime as dt
                    import pytz
                    if market_time:
                        latest_date = pd.Timestamp(dt.fromtimestamp(market_time,
                                        tz=pytz.timezone("Asia/Kolkata"))).normalize()
                    else:
                        latest_date = pd.Timestamp.now(tz="Asia/Kolkata").normalize()

                    new_row = pd.DataFrame({
                        "Open": [info.get("regularMarketOpen", live_price)],
                        "High": [info.get("regularMarketDayHigh", live_price)],
                        "Low": [info.get("regularMarketDayLow", live_price)],
                        "Close": [live_price],
                        "Volume": [info.get("regularMarketVolume", 0)],
                    }, index=[latest_date])

                    # Only append if this date isn't already in the dataframe
                    if latest_date not in df.index:
                        df = pd.concat([df, new_row])
                    else:
                        # Update the existing row with fresh data
                        df.loc[latest_date, "Close"] = live_price
                        if info.get("regularMarketDayHigh"):
                            df.loc[latest_date, "High"] = info["regularMarketDayHigh"]
                        if info.get("regularMarketDayLow"):
                            df.loc[latest_date, "Low"] = info["regularMarketDayLow"]
        except Exception:
            pass  # Fall back to history() data if info fails

        return df
    except Exception:
        return pd.DataFrame()


def fetch_india_vix() -> pd.DataFrame:
    """Fetch India VIX for market fear gauge."""
    try:
        vix = yf.Ticker("^INDIAVIX")
        df = vix.history(period="1mo")
        result = df[["Close"]]

        # Same patch: try to get latest VIX from info
        try:
            info = vix.info
            live_vix = info.get("regularMarketPrice")
            if live_vix and len(result) > 0:
                if abs(live_vix - result["Close"].iloc[-1]) > 0.5:
                    latest_date = pd.Timestamp.now(tz="Asia/Kolkata").normalize()
                    if latest_date not in result.index:
                        new_row = pd.DataFrame({"Close": [live_vix]}, index=[latest_date])
                        result = pd.concat([result, new_row])
                    else:
                        result.loc[latest_date, "Close"] = live_vix
        except Exception:
            pass

        return result
    except Exception:
        return pd.DataFrame()


def log_picks(picks: list[dict]):
    """Save today's picks to the database for historical tracking."""
    conn = _get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    for i, pick in enumerate(picks):
        conn.execute(
            """INSERT OR REPLACE INTO picks_log
               (date, rank, ticker, composite_score, technical_score,
                fundamental_score, institutional_score, risk_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (today, i + 1, pick["ticker"], pick["composite"],
             pick["technical"], pick["fundamental"],
             pick["institutional"], pick["risk"])
        )
    conn.commit()
    conn.close()


def get_picks_history(days: int = 30) -> pd.DataFrame:
    """Retrieve past picks from the database."""
    conn = _get_db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql_query(
        "SELECT * FROM picks_log WHERE date >= ? ORDER BY date DESC, rank ASC",
        conn, params=(cutoff,)
    )
    conn.close()
    return df
