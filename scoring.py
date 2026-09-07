from __future__ import annotations
import re
from copy import deepcopy

DEFAULT_STRATEGY = {
    "signal_confidence_threshold": 7,
    "buy_net_threshold": 25,
    "avoid_net_threshold": -15,
    "leadership_position_threshold": 60,
    "leadership_rvol_threshold": 3,
    "confidence_base": 4,
    "confidence_net_divisor": 15,
    "buy_min_confidence": 7,
    "non_buy_max_confidence": 6,
    "weights": {
        "rvol_bull_max": 18, "rvol_bear_max": 18, "breakout": 15,
        "near_high_position": 8, "trend": 15, "strong_day_close": 10,
        "weak_day_close": 10, "analyst_upside": 12, "partial_upside_max": 8,
        "analyst_buy": 10, "analyst_low_buy": 9, "analyst_sell": 8,
        "positive_news": 9, "negative_news": 9, "positive_window_return_max": 10,
        "negative_window_return_max": 10, "far_below_high": 9,
        "technicals_score_rvol_multiplier": 18, "fundamentals_score_buy_multiplier": 0.25,
        "news_score_sentiment_multiplier": 8
    },
    "triggers": {
        "rvol_bull_start": 1.5, "rvol_bear_below": 1.0, "breakout_position": 85,
        "near_high_position": 60, "trend_positive_sma": 0, "strong_day_close": 70,
        "weak_day_close": 35, "analyst_upside": 10, "analyst_no_headroom": 0,
        "analyst_buy_strong": 80, "analyst_buy_low": 55, "analyst_sell_high": 20,
        "far_below_high": -20, "window_return_positive": 0, "window_return_negative": 0
    },
    "trade_plan": {
        "entry_pullback_pct": 1.5,
        "breakout_buffer_pct": 0.5,
        "swing_rvol": 2.5,
        "swing_day_change_pct": 1.5,
        "target1_min_move_pct": 3.0,
        "target2_min_move_pct": 6.0,
        "target3_min_move_pct": 10.0
    }
}

def merge_strategy(custom=None):
    out = deepcopy(DEFAULT_STRATEGY)
    custom = custom or {}
    for k in ("signal_confidence_threshold", "buy_net_threshold", "avoid_net_threshold", "leadership_position_threshold", "leadership_rvol_threshold", "confidence_base", "confidence_net_divisor", "buy_min_confidence", "non_buy_max_confidence"):
        if k in custom: out[k] = custom[k]
    for group in ("weights", "triggers", "trade_plan"):
        if isinstance(custom.get(group), dict): out[group].update(custom[group])
    return out

def clamp(v, lo=0, hi=100): return max(lo, min(hi, v))

def _price(x):
    return round(float(x), 2) if x is not None and isinstance(x, (int, float)) else None


def build_trade_plan(e, verdict, strategy=None):
    """Build an evidence-derived entry/target plan. Numbers are calculations from the bundle, not invented facts."""
    if verdict != 'BUY':
        return {
            'style': 'No entry', 'entry': {'low': None, 'high': None, 'basis': 'No BUY entry recommended for this verdict.'},
            'targets': [{'label':'Target 1','price':None,'time':'—'}, {'label':'Target 2','price':None,'time':'—'}, {'label':'Target 3','price':None,'time':'—'}],
            'invalidation': None,
            'note': 'Trade plan is generated only for BUY verdicts.'
        }
    s=merge_strategy(strategy); tp=s['trade_plan']; price=e.get('price',{}); tech=e.get('technicals',{}); rng=e.get('range_52w',{}); analyst=e.get('analyst',{})
    cur=price.get('live'); day_high=price.get('high'); day_low=price.get('low'); swing_low=tech.get('swing_low'); swing_high=tech.get('swing_high'); rvol=tech.get('rvol'); day_chg=price.get('day_change_pct'); trend=tech.get('trend')
    if cur is None:
        return {'style':'Data unavailable','entry':{'low':None,'high':None,'basis':'Live price unavailable.'},'targets':[{'label':'Target 1','price':None,'time':'—'},{'label':'Target 2','price':None,'time':'—'},{'label':'Target 3','price':None,'time':'—'}],'invalidation':None,'note':'Entry/targets unavailable because live price is missing.'}
    style='Swing' if ((rvol is not None and rvol>=tp['swing_rvol']) or (day_chg is not None and day_chg>=tp['swing_day_change_pct'])) and trend=='up' else 'Short-term' if trend=='up' else 'Long-term'
    pull=cur*(tp['entry_pullback_pct']/100.0); buf=cur*(tp['breakout_buffer_pct']/100.0)
    entry_low=max(cur-pull, swing_low) if swing_low is not None else cur-pull
    entry_high=cur+buf if rng.get('position_pct') is not None and rng.get('position_pct')>=85 else cur
    if entry_low>entry_high: entry_low,entry_high=entry_high,entry_low
    day_range=(day_high-day_low) if day_high is not None and day_low is not None else None
    mean=analyst.get('target_mean'); high=analyst.get('target_high')
    base=max(day_range or 0, cur*tp['target1_min_move_pct']/100)
    t1_raw=cur+base; t2_raw=cur+max(2*base, cur*tp['target2_min_move_pct']/100); t3_raw=cur+max(3*base, cur*tp['target3_min_move_pct']/100)
    if mean is not None and mean>cur:
        t1=min(t1_raw, cur+(mean-cur)*0.5); t2=mean
    else:
        t1,t2=t1_raw,t2_raw
    if high is not None and high>max(t2,cur): t3=max(t3_raw,high)
    else: t3=t3_raw
    t1=max(t1,cur*1.01); t2=max(t2,t1); t3=max(t3,t2)
    horizons={
        'Swing': ('1–3 weeks','3–6 weeks','1–3 months'),
        'Short-term': ('1–4 weeks','1–3 months','3–6 months'),
        'Long-term': ('1–3 months','3–6 months','6–12 months')
    }[style]
    invalid=max((swing_low if swing_low is not None and swing_low<cur else cur*(1-tp['entry_pullback_pct']/100)), 0)
    return {
        'style': style,
        'entry': {'low':_price(entry_low),'high':_price(entry_high),'basis':'Calculated pullback/breakout entry zone from current price and available swing/52-week evidence.'},
        'targets':[{'label':'Target 1','price':_price(t1),'time':horizons[0]}, {'label':'Target 2','price':_price(t2),'time':horizons[1]}, {'label':'Target 3','price':_price(t3),'time':horizons[2]}],
        'invalidation':_price(invalid),
        'note':'Target timing is a heuristic horizon, not a guaranteed forecast.'
    }


