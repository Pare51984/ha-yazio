# Yazio (unofficial) for Home Assistant

Brings what you log in [Yazio](https://www.yazio.com) into Home Assistant as sensors: calories and macros eaten today, your goals, water, streak, fasting plan and subscription. Build a calorie balance, dashboards and notifications without typing anything twice.

> **Unofficial.** Yazio has no public API. This integration uses the same private endpoints as the Yazio app, as documented by community projects such as [yazio-mcp](https://github.com/fliptheweb/yazio-mcp). It can stop working whenever Yazio changes its backend. Not affiliated with or endorsed by YAZIO GmbH. Use it with your own account and at your own risk.

## What you get

Sensors from your Yazio account, updated every 15 minutes (streak and subscription hourly). Daily values reset at local midnight and their long-term statistics hold real daily totals, so a statistics graph with *change* per day shows each day.

All sensors below are included. The ones marked *off* are created but switched off after setup, so your entity list stays tidy; switch on what you need.

| Sensor | Unit | After setup |
|---|---|---|
| Calories today | kcal | **on** |
| Protein today | g | **on** |
| Fat today | g | **on** |
| Carbs today | g | **on** |
| Calorie goal | kcal | **on** |
| Breakfast / lunch / dinner / snack calories | kcal | off |
| Water today | mL | **on** |
| Steps today | steps | off |
| Activity calories today | kcal | off |
| Protein / fat / carbs goal | g | **on** |
| Water goal | mL | **on** |
| Step goal | steps | off |
| Goal weight / current weight | kg | **on** |
| Streak (days in a row you logged, `0` if none; streak freezes as attribute) | d | **on** |
| Active fasting plan (Yazio's internal plan name, e.g. `16_8_early_fasting_v2`, or `inactive`) | – | **on** |
| Subscription status (`will_renew` = renews automatically, `will_not_renew` = cancelled, `none` if you never had Pro; attributes: plan type, store, start, last change, Yazio's original value) | – | off |
| Subscription ends | date | off |
| Entries today (number of diary entries) | – | off |
| Last entry (time of the most recent diary entry) | time | off |
| Trainings today (attributes: minutes, names) | – | off |
| Training calories today | kcal | off |
| Feeling today (mood tags; note as attribute) | – | off |
| Fasting status (`fasting` / `eating` / `none`; switches exactly at your plan's times; attributes: plan, fasting start and end, next change, meals to skip today) | – | off |

Switch sensors on under *Settings → Devices & services → Yazio → entities*. Off by default: calories per meal (four extra entities most people don't need), steps and activity calories (usually already come from your phone or watch, so you'd get them twice), the subscription sensors (account info rather than health data) and the detail sensors at the end of the table. Those detail sensors are only requested from Yazio while they are switched on.

The sensors only read. Something is written to your Yazio diary only when you call one of the write actions below yourself.

### Import your weight history

Weighed yourself in Yazio for years? The action **Yazio: Import weight history** (`yazio.import_weight_history`) copies those entries into Home Assistant's long-term statistics. Optional field: `start_date` (default: 5 years back). Afterwards add a *Statistics graph* card and pick the statistic **Yazio weight**. Running it again is safe.

### Options

Under *Settings → Devices & services → Yazio → Configure*:

| Option | Default | What it does |
|---|---|---|
| Fasting calendar | off | Calendar with your fasting windows (see below) |
| Update interval | 15 min | How often Yazio is polled: 5, 15 or 30 minutes. Right after midnight it always updates, so daily values start at 0 on time. |

### Fasting calendar (optional)

Switch on **Fasting calendar** under *Configure*. It adds a calendar with one event per fasting window of your Yazio plan, shown in Home Assistant's calendar view and usable as an automation trigger. Switching it off removes the calendar again. Off by default.

Want the fasting windows in another calendar (e.g. Google)? Copy them with an automation. Example, runs daily and adds tomorrow's windows (replace both calendar entities with yours):

```yaml
alias: Copy Yazio fasting windows
triggers:
  - trigger: time
    at: "00:05:00"
actions:
  - action: calendar.get_events
    target:
      entity_id: calendar.yazio_fasting
    data:
      start_date_time: "{{ (today_at() + timedelta(days=1)).isoformat() }}"
      duration:
        hours: 24
    response_variable: yazio
  - repeat:
      for_each: "{{ yazio['calendar.yazio_fasting'].events }}"
      sequence:
        - action: calendar.create_event
          target:
            entity_id: calendar.your_calendar
          data:
            summary: "{{ repeat.item.summary }}"
            start_date_time: "{{ repeat.item.start }}"
            end_date_time: "{{ repeat.item.end }}"
```

Note: Home Assistant can create events in most calendars but cannot delete them, so copied events stay when you stop the automation.

### Write actions (experimental)

These actions write to your Yazio diary, for example from an NFC tag, a button or an automation:

| Action | Fields |
|---|---|
| `yazio.add_water` | `amount` in mL, added to today's water |
| `yazio.add_weight` | `weight` in kg, optional `when` |
| `yazio.add_food` | `name`, `calories`, optional `protein` / `fat` / `carbs` in g, `meal` (breakfast, lunch, dinner, snack) |

Yazio's API is not documented, so these are experimental. Check the result in the app the first times. `add_food` creates a simple entry with your own name and values, not a product from Yazio's database.

### Fasting, feeling and trainings

The fasting status follows the plan you set in Yazio and repeats it every week. Example automation idea: notify 15 minutes before `next_change` while the state is `eating`.

The format of these answers is not documented. The sensors read them defensively; if a value looks wrong, download the diagnostics (*Settings → Devices & services → Yazio → ⋮ → Download diagnostics*) and attach it to an issue. Login data is removed from that file and food names are reduced to field names.

## Requirements

- Home Assistant **2025.6** or newer
- The **email address and password** of your Yazio account. Signing in with Google or Apple is not supported by the integration.
- **Yazio Pro is most likely not required.** The integration reads the same diary that the free app shows. It has only been tested with a Pro account so far, so if you use the free version, a short note in an issue (works / what's missing) helps a lot. Without Pro, the subscription status should show `none`.

**Your Yazio account is linked to Google or Apple?** Then it has no password yet, and you have to create one first:

1. Open the Yazio login (in the app or on yazio.com) and choose **Forgot password**.
2. Enter the email address of your Google/Apple account and request the reset email.
3. Set a new password via the link in that email.
4. Use this email address and the new password in Home Assistant.

It is the same account, so your diary and data stay as they are.

> **Deutsch:** Du brauchst E-Mail-Adresse und Passwort deines Yazio-Kontos. Ist dein Konto mit Google oder Apple verknüpft, hat es noch kein Passwort. Dann im Yazio-Login auf **„Passwort vergessen“** tippen, die E-Mail-Adresse deines Google-/Apple-Kontos eingeben, über den Link in der Mail ein neues Passwort festlegen und damit die Integration einrichten. Deine Daten bleiben erhalten. Yazio Pro ist voraussichtlich nicht nötig (getestet bisher nur mit Pro, Rückmeldungen zur kostenlosen Version gern als Issue).

## Installation

**HACS (custom repository)**

1. HACS → three-dot menu → *Custom repositories*
2. Add `https://github.com/Pare51984/ha-yazio` with category *Integration*
3. Download *Yazio (unofficial)* and restart Home Assistant

**Manual**

Copy `custom_components/yazio` into your Home Assistant `config/custom_components/` folder and restart.

**Updating**

HACS checks custom repositories for new versions only about every 48 hours. To see a new release right away: HACS → *Yazio (unofficial)* → three-dot menu → *Update information*, then install the update and restart Home Assistant. What changed is listed in the [changelog](CHANGELOG.md) and on the [releases page](https://github.com/Pare51984/ha-yazio/releases).

## Setup

*Settings → Devices & services → Add integration → Yazio*, then enter your Yazio email and password (see [Requirements](#requirements) if your account uses Google or Apple sign-in).

## Notes

- Your password is stored in Home Assistant's config entry, like with other cloud integrations.
- The integration is listed as `Yazio (ab…@example.com)`, so the full email address doesn't show up in screenshots.
- When the token expires the integration signs in again instead of refreshing it. Community reports say a token refresh at Yazio signs out your other sessions, including the app on your phone.

## Issues

Please open an issue with your Home Assistant version and the relevant log lines (Settings → System → Logs, filter for `yazio`). Remove your email address from logs before posting.

This repository is maintained with the help of an AI assistant (Claude); code changes are tested before each release.

## License

MIT
