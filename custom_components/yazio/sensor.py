"""One sensor: calories eaten today according to Yazio."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN

MEAL_ATTRS = {
    "breakfast": "breakfast_kcal",
    "lunch": "lunch_kcal",
    "dinner": "dinner_kcal",
    "snack": "snacks_kcal",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([YazioCaloriesSensor(entry.runtime_data, entry)])


class YazioCaloriesSensor(CoordinatorEntity, SensorEntity):
    """Calories today; macros and goal as attributes.

    state_class TOTAL with a daily last_reset, so long-term statistics
    hold real daily sums ("change" per day works in statistics graphs).
    """

    _attr_has_entity_name = True
    _attr_translation_key = "calories_today"
    _attr_native_unit_of_measurement = "kcal"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:food-apple"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_kalorien_heute"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Yazio",
            manufacturer="Yazio (unofficial)",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("energy") if self.coordinator.data else None

    @property
    def last_reset(self) -> datetime | None:
        data = self.coordinator.data or {}
        if not data.get("date"):
            return None
        return dt_util.start_of_local_day(date.fromisoformat(data["date"]))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        attrs: dict[str, Any] = {
            "date": data.get("date"),
            "goal_kcal": data.get("goal"),
            "protein_g": data.get("protein"),
            "fat_g": data.get("fat"),
            "carbs_g": data.get("carb"),
        }
        for meal, key in MEAL_ATTRS.items():
            attrs[key] = (data.get("per_meal") or {}).get(meal)
        return attrs
