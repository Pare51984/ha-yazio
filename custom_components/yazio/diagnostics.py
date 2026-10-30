"""Diagnostics download: helps to adapt the integration to Yazio's answers.

Contains the computed sensor values and the raw answers of the optional
endpoints. Login data is never included; diary entries are reduced to their
structure (field names), not what you ate.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_EMAIL, CONF_PASSWORD

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, "access_token", "refresh_token", "id", "uuid", "user_token", "payment_provider_transaction_id", "fasting_countdown_id"}


def _shape(value: Any, depth: int = 0) -> Any:
    """Field names and types only, no content."""
    if depth > 4:
        return "…"
    if isinstance(value, dict):
        return {k: _shape(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_shape(value[0], depth + 1), f"({len(value)} items)"] if value else []
    return type(value).__name__


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    raw = dict(coordinator.raw_extras)
    if "consumed_items" in raw:
        raw["consumed_items"] = _shape(raw["consumed_items"])
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "data": async_redact_data(dict(coordinator.data or {}), TO_REDACT),
        "raw_extras": async_redact_data(raw, TO_REDACT),
    }
