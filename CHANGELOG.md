# Changelog

All notable changes to this project are documented here.

## [0.6.1] - 2026-09-02

### Fixed
- "Translation error: UNCLOSED_TAG" on the scan action's description in
  Developer Tools > Actions. The text used literal `<config>`, which
  HA's frontend translation renderer interpreted as an unclosed
  HTML/markup tag. Reworded to avoid literal angle brackets entirely.
- Generated scripts (`safe_orphans_remove.sh` /
  `dangerous_orphans_remove.sh`) had `set -e`, which aborted the whole
  batch after just the first entity whenever the underlying bash script
  exited non-zero on an otherwise-normal path (e.g. after the
  orphaned-attributes N/T/A prompt). Removed - each line now runs
  independently regardless of the previous line's exit status.

## [0.6.0] - 2026-09-02

### Changed
- `safe_orphan_cleaner.scan` now writes two **ready-to-run bash scripts**
  (`safe_orphans_remove.sh` / `dangerous_orphans_remove.sh`) instead of
  plain id-list `.txt` files - each line is already a complete removal
  command, so running is just `bash <path>`. No more separate loop
  command to copy-paste (which was error-prone in a terminal for long
  one-liners).
- Scripts are `chmod 755` on write, proactively avoiding a host-side
  "Permission denied" caused by the container and host running as
  different UIDs across the Docker bind mount.
- Default `backup_dir` changed from `/home/pelle/scripts/backups/ha-registry`
  to `/home/pelle/scripts/backups`.

## [0.5.0] - 2026-09-02

### Changed
- `safe_orphan_cleaner.scan` now writes two plain-text files under
  `<config>/safe_orphan_cleaner/` - `safe_orphans_remove.txt` and
  `dangerous_orphans_remove.txt` (one internal `registry_id` per line) -
  and returns counts plus **one ready shell command per file** (a loop
  over the bash script) instead of per-entity detail.

### Removed
- `safe_orphan_cleaner.remove` service - redundant now that `scan`
  writes the files directly.
- Repair issue creation (Settings > System > Repairs) - was already
  informational-only since 0.4.0; simpler to not have it at all.

## [0.4.0] - 2026-09-02

### Changed
- **Breaking behavior change:** `safe_orphan_cleaner.remove` no longer
  attempts to remove entries from the registry itself. Real-world testing
  showed `entity_registry.async_remove()` only reliably removes *live*
  entities (moving them to `deleted_entities`) - it does not purge an
  entry that is already in `deleted_entities`. Rather than rely on an
  undocumented internal API, both `scan` and `remove` now generate the
  exact, ready-to-run command for the proven community bash script
  ([6 Routines to Delete/Rename/Move Devices & Entities](https://community.home-assistant.io/t/6-routines-to-delete-rename-move-devices-entities-and-their-corresponding-registry-entries-data-and-metadata/755476/7)),
  which also cleans up historical `states`/`statistics` data that this
  integration alone could never touch anyway.
- Repair issues (Settings > System > Repairs) are now all
  informational (`is_fixable=False`) - safe orphans show the ready
  command directly in the issue description instead of a one-click Fix
  button, since that button never actually worked correctly.
- Added configurable `script_path`, `config_path`, and `backup_dir` via
  `configuration.yaml` (previously hardcoded).

### Removed
- `repairs.py` - no longer needed, nothing is auto-fixable.

## [0.3.1] - 2026-09-02

### Fixed
- Service names, descriptions, and field labels (shown in Developer
  Tools > Actions) were never translatable - `strings.json` and
  `translations/*.json` only had an `issues` section. Added the missing
  `services` section (`scan`, `remove`, `registry_ids` field) in English
  and Swedish.

## [0.3.0] - 2026-09-02

### Added
- `repairs.py`: implements the actual Repair flow so the "Fix" button in
  Settings > System > Repairs works. Previously referenced by `__init__.py`
  but missing from the repo, so clicking Fix would have failed.
- `strings.json` and `translations/en.json` / `translations/sv.json`:
  issue titles/descriptions and the fix-flow confirmation step text, in
  English and Swedish. Previously missing, so Repair issues would have
  shown with raw/fallback text at best.

### Fixed
- `manifest.json`: filled in real `documentation`/`issue_tracker` URLs
  (previously placeholder `https://github.com/`), version bumped to
  match this release.

## [0.2.0] - 2026-09-02

### Fixed
- Moved the integration from `custom_components/safe-orphan-cleaner`
  (hyphen) to `custom_components/safe_orphan_cleaner` (underscore) to
  match the `domain` in `manifest.json`, per Home Assistant's
  `<config>/custom_components/<domain>` integration discovery path.

## [0.1.0] - 2026-09-01

### Added
- Initial release.
- `safe_orphan_cleaner.scan` service: scans the entity registry for
  entries Home Assistant itself has flagged as orphaned
  (`orphaned_timestamp` set), and checks each one for whether its
  `entity_id` has been reused by a currently live entity before
  classifying it as safe to remove by name.
- `safe_orphan_cleaner.remove` service: removes one or more orphaned
  entries by internal `registry_id`, independently re-verifying the
  live-entity safety check at removal time rather than trusting a prior
  scan.
- Each scan also creates one Repair issue per found orphan (safe ones
  fixable, dangerous/collision ones informational-only).
