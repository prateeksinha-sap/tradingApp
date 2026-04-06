"""
Scoring Engine v4 — Three-Funnel Alpha Engine
"""
import numpy as np
import pandas as pd
import pandas_ta as ta

from config import (
    TECH_CONFIG, FUND_CONFIG, RISK_CONFIG,
    WEIGHTS_LARGE, WEIGHTS_MID, WEIGHTS_SMALL,
    FUND_WEIGHTS_LARGE, FUND_WEIGHTS_MID, FUND_WEIGHTS_SMALL,
    LARGE_CAP_TICKERS, MID_CAP_TICKERS, SMALL_CAP_TICKERS,
    PORTFOLIO_CONFIG, SECTOR_ROCE_BENCHMARKS,
)

def _clamp(val, lo=0, hi=100):
    if val is None or (isinstance(val, float) and np.isnan(val)): return 50
    return max(lo, min(hi, val))

def _get_funnel(ticker):
    if ticker in LARGE_CAP_TICKERS: return "large"
    elif ticker in MID_CAP_TICKERS: return "mid"
    return "small"

_get_tier = _get_funnel  # alias used by backtester

def _get_weights(funnel):
    return {"large": WEIGHTS_LARGE, "mid": WEIGHTS_MID, "small": WEIGHTS_SMALL}.get(funnel, WEIGHTS_MID)

def _get_fund_weights(funnel):
    return {"large": FUND_WEIGHTS_LARGE, "mid": FUND_WEIGHTS_MID, "small": FUND_WEIGHTS_SMALL}.get(funnel, FUND_WEIGHTS_MID)

