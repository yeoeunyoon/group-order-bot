"""One place that decides how the app behaves.

The single most important line is MODE:
    "demo"  -> use fake data (works today, spends no money)
    "live"  -> drive the real dd-cli (after waitlist approval)

Everything reads from environment variables so you can flip modes without
editing code:  GOB_MODE=live python demo.py
"""

import os

# "demo" or "live". Flipping this is the whole demo -> production switch.
MODE = os.environ.get("GOB_MODE", "demo").lower()

# Path/name of the dd-cli binary (only used in live mode).
DDCLI_BINARY = os.environ.get("GOB_DDCLI", "dd-cli")

# Safety cap: checkout is blocked above this total, in cents. Default $75.00.
SPEND_LIMIT_CENTS = int(os.environ.get("GOB_SPEND_LIMIT_CENTS", "7500"))