def deterministic_evaluate(e, strategy=None):
    s = merge_strategy(strategy); w=s['weights']; g=s['triggers']
    t,r,a,n=e.get('technicals',{}),e.get('range_52w',{}),e.get('analyst',{}),e.get('news',{})
    patterns = e.get("patterns", {})
    detected_patterns = patterns.get("detected", [])

    bull=bear=0; br=[]; er=[]
    rv=t.get('rvol')
    if rv is not None:
        bull += min(w['rvol_bull_max'],max(0,(rv-1)*w['rvol_bull_max']/max(0.1,g['rvol_bull_start']-1)))
        bear += max(0,min(w['rvol_bear_max'],(1-rv)*w['rvol_bear_max']))
        if rv>=g['rvol_bull_start']: br.append('High relative volume confirms strong market participation')
        if rv<g['rvol_bear_below']: er.append('Below-normal volume weakens confirmation of the move')
    pos=r.get('position_pct')
    if pos is not None:
        if pos>=g['breakout_position']: bull+=w['breakout']; br.append('52-week position shows breakout territory')
        elif pos>=g['near_high_position']: bull+=w['near_high_position']
        if pos<30: bear+=w['rvol_bear_max']; er.append('52-week position is near the lower end')
    pvs=t.get('price_vs_sma_pct'); trend=t.get('trend')
    if pvs is not None and pvs>g['trend_positive_sma'] and trend=='up': bull+=w['trend']; br.append('price is above a rising trend')
    elif pvs is not None and pvs<0 and trend=='down': bear+=w['trend']; er.append('price is below the trend')
    close=t.get('day_range_position_pct')
    if close is not None:
        if close>=g['strong_day_close']: bull+=w['strong_day_close']; br.append('strong close within the day range')
        if close<=g['weak_day_close']: bear+=w['weak_day_close']; er.append('weak close within the day range')
    up=a.get('upside_pct'); buy=a.get('buy_pct'); sell=a.get('sell_pct')
    if up is not None:
        if up>=g['analyst_upside']: bull+=w['analyst_upside']; br.append('analyst target implies meaningful headroom')
        elif up<=g['analyst_no_headroom']: bear+=w['analyst_upside']; er.append('analyst target shows no headroom')
        else: bull+=min(w['partial_upside_max'],up*0.6)
    if buy is not None:
        if buy>=g['analyst_buy_strong']: bull+=w['analyst_buy']; br.append('analyst mix is strongly buy-weighted')
        elif buy<g['analyst_buy_low']: bear+=w['analyst_low_buy']; er.append('analyst buy conviction is limited')
    if sell is not None and sell>=g['analyst_sell_high']: bear+=w['analyst_sell']; er.append('analyst sell share is elevated')
    p=n.get('positive'); q=n.get('negative')
    if p is not None and q is not None:
        if p>q: bull+=w['positive_news']; br.append('news tone skews positive')
        elif q>p: bear+=w['negative_news']; er.append('news tone skews negative')
        # ---------------------------------------------------------
    # PATTERN DETECTION
    # ---------------------------------------------------------

    for pattern in detected_patterns:
        pattern_name = pattern.get("pattern")
        direction = pattern.get("direction")
        confidence = pattern.get("confidence", 0)
        status = pattern.get("status")

        # Only allow meaningful confidence values.
        confidence = max(
            0,
            min(100, float(confidence or 0))
        )

        # Confirmed patterns receive more weight.
        confirmation_multiplier = (
            1.0 if status == "confirmed"
            else 0.6
        )

        if direction == "bullish":

            points = min(
                18,
                confidence * 0.18
                * confirmation_multiplier
            )

            bull += points

            br.append(
                f"{pattern_name} supports the bullish setup"
            )

        elif direction == "bearish":

            points = min(
                18,
                confidence * 0.18
                * confirmation_multiplier
            )

            bear += points

            er.append(
                f"{pattern_name} supports the bearish setup"
            )


    wr=t.get('window_return_pct')
    if wr is not None:
        if wr>g['window_return_positive']: bull+=min(w['positive_window_return_max'],wr/2); br.append('window return is positive')
        elif wr<g['window_return_negative']: bear+=min(w['negative_window_return_max'],-wr/2); er.append('window return is negative')
    fh=r.get('pct_from_high')
    if fh is not None and fh<=g['far_below_high']: bear+=w['far_below_high']; er.append('price remains far below the 52-week high')
    bull,bear=clamp(round(bull)),clamp(round(bear)); net=bull-bear
    leadership=(pos is not None and pos>=s['leadership_position_threshold']) or (rv is not None and rv>=s['leadership_rvol_threshold'])
    verdict='BUY' if net>=s['buy_net_threshold'] and leadership else 'AVOID' if net<=s['avoid_net_threshold'] else 'WATCH'
    conf=max(1,min(10,round(s['confidence_base']+net/s['confidence_net_divisor'])))
    conf=max(s['buy_min_confidence'],conf) if verdict=='BUY' else min(s['non_buy_max_confidence'],conf)
    winner='Bull' if bull>=bear else 'Bear'; reasons=br if winner=='Bull' else er
    rationale=reasons[0] if reasons else 'Mixed evidence; confirmation is limited.'
    catalyst=(br[1] if winner=='Bull' and len(br)>1 else br[0] if winner=='Bull' and br else 'Trend or valuation needs confirmation.')
    vd={'winner':winner,'verdict':verdict,'confidence':conf,'rationale':rationale,'key_catalyst':catalyst,'bull_score':bull,'bear_score':bear,'net':net}
    return {'scores':{'bull':{'score':bull,'reasons':br[:4]},'bear':{'score':bear,'reasons':er[:4]},'fundamentals':{'score':clamp(round((up or 0)+(buy or 0)*w['fundamentals_score_buy_multiplier'])),'reasons':[]},'technicals':{'score':clamp(round((rv or 0)*w['technicals_score_rvol_multiplier']+max(0,(pvs or 0))*3)),'reasons':[]},'news':{'score':clamp(round(50+((p or 0)-(q or 0))*w['news_score_sentiment_multiplier'])),'reasons':[]}},'verdict':vd,'trade_plan':build_trade_plan(e, verdict, s),'strategy':s}

