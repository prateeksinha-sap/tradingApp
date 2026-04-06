"""
Performance Tracker
Tracks active positions, monitors for target/stop-loss hits, logs results.
"""

import sqlite3
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

from config import CACHE_CONFIG


def _get_db():
    db_path = Path(CACHE_CONFIG["db_path"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=15)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS active_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            name TEXT,
            entry_date TEXT,
            entry_price REAL,
            stop_loss REAL,
            target_1 REAL,
            target_2 REAL,
            shares INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            exit_date TEXT,
            exit_price REAL,
            exit_reason TEXT,
            return_pct REAL,
            notes TEXT
        )
    """)
    conn.commit()
    return conn


def add_position(ticker: str, name: str, entry_price: float,
                 stop_loss: float, target_1: float, target_2: float,
                 shares: int = 0, notes: str = "") -> int:
    """Add a new tracked position. Returns the position ID."""
    conn = _get_db()
    cursor = conn.execute(
        """INSERT INTO active_positions
           (ticker, name, entry_date, entry_price, stop_loss, target_1, target_2, shares, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, name, datetime.now().strftime("%Y-%m-%d"),
         entry_price, stop_loss, target_1, target_2, shares, notes)
    )
    conn.commit()
    pid = cursor.lastrowid
    conn.close()
    return pid


def close_position(position_id: int, exit_price: float, exit_reason: str):
    """Close a position with exit details."""
    conn = _get_db()
    row = conn.execute(
        "SELECT entry_price FROM active_positions WHERE id = ?", (position_id,)
    ).fetchone()

    if row:
        entry_price = row[0]
        return_pct = ((exit_price - entry_price) / entry_price) * 100

        conn.execute(
            """UPDATE active_positions
               SET status = 'closed', exit_date = ?, exit_price = ?,
                   exit_reason = ?, return_pct = ?
               WHERE id = ?""",
            (datetime.now().strftime("%Y-%m-%d"), exit_price,
             exit_reason, round(return_pct, 2), position_id)
        )
        conn.commit()
    conn.close()


def get_active_positions() -> list[dict]:
    """Get all currently active (open) positions."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM active_positions WHERE status = 'active' ORDER BY entry_date DESC"
    ).fetchall()
    conn.close()

    columns = ["id", "ticker", "name", "entry_date", "entry_price",
               "stop_loss", "target_1", "target_2", "shares",
               "status", "exit_date", "exit_price", "exit_reason",
               "return_pct", "notes"]

    return [dict(zip(columns, row)) for row in rows]


def get_closed_positions(days: int = 90) -> list[dict]:
    """Get recently closed positions."""
    conn = _get_db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT * FROM active_positions
           WHERE status = 'closed' AND exit_date >= ?
           ORDER BY exit_date DESC""",
        (cutoff,)
    ).fetchall()
    conn.close()

    columns = ["id", "ticker", "name", "entry_date", "entry_price",
               "stop_loss", "target_1", "target_2", "shares",
               "status", "exit_date", "exit_price", "exit_reason",
               "return_pct", "notes"]

    return [dict(zip(columns, row)) for row in rows]


def check_positions_against_prices() -> list[dict]:
    """
    Check all active positions against current prices.
    Returns list of alerts (target hit, stop loss hit, etc.)
    """
    positions = get_active_positions()
    alerts = []

    for pos in positions:
        ticker = pos["ticker"]
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if hist is None or len(hist) == 0:
                continue

            current_price = hist["Close"].iloc[-1]
            high_today = hist["High"].iloc[-1]
            low_today = hist["Low"].iloc[-1]

            entry = pos["entry_price"]
            pnl_pct = ((current_price - entry) / entry) * 100
            days_held = (datetime.now() - datetime.strptime(pos["entry_date"], "%Y-%m-%d")).days

            alert = {
                "position_id": pos["id"],
                "ticker": ticker.replace(".NS", ""),
                "name": pos["name"],
                "entry_price": entry,
                "current_price": round(current_price, 2),
                "pnl_pct": round(pnl_pct, 2),
                "days_held": days_held,
                "shares": pos["shares"],
                "alert_type": None,
                "alert_message": "",
            }

            # Check stop loss
            if low_today <= pos["stop_loss"]:
                alert["alert_type"] = "stop_loss_hit"
                alert["alert_message"] = f"⛔ STOP LOSS HIT at ₹{pos['stop_loss']:,.2f}"

            # Check target 2
            elif high_today >= pos["target_2"]:
                alert["alert_type"] = "target_2_hit"
                alert["alert_message"] = f"🎯🎯 TARGET 2 HIT at ₹{pos['target_2']:,.2f} — Book full profits!"

            # Check target 1
            elif high_today >= pos["target_1"]:
                alert["alert_type"] = "target_1_hit"
                alert["alert_message"] = f"🎯 TARGET 1 HIT at ₹{pos['target_1']:,.2f} — Consider booking 50%"

            # Trailing check - warn if approaching stop loss
            elif current_price < entry * 0.95:
                alert["alert_type"] = "warning"
                alert["alert_message"] = f"⚠️ Down {pnl_pct:.1f}% — approaching stop loss"

            # Healthy position
            else:
                alert["alert_type"] = "ok"
                alert["alert_message"] = f"{'📈' if pnl_pct > 0 else '📉'} {pnl_pct:+.1f}% ({days_held}d)"

            alerts.append(alert)

        except Exception as e:
            alerts.append({
                "ticker": ticker.replace(".NS", ""),
                "name": pos["name"],
                "alert_type": "error",
                "alert_message": f"Could not fetch price: {e}",
            })

    return alerts


def get_performance_summary() -> dict:
    """Calculate overall trading performance stats."""
    conn = _get_db()
    closed = conn.execute(
        "SELECT return_pct, exit_reason FROM active_positions WHERE status = 'closed'"
    ).fetchall()
    active_count = conn.execute(
        "SELECT COUNT(*) FROM active_positions WHERE status = 'active'"
    ).fetchone()[0]
    conn.close()

    if not closed:
        return {
            "total_trades": 0,
            "active_count": active_count,
            "win_rate": 0,
            "avg_return": 0,
            "total_return": 0,
        }

    returns = [r[0] for r in closed if r[0] is not None]
    reasons = [r[1] for r in closed if r[1] is not None]

    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    t1_hits = reasons.count("target_1_hit")
    t2_hits = reasons.count("target_2_hit")
    sl_hits = reasons.count("stop_loss_hit")

    return {
        "total_trades": len(returns),
        "active_count": active_count,
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / len(returns) * 100, 1) if returns else 0,
        "avg_return": round(sum(returns) / len(returns), 2) if returns else 0,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "best_trade": round(max(returns), 2) if returns else 0,
        "worst_trade": round(min(returns), 2) if returns else 0,
        "total_return": round(sum(returns), 2),
        "target_1_hits": t1_hits,
        "target_2_hits": t2_hits,
        "stop_loss_hits": sl_hits,
    }
