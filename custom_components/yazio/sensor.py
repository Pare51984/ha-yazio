"""Sensors for the values in Yazio's daily summary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN

KCAL = "kcal"
STEPS = "steps"


@dataclass(frozen=True, kw_only=True)
class YazioSensorDescription(SensorEntityDescription):
    """daily=True: value accumulates over the day and resets at midnight."""

    daily: bool = False


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
        enabled=False,
        device_class=SensorDeviceClass.VOLUME,
    ),
    _daily("steps", STEPS, "mdi:walk", enabled=False),
    _daily("activity_energy", KCAL, "mdi:fire", enabled=False),
    # Goals set in Yazio (calorie goal on, the rest off)
    _goal("goal_energy", KCAL, "mdi:target", enabled=True),
    _goal("goal_protein", UnitOfMass.GRAMS, "mdi:target"),
    _goal("goal_fat", UnitOfMass.GRAMS, "mdi:target"),
    _goal("goal_carb", UnitOfMass.GRAMS, "mdi:target"),
    _goal("goal_water", UnitOfVolume.MILLILITERS, "mdi:target", device_class=SensorDeviceClass.VOLUME),
    _goal("goal_steps", STEPS, "mdi:target"),
    _goal("goal_weight", UnitOfMass.KILOGRAMS, "mdi:scale-bathroom", device_class=SensorDeviceClass.WEIGHT),
    _goal("current_weight", UnitOfMass.KILOGRAMS, "mdi:scale-bathroom", device_class=SensorDeviceClass.WEIGHT),
)

# The first released sensor keeps its original unique_id, so existing
# entity_ids, history and dashboards stay as they are.
LEGACY_UNIQUE_SUFFIX = {"energy": "kalorien_heute"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(YazioSensor(coordinator, entry, desc) for desc in SENSORS)


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
        return data.get(self.entity_description.key)

    @property
    def last_reset(self) -> datetime | None:
        if not self.entity_description.daily:
            return None
        day = (self.coordinator.data or {}).get("date")
        if not day:
            return None
        return dt_util.start_of_local_day(date.fromisoformat(day))
