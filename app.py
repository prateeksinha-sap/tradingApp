"""
NiftyScout v4 — Alpha Engine Dashboard
Three-funnel portfolio: Large (30%) / Mid (50%) / Small (20%)
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

from config import (
    APP_TITLE, APP_SUBTITLE, WEIGHTS, EMAIL_CONFIG, NGROK_CONFIG,
    POSITION_CONFIG, BACKTEST_CONFIG, ALLOCATION, TOP_N_PICKS,
    ALL_TICKERS, LARGE_CAP_TICKERS, MID_CAP_TICKERS, SMALL_CAP_TICKERS,
    OLLAMA_CONFIG, PSU_TICKERS,
)
from data_fetcher import (
    fetch_price_data, fetch_fundamentals,
    fetch_nifty_index, fetch_india_vix,
    log_picks, get_picks_history,
)
from scoring import rank_stocks, score_stock
from news_sentiment import (
    fetch_sentiment_batch, get_cached_sentiment_all,
    is_ollama_running, clear_sentiment_cache,
)
from email_notifier import send_picks_email, is_email_configured
from tunnel import start_tunnel, get_active_tunnel, is_ngrok_installed, get_install_instructions
from screener_scraper import fetch_screener_data, merge_fundamentals
from position_sizer import size_portfolio, detect_market_regime
from backtester import run_backtest
from performance_tracker import (
    add_position, get_active_positions, get_closed_positions,
    check_positions_against_prices, get_performance_summary,
)

st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="wide", initial_sidebar_state="expanded")

# ── Premium Terminal CSS ──────────────────────────────────────────────────────
st.markdown("""<style>
/* ── Pick card — glassmorphism ── */
.pick-card {
  background: rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  padding: 18px;
  margin-bottom: 10px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}
.pick-card:hover {
  transform: translateY(-2px);
  border-color: rgba(99, 102, 241, 0.5);
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 0 20px -5px rgba(99, 102, 241, 0.15);
}

