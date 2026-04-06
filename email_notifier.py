"""
Email Notifier — NiftyScout v4
Sends a stunning dark-themed HTML email with all 15 picks organised by tier.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

from config import EMAIL_CONFIG


def _get_credentials():
    """
    Credential lookup order (first match wins):
      1. st.secrets["email"] — Streamlit Cloud or .streamlit/secrets.toml
      2. NIFTYSCOUT_EMAIL / NIFTYSCOUT_EMAIL_PASSWORD env vars (loaded from .env by config.py)
      3. EMAIL_CONFIG hardcoded values (legacy fallback, intentionally left blank)
    """
    sender = password = ""

    # 1 — Streamlit secrets
    try:
        import streamlit as st
        _s = st.secrets.get("email", {})
        sender = _s.get("sender_email", "")
        password = _s.get("sender_password", "")
    except Exception:
        pass

    # 2 — Environment variables
    if not sender:
        sender = os.environ.get("NIFTYSCOUT_EMAIL", "")
    if not password:
        password = os.environ.get("NIFTYSCOUT_EMAIL_PASSWORD", "")

    # 3 — Config fallback (empty by default; kept for backwards compat)
    if not sender:
        sender = EMAIL_CONFIG.get("sender_email", "")
    if not password:
        password = EMAIL_CONFIG.get("sender_password", "")

    return sender, password, EMAIL_CONFIG["recipients"]


def is_email_configured() -> bool:
    sender, password, _ = _get_credentials()
    return bool(sender and password)


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _score_ring(score: float) -> str:
    """Circular score badge."""
    if score >= 70:
        color = "#22c55e"
    elif score >= 50:
        color = "#f59e0b"
    else:
        color = "#ef4444"
    # Use a nested table cell for vertical centering — flexbox is stripped by
    # Gmail and Outlook, making the number fall to the top of the circle.
    return (
        f'<table cellpadding="0" cellspacing="0" style="float:right;margin-left:12px;">'
        f'<tr><td width="52" height="52" align="center" valign="middle"'
        f' style="width:52px;height:52px;border-radius:50%;border:3px solid {color};'
        f'background:rgba(0,0,0,0.3);text-align:center;vertical-align:middle;">'
        f'<span style="font-size:15px;font-weight:900;color:{color};line-height:1;">{score:.0f}</span>'
        f'</td></tr></table>'
    )


def _mini_bar(score: float, label: str) -> str:
    """Compact score bar with label."""
    fill = int((score / 100) * 80)
    if score >= 70:
        color = "#22c55e"
    elif score >= 50:
        color = "#f59e0b"
    else:
        color = "#ef4444"
    return (
        f'<td style="padding:3px 8px 3px 0;white-space:nowrap;">'
        f'<span style="font-size:10px;color:#94a3b8;text-transform:uppercase;'
        f'letter-spacing:0.5px;">{label}</span><br>'
        f'<div style="background:#1e293b;border-radius:3px;width:80px;height:6px;margin-top:3px;display:inline-block;">'
        f'<div style="background:{color};border-radius:3px;width:{fill}px;height:6px;"></div>'
        f'</div>'
        f'<span style="font-size:11px;font-weight:700;color:{color};margin-left:4px;">{score:.0f}</span>'
        f'</td>'
    )


def _badge(text: str, bg: str, fg: str) -> str:
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 7px;border-radius:20px;'
        f'font-size:10px;font-weight:700;letter-spacing:0.3px;margin-right:4px;">{text}</span>'
    )


def _pick_card(pick: dict, rank: int, tier_color: str) -> str:
    """Render one stock card for the email."""
    ei = pick.get("exit", {})
    details = pick.get("details", {})
    fund = details.get("fund", {})
    tech = details.get("tech", {})
    inst = details.get("inst", {})
    rs = details.get("rs", {})

    # Composite score ring
    score_ring = _score_ring(pick["composite"])

    # Funnel label
    fn = pick.get("funnel", "mid")
    funnel_labels = {"large": "Large Cap", "mid": "Mid Cap", "small": "Small Cap"}
    funnel_colors = {"large": "#3b82f6", "mid": "#8b5cf6", "small": "#f97316"}
    funnel_badge = _badge(funnel_labels.get(fn, fn), funnel_colors.get(fn, "#6b7280") + "22", funnel_colors.get(fn, "#6b7280"))

    # Sector badge
    sector = pick.get("sector", "—")
    sector_badge = _badge(sector, "#1e293b", "#94a3b8")

    # Quality gate
    qc = fund.get("quality_checks", [])
    passes = fund.get("passes_quality_gate", False)
    if passes:
        quality_badge = _badge(f"✓ Quality {len(qc)}/10", "#14532d", "#4ade80")
    elif qc:
        quality_badge = _badge(f"Quality {len(qc)}/10", "#292524", "#a8a29e")
    else:
        quality_badge = ""

    # Relative strength badge
    rs3 = rs.get("rs_3m")
    if rs3 is not None:
        rs_color = ("#4ade80", "#14532d") if rs3 > 2 else (("#f87171", "#450a0a") if rs3 < -2 else ("#94a3b8", "#1e293b"))
        rs_badge = _badge(f"RS {rs3:+.1f}% vs Nifty", rs_color[1], rs_color[0])
    else:
        rs_badge = ""

    # Lynch Ratio badge (✦ = weighted in score for large cap, ~ = advisory for others)
    lynch_r = fund.get("lynch_ratio")
    lynch_weighted = fund.get("lynch_weighted", False)
    if lynch_r is not None:
        if lynch_r < 1.0:
            lynch_badge = _badge(f"{'✦' if lynch_weighted else '~'}Lynch {lynch_r:.2f}", "#14532d", "#4ade80")
        elif lynch_r < 2.0:
            lynch_badge = _badge(f"{'✦' if lynch_weighted else '~'}Lynch {lynch_r:.2f}", "#292524", "#a8a29e")
        else:
            lynch_badge = _badge(f"{'✦' if lynch_weighted else '~'}Lynch {lynch_r:.2f}", "#450a0a", "#f87171")
    else:
        lynch_badge = ""

    # MACD / signal badges
    macd = tech.get("macd_signal", "")
    if macd == "bullish":
        macd_badge = _badge("MACD ↑", "#14532d", "#4ade80")
    elif macd == "bearish":
        macd_badge = _badge("MACD ↓", "#450a0a", "#f87171")
    else:
        macd_badge = ""

    # 200 DMA
    above200 = tech.get("above_200dma")
    if above200 is True:
        dma_badge = _badge("▲ 200 DMA", "#14532d", "#4ade80")
    elif above200 is False:
        dma_badge = _badge("▼ 200 DMA", "#450a0a", "#f87171")
    else:
        dma_badge = ""

    price = pick.get("current_price", 0) or 0
    entry = ei.get("entry_price", 0) or 0
    sl = ei.get("stop_loss", 0) or 0
    t1 = ei.get("target_1", 0) or 0
    t2 = ei.get("target_2", 0) or 0
    sl_pct = ei.get("stop_loss_pct", 0) or 0
    t1_pct = ei.get("target_1_pct", 0) or 0
    t2_pct = ei.get("target_2_pct", 0) or 0
    rr = ei.get("risk_reward", 0) or 0
    hold_label = ei.get("hold_label", "—")
    hold_min = ei.get("hold_days_min", "?")
    hold_max = ei.get("hold_days_max", "?")

    rank_emojis = {1: "🥇", 2: "🥈", 3: "🥉"}
    rank_str = rank_emojis.get(rank, f"#{rank}")

    return f"""
