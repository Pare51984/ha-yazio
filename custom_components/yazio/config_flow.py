"""Einrichtungsdialog: E-Mail und Passwort des Yazio-Kontos."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import YazioApiError, YazioAuthError, YazioClient
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN

SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str})


class YazioConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _test(self, email: str, password: str) -> str | None:
        client = YazioClient(async_get_clientsession(self.hass), email, password)
        try:
            await client.async_validate()
        except YazioAuthError:
            return "invalid_auth"
        except YazioApiError:
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            return "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip().lower()
            await self.async_set_unique_id(email)
            self._abort_if_unique_id_configured()
            error = await self._test(email, user_input[CONF_PASSWORD])
            if error is None:
                return self.async_create_entry(
                    title=email, data={CONF_EMAIL: email, CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            errors["base"] = error
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            error = await self._test(entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )
