"""Integration tests against a fake Yazio API (no real account needed)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.yazio.const import DOMAIN

BASE = "https://yzapi.yazio.com/v15"

SUMMARY = {
    "activity_energy": 43,
    "steps": 627,
    "water_intake": 250,
    "goals": {
        "energy.energy": 2215,
        "nutrient.protein": 105.9,
        "nutrient.fat": 70,
        "nutrient.carb": 264.8,
        "water": 2000,
        "activity.step": 10000,
        "bodyvalue.weight": 90,
    },
    "units": {"unit_energy": "kcal", "unit_mass": "kg"},
    "meals": {
        "breakfast": {"energy_goal": 600, "nutrients": {"energy.energy": 78.2, "nutrient.protein": 1.3, "nutrient.fat": 0.5, "nutrient.carb": 16.9}},
        "lunch": {"energy_goal": 800, "nutrients": {}},
        "dinner": {"energy_goal": 600, "nutrients": {}},
        "snack": {"energy_goal": 200, "nutrients": {}},
    },
    "user": {"start_weight": 115, "current_weight": 113, "goal": "lose_weight", "sex": "male"},
    "active_fasting_countdown_template_key": "16:8",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    yield


@pytest.fixture
def yazio_api(aioclient_mock):
    today = dt_util.now().date().isoformat()
    yesterday = (dt_util.now().date() - timedelta(days=1)).isoformat()
    aioclient_mock.post(f"{BASE}/oauth/token", json={"access_token": "tok", "expires_in": 172800})
    aioclient_mock.get(f"{BASE}/user/widgets/daily-summary", json=SUMMARY)
    aioclient_mock.get(
        f"{BASE}/user/streak",
        json={yesterday: {"streak_count": 6, "freeze_count": 1}, today: {"streak_count": 7, "freeze_count": 1}},
    )
    aioclient_mock.get(
        f"{BASE}/user/subscription/latest",
        json={"start": "2026-01-01 10:00:00", "end": "2027-01-01 10:00:00", "status": "active", "type": "yearly", "gateway": "google_play"},
    )
    aioclient_mock.get(
        f"{BASE}/user/bodyvalues/weight",
        json=[{"date": "2026-10-01 07:10:00", "value": 114.2}, {"date": "2026-10-20 07:05:00", "value": 113.0}],
    )
    return aioclient_mock


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={"email": "a@b.de", "password": "x"}, title="a@b.de")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_default_sensors(recorder_mock, hass: HomeAssistant, yazio_api) -> None:
    await _setup(hass)
    assert hass.states.get("sensor.yazio_calories_today").state == "78"
    assert hass.states.get("sensor.yazio_protein_today").state == "1.3"
    assert hass.states.get("sensor.yazio_carbs_today").state == "16.9"
    # on by default
    assert hass.states.get("sensor.yazio_streak").state == "7"
    assert hass.states.get("sensor.yazio_active_fasting_plan").state == "16:8"
    assert hass.states.get("sensor.yazio_water_today").state == "250"
    assert hass.states.get("sensor.yazio_water_goal").state == "2000"
    assert hass.states.get("sensor.yazio_protein_goal").state == "105.9"
    assert hass.states.get("sensor.yazio_current_weight").state == "113.0"
    # off by default
    assert hass.states.get("sensor.yazio_subscription_status") is None
    assert hass.states.get("sensor.yazio_steps_today") is None
    assert hass.states.get("sensor.yazio_breakfast_calories") is None


async def test_extra_sensors_when_enabled(recorder_mock, hass: HomeAssistant, yazio_api) -> None:
    registry = er.async_get(hass)
    entry = await _setup(hass)
    for key in ("streak", "fasting_plan", "subscription_status", "subscription_end", "water", "current_weight"):
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
        assert entity_id, key
        registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.yazio_streak").state == "7"
    assert hass.states.get("sensor.yazio_streak").attributes["streak_freezes"] == 1
    assert hass.states.get("sensor.yazio_active_fasting_plan").state == "16:8"
    sub = hass.states.get("sensor.yazio_subscription_status")
    assert sub.state == "active" and sub.attributes["subscription_type"] == "yearly"
    assert hass.states.get("sensor.yazio_subscription_ends").state.startswith("2027-01-01T10:00:00")
    assert hass.states.get("sensor.yazio_water_today").state == "250"
    assert hass.states.get("sensor.yazio_current_weight").state == "113.0"


async def test_extras_failing_do_not_break_main_sensor(recorder_mock, hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post(f"{BASE}/oauth/token", json={"access_token": "tok", "expires_in": 172800})
    aioclient_mock.get(f"{BASE}/user/widgets/daily-summary", json=SUMMARY)
    aioclient_mock.get(f"{BASE}/user/streak", status=500)
    aioclient_mock.get(f"{BASE}/user/subscription/latest", status=404)
    await _setup(hass)
    assert hass.states.get("sensor.yazio_calories_today").state == "78"


async def test_import_weight_history(recorder_mock, hass: HomeAssistant, yazio_api) -> None:
    entry = await _setup(hass)
    start = dt_util.now().date() - timedelta(days=60)
    result = await hass.services.async_call(
        DOMAIN, "import_weight_history", {"start_date": start.isoformat()}, blocking=True, return_response=True
    )
    assert result["imported"] == 2
    statistic_id = f"yazio:weight_{entry.entry_id.lower()}"
    assert result["statistic_id"] == statistic_id

    from homeassistant.components.recorder import get_instance

    await get_instance(hass).async_block_till_done()
    stats = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        dt_util.utcnow() - timedelta(days=90),
        None,
        {statistic_id},
        "hour",
        None,
        {"mean"},
    )
    means = [row["mean"] for row in stats[statistic_id]]
    assert means == [114.2, 113.0]


async def test_streak_without_count_is_zero(recorder_mock, hass: HomeAssistant, aioclient_mock) -> None:
    today = dt_util.now().date().isoformat()
    aioclient_mock.post(f"{BASE}/oauth/token", json={"access_token": "tok", "expires_in": 172800})
    aioclient_mock.get(f"{BASE}/user/widgets/daily-summary", json=SUMMARY)
    aioclient_mock.get(f"{BASE}/user/streak", json={today: {"daytimes": []}})
    aioclient_mock.get(f"{BASE}/user/subscription/latest", status=404)
    registry = er.async_get(hass)
    entry = await _setup(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_streak")
    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "0"
