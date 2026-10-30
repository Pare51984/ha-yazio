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

    async def _fetch_summary(self, profile: dict[str, Any], day: str) -> dict[str, Any]:
        async with self._session.get(
            f"{profile['base_url']}/user/widgets/daily-summary",
            params={"date": day},
            headers=self._headers(profile),
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status == 401:
                raise YazioAuthError("Token abgelaufen")
            if resp.status != 200:
                raise YazioApiError(f"HTTP {resp.status}: {await resp.text()}")
            return await resp.json(content_type=None)

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


def parse_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Tageszusammenfassung in schlichte Zahlen umwandeln."""
    meals = data.get("meals") or {}
    totals = {"energy": 0.0, "protein": 0.0, "fat": 0.0, "carb": 0.0}
    per_meal: dict[str, float] = {}
    for meal in MEALS:
        nutrients = (meals.get(meal) or {}).get("nutrients") or {}
        kcal = float(nutrients.get("energy.energy") or 0)
        per_meal[meal] = round(kcal)
        totals["energy"] += kcal
        totals["protein"] += float(nutrients.get("nutrient.protein") or 0)
        totals["fat"] += float(nutrients.get("nutrient.fat") or 0)
        totals["carb"] += float(nutrients.get("nutrient.carb") or 0)
    goals = data.get("goals") or {}
    return {
        "energy": round(totals["energy"]),
        "protein": round(totals["protein"], 1),
        "fat": round(totals["fat"], 1),
        "carb": round(totals["carb"], 1),
        "per_meal": per_meal,
        "goal": round(float(goals["energy.energy"])) if goals.get("energy.energy") else None,
        "activity_energy": data.get("activity_energy"),
        "unit": (data.get("units") or {}).get("unit_energy", "kcal"),
    }
