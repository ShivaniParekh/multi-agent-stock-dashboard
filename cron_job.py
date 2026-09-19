from __future__ import annotations

import json
import os
import sys

from pathlib import Path

from app import cycle
from data_sources import timestamp_ist


ROOT = Path(__file__).resolve().parent


def universe_is_stale() -> bool:
    """
    Check whether the NSE universe needs refreshing.
    """
    universe_file = ROOT / "universe.json"

    if not universe_file.exists():
        return True

    try:
        data = json.loads(
            universe_file.read_text(encoding="utf-8")
        )

        return not bool(
            data.get("meta", {}).get("updated_at")
        )

    except Exception:
        return True


def main() -> int:
    print("=" * 70)
    print("SignalDesk scheduled analysis")
    print(f"Started: {timestamp_ist()}")
    print("=" * 70)

    try:
        # ---------------------------------------------------------
        # Optional universe refresh
        # ---------------------------------------------------------
        auto_refresh = os.getenv(
            "CRON_REFRESH_UNIVERSE",
            "true"
        ).lower() == "true"

        print(
            f"Universe auto-refresh enabled: {auto_refresh}"
        )

        if auto_refresh and universe_is_stale():
            print(
                "Universe is stale/missing. "
                "The live cycle will refresh it."
            )

        # ---------------------------------------------------------
        # Run the same live analysis pipeline used by the dashboard
        # ---------------------------------------------------------
        print("Starting live analysis...")

        cycle("live")

        print("=" * 70)
        print("SignalDesk scheduled analysis completed")
        print(f"Finished: {timestamp_ist()}")
        print("=" * 70)

        return 0

    except Exception as exc:
        print("=" * 70)
        print("SignalDesk scheduled analysis FAILED")
        print(f"Time: {timestamp_ist()}")
        print(
            f"{type(exc).__name__}: {exc}"
        )
        print("=" * 70)

        return 1


if __name__ == "__main__":
    sys.exit(main())