<div style="background:#0f172a;border:1px solid {tier_color}33;border-left:3px solid {tier_color};
     border-radius:10px;padding:18px;margin-bottom:12px;overflow:hidden;">

  <!-- Name row -->
  <div style="overflow:hidden;margin-bottom:10px;">
    {score_ring}
    <div style="overflow:hidden;">
      <div style="font-size:16px;font-weight:800;color:#f1f5f9;line-height:1.2;">
        {rank_str} {pick['name']}
      </div>
      <div style="margin-top:4px;">
        {funnel_badge}{sector_badge}
        <span style="font-size:10px;color:#475569;margin-left:4px;">{pick['ticker'].replace('.NS','')}</span>
      </div>
      <div style="margin-top:5px;">
        {quality_badge}{rs_badge}{lynch_badge}{macd_badge}{dma_badge}
      </div>
    </div>
  </div>

  <!-- Score bars -->
  <table style="border-collapse:collapse;margin-bottom:12px;">
    <tr>
      {_mini_bar(pick['technical'], 'Tech')}
      {_mini_bar(pick['fundamental'], 'Fund')}
      {_mini_bar(pick['institutional'], 'Inst')}
      {_mini_bar(pick['risk'], 'Risk')}
      {_mini_bar(pick.get('relative_str', 50), 'RS')}
    </tr>
  </table>

  <!-- Entry / SL / Targets -->
  <table style="width:100%;border-collapse:collapse;background:#0a0f1e;border-radius:8px;overflow:hidden;">
    <tr style="background:#111827;">
      <td style="padding:6px 10px;font-size:10px;color:#94a3b8;text-align:center;text-transform:uppercase;letter-spacing:0.5px;">Price</td>
      <td style="padding:6px 10px;font-size:10px;color:#ef4444;text-align:center;text-transform:uppercase;letter-spacing:0.5px;">Stop Loss</td>
      <td style="padding:6px 10px;font-size:10px;color:#22c55e;text-align:center;text-transform:uppercase;letter-spacing:0.5px;">Target 1</td>
      <td style="padding:6px 10px;font-size:10px;color:#22c55e;text-align:center;text-transform:uppercase;letter-spacing:0.5px;">Target 2</td>
      <td style="padding:6px 10px;font-size:10px;color:#a78bfa;text-align:center;text-transform:uppercase;letter-spacing:0.5px;">R:R</td>
    </tr>
    <tr>
      <td style="padding:8px 10px;text-align:center;">
        <div style="font-size:14px;font-weight:700;color:#f1f5f9;">₹{price:,.0f}</div>
      </td>
      <td style="padding:8px 10px;text-align:center;">
        <div style="font-size:14px;font-weight:700;color:#f87171;">₹{sl:,.0f}</div>
        <div style="font-size:10px;color:#ef4444;">−{sl_pct:.1f}%</div>
      </td>
      <td style="padding:8px 10px;text-align:center;">
        <div style="font-size:14px;font-weight:700;color:#4ade80;">₹{t1:,.0f}</div>
        <div style="font-size:10px;color:#22c55e;">+{t1_pct:.1f}%</div>
      </td>
      <td style="padding:8px 10px;text-align:center;">
        <div style="font-size:14px;font-weight:700;color:#4ade80;">₹{t2:,.0f}</div>
        <div style="font-size:10px;color:#22c55e;">+{t2_pct:.1f}%</div>
      </td>
      <td style="padding:8px 10px;text-align:center;">
        <div style="font-size:14px;font-weight:700;color:#c4b5fd;">{rr:.1f}x</div>
      </td>
    </tr>
  </table>

  <div style="margin-top:8px;font-size:11px;color:#64748b;">
    ⏱ Hold: {hold_min}–{hold_max} days · {hold_label}
  </div>
