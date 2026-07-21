"""Tests for the order flow and — most importantly — the safety guardrails."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bot import OrderSession
from ddcli.errors import GuardrailError
from ddcli.mock import MockDDClient

LIMIT = 7500


def make_session(limit=LIMIT):
    session = OrderSession(client=MockDDClient(), spend_limit_cents=limit)
    session.collect("Yeoeun", "chicken burrito, no onions")
    session.collect("Sam", "steak bowl")
    return session


def priced(limit=LIMIT):
    """A session taken through plan() + prepare() (no charge yet)."""
    session = make_session(limit)
    session.plan()
    session.prepare()
    return session


def test_plan_builds_a_cart_with_matched_items():
    session = make_session()
    cart = session.plan()
    assert cart.store.name == "Chipotle"
    assert len(cart.lines) == 2
    assert cart.total_cents == 1195 + 1395 + 299  # two items + delivery


def test_note_is_extracted_from_request():
    session = make_session()
    session.plan()
    burrito = next(l for l in session.cart.lines if l.person == "Yeoeun")
    assert "no onions" in burrito.note


def test_note_maps_to_a_real_modifier_option():
    session = make_session()
    session.plan()
    burrito = next(l for l in session.cart.lines if l.person == "Yeoeun")
    assert [o.name for o in burrito.selected_options] == ["No Onions"]
    assert burrito.unresolved_note == ""  # fully mapped, nothing dropped


def test_priced_modifier_adds_to_total():
    session = OrderSession(client=MockDDClient(), spend_limit_cents=LIMIT)
    session.collect("Alex", "chips and guac, extra guac")  # +$1.50 option
    session.plan()
    session.prepare()
    assert session.quote.total_cents == 495 + 150 + 299  # item + Extra Guac + delivery


def test_unmappable_note_is_flagged_not_dropped():
    session = OrderSession(client=MockDDClient(), spend_limit_cents=LIMIT)
    session.collect("Sam", "steak bowl, no cilantro")  # Steak Bowl has no options
    session.plan()
    line = session.cart.lines[0]
    assert line.selected_options == []
    assert "no cilantro" in line.unresolved_note


def test_prepare_prices_without_charging():
    session = priced()
    assert session.quote is not None
    assert session.quote.total_cents == 1195 + 1395 + 299
    assert session.quote.total_display == "$28.89"


def test_checkout_blocked_without_confirmation():
    session = priced()
    with pytest.raises(GuardrailError, match="no human confirmation"):
        session.checkout()


def test_checkout_blocked_over_spend_limit():
    session = priced(limit=500)  # $5.00, far below the cart total
    session.confirm()
    with pytest.raises(GuardrailError, match="exceeds"):
        session.checkout()


def test_new_request_invalidates_prior_confirmation():
    session = priced()
    session.confirm()
    session.collect("Priya", "veggie tacos")  # order changed after confirming
    session.plan()
    session.prepare()
    with pytest.raises(GuardrailError, match="no human confirmation"):
        session.checkout()


def test_confirm_requires_a_prepared_quote():
    session = make_session()
    session.plan()  # priced step skipped
    with pytest.raises(ValueError, match="prepare"):
        session.confirm()


def test_happy_path_places_order():
    session = priced()
    session.confirm()
    result = session.checkout()
    assert result.order_id.startswith("MOCK-")
    assert result.status == "placed"
    assert result.total_cents == session.quote.total_cents