# ═══════════════════════════════════════════════════════════════════════════════
# TECHNICAL
# ═══════════════════════════════════════════════════════════════════════════════
def compute_technical_score(df, nifty_df=None):
    if df is None or len(df) < 50:
        return {"technical": 50, "rsi": None, "macd_signal": None, "ma_crossover": None,
                "above_200dma": None, "sma_200": None, "volume_ratio": None,
                "pct_from_200dma": None, "dma_200_score": 50, "rsi_score": 50,
                "macd_score": 50, "ma_score": 50, "volume_score": 50}
    close = df["Close"]; volume = df["Volume"]

    # RSI
    rsi_s = ta.rsi(close, length=14)
    rsi = rsi_s.iloc[-1] if rsi_s is not None and len(rsi_s) > 0 else 50
    lo, hi = TECH_CONFIG["rsi_sweet_spot"]
    if lo <= rsi <= hi: rsi_sc = 80 + (20 * (1 - abs(rsi - 52.5) / 22.5))
    elif rsi < 30: rsi_sc = 70
    elif rsi > 70: rsi_sc = 20
    else: rsi_sc = 50

    # MACD
    md = ta.macd(close, fast=12, slow=26, signal=9)
    if md is not None and len(md) > 1:
        ml = md.iloc[-1, 0]; sl = md.iloc[-1, 2]; h = md.iloc[-1, 1]; ph = md.iloc[-2, 1]
        if ml > sl and h > ph: macd_sc = 90
        elif ml > sl: macd_sc = 70
        elif h > ph: macd_sc = 60
        else: macd_sc = 30
        macd_sig = "bullish" if ml > sl else "bearish"
    else: macd_sc = 50; macd_sig = "neutral"

    # MA cross
    s20 = ta.sma(close, 20); s50 = ta.sma(close, 50)
    if s20 is not None and s50 is not None and len(s20) > 1 and len(s50) > 1:
        ab = s20.iloc[-1] > s50.iloc[-1]; pr = s20.iloc[-2] > s50.iloc[-2]
        if ab and not pr: ma_sc = 95
        elif ab: ma_sc = 75
        elif not ab and pr: ma_sc = 15
        else: ma_sc = 35
        ma_cross = "bullish" if ab else "bearish"
    else: ma_sc = 50; ma_cross = "neutral"

    # 200 DMA
    sma200 = None; above200 = None; dma_sc = 50; pct200 = None
    if len(close) >= 200:
        s200 = ta.sma(close, 200)
        if s200 is not None and len(s200) > 0:
            sma200 = round(s200.iloc[-1], 2); c = close.iloc[-1]
            above200 = c > sma200; pct200 = ((c - sma200) / sma200) * 100
            if above200 and pct200 < 10: dma_sc = 90
            elif above200 and pct200 < 20: dma_sc = 75
            elif above200: dma_sc = 55
            elif pct200 > -5: dma_sc = 45
            else: dma_sc = 20

    # Volume
    avg_v = volume.rolling(20).mean().iloc[-1]; cur_v = volume.iloc[-1]
    if avg_v and avg_v > 0:
        vr = cur_v / avg_v
        if vr >= 1.5: vol_sc = min(95, 60 + (vr - 1) * 30)
        elif vr >= 1.0: vol_sc = 60
        else: vol_sc = 30
    else: vr = 1.0; vol_sc = 50

    # Relative Strength vs Nifty — blended 3-month (40%) + 12-month (60%)
    # 3-month captures recent momentum; 12-month rewards persistent compounders.
    rs_3m = None; rs_12m = None; rs_sc = 50
    if nifty_df is not None:
        nc = nifty_df["Close"]
        try:
            if len(close) >= 63 and len(nc) >= 63:
                sr_3m = (close.iloc[-1] / close.iloc[-63] - 1) * 100
                nr_3m = (nc.iloc[-1]   / nc.iloc[-63]   - 1) * 100
                rs_3m = sr_3m - nr_3m

            if len(close) >= 252 and len(nc) >= 252:
                sr_12m = (close.iloc[-1] / close.iloc[-252] - 1) * 100
                nr_12m = (nc.iloc[-1]   / nc.iloc[-252]   - 1) * 100
                rs_12m = sr_12m - nr_12m
        except: pass

        def _rs_to_score(rs_val):
            if rs_val > 15: return 95
            elif rs_val > 8:  return 80
            elif rs_val > 2:  return 65
            elif rs_val > -2: return 50
            elif rs_val > -8: return 35
            else:             return 15

        if rs_3m is not None and rs_12m is not None:
            # Full blend: 40% short-term momentum + 60% long-term persistence
            rs_sc = _rs_to_score(rs_3m) * 0.4 + _rs_to_score(rs_12m) * 0.6
        elif rs_3m is not None:
            # Younger stocks with < 1 year of history: use 3-month only
            rs_sc = _rs_to_score(rs_3m)

    tech = rsi_sc * 0.20 + macd_sc * 0.20 + ma_sc * 0.20 + dma_sc * 0.25 + vol_sc * 0.15

    return {
        "technical": round(_clamp(tech), 1), "relative_str": round(_clamp(rs_sc), 1),
        "rs_3m":  round(rs_3m,  1) if rs_3m  is not None else None,
        "rs_12m": round(rs_12m, 1) if rs_12m is not None else None,
        "rsi": round(rsi, 1), "rsi_score": round(rsi_sc, 1),
        "macd_signal": macd_sig, "macd_score": round(macd_sc, 1),
        "ma_crossover": ma_cross, "ma_score": round(ma_sc, 1),
        "sma_200": sma200, "above_200dma": above200,
        "pct_from_200dma": round(pct200, 1) if pct200 is not None else None,
        "dma_200_score": round(dma_sc, 1),
        "volume_ratio": round(vr, 2), "volume_score": round(vol_sc, 1),
    }

