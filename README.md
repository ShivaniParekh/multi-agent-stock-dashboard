# SignalDesk — multi-agent Indian stock dashboard

This version adds automatic NSE universe discovery and a two-stage live screener.

## What changed

The old small hand-maintained universe is now optional. `refresh_universe.py` downloads NSE's current equity-segment security list, keeps normal `EQ` series symbols, applies `universe_overrides.json`, queries market-cap metadata, and writes `universe.json` grouped into large/mid/small. NSE publishes a current equity securities CSV on its “Securities available for Trading” page. The series legend identifies EQ as rolling-settlement fully paid equity shares. 

Live analysis is now two-stage:

1. The expanded universe is screened with batched ~1-month daily data.
2. Price and average-volume filters remove very small/illiquid names.
3. Top `SHORTLIST_PER_BUCKET` by day-change are selected in each cap bucket.
4. Only those shortlisted stocks receive detailed yfinance metadata/history/news and the LLM/debate evaluation.

This prevents an expanded universe from causing thousands of full per-stock API requests.

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

## Universe controls

`universe_overrides.json` lets you preserve manual additions/removals:

```json
{"include":["ABC.NS"],"exclude":["XYZ.NS"]}
```

Environment settings:

```env
SHORTLIST_PER_BUCKET=6
MIN_PRICE=20
MIN_AVG_VOLUME=100000
MAX_UNIVERSE=2000
UNIVERSE_REFRESH_MAX=2000
EXCLUDE_SME=true
```

`UNIVERSE_REFRESH_MAX` limits how many NSE symbols are considered during a refresh. Market-cap grouping is derived from Yahoo metadata and is intended as a practical screening classification, not an official NSE index classification.

## LLM / Telegram

The existing LLM provider chain, deterministic fallback, SQLite audit trail, evidence verifier, and Telegram BUY signaling remain intact. See `.env.example` and the dashboard project's earlier setup instructions.

## Data-source note

NSE's securities page provides separate CSVs for equity, SME, ETF, REIT/InvIT and other instruments, so this refresh uses the equity CSV and `EQ` series rather than treating every listed security as a normal stock. 

## Trade-plan output

BUY verdicts now include a generated trade plan in the dashboard and Telegram alert:

- **Entry zone:** a calculated pullback/current-price or breakout-buffer range using the evidence bundle.
- **Target 1 / Target 2 / Target 3:** calculated levels using available day-range evidence and analyst target mean/high where available.
- **Style:** Swing, Short-term, or Long-term, inferred from trend/relative-volume/day-move evidence.
- **Target horizon:** estimated time windows for each target. These are heuristic horizons, not guarantees.
- **Invalidation:** a calculated level based on available swing-low/current-price evidence.

For WATCH/AVOID verdicts, the dashboard explicitly shows **No entry** rather than inventing a trade plan.

Trade-plan calculation controls are also exposed in **Strategy / Scoring Settings** so you can tune entry pullback, breakout buffer, swing triggers, and minimum target moves without editing Python.

## Future Scope

[] Use AngelOne/Zerodha API.
[] Add inhouse paper trading.
[] Update trade every X mins.
[] Add support for short trades.