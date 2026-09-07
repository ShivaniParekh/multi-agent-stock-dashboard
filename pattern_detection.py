from __future__ import annotations

from typing import Any, Dict, List, Optional
import math

import numpy as np
import pandas as pd


def _clean_series(series: pd.Series) -> pd.Series:
    """Return a clean numeric series."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    return s


def _pct(a: float, b: float) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return (a / b - 1.0) * 100.0


def _local_extrema(close: pd.Series, order: int = 3):
    """
    Simple local extrema detector.
    Returns lists of (index, price).
    """
    values = close.values
    highs = []
    lows = []

    if len(values) < order * 2 + 1:
        return highs, lows

    for i in range(order, len(values) - order):
        window = values[i - order:i + order + 1]
        v = values[i]

        if np.isfinite(v) and v == np.max(window):
            highs.append((i, float(v)))

        if np.isfinite(v) and v == np.min(window):
            lows.append((i, float(v)))

    return highs, lows


def detect_double_bottom(
    close: pd.Series,
    tolerance_pct: float = 3.0,
) -> Optional[Dict[str, Any]]:
    """
    Detect a simplified double-bottom structure:
        low -> rebound/high -> second low -> neckline breakout
    """

    if len(close) < 40:
        return None

    highs, lows = _local_extrema(close, order=3)

    if len(lows) < 2:
        return None

    for i in range(len(lows) - 1):
        idx1, low1 = lows[i]
        idx2, low2 = lows[i + 1]

        distance = idx2 - idx1

        if distance < 10 or distance > 90:
            continue

        avg_low = (low1 + low2) / 2.0

        difference_pct = abs(low1 - low2) / avg_low * 100.0

        if difference_pct > tolerance_pct:
            continue

        middle_highs = [
            (idx, price)
            for idx, price in highs
            if idx1 < idx < idx2
        ]

        if not middle_highs:
            continue

        neckline_idx, neckline = max(
            middle_highs,
            key=lambda x: x[1]
        )

        current = float(close.iloc[-1])

        breakout = current > neckline

        confidence = min(
            95.0,
            max(
                55.0,
                95.0
                - difference_pct * 8.0
                + (15.0 if breakout else 0.0)
            )
        )

        return {
            "pattern": "Double Bottom",
            "direction": "bullish",
            "confidence": round(confidence),
            "status": "confirmed" if breakout else "forming",
            "neckline": round(float(neckline), 2),
            "breakout_price": round(float(neckline), 2),
            "low_1": round(float(low1), 2),
            "low_2": round(float(low2), 2),
        }

    return None


def detect_double_top(
    close: pd.Series,
    tolerance_pct: float = 3.0,
) -> Optional[Dict[str, Any]]:
    """
    Detect a simplified double-top structure.
    """

    if len(close) < 40:
        return None

    highs, lows = _local_extrema(close, order=3)

    if len(highs) < 2:
        return None

    for i in range(len(highs) - 1):
        idx1, high1 = highs[i]
        idx2, high2 = highs[i + 1]

        distance = idx2 - idx1

        if distance < 10 or distance > 90:
            continue

        avg_high = (high1 + high2) / 2.0

        difference_pct = abs(high1 - high2) / avg_high * 100.0

        if difference_pct > tolerance_pct:
            continue

        middle_lows = [
            (idx, price)
            for idx, price in lows
            if idx1 < idx < idx2
        ]

        if not middle_lows:
            continue

        neckline_idx, neckline = min(
            middle_lows,
            key=lambda x: x[1]
        )

        current = float(close.iloc[-1])

        breakdown = current < neckline

        confidence = min(
            95.0,
            max(
                55.0,
                95.0
                - difference_pct * 8.0
                + (15.0 if breakdown else 0.0)
            )
        )

        return {
            "pattern": "Double Top",
            "direction": "bearish",
            "confidence": round(confidence),
            "status": "confirmed" if breakdown else "forming",
            "neckline": round(float(neckline), 2),
            "breakdown_price": round(float(neckline), 2),
            "high_1": round(float(high1), 2),
            "high_2": round(float(high2), 2),
        }

    return None


def detect_head_shoulders(
    close: pd.Series,
    tolerance_pct: float = 4.0,
) -> Optional[Dict[str, Any]]:
    """
    Simplified head-and-shoulders detector.
    """

    if len(close) < 60:
        return None

    highs, lows = _local_extrema(close, order=4)

    if len(highs) < 3 or len(lows) < 2:
        return None

    for i in range(len(highs) - 2):
        left = highs[i]
        head = highs[i + 1]
        right = highs[i + 2]

        li, lp = left
        hi, hp = head
        ri, rp = right

        if not (li < hi < ri):
            continue

        if hp <= lp or hp <= rp:
            continue

        shoulder_diff = abs(lp - rp) / ((lp + rp) / 2) * 100

        if shoulder_diff > tolerance_pct:
            continue

        neckline_lows = [
            x for x in lows
            if li < x[0] < ri
        ]

        if len(neckline_lows) < 2:
            continue

        neckline = sum(
            x[1] for x in neckline_lows
        ) / len(neckline_lows)

        current = float(close.iloc[-1])
        breakdown = current < neckline

        confidence = min(
            95.0,
            max(
                55.0,
                90.0
                - shoulder_diff * 7.0
                + (15.0 if breakdown else 0.0)
            )
        )

        return {
            "pattern": "Head & Shoulders",
            "direction": "bearish",
            "confidence": round(confidence),
            "status": "confirmed" if breakdown else "forming",
            "neckline": round(float(neckline), 2),
            "breakdown_price": round(float(neckline), 2),
        }

    return None


def detect_inverse_head_shoulders(
    close: pd.Series,
    tolerance_pct: float = 4.0,
) -> Optional[Dict[str, Any]]:
    """
    Simplified inverse head-and-shoulders detector.
    """

    if len(close) < 60:
        return None

    highs, lows = _local_extrema(close, order=4)

    if len(lows) < 3 or len(highs) < 2:
        return None

    for i in range(len(lows) - 2):
        left = lows[i]
        head = lows[i + 1]
        right = lows[i + 2]

        li, lp = left
        hi, hp = head
        ri, rp = right

        if not (li < hi < ri):
            continue

        if hp >= lp or hp >= rp:
            continue

        shoulder_diff = abs(lp - rp) / ((lp + rp) / 2) * 100

        if shoulder_diff > tolerance_pct:
            continue

        neckline_highs = [
            x for x in highs
            if li < x[0] < ri
        ]

        if len(neckline_highs) < 2:
            continue

        neckline = sum(
            x[1] for x in neckline_highs
        ) / len(neckline_highs)

        current = float(close.iloc[-1])
        breakout = current > neckline

        confidence = min(
            95.0,
            max(
                55.0,
                90.0
                - shoulder_diff * 7.0
                + (15.0 if breakout else 0.0)
            )
        )

        return {
            "pattern": "Inverse Head & Shoulders",
            "direction": "bullish",
            "confidence": round(confidence),
            "status": "confirmed" if breakout else "forming",
            "neckline": round(float(neckline), 2),
            "breakout_price": round(float(neckline), 2),
        }

    return None


def detect_breakout(
    close: pd.Series,
    volume: Optional[pd.Series] = None,
    lookback: int = 20,
) -> Optional[Dict[str, Any]]:

    if len(close) < lookback + 2:
        return None

    current = float(close.iloc[-1])
    prior_high = float(close.iloc[-lookback - 1:-1].max())

    if current <= prior_high:
        return None

    volume_confirmed = False

    if volume is not None and len(volume) >= 21:
        current_volume = float(volume.iloc[-1])
        avg_volume = float(volume.iloc[-21:-1].mean())

        if avg_volume > 0:
            volume_confirmed = current_volume >= avg_volume * 1.5

    return {
        "pattern": "Breakout",
        "direction": "bullish",
        "confidence": 85 if volume_confirmed else 70,
        "status": "confirmed",
        "breakout_price": round(prior_high, 2),
        "volume_confirmed": volume_confirmed,
    }


def detect_breakdown(
    close: pd.Series,
    volume: Optional[pd.Series] = None,
    lookback: int = 20,
) -> Optional[Dict[str, Any]]:

    if len(close) < lookback + 2:
        return None

    current = float(close.iloc[-1])
    prior_low = float(close.iloc[-lookback - 1:-1].min())

    if current >= prior_low:
        return None

    volume_confirmed = False

    if volume is not None and len(volume) >= 21:
        current_volume = float(volume.iloc[-1])
        avg_volume = float(volume.iloc[-21:-1].mean())

        if avg_volume > 0:
            volume_confirmed = current_volume >= avg_volume * 1.5

    return {
        "pattern": "Breakdown",
        "direction": "bearish",
        "confidence": 85 if volume_confirmed else 70,
        "status": "confirmed",
        "breakdown_price": round(prior_low, 2),
        "volume_confirmed": volume_confirmed,
    }


def detect_patterns(
    hist: pd.DataFrame,
    tolerance_pct: float = 3.0,
) -> Dict[str, Any]:

    if hist is None or hist.empty or "Close" not in hist.columns:
        return {
            "detected": [],
            "primary": None,
            "data_gaps": ["patterns.close"]
        }

    close = _clean_series(hist["Close"])

    if len(close) < 40:
        return {
            "detected": [],
            "primary": None,
            "data_gaps": [
                "patterns.insufficient_history"
            ]
        }

    volume = (
        _clean_series(hist["Volume"])
        if "Volume" in hist.columns
        else None
    )

    detected: List[Dict[str, Any]] = []

    detectors = [
        lambda: detect_double_bottom(
            close,
            tolerance_pct
        ),
        lambda: detect_double_top(
            close,
            tolerance_pct
        ),
        lambda: detect_head_shoulders(
            close,
            tolerance_pct + 1.0
        ),
        lambda: detect_inverse_head_shoulders(
            close,
            tolerance_pct + 1.0
        ),
        lambda: detect_breakout(
            close,
            volume
        ),
        lambda: detect_breakdown(
            close,
            volume
        ),
    ]

    for detector in detectors:
        try:
            result = detector()

            if result:
                detected.append(result)

        except Exception:
            continue

    if not detected:
        return {
            "detected": [],
            "primary": None,
            "data_gaps": []
        }

    # Prefer confirmed patterns, then highest confidence.
    detected.sort(
        key=lambda x: (
            x.get("status") == "confirmed",
            x.get("confidence", 0),
        ),
        reverse=True,
    )

    return {
        "detected": detected,
        "primary": detected[0],
        "data_gaps": [],
    }