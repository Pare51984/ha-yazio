"""Kleiner Client für die inoffizielle Yazio-API (nur Lesen)."""

from __future__ import annotations

import time
from typing import Any

import aiohttp

from .const import API_PROFILES, MEALS


class YazioAuthError(Exception):
    """Login fehlgeschlagen (falsche Zugangsdaten)."""


class YazioApiError(Exception):
    """Die API hat unerwartet geantwortet."""


class YazioClient:
    """Holt die Tageszusammenfassung aus Yazio.

    Bewusst ohne Refresh-Token: Ein Refresh bei Yazio macht laut
    Community-Berichten alle anderen Sitzungen ungültig, also auch die
    in der App auf dem Handy. Läuft das Token ab, wird neu eingeloggt.
    """

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._profile: dict[str, Any] | None = None
        self._token: str | None = None
        self._expires_at = 0.0

    def _headers(self, profile: dict[str, Any], auth: bool = True) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if profile.get("user_agent"):
            headers["User-Agent"] = profile["user_agent"]
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _login_with(self, profile: dict[str, Any]) -> None:
        payload = {
            "client_id": profile["client_id"],
            "client_secret": profile["client_secret"],
            "grant_type": "password",
            "username": self._email,
            "password": self._password,
        }
        async with self._session.post(
            f"{profile['base_url']}/oauth/token",
            json=payload,
            headers=self._headers(profile, auth=False),
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status in (400, 401):
                raise YazioAuthError(await resp.text())
            if resp.status != 200:
                raise YazioApiError(f"Login HTTP {resp.status}: {await resp.text()}")
            data = await resp.json(content_type=None)
        self._token = data["access_token"]
        # Etwas Puffer, damit nicht mitten im Abruf das Token abläuft.
        self._expires_at = time.time() + float(data.get("expires_in", 3600)) - 300
        self._profile = profile

    async def _get_json(
        self, profile: dict[str, Any], path: str, params: dict[str, str] | None = None
    ) -> Any:
        async with self._session.get(
            f"{profile['base_url']}{path}",
            params=params,
            headers=self._headers(profile),
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status == 401:
                raise YazioAuthError("Token abgelaufen")
            if resp.status != 200:
                raise YazioApiError(f"{path} HTTP {resp.status}: {await resp.text()}")
            return await resp.json(content_type=None)

    async def _fetch_summary(self, profile: dict[str, Any], day: str) -> dict[str, Any]:
        return await self._get_json(profile, "/user/widgets/daily-summary", {"date": day})

    async def async_get_extra(self, path: str, params: dict[str, str] | None = None) -> Any:
        """Zusatzdaten mit der bestehenden Sitzung holen (nach async_get_summary).

        Wirft YazioApiError, wenn keine Sitzung besteht oder der Abruf scheitert.
        Ein Login wird hier bewusst nicht ausgelöst; das macht der nächste
        reguläre Abruf der Tageszusammenfassung.
        """
        if not (self._profile and self._token and time.time() < self._expires_at):
            raise YazioApiError("Keine aktive Sitzung")
        try:
            return await self._get_json(self._profile, path, params)
        except YazioAuthError as err:
            raise YazioApiError(str(err)) from err
        except aiohttp.ClientError as err:
            raise YazioApiError(str(err)) from err

    async def async_validate(self) -> None:
        """Für den Einrichtungsdialog: Login und ein Testabruf."""
        await self.async_get_summary(time.strftime("%Y-%m-%d"))

    async def async_get_summary(self, day: str) -> dict[str, Any]:
        """Tageszusammenfassung holen, bei Bedarf (neu) einloggen."""
        # Bekanntes, funktionierendes Profil zuerst.
        if self._profile and self._token and time.time() < self._expires_at:
            try:
                return await self._fetch_summary(self._profile, day)
            except YazioAuthError:
                self._token = None
            except YazioApiError:
                # z. B. version_blocked: alle Profile neu durchprobieren
                self._profile = None
                self._token = None

        last_error: Exception | None = None
        profiles = [self._profile] if self._profile else []
        profiles += [p for p in API_PROFILES if p is not self._profile]
        for profile in profiles:
            try:
                await self._login_with(profile)
                return await self._fetch_summary(profile, day)
            except YazioAuthError as err:
                last_error = err
            except (YazioApiError, aiohttp.ClientError, KeyError) as err:
                last_error = err
            self._profile = None
            self._token = None
        if isinstance(last_error, YazioAuthError):
            raise last_error
        raise YazioApiError(str(last_error))


def _num(value: Any, digits: int = 0) -> float | int | None:
    """Zahl runden, None/Unsinn bleibt None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number) if digits == 0 else round(number, digits)


def parse_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Tageszusammenfassung in flache Werte umwandeln (ein Schlüssel pro Sensor)."""
    meals = data.get("meals") or {}
    totals = {"energy": 0.0, "protein": 0.0, "fat": 0.0, "carb": 0.0}
    out: dict[str, Any] = {}
    for meal in MEALS:
        nutrients = (meals.get(meal) or {}).get("nutrients") or {}
        kcal = float(nutrients.get("energy.energy") or 0)
        out[f"{meal}_energy"] = round(kcal)
        totals["energy"] += kcal
        totals["protein"] += float(nutrients.get("nutrient.protein") or 0)
        totals["fat"] += float(nutrients.get("nutrient.fat") or 0)
        totals["carb"] += float(nutrients.get("nutrient.carb") or 0)
    goals = data.get("goals") or {}
    user = data.get("user") or {}
    out.update(
        {
            "energy": round(totals["energy"]),
            "protein": round(totals["protein"], 1),
            "fat": round(totals["fat"], 1),
            "carb": round(totals["carb"], 1),
            "water": _num(data.get("water_intake")),
            "steps": _num(data.get("steps")),
            "activity_energy": _num(data.get("activity_energy")),
            "goal_energy": _num(goals.get("energy.energy")),
            "goal_protein": _num(goals.get("nutrient.protein"), 1),
            "goal_fat": _num(goals.get("nutrient.fat"), 1),
            "goal_carb": _num(goals.get("nutrient.carb"), 1),
            "goal_water": _num(goals.get("water")),
            "goal_steps": _num(goals.get("activity.step")),
            "goal_weight": _num(goals.get("bodyvalue.weight"), 1),
            "current_weight": _num(user.get("current_weight"), 1),
            "fasting_plan": data.get("active_fasting_countdown_template_key") or "inactive",
        }
    )
    return out


def parse_streak(data: Any, today: str) -> dict[str, Any] | None:
    """Streak-Kalender {"YYYY-MM-DD": {streak_count, freeze_count, ...}} auswerten.

    Nimmt den Eintrag von heute, sonst den jüngsten Tag davor.
    """
    if not isinstance(data, dict):
        return None
    days = sorted(d for d in data if isinstance(d, str) and d[:10] <= today)
    if not days:
        return {"streak": 0, "streak_freezes": None, "streak_date": None}
    entry = data[days[-1]] if isinstance(data[days[-1]], dict) else {}
    # Yazio liefert für Tage ohne laufenden Streak einen Eintrag ohne Zahl.
    return {
        "streak": _num(entry.get("streak_count")) or 0,
        "streak_freezes": _num(entry.get("freeze_count")) or 0,
        "streak_date": days[-1][:10],
    }


def parse_subscription(data: Any) -> dict[str, Any] | None:
    """Neuestes Abo auswerten. Ohne Abo liefert Yazio leer/404."""
    if not isinstance(data, dict) or not data:
        return {"subscription_status": "none", "subscription_end": None}
    return {
        "subscription_status": data.get("status") or "unknown",
        "subscription_end": data.get("end"),
        "subscription_start": data.get("start"),
        "subscription_type": data.get("type"),
        "subscription_gateway": data.get("gateway"),
        "subscription_changed": data.get("last_status_change_at"),
    }


def parse_weight_history(data: Any) -> list[tuple[str, float]]:
    """Gewichtseinträge [{date, value}, ...] als (Zeitstempel, kg) sortiert."""
    if isinstance(data, dict):
        data = data.get("items") or data.get("entries") or list(data.values())
    out: list[tuple[str, float]] = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        value = _num(item.get("value"), 2)
        when = item.get("date")
        if value is not None and isinstance(when, str):
            out.append((when, float(value)))
    return sorted(out)
