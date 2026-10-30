# Changelog

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