# ═══════════════════════════════════════════════════════════════════════════════
# FUNDAMENTAL (funnel-aware weights)
# ═══════════════════════════════════════════════════════════════════════════════
def compute_fundamental_score(fundamentals, funnel="mid", use_lynch=True):
    fw = _get_fund_weights(funnel)
    nifty_pe = FUND_CONFIG.get("nifty_pe_avg", 22)

    pe = fundamentals.get("pe_trailing") or fundamentals.get("pe_forward")
    ipe = fundamentals.get("industry_pe")
    if pe and pe > 0 and ipe and ipe > 0: pe_ratio = pe / ipe; pe_label = "vs Industry"
    elif pe and pe > 0: pe_ratio = pe / nifty_pe; pe_label = "vs Market"
    else: pe_ratio = None; pe_label = "N/A"
    pe_rel_sc = (95 if pe_ratio < 0.6 else (80 if pe_ratio < 0.85 else (60 if pe_ratio < 1.15 else (35 if pe_ratio < 1.5 else 15)))) if pe_ratio else 40

    peg = fundamentals.get("peg_ratio")
    peg_sc = (95 if peg < 0.8 else (85 if peg < 1.0 else (65 if peg < 1.5 else (40 if peg < 2.0 else 15)))) if (peg and peg > 0) else 50

    roce = fundamentals.get("roce")
    sector = (fundamentals.get("sector") or "").strip()
    _roce_benchmark = SECTOR_ROCE_BENCHMARKS.get(sector)  # None → use absolute fallback
    # TODO: Replace SECTOR_ROCE_BENCHMARKS with dynamically scraped industry-average
    # ROCE values from Screener.in sector/screen pages or a structured data provider
    # (e.g. Trendlyne, Tijori Finance). See SECTOR_ROCE_BENCHMARKS in config.py for
    # the full architectural note. Dynamic benchmarks would make this scoring truly
    # relative and self-updating rather than relying on hardcoded sector medians.
    if roce:
        if _roce_benchmark:
            # Relative scoring: evaluate the company vs its sector's typical ROCE.
            # Analogous to how pe_ratio is scored vs industry PE.
            roce_ratio = roce / _roce_benchmark
            roce_sc = (95 if roce_ratio >= 1.3 else
                       (80 if roce_ratio >= 1.0 else
                        (60 if roce_ratio >= 0.7 else
                         (35 if roce_ratio >= 0.5 else 15))))
        else:
            # Absolute fallback for sectors not in the benchmark dict (e.g. IT, FMCG
            # where the existing 25% bar is already a fair universal standard).
            roce_sc = 95 if roce >= 25 else (80 if roce >= 18 else (55 if roce >= 12 else 25))
    else:
        roce_sc = 50

    roe = fundamentals.get("roe")
    if roe:
        rp = roe * 100 if abs(roe) < 1 else roe
        roe_sc = 90 if rp >= 20 else (75 if rp >= 15 else (55 if rp >= 10 else 30))
    else: roe_sc = 50

    de = fundamentals.get("debt_to_equity")
    _is_financial = (fundamentals.get("sector") or "").strip() == "Financial Services"
    if _is_financial:
        # Banks and NBFCs structurally carry high leverage — D/E is not a
        # meaningful quality signal for them. Assign a neutral passing score
        # so they are not penalised vs. the rest of the universe.
        if de is not None:
            de = de / 100 if de > 10 else de  # normalise for downstream use
        de_sc = 75
    elif de is not None:
        de = de / 100 if de > 10 else de
        de_sc = 95 if de <= 0.3 else (85 if de <= 0.5 else (70 if de <= 0.7 else (45 if de <= 1.5 else 15)))
    else:
        de_sc = 50

    icr = fundamentals.get("interest_coverage")
    icr_sc = (90 if icr >= 10 else (75 if icr >= 5 else (50 if icr >= 3 else 25))) if icr else 50

    pb = fundamentals.get("pb_ratio")
    pb_sc = (90 if pb < 1.5 else (70 if pb < 3 else (45 if pb < 5 else 20))) if (pb and pb > 0) else 50

    sg5 = fundamentals.get("sales_growth_5y")
    sg5_sc = (90 if sg5 >= 20 else (75 if sg5 >= 12 else (55 if sg5 >= 8 else (35 if sg5 >= 0 else 15)))) if sg5 is not None else 50
    pg5 = fundamentals.get("profit_growth_5y")
    pg5_sc = (90 if pg5 >= 20 else (80 if pg5 >= 15 else (60 if pg5 >= 10 else (35 if pg5 >= 0 else 15)))) if pg5 is not None else 50

    prom = fundamentals.get("promoter_holding")
    prom_sc = (90 if prom >= 60 else (75 if prom >= 50 else (55 if prom >= 40 else 25))) if prom else 50
    plg = fundamentals.get("pledged_pct")
    plg_sc = (95 if plg == 0 else (70 if plg < 5 else (40 if plg < 15 else 10))) if plg is not None else 50

    # Lynch Ratio (PEGY) = P/E ÷ (EPS Growth% + Dividend Yield%)
    # Peter Lynch: <1 undervalued, 1-2 fair, >2 expensive. Scored for all but only weighted for Large Cap.
    lynch_ratio = None; lynch_sc = 50
    if pe and pe > 0:
        eg = fundamentals.get("earnings_growth")
        growth_pct = (eg * 100 if eg and abs(eg) < 5 else eg) if eg else pg5  # normalise decimal if needed
        div_pct = (fundamentals.get("dividend_yield") or 0) * 100
        denominator = (growth_pct or 0) + div_pct
        if denominator > 0:
            lynch_ratio = round(pe / denominator, 2)
            lynch_sc = (95 if lynch_ratio < 0.5 else (85 if lynch_ratio < 1.0 else
                        (65 if lynch_ratio < 1.5 else (35 if lynch_ratio < 2.0 else 15))))

    scores = {"roce": roce_sc, "roe": roe_sc, "de": de_sc, "icr": icr_sc,
              "pe_rel": pe_rel_sc, "peg": peg_sc, "pb": pb_sc,
              "sg5": sg5_sc, "pg5": pg5_sc, "promoter": prom_sc, "pledge": plg_sc}
    # Lynch only enters the weighted score when use_lynch=True AND it's a large cap
    if use_lynch:
        scores["lynch"] = lynch_sc
    total_w = sum(fw.values())
    fundamental = sum(fw.get(k, 0) * v for k, v in scores.items()) / total_w if total_w > 0 else 50

    qc = []
    if roce and roce >= 18: qc.append("ROCE≥18%")
    if roe and ((roe >= 15) or (abs(roe) < 1 and roe * 100 >= 15)): qc.append("ROE≥15%")
    # Financial Services stocks pass the D/E check automatically — high leverage
    # is structural for banks/NBFCs and should not penalise their quality gate.
    if _is_financial or (de is not None and de <= 0.5): qc.append("D/E≤0.5")
    if sg5 and sg5 >= 12: qc.append("Sales5Y≥12%")
    if pg5 and pg5 >= 15: qc.append("Profit5Y≥15%")
    if prom and prom >= 50: qc.append("Promoter≥50%")
    if plg is not None and plg == 0: qc.append("ZeroPledge")
    if icr and icr >= 5: qc.append("ICR≥5")
    if peg and peg < 1.5: qc.append("PEG<1.5")
    if pe_ratio and pe_ratio < 1.0: qc.append("PE<Industry")
    if funnel == "large" and lynch_ratio is not None and lynch_ratio < 1.0: qc.append("Lynch<1")

    # Safety override: if the scraper failed to return critical metrics, force the quality
    # gate to False regardless of how many other checks passed. Without this, a stock with
    # all None fundamentals could still accumulate enough soft checks to slip through.
    # For Financial Services, D/E being None is acceptable — use only roce + prom.
    if _is_financial:
        _critical_data_present = roce is not None and prom is not None
    else:
        _critical_data_present = roce is not None and prom is not None and de is not None
    passes_gate = len(qc) >= 6 and _critical_data_present

    return {
        "fundamental": round(_clamp(fundamental), 1),
        "pe": pe, "pe_vs_market": round(pe_ratio, 2) if pe_ratio else None,
        "pe_comparison_label": pe_label, "pe_rel_score": round(pe_rel_sc, 1),
        "pe_abs_score": round(pe_rel_sc, 1), "industry_pe": ipe,
        "peg_ratio": peg, "peg_score": round(peg_sc, 1),
        "lynch_ratio": lynch_ratio, "lynch_score": round(lynch_sc, 1),
        "lynch_weighted": funnel == "large",  # flag so UI knows it's scored
        "roce": roce, "roce_score": round(roce_sc, 1),
        "pb_ratio": pb, "pb_score": round(pb_sc, 1),
        "debt_equity": de, "de_score": round(de_sc, 1),
        "interest_coverage": icr, "icr_score": round(icr_sc, 1),
        "roe": roe, "roe_score": round(roe_sc, 1),
        "sales_growth_5y": sg5, "sg5_score": round(sg5_sc, 1),
        "profit_growth_5y": pg5, "pg5_score": round(pg5_sc, 1),
        "promoter_holding": prom, "promoter_score": round(prom_sc, 1),
        "pledged_pct": plg, "pledge_score": round(plg_sc, 1),
        "quality_checks": qc, "passes_quality_gate": passes_gate,
        "earnings_growth": fundamentals.get("earnings_growth"), "growth_score": round(pg5_sc, 1),
    }

