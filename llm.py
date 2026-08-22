from __future__ import annotations
import json,os,shutil,subprocess,requests
from scoring import deterministic_evaluate,sanitize_grounding,build_trade_plan
SYSTEM='''You are an equity analysis panel. Use ONLY the supplied evidence bundle. Never invent facts or numbers. If a needed value is missing, say data unavailable. A BUY requires favorable risk/reward with confirmation (momentum/volume). WATCH means promising but unconfirmed. AVOID means poor setup. Return JSON only.'''
def provider():
    f=os.getenv('LLM_PROVIDER','').strip().lower()
    if f:return f
    if shutil.which('claude'):return 'claude_code'
    if os.getenv('ANTHROPIC_API_KEY'):return 'anthropic'
    if os.getenv('OPENAI_API_KEY'):return 'openai'
    return 'deterministic'
def prompt(e):return SYSTEM+'\nEvidence bundle:\n'+json.dumps(e,separators=(',',':'))+'\nReturn {scores:{bull:{score,reasons},bear:{score,reasons},fundamentals:{score,reasons},technicals:{score,reasons},news:{score,reasons}},verdict:{winner,verdict,confidence,rationale,key_catalyst}}.'
def parse(s):
    o=json.loads(s)
    if isinstance(o,dict) and isinstance(o.get('result'),str):
        if o.get('is_error'): raise RuntimeError(o.get('result','claude error'))
        return json.loads(o['result'])
    return o
def evaluate(e, strategy=None):
    p=provider()
    if p=='deterministic': return deterministic_evaluate(e, strategy),'deterministic'
    try:
        text=prompt(e)
        if p=='claude_code':
            r=subprocess.run(['claude','-p',text,'--output-format','json','--model',os.getenv('CLAUDE_MODEL','haiku')],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=120); r.check_returncode(); raw=parse(r.stdout)
        elif p=='anthropic':
            r=requests.post('https://api.anthropic.com/v1/messages',headers={'x-api-key':os.getenv('ANTHROPIC_API_KEY'),'anthropic-version':'2023-06-01','content-type':'application/json'},json={'model':os.getenv('ANTHROPIC_MODEL','claude-3-5-haiku-latest'),'max_tokens':2200,'system':SYSTEM,'messages':[{'role':'user','content':text}]},timeout=90); r.raise_for_status(); raw=parse(''.join(x.get('text','') for x in r.json().get('content',[]) if x.get('type')=='text'))
        else:
            r=requests.post('https://api.openai.com/v1/chat/completions',headers={'Authorization':'Bearer '+os.getenv('OPENAI_API_KEY')},json={'model':os.getenv('OPENAI_MODEL','gpt-4o-mini'),'temperature':.1,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':text}]},timeout=90); r.raise_for_status(); raw=parse(r.json()['choices'][0]['message']['content'])
        out={'scores':raw.get('scores',{}),'verdict':raw.get('verdict',{})}; out=sanitize_grounding(out,e)
        if out['verdict'].get('verdict') not in {'BUY','WATCH','AVOID'}: raise ValueError('invalid verdict')
        out['trade_plan']=build_trade_plan(e,out['verdict']['verdict'],strategy)
        out['strategy']=strategy
        return out,p
    except Exception:return deterministic_evaluate(e, strategy),'deterministic'
