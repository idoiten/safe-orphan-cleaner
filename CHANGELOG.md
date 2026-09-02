# Changelog

All notable changes to this project are documented here.

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
