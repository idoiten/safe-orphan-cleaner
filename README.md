# Safe Orphan Cleaner

Finds Home Assistant entity registry entries that HA itself has already
flagged as orphaned (`orphaned_timestamp` set — the same signal behind the
"This entity is currently unavailable and is an orphan..." warning), and
crucially checks whether that `entity_id` has since been **reused by a
currently live entity** before ever suggesting removal by name.

Existing community tools either can't detect this collision (and could
delete a live entity by accident) or have no discovery step at all. This
integration does both, safely.

## Why this exists

Built after discovering, the hard way, that:
- An old deleted `automation.hackbevattning` shared its entity_id with the
  live, actively-used irrigation automation of the same name.
- An old deleted `binary_sensor.markisstyrning_sol` shared its entity_id
  with the live awning sun sensor.

Removing either "by name" would have deleted the live entity instead of
the intended orphan. This integration makes that class of mistake
impossible by design: entries with a live-entity collision are reported
separately and can **only** be removed by internal `registry_id`, never
by `entity_id`.

## Installation (HACS custom repository)

1. HACS → the three dots (top right) → **Custom repositories**
2. Add this repo's URL, category **Integration**
3. Install **Safe Orphan Cleaner**
4. Add to `configuration.yaml`:
   ```yaml
   safe_orphan_cleaner:
   ```
5. Restart Home Assistant

## Usage

**1. Scan** (Developer Tools → Actions → `safe_orphan_cleaner.scan`)

Returns something like:
```yaml
safe_count: 41
dangerous_count: 2
safe:
  - entity_id: sensor.old_thing
    registry_id: abc123...
    platform: some_platform
    orphaned_since: 1735689600.0
dangerous:
  - entity_id: automation.hackbevattning
    registry_id: 5040ffe9...
    reason: "entity_id currently reused by a LIVE entity — do not remove by entity_id, use registry_id only"
```

**2. Remove** (only after reviewing the scan yourself)
```yaml
service: safe_orphan_cleaner.remove
data:
  registry_ids:
    - abc123...
```

Every `registry_id` passed to `remove` is independently re-checked for a
live-entity collision at removal time — not just trusted from an earlier
scan — and refused if one is found.

## What this does *not* do

Unlike the [bash script approach](https://community.home-assistant.io/t/6-routines-to-delete-rename-move-devices-entities-and-their-corresponding-registry-entries-data-and-metadata/755476),
this only touches the entity registry — it does **not** clean up
`states`/`statistics` history in `home-assistant_v2.db`. For orphans with
substantial historical data, run that script afterward for a full
cleanup.

## Disclaimer

Directly manipulates the entity registry. Review scan results yourself
before calling `remove`. No warranty.
