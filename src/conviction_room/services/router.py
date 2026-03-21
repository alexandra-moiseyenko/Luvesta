"""Plugin Router / Dispatcher service for Conviction Room.

Resolves the active plugin for a dimension, checks budget with the Cost
Governor, simulates dispatch, records cost, and emits trace events.

Requirements: 2.2, 2.3, 7.2, 12.1
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime
from uuid import UUID

from conviction_room.models.cost import CostRecord
from conviction_room.models.plugin import PluginError, PluginMetadata
from conviction_room.models.trace import TraceEvent
from conviction_room.services.cost_governor import CostGovernorService
from conviction_room.services.registry import PluginRegistryService

# Default estimated cost per dispatch (used for pre-flight budget check).
_DEFAULT_ESTIMATED_COST = 0.001

# TTL for the active-plugin cache (seconds).
_CACHE_TTL_SECONDS = 5.0


class PluginRouterService:
    """Routes dimension calls through the active plugin.

    Constructor accepts ``registry`` and ``cost_governor`` as dependencies.
    """

    def __init__(
        self,
        registry: PluginRegistryService,
        cost_governor: CostGovernorService,
    ) -> None:
        self._registry = registry
        self._cost_governor = cost_governor

        # Simple TTL cache: dimension -> (PluginMetadata, timestamp)
        self._plugin_cache: dict[str, tuple[PluginMetadata, float]] = {}

        # Internal trace event store (for testability via get_traces).
        self._traces: list[TraceEvent] = []

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    def dispatch(
        self,
        dimension: str,
        endpoint: str,
        payload: dict,
    ) -> dict | PluginError:
        """Dispatch a call to the active plugin for *dimension*.

        Steps:
        1. Resolve active plugin (with short TTL cache).
        2. Pre-flight budget check via Cost Governor.
        3. Simulate the plugin call.
        4. Record cost via Cost Governor.
        5. Emit a trace event.
        6. Return the simulated response or a PluginError.
        """
        start_time = time.monotonic()

        # 1. Resolve active plugin from registry (cached).
        plugin = self._resolve_plugin(dimension)
        if isinstance(plugin, PluginError):
            return plugin

        # 2. Pre-flight budget check.
        budget_error = self._cost_governor.check_budget(
            dimension=dimension,
            estimated_cost=_DEFAULT_ESTIMATED_COST,
        )
        if budget_error is not None:
            return budget_error

        # 3. Simulate dispatch (no real plugins yet).
        response = {
            "plugin_id": str(plugin.plugin_id),
            "dimension": dimension,
            "endpoint": endpoint,
            "status": "dispatched",
        }

        elapsed_ms = (time.monotonic() - start_time) * 1000.0

        # 4. Record cost after dispatch.
        cost_record = CostRecord(
            dimension=dimension,
            plugin_id=plugin.plugin_id,
            token_count=0,
            api_calls=1,
            dollar_cost=_DEFAULT_ESTIMATED_COST,
            is_estimated=True,
        )
        self._cost_governor.record_cost(cost_record)

        # 5. Emit trace event.
        trace = TraceEvent(
            dimension=dimension,
            plugin_id=plugin.plugin_id,
            input_hash=self._hash(payload),
            output_hash=self._hash(response),
            latency_ms=elapsed_ms,
            token_usage=0,
            cost_usd=_DEFAULT_ESTIMATED_COST,
            success=True,
        )
        self._traces.append(trace)

        # 6. Return simulated response.
        return response

    # ------------------------------------------------------------------
    # get_traces
    # ------------------------------------------------------------------

    def get_traces(self) -> list[TraceEvent]:
        """Return all emitted trace events (for testability)."""
        return list(self._traces)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_plugin(self, dimension: str) -> PluginMetadata | PluginError:
        """Resolve the active plugin, using a short TTL cache."""
        now = time.monotonic()
        cached = self._plugin_cache.get(dimension)
        if cached is not None:
            plugin, ts = cached
            if (now - ts) < _CACHE_TTL_SECONDS:
                return plugin

        result = self._registry.get_active(dimension)
        if isinstance(result, PluginMetadata):
            self._plugin_cache[dimension] = (result, now)
        return result

    @staticmethod
    def _hash(data: dict) -> str:
        """Return a short SHA-256 hex digest of the dict's repr."""
        return hashlib.sha256(repr(sorted(data.items())).encode()).hexdigest()[:16]
