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
from scoring import rank_stocks
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

    # Initialise recipient list from config
    if "email_recipients" not in st.session_state:
        st.session_state["email_recipients"] = list(EMAIL_CONFIG.get("recipients", []))

    # Add a new recipient
    with st.form("add_recipient_form", clear_on_submit=True):
        new_email = st.text_input("Add recipient", placeholder="friend@gmail.com", label_visibility="collapsed")
        if st.form_submit_button("➕ Add", use_container_width=True):
            new_email = new_email.strip()
            if new_email and "@" in new_email and new_email not in st.session_state["email_recipients"]:
                st.session_state["email_recipients"].append(new_email)
            elif new_email in st.session_state["email_recipients"]:
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

# ── Header ───────────────────────────────────────────────────────────────────
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

def _price_spectrum_bar(ei: dict, current_price: float) -> str:
    """
    Returns an HTML string: a red→amber→green gradient bar spanning
    stop_loss (left) to target_2 (right), with a white dot marking current_price.
    Returns an empty string when the values are missing or degenerate.
    """
    sl   = ei.get("stop_loss",  0) or 0
    t1   = ei.get("target_1",   0) or 0
    t2   = ei.get("target_2",   0) or 0
    price = current_price or 0

    # Need a non-degenerate range to draw anything meaningful
    span = t2 - sl
    if span <= 0 or sl <= 0 or t2 <= 0:
        return ""

    # Percentage positions along the bar (0–100), clamped
    t1_pct    = max(0, min(100, (t1    - sl) / span * 100))
    price_pct = max(0, min(100, (price - sl) / span * 100))

    # Gradient: red at 0% → amber at T1 position → green at 100%
    gradient = (
        f"linear-gradient(to right, "
        f"#ef4444 0%, "
        f"#f59e0b {t1_pct:.1f}%, "
        f"#22c55e 100%)"
    )

    # Price label: show above the dot, flipped to stay inside bar edges
    label_align = "right" if price_pct > 85 else ("left" if price_pct < 15 else "center")
    label_transform = {
        "right":  "translateX(-100%)",
        "left":   "translateX(0%)",
        "center": "translateX(-50%)",
    }[label_align]

    return f"""
<div style="margin:12px 0 4px;padding:0 2px;">
  <!-- bar track -->
  <div style="position:relative;height:8px;border-radius:6px;background:{gradient};
              box-shadow:inset 0 1px 3px rgba(0,0,0,0.4);">

    <!-- T1 tick -->
    <div style="position:absolute;top:0;bottom:0;left:{t1_pct:.1f}%;
                width:1px;background:rgba(255,255,255,0.25);"></div>

    <!-- current price dot -->
    <div style="position:absolute;top:50%;left:{price_pct:.1f}%;
                transform:translate(-50%,-50%);
                width:13px;height:13px;border-radius:50%;
                background:#ffffff;
                box-shadow:0 0 8px rgba(255,255,255,0.7),0 0 0 2px rgba(15,23,42,0.9);
                z-index:2;">
    </div>

    <!-- price label above dot -->
    <div style="position:absolute;bottom:14px;left:{price_pct:.1f}%;
                transform:{label_transform};
                font-size:0.6rem;font-weight:700;color:#f1f5f9;
                white-space:nowrap;text-shadow:0 1px 3px rgba(0,0,0,0.8);">
      ₹{price:,.0f}
    </div>
  </div>

  <!-- axis labels -->
  <div style="display:flex;justify-content:space-between;margin-top:5px;
              font-size:0.58rem;letter-spacing:0.2px;">
    <span style="color:#f87171;">SL ₹{sl:,.0f}</span>
    <span style="color:#fbbf24;opacity:0.8;">T1 ₹{t1:,.0f}</span>
    <span style="color:#4ade80;">T2 ₹{t2:,.0f}</span>
  </div>
</div>"""


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
