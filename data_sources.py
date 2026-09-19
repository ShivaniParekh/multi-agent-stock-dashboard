from __future__ import annotations
import json, math, os, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
from pattern_detection import detect_patterns


ROOT = Path(__file__).resolve().parent
IST = timezone(timedelta(hours=5, minutes=30))
NSE_EQUITY_URL = 'https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv'


def load_demo(n=4):
    return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT / 'demo_data').glob('*.json'))][:max(1, n * 3)]


def safe(x):
    try:
        return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)
    except Exception:
        return None


def tone(title):
    t = (title or '').lower()
    pos = ('upgrade', 'buy', 'bullish', 'growth', 'strong', 'beat', 'outperform', 'constructive', 'surge', 'record', 'robust', 'positive', 'reiterate')
    neg = ('downgrade', 'sell', 'bearish', 'weak', 'miss', 'underperform', 'pressure', 'risk', 'cut', 'decline', 'negative', 'concern')
    a = sum(w in t for w in pos)
    b = sum(w in t for w in neg)
    return 'positive' if a > b else 'negative' if b > a else 'neutral'


def build_evidence(ticker, segment, info, hist, news):
    sym = ticker.replace('.NS', '')
    close = hist.get('Close', pd.Series(dtype=float))
    vol = hist.get('Volume', pd.Series(dtype=float))
    live = safe(close.iloc[-1]) if len(close) else None
    prev = safe(close.iloc[-2]) if len(close) > 1 else safe(info.get('previousClose'))
    day_open = safe(hist['Open'].iloc[-1]) if len(hist) else None
    hi = safe(hist['High'].iloc[-1]) if len(hist) else None
    lo = safe(hist['Low'].iloc[-1]) if len(hist) else None
    tv = safe(vol.iloc[-1]) if len(vol) else None
    av = safe(vol.iloc[-21:-1].mean()) if len(vol) >= 3 else None
    gaps = []
    sma = safe(close.tail(min(10, len(close))).mean()) if len(close) else None
    ret = ((live / safe(close.iloc[0])) - 1) * 100 if live and len(close) and safe(close.iloc[0]) else None
    hi52 = safe(info.get('fiftyTwoWeekHigh'))
    lo52 = safe(info.get('fiftyTwoWeekLow'))
    pos = ((live - lo52) / (hi52 - lo52) * 100) if None not in (live, hi52, lo52) and hi52 != lo52 else None
    pct = ((live / hi52) - 1) * 100 if live and hi52 else None
    dr = ((live - lo) / (hi - lo) * 100) if None not in (live, lo, hi) and hi != lo else None
    pvs = ((live / sma) - 1) * 100 if live and sma else None
    trend = None
    if len(close) >= 10:
        a = close.tail(10).mean()
        b = close.rolling(10).mean().iloc[-6]
        trend = 'up' if a > .005 * b else 'down' if a < -.005 * b else 'sideways'
    patterns = detect_patterns(
    hist,
    tolerance_pct=float(
        os.getenv("PATTERN_TOLERANCE_PCT", "3")
    )
    )
    analyst = {
        'consensus': info.get('recommendationKey'),
        'num_analysts': info.get('numberOfAnalystOpinions'),
        'buy_pct': None,
        'hold_pct': None,
        'sell_pct': None,
        'target_mean': safe(info.get('targetMeanPrice')),
        'target_low': safe(info.get('targetLowPrice')),
        'target_high': safe(info.get('targetHighPrice')),
        'upside_pct': ((info.get('targetMeanPrice') / live) - 1) * 100 if info.get('targetMeanPrice') and live else None
    }
    for k in ('consensus', 'num_analysts', 'target_mean'):
        if analyst[k] is None:
            gaps.append('analyst.' + k)

    rec = []
    posn = negn = neun = 0
    for x in news or []:
        title = x.get('title') or x.get('content', {}).get('title')
        if title:
            tt = tone(str(title))
            rec.append({'title': str(title), 'tone': tt})
            posn += tt == 'positive'
            negn += tt == 'negative'
            neun += tt == 'neutral'
    if not rec:
        gaps.append('news.recent')

    return {
        'symbol': sym,
        'name': info.get('longName') or info.get('shortName') or sym,
        'cap_segment': segment,
        'sector': info.get('sector'),
        "patterns": patterns,
        'price': {
            'live': live,
            'day_open': day_open,
            'high': hi,
            'low': lo,
            'prev_close': prev,
            'day_change_pct': ((live / prev) - 1) * 100 if live and prev else None,
            'volume': tv
        },
        'range_52w': {
            'high': hi52,
            'low': lo52,
            'pct_from_high': pct,
            'position_pct': pos
        },
        'technicals': {
            'rvol': tv / av if tv is not None and av else None,
            'price_vs_sma_pct': pvs,
            'window_return_pct': ret,
            'swing_high': safe(close.max()) if len(close) else None,
            'swing_low': safe(close.min()) if len(close) else None,
            'day_range_position_pct': dr,
            'trend': trend
        },
        'analyst': analyst,
        'news': {
            'total': len(rec),
            'positive': posn,
            'negative': negn,
            'neutral': neun,
            'recent': rec[:8]
        },
        'data_gaps': gaps
    }


def fetch_nse_equity_csv():
    import io, requests
    r = requests.get(NSE_EQUITY_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content))


