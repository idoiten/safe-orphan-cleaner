"""Safe Orphan Cleaner.

Finds entity_registry entries flagged as orphaned by Home Assistant itself
(the same orphaned_timestamp signal used by the official frontend warning),
and — critically — checks whether the same entity_id has been reused by a
currently LIVE entity before ever suggesting removal by name.

Two ways to review and act on results:

1. Settings > System > Repairs — a scan creates one Repair issue per safe
   orphan, each with its own "Fix" button (click through individually,
   or dismiss the ones you want to keep). Dangerous (entity_id-collision)
   orphans get an informational, non-fixable issue instead.

2. Services (for bulk/scripted use):
     safe_orphan_cleaner.scan    - re-scan and refresh the Repairs list
     safe_orphan_cleaner.remove  - remove several by registry_id at once
                                    (e.g. "fix all the safe ones" in one call)
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

REMOVE_SCHEMA = vol.Schema(
    {
        vol.Required("registry_ids"): vol.All(cv.ensure_list, [cv.string]),
    }
)

ISSUE_PREFIX = "orphan_"


def _deleted_entity_id(deleted_entry) -> str | None:
    """Best-effort extraction of the entity_id from a DeletedRegistryEntry."""
    return getattr(deleted_entry, "entity_id", None)


def _run_scan(hass: HomeAssistant) -> dict:
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

        info = {
            "entity_id": entity_id,
            "unique_id": getattr(deleted_entry, "unique_id", None),
            "platform": getattr(deleted_entry, "platform", None),
            "registry_id": getattr(deleted_entry, "id", None),
            "orphaned_since": orphaned_ts,
        }

        if entity_id in live_ids:
            info["reason"] = (
                "entity_id currently reused by a LIVE entity - "
                "do not remove by entity_id, use registry_id only"
            )
            dangerous.append(info)
        else:
            safe.append(info)

    return {
        "safe": safe,
        "dangerous": dangerous,
        "safe_count": len(safe),
        "dangerous_count": len(dangerous),
        "skipped_unresolvable": skipped_no_entity_id,
    }


def _sync_repair_issues(hass: HomeAssistant, results: dict) -> None:
    """Create/refresh a Repair issue per found orphan, and clear stale ones."""
    current_issue_ids: set[str] = set()

    for item in results["safe"]:
        issue_id = f"{ISSUE_PREFIX}{item['registry_id']}"
        current_issue_ids.add(issue_id)
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="orphan_safe",
            translation_placeholders={
                "entity_id": item["entity_id"],
                "platform": str(item["platform"]),
            },
            data={
                "entity_id": item["entity_id"],
                "registry_id": item["registry_id"],
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

    async def handle_scan(call: ServiceCall) -> dict:
        results = _run_scan(hass)
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

        by_registry_id = {
            getattr(d, "id", None): d for d in registry.deleted_entities.values()
        }

        removed: list[dict] = []
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

            try:
                registry.async_remove(entity_id)
                removed.append({"registry_id": reg_id, "entity_id": entity_id})
                ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_PREFIX}{reg_id}")
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Failed to remove orphaned entry %s (%s)", reg_id, entity_id)
                skipped.append(
                    {"registry_id": reg_id, "entity_id": entity_id, "reason": f"removal failed: {err}"}
                )

        results = {"removed": removed, "skipped": skipped}
        _LOGGER.info(
            "Safe Orphan Cleaner remove: %d removed, %d skipped",
            len(removed),
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