# ═══════════════════════════════════════════════════════════════════════════════
# INSTITUTIONAL
# ═══════════════════════════════════════════════════════════════════════════════
def compute_institutional_score(df, fundamentals):
    if df is None or len(df) < 20:
        return {"institutional": 50, "accumulation_signal": "neutral",
                "obv_score": 50, "trend_score": 50, "returns_5d": 0, "returns_20d": 0}
    close = df["Close"]; volume = df["Volume"]
    obv = ta.obv(close, volume)
    if obv is not None and len(obv) > 20:
        osma = obv.rolling(20).mean()
        if obv.iloc[-1] > osma.iloc[-1] * 1.05: obv_sc = 80; acc = "accumulating"
        elif obv.iloc[-1] > osma.iloc[-1]: obv_sc = 65; acc = "mild accumulation"
        elif obv.iloc[-1] < osma.iloc[-1] * 0.95: obv_sc = 25; acc = "distributing"
        else: obv_sc = 45; acc = "neutral"
    else: obv_sc = 50; acc = "neutral"

    r5 = close.pct_change(5, fill_method=None).iloc[-1] if len(close) > 5 else 0
    r20 = close.pct_change(20, fill_method=None).iloc[-1] if len(close) > 20 else 0
    if pd.isna(r5): r5 = 0
    if pd.isna(r20): r20 = 0

    if r5 > 0 and r20 > 0: ts = 80
    elif r20 > 0: ts = 60
    elif r5 > 0: ts = 50
    else: ts = 30

    dy = fundamentals.get("dividend_yield")
    db = 15 if (dy and dy > 0.02) else (8 if (dy and dy > 0.01) else 0)
    inst = min(100, obv_sc * 0.5 + ts * 0.5 + db)
    return {"institutional": round(_clamp(inst), 1), "accumulation_signal": acc,
            "obv_score": round(obv_sc, 1), "trend_score": round(ts, 1),
            "returns_5d": round(r5 * 100, 2), "returns_20d": round(r20 * 100, 2)}

