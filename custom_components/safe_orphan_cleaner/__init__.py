"""Safe Orphan Cleaner.

Finds entity_registry entries flagged as orphaned by Home Assistant itself
(the same orphaned_timestamp signal used by the official frontend warning),
and - critically - checks whether the same entity_id has been reused by a
currently LIVE entity before ever suggesting removal by name.

IMPORTANT DESIGN NOTE (as of 0.4.0): this integration does NOT remove
registry entries itself. Testing showed entity_registry.async_remove()
only reliably removes LIVE entities (moving them to deleted_entities) -
it does not purge an entry that is already in deleted_entities. Rather
than guess at an undocumented internal API, this integration generates
the exact, ready-to-run command for the community bash script
(https://community.home-assistant.io/t/6-routines-to-delete-rename-move-devices-entities-and-their-corresponding-registry-entries-data-and-metadata/755476/7)
which is proven to work (including cleaning up historical
states/statistics data, which this integration alone cannot do anyway).

Usage:
  safe_orphan_cleaner.scan
    Scans the registry. Each safe orphan's result includes a ready
    remove_command. Also creates one informational Repair issue per
    found orphan (Settings > System > Repairs) with the command in its
    description - nothing is auto-fixable, by design.

  safe_orphan_cleaner.remove
    Given a list of registry_ids, re-verifies the live-entity safety
    check and returns the exact shell command(s) to run manually
    (does not touch the registry itself).
"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

DOMAIN = "safe_orphan_cleaner"
_LOGGER = logging.getLogger(__name__)

SERVICE_SCAN = "scan"
SERVICE_REMOVE = "remove"

CONF_SCRIPT_PATH = "script_path"
CONF_CONFIG_PATH = "config_path"
CONF_BACKUP_DIR = "backup_dir"

DEFAULT_SCRIPT_PATH = "/home/pelle/scripts/ha_delete_device_entity.sh"
DEFAULT_CONFIG_PATH = "/home/pelle/docker/homeassistant/config"
DEFAULT_BACKUP_DIR = "/home/pelle/scripts/backups/ha-registry"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_SCRIPT_PATH, default=DEFAULT_SCRIPT_PATH): cv.string,
                vol.Optional(CONF_CONFIG_PATH, default=DEFAULT_CONFIG_PATH): cv.string,
                vol.Optional(CONF_BACKUP_DIR, default=DEFAULT_BACKUP_DIR): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

REMOVE_SCHEMA = vol.Schema(
    {
        vol.Required("registry_ids"): vol.All(cv.ensure_list, [cv.string]),
    }
)

ISSUE_PREFIX = "orphan_"


def _deleted_entity_id(deleted_entry) -> str | None:
    """Best-effort extraction of the entity_id from a DeletedRegistryEntry."""
    return getattr(deleted_entry, "entity_id", None)


def _build_command(paths: dict, registry_id: str) -> str:
    """Build the ready-to-run shell command for one registry_id."""
    return (
        f"sudo {paths[CONF_SCRIPT_PATH]} "
        f"-x {paths[CONF_CONFIG_PATH]} "
        f"-b {paths[CONF_BACKUP_DIR]} "
        f"-E {registry_id}"
    )


def _run_scan(hass: HomeAssistant, paths: dict) -> dict:
    """Do the actual registry scan. Returns the raw results dict."""
    registry = er.async_get(hass)
    live_ids = set(registry.entities.keys())

    safe: list[dict] = []
    dangerous: list[dict] = []
    skipped_no_entity_id = 0

    for deleted_entry in registry.deleted_entities.values():
        orphaned_ts = getattr(deleted_entry, "orphaned_timestamp", None)
        if orphaned_ts is None:
            continue

        entity_id = _deleted_entity_id(deleted_entry)
        if entity_id is None:
            skipped_no_entity_id += 1
            continue

        registry_id = getattr(deleted_entry, "id", None)
        info = {
            "entity_id": entity_id,
            "unique_id": getattr(deleted_entry, "unique_id", None),
            "platform": getattr(deleted_entry, "platform", None),
            "registry_id": registry_id,
            "orphaned_since": orphaned_ts,
        }

        if entity_id in live_ids:
            info["reason"] = (
                "entity_id currently reused by a LIVE entity - "
                "do not remove by entity_id, use registry_id only"
            )
            dangerous.append(info)
        else:
            info["remove_command"] = _build_command(paths, registry_id)
            safe.append(info)

    return {
        "safe": safe,
        "dangerous": dangerous,
        "safe_count": len(safe),
        "dangerous_count": len(dangerous),
        "skipped_unresolvable": skipped_no_entity_id,
    }


def _sync_repair_issues(hass: HomeAssistant, results: dict) -> None:
    """Create/refresh an informational Repair issue per found orphan.

    None of these are auto-fixable (is_fixable=False) - see the module
    docstring for why. The ready remove_command is included directly in
    each safe issue's description so it's visible without extra clicks.
    """
    current_issue_ids: set[str] = set()

    for item in results["safe"]:
        issue_id = f"{ISSUE_PREFIX}{item['registry_id']}"
        current_issue_ids.add(issue_id)
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="orphan_safe",
            translation_placeholders={
                "entity_id": item["entity_id"],
                "platform": str(item["platform"]),
                "remove_command": item["remove_command"],
            },
        )

    for item in results["dangerous"]:
        issue_id = f"{ISSUE_PREFIX}{item['registry_id']}"
        current_issue_ids.add(issue_id)
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="orphan_dangerous",
            translation_placeholders={
                "entity_id": item["entity_id"],
                "registry_id": str(item["registry_id"]),
            },
        )

    previous_issue_ids: set[str] = hass.data.get(DOMAIN, {}).get("issue_ids", set())
    for stale_issue_id in previous_issue_ids - current_issue_ids:
        ir.async_delete_issue(hass, DOMAIN, stale_issue_id)

    hass.data.setdefault(DOMAIN, {})["issue_ids"] = current_issue_ids


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the safe_orphan_cleaner services."""
    hass.data.setdefault(DOMAIN, {})

    domain_config = config.get(DOMAIN) or {}
    paths = {
        CONF_SCRIPT_PATH: domain_config.get(CONF_SCRIPT_PATH, DEFAULT_SCRIPT_PATH),
        CONF_CONFIG_PATH: domain_config.get(CONF_CONFIG_PATH, DEFAULT_CONFIG_PATH),
        CONF_BACKUP_DIR: domain_config.get(CONF_BACKUP_DIR, DEFAULT_BACKUP_DIR),
    }
    hass.data[DOMAIN]["paths"] = paths

    async def handle_scan(call: ServiceCall) -> dict:
        results = _run_scan(hass, hass.data[DOMAIN]["paths"])
        _sync_repair_issues(hass, results)

        _LOGGER.info(
            "Safe Orphan Cleaner scan: %d safe, %d dangerous, %d unresolvable",
            results["safe_count"],
            results["dangerous_count"],
            results["skipped_unresolvable"],
        )
        hass.bus.async_fire(f"{DOMAIN}_scan_complete", results)
        return results

    async def handle_remove(call: ServiceCall) -> dict:
        registry = er.async_get(hass)
        live_ids = set(registry.entities.keys())
        requested_ids = call.data["registry_ids"]
        paths = hass.data[DOMAIN]["paths"]

        by_registry_id = {
            getattr(d, "id", None): d for d in registry.deleted_entities.values()
        }

        commands: list[dict] = []
        skipped: list[dict] = []

        for reg_id in requested_ids:
            deleted_entry = by_registry_id.get(reg_id)
            if deleted_entry is None:
                skipped.append({"registry_id": reg_id, "reason": "not found among orphaned entries"})
                continue

            entity_id = _deleted_entity_id(deleted_entry)

            if entity_id is not None and entity_id in live_ids:
                skipped.append(
                    {
                        "registry_id": reg_id,
                        "entity_id": entity_id,
                        "reason": "SAFETY: entity_id is currently live - refused",
                    }
                )
                continue

            commands.append(
                {
                    "registry_id": reg_id,
                    "entity_id": entity_id,
                    "command": _build_command(paths, reg_id),
                }
            )

        results = {"commands": commands, "skipped": skipped}
        _LOGGER.info(
            "Safe Orphan Cleaner remove: %d command(s) generated, %d skipped",
            len(commands),
            len(skipped),
        )
        return results

    hass.services.async_register(
        DOMAIN, SERVICE_SCAN, handle_scan, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE,
        handle_remove,
        schema=REMOVE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    return True
