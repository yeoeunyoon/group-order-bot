"""End-to-end demo you can run today:  python demo.py

It plays out a full group order on fake data — the same flow that will place
real orders once dd-cli is wired in. Watch for the confirm gate: the order is
NOT placed until a (simulated) human says yes.

Try also:
    python demo.py --deny        # human says no -> nothing is ordered
    GOB_SPEND_LIMIT_CENTS=1000 python demo.py   # tiny limit -> checkout blocked
"""

import sys

import config
from bot import OrderSession
from ddcli import GuardrailError, dollars, get_client

# The pretend group chat: who asked for what, in plain language.
GROUP_REQUESTS = [
    ("Yeoeun", "chicken burrito, no onions"),
    ("Sam", "steak bowl"),
    ("Priya", "veggie tacos"),
    ("Alex", "chips and guac, extra guac"),
]


def banner(text: str) -> None:
    print(f"\n\033[1m{text}\033[0m")


def main() -> int:
    deny = "--deny" in sys.argv

    print(f"Group-Order Bot  ·  mode = {config.MODE.upper()}  ·  "
          f"limit = {dollars(config.SPEND_LIMIT_CENTS)}")

    session = OrderSession(client=get_client(), spend_limit_cents=config.SPEND_LIMIT_CENTS)

    banner("1. Everyone drops their request in the channel")
    for person, text in GROUP_REQUESTS:
        print(f"   {person}: \"{text}\"")
        session.collect(person, text)

    banner("2. The agent searches, picks a store, and builds one shared cart")
    session.plan()

    banner("3. Preview — nothing is ordered yet")
    print(session.preview())

    banner("4. Confirm gate — a human decides")
    if deny:
        print("   Yeoeun: \"actually, no\"  ✗")
        print("\n   Order was NOT placed. No money spent.")
        return 0
    print("   Yeoeun: \"yes, order it\"  ✓")
    session.confirm()

    banner("5. Checkout")
    try:
        result = session.checkout()
    except GuardrailError as exc:
        print(f"   🛡️  Blocked by guardrail: {exc}")
        return 0

    print(f"   ✅ Order {result.order_id} placed — {dollars(result.total_cents)}, "
          f"arriving in ~{result.eta_minutes} min 🛵")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
