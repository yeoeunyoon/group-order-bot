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
| `ddcli/mock.py` | Demo backend: invents realistic stores, pretends to check out |
| `ddcli/real.py` | Live backend: shells out to the real `dd-cli` *(finish on approval)* |
| `ddcli/factory.py` | The **switch** — hands the app mock or real based on `config.MODE` |
| `bot/matcher.py` | The **brain** seam — turns human text into menu items; swap for an AI later |
| `bot/order_session.py` | The **coordinator** — runs the flow and **enforces the guardrail** |
| `config.py` | The one place that sets demo/live mode and the spending limit |
| `demo.py` | The runnable end-to-end demo |

The flow is staged so the safety gate can't be skipped:

```
collect  ->  plan  ->  preview  ->  confirm (human) ->  checkout
                                       │
              checkout() refuses to run unless confirm() happened
              AND the total is under the spending limit
```

## Going live (once dd-cli is approved)

1. Install the approved `dd-cli` binary and make sure it's on your `PATH`.
2. Run `dd-cli --help` and fill in the three `# TODO(live)` spots in
   `ddcli/real.py` (the exact menu/cart/checkout commands and JSON shape).
3. Switch modes:

   ```bash
   GOB_MODE=live python demo.py
   ```

That's it — the coordinator, the guardrail, the preview, and every test stay
exactly as they were in the demo.

## Later: a real AI brain

`bot/matcher.py` currently uses a simple keyword matcher so the demo needs no
API key. To let Claude read the requests, choose the store, and map each
request to a menu item, add an `AgentMatcher` with the same two functions
(`resolve_item`, `choose_store`). Nothing else changes.
