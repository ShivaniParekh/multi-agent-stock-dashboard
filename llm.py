from __future__ import annotations
import json,os,shutil,subprocess,requests
from scoring import deterministic_evaluate,sanitize_grounding,build_trade_plan
SYSTEM='''You are an equity analysis panel. Use ONLY the supplied evidence bundle. 
Never invent facts or numbers. 
If a needed value is missing, say data unavailable. 
A BUY requires favorable risk/reward with confirmation (momentum/volume). 
WATCH means promising but unconfirmed. 
AVOID means poor setup.
Pattern detection is quantitative technical evidence, not certainty.
Treat "forming" patterns as weaker than "confirmed" patterns.
Never invent a pattern or pattern price that is not present in the evidence bundle.
Do not issue BUY solely because a chart pattern is detected. 
Return JSON only.'''
def provider():
    f = os.getenv("LLM_PROVIDER", "").strip().lower()

    if f:
        return f

    if shutil.which("claude"):
        return "claude_code"

    if os.getenv("GEMINI_API_KEY"):
        return "gemini"

    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"

    if os.getenv("OPENAI_API_KEY"):
        return "openai"

    return "deterministic"


def prompt(e):return SYSTEM+'\nEvidence bundle:\n'+json.dumps(e,separators=(',',':'))+'\nReturn {scores:{bull:{score,reasons},bear:{score,reasons},fundamentals:{score,reasons},technicals:{score,reasons},news:{score,reasons}},verdict:{winner,verdict,confidence,rationale,key_catalyst}}.'
def parse(s):
    o=json.loads(s)
    if isinstance(o,dict) and isinstance(o.get('result'),str):
        if o.get('is_error'): raise RuntimeError(o.get('result','claude error'))
        return json.loads(o['result'])
    return o

def gemini(prompt_text):
    key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing")

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

    response_schema = {
        "type": "object",
        "properties": {
            "scores": {
                "type": "object",
                "properties": {
                    "bull": {
                        "type": "object",
                        "properties": {
                            "score": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 100
                            },
                            "reasons": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                }
                            }
                        },
                        "required": ["score", "reasons"]
                    },
                    "bear": {
                        "type": "object",
                        "properties": {
                            "score": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 100
                            },
                            "reasons": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                }
                            }
                        },
                        "required": ["score", "reasons"]
                    },
                    "fundamentals": {
                        "type": "object",
                        "properties": {
                            "score": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 100
                            },
                            "reasons": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                }
                            }
                        },
                        "required": ["score", "reasons"]
                    },
                    "technicals": {
                        "type": "object",
                        "properties": {
                            "score": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 100
                            },
                            "reasons": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                }
                            }
                        },
                        "required": ["score", "reasons"]
                    },
                    "news": {
                        "type": "object",
                        "properties": {
                            "score": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 100
                            },
                            "reasons": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                }
                            }
                        },
                        "required": ["score", "reasons"]
                    }
                },
                "required": [
                    "bull",
                    "bear",
                    "fundamentals",
                    "technicals",
                    "news"
                ]
            },

            "verdict": {
                "type": "object",
                "properties": {
                    "winner": {
                        "type": "string",
                        "enum": ["Bull", "Bear"]
                    },
                    "verdict": {
                        "type": "string",
                        "enum": ["BUY", "WATCH", "AVOID"]
                    },
                    "confidence": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10
                    },
                    "rationale": {
                        "type": "string"
                    },
                    "key_catalyst": {
                        "type": "string"
                    }
                },
                "required": [
                    "winner",
                    "verdict",
                    "confidence",
                    "rationale",
                    "key_catalyst"
                ]
            }
        },
        "required": [
            "scores",
            "verdict"
        ]
    }

    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": SYSTEM
                }
            ]
        },

        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            prompt_text
                            + "\n\nIMPORTANT OUTPUT RULES:"
                            + "\n- Return JSON only."
                            + "\n- confidence MUST be an integer from 1 to 10."
                            + '\n- Do NOT return confidence as "8/10".'
                            + '\n- Do NOT return confidence as a string.'
                            + "\n- Scores must be integers from 0 to 100."
                        )
                    }
                ]
            }
        ],

        "generationConfig": {
            "temperature": 0.1,

            "responseMimeType": "application/json",

            "responseSchema": response_schema
        }
    }

    r = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key
        },
        json=payload,
        timeout=90
    )

    if not r.ok:
        raise RuntimeError(
            f"Gemini API {r.status_code}: {r.text[:1000]}"
        )

    data = r.json()

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected Gemini response: {data}"
        ) from exc

    return parse(text)

def evaluate(e, strategy=None):
    p = provider()

    if p == "deterministic":
        return deterministic_evaluate(e, strategy), "deterministic"

    try:
        text = prompt(e)

        if p == "claude_code":
            r = subprocess.run(
                [
                    "claude",
                    "-p",
                    text,
                    "--output-format",
                    "json",
                    "--model",
                    os.getenv("CLAUDE_MODEL", "haiku")
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=120
            )

            if r.returncode != 0:
                raise RuntimeError(
                    r.stderr.strip() or "Claude CLI failed"
                )

            raw = parse(r.stdout)

        elif p == "gemini":
            raw = gemini(text)

        elif p == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY is missing")
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": os.getenv(
                        "ANTHROPIC_MODEL",
                        "claude-3-5-haiku-latest"
                    ),
                    "max_tokens": 2200,
                    "system": SYSTEM,
                    "messages": [
                        {
                            "role": "user",
                            "content": text
                        }
                    ]
                },
                timeout=90
            )

            r.raise_for_status()

            raw = parse(
                "".join(
                    x.get("text", "")
                    for x in r.json().get("content", [])
                    if x.get("type") == "text"
                )
            )

        elif p == "openai":
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}"
                },
                json={
                    "model": os.getenv(
                        "OPENAI_MODEL",
                        "gpt-4o-mini"
                    ),
                    "temperature": 0.1,
                    "response_format": {
                        "type": "json_object"
                    },
                    "messages": [
                        {
                            "role": "system",
                            "content": SYSTEM
                        },
                        {
                            "role": "user",
                            "content": text
                        }
                    ]
                },
                timeout=90
            )

            r.raise_for_status()

            raw = parse(
                r.json()["choices"][0]["message"]["content"]
            )

        else:
            raise ValueError(
                f"Unsupported LLM_PROVIDER: {p}"
            )

        out = {
            "scores": raw.get("scores", {}),
            "verdict": raw.get("verdict", {})
        }

        out = sanitize_grounding(out, e)

        if out["verdict"].get("verdict") not in {
            "BUY",
            "WATCH",
            "AVOID"
        }:
            raise ValueError("Invalid LLM verdict")

        raw_confidence = out["verdict"].get("confidence")

        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            raise ValueError(
                f"Invalid LLM confidence: {raw_confidence!r}"
            )

        if not 1 <= confidence <= 10:
            raise ValueError(
                f"LLM confidence must be between 1 and 10: {confidence}"
            )

        out["verdict"]["confidence"] = int(round(confidence))

        out["trade_plan"] = build_trade_plan(
            e,
            out["verdict"]["verdict"],
            strategy
        )

        out["strategy"] = strategy

        return out, p

    except Exception as exc:
        # IMPORTANT: show the reason while testing.
        print(
            f"[LLM ERROR] provider={p} "
            f"error={type(exc).__name__}: {exc}"
        )

        return (
            deterministic_evaluate(e, strategy),
            "deterministic"
        )