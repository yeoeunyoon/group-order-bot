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

import html
import json
import os
import re
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
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise DDCliError(
                f"could not read dd-cli output as JSON:\n{proc.stdout[:500]}"
            ) from exc

        data = _unwrap_envelope(parsed)
        if isinstance(data, dict) and data.get("success") is False:
            raise DDCliError(data.get("message") or "dd-cli reported success=false")
        return data

    # --- read-only (no charge) ---------------------------------------------

    def default_location(self) -> tuple[float | None, float | None]:
        """Lat/lng of the consumer's default saved DoorDash address, if any."""
        data = self._run("address", "list")
        for addr in _as_list(data, "addresses"):
            if addr.get("is_default"):
                return addr.get("lat"), addr.get("lng")
        return None, None

    def search_stores(self, query, lat=None, lng=None, limit=5):
        # "Near me" with no coords → resolve the consumer's default address
        # rather than letting dd-cli fall back to a default region.
        if lat is None and lng is None:
            lat, lng = self.default_location()
        args = ["search", "-q", query, "--limit", str(limit)]
        if lat is not None:
            args += ["--lat", str(lat)]
        if lng is not None:
            args += ["--lng", str(lng)]
        data = self._run(*args)
        return [self._parse_search_store(s) for s in _as_list(data, "stores")]

    def get_menu(self, store_id):
        data = self._run("menu", "--store-id", str(store_id))
        return Store(
            id=str(store_id),
            name=_clean(data.get("store_name", data.get("name", ""))),
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
        items = []
        for line in cart.lines:
            entry = {"item_id": line.item.id, "item_name": line.item.name, "quantity": 1}
            if line.selected_options:
                entry["nested_options"] = [
                    {"id": o.id, "name": o.name, "quantity": 1}
                    for o in line.selected_options
                ]
            items.append(entry)
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
        total_display = total.get("display_string", "")
        # Parse the total from the formatted string to sidestep any
        # cents-vs-dollars ambiguity in the raw unit_amount.
        total_cents = _money_to_cents(total_display)
        if total_cents is None:
            total_cents = int(total.get("unit_amount", 0) or 0)
        return Quote(
            handle=str(cart_uuid),
            store_name=cart.store.name,
            total_cents=total_cents,
            total_display=total_display,
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
            name=_clean(raw.get("name", raw.get("store_name", "Unknown store"))),
            cuisine=raw.get("cuisine", ""),
            eta_minutes=int(raw.get("eta_minutes", 0) or 0),
            delivery_fee_cents=int(raw.get("delivery_fee_cents", 0) or 0),
            menu_id=str(raw.get("menu_id", "")),
        )

    @staticmethod
    def _parse_menu_item(raw: dict) -> MenuItem:
        # `price` is a float in DOLLARS (e.g. 4.8 -> $4.80). Modifiers are NOT
        # inline on the menu item — when raw["has_modifiers"] is true they must
        # be fetched via `restaurant-item-details`. Until that's wired, options
        # stay empty and any note is surfaced as "not applied" (honest, not
        # silently dropped). TODO(modifiers): fetch options for has_modifiers items.
        return MenuItem(
            id=str(raw.get("item_id", raw.get("id", ""))),
            name=_clean(raw.get("name", raw.get("item_name", ""))),
            price_cents=_dollars_to_cents(raw.get("price")),
            description=_clean(raw.get("description", "")),
        )


def _as_list(data: dict, key: str) -> list:
    value = data.get(key, [])
    return value if isinstance(value, list) else []


def _clean(text: str) -> str:
    """Unescape HTML entities DoorDash returns (e.g. 'Soup &amp; Salad')."""
    return html.unescape(text) if text else text


def _dollars_to_cents(price) -> int:
    """dd-cli menu prices are floats in dollars (4.8 -> 480 cents)."""
    try:
        return round(float(price) * 100)
    except (TypeError, ValueError):
        return 0


def _money_to_cents(display: str) -> int | None:
    """Parse a formatted money string like '$45.29' or 'CA$10.00' to cents."""
    if not display:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", display)
    try:
        return round(float(cleaned) * 100)
    except (TypeError, ValueError):
        return None


def _unwrap_envelope(parsed):
    """dd-cli wraps results in an MCP-style envelope. Pull out the real data.

    Shape: {"content": [{"type":"text","text":"<stringified JSON>"}],
            "structuredContent": {<the actual fields: stores/items/...>}}
    Prefer structuredContent; fall back to parsing the content[].text JSON.
    """
    if not isinstance(parsed, dict):
        return parsed
    inner = parsed.get("structuredContent")
    if isinstance(inner, dict):
        return inner
    for part in parsed.get("content", []) or []:
        if isinstance(part, dict) and part.get("type") == "text":
            try:
                return json.loads(part["text"])
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    return parsed
