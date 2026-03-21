"""Plugin Registry service for Conviction Room.

Maintains a catalog of all registered plugins, indexed by dimension, version,
and status.  Supports registration (with contract validation), activation
(atomic swap), deactivation, deletion, and filtered queries.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 1.2, 1.4, 1.5
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from conviction_room.contracts.base import PluginContractBase
from conviction_room.contracts.validator import validate_plugin_against_contract
from conviction_room.models.plugin import PluginError, PluginMetadata


class PluginRegistryService:
    """In-memory plugin registry.

    Stores plugins in a ``dict[UUID, PluginMetadata]`` and provides
    registration, activation, deactivation, deletion, and query methods.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, PluginMetadata] = {}

    # ------------------------------------------------------------------
    # register
    # ------------------------------------------------------------------

    def register(
        self,
        plugin: PluginMetadata,
        contract: PluginContractBase,
        plugin_endpoints: list[dict],
    ) -> PluginMetadata | PluginError:
        """Register a new plugin after validating it against its contract.

        Returns the registered ``PluginMetadata`` on success, or a
        ``PluginError`` listing every contract violation on failure.
        """
        violations = validate_plugin_against_contract(
            plugin, contract, plugin_endpoints,
        )
        if violations:
            return PluginError(
                error_code="CONTRACT_VALIDATION_FAILED",
                message="Plugin failed contract validation",
                dimension=plugin.dimension,
                plugin_id=plugin.plugin_id,
                details=violations,
            )

        now = datetime.utcnow()
        plugin = plugin.model_copy(
            update={
                "validated_at": now,
                "contract_violations": [],
            },
        )
        self._store[plugin.plugin_id] = plugin
        return plugin

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------

    def get(self, plugin_id: UUID) -> PluginMetadata | None:
        """Return plugin metadata by ID, or ``None`` if not found."""
        return self._store.get(plugin_id)

    # ------------------------------------------------------------------
    # activate  (atomic: deactivate current + activate new)
    # ------------------------------------------------------------------

    def activate(self, plugin_id: UUID) -> PluginMetadata | PluginError:
        """Activate a plugin for its dimension.

        Atomically deactivates the currently active plugin for the same
        dimension (if any) and activates the requested one.
        """
        plugin = self._store.get(plugin_id)
        if plugin is None:
            return PluginError(
                error_code="PLUGIN_NOT_FOUND",
                message=f"Plugin {plugin_id} not found",
                plugin_id=plugin_id,
            )

        dimension = plugin.dimension

        # Deactivate the current active plugin for this dimension (if any)
        for pid, p in self._store.items():
            if p.dimension == dimension and p.status == "active" and pid != plugin_id:
                self._store[pid] = p.model_copy(update={"status": "inactive"})

        # Activate the requested plugin
        self._store[plugin_id] = plugin.model_copy(update={"status": "active"})
        return self._store[plugin_id]

    # ------------------------------------------------------------------
    # deactivate
    # ------------------------------------------------------------------

    def deactivate(self, plugin_id: UUID) -> PluginMetadata | PluginError:
        """Deactivate a plugin."""
        plugin = self._store.get(plugin_id)
        if plugin is None:
            return PluginError(
                error_code="PLUGIN_NOT_FOUND",
                message=f"Plugin {plugin_id} not found",
                plugin_id=plugin_id,
            )

        self._store[plugin_id] = plugin.model_copy(update={"status": "inactive"})
        return self._store[plugin_id]

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    def delete(self, plugin_id: UUID) -> bool:
        """Delete a plugin from the registry. Returns True if deleted."""
        return self._store.pop(plugin_id, None) is not None

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------

    def query(
        self,
        dimension: str | None = None,
        status: str | None = None,
        version: str | None = None,
    ) -> list[PluginMetadata]:
        """Query plugins with optional filters.

        Results include contract_version, health_status, and
        latest_benchmark_score (all part of PluginMetadata).
        """
        results: list[PluginMetadata] = []
        for plugin in self._store.values():
            if dimension is not None and plugin.dimension != dimension:
                continue
            if status is not None and plugin.status != status:
                continue
            if version is not None and plugin.version != version:
                continue
            results.append(plugin)
        return results

    # ------------------------------------------------------------------
    # get_active
    # ------------------------------------------------------------------

    def get_active(self, dimension: str) -> PluginMetadata | PluginError:
        """Return the active plugin for a dimension.

        If no active plugin exists, returns a ``PluginError`` with
        ``error_code="PLUGIN_NOT_FOUND"`` and details listing available
        inactive plugins.
        """
        for plugin in self._store.values():
            if plugin.dimension == dimension and plugin.status == "active":
                return plugin

        # No active plugin — gather suggestions
        inactive = [
            f"{p.name} (id={p.plugin_id}, version={p.version})"
            for p in self._store.values()
            if p.dimension == dimension and p.status != "active"
        ]
        return PluginError(
            error_code="PLUGIN_NOT_FOUND",
            message=f"No active plugin for dimension '{dimension}'",
            dimension=dimension,
            details=inactive if inactive else ["No plugins registered for this dimension"],
        )

    # ------------------------------------------------------------------
    # flag_unvalidated  (Requirement 1.5)
    # ------------------------------------------------------------------

    def flag_unvalidated(
        self, dimension: str, new_contract_version: str,
    ) -> list[PluginMetadata]:
        """Flag plugins whose contract_version doesn't match the new version.

        Returns the list of plugins that need re-validation.
        """
        flagged: list[PluginMetadata] = []
        for pid, plugin in self._store.items():
            if plugin.dimension == dimension and plugin.contract_version != new_contract_version:
                flagged.append(plugin)
        return flagged
