from __future__ import annotations
import os, json, sqlite3, threading, time
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
import requests
from data_sources import load_demo, load_live, timestamp_ist, refresh_universe
from llm import evaluate, provider
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)


def load_env():
    p = ROOT / '.env'
    if not p.exists():
        return
    for line in p.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
DB = ROOT / 'audit.sqlite3'


def db():
    c = sqlite3.connect(DB)
    c.execute('CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT,started_at TEXT,finished_at TEXT,mode TEXT,stocks INTEGER,engine TEXT,telegram_sent INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS verdicts(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id INTEGER,symbol TEXT,segment TEXT,verdict TEXT,confidence REAL,winner TEXT,rationale TEXT,catalyst TEXT,price REAL,day_change REAL,payload TEXT)')
    c.execute("""
        CREATE TABLE IF NOT EXISTS telegram_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            verdict TEXT NOT NULL,
            confidence REAL,
            entry_low REAL,
            entry_high REAL,
            target1 REAL,
            target2 REAL,
            target3 REAL,
            sent_at TEXT NOT NULL,
            UNIQUE(symbol, signal_date)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS telegram_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            summary_date TEXT NOT NULL UNIQUE,
            sent_at TEXT NOT NULL
        )
    """)
    c.commit()
    return c


def scrub(x):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    return str(x).replace(token, '[REDACTED]') if token else x


AGENTS = [
    ('scout', 'Scout', 'screens the stock universe for movers', 'Scanned', 'Shortlisted'),
    ('technician', 'Technician', 'reads price action, RVOL & trend', 'Analyzed', 'Avg RVOL'),
    ('fundamentalist', 'Fundamentalist', 'weighs valuation & analyst targets', 'Covered', 'Avg upside'),
    ('newsdesk', 'Newsdesk', 'pulls live news & scores sentiment', 'Headlines', 'Net tone'),
    ('bull', 'Bull', 'argues the case to buy', 'Cases', 'Avg score'),
    ('bear', 'Bear', 'argues the case against', 'Cases', 'Avg score'),
    ('judge', 'Judge', 'weighs the debate, issues verdict + confidence', 'Verdicts', 'Buy'),
    ('messenger', 'Messenger', 'sends signals to Telegram', 'Sent', 'Engine')
]

