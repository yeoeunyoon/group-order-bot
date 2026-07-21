# Group-Order Bot

A bot that lets a group order DoorDash together, in plain language, and **never
spends real money without a human saying yes.**

It's built to **demo today on fake data** and **go live the day `dd-cli`
access is approved** — flipping one setting is the only change.

```
GUI you know:   tap pictures in the app
This bot:       "chicken burrito, no onions"  ->  one shared cart  ->  you confirm  ->  ordered
```

## Run the demo (no setup, no account, no API key)

```bash
cd group-order-bot
python demo.py
```

You'll see a full group order play out: requests come in, the agent picks a
store and builds one cart, shows a preview, waits for a human "yes," then
places the (pretend) order.

Try the safety behavior:

```bash
python demo.py --deny                       # human says no -> nothing ordered
GOB_SPEND_LIMIT_CENTS=1000 python demo.py   # $10 limit -> checkout blocked
```

Run the tests:

```bash
pip install -r requirements.txt
pytest
```

## How it's built

| Folder / file | What it is |
|---|---|
| `ddcli/` | **The adapter layer** — one interface, two backends |
| `ddcli/mock.py` | Demo backend: invents realistic stores, prices locally, pretends to submit |
| `ddcli/real.py` | Live backend: drives the real `dd-cli` (wired for v0.2.0) |
| `ddcli/factory.py` | The **switch** — hands the app mock or real based on `config.MODE` |
| `bot/matcher.py` | The **brain** seam — turns human text into menu items; swap for an AI later |
| `bot/order_session.py` | The **coordinator** — runs the flow and **enforces the guardrail** |
| `config.py` | The one place that sets demo/live mode, spending limit, and tip |
| `demo.py` | The runnable end-to-end demo |
| `live_smoke.py` | Read-only live check (search + menu only; spends/creates nothing) |

The flow is staged so the safety gate can't be skipped:

```
collect -> plan -> prepare(price) -> preview -> confirm (human) -> checkout
                                                   │
            checkout() refuses to run unless confirm() happened AND the
            quoted total is under the spending limit. In LIVE mode the
            backend ALSO requires GOB_ALLOW_REAL_ORDERS=1 before it will
            place a real (charged) order — a second, independent latch.
```

Real dd-cli command mapping (v0.2.0):

| App step | dd-cli command |
|---|---|
| search | `dd-cli --json-output search -q "<q>" [--lat --lng --limit]` |
| get menu | `dd-cli --json-output menu --store-id <id>` |
| prepare | `cart add-items --store-id --menu-id --items-json` → `order preview --cart-uuid` |
| checkout | `order submit --cart-uuid --tip-cents N --yes` *(charges)* |

## Going live

Prerequisites: the approved `dd-cli` binary on your `PATH`, and `dd-cli login` done once.

1. **Read-only check** (spends/creates nothing):

   ```bash
   python live_smoke.py "sushi near me"
   ```

2. **Full flow, but submit still latched OFF** — real search/menu/cart/preview,
   then checkout is blocked:

   ```bash
   GOB_MODE=live python demo.py
   ```

3. **Enable real, charged orders** — only when you truly mean it:

   ```bash
   GOB_MODE=live GOB_ALLOW_REAL_ORDERS=1 python demo.py
   ```

The coordinator, the human-confirm guardrail, the preview, and every test stay
exactly as they were in the demo. `GOB_ALLOW_REAL_ORDERS` is a second latch so a
real charge can never fire by accident during development.

Note: `search` needs a location. Set `DD_LAT` / `DD_LNG`, or rely on your
default DoorDash address; otherwise dd-cli falls back to a default region.

## Later: a real AI brain

`bot/matcher.py` currently uses a simple keyword matcher so the demo needs no
API key. To let Claude read the requests, choose the store, and map each
request to a menu item, add an `AgentMatcher` with the same two functions
(`resolve_item`, `choose_store`). Nothing else changes.
