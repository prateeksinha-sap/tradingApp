# 🎯 NiftyScout — Daily Nifty 50 Stock Picker

A locally-deployed Python app that analyses all Nifty 50 stocks and suggests the top 3 "no-brainer" picks for the day, based on a composite scoring model.

## What It Does

Every time you run it, NiftyScout:
1. Fetches end-of-day price/volume data for all 50 Nifty stocks (via Yahoo Finance)
2. Pulls fundamental data (P/E, debt, ROE, growth, beta)
3. Computes **4 dimension scores** (0–100 each) for every stock
4. Produces a **weighted composite score** and ranks all 50 stocks
5. Shows you the **top 3 picks** with detailed breakdowns, charts, and reasoning

## Scoring Model

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| **Technical** (25%) | RSI, MACD, SMA crossover, volume spike | Is the stock trending up with conviction? |
| **Fundamental** (25%) | P/E ratio, debt/equity, ROE, earnings growth | Is the company financially strong? |
| **Institutional** (25%) | OBV accumulation, price trend, dividend yield | Are big players buying? |
| **Risk Safety** (25%) | Beta, volatility, drawdown from 52-week high | How risky is this entry? |

Weights are adjustable via sliders in the sidebar.

## Setup (Windows)

### 1. Install Python
Download Python 3.10+ from [python.org](https://python.org). During install, check **"Add Python to PATH"**.

### 2. Clone / Download this project
Put the `nifty-scout` folder anywhere on your machine.

### 3. Open a terminal in the project folder
```
cd C:\path\to\nifty-scout
```

### 4. Create a virtual environment (recommended)
```
python -m venv venv
venv\Scripts\activate
```

### 5. Install dependencies
```
pip install -r requirements.txt
```

### 6. Run the app
```
streamlit run app.py
```

Your browser will open at `http://localhost:8501` with the dashboard.

## Daily Usage

Just run `streamlit run app.py` each day after market close (3:30 PM IST).
The app caches data to avoid redundant API calls.

Click **"Clear Cache & Refresh"** in the sidebar to force a fresh data pull.

## Project Structure

```
nifty-scout/
├── app.py              # Streamlit dashboard (main entry point)
├── config.py           # All settings, tickers, weights, thresholds
├── data_fetcher.py     # Yahoo Finance data download + SQLite caching
├── scoring.py          # The 4-dimension scoring engine
├── email_notifier.py   # HTML email builder + Gmail SMTP sender
├── tunnel.py           # ngrok tunnel manager for mobile access
├── requirements.txt    # Python dependencies
├── data/               # SQLite cache (auto-created)
│   └── niftyscout.db
└── README.md
```

## 📧 Email Setup (Gmail)

NiftyScout can email today's top picks to up to 3 people automatically.

### Step 1: Create a Gmail App Password
1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. You may need to enable 2-Factor Authentication first
3. Select **Mail** → **Windows Computer** → **Generate**
4. Copy the 16-character password (e.g., `abcd efgh ijkl mnop`)

### Step 2: Configure in `config.py`
```python
EMAIL_CONFIG = {
    "sender_email":  "you@gmail.com",
    "sender_password": "abcd efgh ijkl mnop",  # App Password, NOT your Gmail password
    "recipients": [
        "friend1@example.com",
        "friend2@example.com",
        "friend3@example.com",
    ],
    "auto_send_after_analysis": True,  # Sends automatically when app loads
}
```

### How It Works
- **Auto-send**: When `auto_send_after_analysis` is `True`, an email is sent once per session when the analysis completes
- **Manual send**: Click **"📤 Send Email Now"** in the sidebar anytime
- The email is a polished HTML with score bars, signals, and a link to the dashboard

## 📱 Mobile Access (ngrok)

Access the dashboard from your phone — anywhere, not just on Wi-Fi.

### Step 1: Install ngrok
1. Sign up free at [ngrok.com](https://ngrok.com/signup)
2. Download from [ngrok.com/download](https://ngrok.com/download)
3. Unzip `ngrok.exe` to a folder and add to your system PATH

### Step 2: Authenticate (one-time)
```
ngrok config add-authtoken YOUR_TOKEN_FROM_DASHBOARD
```

### Step 3: Enable in `config.py`
```python
NGROK_CONFIG = {
    "auth_token": "your_token_here",
    "enabled": True,
}
```

### Step 4: Run the app
The tunnel starts automatically. A public URL (like `https://abc123.ngrok-free.app`) appears in the sidebar — open it on your phone.

You can also click **"▶️ Start Tunnel Now"** in the sidebar without changing config.

> **Note**: Free ngrok gives you a new URL each time. Paid plans ($8/mo) give a fixed subdomain.

## Customisation

- **Change weights**: Use sidebar sliders, or edit `WEIGHTS` in `config.py`
- **Change stock universe**: Edit `NIFTY_50_TICKERS` in `config.py`
- **Adjust thresholds**: Tweak `TECH_CONFIG`, `FUND_CONFIG`, `RISK_CONFIG` in `config.py`
- **Add more indicators**: Extend `compute_technical_score()` in `scoring.py`

## Limitations & Disclaimer

- Data is **end-of-day** (not real-time) from Yahoo Finance
- Fundamental data from yfinance can occasionally be missing or stale
- FII/DII flow data is approximated via OBV (not actual exchange data)
- **This is NOT financial advice.** It's a decision-support tool. Always do your own research.

## Future Improvements

- [x] Email daily picks to multiple recipients
- [x] Mobile access via ngrok tunnel
- [ ] Add actual FII/DII flow scraping from NSE/MoneyControl
- [ ] Add screener.in scraping for promoter holding data
- [ ] Backtesting module to validate the scoring model on historical data
- [ ] Telegram bot integration for daily alerts
- [ ] Fixed ngrok subdomain for permanent mobile URL
