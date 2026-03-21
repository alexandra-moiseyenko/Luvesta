"""Unit tests for Plugin Registry edge cases.

Tests cover: missing endpoint registration, activate non-existent plugin,
empty query, concurrent activation, get_active with no plugins, and
delete non-existent plugin.

**Validates: Requirements 2.4, 2.6**
"""

from __future__ import annotations

from uuid import uuid4

from conviction_room.contracts.base import (
    ContractConstraints,
    Endpoint,
    PluginContractBase,
)
from conviction_room.models.plugin import PluginError, PluginMetadata
from conviction_room.services.registry import PluginRegistryService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(dimension: str = "test-dim", version: str = "1.0.0") -> PluginContractBase:
    return PluginContractBase(
        version=version,
        dimension=dimension,
        endpoints=[
            Endpoint(name="run", method="POST", path="/run"),
        ],
        health_check=Endpoint(name="health", method="GET", path="/health"),
        constraints=ContractConstraints(
            max_response_time_ms=5000,
            max_payload_bytes=1_048_576,
        ),
    )


def _make_plugin(dimension: str = "test-dim", contract_version: str = "1.0.0") -> PluginMetadata:
    return PluginMetadata(
        plugin_id=uuid4(),
        dimension=dimension,
        name="test-plugin",
        version="1.0.0",
        contract_version=contract_version,
        status="inactive",
        endpoint_base_url="http://localhost:8000",
    )


def _valid_endpoints() -> list[dict]:
    return [
        {"name": "run", "method": "POST", "path": "/run"},
        {"name": "health", "method": "GET", "path": "/health"},
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_register_with_missing_endpoint_returns_plugin_error():
    """Register plugin with missing endpoint → returns PluginError with violations."""
    registry = PluginRegistryService()
    contract = _make_contract()
    plugin = _make_plugin()

    # Only provide health check, missing the "run" endpoint
    incomplete_endpoints = [{"name": "health", "method": "GET", "path": "/health"}]

    result = registry.register(plugin, contract, incomplete_endpoints)

    assert isinstance(result, PluginError)
    assert result.error_code == "CONTRACT_VALIDATION_FAILED"
    assert len(result.details) > 0
    assert any("run" in v for v in result.details)


def test_activate_nonexistent_plugin_returns_plugin_error():
    """Activate when plugin doesn't exist → returns PluginError."""
    registry = PluginRegistryService()
    fake_id = uuid4()

    result = registry.activate(fake_id)

    assert isinstance(result, PluginError)
    assert result.error_code == "PLUGIN_NOT_FOUND"
    assert str(fake_id) in result.message


def test_query_with_no_results_returns_empty_list():
    """Query with no results → returns empty list."""
    registry = PluginRegistryService()

    results = registry.query(dimension="nonexistent-dimension")

    assert results == []


def test_concurrent_activation_only_last_is_active():
    """Concurrent activation (activate A, then activate B for same dimension)
    → only B is active."""
    registry = PluginRegistryService()
    contract = _make_contract()

    plugin_a = _make_plugin()
    plugin_b = _make_plugin()

    registry.register(plugin_a, contract, _valid_endpoints())
    registry.register(plugin_b, contract, _valid_endpoints())

    # Activate A
    result_a = registry.activate(plugin_a.plugin_id)
    assert isinstance(result_a, PluginMetadata)
    assert result_a.status == "active"

    # Activate B
    result_b = registry.activate(plugin_b.plugin_id)
    assert isinstance(result_b, PluginMetadata)
    assert result_b.status == "active"

    # Only B should be active
    active = registry.get_active("test-dim")
    assert isinstance(active, PluginMetadata)
    assert active.plugin_id == plugin_b.plugin_id

    # A should be inactive
    a_now = registry.get(plugin_a.plugin_id)
    assert a_now is not None
    assert a_now.status == "inactive"


def test_get_active_no_plugins_registered_returns_error():
    """get_active when no plugins registered → returns PluginError with
    'No plugins registered' message."""
    registry = PluginRegistryService()

    result = registry.get_active("empty-dimension")

    assert isinstance(result, PluginError)
    assert result.error_code == "PLUGIN_NOT_FOUND"
    assert result.dimension == "empty-dimension"
    assert any("No plugins registered" in d for d in result.details)


def test_delete_nonexistent_plugin_returns_false():
    """Delete non-existent plugin → returns False."""
    registry = PluginRegistryService()
    fake_id = uuid4()

    result = registry.delete(fake_id)

    assert result is False
