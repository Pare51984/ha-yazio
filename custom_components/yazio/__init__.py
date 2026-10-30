"""Unofficial Yazio integration: values from the Yazio diary as sensors."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant.components.recorder.models import StatisticData, StatisticMeanType, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform, UnitOfMass
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    YazioApiError,
    YazioAuthError,
    YazioClient,
    parse_consumed_items,
    parse_exercises,
    parse_fasting,
    parse_feeling,
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
SERVICE_ADD_WATER = "add_water"
SERVICE_ADD_WEIGHT = "add_weight"
SERVICE_ADD_FOOD = "add_food"
ATTR_AMOUNT = "amount"
ATTR_WEIGHT = "weight"
ATTR_WHEN = "when"
ATTR_NAME = "name"
ATTR_CALORIES = "calories"
ATTR_MEAL = "meal"
ATTR_ENTRY_ID = "config_entry_id"
ATTR_START_DATE = "start_date"


class YazioCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls Yazio. Daily summary every 15 min, streak and subscription hourly."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: YazioClient) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL
        )
        self.client = client
        self._extras: dict[str, Any] = {}
        self._extras_fetched: datetime | None = None
        # Last raw answers of optional endpoints, shown in the diagnostics download.
        self.raw_extras: dict[str, Any] = {}

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

        enabled = self._enabled_keys()
        now = dt_util.utcnow()
        if self._extras_fetched is None or now - self._extras_fetched >= EXTRA_INTERVAL:
            await self._async_fetch_hourly(today, enabled)
            self._extras_fetched = now
        await self._async_fetch_daily(today, enabled)
        data.update(self._extras)
        return data

    def _enabled_keys(self) -> set[str] | None:
        """Sensor keys that are enabled. None = unknown (first setup): fetch all."""
        if self.config_entry is None:
            return None
        prefix = f"{self.config_entry.entry_id}_"
        entries = er.async_entries_for_config_entry(er.async_get(self.hass), self.config_entry.entry_id)
        if not entries:
            return None
        return {
            e.unique_id[len(prefix):]
            for e in entries
            if e.unique_id.startswith(prefix) and e.disabled_by is None
        }

    async def _async_extra(self, key: str, path: str, params: dict[str, str] | None = None) -> Any:
        """Fetch one optional endpoint; keep the raw answer for diagnostics."""
        try:
            raw = await self.client.async_get_extra(path, params)
        except YazioApiError as err:
            self.raw_extras[key] = {"error": str(err)[:300]}
            raise
        self.raw_extras[key] = raw
        return raw

    async def _async_fetch_hourly(self, today: str, enabled: set[str] | None) -> None:
        """Streak and subscription change rarely. Failures never break the main sensors."""
        if enabled is None or "streak" in enabled:
            try:
                streak = parse_streak(await self._async_extra("streak", "/user/streak"), today)
                if streak:
                    self._extras.update(streak)
            except YazioApiError as err:
                _LOGGER.debug("Streak not available: %s", err)
        if enabled is None or enabled & {"subscription_status", "subscription_end"}:
            try:
                sub = parse_subscription(
                    await self._async_extra("subscription", "/user/subscription/latest")
                )
                if sub:
                    self._extras.update(sub)
            except YazioApiError as err:
                # Accounts that never had Pro may answer 404 here.
                if "HTTP 404" in str(err):
                    self._extras.update(parse_subscription(None))
                else:
                    _LOGGER.debug("Subscription not available: %s", err)

    async def _async_fetch_daily(self, today: str, enabled: set[str] | None) -> None:
        """Today's details, only for sensors that are switched on."""

        def wanted(*keys: str) -> bool:
            return enabled is None or bool(enabled & set(keys))

        jobs = (
            (("entries_today", "last_entry"), "consumed_items", "/user/consumed-items", {"date": today}, parse_consumed_items),
            (("trainings_today", "training_energy"), "exercises", "/user/exercises", {"date": today}, parse_exercises),
            (("feeling",), "feeling", "/user/feeling", {"date": today}, parse_feeling),
            (("fasting_status",), "fasting", "/user/fasting-countdowns", None, parse_fasting),
        )
        for keys, raw_key, path, params, parser in jobs:
            if not wanted(*keys):
                continue
            try:
                self._extras.update(parser(await self._async_extra(raw_key, path, params)))
            except YazioApiError as err:
                _LOGGER.debug("%s not available: %s", raw_key, err)


