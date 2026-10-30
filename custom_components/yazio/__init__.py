"""Unofficial Yazio integration: values from the Yazio diary as sensors."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.recorder.models import StatisticData, StatisticMeanType, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform, UnitOfMass
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    YazioApiError,
    YazioAuthError,
    YazioClient,
    parse_streak,
    parse_subscription,
    parse_summary,
    parse_weight_history,
)
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN, EXTRA_INTERVAL, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_IMPORT_WEIGHT = "import_weight_history"
ATTR_ENTRY_ID = "config_entry_id"
ATTR_START_DATE = "start_date"


class YazioCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls Yazio. Daily summary every 15 min, streak and subscription hourly."""

    def __init__(self, hass: HomeAssistant, client: YazioClient) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.client = client
        self._extras: dict[str, Any] = {}
        self._extras_fetched: datetime | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        today = dt_util.now().date().isoformat()
        try:
            raw = await self.client.async_get_summary(today)
        except YazioAuthError as err:
            raise ConfigEntryAuthFailed("Yazio login rejected") from err
        except YazioApiError as err:
            raise UpdateFailed(f"Yazio not reachable: {err}") from err
        data = parse_summary(raw)
        data["date"] = today

        now = dt_util.utcnow()
        if self._extras_fetched is None or now - self._extras_fetched >= EXTRA_INTERVAL:
            await self._async_fetch_extras(today)
            self._extras_fetched = now
        data.update(self._extras)
        return data

    async def _async_fetch_extras(self, today: str) -> None:
        """Optional data. A failure here never breaks the main sensors."""
        try:
            streak = parse_streak(await self.client.async_get_extra("/user/streak"), today)
            if streak:
                self._extras.update(streak)
        except YazioApiError as err:
            _LOGGER.debug("Streak not available: %s", err)
        try:
            sub = parse_subscription(await self.client.async_get_extra("/user/subscription/latest"))
            if sub:
                self._extras.update(sub)
        except YazioApiError as err:
            # Accounts that never had Pro may answer 404 here.
            if "HTTP 404" in str(err):
                self._extras.update(parse_subscription(None))
            else:
                _LOGGER.debug("Subscription not available: %s", err)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the weight import action once for the domain."""

    async def import_weight(call: ServiceCall) -> ServiceResponse:
        entries = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
        ]
        wanted = call.data.get(ATTR_ENTRY_ID)
        if wanted:
            entries = [e for e in entries if e.entry_id == wanted]
        if len(entries) != 1:
            raise HomeAssistantError(
                "Select exactly one loaded Yazio account (config_entry_id)."
            )
        entry = entries[0]
        start: date = call.data.get(ATTR_START_DATE) or (dt_util.now().date() - timedelta(days=5 * 365))
        return await _async_import_weight(hass, entry, start)

    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_WEIGHT,
        import_weight,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_ENTRY_ID): cv.string,
                vol.Optional(ATTR_START_DATE): cv.date,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def _async_import_weight(hass: HomeAssistant, entry: ConfigEntry, start: date) -> dict[str, Any]:
    """Copy Yazio's weight history into an external long-term statistic.

    It shows up as statistic `yazio:weight_<id>` (e.g. in a statistics graph
    card). Running it again is safe: the same hours are overwritten.
    """
    coordinator: YazioCoordinator = entry.runtime_data
    end = dt_util.now().date()
    entries: list[tuple[str, float]] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=364), end)
        try:
            raw = await coordinator.client.async_get_extra(
                "/user/bodyvalues/weight",
                {"start": chunk_start.isoformat(), "end": chunk_end.isoformat()},
            )
        except YazioApiError as err:
            raise HomeAssistantError(f"Could not read weight history from Yazio: {err}") from err
        entries += parse_weight_history(raw)
        chunk_start = chunk_end + timedelta(days=1)

    hourly: dict[datetime, float] = {}
    for when, kg in entries:
        local = dt_util.parse_datetime(when.replace(" ", "T"))
        if local is None:
            continue
        if local.tzinfo is None:
            local = local.replace(tzinfo=dt_util.get_default_time_zone())
        hour = dt_util.as_utc(local).replace(minute=0, second=0, microsecond=0)
        hourly[hour] = kg  # last entry of an hour wins

    statistic_id = f"{DOMAIN}:weight_{entry.entry_id.lower()}"
    if hourly:
        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.ARITHMETIC,
            has_sum=False,
            name=f"Yazio weight ({entry.title})",
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_class="mass",
            unit_of_measurement=UnitOfMass.KILOGRAMS,
        )
        stats = [
            StatisticData(start=hour, mean=kg, min=kg, max=kg)
            for hour, kg in sorted(hourly.items())
        ]
        async_add_external_statistics(hass, metadata, stats)
    return {"statistic_id": statistic_id, "imported": len(hourly), "start_date": start.isoformat()}


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
