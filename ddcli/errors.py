"""Errors the app can raise."""


class DDCliError(Exception):
    """The real dd-cli tool failed or returned something we couldn't read."""


class GuardrailError(Exception):
    """A safety rule blocked checkout (no human confirmation, or over the
    spending limit). This is the promise that an agent never spends real
    money on its own."""