</div>
"""


def _tier_section(title: str, subtitle: str, picks: list, color: str, start_rank: int) -> str:
    if not picks:
        return ""
    cards = "".join(_pick_card(p, start_rank + i, color) for i, p in enumerate(picks))
    return f"""
<div style="margin-bottom:8px;">
  <div style="background:linear-gradient(90deg,{color}22,transparent);border-left:3px solid {color};
       border-radius:0 8px 8px 0;padding:10px 16px;margin-bottom:12px;">
    <div style="font-size:15px;font-weight:800;color:{color};">{title}</div>
    <div style="font-size:11px;color:#64748b;margin-top:2px;">{subtitle}</div>
  </div>
  {cards}
</div>
"""


def build_email_html(picks_by_tier: dict, dashboard_url: str = None) -> str:
    """Build the full stunning HTML email."""
    today = datetime.now().strftime("%A, %d %B %Y")
    generated = datetime.now().strftime("%H:%M IST")

    large = picks_by_tier.get("large", [])
    mid = picks_by_tier.get("mid", [])
    small = picks_by_tier.get("small", [])
    total = len(large) + len(mid) + len(small)

    # Tier sections (ranks are global across tiers for simplicity)
    sections = (
        _tier_section("🔵 Large Cap Anchors", f"{len(large)} picks · 30% allocation · Quality & Cash Flow focus", large, "#3b82f6", 1)
        + _tier_section("🟣 Mid Cap Growth Engine", f"{len(mid)} picks · 50% allocation · Growth & Momentum focus", mid, "#8b5cf6", len(large) + 1)
        + _tier_section("🟠 Small Cap Alpha Boosters", f"{len(small)} picks · 20% allocation · High-growth potential", small, "#f97316", len(large) + len(mid) + 1)
    )

    dashboard_btn = ""
    if dashboard_url:
        dashboard_btn = f"""
