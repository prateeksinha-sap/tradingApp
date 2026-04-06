"""
NiftyScout v4 Configuration
Three-funnel architecture: Large Cap / Mid Cap / Small Cap
Designed for 10-year alpha generation over Nifty 50.
"""

# Load .env into environment variables (no-op if python-dotenv not installed or file missing)
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)  # override=False: real env vars always win over .env
except ImportError:
    pass

# ── Large Caps (Nifty 50) — The Anchors ──────────────────────────────────────
LARGE_CAP_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "HCLTECH.NS",
    "SUNPHARMA.NS", "TITAN.NS", "BAJFINANCE.NS", "WIPRO.NS", "ULTRACEMCO.NS",
    "NESTLEIND.NS", "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "M&M.NS",
    "TRENT.NS", "ADANIENT.NS", "ADANIPORTS.NS", "JSWSTEEL.NS", "TATASTEEL.NS",
    "TECHM.NS", "INDUSINDBK.NS", "BAJAJFINSV.NS", "HINDALCO.NS", "COALINDIA.NS",
    "GRASIM.NS", "CIPLA.NS", "DRREDDY.NS", "EICHERMOT.NS", "DIVISLAB.NS",
    "APOLLOHOSP.NS", "BPCL.NS", "HEROMOTOCO.NS", "TATACONSUM.NS", "BRITANNIA.NS",
    "SBILIFE.NS", "HDFCLIFE.NS", "BAJAJ-AUTO.NS", "SHRIRAMFIN.NS",
]

# ── Mid Caps — The Growth Engine ─────────────────────────────────────────────
MID_CAP_TICKERS = [
    "ADANIGREEN.NS", "AMBUJACEM.NS", "AUROPHARMA.NS", "BANKBARODA.NS", "BEL.NS",
    "BOSCHLTD.NS", "CANBK.NS", "CHOLAFIN.NS", "COLPAL.NS", "DLF.NS",
    "DABUR.NS", "GODREJCP.NS", "HAVELLS.NS", "HAL.NS", "ICICIPRULI.NS",
    "INDHOTEL.NS", "IOC.NS", "INDUSTOWER.NS", "IRCTC.NS", "IRFC.NS",
    "JINDALSTEL.NS", "LUPIN.NS", "MARICO.NS", "MAXHEALTH.NS", "NHPC.NS",
    "NAUKRI.NS", "PIDILITIND.NS", "PFC.NS", "PNB.NS", "POLYCAB.NS",
    "RECLTD.NS", "SBICARD.NS", "SIEMENS.NS", "SRF.NS", "TATAPOWER.NS",
    "TORNTPHARM.NS", "TRENT.NS", "VEDL.NS", "ETERNAL.NS", "ZYDUSLIFE.NS",
    "PERSISTENT.NS", "COFORGE.NS", "MPHASIS.NS", "LTIM.NS", "DEEPAKNTR.NS",
    "PIIND.NS", "ASTRAL.NS", "BALKRISIND.NS", "BATAINDIA.NS", "BHARATFORG.NS",
    "CROMPTON.NS", "CUMMINSIND.NS", "ESCORTS.NS", "FEDERALBNK.NS",
    "JUBLFOOD.NS", "LALPATHLAB.NS", "LICHSGFIN.NS", "MUTHOOTFIN.NS",
    "OBEROIRLTY.NS", "PAGEIND.NS", "PETRONET.NS", "SAIL.NS",
    "TATACHEM.NS", "TATAELXSI.NS", "TATACOMM.NS", "TORNTPOWER.NS", "VOLTAS.NS",
]

# ── Small / Emerging Caps — The Alpha Boosters ──────────────────────────────
SMALL_CAP_TICKERS = [
    "AFFLE.NS", "APARINDS.NS", "BSOFT.NS", "CAMPUS.NS", "CDSL.NS",
    "CYIENT.NS", "DEVYANI.NS", "DIXON.NS", "ELGIEQUIP.NS", "GRINDWELL.NS",
    "HAPPSTMNDS.NS", "IPCALAB.NS", "JKCEMENT.NS", "KALYANKJIL.NS", "KEI.NS",
    "KPITTECH.NS", "LATENTVIEW.NS", "LTTS.NS", "MASTEK.NS", "METROPOLIS.NS",
    "NATCOPHARM.NS", "OLECTRA.NS", "ROUTE.NS", "SONACOMS.NS", "SYNGENE.NS",
    "TANLA.NS", "TIINDIA.NS", "UTIAMC.NS", "ZENSARTECH.NS",
]

ALL_TICKERS = list(dict.fromkeys(LARGE_CAP_TICKERS + MID_CAP_TICKERS + SMALL_CAP_TICKERS))
NIFTY_50_TICKERS = LARGE_CAP_TICKERS  # Backward compat

# ── PSU Tickers — excluded by default, opt-in via sidebar toggle ─────────────
PSU_TICKERS = [
    "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "COALINDIA.NS", "BPCL.NS",
    "SBIN.NS", "BANKBARODA.NS", "CANBK.NS", "HAL.NS", "IOC.NS",
    "IRCTC.NS", "IRFC.NS", "NHPC.NS", "PFC.NS", "PNB.NS",
    "RECLTD.NS", "SAIL.NS", "BEL.NS", "OIL.NS", "GAIL.NS",
    "CONCOR.NS", "BHEL.NS", "HUDCO.NS", "MAZDOCK.NS",
]

# ═══════════════════════════════════════════════════════════════════════════════
# ALLOCATION — 30 / 50 / 20 with drift bands
# ═══════════════════════════════════════════════════════════════════════════════
ALLOCATION = {
    "large_cap_pct": 30, "mid_cap_pct": 50, "small_cap_pct": 20,
    "max_drift_pct": 15,
    "stocks_per_bucket": {"large": 4, "mid": 7, "small": 4},
    "rebalance_days": 90,
}