def evidence_numbers(e):
    out=set()
    def walk(v):
        if isinstance(v,dict):
            for x in v.values(): walk(x)
        elif isinstance(v,list):
            for x in v: walk(x)
        elif isinstance(v,(int,float)) and not isinstance(v,bool): out.add(round(float(v),3))
    walk(e); return out

def verify_text(text,e):
    allowed=evidence_numbers(e); unknown=[]
    for x in re.findall(r'(?<![A-Za-z])[-+]?\d+(?:\.\d+)?',text or ''):
        n=float(x)
        if n in {25,52}: continue
        if round(n,3) not in allowed and round(n,1) not in {round(a,1) for a in allowed}: unknown.append(n)
    return unknown

def sanitize_grounding(result,e):
    flags=[]
    for agent,payload in result.get('scores',{}).items():
        clean=[]
        for text in payload.get('reasons',[]) or []:
            nums=verify_text(text,e)
            if nums:
                flags.extend([f'{agent}: {n}' for n in nums]); text=re.sub(r'[-+]?\d+(?:\.\d+)?','data unavailable',text)
            clean.append(text)
        payload['reasons']=clean
    for key in ('rationale','key_catalyst'):
        text=result.get('verdict',{}).get(key,''); nums=verify_text(text,e)
        if nums:
            flags.extend([f'verdict.{key}: {n}' for n in nums]); result['verdict'][key]=re.sub(r'[-+]?\d+(?:\.\d+)?','data unavailable',text)
    result['grounding_flags']=flags; return result
