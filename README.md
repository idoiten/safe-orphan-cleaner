# Safe Orphan Cleaner

Finds Home Assistant entity registry entries that HA itself has already
flagged as orphaned (`orphaned_timestamp` set — the same signal behind the
"This entity is currently unavailable and is an orphan..." warning), and
crucially checks whether that `entity_id` has since been **reused by a
currently live entity** before treating it the same as a genuinely unused
one.

Existing community tools either can't detect this collision (and could
guide you into deleting a live entity by accident) or have no discovery
step at all. This integration does the discovery and the safety check,
then hands off the actual removal to a proven external tool rather than
guessing at an undocumented internal API.

## Why this exists

Built after discovering, the hard way, that:
- An old deleted `automation.hackbevattning` shared its entity_id with the
  live, actively-used irrigation automation of the same name.
- An old deleted `binary_sensor.markisstyrning_sol` shared its entity_id
  with the live awning sun sensor.

Using either "by name" would have deleted the live entity instead of the
intended orphan. This integration keeps that class of mistake off the
table: every orphan is scanned and split into two lists by exactly this
collision check, and only ever referenced afterward by its internal
`registry_id`, never by `entity_id`.

## What this does *not* do

**It does not remove anything itself.** Testing showed
`entity_registry.async_remove()` only reliably removes *live* entities
(moving them to `deleted_entities`) — it does not purge an entry that's
already there, and there's no documented public API that does. Rather
than pretend to have a working "Remove" button, this integration
generates ready-to-run scripts for the proven community bash script,
[6 Routines to Delete/Rename/Move Devices & Entities](https://community.home-assistant.io/t/6-routines-to-delete-rename-move-devices-entities-and-their-corresponding-registry-entries-data-and-metadata/755476/7),
which also cleans up historical `states`/`statistics` data that this
integration alone could never touch anyway.

## Installation (HACS custom repository)

1. HACS → the three dots (top right) → **Custom repositories**
2. Add this repo's URL, category **Integration**
3. Install **Safe Orphan Cleaner**
4. Add to `configuration.yaml` (all three keys are optional — shown
   defaults below):
   ```yaml
   safe_orphan_cleaner:
     script_path: /home/pelle/scripts/ha_delete_device_entity.sh
     config_path: /home/pelle/docker/homeassistant/config
     backup_dir: /home/pelle/scripts/backups
   ```
5. Restart Home Assistant
6. Separately, install the bash script itself from the community thread
   linked above — this integration only generates commands for it, it
   doesn't include it.

## Usage

Developer Tools → Actions → `safe_orphan_cleaner.scan`

This writes two ready-to-run bash scripts under
`<config_path>/safe_orphan_cleaner/`:

- `safe_orphans_remove.sh` — entity_id not reused anywhere live
- `dangerous_orphans_remove.sh` — entity_id reused by a currently live
  entity (still safe to remove, since both scripts always use `-E`/
  `registry_id`, never `-e`/`entity_id` — the split exists so you can
  choose to review the "dangerous" batch more carefully if you want, not
  because it's unsafe on its own)

Each script already contains one full removal command per line — running
it is just `bash <path>`, nothing to copy-paste. The service response
gives you the exact path to each:

```yaml
safe_count: 41
dangerous_count: 2
safe_script: /home/pelle/docker/homeassistant/config/safe_orphan_cleaner/safe_orphans_remove.sh
dangerous_script: /home/pelle/docker/homeassistant/config/safe_orphan_cleaner/dangerous_orphans_remove.sh
```

**Stop Home Assistant first** (the underlying bash script requires this),
then run e.g.:

```bash
bash /home/pelle/docker/homeassistant/config/safe_orphan_cleaner/safe_orphans_remove.sh
```

Review each prompt the underlying script shows before confirming — it
asks per entity, it does not blindly bulk-delete.

## Disclaimer

Read-only against the entity registry itself; the actual deletion happens
via the external bash script, which directly manipulates Home Assistant's
storage files and database. Review the generated scripts yourself before
running anything. No warranty.
