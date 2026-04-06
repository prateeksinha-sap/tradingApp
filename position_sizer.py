"""
Position Sizer & Market Regime Detector
Calculates how much to buy and when to be cautious.
"""

import numpy as np
import pandas as pd

from config import POSITION_CONFIG


# ═══════════════════════════════════════════════════════════════════════════════
# POSITION SIZING
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_position_size(
    capital: float,
    entry_price: float,
    stop_loss: float,
    risk_per_trade_pct: float = None,
    max_position_pct: float = None,
) -> dict:
    """
    Calculate position size using the risk-based method.

    Logic:
    1. Max risk per trade = capital × risk_per_trade_pct
    2. Risk per share = entry_price - stop_loss
    3. Shares = max_risk / risk_per_share
    4. Cap at max_position_pct of capital
    """
    risk_pct = risk_per_trade_pct or POSITION_CONFIG["risk_per_trade_pct"]
    max_pos_pct = max_position_pct or POSITION_CONFIG["max_position_pct"]

    max_risk_amount = capital * (risk_pct / 100)
    max_position_amount = capital * (max_pos_pct / 100)

    risk_per_share = entry_price - stop_loss
    if risk_per_share <= 0:
        risk_per_share = entry_price * 0.05  # Default 5% if SL is bad

    # Shares based on risk
    shares_by_risk = int(max_risk_amount / risk_per_share)

    # Shares based on max position size
    shares_by_position = int(max_position_amount / entry_price)

    # Take the smaller (more conservative)
    shares = min(shares_by_risk, shares_by_position)
    shares = max(1, shares)  # At least 1 share

    investment = shares * entry_price
    risk_amount = shares * risk_per_share
    position_pct = (investment / capital) * 100

    return {
        "shares": shares,
        "investment": round(investment, 2),
        "risk_amount": round(risk_amount, 2),
        "position_pct": round(position_pct, 1),
        "risk_pct_of_capital": round((risk_amount / capital) * 100, 2),
        "entry_price": entry_price,
        "stop_loss": stop_loss,
    }