# ═══════════════════════════════════════════════════════════════════════════════
# THREE SCORING FUNNELS
# ═══════════════════════════════════════════════════════════════════════════════
# ── Composite dimension weights (must sum to 1.0 per tier) ───────────────────
# sentiment weight is 0.05 for all tiers; RS reduced slightly to compensate.
# Toggle use_sentiment in the sidebar to include/exclude from scoring.
WEIGHTS_LARGE = {"technical": 0.15, "fundamental": 0.40, "institutional": 0.20, "risk": 0.15, "relative_str": 0.05, "sentiment": 0.05}
WEIGHTS_MID   = {"technical": 0.15, "fundamental": 0.30, "institutional": 0.15, "risk": 0.10, "relative_str": 0.25, "sentiment": 0.05}
WEIGHTS_SMALL = {"technical": 0.20, "fundamental": 0.25, "institutional": 0.10, "risk": 0.10, "relative_str": 0.30, "sentiment": 0.05}

# ── Fundamental sub-weights ───────────────────────────────────────────────────
# Large Cap: quality & cash-flow focus (ROCE, D/E, ICR, ROE dominate)
FUND_WEIGHTS_LARGE = {
    "roce": 0.18, "de": 0.15, "icr": 0.12, "roe": 0.12,
    "pe_rel": 0.08, "promoter": 0.08, "lynch": 0.07,
    "pledge": 0.05, "pb": 0.05, "peg": 0.05, "sg5": 0.05,
}
# Mid Cap: growth + valuation focus — PEG and 5Y sales growth heavily weighted;
# absolute PE de-emphasised (pe_rel removed, pe_abs was dead weight — both dropped).
FUND_WEIGHTS_MID = {
    "peg": 0.22, "sg5": 0.22, "pg5": 0.12,
    "roce": 0.10, "de": 0.08, "roe": 0.07,
    "icr": 0.04, "promoter": 0.06, "pledge": 0.04,
    "pb": 0.03, "pe_rel": 0.02,
}
# Small Cap: pure growth — PEG and sales growth dominate; PE irrelevant at this stage.
FUND_WEIGHTS_SMALL = {
    "peg": 0.25, "sg5": 0.25, "pg5": 0.14,
    "de": 0.09, "roe": 0.07, "roce": 0.07,
    "promoter": 0.05, "pledge": 0.04,
    "icr": 0.02, "pb": 0.02,
}

WEIGHTS_BY_TIER = {"large": WEIGHTS_LARGE, "mid": WEIGHTS_MID, "small": WEIGHTS_SMALL}
FUND_WEIGHTS_BY_TIER = {"large": FUND_WEIGHTS_LARGE, "mid": FUND_WEIGHTS_MID, "small": FUND_WEIGHTS_SMALL}
WEIGHTS = WEIGHTS_MID  # Legacy compat

# ═══════════════════════════════════════════════════════════════════════════════
# TECHNICAL, FUNDAMENTAL, RISK CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
TECH_CONFIG = {
    "rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70,
    "rsi_sweet_spot": (40, 65),
    "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
    "sma_short": 20, "sma_long": 50, "sma_200": 200,
    "volume_spike_threshold": 1.5, "lookback_days": 300,
    "rs_period_days": 63,  # NEW: Relative Strength vs Nifty (3 months)
}

FUND_CONFIG = {
    "pe_max": 50, "pe_ideal": 25,
    "debt_equity_max": 1.5, "min_market_cap_cr": 5000, "nifty_pe_avg": 22,
}

RISK_CONFIG = {
    "max_beta": 1.8, "ideal_beta": (0.7, 1.3),
    "max_drawdown_pct": 30, "volatility_window": 20,
}

# ═══════════════════════════════════════════════════════════════════════════════
# CACHE, DISPLAY, SIZING, BACKTEST
# ═══════════════════════════════════════════════════════════════════════════════
CACHE_CONFIG = {
    "db_path": "data/niftyscout.db",
    "price_cache_hours": 4, "fundamental_cache_days": 7,
}

TOP_N_PICKS = 15
APP_TITLE = "NiftyScout"
APP_SUBTITLE = "Alpha Engine — 15-Stock Growth Portfolio"

POSITION_CONFIG = {"default_capital": 500000, "max_position_pct": 12, "risk_per_trade_pct": 2}

PORTFOLIO_CONFIG = {"large_cap_picks": 4, "mid_cap_picks": 7, "small_cap_picks": 4, "max_per_sector": 3}

BACKTEST_CONFIG = {
    "lookback_years": 3, "rebalance_days": 63,
    "top_n": 15, "initial_capital": 500000,
}

# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL & NGROK
# ═══════════════════════════════════════════════════════════════════════════════
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com", "smtp_port": 587,
    # Credentials are loaded from .env (NIFTYSCOUT_EMAIL / NIFTYSCOUT_EMAIL_PASSWORD)
    # or .streamlit/secrets.toml — never hardcode them here.
    "sender_email": "",
    "sender_password": "",
    "recipients": [], "auto_send_after_analysis": True,
}
NGROK_CONFIG = {"auth_token": "", "enabled": False}

# ═══════════════════════════════════════════════════════════════════════════════
# OLLAMA — local LLM for news sentiment analysis
# ═══════════════════════════════════════════════════════════════════════════════
OLLAMA_CONFIG = {
    "host": "http://localhost:11434",
    "model": "llama3.2",
    "sentiment_cache_hours": 24,
    "max_headlines_per_stock": 5,
    "enabled": True,
}