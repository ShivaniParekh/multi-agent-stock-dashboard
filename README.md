# SignalDesk — Multi-Agent Indian Stock Dashboard

SignalDesk is an intelligent multi-agent stock analysis and screening platform for the Indian Equity Market (NSE). It combines automated market scanning, technical pattern recognition, multi-agent LLM debates, calculated trade plans, and Telegram signaling into an interactive web dashboard.

---

## Version History

### Version 3.0 — Pattern Recognition & Excel Export *(Current)*
- **Technical Chart Pattern Detection:** Automated recognition of formations (Double Bottom, Double Top, Support/Resistance levels, Breakouts, and Reversal setups) via [`pattern_detection.py`](file:///f:/multiAgentStockBot/multi_agent_stock_dashboard/pattern_detection.py).
- **Interactive UI Charts:** Direct rendering of technical indicators and pattern overlays in the web UI.
- **Excel Data Export:** One-click save and export of complete analysis history, verdicts, targets, and indicators into formatted `.xlsx` workbooks via [`excel_export.py`](file:///f:/multiAgentStockBot/multi_agent_stock_dashboard/excel_export.py).

### Version 2.0 — Automated NSE Universe, Screener & Trade Planning
- **Automated Universe Discovery:** `refresh_universe.py` automatically downloads NSE equity security lists, filters active `EQ` series stocks, queries market-cap metadata, and builds `universe.json` (Large/Mid/Small caps).
- **Two-Stage Live Screener:** Batched short-period screening reduces thousands of raw API calls down to the top shortlist per bucket before running full LLM evaluation.
- **Trade-Plan Generation:** Automatic calculation of Entry Zones, Targets (T1/T2/T3), Horizons, Style (Swing/Short-term/Long-term), and Invalidation levels for BUY verdicts.
- **Automated Periodic Refresh:** Background scanner running every N minutes during market hours (`AUTO_REFRESH`).

### Version 1.0 — Initial Multi-Agent Dashboard
- **Multi-Agent LLM Debate Engine:** Bull vs. Bear agent deliberation and deterministic fallback scoring logic.
- **Audit & Persistence:** SQLite database storage (`audit.sqlite3`) preserving evidence and debate transcripts.
- **Telegram Signaling:** Instant notification bot for verified `BUY` signals.

---

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env`.

### Refresh the universe manually

```bash
python refresh_universe.py
```

On Windows, double-click `refresh_universe.bat`.

### Run dashboard

On Windows, double-click `run.bat`. It installs requirements, refreshes the universe, starts Flask, and opens the browser.

```bash
python app.py
```

Then open http://127.0.0.1:5000.

---

## Configuration & Environment Controls

### Universe Overrides
`universe_overrides.json` lets you preserve manual additions/removals:

```json
{"include":["ABC.NS"],"exclude":["XYZ.NS"]}
```

### Environment Settings (`.env`)

```env
# Screening & Universe Controls
SHORTLIST_PER_BUCKET=6
MIN_PRICE=20
MIN_AVG_VOLUME=100000
MAX_UNIVERSE=2000
UNIVERSE_REFRESH_MAX=2000
EXCLUDE_SME=true

# Automatic Periodic Scans
AUTO_REFRESH=true
AUTO_REFRESH_MINUTES=15
MARKET_HOURS_ONLY=true
```

- `UNIVERSE_REFRESH_MAX`: Limits how many NSE symbols are considered during a refresh.
- `AUTO_REFRESH`: Enables automatic background scanning when set to `true`.
- `AUTO_REFRESH_MINUTES`: Sets the interval (in minutes) between automated scans (e.g., `15`).
- `MARKET_HOURS_ONLY`: Restricts auto-scans to active NSE market hours (Mon–Fri, 9:15 AM – 3:30 PM IST).

---

## Key Features & Components

### 1. Two-Stage Live Screener
1. The expanded universe is screened with batched ~1-month daily data.
2. Price and average-volume filters remove small or illiquid stocks.
3. Top `SHORTLIST_PER_BUCKET` by day-change are selected in each cap bucket.
4. Only shortlisted stocks receive detailed yfinance metadata/history/news and LLM debate evaluation.

### 2. Trade-Plan Output
`BUY` verdicts generate actionable trade plans:
- **Entry zone:** Calculated pullback/current-price or breakout-buffer range.
- **Target 1 / Target 2 / Target 3:** Calculated resistance/swing targets and analyst targets.
- **Style:** Swing, Short-term, or Long-term.
- **Target horizon:** Estimated time windows for targets.
- **Invalidation:** Swing-low or calculated stop-loss level.

For `WATCH` or `AVOID` verdicts, the dashboard displays **No entry**.

### 3. Pattern Detection & Interactive Charts
- Identifies technical chart patterns via `pattern_detection.py`.
- Integrates pattern evidence into the LLM debate.
- Visualizes chart patterns directly in the dashboard UI.

### 4. Excel Export
- Generates structured `.xlsx` workbooks containing audit logs, verdicts, technical metrics, and confidence scores via `excel_export.py`.

### 5. LLM / Telegram Integration
- Multi-provider LLM chain with deterministic fallback, SQLite audit trail, evidence verification, and Telegram alert delivery.

---

## Future Scope

- [ ] Use AngelOne/Zerodha API.
- [ ] Add inhouse paper trading.
- [x] Update trade every X mins *(Implemented via `AUTO_REFRESH`)*.
- [ ] Add support for short trades.