def size_portfolio(picks: list[dict], capital: float,
                   risk_per_trade_pct: float = None,
                   max_position_pct: float = None) -> list[dict]:
    """
    Size positions for all top picks.
    Returns list of picks with position sizing info.
    """
    results = []
    remaining_capital = capital
    num_picks = len(picks)

    for pick in picks:
        exit_info = pick.get("exit", {})
        entry = exit_info.get("entry_price", pick.get("current_price", 0))
        sl = exit_info.get("stop_loss", entry * 0.92)

        if entry <= 0 or remaining_capital <= 0:
            continue

        # Adjust max position to spread across picks
        adjusted_max = min(
            max_position_pct or POSITION_CONFIG["max_position_pct"],
            100 / num_picks * 1.2  # Slight over-allocation allowed
        )

        sizing = calculate_position_size(
            capital=remaining_capital,
            entry_price=entry,
            stop_loss=sl,
            risk_per_trade_pct=risk_per_trade_pct,
            max_position_pct=adjusted_max,
        )

        results.append({
            **pick,
            "sizing": sizing,
        })

        remaining_capital -= sizing["investment"]

    cash_remaining = max(0, remaining_capital)
    return results, round(cash_remaining, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# MARKET REGIME DETECTOR
# ═══════════════════════════════════════════════════════════════════════════════

def detect_market_regime(nifty_df: pd.DataFrame, vix_df: pd.DataFrame) -> dict:
    """
    Determine current market regime based on:
    - Nifty trend (above/below 200 DMA)
    - Nifty momentum (20-day return)
    - India VIX level
    - Recent drawdown from highs

    Returns regime info with trading recommendations.
    """
    regime = {
        "name": "Unknown",
        "color": "gray",
        "emoji": "❓",
        "recommendation": "",
        "position_size_multiplier": 1.0,
        "signals": [],
    }

    if nifty_df is None or len(nifty_df) < 50:
        return regime

    close = nifty_df["Close"]
    current = close.iloc[-1]

    # Nifty vs 200 DMA
    sma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.rolling(50).mean().iloc[-1]
    above_200 = current > sma_200
    pct_from_200 = ((current - sma_200) / sma_200) * 100

    # Nifty 20-day return
    if len(close) > 20:
        ret_20d = ((current - close.iloc[-20]) / close.iloc[-20]) * 100
    else:
        ret_20d = 0

    # Nifty drawdown from 52w high
    high_52w = close.tail(252).max() if len(close) >= 252 else close.max()
    drawdown = ((high_52w - current) / high_52w) * 100

    # VIX level
    vix = vix_df["Close"].iloc[-1] if vix_df is not None and len(vix_df) > 0 else 15

    # Signals
    signals = []
    fear_score = 0  # Higher = more fearful

    if above_200:
        signals.append(("Nifty above 200 DMA", "bullish"))
    else:
        signals.append(("Nifty below 200 DMA", "bearish"))
        fear_score += 2

    if ret_20d > 3:
        signals.append((f"Strong 20D momentum ({ret_20d:+.1f}%)", "bullish"))
    elif ret_20d < -3:
        signals.append((f"Weak 20D momentum ({ret_20d:+.1f}%)", "bearish"))
        fear_score += 1

    if drawdown > 15:
        signals.append((f"Deep correction (-{drawdown:.0f}% from high)", "bearish"))
        fear_score += 2
    elif drawdown > 8:
        signals.append((f"Moderate pullback (-{drawdown:.0f}% from high)", "cautious"))
        fear_score += 1

    if vix > 25:
        signals.append((f"VIX elevated ({vix:.0f}) — High fear", "bearish"))
        fear_score += 2
    elif vix > 18:
        signals.append((f"VIX moderate ({vix:.0f})", "cautious"))
        fear_score += 1
    else:
        signals.append((f"VIX calm ({vix:.0f})", "bullish"))

    # Determine regime
    if fear_score >= 5:
        regime = {
            "name": "Crisis / High Fear",
            "color": "#ef4444",
            "emoji": "🔴",
            "recommendation": "Reduce position sizes to 50%. Focus only on stocks that pass the quality gate. Consider sitting out if VIX > 30.",
            "position_size_multiplier": 0.5,
            "signals": signals,
            "vix": vix,
            "nifty_vs_200dma": round(pct_from_200, 1),
            "drawdown": round(drawdown, 1),
        }
    elif fear_score >= 3:
        regime = {
            "name": "Cautious / Correction",
            "color": "#f59e0b",
            "emoji": "🟡",
            "recommendation": "Reduce position sizes to 75%. Prefer low-beta, high-ROCE stocks. Tighten stop losses.",
            "position_size_multiplier": 0.75,
            "signals": signals,
            "vix": vix,
            "nifty_vs_200dma": round(pct_from_200, 1),
            "drawdown": round(drawdown, 1),
        }
    elif fear_score <= 1 and above_200:
        regime = {
            "name": "Bullish / Risk-On",
            "color": "#22c55e",
            "emoji": "🟢",
            "recommendation": "Full position sizes. Momentum and growth stocks favored. Let winners run.",
            "position_size_multiplier": 1.0,
            "signals": signals,
            "vix": vix,
            "nifty_vs_200dma": round(pct_from_200, 1),
            "drawdown": round(drawdown, 1),
        }
    else:
        regime = {
            "name": "Neutral / Mixed",
            "color": "#6366f1",
            "emoji": "🔵",
            "recommendation": "Normal position sizes. Balanced approach — mix of value and momentum.",
            "position_size_multiplier": 0.85,
            "signals": signals,
            "vix": vix,
            "nifty_vs_200dma": round(pct_from_200, 1),
            "drawdown": round(drawdown, 1),
        }

    return regime
