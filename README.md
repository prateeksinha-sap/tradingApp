# NiftyScout v4 — Alpha Engine

A Streamlit dashboard that scores and ranks Indian stocks across three funnels (Large / Mid / Small Cap), generates a 15-stock portfolio with entry, stop-loss, and target levels, and sends a dark-themed HTML email report.

---

## Features

- **3-funnel scoring** — Large (30%), Mid (50%), Small (20%) with separate weight profiles
- **6 scoring dimensions** — Technical, Fundamental, Institutional, Risk, Relative Strength, Sentiment
- **Lynch Ratio (PEGY)** — optional scoring dimension, toggleable in the sidebar
- **PSU filter** — state-owned enterprises excluded by default, opt-in via sidebar
- **Ollama sentiment** — local LLM (llama3.2) analyses Indian market RSS news per stock
- **Dynamic stop losses** — 8% / 12% / 15% caps by funnel
- **Backtest** — custom date range, equity curve vs Nifty benchmark
- **Performance tracker** — log positions, monitor target/SL hits
- **Email report** — dark-themed HTML email with all 15 picks sent to any recipient list
- **SQLite caching** — price (4 h), fundamentals (7 d), screener (7 d), sentiment (24 h)

---

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) (optional — for news sentiment only)

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/prateeksinha-sap/tradingApp.git
cd tradingApp
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure email credentials

Copy the example env file and fill in your Gmail details:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Edit `.env`:

```
NIFTYSCOUT_EMAIL=your-gmail@gmail.com
NIFTYSCOUT_EMAIL_PASSWORD=your-16-char-gmail-app-password
```

**How to get a Gmail App Password:**
1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Enable 2-Factor Authentication if you haven't already
3. Click **Create**, name it "NiftyScout", copy the 16-character code
4. Paste it as `NIFTYSCOUT_EMAIL_PASSWORD` — your regular Gmail password will not work

> `.env` is listed in `.gitignore` and will never be committed to git.

Credentials are resolved in this order at runtime:
1. `.streamlit/secrets.toml` — for Streamlit Cloud deployment
2. `.env` / environment variables — for local development
3. `EMAIL_CONFIG` in `config.py` — intentionally left blank

### 5. (Optional) Set up Ollama for news sentiment

Install Ollama from [ollama.com](https://ollama.com), then pull the model:

```bash
ollama pull llama3.2
```

Ollama must be running when you start the app. The `start.bat` script handles this automatically on Windows. On macOS / Linux, run `ollama serve` in a separate terminal before launching Streamlit.

### 6. Run the app

**Windows** — double-click `start.bat`, or from a terminal:

```
start.bat
```

**macOS / Linux:**

```bash
streamlit run app.py
```

The dashboard opens at `http://localhost:8501`.

---

## Streamlit Cloud Deployment

1. Push your repo to GitHub (`.env` and `.streamlit/secrets.toml` are git-ignored and never committed).
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect your repo.
3. In the app settings, open **Secrets** and add:

```toml
[email]
sender_email = "your-gmail@gmail.com"
sender_password = "your-16-char-app-password"
```

> Ollama sentiment will show as offline on Streamlit Cloud (it requires a local process). All other features work normally.

---

## Project Structure

```
tradingApp/
├── app.py                  # Streamlit dashboard — main entry point
├── config.py               # All configuration constants and weights
├── scoring.py              # Core alpha engine — all scoring logic
├── data_fetcher.py         # yfinance price + fundamental data with retry/cache
├── screener_scraper.py     # Screener.in scraper (ROCE, promoter holding, PEG, etc.)
├── news_sentiment.py       # Ollama + RSS sentiment pipeline
├── email_notifier.py       # Dark-themed HTML email builder and sender
├── backtester.py           # Backtester with date range and Nifty benchmark
├── performance_tracker.py  # Position tracker — targets, stop-loss, P&L log
├── position_sizer.py       # Capital allocation and market regime detection
├── tunnel.py               # ngrok tunnel for mobile access
├── start.bat               # Windows launcher (starts Ollama + Streamlit)
├── requirements.txt        # Python dependencies
├── .env.example            # Credential template — copy to .env and fill in
└── data/                   # SQLite cache (auto-created, git-ignored)
```

---

## Sidebar Controls

| Control | Description |
|---|---|
| Show market overview | Nifty / VIX / market breadth panel |
| Include Lynch Ratio | PEGY weighted in Large Cap fundamental score (~6.5% of fundamental sub-score) |
| Include PSUs | Add state-owned enterprises to the universe (excluded by default) |
| Sentiment (Ollama) | Adds a 5% sentiment dimension; auto-runs on the 15 picks after scoring |
| Full Scan | Run sentiment across all ~160 stocks |
| Clear Cache & Refresh | Force re-fetch of all price and fundamental data |
| Mobile tunnel | Start an ngrok tunnel for access from your phone |
| Email Report | Add recipients and send the dark-themed HTML report |

---

## Scoring Architecture

### Composite weights (sum to 1.0 per funnel)

| Dimension | Large Cap | Mid Cap | Small Cap |
|---|---|---|---|
| Technical | 15% | 15% | 20% |
| Fundamental | 40% | 30% | 25% |
| Institutional | 20% | 15% | 10% |
| Risk | 15% | 10% | 10% |
| Relative Strength | 5% | 25% | 30% |
| Sentiment (Ollama) | 5% | 5% | 5% |

### Fundamental sub-weights

**Large Cap** — quality and cash-flow focus: ROCE, D/E, ICR, ROE, Lynch Ratio dominate.

**Mid Cap** — growth focus: PEG (22%) and 5-year sales growth (22%) dominate; absolute PE de-emphasised.

**Small Cap** — pure growth: PEG (25%) and 5-year sales growth (25%) dominate.

### Quality gate

A stock must pass at least 6 of 10 quality checks **and** have non-null ROCE, promoter holding, and debt/equity (scraped from Screener.in) to appear in the portfolio. Stocks that fail the gate are shown in the full rankings table but not selected as picks.

---

## Data Sources

| Source | Data | Cache TTL |
|---|---|---|
| Yahoo Finance (yfinance) | OHLCV prices, fundamentals | 4 h (price), 7 d (fundamentals) |
| Screener.in | ROCE, promoter holding, pledged %, PEG, 5-year growth rates | 7 d |
| NSE via yfinance | Nifty 50 index, India VIX | Live patch on top of history |
| ET / Moneycontrol / Business Standard RSS | News headlines for Ollama sentiment | 24 h |

All data is fetched with automatic exponential-backoff retry (up to 3 attempts, 2 s / 4 s delays) to handle transient Yahoo Finance rate-limit errors.

---

## Mobile Access (ngrok)

1. Sign up free at [ngrok.com](https://ngrok.com) and download `ngrok`.
2. Authenticate once: `ngrok config add-authtoken YOUR_TOKEN`
3. Click **▶️ Start Tunnel** in the sidebar — a public URL appears that you can open on any device.

---

## Disclaimer

NiftyScout is a **decision-support tool**, not financial advice. All scores and signals are algorithmic and do not account for macroeconomic events, management quality, or other qualitative factors. Always do your own research before investing.
