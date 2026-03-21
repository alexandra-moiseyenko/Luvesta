# Feature: conviction-room, Property 5: Registry returns correct active plugin
# Feature: conviction-room, Property 6: Registry query returns correct filtered results
# Feature: conviction-room, Property 7: Active plugin switch is atomic
"""
Property tests for Plugin Registry correctness.

Property 5 — get_active returns the correct active plugin or a PluginError.
Property 6 — query returns exactly the plugins matching all filter criteria.
Property 7 — active plugin switch is atomic.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**
"""

from __future__ import annotations

from uuid import uuid4

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from conviction_room.contracts.base import (
    ContractConstraints,
    Endpoint,
    PluginContractBase,
)
from conviction_room.models.plugin import PluginError, PluginMetadata
from conviction_room.services.registry import PluginRegistryService
from tests.conftest import safe_text, safe_dicts


# ---------------------------------------------------------------------------
# Helpers — build a valid plugin + contract + endpoints triple
# ---------------------------------------------------------------------------

semver_st = st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True)


def _build_contract(dimension: str, version: str) -> PluginContractBase:
    """Build a minimal valid contract for a dimension."""
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


def _build_plugin(dimension: str, contract_version: str, status: str = "inactive") -> PluginMetadata:
    """Build a PluginMetadata that matches the contract from _build_contract."""
    return PluginMetadata(
        plugin_id=uuid4(),
        dimension=dimension,
        name=f"plugin-{uuid4().hex[:6]}",
        version="1.0.0",
        contract_version=contract_version,
        status=status,
        endpoint_base_url="http://localhost:8000",
    )


def _matching_endpoints() -> list[dict]:
    """Endpoints that satisfy the contract from _build_contract."""
    return [
        {"name": "run", "method": "POST", "path": "/run"},
        {"name": "health", "method": "GET", "path": "/health"},
    ]


def _register(registry: PluginRegistryService, plugin: PluginMetadata, contract: PluginContractBase) -> PluginMetadata:
    """Register a plugin and assert success."""
    result = registry.register(plugin, contract, _matching_endpoints())
    assert isinstance(result, PluginMetadata), f"Registration failed: {result}"
    return result


# ---------------------------------------------------------------------------
# Property 5: Registry returns correct active plugin
# ---------------------------------------------------------------------------


@st.composite
def _dimension_with_one_active(draw: st.DrawFn):
    """Generate a registry with one dimension that has exactly one active plugin
    among several registered plugins."""
    dimension = draw(safe_text)
    contract_version = draw(semver_st)
    num_plugins = draw(st.integers(min_value=1, max_value=6))

    registry = PluginRegistryService()
    contract = _build_contract(dimension, contract_version)

    plugins: list[PluginMetadata] = []
    for _ in range(num_plugins):
        p = _build_plugin(dimension, contract_version)
        registered = _register(registry, p, contract)
        plugins.append(registered)

    # Activate exactly one
    active_idx = draw(st.integers(min_value=0, max_value=num_plugins - 1))
    active_plugin = plugins[active_idx]
    result = registry.activate(active_plugin.plugin_id)
    assert isinstance(result, PluginMetadata)

    return registry, dimension, active_plugin.plugin_id


@given(data=_dimension_with_one_active())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_get_active_returns_correct_plugin(
    data: tuple[PluginRegistryService, str, ...],
) -> None:
    """For any dimension with exactly one active plugin, requesting that
    dimension shall return that plugin.

    # Feature: conviction-room, Property 5: Registry returns correct active plugin
    **Validates: Requirements 2.2, 2.3, 2.6**
    """
    registry, dimension, active_id = data
    result = registry.get_active(dimension)

    assert isinstance(result, PluginMetadata), (
        f"Expected PluginMetadata but got PluginError: {result}"
    )
    assert result.plugin_id == active_id
    assert result.status == "active"
    assert result.dimension == dimension


@st.composite
def _dimension_with_no_active(draw: st.DrawFn):
    """Generate a registry with plugins in a dimension but none active."""
    dimension = draw(safe_text)
    contract_version = draw(semver_st)
    num_plugins = draw(st.integers(min_value=1, max_value=5))

    registry = PluginRegistryService()
    contract = _build_contract(dimension, contract_version)

    plugins: list[PluginMetadata] = []
    for _ in range(num_plugins):
        p = _build_plugin(dimension, contract_version, status="inactive")
        registered = _register(registry, p, contract)
        plugins.append(registered)

    return registry, dimension, plugins


@given(data=_dimension_with_no_active())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_get_active_returns_error_when_no_active(
    data: tuple[PluginRegistryService, str, list[PluginMetadata]],
) -> None:
    """For any dimension with no active plugin, the request shall return a
    PluginError identifying the dimension and listing available inactive plugins.

    # Feature: conviction-room, Property 5: Registry returns correct active plugin
    **Validates: Requirements 2.2, 2.3, 2.6**
    """
    registry, dimension, plugins = data
    result = registry.get_active(dimension)

    assert isinstance(result, PluginError), (
        f"Expected PluginError but got PluginMetadata: {result}"
    )
    assert result.dimension == dimension
    assert result.error_code == "PLUGIN_NOT_FOUND"
    # The error details should list available inactive plugins
    assert len(result.details) > 0


