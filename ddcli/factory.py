"""The switch. Hands the app the right backend based on config.MODE.

This is the seam the whole 'demo today, live later' promise rests on: the bot
calls get_client() and gets back something that satisfies the DDClient contract.
It never learns whether it's the mock or the real thing.
"""

import config

from .base import DDClient
from .mock import MockDDClient
from .real import RealDDClient


def get_client() -> DDClient:
    if config.MODE == "live":
        return RealDDClient(binary=config.DDCLI_BINARY)
    if config.MODE == "demo":
        return MockDDClient()
    raise ValueError(f"Unknown GOB_MODE={config.MODE!r} (expected 'demo' or 'live')")