# ═══════════════════════════════════════════════════════════════════════════════
# RISK
# ═══════════════════════════════════════════════════════════════════════════════
def compute_risk_score(df, fundamentals):
    if df is None or len(df) < 20:
        return {"risk": 50, "beta": None, "beta_score": 50, "volatility_pct": None,
                "vol_score": 50, "drawdown_pct": None, "dd_score": 50}
    close = df["Close"]
    beta = fundamentals.get("beta")
    ilo, ihi = RISK_CONFIG["ideal_beta"]
    if beta: beta_sc = 85 if ilo <= beta <= ihi else (70 if beta < ilo else (50 if beta <= RISK_CONFIG["max_beta"] else 20))
    else: beta_sc = 50

    dr = close.pct_change(fill_method=None).dropna()
    if len(dr) >= 20:
        rv = dr.tail(20).std() * np.sqrt(252) * 100
        if pd.isna(rv): rv = 25
        vol_sc = 90 if rv < 15 else (70 if rv < 25 else (45 if rv < 35 else 20))
    else: rv = None; vol_sc = 50

    h52 = fundamentals.get("52w_high"); cp = close.iloc[-1]
    if h52 and h52 > 0:
        dd = ((h52 - cp) / h52) * 100
        dd_sc = 90 if dd < 5 else (75 if dd < 10 else (50 if dd < RISK_CONFIG["max_drawdown_pct"] else 20))
    else: dd = None; dd_sc = 50
    risk = beta_sc * 0.35 + vol_sc * 0.35 + dd_sc * 0.30
    return {"risk": round(_clamp(risk), 1), "beta": beta, "beta_score": round(beta_sc, 1),
            "volatility_pct": round(rv, 1) if rv else None, "vol_score": round(vol_sc, 1),
            "drawdown_pct": round(dd, 1) if dd else None, "dd_score": round(dd_sc, 1)}