<div style="text-align:center;margin:28px 0;">
  <a href="{dashboard_url}"
     style="background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#ffffff;
            padding:14px 36px;border-radius:8px;text-decoration:none;
            font-weight:700;font-size:14px;letter-spacing:0.5px;
            display:inline-block;">
    📊 Open Full Dashboard
  </a>
</div>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>NiftyScout — {today}</title>
</head>
<body style="margin:0;padding:0;background:#060912;
     font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
<div style="max-width:640px;margin:0 auto;padding:16px;">

  <!-- ── HEADER ── -->
  <div style="background:linear-gradient(135deg,#0f0f2e 0%,#1a0a3e 40%,#0a1628 100%);
       border:1px solid #1e1b4b;border-radius:16px;padding:36px 32px;
       text-align:center;margin-bottom:16px;">
    <div style="font-size:48px;line-height:1;margin-bottom:12px;">🎯</div>
    <div style="font-size:36px;font-weight:900;color:#ffffff;letter-spacing:-1.5px;">NiftyScout</div>
    <div style="font-size:12px;color:#818cf8;letter-spacing:3px;
         text-transform:uppercase;margin-top:6px;">Alpha Engine · Daily Portfolio</div>
    <div style="display:inline-block;background:rgba(99,102,241,0.15);
         border:1px solid rgba(99,102,241,0.35);border-radius:20px;
         padding:6px 22px;margin-top:14px;">
      <span style="color:#c7d2fe;font-size:13px;font-weight:600;">{today}</span>
    </div>
  </div>

  <!-- ── SUMMARY ROW ── -->
  <table style="width:100%;border-collapse:collapse;background:#0f172a;
         border:1px solid #1e293b;border-radius:12px;overflow:hidden;
         margin-bottom:16px;">
    <tr>
      <td style="padding:18px;text-align:center;border-right:1px solid #1e293b;">
        <div style="font-size:30px;font-weight:900;color:#60a5fa;">{len(large)}</div>
        <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:2px;">Large Cap</div>
        <div style="font-size:11px;color:#3b82f6;margin-top:3px;font-weight:600;">30% Capital</div>
      </td>
      <td style="padding:18px;text-align:center;border-right:1px solid #1e293b;">
        <div style="font-size:30px;font-weight:900;color:#a78bfa;">{len(mid)}</div>
        <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:2px;">Mid Cap</div>
        <div style="font-size:11px;color:#8b5cf6;margin-top:3px;font-weight:600;">50% Capital</div>
      </td>
      <td style="padding:18px;text-align:center;border-right:1px solid #1e293b;">
        <div style="font-size:30px;font-weight:900;color:#fb923c;">{len(small)}</div>
        <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:2px;">Small Cap</div>
        <div style="font-size:11px;color:#f97316;margin-top:3px;font-weight:600;">20% Capital</div>
      </td>
      <td style="padding:18px;text-align:center;">
        <div style="font-size:30px;font-weight:900;color:#f1f5f9;">{total}</div>
        <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:2px;">Total Picks</div>
        <div style="font-size:11px;color:#94a3b8;margin-top:3px;font-weight:600;">Quarterly Hold</div>
      </td>
    </tr>
  </table>

  <!-- ── PICKS ── -->
  {sections}

  <!-- ── DASHBOARD BUTTON ── -->
  {dashboard_btn}

  <!-- ── FOOTER ── -->
  <div style="text-align:center;padding:20px 0 8px;border-top:1px solid #1e293b;margin-top:8px;">
    <div style="font-size:11px;color:#475569;line-height:1.7;">
      ⚠️ This is a <strong style="color:#64748b;">decision-support tool</strong>, not financial advice.<br>
      Always do your own research before investing.<br>
      <span style="color:#334155;">NiftyScout · Data via Yahoo Finance (EOD) + Screener.in · {generated}</span>
    </div>
  </div>

