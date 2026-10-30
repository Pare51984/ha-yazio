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
    aioclient_mock.get(
        f"{BASE}/user/consumed-items",
        json={
            "products": [{"id": "p1", "date": f"{today} 08:10:00", "daytime": "breakfast", "product_id": "x", "amount": 30}],
            "recipe_portions": [],
            "simple_products": [{"id": "s1", "date": f"{today} 12:45:00", "daytime": "lunch", "name": "Shake", "nutrients": {"energy.energy": 400}}],
        },
    )
    aioclient_mock.get(
        f"{BASE}/user/exercises",
        json={"training": [{"name": "cycling", "energy": 321.0, "duration": 45}], "custom_training": [{"name": "Gym", "energy": 171.0, "duration": 66}], "activity": {"steps": 8132}},
    )
    aioclient_mock.get(f"{BASE}/user/feeling", json={"note": "good day", "tags": ["happy", "energetic"]})
    aioclient_mock.get(f"{BASE}/user/fasting-countdowns", json=[{"template_key": "16_8_early_fasting_v2", "start": f"{today} 20:00:00"}])
    aioclient_mock.get(f"{BASE}/user/water-intake", json={"water_intake": 250.0, "gateway": None, "source": None})
    aioclient_mock.post(f"{BASE}/user/water-intake", status=204)
    aioclient_mock.post(f"{BASE}/user/bodyvalues", status=204)
    aioclient_mock.post(f"{BASE}/user/consumed-items", status=204)
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


NEW_KEYS = ("entries_today", "last_entry", "trainings_today", "training_energy", "feeling", "fasting_status")


async def _enable(hass: HomeAssistant, entry, keys) -> dict[str, str]:
    registry = er.async_get(hass)
    ids = {}
    for key in keys:
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
        assert entity_id, key
        registry.async_update_entity(entity_id, disabled_by=None)
        ids[key] = entity_id
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    return ids


async def test_today_details_sensors(recorder_mock, hass: HomeAssistant, yazio_api) -> None:
    entry = await _setup(hass)
    ids = await _enable(hass, entry, NEW_KEYS)
    assert hass.states.get(ids["entries_today"]).state == "2"
    assert hass.states.get(ids["last_entry"]).state.startswith(dt_util.now().date().isoformat())
    trainings = hass.states.get(ids["trainings_today"])
    assert trainings.state == "2" and trainings.attributes["training_minutes"] == 111
    assert hass.states.get(ids["training_energy"]).state == "492"
    feeling = hass.states.get(ids["feeling"])
    assert feeling.state == "happy, energetic" and feeling.attributes["feeling_note"] == "good day"
    fasting = hass.states.get(ids["fasting_status"])
    assert fasting.state == "active" and fasting.attributes["template_key"] == "16_8_early_fasting_v2"


async def test_disabled_details_are_not_fetched(recorder_mock, hass: HomeAssistant, yazio_api) -> None:
    entry = await _setup(hass)
    # After the first setup the registry knows which sensors are off.
    yazio_api.mock_calls.clear()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    called = {str(url) for _, url, _, _ in yazio_api.mock_calls}
    assert not any("consumed-items" in u or "exercises" in u or "feeling" in u or "fasting" in u for u in called), called


async def test_add_water_adds_to_total(recorder_mock, hass: HomeAssistant, yazio_api) -> None:
    await _setup(hass)
    yazio_api.mock_calls.clear()
    await hass.services.async_call(DOMAIN, "add_water", {"amount": 300}, blocking=True)
    posts = [(url, data) for method, url, data, _ in yazio_api.mock_calls if method == "POST" and "water-intake" in str(url)]
    assert len(posts) == 1
    body = posts[0][1]
    assert body[0]["water_intake"] == 550 and len(body[0]["date"]) == 19


async def test_add_weight_and_food(recorder_mock, hass: HomeAssistant, yazio_api) -> None:
    await _setup(hass)
    yazio_api.mock_calls.clear()
    await hass.services.async_call(DOMAIN, "add_weight", {"weight": 112.4}, blocking=True)
    await hass.services.async_call(
        DOMAIN, "add_food", {"name": "Shake", "calories": 400, "protein": 40, "meal": "lunch"}, blocking=True
    )
    posts = {str(url).rsplit("/", 1)[-1]: data for method, url, data, _ in yazio_api.mock_calls if method == "POST"}
    assert posts["bodyvalues"]["weight"][0]["value"] == 112.4
    food = posts["consumed-items"]["simple_products"][0]
    assert food["name"] == "Shake" and food["daytime"] == "lunch"
    assert food["nutrients"] == {"energy.energy": 400.0, "nutrient.protein": 40.0}


async def test_diagnostics_hide_login_and_food(recorder_mock, hass: HomeAssistant, yazio_api) -> None:
    from custom_components.yazio.diagnostics import async_get_config_entry_diagnostics

    entry = await _setup(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = str(diag)
    assert "a@b.de" not in text and "'x'" not in text
    assert "Shake" not in text  # food names are reduced to field names
    assert diag["raw_extras"]["fasting"][0]["template_key"] == "16_8_early_fasting_v2"
