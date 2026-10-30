"""Sensors for the values in Yazio's daily summary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass, UnitOfTime, UnitOfVolume
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN

KCAL = "kcal"
STEPS = "steps"


@dataclass(frozen=True, kw_only=True)
class YazioSensorDescription(SensorEntityDescription):
    """daily=True: value accumulates over the day and resets at midnight."""

    daily: bool = False
    value_fn: Callable[[Any], Any] | None = None
    attrs: tuple[str, ...] = ()
    attrs_dict: str | None = None  # data key holding a dict that becomes the attributes


def _local_timestamp(value: Any) -> datetime | None:
    """Yazio diary times are local ('2026-10-30 13:18:40')."""
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value.replace(" ", "T"))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return parsed


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value.replace(" ", "T"))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return parsed


def _daily(key: str, unit: str, icon: str, enabled: bool = True, **kw) -> YazioSensorDescription:
    return YazioSensorDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=unit,
        state_class=SensorStateClass.TOTAL,
        icon=icon,
        entity_registry_enabled_default=enabled,
        daily=True,
        **kw,
    )


def _goal(key: str, unit: str, icon: str, enabled: bool = False, **kw) -> YazioSensorDescription:
    return YazioSensorDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=unit,
        state_class=SensorStateClass.MEASUREMENT,
        icon=icon,
        entity_registry_enabled_default=enabled,
        **kw,
    )


SENSORS: tuple[YazioSensorDescription, ...] = (
    # Eaten today (enabled by default)
    _daily("energy", KCAL, "mdi:food-apple"),
    _daily("protein", UnitOfMass.GRAMS, "mdi:food-steak"),
    _daily("fat", UnitOfMass.GRAMS, "mdi:oil"),
    _daily("carb", UnitOfMass.GRAMS, "mdi:bread-slice"),
    # Per meal (off by default)
    _daily("breakfast_energy", KCAL, "mdi:coffee", enabled=False),
    _daily("lunch_energy", KCAL, "mdi:food", enabled=False),
    _daily("dinner_energy", KCAL, "mdi:food-variant", enabled=False),
    _daily("snack_energy", KCAL, "mdi:cookie", enabled=False),
    # Other daily values Yazio tracks (off by default; often come from other apps)
    _daily(
        "water",
        UnitOfVolume.MILLILITERS,
        "mdi:cup-water",
        enabled=True,
        device_class=SensorDeviceClass.VOLUME,
    ),
    _daily("steps", STEPS, "mdi:walk", enabled=False),
    _daily("activity_energy", KCAL, "mdi:fire", enabled=False),
    # Goals set in Yazio (calorie goal on, the rest off)
    _goal("goal_energy", KCAL, "mdi:target", enabled=True),
    _goal("goal_protein", UnitOfMass.GRAMS, "mdi:target", enabled=True),
    _goal("goal_fat", UnitOfMass.GRAMS, "mdi:target", enabled=True),
    _goal("goal_carb", UnitOfMass.GRAMS, "mdi:target", enabled=True),
    _goal("goal_water", UnitOfVolume.MILLILITERS, "mdi:target", device_class=SensorDeviceClass.VOLUME, enabled=True),
    _goal("goal_steps", STEPS, "mdi:target"),
    _goal("goal_weight", UnitOfMass.KILOGRAMS, "mdi:scale-bathroom", device_class=SensorDeviceClass.WEIGHT, enabled=True),
    _goal("current_weight", UnitOfMass.KILOGRAMS, "mdi:scale-bathroom", device_class=SensorDeviceClass.WEIGHT, enabled=True),
    # Streak, fasting, subscription (off by default)
    YazioSensorDescription(
        key="streak",
        translation_key="streak",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fire-circle",
        entity_registry_enabled_default=True,
        attrs=("streak_freezes", "streak_date"),
    ),
    YazioSensorDescription(
        key="fasting_plan",
        translation_key="fasting_plan",
        icon="mdi:timer-sand",
        entity_registry_enabled_default=True,
    ),
    YazioSensorDescription(
        key="subscription_status",
        translation_key="subscription_status",
        icon="mdi:crown",
        entity_registry_enabled_default=False,
        attrs=("subscription_type", "subscription_gateway", "subscription_start", "subscription_changed"),
    ),
    YazioSensorDescription(
        key="subscription_end",
        translation_key="subscription_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-end",
        entity_registry_enabled_default=False,
        value_fn=_timestamp,
    ),
    # Today's details (off by default; only fetched when switched on)
    YazioSensorDescription(
        key="entries_today",
        translation_key="entries_today",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:notebook-edit",
        entity_registry_enabled_default=False,
    ),
    YazioSensorDescription(
        key="last_entry",
        translation_key="last_entry",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check",
        entity_registry_enabled_default=False,
        value_fn=_local_timestamp,
    ),
    YazioSensorDescription(
        key="trainings_today",
        translation_key="trainings_today",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:dumbbell",
        entity_registry_enabled_default=False,
        attrs=("training_minutes", "training_names"),
    ),
    YazioSensorDescription(
        key="training_energy",
        translation_key="training_energy",
        native_unit_of_measurement=KCAL,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:fire",
        entity_registry_enabled_default=False,
        daily=True,
    ),
    YazioSensorDescription(
        key="feeling",
        translation_key="feeling",
        icon="mdi:emoticon-outline",
        entity_registry_enabled_default=False,
        attrs=("feeling_note",),
    ),
    YazioSensorDescription(
        key="fasting_status",
        translation_key="fasting_status",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.ENUM,
        options=["fasting", "eating", "active", "none"],
        entity_registry_enabled_default=False,
        attrs_dict="fasting_details",
    ),
)

# The first released sensor keeps its original unique_id, so existing
# entity_ids, history and dashboards stay as they are.
LEGACY_UNIQUE_SUFFIX = {"energy": "kalorien_heute"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        (YazioFastingSensor if desc.key == "fasting_status" else YazioSensor)(coordinator, entry, desc)
        for desc in SENSORS
    )


class YazioSensor(CoordinatorEntity, SensorEntity):
    """One value from the Yazio daily summary."""

    entity_description: YazioSensorDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, description: YazioSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        suffix = LEGACY_UNIQUE_SUFFIX.get(description.key, description.key)
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Yazio",
            manufacturer="Yazio (unofficial)",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        value = data.get(self.entity_description.key)
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(value)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        if self.entity_description.attrs_dict:
            details = data.get(self.entity_description.attrs_dict)
            return dict(details) if isinstance(details, dict) else None
        if not self.entity_description.attrs:
            return None
        return {key: data.get(key) for key in self.entity_description.attrs}

    @property
    def last_reset(self) -> datetime | None:
        if not self.entity_description.daily:
            return None
        day = (self.coordinator.data or {}).get("date")
        if not day:
            return None
        return dt_util.start_of_local_day(date.fromisoformat(day))


def fasting_windows(plan: dict[str, Any], now: datetime) -> list[tuple[datetime, datetime]]:
    """Real fasting windows around now. The plan repeats after its last day."""
    base = date.fromisoformat(plan["start_date"])
    periods = plan["periods"]
    cycle = max(begin[0] for begin, _ in periods) + 1
    tz = dt_util.get_default_time_zone()
    week = max(0, (now.date() - base).days // cycle)
    windows = []
    for rep in (week - 1, week, week + 1):
        if rep < 0:
            continue
        offset = rep * cycle
        for (b_day, b_time), (e_day, e_time) in periods:
            begin = datetime.combine(base + timedelta(days=offset + b_day), time.fromisoformat(b_time), tz)
            end = datetime.combine(base + timedelta(days=offset + e_day), time.fromisoformat(e_time), tz)
            if end > begin:
                windows.append((begin, end))
    return sorted(windows)


def fasting_state(plan: dict[str, Any], now: datetime) -> tuple[str, dict[str, Any], datetime | None]:
    """State, attributes and the time of the next change."""
    windows = fasting_windows(plan, now)
    current = next(((b, e) for b, e in windows if b <= now < e), None)
    upcoming = next(((b, e) for b, e in windows if b > now), None)
    base = date.fromisoformat(plan["start_date"])
    cycle = max(begin[0] for begin, _ in plan["periods"]) + 1
    day_index = (now.date() - base).days % cycle if now.date() >= base else None
    skipped = plan.get("skipped_meals", {}).get(day_index, []) if day_index is not None else []
    if current:
        state, change = "fasting", current[1]
        attrs = {"fasting_start": current[0].isoformat(), "fasting_end": current[1].isoformat()}
    else:
        state, change = "eating", upcoming[0] if upcoming else None
        attrs = {
            "fasting_start": upcoming[0].isoformat() if upcoming else None,
            "fasting_end": upcoming[1].isoformat() if upcoming else None,
        }
    attrs["next_change"] = change.isoformat() if change else None
    attrs["meals_to_skip_today"] = skipped
    return state, attrs, change


class YazioFastingSensor(YazioSensor):
    """Fasting or eating window, switches exactly at the plan's times."""

    _unsub_timer: CALLBACK_TYPE | None = None

    def _plan(self) -> dict[str, Any] | None:
        plan = (self.coordinator.data or {}).get("fasting_plan_data")
        return plan if isinstance(plan, dict) and plan.get("periods") else None

    @property
    def native_value(self):
        plan = self._plan()
        if plan is None:
            return (self.coordinator.data or {}).get("fasting_status")
        return fasting_state(plan, dt_util.now())[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs = dict(super().extra_state_attributes or {})
        plan = self._plan()
        if plan is not None:
            attrs.update(fasting_state(plan, dt_util.now())[1])
        return attrs

    def _schedule(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        plan = self._plan()
        if plan is None:
            return
        change = fasting_state(plan, dt_util.now())[2]
        if change:
            self._unsub_timer = async_track_point_in_time(self.hass, self._timer_fired, change + timedelta(seconds=1))

    @callback
    def _timer_fired(self, _now: datetime) -> None:
        self._unsub_timer = None
        self.async_write_ha_state()
        self._schedule()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._schedule()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._schedule()
        super()._handle_coordinator_update()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        await super().async_will_remove_from_hass()