</div>
</body>
</html>"""


def send_picks_email(picks_by_tier: dict, dashboard_url: str = None, recipients: list = None) -> tuple[bool, str]:
    """
    Send the daily picks email.
    picks_by_tier: dict with keys 'large', 'mid', 'small' — each a list of pick dicts.
    recipients: optional override list; falls back to EMAIL_CONFIG['recipients'].
    Returns (success: bool, message: str).
    """
    sender, password, config_recipients = _get_credentials()
    recipients = recipients if recipients is not None else config_recipients

    if not sender or not password:
        return False, "Email not configured. Add sender_email and sender_password to EMAIL_CONFIG in config.py"
    if not recipients:
        return False, "No recipients selected."

    today = datetime.now().strftime("%d %b %Y")
    subject = f"🎯 NiftyScout — {today} Portfolio ({sum(len(v) for v in picks_by_tier.values())} picks)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"NiftyScout 🎯 <{sender}>"
    msg["To"] = ", ".join(recipients)

    # Plain text fallback
    plain = f"NiftyScout Daily Picks — {today}\n\n"
    rank = 1
    for tier, label in [("large", "LARGE CAP"), ("mid", "MID CAP"), ("small", "SMALL CAP")]:
        picks = picks_by_tier.get(tier, [])
        if picks:
            plain += f"\n── {label} ──\n"
            for p in picks:
                ei = p.get("exit", {})
                plain += (
                    f"#{rank} {p['name']} ({p['ticker'].replace('.NS','')}) "
                    f"Score:{p['composite']:.0f} ₹{p.get('current_price',0):,.0f} "
                    f"SL:₹{ei.get('stop_loss',0):,.0f} T1:₹{ei.get('target_1',0):,.0f}\n"
                )
                rank += 1
    plain += "\nNot financial advice. Always DYOR."

    html_body = build_email_html(picks_by_tier, dashboard_url)

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
        n = sum(len(v) for v in picks_by_tier.values())
        return True, f"Sent {n} picks to {len(recipients)} recipient(s)"
    except smtplib.SMTPAuthenticationError:
        return False, "Auth failed. Use a Gmail App Password (not your regular password)."
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {e}"
    except Exception as e:
        return False, f"Failed: {e}"
