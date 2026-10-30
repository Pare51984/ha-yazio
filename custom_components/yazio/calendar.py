"""Optional calendar with the fasting windows of the Yazio plan."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .fasting import fasting_state, plan_label, windows_between


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([YazioFastingCalendar(entry.runtime_data, entry)])


class YazioFastingCalendar(CoordinatorEntity, CalendarEntity):
    """One event per fasting window, computed from the plan set in Yazio."""

    _attr_has_entity_name = True
    _attr_translation_key = "fasting_calendar"
    _attr_icon = "mdi:calendar-clock"
    _unsub_timer: CALLBACK_TYPE | None = None

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_fasting_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Yazio",
            manufacturer="Yazio (unofficial)",
            entry_type=DeviceEntryType.SERVICE,
        )

    def _plan(self) -> dict[str, Any] | None:
        plan = (self.coordinator.data or {}).get("fasting_plan_data")
        return plan if isinstance(plan, dict) and plan.get("periods") else None

    def _summary(self) -> str:
        german = (self.hass.config.language or "").startswith("de")
        label = plan_label(((self.coordinator.data or {}).get("fasting_details") or {}).get("plan"))
        word = "Fasten" if german else "Fasting"
        return f"{word} {label}" if label else word

    def _event(self, begin: datetime, end: datetime) -> CalendarEvent:
        return CalendarEvent(start=begin, end=end, summary=self._summary())

    @property
    def event(self) -> CalendarEvent | None:
        """Current fasting window, otherwise the next one."""
        plan = self._plan()
        if plan is None:
            return None
        now = dt_util.now()
        for begin, end in windows_between(plan, now - timedelta(days=2), now + timedelta(days=8)):
            if end > now:
                return self._event(begin, end)
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        plan = self._plan()
        if plan is None:
            return []
        return [self._event(b, e) for b, e in windows_between(plan, start_date, end_date)]

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