def refresh_universe():
    import yfinance as yf
    df = fetch_nse_equity_csv()
    cols = {c.strip().upper(): c for c in df.columns}
    sym = cols.get('SYMBOL')
    series = cols.get('SERIES')
    if not sym or not series:
        raise RuntimeError('Unexpected NSE equity CSV columns')

    syms = []
    for _, row in df.iterrows():
        s = str(row[sym]).strip().upper()
        ser = str(row[series]).strip().upper()
        if not s or ser != 'EQ' or not re.match(r'^[A-Z0-9&-]+$', s):
            continue
        syms.append(s + '.NS')

    ov = json.loads((ROOT / 'universe_overrides.json').read_text()) if (ROOT / 'universe_overrides.json').exists() else {'include': [], 'exclude': []}
    exc = {x.upper() for x in ov.get('exclude', [])}
    inc = {x.upper() for x in ov.get('include', [])}
    syms = [s for s in syms if s not in exc and s.replace('.NS', '') not in exc]
    syms = sorted(set(syms) | {(x if x.endswith('.NS') else x + '.NS').upper() for x in inc})
    maxu = int(os.getenv('UNIVERSE_REFRESH_MAX', '500'))
    syms = syms[:maxu]

    caps = []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def cap(t):
        try:
            fi = yf.Ticker(t).fast_info
            return t, float(fi.get('market_cap') or 0)
        except Exception:
            return t, 0

    with ThreadPoolExecutor(
    max_workers=int(os.getenv('UNIVERSE_REFRESH_WORKERS', '3'))
) as ex:
        for f in as_completed([ex.submit(cap, s) for s in syms]):
            caps.append(f.result())

    caps.sort(key=lambda x: x[1], reverse=True)
    n = len(caps)
    large_end = max(1, int(n * .20))
    mid_end = max(large_end + 1, int(n * .50))
    groups = {
        'large': [s for s, c in caps[:large_end]],
        'mid': [s for s, c in caps[large_end:mid_end]],
        'small': [s for s, c in caps[mid_end:]]
    }
    out = {'meta': {'source': 'NSE equity EQ series + Yahoo market cap', 'updated_at': timestamp_ist(), 'count': n}, **groups}
    (ROOT / 'universe.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    return out


def load_live(shortlist=6):
    import gc
    import yfinance as yf

    u = json.loads((ROOT / 'universe.json').read_text(encoding='utf-8'))

    candidates = []


    batch_size = int(os.getenv('YF_BATCH_SIZE', '25'))

    min_price = float(os.getenv('MIN_PRICE', '20'))
    min_avg_volume = float(os.getenv('MIN_AVG_VOLUME', '100000'))

    for seg in ('large', 'mid', 'small'):
        tickers = u.get(seg, [])

        if not tickers:
            continue

        scored = []

        # Process the universe in small batches.
        for start in range(0, len(tickers), batch_size):
            batch = tickers[start:start + batch_size]

            try:
                data = yf.download(
                    tickers=batch,
                    period='1mo',
                    interval='1d',
                    auto_adjust=False,
                    group_by='ticker',
                    threads=False,
                    progress=False
                )

                if data is None or data.empty:
                    del data
                    gc.collect()
                    continue

                for t in batch:
                    try:
                        if isinstance(data.columns, pd.MultiIndex):
                            if t not in data.columns.get_level_values(0):
                                continue
                            d = data[t]
                        else:
                            d = data

                        if 'Close' not in d.columns or 'Volume' not in d.columns:
                            continue

                        c = d['Close'].dropna()
                        v = d['Volume'].dropna()

                        if len(c) < 2:
                            continue

                        price = float(c.iloc[-1])
                        prev = float(c.iloc[-2])

                        volume = float(v.iloc[-1]) if len(v) else 0
                        avg = float(v.iloc[-21:-1].mean()) if len(v) > 2 else 0

                        day = ((price / prev) - 1) * 100

                        if price < min_price:
                            continue

                        if avg < min_avg_volume:
                            continue

                        scored.append((t, day, volume, avg))

                    except Exception:
                        continue

                # Immediately release this batch before downloading
                # the next batch.
                del data
                gc.collect()

            except Exception as e:
                # One failed Yahoo batch should not kill the entire run.
                print(f"[load_live] batch failed for {seg}: {e}")
                gc.collect()
                continue

        scored.sort(key=lambda x: x[1], reverse=True)

        # Only keep the top movers from this segment for detailed analysis.
        candidates += [
            (seg, x[0])
            for x in scored[:shortlist]
        ]

    # ---------------------------------------------------------
    # SECOND STAGE:
    # Detailed data only for shortlisted stocks.
    # ---------------------------------------------------------

    out = []

    for seg, t in candidates:
        try:
            o = yf.Ticker(t)

            # Only finalists reach this stage.
            h = o.history(
                period=os.getenv('DETAIL_HISTORY_PERIOD', '6mo'),
                interval='1d',
                auto_adjust=False
            )

            if h is None or h.empty:
                continue

            info = {}
            news = []

            # These calls can be expensive/unreliable, so keep them
            # isolated to shortlisted stocks only.
            try:
                info = o.info or {}
            except Exception as e:
                print(f"[load_live] info failed for {t}: {e}")

            try:
                news = o.news or []
            except Exception as e:
                print(f"[load_live] news failed for {t}: {e}")

            out.append(
                build_evidence(
                    t,
                    seg,
                    info,
                    h,
                    news
                )
            )

            del h
            del o
            gc.collect()

        except Exception as e:
            print(f"[load_live] detailed fetch failed for {t}: {e}")
            gc.collect()
            continue

    if not out:
        raise RuntimeError(
            'Failed to load live data: no valid stock data was returned by Yahoo Finance'
        )

    return {
        'universe_count': sum(
            len(u.get(seg, []))
            for seg in ('large', 'mid', 'small')
        ),
        'screened_count': len(candidates),
        'bundles': out
    }

def timestamp_ist():
    return datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')
