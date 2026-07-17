"""Tests for the order flow and — most importantly — the safety guardrail."""

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


def test_checkout_blocked_without_confirmation():
    session = make_session()
    session.plan()
    with pytest.raises(GuardrailError, match="no human confirmation"):
        session.checkout()


def test_checkout_blocked_over_spend_limit():
    session = make_session(limit=500)  # $5.00, far below the cart total
    session.plan()
    session.confirm()
    with pytest.raises(GuardrailError, match="exceeds"):
        session.checkout()


def test_new_request_invalidates_prior_confirmation():
    session = make_session()
    session.plan()
    session.confirm()
    session.collect("Priya", "veggie tacos")  # order changed after confirming
    session.plan()
    with pytest.raises(GuardrailError, match="no human confirmation"):
        session.checkout()


def test_happy_path_places_order():
    session = make_session()
    session.plan()
    session.confirm()
    result = session.checkout()
    assert result.order_id.startswith("MOCK-")
    assert result.status == "placed"
    assert result.total_cents == session.cart.total_cents
