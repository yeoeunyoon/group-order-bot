"""Live-mode backend: drives the real DoorDash `dd-cli`.

Wired against dd-cli v0.2.0's real command surface:

    dd-cli --json-output search -q "<query>" [--lat --lng --limit]   -> stores[]
    dd-cli --json-output menu --store-id <id>                        -> menu_id, items[]
    dd-cli --json-output cart add-items --store-id --menu-id --items-json  -> cart_uuid
    dd-cli --json-output order preview --cart-uuid <uuid>            -> quote (no charge)
    dd-cli --json-output order submit  --cart-uuid <uuid> --yes      -> order_uuid (CHARGES)

Two facts from dd-cli's own docs shaped this file:
  * `--json-output` is a GLOBAL flag and must come BEFORE the subcommand.
  * `order submit` is DESTRUCTIVE (charges the default card) and needs `--yes`
    when there's no TTY. So place_order() has a SECOND safety latch on top of
    the app's human-confirm guardrail: the env var GOB_ALLOW_REAL_ORDERS must
    be "1", or it refuses to submit. This makes an accidental real charge
    during development impossible.

Field names come from the dd-cli `--help` docs; the `_parse_*` helpers are the
only spots to adjust if a response shape differs in practice.
"""

import json
import os
import subprocess

from .base import DDClient
from .errors import DDCliError, GuardrailError
from .models import Cart, MenuItem, OrderResult, Quote, Store


class RealDDClient(DDClient):
    def __init__(self, binary: str = "dd-cli", timeout_seconds: int = 45):
        self.binary = binary
        self.timeout_seconds = timeout_seconds

    def _run(self, *args: str) -> dict:
        """Run a dd-cli command with global --json-output and return parsed JSON."""
        cmd = [self.binary, "--json-output", *args]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout_seconds
            )
        except FileNotFoundError as exc:
            raise DDCliError(
                f"'{self.binary}' not found on PATH. Install the approved dd-cli "
                f"binary (see the project README) and run `dd-cli login` once."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DDCliError(f"dd-cli timed out after {self.timeout_seconds}s") from exc

        if proc.returncode != 0:
            msg = proc.stderr.strip() or proc.stdout.strip()
            if "login" in msg.lower():
                msg += "  (try: dd-cli login)"
            raise DDCliError(msg or f"dd-cli {' '.join(args)} failed")

        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise DDCliError(
                f"could not read dd-cli output as JSON:\n{proc.stdout[:500]}"
            ) from exc

    # --- read-only (no charge) ---------------------------------------------

    def search_stores(self, query, lat=None, lng=None, limit=5):
        args = ["search", "-q", query, "--limit", str(limit)]
        if lat is not None:
            args += ["--lat", str(lat)]
        if lng is not None:
            args += ["--lng", str(lng)]
        # If no lat/lng, dd-cli falls back to env DD_LAT/DD_LNG then a default.
        data = self._run(*args)
        return [self._parse_search_store(s) for s in _as_list(data, "stores")]

    def get_menu(self, store_id):
        data = self._run("menu", "--store-id", str(store_id))
        return Store(
            id=str(store_id),
            name=data.get("store_name", data.get("name", "")),
            cuisine="",
            eta_minutes=0,
            delivery_fee_cents=0,
            menu_id=str(data.get("menu_id", "")),
            menu=[self._parse_menu_item(i) for i in _as_list(data, "items")],
        )

    def prepare_order(self, cart: Cart) -> Quote:
        """add-items builds the server cart; preview prices it. No charge."""
        if not cart.store.menu_id:
            raise DDCliError(
                "missing menu_id — call get_menu(store_id) so the cart knows "
                "which menu to add items from."
            )
        items = [
            {"item_id": line.item.id, "item_name": line.item.name, "quantity": 1}
            for line in cart.lines
        ]
        add = self._run(
            "cart", "add-items",
            "--store-id", cart.store.id,
            "--menu-id", cart.store.menu_id,
            "--items-json", json.dumps(items),
        )
        if add.get("success") is False:
            errs = "; ".join(
                e.get("error_message", "item error") for e in _as_list(add, "item_errors")
            )
            raise DDCliError(f"cart add-items failed: {errs or 'unknown error'}")
        cart_uuid = add.get("cart_uuid")
        if not cart_uuid:
            raise DDCliError("cart add-items returned no cart_uuid")

        prev = self._run("order", "preview", "--cart-uuid", str(cart_uuid))
        quote = prev.get("quote", prev)
        total = quote.get("net_total_before_tip", {})
        delivery = quote.get("delivery_availability", {})
        return Quote(
            handle=str(cart_uuid),
            store_name=cart.store.name,
            total_cents=int(total.get("unit_amount", 0) or 0),
            total_display=total.get("display_string", ""),
            eta_text=delivery.get("asap_minutes_range_string", ""),
            raw=prev,
        )

    # --- placing the order (CHARGES money) ---------------------------------

    def place_order(self, quote: Quote, tip_cents: int = 0) -> OrderResult:
        # Second safety latch: refuse to spend real money unless explicitly enabled.
        if os.environ.get("GOB_ALLOW_REAL_ORDERS") != "1":
            raise GuardrailError(
                "Live checkout is disabled. Set GOB_ALLOW_REAL_ORDERS=1 to allow "
                "placing REAL, CHARGED DoorDash orders. (The human confirm gate "
                "still applies on top of this.)"
            )
        data = self._run(
            "order", "submit",
            "--cart-uuid", quote.handle,
            "--tip-cents", str(tip_cents),
            "--yes",  # required for non-interactive callers
        )
        return OrderResult(
            order_id=str(data.get("order_uuid", data.get("order_id", ""))),
            # A successful return means "accepted into processing", not settled;
            # poll `order status --order-uuid <id>` before calling it confirmed.
            status=data.get("status", "pending"),
            total_cents=quote.total_cents,
            total_display=quote.total_display,
            eta_text=quote.eta_text,
        )

    # --- parsers: adjust here if a real response shape differs --------------

    @staticmethod
    def _parse_search_store(raw: dict) -> Store:
        return Store(
            id=str(raw.get("store_id", raw.get("id", ""))),
            name=raw.get("name", raw.get("store_name", "Unknown store")),
            cuisine=raw.get("cuisine", ""),
            eta_minutes=int(raw.get("eta_minutes", 0) or 0),
            delivery_fee_cents=int(raw.get("delivery_fee_cents", 0) or 0),
            menu_id=str(raw.get("menu_id", "")),
        )

    @staticmethod
    def _parse_menu_item(raw: dict) -> MenuItem:
        return MenuItem(
            id=str(raw.get("item_id", raw.get("id", ""))),
            name=raw.get("name", raw.get("item_name", "")),
            price_cents=int(raw.get("price", raw.get("price_cents", 0)) or 0),
            description=raw.get("description", ""),
        )


def _as_list(data: dict, key: str) -> list:
    value = data.get(key, [])
    return value if isinstance(value, list) else []