lock = threading.Lock()
state = {
    'running': False,
    'mode': 'demo',
    'engine': provider(),
    'timestamp': timestamp_ist(),
    'universe': 0,
    'screened': 0,
    'debate': 0,
    'buy_signals': 0,
    'top_pick': {'symbol': '—', 'confidence': 0},
    'agents': {a[0]: {'status': 'offline', 's1': 0, 's2': 0} for a in AGENTS},
    'verdicts': [],
    'last_error': None,
    'telegram': {'configured': bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID')), 'sent': 0}
}


def agent(aid, status=None, s1=None, s2=None):
    with lock:
        if status is not None:
            state['agents'][aid]['status'] = status
        if s1 is not None:
            state['agents'][aid]['s1'] = s1
        if s2 is not None:
            state['agents'][aid]['s2'] = s2


def tg(text):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat:
        return False
    r = requests.post(
        f'https://api.telegram.org/bot{token}/sendMessage',
        json={'chat_id': chat, 'text': text, 'parse_mode': 'HTML'},
        timeout=20
    )
    r.raise_for_status()
    return True
IST = ZoneInfo("Asia/Kolkata")


def is_market_open_now():
    """
    NSE regular equity market window:
    Monday-Friday, 09:15 to 15:30 IST.

    This checks the time window only.
    It does not know about NSE exchange holidays.
    """
    now = datetime.now(IST)

    if now.weekday() >= 5:
        return False

    market_open = dt_time(9, 15)
    market_close = dt_time(15, 30)

    return market_open <= now.time() <= market_close


def trading_date():
    return datetime.now(IST).date().isoformat()


def already_sent_signal(con, symbol):
    """
    Return True if this symbol already generated a Telegram
    BUY signal today.
    """
    row = con.execute(
        """
        SELECT 1
        FROM telegram_signals
        WHERE symbol = ?
          AND signal_date = ?
        LIMIT 1
        """,
        (symbol, trading_date())
    ).fetchone()

    return row is not None

def get_new_signal_entries(con, fired):
    """
    Return only BUY entries that have not already generated
    a Telegram signal today.
    """
    new_entries = []

    for _, entry in fired:
        if not already_sent_signal(con, entry["symbol"]):
            new_entries.append(entry)

    return new_entries

def record_sent_signal(con, entry):
    """
    Persist a sent BUY signal so the same stock is not
    repeatedly messaged every 15 minutes.
    """
    plan = entry.get("trade_plan") or {}
    entry_zone = plan.get("entry") or {}
    targets = plan.get("targets") or []

    target_prices = []
    for target in targets[:3]:
        target_prices.append(target.get("price"))

    while len(target_prices) < 3:
        target_prices.append(None)

    con.execute(
        """
        INSERT OR IGNORE INTO telegram_signals (
            symbol,
            signal_date,
            verdict,
            confidence,
            entry_low,
            entry_high,
            target1,
            target2,
            target3,
            sent_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry["symbol"],
            trading_date(),
            entry["verdict"],
            entry["confidence"],
            entry_zone.get("low"),
            entry_zone.get("high"),
            target_prices[0],
            target_prices[1],
            target_prices[2],
            datetime.now(IST).isoformat()
        )
    )


def summary_already_sent(con):
    row = con.execute(
        """
        SELECT 1
        FROM telegram_summaries
        WHERE summary_date = ?
        LIMIT 1
        """,
        (trading_date(),)
    ).fetchone()

    return row is not None


def record_sent_summary(con):
    con.execute(
        """
        INSERT OR IGNORE INTO telegram_summaries (
            summary_date,
            sent_at
        )
        VALUES (?, ?)
        """,
        (
            trading_date(),
            datetime.now(IST).isoformat()
        )
    )

def cycle(mode):
    try:
        delay = float(os.getenv('AGENT_DELAY', '.45'))
        per = int(os.getenv('SHORTLIST_PER_BUCKET', '6'))

        if mode == 'live':
            try:
                u = json.loads((ROOT / 'universe.json').read_text(encoding='utf-8'))
                stale = not u.get('meta', {}).get('updated_at')
            except Exception:
                stale = True
            if stale:
                refresh_universe()
            live_result = load_live(per)
            bundles = live_result['bundles']
            universe_count = live_result['universe_count']
            screened_count = live_result['screened_count']
        else:
            bundles = load_demo(per)
            universe_count = len(bundles)
            screened_count = len(bundles)

        with lock:
            state.update({
                'running': True,
                'mode': mode,
                'timestamp': timestamp_ist(),
                'universe': universe_count,
                'screened': screened_count,
                'debate': 0,
                'buy_signals': 0,
                'top_pick': {'symbol': '—', 'confidence': 0},
                'verdicts': [],
                'last_error': None,
                'engine': '',
                'agents': {a[0]: {'status': 'offline', 's1': 0, 's2': 0} for a in AGENTS}
            })

        agent('scout', 'working')
        time.sleep(delay)
        agent('scout', 'done', screened_count, len(bundles))

        agent('technician', 'working')
        rv = [b['technicals'].get('rvol') for b in bundles if b['technicals'].get('rvol') is not None]
        time.sleep(delay)
        agent('technician', 'done', len(bundles), round(sum(rv) / len(rv), 2) if rv else '—')

        agent('fundamentalist', 'working')
        up = [b['analyst'].get('upside_pct') for b in bundles if b['analyst'].get('upside_pct') is not None]
        time.sleep(delay)
        agent('fundamentalist', 'done', len(bundles), round(sum(up) / len(up), 2) if up else '—')

        agent('newsdesk', 'working')
        h = sum(int(b['news'].get('total') or 0) for b in bundles)
        nt = sum(int(b['news'].get('positive') or 0) - int(b['news'].get('negative') or 0) for b in bundles)
        time.sleep(delay)
        agent('newsdesk', 'done', h, nt)

        agent('bull', 'working')
        agent('bear', 'working')
        results = []
        engines = []
        for b in bundles:
            r, e = evaluate(b)
            results.append((b, r))
            engines.append(e)

        agent('bull', 'done', len(results), round(sum(r['scores']['bull']['score'] for _, r in results) / len(results), 1) if results else 0)
        agent('bear', 'done', len(results), round(sum(r['scores']['bear']['score'] for _, r in results) / len(results), 1) if results else 0)

        with lock:
            state['debate'] = len(results)

        agent('judge', 'working')
        time.sleep(delay)
        con = db()
        rid = con.execute(
            'INSERT INTO runs(started_at,mode,stocks,engine) VALUES(?,?,?,?)',
            (timestamp_ist(), mode, len(results), engines[0] if len(set(engines)) == 1 and engines else 'mixed')
        ).lastrowid
        fired = []

        for idx, (b, r) in enumerate(results):
            v = r['verdict']
            p = b['price']
            plan = r.get('trade_plan') or {
                'style': 'No entry',
                'entry': {'low': None, 'high': None},
                'targets': [],
                'invalidation': None,
                'note': ''
            }
            entry = {
                'symbol': b['symbol'],
                'name': b['name'],
                'cap': b['cap_segment'],
                'verdict': v['verdict'],
                'confidence': v['confidence'],
                'winner': v['winner'],
                'why': scrub(v.get('rationale')),
                'catalyst': scrub(v.get('key_catalyst')),
                'price': p.get('live'),
                'day_change_pct': p.get('day_change_pct'),
                'engine': engines[idx],
                'trade_plan': plan
            }
            con.execute(
                'INSERT INTO verdicts(run_id,symbol,segment,verdict,confidence,winner,rationale,catalyst,price,day_change,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (rid, b['symbol'], b['cap_segment'], v['verdict'], v['confidence'], v['winner'], entry['why'], entry['catalyst'], p.get('live'), p.get('day_change_pct'), json.dumps(r))
            )
            state['verdicts'].append(entry)
            if v['verdict'] == 'BUY' and float(v['confidence']) >= int(os.getenv('CONFIDENCE_THRESHOLD', '7')):
                fired.append((b, entry))

        agent('judge', 'done', len(results), len(fired))
        top = max(state['verdicts'], key=lambda x: x['confidence'], default=None)
        if top:
            state['top_pick'] = {'symbol': top['symbol'], 'confidence': top['confidence']}

        agent('messenger', 'working', 0, engines[0] if len(set(engines)) == 1 and engines else 'mixed')
        sent = 0
        new_entries = []

# ---------------------------------------------------------
# 1. SEND ONLY NEW BUY SIGNALS
# ---------------------------------------------------------

        for b, e in fired:

            try:
                if already_sent_signal(con, e["symbol"]):
                    continue

                tp = e.get("trade_plan", {})
                ent = tp.get("entry", {})
                tgts = tp.get("targets", [])

                if (
                    ent.get("low") is not None
                    and ent.get("high") is not None
                ):
                    entry_text = (
                        f"₹{ent['low']}–₹{ent['high']}"
                    )
                else:
                    entry_text = "data unavailable"

                target_lines = []

                for target in tgts[:3]:
                    if target.get("price") is not None:
                        target_lines.append(
                            f"{target.get('label')}: "
                            f"₹{target.get('price')} "
                            f"({target.get('time')})"
                        )

                target_text = (
                    "\n".join(target_lines)
                    if target_lines
                    else "data unavailable"
                )

                msg = (
                    f"🟢 <b>BUY SIGNAL — "
                    f"{e['symbol']} ({e['cap']} cap)</b>\n"
                    f"Verdict: BUY | "
                    f"Confidence: {e['confidence']}/10\n"
                    f"Winner: {e['winner']}\n"
                    f"Why: {e['why']}\n"
                    f"Key catalyst: {e['catalyst']}\n\n"

                    f"<b>Entry zone:</b> {entry_text}\n"
                    f"<b>Style:</b> "
                    f"{tp.get('style', 'data unavailable')}\n"

                    f"<b>Targets:</b>\n"
                    f"{target_text}\n"

                    f"<b>Stop Loss:</b> "
                    f"₹{tp.get('invalidation')}\n\n"

                    f"Live price: ₹{e['price']} | "
                    f"Day change: {e['day_change_pct']}%\n"

                    f"— Analysis only. "
                    f"No trade was placed. "
                    f"Not investment advice."
                )

                if tg(msg):

                    record_sent_signal(con, e)

                    new_entries.append(e)
                    sent += 1

            except Exception as exc:
                print(
                    f"[TELEGRAM BUY ERROR] "
                    f"{scrub(str(exc))}"
                )

# ---------------------------------------------------------
# 2. SEND SUMMARY ONLY WHEN NEW BUY SIGNALS APPEAR
# ---------------------------------------------------------

        if new_entries:

            try:

                summary_lines = [
                    "<b>🟢 NEW BUY SIGNALS</b>",
                    f"Date: {trading_date()}",
                    ""
                ]

                for e in new_entries:

                    tp = e.get("trade_plan", {})
                    ent = tp.get("entry", {})

                    if (
                        ent.get("low") is not None
                        and ent.get("high") is not None
                    ):
                        entry_text = (
                            f"₹{ent['low']}–₹{ent['high']}"
                        )
                    else:
                        entry_text = "data unavailable"

                    summary_lines.append(
                        f"<b>{e['symbol']}</b> — "
                        f"BUY | "
                        f"Confidence: {e['confidence']}/10"
                    )

                    summary_lines.append(
                        f"Entry: {entry_text}"
                    )

                    summary_lines.append(
                        f"Style: "
                        f"{tp.get('style', 'data unavailable')}"
                    )

                    targets = tp.get("targets", [])

                    for target in targets[:3]:

                        if target.get("price") is not None:

                            summary_lines.append(
                                f"{target.get('label')}: "
                                f"₹{target.get('price')} "
                                f"({target.get('time')})"
                            )

                    summary_lines.append("")

                summary_lines.append(
                    "— Analysis only. "
                    "No trade was placed. "
                    "Not investment advice."
                )

                summary_msg = "\n".join(summary_lines)

                tg(summary_msg)

            except Exception as exc:

                print(
                    f"[TELEGRAM SUMMARY ERROR] "
                    f"{scrub(str(exc))}"
                )


        agent('messenger', 'done', sent, engines[0] if len(set(engines)) == 1 and engines else 'mixed')
        con.execute('UPDATE runs SET finished_at=?,telegram_sent=? WHERE id=?', (timestamp_ist(), sent, rid))
        con.commit()
        con.close()

        with lock:
            state.update({
                'running': False,
                'buy_signals': len(fired),
                'engine': engines[0] if len(set(engines)) == 1 and engines else 'mixed',
                'timestamp': timestamp_ist(),
                'telegram': {'configured': bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID')), 'sent': sent}
            })
    except Exception as e:
        with lock:
            state['running'] = False
            state['last_error'] = scrub(str(e))
            state['timestamp'] = timestamp_ist()

def auto_refresh_loop():
    """
    Automatically run the LIVE analysis every N minutes
    while the NSE market is open.

    The scheduler uses IST and prevents overlapping runs.
    """

    interval_minutes = int(
        os.getenv("AUTO_REFRESH_MINUTES", "15")
    )

    interval_seconds = max(1, interval_minutes * 60)

    print(
        f"Auto-refresh enabled: every "
        f"{interval_minutes} minutes during market hours."
    )

    while True:

        try:
            # Wait until the next scheduled interval.
            time.sleep(interval_seconds)

            # Only run during the configured market window.
            market_hours_only = (
                os.getenv(
                    "MARKET_HOURS_ONLY",
                    "true"
                ).lower() == "true"
            )

            if market_hours_only and not is_market_open_now():
                continue

            # Never start another cycle if one is already running.
            with lock:
                if state["running"]:
                    continue

            print(
                f"[AUTO REFRESH] Starting live scan "
                f"at {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}"
            )

            threading.Thread(
                target=cycle,
                args=("live",),
                daemon=True
            ).start()

        except Exception as exc:
            # Keep scheduler alive even if one scheduled run fails.
            print(
                f"[AUTO REFRESH ERROR] {scrub(str(exc))}"
            )

@app.get('/')
def home():
    return send_from_directory(ROOT, 'dashboard.html')


@app.post('/start')
def start():
    mode = (request.get_json(silent=True) or {}).get('mode', 'demo')
    with lock:
        if state['running']:
            return jsonify(ok=False, error='already running'), 409
        state['running'] = True
    threading.Thread(target=cycle, args=(mode,), daemon=True).start()
    return jsonify(ok=True)


@app.get('/status')
def status():
    with lock:
        return jsonify(json.loads(json.dumps(state)))


@app.get('/config')
def config():
    return jsonify({
        'brand': os.getenv('BRAND', 'SignalDesk'),
        'confidence_threshold': int(os.getenv('CONFIDENCE_THRESHOLD', '7')),
        'port': int(os.getenv('PORT', '5000')),
        'telegram_configured': bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID'))
    })


if __name__ == "__main__":

    db().close()

    auto_refresh_enabled = (
        os.getenv(
            "AUTO_REFRESH",
            "false"
        ).lower() == "true"
    )

    if auto_refresh_enabled:

        scheduler_thread = threading.Thread(
            target=auto_refresh_loop,
            daemon=True
        )

        scheduler_thread.start()

    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        debug=False
    )