"""End-to-end demo:  python demo.py

Plays out a full group order — the same flow that places real orders in live
mode. Watch for the confirm gate: the order is NOT placed until a (simulated)
human says yes.

Try also:
    python demo.py --deny                        # human says no -> nothing ordered
    GOB_SPEND_LIMIT_CENTS=1000 python demo.py    # tiny limit -> checkout blocked

Live mode (after `dd-cli login`):
    GOB_MODE=live python demo.py                 # real search/menu/preview, but
                                                 # submit still blocked unless
    GOB_MODE=live GOB_ALLOW_REAL_ORDERS=1 python demo.py   # ...this is set
"""

import sys

import config
from bot import OrderSession
from ddcli import DDCliError, GuardrailError, get_client

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
          f"limit = ${config.SPEND_LIMIT_CENTS / 100:,.2f}")

    session = OrderSession(
        client=get_client(),
        spend_limit_cents=config.SPEND_LIMIT_CENTS,
        tip_cents=config.TIP_CENTS,
    )

    banner("1. Everyone drops their request in the channel")
    for person, text in GROUP_REQUESTS:
        print(f"   {person}: \"{text}\"")
        session.collect(person, text)

    try:
        banner("2. The agent searches, picks a store, and builds one shared cart")
        session.plan()

        banner("3. Pricing the cart (no charge)")
        session.prepare()

        banner("4. Preview — nothing is ordered yet")
        print(session.preview())
    except (DDCliError, GuardrailError) as exc:
        print(f"   ✋ Stopped before any charge: {exc}")
        return 1

    banner("5. Confirm gate — a human decides")
    if deny:
        print("   Yeoeun: \"actually, no\"  ✗")
        print("\n   Order was NOT placed. No money spent.")
        return 0
    print("   Yeoeun: \"yes, order it\"  ✓")
    session.confirm()

    banner("6. Checkout")
    try:
        result = session.checkout()
    except (GuardrailError, DDCliError) as exc:
        print(f"   🛡️  Blocked: {exc}")
        return 0

    print(f"   ✅ Order {result.order_id} — {result.total_display}, "
          f"status: {result.status}"
          + (f", ETA {result.eta_text}" if result.eta_text else "") + " 🛵")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