# ---------------------------------------------------------------------------
# Property 6: Registry query returns correct filtered results
# ---------------------------------------------------------------------------


@st.composite
def _registry_with_diverse_plugins(draw: st.DrawFn):
    """Generate a registry with plugins across multiple dimensions, versions,
    and statuses, plus a random query filter."""
    dimensions = draw(st.lists(safe_text, min_size=1, max_size=3, unique=True))
    versions = draw(st.lists(semver_st, min_size=1, max_size=3, unique=True))
    statuses = ["active", "inactive", "deprecated"]

    registry = PluginRegistryService()
    all_plugins: list[PluginMetadata] = []

    for dim in dimensions:
        cv = versions[0]  # use first version as contract version for this dim
        contract = _build_contract(dim, cv)
        num = draw(st.integers(min_value=1, max_value=3))
        for _ in range(num):
            ver = draw(st.sampled_from(versions))
            status = draw(st.sampled_from(statuses))
            p = PluginMetadata(
                plugin_id=uuid4(),
                dimension=dim,
                name=f"plugin-{uuid4().hex[:6]}",
                version=ver,
                contract_version=cv,
                status=status,
                endpoint_base_url="http://localhost:8000",
            )
            registered = _register(registry, p, contract)
            all_plugins.append(registered)

    # Build a random query filter
    q_dim = draw(st.none() | st.sampled_from(dimensions))
    q_ver = draw(st.none() | st.sampled_from(versions))
    q_status = draw(st.none() | st.sampled_from(statuses))

    return registry, all_plugins, q_dim, q_ver, q_status


@given(data=_registry_with_diverse_plugins())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_query_returns_correct_filtered_results(
    data: tuple[PluginRegistryService, list[PluginMetadata], str | None, str | None, str | None],
) -> None:
    """For any set of registered plugins and any query filter (by dimension,
    version, status), the query result shall contain exactly the plugins
    matching all filter criteria, and each result shall include contract_version,
    health_status, and latest_benchmark_score.

    # Feature: conviction-room, Property 6: Registry query returns correct filtered results
    **Validates: Requirements 2.1, 2.5**
    """
    registry, all_plugins, q_dim, q_ver, q_status = data

    results = registry.query(dimension=q_dim, version=q_ver, status=q_status)

    # Compute expected set by filtering all_plugins manually
    expected = all_plugins
    if q_dim is not None:
        expected = [p for p in expected if p.dimension == q_dim]
    if q_ver is not None:
        expected = [p for p in expected if p.version == q_ver]
    if q_status is not None:
        expected = [p for p in expected if p.status == q_status]

    result_ids = {p.plugin_id for p in results}
    expected_ids = {p.plugin_id for p in expected}

    assert result_ids == expected_ids, (
        f"Query mismatch: got {result_ids}, expected {expected_ids}"
    )

    # Each result must include contract_version, health_status, latest_benchmark_score
    for p in results:
        assert hasattr(p, "contract_version") and p.contract_version is not None
        assert hasattr(p, "health_status") and p.health_status is not None
        # latest_benchmark_score may be None, but the field must exist
        assert hasattr(p, "latest_benchmark_score")


# ---------------------------------------------------------------------------
# Property 7: Active plugin switch is atomic
# ---------------------------------------------------------------------------


@st.composite
def _dimension_with_two_plugins(draw: st.DrawFn):
    """Generate a registry with a dimension containing two plugins, A active
    and B inactive."""
    dimension = draw(safe_text)
    contract_version = draw(semver_st)

    registry = PluginRegistryService()
    contract = _build_contract(dimension, contract_version)

    plugin_a = _build_plugin(dimension, contract_version)
    plugin_b = _build_plugin(dimension, contract_version)

    _register(registry, plugin_a, contract)
    _register(registry, plugin_b, contract)

    # Activate A first
    result_a = registry.activate(plugin_a.plugin_id)
    assert isinstance(result_a, PluginMetadata)

    return registry, dimension, plugin_a.plugin_id, plugin_b.plugin_id


@given(data=_dimension_with_two_plugins())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_active_plugin_switch_is_atomic(
    data: tuple[PluginRegistryService, str, ...],
) -> None:
    """For any dimension, when the active plugin is changed from plugin A to
    plugin B, after the switch completes, all subsequent requests for that
    dimension shall be routed to plugin B.

    # Feature: conviction-room, Property 7: Active plugin switch is atomic
    **Validates: Requirements 2.4**
    """
    registry, dimension, plugin_a_id, plugin_b_id = data

    # Verify A is currently active
    active_before = registry.get_active(dimension)
    assert isinstance(active_before, PluginMetadata)
    assert active_before.plugin_id == plugin_a_id

    # Switch to B
    result = registry.activate(plugin_b_id)
    assert isinstance(result, PluginMetadata)
    assert result.plugin_id == plugin_b_id
    assert result.status == "active"

    # All subsequent requests should return B
    active_after = registry.get_active(dimension)
    assert isinstance(active_after, PluginMetadata)
    assert active_after.plugin_id == plugin_b_id
    assert active_after.status == "active"

    # A should no longer be active
    plugin_a = registry.get(plugin_a_id)
    assert plugin_a is not None
    assert plugin_a.status != "active"
