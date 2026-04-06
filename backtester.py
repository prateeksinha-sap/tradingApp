"""
Backtester v4 — Three-funnel, quarterly rebalance, 15-stock portfolio.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from config import BACKTEST_CONFIG, WEIGHTS_BY_TIER, ALLOCATION
from scoring import compute_technical_score, compute_fundamental_score, compute_risk_score, _get_tier


def run_backtest(price_data, fundamentals, nifty_df_for_rs=None,
                 lookback_years=None, rebalance_days=None,
                 top_n=None, initial_capital=None, progress_callback=None,
                 start_date=None, end_date=None):
    lookback_years = lookback_years or BACKTEST_CONFIG["lookback_years"]
    rebalance_days = rebalance_days or BACKTEST_CONFIG["rebalance_days"]
    top_n = top_n or BACKTEST_CONFIG["top_n"]
    initial_capital = initial_capital or BACKTEST_CONFIG["initial_capital"]

    # Find common dates
    all_dates = None
    valid = {}
    for ticker, df in price_data.items():
        if df is not None and len(df) > 100:
            valid[ticker] = df
            if all_dates is None: all_dates = set(df.index)
            else: all_dates = all_dates.intersection(set(df.index))

    if not all_dates or len(all_dates) < 50:
        return {"error": "Not enough overlapping data"}

    common = sorted(list(all_dates))

    # Timezone-safe helper
    def _ts(dt):
        ref = common[0]
        ts = pd.Timestamp(dt)
        if hasattr(ref, 'tzinfo') and ref.tzinfo is not None:
            return ts.tz_localize(ref.tzinfo) if ts.tzinfo is None else ts.tz_convert(ref.tzinfo)
        return ts.tz_localize(None) if ts.tzinfo is not None else ts

    # Apply date range — explicit dates take priority over lookback_years
    if start_date is not None:
        common = [d for d in common if d >= _ts(start_date)]
    else:
        cutoff = datetime.now() - timedelta(days=lookback_years * 365)
        common = [d for d in common if d >= _ts(cutoff)]

    if end_date is not None:
        common = [d for d in common if d <= _ts(end_date)]

    if len(common) < 50:
        return {"error": "Not enough data in the selected date range. Try widening the period."}

    capital = initial_capital
    holdings = {}
    equity_curve = []
    trades = []
    win = 0; loss = 0; returns_list = []

    start_idx = 50
    total_steps = max(1, (len(common) - start_idx) // rebalance_days)
    step = 0

    for i in range(start_idx, len(common), rebalance_days):
        date = common[i]
        if progress_callback:
            step += 1
            progress_callback(step / total_steps, f"Backtesting: {date.strftime('%Y-%m-%d')}")

        # Score stocks
        scores = []
        for ticker, full_df in valid.items():
            hist = full_df[full_df.index <= date]
            if len(hist) < 50: continue
            try:
                tier = _get_tier(ticker)
                w = WEIGHTS_BY_TIER.get(tier, WEIGHTS_BY_TIER["mid"])
                tech = compute_technical_score(hist)
                fund = compute_fundamental_score(fundamentals.get(ticker, {}), tier)
                risk = compute_risk_score(hist, fundamentals.get(ticker, {}))
                comp = (tech["technical"] * w["technical"] + fund["fundamental"] * w["fundamental"] +
                        50 * w["institutional"] + risk["risk"] * w["risk"])
                scores.append({"ticker": ticker, "tier": tier, "composite": comp, "price": hist["Close"].iloc[-1]})
            except Exception: continue

        if not scores: continue

        # Current portfolio value
        pv = capital
        for t, sh in holdings.items():
            if t in valid:
                p = valid[t][valid[t].index <= date]["Close"]
                if len(p) > 0: pv += sh * p.iloc[-1]

        # Sell all
        prev_holdings = dict(holdings)
        for t, sh in holdings.items():
            if t in valid:
                p = valid[t][valid[t].index <= date]["Close"]
                if len(p) > 0: capital += sh * p.iloc[-1]
        holdings = {}

        # Log trades from previous cycle
        if prev_holdings and len(equity_curve) > 0:
            prev_date = equity_curve[-1]["date"]
            for t, sh in prev_holdings.items():
                if t in valid:
                    bp = valid[t][valid[t].index <= prev_date]["Close"]
                    sp = valid[t][valid[t].index <= date]["Close"]
                    if len(bp) > 0 and len(sp) > 0:
                        ret = ((sp.iloc[-1] - bp.iloc[-1]) / bp.iloc[-1]) * 100
                        returns_list.append(ret)
                        if ret > 0: win += 1
                        else: loss += 1
                        trades.append({"date": str(prev_date)[:10], "exit_date": str(date)[:10],
                                       "ticker": t.replace(".NS", ""), "tier": _get_tier(t),
                                       "buy": round(bp.iloc[-1], 2), "sell": round(sp.iloc[-1], 2),
                                       "return_pct": round(ret, 2)})

        # Buy top N (spread across tiers)
        scores.sort(key=lambda x: x["composite"], reverse=True)
        picks = scores[:top_n]
        per_stock = capital / len(picks) if picks else capital

        for pick in picks:
            if pick["price"] > 0:
                sh = int(per_stock / pick["price"])
                if sh > 0:
                    holdings[pick["ticker"]] = sh
                    capital -= sh * pick["price"]

        # Record equity
        eq = capital
        for t, sh in holdings.items():
            if t in valid:
                p = valid[t][valid[t].index <= date]["Close"]
                if len(p) > 0: eq += sh * p.iloc[-1]
        equity_curve.append({"date": date, "equity": round(eq, 2),
                            "holdings": [t.replace(".NS", "") for t in holdings]})

    # Final value
    final = common[-1]
    feq = capital
    for t, sh in holdings.items():
        if t in valid:
            p = valid[t][valid[t].index <= final]["Close"]
            if len(p) > 0: feq += sh * p.iloc[-1]

    # Nifty benchmark
    try:
        import yfinance as yf
        ndf = yf.Ticker("^NSEI").history(period=f"{lookback_years + 1}y")
        if ndf.index.tzinfo is None and common and hasattr(common[0], 'tzinfo') and common[0].tzinfo:
            ndf.index = ndf.index.tz_localize(common[0].tzinfo)
        elif ndf.index.tzinfo is not None and common and (not hasattr(common[0], 'tzinfo') or common[0].tzinfo is None):
            ndf.index = ndf.index.tz_localize(None)
        ns = ndf[ndf.index >= common[start_idx]]["Close"].iloc[0]
        ne = ndf[ndf.index <= final]["Close"].iloc[-1]
        nr = ((ne - ns) / ns) * 100
        nc = []
        for ec in equity_curve:
            nd = ndf[ndf.index <= ec["date"]]["Close"]
            if len(nd) > 0:
                nc.append({"date": ec["date"], "nifty_equity": round(initial_capital * (nd.iloc[-1] / ns), 2)})
    except Exception:
        nr = None; nc = []

    # Stats
    tt = win + loss
    wr = (win / tt * 100) if tt > 0 else 0
    ar = np.mean(returns_list) if returns_list else 0
    aw = np.mean([r for r in returns_list if r > 0]) if any(r > 0 for r in returns_list) else 0
    al = np.mean([r for r in returns_list if r <= 0]) if any(r <= 0 for r in returns_list) else 0
    tr = ((feq - initial_capital) / initial_capital) * 100

    peak = initial_capital; mdd = 0
    for ec in equity_curve:
        if ec["equity"] > peak: peak = ec["equity"]
        dd = ((peak - ec["equity"]) / peak) * 100
        if dd > mdd: mdd = dd

    gp = sum(r for r in returns_list if r > 0)
    gl = abs(sum(r for r in returns_list if r <= 0))
    pf = gp / gl if gl > 0 else float('inf')

    return {"initial_capital": initial_capital, "final_equity": round(feq, 2),
            "total_return_pct": round(tr, 2),
            "nifty_return_pct": round(nr, 2) if nr else None,
            "alpha": round(tr - nr, 2) if nr else None,
            "total_trades": tt, "win_count": win, "loss_count": loss,
            "win_rate": round(wr, 1), "avg_return_per_trade": round(ar, 2),
            "avg_win": round(aw, 2), "avg_loss": round(al, 2),
            "profit_factor": round(pf, 2), "max_drawdown_pct": round(mdd, 2),
            "rebalance_count": len(equity_curve),
            "equity_curve": equity_curve, "nifty_curve": nc, "trades": trades}