/* ── Score badge — glow ring ── */
.score-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  border-radius: 50%;
  border: 3px solid currentColor;
  font-size: 1.3rem;
  font-weight: 900;
  line-height: 1;
}
.score-badge.high { color: #22c55e; box-shadow: 0 0 15px rgba(34, 197, 94, 0.35); }
.score-badge.mid  { color: #f59e0b; box-shadow: 0 0 15px rgba(245, 158, 11, 0.35); }
.score-badge.low  { color: #ef4444; box-shadow: 0 0 15px rgba(239, 68,  68, 0.35); }

/* ── Typography ── */
.pick-name { font-size: 1.05rem; font-weight: 700; }
.pick-meta { font-size: 0.78rem; opacity: 0.6; }

/* ── Sub-score pills ── */
.sub-score-row { display: flex; gap: 5px; margin-top: 8px; flex-wrap: wrap; }
.sub-pill {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.05);
}

/* ── Target grid ── */
.target-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 8px;
  margin-top: 10px;
}
.target-box {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 10px;
  text-align: center;
}
.target-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  opacity: 0.45;
  margin-bottom: 2px;
}
.target-value { font-size: 1rem; font-weight: 700; }
.target-pct   { font-size: 0.72rem; font-weight: 600; }
.target-pct.green { color: #22c55e; }
.target-pct.red   { color: #ef4444; }

/* ── Hold badge ── */
.hold-badge {
  display: inline-block;
  margin-top: 6px;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
  background: rgba(99, 102, 241, 0.12);
  color: #818cf8;
  border: 1px solid rgba(99, 102, 241, 0.3);
}

/* ── Signal badges ── */
.signal-badge {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.signal-badge.bullish { background: rgba(34, 197, 94, 0.12); color: #4ade80; border: 1px solid rgba(34,197,94,0.2); }
.signal-badge.bearish { background: rgba(239, 68, 68, 0.12); color: #f87171; border: 1px solid rgba(239,68,68,0.2); }
.signal-badge.neutral { background: rgba(148, 163, 184, 0.08); color: #94a3b8; border: 1px solid rgba(148,163,184,0.15); }

/* ── Funnel tags ── */
.funnel-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  margin-right: 4px;
  letter-spacing: 0.4px;
}
.funnel-tag.large { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59,130,246,0.2); }
.funnel-tag.mid   { background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168,85,247,0.2); }
.funnel-tag.small { background: rgba(249, 115, 22, 0.15); color: #fb923c; border: 1px solid rgba(249,115,22,0.2); }

/* ── Metric cards ── */
div[data-testid="stMetric"] {
  border-radius: 12px;
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  background: rgba(30, 41, 59, 0.5);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
</style>""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"## 🎯 {APP_TITLE}")
    st.caption(APP_SUBTITLE)
    app_mode = st.radio(
        "mode",
        ["🎯 Portfolio Engine", "🔬 Deep Dive"],
        horizontal=True,
        label_visibility="collapsed",
        key="app_mode_nav",
    )
    st.divider()
    st.markdown("### 📊 Allocation")
    st.caption(f"Large: {ALLOCATION['large_cap_pct']}% · Mid: {ALLOCATION['mid_cap_pct']}% · Small: {ALLOCATION['small_cap_pct']}%")
    spb = ALLOCATION['stocks_per_bucket']
    st.caption(f"Stocks: {spb['large']}L + {spb['mid']}M + {spb['small']}S = {spb['large']+spb['mid']+spb['small']}")
    st.divider()
    show_market = st.checkbox("Show market overview", value=True)
    st.divider()
    st.markdown("### ⚙️ Scoring Mode")
    use_lynch = st.toggle(
        "Include Lynch Ratio",
        value=True,
        help="Lynch Ratio (PEGY = P/E ÷ Growth% + Div%) is weighted at ~6.5% "
             "inside the Fundamental score for Large Cap stocks only. "
             "Toggle off to score and rank purely without it.",
    )
    if use_lynch:
        st.caption("✦ Lynch weighted in Large Cap fundamental score")
    else:
        st.caption("~ Lynch shown for reference only — not scored")
    include_psus = st.toggle(
        "🏛️ Include PSUs",
        value=False,
        help="PSUs (state-owned enterprises) are excluded by default — they tend to "
             "underperform on ROCE, promoter holding quality, and capital allocation. "
             "Toggle ON to include them in the universe.",
    )
    if include_psus:
        st.caption(f"🏛️ PSUs included (+{len(PSU_TICKERS)} stocks in universe)")
    else:
        st.caption(f"🏛️ PSUs excluded ({len(PSU_TICKERS)} stocks filtered out)")
    st.divider()
    st.markdown("### 🧠 Sentiment (Ollama)")
    _ollama_ok = is_ollama_running()
    if _ollama_ok:
        st.success(f"🟢 Running · {OLLAMA_CONFIG['model']}", icon=None)
    else:
        st.error("🔴 Ollama offline", icon=None)
    use_sentiment = st.toggle(
        "Include in scoring",
        value=_ollama_ok,
        disabled=not _ollama_ok,
        help="Adds a 5% sentiment dimension to the composite score based on "
             "Indian market RSS news analysed by Ollama. Auto-runs on the 15 picks; "
             "use the button below for all stocks.",
    )
    if _ollama_ok:
        st.caption("Auto-runs on 15 picks after scoring · 24h cache")
        if st.button("🔄 Full Scan (all stocks)", use_container_width=True, key="full_sentiment_btn"):
            st.session_state["run_full_sentiment"] = True
        if st.button("🗑 Clear Sentiment Cache", use_container_width=True, key="clear_sent_btn"):
            clear_sentiment_cache()
            st.toast("Sentiment cache cleared", icon="🗑")
    st.divider()
    if st.button("🗑️ Clear Cache & Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # Tunnel
    st.divider()
    st.markdown("### 📱 Mobile")
    tunnel_url = get_active_tunnel()
    if tunnel_url:
        st.success("Active!"); st.code(tunnel_url, language=None)
    elif st.button("▶️ Start Tunnel", use_container_width=True, key="tun"):
        if is_ngrok_installed():
            ok, r = start_tunnel()
            if ok: st.success("Started!"); st.code(r)
            else: st.error(r)

    # Email
    st.divider()
    st.markdown("### 📧 Email Report")

    # Initialise recipient list and input counter from config
    if "email_recipients" not in st.session_state:
        st.session_state["email_recipients"] = list(EMAIL_CONFIG.get("recipients", []))
    if "email_input_gen" not in st.session_state:
        st.session_state["email_input_gen"] = 0

    # Add a new recipient — counter in key forces a blank widget after each add
    new_email = st.text_input("Add recipient", placeholder="friend@gmail.com",
                              label_visibility="collapsed",
                              key=f"new_email_input_{st.session_state['email_input_gen']}")
    if st.button("➕ Add", use_container_width=True, key="add_email_btn"):
        addr = new_email.strip()
        if addr and "@" in addr and addr not in st.session_state["email_recipients"]:
            st.session_state["email_recipients"].append(addr)
            st.session_state["email_input_gen"] += 1  # new key → fresh empty widget
            st.rerun()
        elif addr in st.session_state["email_recipients"]:
            st.toast("Already in list", icon="ℹ️")

    # Pick who to send to
    all_recipients = st.session_state["email_recipients"]
    if all_recipients:
        selected = st.multiselect(
            "Send to:",
            options=all_recipients,
            default=all_recipients,
            key="selected_recipients",
            label_visibility="collapsed",
        )
        # Remove button
        to_remove = st.selectbox("Remove:", ["—"] + all_recipients, key="remove_recipient", label_visibility="collapsed")
        if st.button("🗑 Remove selected", use_container_width=True, key="remove_btn"):
            if to_remove != "—":
                st.session_state["email_recipients"].remove(to_remove)
                st.rerun()

        if is_email_configured():
            if st.button("📤 Send Now", use_container_width=True, key="email", type="primary"):
                st.session_state["manual_email_requested"] = True
                st.session_state["manual_email_recipients"] = selected
        else:
            st.warning("Sender not configured in config.py")
    else:
        st.caption("Add at least one recipient above.")
        if is_email_configured():
            st.button("📤 Send Now", use_container_width=True, key="email", disabled=True)

    st.divider()
    st.caption("⚠️ Decision-support tool, not financial advice. DYOR.")

# ═══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS — defined before mode routing so both modes can use them
# ═══════════════════════════════════════════════════════════════════════════════

def _price_spectrum_bar(ei: dict, current_price: float) -> str:
    sl    = ei.get("stop_loss",  0) or 0
    t1    = ei.get("target_1",   0) or 0
    t2    = ei.get("target_2",   0) or 0
    price = current_price or 0
    span  = t2 - sl
    if span <= 0 or sl <= 0 or t2 <= 0:
        return ""
    t1_pct    = max(0, min(100, (t1    - sl) / span * 100))
    price_pct = max(0, min(100, (price - sl) / span * 100))
    gradient  = (f"linear-gradient(to right,#ef4444 0%,#f59e0b {t1_pct:.1f}%,#22c55e 100%)")
    label_align = "right" if price_pct > 85 else ("left" if price_pct < 15 else "center")
    label_transform = {"right": "translateX(-100%)", "left": "translateX(0%)", "center": "translateX(-50%)"}[label_align]
    return (
        f'<div style="margin:12px 0 4px;padding:0 2px;">'
        f'<div style="position:relative;height:8px;border-radius:6px;background:{gradient};box-shadow:inset 0 1px 3px rgba(0,0,0,0.4);">'
        f'<div style="position:absolute;top:0;bottom:0;left:{t1_pct:.1f}%;width:1px;background:rgba(255,255,255,0.25);"></div>'
        f'<div style="position:absolute;top:50%;left:{price_pct:.1f}%;transform:translate(-50%,-50%);width:13px;height:13px;border-radius:50%;background:#ffffff;box-shadow:0 0 8px rgba(255,255,255,0.7),0 0 0 2px rgba(15,23,42,0.9);z-index:2;"></div>'
        f'<div style="position:absolute;bottom:14px;left:{price_pct:.1f}%;transform:{label_transform};font-size:0.6rem;font-weight:700;color:#f1f5f9;white-space:nowrap;text-shadow:0 1px 3px rgba(0,0,0,0.8);">&#8377;{price:,.0f}</div>'
        f'</div>'
        f'<div style="display:flex;justify-content:space-between;margin-top:5px;font-size:0.58rem;letter-spacing:0.2px;">'
        f'<span style="color:#f87171;">SL &#8377;{sl:,.0f}</span>'
        f'<span style="color:#fbbf24;opacity:0.8;">T1 &#8377;{t1:,.0f}</span>'
        f'<span style="color:#4ade80;">T2 &#8377;{t2:,.0f}</span>'
        f'</div></div>'
    )


def _build_candlestick_chart(df: pd.DataFrame, title: str = "", x_range_days: int = 126) -> go.Figure:
    """Candlestick + SMA 20/50/200 + volume chart. Reusable across modes.
    df should be the FULL price history so rolling(200) has enough data.
    x_range_days controls the visible window (default 126 ≈ 6 months)."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.72, 0.28], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="Price",
        increasing_line_color="#22c55e", decreasing_line_color="#ef4444",
        increasing_fillcolor="rgba(34,197,94,0.7)", decreasing_fillcolor="rgba(239,68,68,0.7)",
    ), row=1, col=1)
    sma20  = df["Close"].rolling(20).mean()
    sma50  = df["Close"].rolling(50).mean()
    sma200 = df["Close"].rolling(200).mean()
    fig.add_trace(go.Scatter(x=df.index, y=sma20, name="SMA 20",
                             line=dict(color="#f59e0b", width=1.5, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=sma50, name="SMA 50",
                             line=dict(color="#818cf8", width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=sma200, name="SMA 200",
                             line=dict(color="#e2e8f0", width=2, dash="dash")), row=1, col=1)
    vol_colors = ["#22c55e" if c >= o else "#ef4444"
                  for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volume",
                         marker_color=vol_colors, opacity=0.5, showlegend=False), row=2, col=1)
    fig.update_layout(
        height=500, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(15,23,42,0.5)",
        xaxis_rangeslider_visible=False, margin=dict(t=16, b=10, l=0, r=0),
        xaxis_range=[df.index[-min(x_range_days, len(df))], df.index[-1]],
        legend=dict(
            orientation="h", xanchor="left", x=0.01,
            yanchor="top",   y=0.99,
            bgcolor="rgba(15,23,42,0.75)",
            bordercolor="rgba(255,255,255,0.08)", borderwidth=1,
            font=dict(size=11),
        ),
        font=dict(color="#94a3b8"),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)", showgrid=True, row=1, col=1)
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)", showgrid=True, row=2, col=1)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)", showgrid=True)
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# MODE ROUTING
# ═══════════════════════════════════════════════════════════════════════════════

if app_mode == "🔬 Deep Dive":

    st.markdown("# 🔬 Deep Dive Analyzer")
    st.caption("Comprehensive single-stock analysis · Data fetched fresh for the selected ticker")

    # ── Ticker selector ───────────────────────────────────────────────────────
    dd_c1, dd_c2 = st.columns([5, 1])
    dd_ticker_select = dd_c1.selectbox(
        "ticker", ALL_TICKERS,
        format_func=lambda t: t.replace(".NS", ""),
        label_visibility="collapsed",
        key="dd_ticker_select",
    )
    if dd_c2.button("🔍 Analyse", type="primary", use_container_width=True, key="dd_run_btn"):
        st.session_state["dd_run"] = dd_ticker_select

    dd_run = st.session_state.get("dd_run")
    if not dd_run:
        st.info("👆 Select a stock above and click **Analyse** to run a deep dive.")
        st.stop()

    # ── Data fetch ────────────────────────────────────────────────────────────
    @st.cache_data(ttl=3600, show_spinner=False)
    def _dd_load(ticker):
        _p = fetch_price_data([ticker])
        _y = fetch_fundamentals([ticker])
        _s = fetch_screener_data(list(_y.keys()))
        _f = merge_fundamentals(_y, _s)
        _n = fetch_nifty_index()
        return _p, _f, _n

    with st.status(f"📡 Loading {dd_run.replace('.NS', '')}…", expanded=False) as _dds:
        dd_price_data, dd_fund_data, dd_nifty = _dd_load(dd_run)
        _dds.update(label="✅ Data loaded", state="complete", expanded=False)

    dd_price_df = dd_price_data.get(dd_run)
    dd_fund     = dd_fund_data.get(dd_run, {})

    if dd_price_df is None or len(dd_price_df) < 20:
        st.error(f"Insufficient price data for **{dd_run}**. Check the ticker symbol.")
        st.stop()

    # ── Score ─────────────────────────────────────────────────────────────────
    dd_result = score_stock(dd_run, dd_price_df, dd_fund, dd_nifty, use_lynch=True)

    # ── Sentiment (if Ollama running) ─────────────────────────────────────────
    dd_sent_raw = {}
    if _ollama_ok:
        with st.status("🧠 Fetching sentiment…", expanded=False) as _ddsent:
            dd_sent_raw = fetch_sentiment_batch([dd_run], dd_fund_data)
            _ddsent.update(label="🧠 Sentiment ready", state="complete", expanded=False)
        if dd_sent_raw.get(dd_run):
            dd_result = score_stock(dd_run, dd_price_df, dd_fund, dd_nifty,
                                    use_lynch=True, sentiment_data=dd_sent_raw.get(dd_run))

    comp   = dd_result["composite"]
    f_det  = dd_result.get("details", {}).get("fund", {})
    t_det  = dd_result.get("details", {}).get("tech", {})
    rs_det = dd_result.get("details", {}).get("rs", {})
    ei     = dd_result.get("exit", {})
    sent_d = dd_sent_raw.get(dd_run, {})

    # ── Header row ────────────────────────────────────────────────────────────
    st.markdown("---")
    hc1, hc2, hc3, hc4 = st.columns([3, 1, 1, 1])
    hc1.markdown(f"## {dd_result['name']}")
    hc1.caption(f"{dd_result.get('sector','—')} · {dd_run.replace('.NS','')}")
    hc2.metric("Price", f"₹{dd_result.get('current_price', 0):,.2f}")
    hc3.metric("Funnel", dd_result["funnel"].title())
    fn_color = {"large": "#3b82f6", "mid": "#a855f7", "small": "#f97316"}.get(dd_result["funnel"], "#6b7280")
    qc_count = len(f_det.get("quality_checks", []))
    hc4.metric("Quality Gate", f"{qc_count}/10 checks",
               "✅ Pass" if f_det.get("passes_quality_gate") else "❌ Fail")

    st.markdown("---")

    # ── Gauge + sub-scores ────────────────────────────────────────────────────
    g_col, s_col = st.columns([1, 2])

    with g_col:
        g_color = "#22c55e" if comp >= 65 else ("#f59e0b" if comp >= 50 else "#ef4444")
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=comp,
            number={"font": {"size": 52, "color": g_color}},
            title={"text": "Composite Score", "font": {"size": 13, "color": "#64748b"}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#334155",
                         "tickvals": [0, 25, 50, 65, 75, 100]},
                "bar": {"color": g_color, "thickness": 0.28},
                "bgcolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0,  50], "color": "rgba(239,68,68,0.08)"},
                    {"range": [50, 65], "color": "rgba(245,158,11,0.08)"},
                    {"range": [65,100], "color": "rgba(34,197,94,0.08)"},
                ],
                "threshold": {"line": {"color": g_color, "width": 3},
                              "thickness": 0.8, "value": comp},
            },
        ))
        fig_gauge.update_layout(
            height=270, margin=dict(t=30, b=0, l=20, r=20),
            paper_bgcolor="rgba(0,0,0,0)", font_color="#f1f5f9",
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

    with s_col:
        sm1, sm2 = st.columns(2)
        sm3, sm4 = st.columns(2)
        sm1.metric("📊 Technical",    f"{dd_result['technical']:.0f} / 100")
        sm2.metric("📋 Fundamental",  f"{dd_result['fundamental']:.0f} / 100")
        sm3.metric("🏛️ Institutional", f"{dd_result['institutional']:.0f} / 100")
        sm4.metric("🛡️ Risk",          f"{dd_result['risk']:.0f} / 100")
        rs_val  = dd_result.get("relative_str", 50)
        rs_3m   = rs_det.get("rs_3m")
        rs_12m  = rs_det.get("rs_12m")
        rs_delta = (f"3M {rs_3m:+.1f}% / 12M {rs_12m:+.1f}%" if rs_3m is not None and rs_12m is not None
                    else (f"3M {rs_3m:+.1f}%" if rs_3m is not None else None))
        st.metric("🚀 Relative Strength", f"{rs_val:.0f} / 100", rs_delta)

    st.markdown("---")

    # ── Price chart ───────────────────────────────────────────────────────────
    st.markdown("#### 📈 Price Chart")
    # Pass the full history so rolling(200) has enough bars to compute SMA 200.
    # x_range_days limits the *visible* window to ~6 months without slicing the data.
    st.plotly_chart(_build_candlestick_chart(dd_price_df, x_range_days=126),
                    use_container_width=True)

    st.markdown("---")

    # ── Fundamentals + Quality Gate ───────────────────────────────────────────
    st.markdown("#### 📋 Fundamentals & Quality Gate")
    fq1, fq2 = st.columns(2)

    with fq1:
        st.markdown("**Key Metrics**")
        _metrics = [
            ("P/E Ratio",        f_det.get("pe"),              None),
            ("PEG Ratio",        f_det.get("peg_ratio"),       None),
            ("ROCE",             f_det.get("roce"),            "%"),
            ("ROE",              f_det.get("roe"),             "%"),
            ("Debt / Equity",    f_det.get("debt_equity"),     None),
            ("Interest Coverage",f_det.get("interest_coverage"),"x"),
            ("Sales Growth 5Y",  f_det.get("sales_growth_5y"), "%"),
            ("Profit Growth 5Y", f_det.get("profit_growth_5y"),"%"),
            ("Promoter Holding", f_det.get("promoter_holding"),"%"),
            ("Pledged %",        f_det.get("pledged_pct"),     "%"),
            ("Lynch Ratio",      f_det.get("lynch_ratio"),     None),
        ]
        _rows = ""
        for _lbl, _val, _unit in _metrics:
            _disp = (f"{_val:.1f}{_unit}" if _unit else f"{_val:.2f}") if _val is not None else "—"
            _rows += (
                f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
                f'border-bottom:1px solid rgba(255,255,255,0.05);">'
                f'<span style="color:#94a3b8;font-size:0.83rem;">{_lbl}</span>'
                f'<span style="font-weight:600;font-size:0.83rem;">{_disp}</span></div>'
            )
        st.markdown(
            f'<div style="background:rgba(15,23,42,0.55);border:1px solid rgba(255,255,255,0.07);'
            f'border-radius:12px;padding:12px 16px;">{_rows}</div>',
            unsafe_allow_html=True,
        )

    with fq2:
        st.markdown("**Quality Gate**")
        _passed = set(f_det.get("quality_checks", []))
        _all_checks = ["ROCE≥18%", "ROE≥15%", "D/E≤0.5", "Sales5Y≥12%", "Profit5Y≥15%",
                       "Promoter≥50%", "ZeroPledge", "ICR≥5", "PEG<1.5", "PE<Industry"]
        if dd_result.get("funnel") == "large":
            _all_checks.append("Lynch<1")
        _gate_rows = ""
        for _chk in _all_checks:
            _ok  = _chk in _passed
            _ico = "✅" if _ok else "❌"
            _clr = "#4ade80" if _ok else "#f87171"
            _bg  = "rgba(34,197,94,0.07)" if _ok else "rgba(239,68,68,0.07)"
            _gate_rows += (
                f'<div style="display:flex;align-items:center;gap:8px;padding:5px 10px;'
                f'margin-bottom:3px;border-radius:7px;background:{_bg};">'
                f'<span>{_ico}</span>'
                f'<span style="font-size:0.81rem;color:{_clr};">{_chk}</span></div>'
            )
        _passes   = f_det.get("passes_quality_gate", False)
        _tot      = len(_all_checks)
        _summary  = (
            f'<div style="margin-bottom:8px;padding:8px 12px;border-radius:8px;text-align:center;'
            f'background:{"rgba(34,197,94,0.15)" if _passes else "rgba(239,68,68,0.15)"};'
            f'color:{"#4ade80" if _passes else "#f87171"};font-weight:700;font-size:0.88rem;">'
            f'{"✅ PASSES" if _passes else "❌ FAILS"} Quality Gate · {len(_passed)}/{_tot} checks</div>'
        )
        st.markdown(
            f'<div style="background:rgba(15,23,42,0.55);border:1px solid rgba(255,255,255,0.07);'
            f'border-radius:12px;padding:12px;">{_summary}{_gate_rows}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Sentiment ─────────────────────────────────────────────────────────────
    if sent_d:
        st.markdown("#### 🧠 Sentiment Analysis (Ollama)")
        _summary_txt   = sent_d.get("summary", "")
        _catalysts     = sent_d.get("key_catalysts", [])
        _risks         = sent_d.get("key_risks", [])
        if _summary_txt:
            st.info(f"📰 **Summary:** {_summary_txt}")
        _sc1, _sc2 = st.columns(2)
        with _sc1:
            if _catalysts:
                st.success("**Key Catalysts**\n\n" + "\n".join(f"• {c}" for c in _catalysts))
        with _sc2:
            if _risks:
                st.warning("**Key Risks**\n\n" + "\n".join(f"• {r}" for r in _risks))
        st.markdown("---")
    elif _ollama_ok:
        st.caption("🧠 No sentiment data cached for this ticker.")
        st.markdown("---")

    # ── Exit Strategy ─────────────────────────────────────────────────────────
    st.markdown("#### 🎯 Exit Strategy")
    ec1, ec2, ec3, ec4, ec5 = st.columns(5)
    ec1.metric("Entry",     f"₹{ei.get('entry_price',  0):,.2f}")
    ec2.metric("Stop Loss", f"₹{ei.get('stop_loss',    0):,.2f}", f"-{ei.get('stop_loss_pct', 0):.1f}%")
    ec3.metric("Target 1",  f"₹{ei.get('target_1',     0):,.2f}", f"+{ei.get('target_1_pct', 0):.1f}%")
    ec4.metric("Target 2",  f"₹{ei.get('target_2',     0):,.2f}", f"+{ei.get('target_2_pct', 0):.1f}%")
    ec5.metric("R:R",       f"{ei.get('risk_reward',   0):.1f}x")
    st.markdown(_price_spectrum_bar(ei, dd_result.get("current_price", 0)), unsafe_allow_html=True)
    st.caption(f"⏱️ Hold: {ei.get('hold_days_min','?')}–{ei.get('hold_days_max','?')} days · {ei.get('hold_label','')}")

    st.markdown("---")
    st.caption(f"🔬 Deep Dive · {dd_result['name']} · {datetime.now().strftime('%Y-%m-%d %H:%M')} · Not financial advice")
    st.stop()  # ← halt here; Portfolio Engine code below will not execute


# ── Header (Portfolio Engine) ─────────────────────────────────────────────────
st.markdown(f"# 🎯 {APP_TITLE}")
st.caption(f"{APP_SUBTITLE} · {datetime.now().strftime('%A, %d %B %Y')}")

# ── Active ticker universe (PSU toggle applied) ───────────────────────────────
active_tickers = ALL_TICKERS if include_psus else [t for t in ALL_TICKERS if t not in PSU_TICKERS]

# ── Data Loading ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def load_all_data(tickers):
    price_data = fetch_price_data(tickers)
    yf_fund = fetch_fundamentals(tickers)
    screener = fetch_screener_data(list(yf_fund.keys()))
    fund = merge_fundamentals(yf_fund, screener)
    nifty_df = fetch_nifty_index()
    return price_data, fund, nifty_df

with st.status("📡 Loading market data...", expanded=True) as status:
    st.write(f"Fetching {len(active_tickers)} stocks across Large/Mid/Small caps...")
    price_data, fundamentals, nifty_df = load_all_data(active_tickers)
    st.write(f"✅ Loaded {len(price_data)} stocks with Screener.in data" + ("" if include_psus else f" (PSUs excluded)"))
    st.write("Scoring across 3 funnels...")
    all_ranked, picks_by_tier = rank_stocks(price_data, fundamentals, nifty_df, use_lynch=use_lynch)
    portfolio = picks_by_tier["large"] + picks_by_tier["mid"] + picks_by_tier["small"]
    portfolio.sort(key=lambda x: x["composite"], reverse=True)
    rankings = all_ranked  # Full list for the table
    st.write(f"✅ Portfolio: {len(portfolio)} stocks — "
             f"{len(picks_by_tier['large'])}L + {len(picks_by_tier['mid'])}M + {len(picks_by_tier['small'])}S")
    log_picks(portfolio[:3])
    status.update(label="✅ Analysis complete!", state="complete", expanded=False)

# ── Sentiment layer ───────────────────────────────────────────────────────────
# Load any already-cached sentiment for all tickers (instant, no Ollama call)
_sentiment_data = get_cached_sentiment_all() if use_sentiment else {}

# Full scan requested via sidebar button
if st.session_state.get("run_full_sentiment") and use_sentiment and is_ollama_running():
    st.session_state["run_full_sentiment"] = False
    with st.status("🧠 Running full sentiment scan...", expanded=True) as _ss:
        def _sent_prog(p, msg): _ss.write(msg)
        _sentiment_data = fetch_sentiment_batch(active_tickers, fundamentals, _sent_prog)
        _ss.update(label=f"✅ Sentiment complete — {len(_sentiment_data)} stocks", state="complete", expanded=False)
    # Re-rank with full sentiment
    all_ranked, picks_by_tier = rank_stocks(
        price_data, fundamentals, nifty_df,
        use_lynch=use_lynch, sentiment_data=_sentiment_data
    )
    portfolio = picks_by_tier["large"] + picks_by_tier["mid"] + picks_by_tier["small"]
    portfolio.sort(key=lambda x: x["composite"], reverse=True)

# Auto-run sentiment on the 15 portfolio picks (only cache misses hit Ollama)
elif use_sentiment and is_ollama_running():
    _pick_tickers = [p["ticker"] for p in portfolio]
    _missing = [t for t in _pick_tickers if t not in _sentiment_data]
    if _missing:
        with st.status(f"🧠 Sentiment: analysing {len(_missing)} picks...", expanded=False) as _ss:
            _new = fetch_sentiment_batch(_missing, fundamentals)
            _sentiment_data.update(_new)
            _ss.update(label="🧠 Sentiment ready", state="complete", expanded=False)
    # Re-score the 15 picks only (fast — no data fetch)
    if _sentiment_data:
        from scoring import score_stock as _score_stock
        _refreshed = []
        for p in portfolio:
            sd = _sentiment_data.get(p["ticker"])
            if sd:
                _refreshed.append(_score_stock(
                    p["ticker"], price_data.get(p["ticker"]),
                    fundamentals.get(p["ticker"], {}), nifty_df,
                    use_lynch=use_lynch, sentiment_data=sd
                ))
            else:
                _refreshed.append(p)
        portfolio = sorted(_refreshed, key=lambda x: x["composite"], reverse=True)

# Email handling
_dash_url = get_active_tunnel() or "http://localhost:8501"
if EMAIL_CONFIG.get("auto_send_after_analysis") and is_email_configured() and "auto_email_sent" not in st.session_state:
    ok, msg = send_picks_email(picks_by_tier, _dash_url)
    st.session_state["auto_email_sent"] = True
    st.toast(f"📧 {'Sent' if ok else 'Failed'}: {msg}", icon="✅" if ok else "⚠️")
if st.session_state.get("manual_email_requested"):
    st.session_state["manual_email_requested"] = False
    chosen = st.session_state.pop("manual_email_recipients", None)
    ok, msg = send_picks_email(picks_by_tier, _dash_url, recipients=chosen)
    st.toast(f"📧 {msg}", icon="✅" if ok else "❌")

# ── Market Context ───────────────────────────────────────────────────────────
if show_market:
    st.markdown("---")
    st.markdown("### 📈 Market Overview")
    c1, c2, c3, c4 = st.columns(4)
    if nifty_df is not None and len(nifty_df) > 1:
        nn = nifty_df["Close"].iloc[-1]; np_ = nifty_df["Close"].iloc[-2]
        c1.metric("Nifty 50", f"{nn:,.0f}", f"{((nn-np_)/np_)*100:+.2f}%")
    vix_df = fetch_india_vix()
    if vix_df is not None and len(vix_df) > 0:
        vv = vix_df["Close"].iloc[-1]
        c2.metric("India VIX", f"{vv:.1f}", "Low Fear" if vv < 15 else ("Moderate" if vv < 20 else "High Fear"))
    else: vix_df = pd.DataFrame()
    c3.metric("Universe", f"{len(price_data)} stocks")
    c4.metric("Portfolio", f"{len(portfolio)} picks")

    # Market Regime
    regime = detect_market_regime(nifty_df, vix_df)
    regime_html = (
        f'<div class="pick-card" style="border-left:4px solid {regime["color"]};">'
        f'<span style="font-size:1.5rem;">{regime["emoji"]}</span> '
        f'<strong>{regime["name"]}</strong> · Size: {regime["position_size_multiplier"]:.0%}<br>'
        f'<span style="font-size:0.85rem;">{regime["recommendation"]}</span>'
        f'<div class="sub-score-row" style="margin-top:6px;">'
    )
    for stxt, stype in regime.get("signals", []):
        regime_html += f'<span class="signal-badge {stype}">{stxt}</span>'
    regime_html += '</div></div>'
    st.markdown(regime_html, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO — by funnel
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### 🏆 Your 15-Stock Portfolio")
st.caption(f"🔵 {ALLOCATION['stocks_per_bucket']['large']} Large Caps (30%) · 🟣 {ALLOCATION['stocks_per_bucket']['mid']} Mid Caps (50%) · 🟠 {ALLOCATION['stocks_per_bucket']['small']} Small Caps (20%)")

def render_pick_card(pick, rank_emoji=""):
    s = pick["composite"]
    sc = "high" if s >= 65 else ("mid" if s >= 50 else "low")
    f = pick.get("details", {}).get("fund", {})
    t = pick.get("details", {}).get("tech", {})
    rs = pick.get("details", {}).get("rs", {})
    ei = pick.get("exit", {})
    fn = pick["funnel"]
    fn_tag = f'<span class="funnel-tag {fn}">{"Large" if fn == "large" else ("Mid" if fn == "mid" else "Small")}</span>'

    # RS badge
    rs3 = rs.get("rs_3m")
    if rs3 is not None:
        rs_class = "bullish" if rs3 > 2 else ("bearish" if rs3 < -2 else "neutral")
        rs_badge = f'<span class="signal-badge {rs_class}">RS {rs3:+.1f}% vs Nifty</span>'
    else: rs_badge = ""

    # Quality badge
    qc = f.get("quality_checks", [])
    pq = f.get("passes_quality_gate", False)
    q_badge = f'<span class="signal-badge bullish">✅ Quality {len(qc)}/10</span>' if pq else (f'<span class="signal-badge neutral">Quality {len(qc)}/10</span>' if qc else "")

    # Lynch Ratio badge — displayed for large caps, advisory label for others
    lynch_r = f.get("lynch_ratio")
    lynch_weighted = f.get("lynch_weighted", False)
    if lynch_r is not None:
        lynch_color = "bullish" if lynch_r < 1.0 else ("neutral" if lynch_r < 2.0 else "bearish")
        lynch_label = "✦ " if lynch_weighted else "~"  # ✦ = scored, ~ = advisory only
        lynch_badge = f'<span class="signal-badge {lynch_color}">{lynch_label}Lynch {lynch_r:.2f}</span>'
    else:
        lynch_badge = ""

    # Sentiment badge
    sent = pick.get("details", {}).get("sentiment", {})
    sent_signal = sent.get("signal", "")
    sent_score = pick.get("sentiment", 50)
    if sent_signal and sent_signal != "neutral":
        sent_badge = f'<span class="signal-badge {sent_signal}">📰 {sent_signal.title()} {sent_score:.0f}</span>'
    elif sent_signal == "neutral" and sent.get("summary"):
        sent_badge = f'<span class="signal-badge neutral">📰 Neutral {sent_score:.0f}</span>'
    else:
        sent_badge = ""

    price_str = f"· ₹{pick['current_price']:,.2f}" if pick.get('current_price') else ""

    card = (
        f'<div class="pick-card">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">'
        f'<div>'
        f'<div class="pick-name">{rank_emoji} {pick["name"]}</div>'
        f'<div class="pick-meta">{fn_tag} {pick["ticker"].replace(".NS","")} · {pick["sector"]} {price_str}</div>'
        f'</div>'
        f'<div style="text-align:right;">'
        f'<div class="score-badge {sc}">{s:.0f}</div>'
        f'<div style="font-size:0.6rem;opacity:0.5;text-transform:uppercase;">Score</div>'
        f'</div></div>'
        f'<div class="sub-score-row">'
        f'<span class="sub-pill">📊 Tech {pick["technical"]:.0f}</span>'
        f'<span class="sub-pill">📋 Fund {pick["fundamental"]:.0f}</span>'
        f'<span class="sub-pill">🏛️ Inst {pick["institutional"]:.0f}</span>'
        f'<span class="sub-pill">🛡️ Risk {pick["risk"]:.0f}</span>'
        f'<span class="sub-pill">🚀 RS {pick.get("relative_str", 50):.0f}</span>'
        f'{rs_badge}{q_badge}{lynch_badge}{sent_badge}'
        f'</div>'
        f'<div class="target-grid">'
        f'<div class="target-box"><div class="target-label">Entry</div><div class="target-value">₹{ei.get("entry_price",0):,.2f}</div></div>'
        f'<div class="target-box"><div class="target-label">Stop Loss</div><div class="target-value">₹{ei.get("stop_loss",0):,.2f}</div><div class="target-pct red">-{ei.get("stop_loss_pct",0):.1f}%</div></div>'
        f'<div class="target-box"><div class="target-label">Target 1</div><div class="target-value">₹{ei.get("target_1",0):,.2f}</div><div class="target-pct green">+{ei.get("target_1_pct",0):.1f}%</div></div>'
        f'<div class="target-box"><div class="target-label">Target 2</div><div class="target-value">₹{ei.get("target_2",0):,.2f}</div><div class="target-pct green">+{ei.get("target_2_pct",0):.1f}%</div></div>'
        f'<div class="target-box"><div class="target-label">R:R</div><div class="target-value">{ei.get("risk_reward",0):.1f}x</div></div>'
        f'</div>'
        + _price_spectrum_bar(ei, pick.get("current_price", 0))
        + f'<div><span class="hold-badge">⏱️ {ei.get("hold_days_min","?")}–{ei.get("hold_days_max","?")}d · {ei.get("hold_label","")}</span></div>'
        f'</div>'
    )
    st.markdown(card, unsafe_allow_html=True)

# Show portfolio grouped by funnel
tab_all, tab_large, tab_mid, tab_small = st.tabs(["📊 Full Portfolio", "🔵 Large Cap", "🟣 Mid Cap", "🟠 Small Cap"])

with tab_all:
    emojis = ["🥇","🥈","🥉"] + [f"#{i}" for i in range(4, 20)]
    for i, p in enumerate(portfolio):
        render_pick_card(p, emojis[i] if i < len(emojis) else "")

with tab_large:
    st.caption(f"Top {ALLOCATION['stocks_per_bucket']['large']} from {len(picks_by_tier['large'])} large caps · Focus: Quality & Cash Flow")
    for p in picks_by_tier["large"][:ALLOCATION["stocks_per_bucket"]["large"]]:
        render_pick_card(p)

with tab_mid:
    st.caption(f"Top {ALLOCATION['stocks_per_bucket']['mid']} from {len(picks_by_tier['mid'])} mid caps · Focus: Growth & Relative Strength")
    for p in picks_by_tier["mid"][:ALLOCATION["stocks_per_bucket"]["mid"]]:
        render_pick_card(p)

with tab_small:
    st.caption(f"Top {ALLOCATION['stocks_per_bucket']['small']} from {len(picks_by_tier['small'])} small caps · Focus: Momentum & Growth")
    for p in picks_by_tier["small"][:ALLOCATION["stocks_per_bucket"]["small"]]:
        render_pick_card(p)

# ── Full Rankings ────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### 📋 Full Rankings")

def _sparkline(ticker):
    """Return the last 30 daily closes for ticker as a list of floats, or None."""
    df = price_data.get(ticker)
    if df is None or "Close" not in df.columns or len(df) == 0:
        return None
    closes = df["Close"].dropna().tail(30).tolist()
    return closes if len(closes) >= 2 else None

rdf = pd.DataFrame([{
    "Rank": i+1, "Stock": r["name"], "Ticker": r["ticker"].replace(".NS",""),
    "Funnel": r["funnel"].title(), "Sector": r["sector"],
    "Score": r["composite"], "Tech": r["technical"], "Fund": r["fundamental"],
    "Inst": r["institutional"], "Risk": r["risk"], "RS": r.get("relative_str", 50),
    "Lynch": r.get("details", {}).get("fund", {}).get("lynch_ratio"),
    "Sentiment": r.get("sentiment") or _sentiment_data.get(r["ticker"], {}).get("score"),
    "Trend (30d)": _sparkline(r["ticker"]),
    "Target 1": f"₹{r['exit']['target_1']:,.0f}" if r.get("exit",{}).get("target_1") else "—",
} for i, r in enumerate(all_ranked)])

# ── Sort controls ─────────────────────────────────────────────────────────────
_SORTABLE = ["Score", "Tech", "Fund", "Inst", "Risk", "RS", "Lynch",
             "Stock", "Ticker", "Funnel", "Sector", "Rank"]
_sc1, _sc2, _sc3 = st.columns([3, 1, 4])
_sort_col = _sc1.selectbox("Sort by", _SORTABLE, index=0, key="tbl_sort_col", label_visibility="collapsed")
_sort_asc = _sc2.radio("Order", ["↓ Desc", "↑ Asc"], index=0, key="tbl_sort_dir",
                       label_visibility="collapsed", horizontal=False) == "↑ Asc"
_sc3.caption(f"Sorted by **{_sort_col}** {'ascending ↑' if _sort_asc else 'descending ↓'}  ·  "
             f"Click any column header to also sort interactively")

_numeric_cols = {"Score", "Tech", "Fund", "Inst", "Risk", "RS", "Lynch", "Rank"}
if _sort_col in _numeric_cols:
    rdf = rdf.sort_values(_sort_col, ascending=_sort_asc, na_position="last").reset_index(drop=True)
else:
    rdf = rdf.sort_values(_sort_col, ascending=_sort_asc, key=lambda s: s.str.lower()).reset_index(drop=True)

st.dataframe(rdf, hide_index=True, use_container_width=True, column_config={
    "Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
    "RS":    st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
    "Lynch": st.column_config.NumberColumn(
        "Lynch ✦L",
        help="Lynch Ratio (PEGY) = P/E ÷ (EPS Growth% + Div Yield%). "
             "<1 undervalued · 1–2 fair · >2 expensive. "
             "✦ Scored in composite for Large Cap only.",
        format="%.2f",
    ),
    "Sentiment": st.column_config.ProgressColumn(
        "📰 Sentiment",
        help="Ollama news sentiment score (0=bearish · 50=neutral · 100=bullish). "
             "Sourced from Indian market RSS feeds. Run sentiment scan to populate.",
        min_value=0, max_value=100, format="%.0f",
    ),
    "Trend (30d)": st.column_config.LineChartColumn(
        "Trend (30d)",
        help="Last 30 trading days of closing prices.",
        y_min=0,
    ),
})

# ── Position Sizing ──────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### 💰 Position Sizing")
capital = st.number_input("Capital (₹)", min_value=10000, value=POSITION_CONFIG["default_capital"], step=50000)
regime = detect_market_regime(nifty_df, vix_df if 'vix_df' in dir() else pd.DataFrame())
adj_risk = POSITION_CONFIG["risk_per_trade_pct"] * regime.get("position_size_multiplier", 1.0)
if regime.get("position_size_multiplier", 1) < 1:
    st.caption(f"⚠️ Risk adjusted to {adj_risk:.1f}% due to {regime['name']} regime")

sized, cash = size_portfolio(portfolio, capital, adj_risk, POSITION_CONFIG["max_position_pct"])
for sp in sized:
    s = sp["sizing"]; fn = sp["funnel"]
    st.markdown(
        f'<div class="pick-card"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;">'
        f'<div><span class="funnel-tag {fn}">{"L" if fn=="large" else ("M" if fn=="mid" else "S")}</span>'
        f'<strong>{sp["name"]}</strong> <span style="opacity:0.6;font-size:0.85rem;">({sp["ticker"].replace(".NS","")})</span></div>'
        f'<div style="text-align:right;"><div style="font-size:1.1rem;font-weight:700;">{s["shares"]} shares</div>'
        f'<div style="font-size:0.75rem;opacity:0.6;">₹{s["investment"]:,.0f} ({s["position_pct"]:.0f}%)</div>'
        f'</div></div></div>', unsafe_allow_html=True)
st.caption(f"💵 Cash remaining: ₹{cash:,.0f}")

# ── Backtest ─────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### 🧪 Backtest")

# Compute the actual available date range from cached price data
_all_dates = []
for _df in price_data.values():
    if _df is not None and len(_df) > 0:
        _all_dates.extend(_df.index.tolist())
_bt_min = pd.Timestamp(min(_all_dates)).date() if _all_dates else datetime(2023, 1, 1).date()
_bt_max = pd.Timestamp(max(_all_dates)).date() if _all_dates else datetime.now().date()
st.caption(f"📅 Available data: **{_bt_min}** → **{_bt_max}** ({(_bt_max - _bt_min).days} days)")

bc1, bc2, bc3, bc4 = st.columns(4)
bt_start = bc1.date_input(
    "Start Date",
    value=_bt_min,
    min_value=_bt_min,
    max_value=_bt_max,
    key="bt_start",
)
bt_end = bc2.date_input(
    "End Date",
    value=_bt_max,
    min_value=_bt_min,
    max_value=_bt_max,
    key="bt_end",
)
bt_r = bc3.selectbox("Rebalance", [21, 42, 63], index=2, format_func=lambda x: f"{x}d (~{x//21}mo)")
bt_n = bc4.selectbox("Picks", [5, 10, 15], index=2)

if st.button("🚀 Run Backtest", use_container_width=True, type="primary"):
    if bt_start >= bt_end:
        st.error("Start date must be before end date.")
    else:
        with st.status("Running backtest...", expanded=True) as bst:
            st.write(f"Simulating {bt_start} → {bt_end}, {bt_n} picks, rebalance every {bt_r}d...")
            bt = run_backtest(price_data, fundamentals,
                              start_date=bt_start, end_date=bt_end,
                              rebalance_days=bt_r, top_n=bt_n, initial_capital=capital)
            bst.update(label="✅ Done!", state="complete", expanded=False)

        if "error" in bt:
            st.error(bt["error"])
        else:
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Strategy", f"{bt['total_return_pct']:+.1f}%")
            if bt.get("nifty_return_pct") is not None:
                r2.metric("Nifty", f"{bt['nifty_return_pct']:+.1f}%")
                r3.metric("Alpha", f"{bt.get('alpha',0):+.1f}%")
            r4.metric("Max DD", f"-{bt['max_drawdown_pct']:.1f}%")

            r5, r6, r7, r8 = st.columns(4)
            r5.metric("Win Rate", f"{bt['win_rate']:.0f}%")
            r6.metric("Profit Factor", f"{bt['profit_factor']:.1f}x")
            r7.metric("Final Value", f"₹{bt['final_equity']:,.0f}")
            r8.metric("Trades", bt["total_trades"])

            if bt.get("equity_curve"):
                eq = pd.DataFrame(bt["equity_curve"])
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=eq["date"], y=eq["equity"], name="Strategy",
                                         line=dict(color="#6366f1", width=2.5), fill="tozeroy",
                                         fillcolor="rgba(99,102,241,0.1)"))
                if bt.get("nifty_curve"):
                    neq = pd.DataFrame(bt["nifty_curve"])
                    fig.add_trace(go.Scatter(x=neq["date"], y=neq["nifty_equity"], name="Nifty B&H",
                                             line=dict(color="#9ca3af", width=1.5, dash="dot")))
                fig.update_layout(title="Equity Curve", height=400,
                                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)

# ── Footer ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"🎯 NiftyScout v4 · Alpha Engine · {len(active_tickers)} stocks · "
           f"{datetime.now().strftime('%Y-%m-%d %H:%M')} · Not financial advice")