def _pick_entry(hass: HomeAssistant, call: ServiceCall) -> ConfigEntry:
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED
    ]
    wanted = call.data.get(ATTR_ENTRY_ID)
    if wanted:
        entries = [e for e in entries if e.entry_id == wanted]
    if len(entries) != 1:
        raise HomeAssistantError("Select exactly one loaded Yazio account (config_entry_id).")
    return entries[0]


def _yazio_time(when: datetime | None) -> str:
    """Yazio expects local time as 'YYYY-MM-DD HH:MM:SS'."""
    local = dt_util.as_local(when) if when else dt_util.now()
    return local.strftime("%Y-%m-%d %H:%M:%S")


async def _async_write(hass: HomeAssistant, entry: ConfigEntry, path: str, payload: Any) -> None:
    coordinator: YazioCoordinator = entry.runtime_data
    try:
        await coordinator.client.async_post(path, payload)
    except YazioApiError as err:
        raise HomeAssistantError(f"Yazio did not accept the entry: {err}") from err
    await coordinator.async_request_refresh()


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the actions once for the domain."""

    async def add_water(call: ServiceCall) -> None:
        entry = _pick_entry(hass, call)
        coordinator: YazioCoordinator = entry.runtime_data
        day = dt_util.now().date().isoformat()
        try:
            current = await coordinator.client.async_get_extra("/user/water-intake", {"date": day})
        except YazioApiError as err:
            raise HomeAssistantError(f"Could not read today's water from Yazio: {err}") from err
        total = float((current or {}).get("water_intake") or 0) + float(call.data[ATTR_AMOUNT])
        # Yazio stores the day's cumulative total, so the new amount is added to it.
        await _async_write(
            hass, entry, "/user/water-intake", [{"date": _yazio_time(None), "water_intake": round(total)}]
        )

    async def add_weight(call: ServiceCall) -> None:
        entry = _pick_entry(hass, call)
        await _async_write(
            hass,
            entry,
            "/user/bodyvalues",
            {"weight": [{"id": str(uuid.uuid4()), "date": _yazio_time(call.data.get(ATTR_WHEN)), "value": float(call.data[ATTR_WEIGHT])}]},
        )

    async def add_food(call: ServiceCall) -> None:
        entry = _pick_entry(hass, call)
        nutrients = {"energy.energy": float(call.data[ATTR_CALORIES])}
        for attr, key in (("protein", "nutrient.protein"), ("fat", "nutrient.fat"), ("carbs", "nutrient.carb")):
            if call.data.get(attr) is not None:
                nutrients[key] = float(call.data[attr])
        await _async_write(
            hass,
            entry,
            "/user/consumed-items",
            {
                "products": [],
                "recipe_portions": [],
                "simple_products": [
                    {
                        "id": str(uuid.uuid4()),
                        "date": _yazio_time(None),
                        "daytime": call.data[ATTR_MEAL],
                        "name": call.data[ATTR_NAME],
                        "nutrients": nutrients,
                    }
                ],
            },
        )

    base = {vol.Optional(ATTR_ENTRY_ID): cv.string}
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_WATER, add_water,
        schema=vol.Schema({**base, vol.Required(ATTR_AMOUNT): vol.All(vol.Coerce(float), vol.Range(min=1, max=5000))}),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_WEIGHT, add_weight,
        schema=vol.Schema({**base, vol.Required(ATTR_WEIGHT): vol.All(vol.Coerce(float), vol.Range(min=20, max=400)), vol.Optional(ATTR_WHEN): cv.datetime}),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_FOOD, add_food,
        schema=vol.Schema({
            **base,
            vol.Required(ATTR_NAME): vol.All(cv.string, vol.Length(min=1, max=100)),
            vol.Required(ATTR_CALORIES): vol.All(vol.Coerce(float), vol.Range(min=0, max=10000)),
            vol.Optional("protein"): vol.All(vol.Coerce(float), vol.Range(min=0, max=1000)),
            vol.Optional("fat"): vol.All(vol.Coerce(float), vol.Range(min=0, max=1000)),
            vol.Optional("carbs"): vol.All(vol.Coerce(float), vol.Range(min=0, max=1000)),
            vol.Required(ATTR_MEAL): vol.In(["breakfast", "lunch", "dinner", "snack"]),
        }),
    )

    async def import_weight(call: ServiceCall) -> ServiceResponse:
        entry = _pick_entry(hass, call)
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
    coordinator = YazioCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
