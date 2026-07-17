"""Live-mode backend: shells out to the real DoorDash `dd-cli`.

STATUS: ready to finish the day dd-cli access is approved.

We already know these real commands from DoorDash's docs:
    dd-cli search --query "ramen near me"
    dd-cli order history
    dd-cli --help

What we do NOT yet know (because it needs the approved binary in hand):
    * the exact menu / cart / checkout subcommands and their flags
    * whether there is a --json / machine-readable output mode
    * the exact shape of the JSON that comes back

So every place that depends on those is marked `# TODO(live)` below. The three
`_parse_*` helpers are the ONLY things that should need editing once we can run
`dd-cli --help` for real — the rest of the app stays exactly as demoed.
"""

import json
import subprocess

from .base import DDClient
from .errors import DDCliError
from .models import Cart, MenuItem, OrderResult, Store


class RealDDClient(DDClient):
    def __init__(self, binary: str = "dd-cli", timeout_seconds: int = 30):
        self.binary = binary
        self.timeout_seconds = timeout_seconds

    def _run(self, *args: str) -> dict:
        """Run a dd-cli command and return parsed JSON.

        We append `--json` on the assumption dd-cli offers a machine-readable
        mode (its own docs pitch it as agent-drivable). If the real flag turns
        out to be different, change it in this one spot.
        """
        cmd = [self.binary, *args, "--json"]  # TODO(live): confirm the JSON flag
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise DDCliError(
                f"'{self.binary}' not found. Install the approved dd-cli binary "
                f"and make sure it's on your PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DDCliError(f"dd-cli timed out after {self.timeout_seconds}s") from exc

        if proc.returncode != 0:
            raise DDCliError(proc.stderr.strip() or f"dd-cli {' '.join(args)} failed")

        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise DDCliError(
                f"could not read dd-cli output as JSON:\n{proc.stdout[:500]}"
            ) from exc

    # --- public API ---------------------------------------------------------

    def search_stores(self, query: str) -> list[Store]:
        data = self._run("search", "--query", query)
        return [self._parse_store(s) for s in _as_list(data, "stores")]

    def get_menu(self, store_id: str) -> Store:
        # TODO(live): confirm the real subcommand (e.g. `dd-cli menu --store <id>`)
        data = self._run("menu", "--store", store_id)
        return self._parse_store(data.get("store", data))

    def checkout(self, cart: Cart) -> OrderResult:
        # TODO(live): the real flow is probably: add each item to a cart, then
        # `dd-cli checkout`. Wire the exact subcommands here once known. Until
        # then this raises loudly rather than pretending to spend money.
        raise DDCliError(
            "Live checkout is not wired yet — finish the TODO(live) sections in "
            "real.py using the real `dd-cli` command reference."
        )

    # --- parsers: the ONLY bits expected to change once we see real output ---

    @staticmethod
    def _parse_store(raw: dict) -> Store:
        return Store(
            id=str(raw.get("id", "")),
            name=raw.get("name", "Unknown store"),
            cuisine=raw.get("cuisine", ""),
            eta_minutes=int(raw.get("eta_minutes", 0)),
            delivery_fee_cents=int(raw.get("delivery_fee_cents", 0)),
            menu=[RealDDClient._parse_item(i) for i in _as_list(raw, "menu")],
        )

    @staticmethod
    def _parse_item(raw: dict) -> MenuItem:
        return MenuItem(
            id=str(raw.get("id", "")),
            name=raw.get("name", ""),
            price_cents=int(raw.get("price_cents", 0)),
            description=raw.get("description", ""),
        )

    @staticmethod
    def _parse_order(raw: dict) -> OrderResult:
        return OrderResult(
            order_id=str(raw.get("order_id", raw.get("id", ""))),
            status=raw.get("status", "placed"),
            total_cents=int(raw.get("total_cents", 0)),
            eta_minutes=int(raw.get("eta_minutes", 0)),
        )


def _as_list(data: dict, key: str) -> list:
    value = data.get(key, [])
    return value if isinstance(value, list) else []