# ═══════════════════════════════════════════════════════════════════════════════
# EXIT & HOLD (NaN-safe)
# ═══════════════════════════════════════════════════════════════════════════════
def compute_exit_and_hold(df, fundamentals, tech_details, funnel="mid"):
    empty = {"entry_price": None, "stop_loss": None, "target_1": None, "target_2": None,
             "risk_reward": None, "stop_loss_pct": 0, "target_1_pct": 0, "target_2_pct": 0,
             "hold_days_min": None, "hold_days_max": None, "hold_label": None}
    if df is None or len(df) < 50: return empty
    try:
        close = df["Close"]; high = df["High"]; low = df["Low"]; cur = close.iloc[-1]
        if pd.isna(cur) or cur <= 0: return empty
        atr_s = ta.atr(high, low, close, length=14)
        atr = atr_s.iloc[-1] if atr_s is not None and len(atr_s) > 0 and not pd.isna(atr_s.iloc[-1]) else cur * 0.02
        sl_cap = cur * 0.92 if funnel == "large" else (cur * 0.88 if funnel == "mid" else cur * 0.85)
        sl = max(low.tail(20).min() - 0.5 * atr, cur - 2 * atr, sl_cap)
        h52 = fundamentals.get("52w_high") or high.tail(252).max()
        risk = cur - sl
        if risk <= 0: risk = cur * 0.05
        t1 = cur + risk * 2
        t2 = min(cur + risk * 3, h52) if h52 and h52 > cur else cur + risk * 3
        if t2 <= t1: t2 = t1 * 1.03
        rr = round((t1 - cur) / risk, 1) if risk > 0 else 0
        adm = close.pct_change(fill_method=None).dropna().abs().mean()
        if adm and not pd.isna(adm) and adm > 0:
            hmin = max(3, min(60, int(((t1 - cur) / cur) / adm * 2)))
            hmax = max(hmin + 5, min(120, int(((t2 - cur) / cur) / adm * 3)))
        else: hmin, hmax = 10, 30
        avg = (hmin + hmax) / 2
        hl = "Short-term" if avg <= 7 else ("Swing (1-3w)" if avg <= 21 else ("Medium (1-3m)" if avg <= 60 else "Position (3+m)"))
        return {"entry_price": round(cur, 2), "stop_loss": round(sl, 2),
                "stop_loss_pct": round((cur - sl) / cur * 100, 1),
                "target_1": round(t1, 2), "target_1_pct": round((t1 - cur) / cur * 100, 1),
                "target_2": round(t2, 2), "target_2_pct": round((t2 - cur) / cur * 100, 1),
                "risk_reward": rr, "hold_days_min": hmin, "hold_days_max": hmax, "hold_label": hl}
    except Exception:
        return empty

# ═══════════════════════════════════════════════════════════════════════════════
# COMPOSITE SCORER
# ═══════════════════════════════════════════════════════════════════════════════
def compute_sentiment_score(sentiment_data: dict) -> dict:
    """Wrap raw Ollama sentiment dict into a normalised scoring dict."""
    if not sentiment_data:
        return {"sentiment": 50, "signal": "neutral", "summary": "", "key_risks": [], "key_catalysts": []}
    score = _clamp(sentiment_data.get("score", 50))
    return {
        "sentiment": score,
        "signal": sentiment_data.get("signal", "neutral"),
        "summary": sentiment_data.get("summary", ""),
        "key_risks": sentiment_data.get("key_risks", []),
        "key_catalysts": sentiment_data.get("key_catalysts", []),
        "headlines_used": sentiment_data.get("headlines_used", []),
    }


