# Yazio (unofficial) for Home Assistant

Brings the calories you logged in [Yazio](https://www.yazio.com) today into Home Assistant as one sensor, so you can build a calorie balance, dashboards and notifications without typing anything twice.

> **Unofficial.** Yazio has no public API. This integration uses the same private endpoints as the Yazio app, as documented by community projects such as [yazio-mcp](https://github.com/fliptheweb/yazio-mcp). It can stop working whenever Yazio changes its backend. Not affiliated with or endorsed by YAZIO GmbH. Use it with your own account and at your own risk.

## What you get

One sensor, `sensor.yazio_calories_today` (German UI: *Kalorien heute*), in kcal. It updates every 15 minutes and resets at local midnight. Its long-term statistics hold real daily totals, so a statistics graph with *change* per day shows what you ate each day.

Attributes: `date`, `goal_kcal` (your Yazio goal), `protein_g`, `fat_g`, `carbs_g`, and kcal per meal (`breakfast_kcal`, `lunch_kcal`, `dinner_kcal`, `snacks_kcal`).

The integration only reads. It never writes to your Yazio diary.

## Installation

**HACS (custom repository)**

1. HACS → three-dot menu → *Custom repositories*
2. Add `https://github.com/Pare51984/ha-yazio` with category *Integration*
3. Download *Yazio (unofficial)* and restart Home Assistant

**Manual**

Copy `custom_components/yazio` into your Home Assistant `config/custom_components/` folder and restart.

## Setup

*Settings → Devices & services → Add integration → Yazio*, then enter your Yazio email and password.

**Signed up with Google or Apple?** Then your account has no Yazio password yet. Use *Forgot password* on the Yazio login with your account's email address to set one, then sign in here with it.

## Notes

- Your password is stored in Home Assistant's config entry, like with other cloud integrations.
- When the token expires the integration signs in again instead of refreshing it. Community reports say a token refresh at Yazio signs out your other sessions, including the app on your phone.

## Issues

Please open an issue with your Home Assistant version and the relevant log lines (Settings → System → Logs, filter for `yazio`). Remove your email address from logs before posting.

This repository is maintained with the help of an AI assistant (Claude). Replies on issues may be AI-generated and say so.

## License

MIT
