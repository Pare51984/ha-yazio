# Changelog

## 0.8.0
- New option *Update interval* (5, 15 or 30 minutes, default 15).
- Daily values update right after midnight instead of up to one interval later.
- The integration is now titled `Yazio (ab…@example.com)` instead of the full email address; existing installations are renamed automatically. Entities and history are not affected.
- Translated states for subscription status, feeling (`none`) and fasting plan (`inactive`).

## 0.7.0
- New option *Fasting calendar* under Configure: a calendar with one event per fasting window of your Yazio plan. Off by default; switching it off removes the calendar again.
- README: example automation to copy the fasting windows into another calendar.

## 0.6.1
- Fasting status now shows `fasting` or `eating` based on your Yazio plan and switches exactly at the plan's times. Attributes: plan, fasting start and end, next change, meals to skip today.

## 0.6.0
- New sensors (all off after setup, only requested while switched on): entries today, last entry, trainings today, training calories today, feeling today, fasting status.
- New experimental actions that write to your Yazio diary: `yazio.add_water`, `yazio.add_weight`, `yazio.add_food`.
- Diagnostics download with the raw answers of the optional endpoints (login data removed, food names reduced to field names).
- Optional data that fails to load never affects the main sensors.

## 0.5.3
- Each release now includes `yazio.zip`, which HACS downloads. This lets the release page show download counts. No functional changes.

## 0.5.2
- Releases are now created only after the HACS and hassfest checks passed. No functional changes.

## 0.5.1
- Own icon and logo for the integration (shown in Home Assistant 2026.3 and newer).

## 0.5.0
- More sensors are on after setup: protein/fat/carbs goal, water today, water goal, goal weight, current weight, streak, active fasting plan.
- Still off after setup: calories per meal, steps, activity calories, step goal, subscription status and end.
- Existing installations keep their own on/off choices; only new installs get the new defaults.

## 0.4.2
- Streak sensor shows `0` instead of `unknown` when no streak is running.

## 0.4.1
- Fixed the action description so Home Assistant's validation passes. No functional changes.

## 0.4.0
- New optional sensors: streak, active fasting plan, subscription status, subscription end date.
- New action `yazio.import_weight_history` copies your Yazio weight history into long-term statistics.
- Streak and subscription are fetched hourly; if they fail, the main sensors keep working.
- Requires Home Assistant 2025.6 or newer.

## 0.3.0
- All values from Yazio's daily summary as sensors: protein, fat, carbs, calorie goal (enabled); calories per meal, water, steps, activity calories, goals, goal weight, current weight (disabled by default).
- The calories sensor keeps its entity ID and history.

## 0.2.0
- First public release: calories eaten today, with real daily totals in long-term statistics.