def score_stock(ticker, price_df, fundamentals, nifty_df=None, use_lynch=True, sentiment_data=None):
    funnel = _get_funnel(ticker)
    w = _get_weights(funnel)
    tech = compute_technical_score(price_df, nifty_df)
    fund = compute_fundamental_score(fundamentals, funnel, use_lynch=use_lynch)
    inst = compute_institutional_score(price_df, fundamentals)
    risk = compute_risk_score(price_df, fundamentals)
    exit_info = compute_exit_and_hold(price_df, fundamentals, tech, funnel=funnel)
    sentiment = compute_sentiment_score(sentiment_data)
    # Only include sentiment in composite when actual data exists (not just the neutral default)
    sentiment_weight = w.get("sentiment", 0.0) if sentiment_data else 0.0

    rs_score = tech.get("relative_str", 50)
    composite = (
        tech["technical"] * w.get("technical", 0.2) +
        fund["fundamental"] * w.get("fundamental", 0.3) +
        inst["institutional"] * w.get("institutional", 0.15) +
        risk["risk"] * w.get("risk", 0.15) +
        rs_score * w.get("relative_str", 0.2) +
        sentiment["sentiment"] * sentiment_weight
    )

    return {
        "ticker": ticker, "name": fundamentals.get("short_name", ticker.replace(".NS", "")),
        "sector": fundamentals.get("sector", "—"), "funnel": funnel,
        "composite": round(composite, 1), "technical": tech["technical"],
        "fundamental": fund["fundamental"], "institutional": inst["institutional"],
        "risk": risk["risk"], "relative_str": rs_score,
        # None when not yet analysed — shows blank in table rather than a misleading 50
        "sentiment": sentiment["sentiment"] if sentiment_data else None,
        "current_price": round(price_df["Close"].iloc[-1], 2) if price_df is not None and len(price_df) > 0 else None,
        "exit": exit_info,
        "details": {"tech": tech, "fund": fund, "inst": inst, "risk": risk,
                    "rs": {"rs_3m": tech.get("rs_3m"), "rs_12m": tech.get("rs_12m")}, "sentiment": sentiment},
    }

def rank_stocks(price_data, fundamentals, nifty_df=None, progress_callback=None, use_lynch=True, sentiment_data=None):
    buckets = {"large": [], "mid": [], "small": []}
    tickers = list(price_data.keys()); total = len(tickers)
    for i, ticker in enumerate(tickers):
        if progress_callback: progress_callback(i / total, f"Scoring {ticker.replace('.NS', '')}...")
        if ticker in price_data and price_data[ticker] is not None:
            try:
                sd = (sentiment_data or {}).get(ticker)
                result = score_stock(ticker, price_data[ticker], fundamentals.get(ticker, {}), nifty_df, use_lynch=use_lynch, sentiment_data=sd)
                buckets[result["funnel"]].append(result)
            except Exception as e:
                print(f"  ⚠ Scoring failed for {ticker}: {e}")

    for k in buckets: buckets[k].sort(key=lambda x: x["composite"], reverse=True)

    pc = PORTFOLIO_CONFIG
    max_sector = pc.get("max_per_sector", 3)
    funnel_limits = {
        "large": pc["large_cap_picks"],
        "mid":   pc["mid_cap_picks"],
        "small": pc["small_cap_picks"],
    }

    # Build picks with a cross-funnel sector concentration cap.
    # sector_counts is shared across all three funnels so that, e.g.,
    # 2 Technology picks already chosen in Large Cap count against the
    # remaining Technology budget for Mid and Small Cap funnels.
    sector_counts: dict[str, int] = {}
    picks: dict[str, list] = {"large": [], "mid": [], "small": []}

    for funnel in ("large", "mid", "small"):
        limit = funnel_limits[funnel]
        for stock in buckets[funnel]:
            if len(picks[funnel]) >= limit:
                break
            sector = (stock.get("sector") or "Unknown").strip()
            if sector_counts.get(sector, 0) >= max_sector:
                continue  # sector cap reached — try the next highest scorer
            picks[funnel].append(stock)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

    all_ranked = buckets["large"] + buckets["mid"] + buckets["small"]
    all_ranked.sort(key=lambda x: x["composite"], reverse=True)
    if progress_callback: progress_callback(1.0, "Scoring complete!")
    return all_ranked, picks