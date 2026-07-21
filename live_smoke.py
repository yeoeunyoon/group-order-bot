"""Read-only live check against the real dd-cli. Spends nothing, creates nothing.

Exercises only the two no-charge read commands (`search`, then `menu` on the
first result) so we can confirm the RealDDClient parses actual dd-cli output.
No cart is built, no order is previewed or placed.

Run after `dd-cli login`:
    python live_smoke.py "sushi near me"

Tip: set DD_LAT / DD_LNG (or have a default DoorDash address) so "near me"
resolves to your location rather than dd-cli's fallback.
"""

import sys

from ddcli.real import RealDDClient

query = sys.argv[1] if len(sys.argv) > 1 else "sushi near me"
client = RealDDClient()

print(f"search: {query!r}")
stores = client.search_stores(query, limit=5)
if not stores:
    print("  no stores returned — try a different query or set DD_LAT/DD_LNG.")
    raise SystemExit(0)

for s in stores:
    print(f"  - {s.name!r}  store_id={s.id}")

first = stores[0]
print(f"\nmenu for {first.name!r} (store_id={first.id}):")
store = client.get_menu(first.id)
print(f"  menu_id={store.menu_id}  ·  {len(store.menu)} items")
for item in store.menu[:8]:
    price = f"${item.price_cents / 100:,.2f}" if item.price_cents else "(no price)"
    print(f"  - {item.name}  {price}  item_id={item.id}")

print("\n✓ read-only live check done — nothing was ordered.")
