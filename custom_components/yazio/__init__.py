"""Inoffizielle Yazio-Integration: liefert die heute gegessenen Kalorien."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import YazioApiError, YazioAuthError, YazioClient, parse_summary
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]


class YazioCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fragt Yazio regelmäßig ab."""

    def __init__(self, hass: HomeAssistant, client: YazioClient) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        today = dt_util.now().date().isoformat()
        try:
            raw = await self.client.async_get_summary(today)
        except YazioAuthError as err:
            raise ConfigEntryAuthFailed("Yazio-Login abgelehnt") from err
        except YazioApiError as err:
            raise UpdateFailed(f"Yazio nicht erreichbar: {err}") from err
        data = parse_summary(raw)
        data["date"] = today
        return data


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = YazioClient(
        async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
    )
    coordinator = YazioCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
