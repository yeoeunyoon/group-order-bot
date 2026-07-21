"""Demo-mode backend: fake but realistic DoorDash data.

This is what lets the whole app run today without spending money. Nothing here
touches the network. When you go live, the app stops calling this file and
calls real.py instead — see factory.py.
"""

import itertools

from .base import DDClient
from .models import Cart, MenuItem, ModifierOption, OrderResult, Quote, Store, dollars

# A tiny pretend universe of nearby restaurants.
_CATALOG: list[Store] = [
    Store(
        id="store_ippudo",
        name="Ippudo Ramen",
        cuisine="ramen japanese noodles",
        eta_minutes=32,
        delivery_fee_cents=399,
        menu_id="menu_ippudo",
        menu=[
            MenuItem("i1", "Tonkotsu Ramen", 1650, "Pork broth, chashu, egg"),
            MenuItem("i2", "Spicy Miso Ramen", 1750, "Miso broth with chili"),
            MenuItem("i3", "Veggie Ramen", 1550, "Mushroom broth, tofu"),
            MenuItem("i4", "Pork Gyoza", 850, "Six pan-fried dumplings"),
        ],
    ),
    Store(
        id="store_chipotle",
        name="Chipotle",
        cuisine="mexican burrito tacos bowl",
        eta_minutes=24,
        delivery_fee_cents=299,
        menu_id="menu_chipotle",
        menu=[
            MenuItem("c1", "Chicken Burrito", 1195, "Flour tortilla, rice, beans",
                     options=[
                         ModifierOption("c1o1", "No Onions", 0),
                         ModifierOption("c1o2", "Extra Chicken", 250),
                     ]),
            MenuItem("c2", "Steak Bowl", 1395, "No tortilla, extra steak"),
            MenuItem("c3", "Veggie Tacos", 995, "Three soft tacos, fajita veg"),
            MenuItem("c4", "Chips & Guac", 495, "Fresh guacamole",
                     options=[ModifierOption("c4o1", "Extra Guac", 150)]),
        ],
    ),
    Store(
        id="store_sweetgreen",
        name="Sweetgreen",
        cuisine="salad healthy bowl vegetarian",
        eta_minutes=19,
        delivery_fee_cents=349,
        menu_id="menu_sweetgreen",
        menu=[
            MenuItem("s1", "Harvest Bowl", 1345, "Chicken, sweet potato, wild rice"),
            MenuItem("s2", "Kale Caesar Salad", 1145, "Kale, parmesan, croutons"),
            MenuItem("s3", "Guacamole Greens", 1245, "Avocado, tomato, greens"),
        ],
    ),
]

_cart_counter = itertools.count(1)
_order_counter = itertools.count(1001)


class MockDDClient(DDClient):
    def search_stores(self, query, lat=None, lng=None, limit=5):
        q = query.lower()
        words = {w for w in q.replace(",", " ").split() if len(w) > 2}
        scored = []
        for store in _CATALOG:
            haystack = f"{store.name} {store.cuisine}".lower()
            score = sum(1 for w in words if w in haystack)
            scored.append((score, store))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        if scored and scored[0][0] == 0:  # nothing matched — act like a broad search
            return list(_CATALOG)[:limit]
        return [store for score, store in scored if score > 0][:limit]

    def get_menu(self, store_id):
        for store in _CATALOG:
            if store.id == store_id:
                return store
        raise KeyError(f"unknown store: {store_id}")

    def prepare_order(self, cart: Cart) -> Quote:
        return Quote(
            handle=f"MOCK-CART-{next(_cart_counter)}",
            store_name=cart.store.name,
            total_cents=cart.total_cents,
            total_display=dollars(cart.total_cents),
            eta_text=f"~{cart.store.eta_minutes} min",
        )

    def place_order(self, quote: Quote, tip_cents: int = 0) -> OrderResult:
        total = quote.total_cents + tip_cents
        return OrderResult(
            order_id=f"MOCK-{next(_order_counter)}",
            status="placed",
            total_cents=total,
            total_display=dollars(total),
            eta_text=quote.eta_text,
        )
