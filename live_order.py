"""Full-pipeline LIVE test — builds a real cart and pulls real pricing, but
does NOT place an order.

    GOB_MODE=live python live_order.py "sushi"

It runs the real flow end to end:
    search -> menu -> cart add-items -> order preview   (all no-charge)
then confirms and calls checkout to show the second safety latch stop it:
`order submit` never runs unless GOB_ALLOW_REAL_ORDERS=1.

Side effect to know about: `cart add-items` creates a REAL open cart in your
DoorDash account (unsubmitted, uncharged). Clean up anytime with:
    dd-cli cart list
    dd-cli cart delete --cart-uuid <uuid>
"""

import sys

import config
from bot import OrderSession
from ddcli import DDCliError, GuardrailError, dollars, get_client

QUERY = sys.argv[1] if len(sys.argv) > 1 else "sushi"

# Realistic requests for a sushi place — tweak to match a real nearby menu.
GROUP_REQUESTS = [
    ("Yeoeun", "miso soup"),
    ("Sam", "edamame"),
    ("Priya", "california roll"),
    ("Alex", "salmon avocado roll"),
]


def banner(text):
    print(f"\n\033[1m{text}\033[0m")


def main() -> int:
    print(f"LIVE order test  ·  mode = {config.MODE.upper()}  ·  "
          f"search = {QUERY!r}  ·  limit = {dollars(config.SPEND_LIMIT_CENTS)}")
    if config.MODE != "live":
        print("  (set GOB_MODE=live to hit the real dd-cli)")

    session = OrderSession(get_client(), config.SPEND_LIMIT_CENTS, config.TIP_CENTS)

    banner("1. Requests")
    for person, text in GROUP_REQUESTS:
        print(f"   {person}: \"{text}\"")
        session.collect(person, text)

    try:
        banner("2. Plan — search + pick store + match items")
        cart = session.plan(search_query=QUERY)
        print(f"   store: {cart.store.name}  ({len(cart.lines)} items matched)")
        for line in cart.lines:
            print(f"     {line.person}: {line.item.name} ({dollars(line.item.price_cents)})")

        banner("3. Prepare — real cart + real DoorDash pricing (no charge)")
        session.prepare()
        print(session.preview())
    except (DDCliError, GuardrailError) as exc:
        print(f"   ✋ Stopped before any charge: {exc}")
        return 1

    banner("4. Confirm + checkout — expect the safety latch to block")
    session.confirm()
    try:
        result = session.checkout()
        print(f"   ✅ Order {result.order_id} — {result.total_display}")
    except GuardrailError as exc:
        print(f"   🛡️  Blocked as designed: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
