from __future__ import annotations

import sys

from app import cycle
from data_sources import timestamp_ist


def main() -> int:
    print("=" * 70)
    print("SignalDesk scheduled analysis")
    print(f"Started: {timestamp_ist()}")
    print("=" * 70)

    try:
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
        print(f"{type(exc).__name__}: {exc}")
        print("=" * 70)

        return 1


if __name__ == "__main__":
    sys.exit(main())