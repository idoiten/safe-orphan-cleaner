"""Repair flows for Safe Orphan Cleaner.

Each safe orphan found by a scan becomes its own Repair issue in
Settings > System > Repairs, with a "Fix" button. Dangerous
(entity_id-collision) orphans also get an issue, but a non-fixable one —
informational only, since those must never be removed by entity_id.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


class RemoveOrphanFlow(RepairsFlow):
    """Confirm-and-remove flow for a single safe orphaned entity."""

    def __init__(self, entity_id: str, registry_id: str) -> None:
        self._entity_id = entity_id
        self._registry_id = registry_id

    async def async_step_init(self, user_input: dict | None = None):
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict | None = None):
        if user_input is not None:
            registry = er.async_get(self.hass)
            live_ids = set(registry.entities.keys())
            # Re-verify at fix-time — never trust the state of the world
            # from whenever the scan happened to run.
            if self._entity_id in live_ids:
                return self.async_abort(reason="entity_now_live")
            registry.async_remove(self._entity_id)
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "entity_id": self._entity_id,
                "registry_id": self._registry_id,
            },
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict | None
) -> RepairsFlow:
    """Home Assistant calls this when the user clicks Fix on an issue."""
    assert data is not None
    return RemoveOrphanFlow(data["entity_id"], data["registry_id"])
