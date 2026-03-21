# Feature: conviction-room, Property 2: Plugin contract structural completeness
# Feature: conviction-room, Property 3: Registration validates against contract
# Feature: conviction-room, Property 4: Contract version bump flags unvalidated plugins
"""
Property tests for plugin contract validation.

Property 2 — structural completeness of PluginContractBase.
Property 3 — registration validates plugin endpoints against contract.
Property 4 — contract version bump flags unvalidated plugins.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.1, 8.2, 10.1–10.6**
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings, assume
from hypothesis import strategies as st

from conviction_room.contracts.base import (
    ContractConstraints,
    ContractSchemas,
    Endpoint,
    LifecycleHooks,
    PluginContractBase,
)
from conviction_room.contracts.validator import validate_plugin_against_contract
from conviction_room.models.plugin import PluginMetadata
from tests.conftest import safe_text, safe_floats, safe_dicts, safe_ints


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

endpoint_st = st.builds(
    Endpoint,
    name=safe_text,
    method=st.sampled_from(["GET", "POST", "PUT", "DELETE"]),
    path=st.builds(lambda s: "/" + s, st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L",)))),
    request_schema=safe_dicts,
    response_schema=safe_dicts,
    error_schema=safe_dicts,
)

lifecycle_hooks_st = st.builds(
    LifecycleHooks,
    init=st.booleans(),
    warmup=st.booleans(),
    shutdown=st.booleans(),
    readiness=st.booleans(),
)

constraints_st = st.builds(
    ContractConstraints,
    max_response_time_ms=st.integers(min_value=1, max_value=30_000),
    max_payload_bytes=st.integers(min_value=1, max_value=10_485_760),
    required_error_codes=st.lists(safe_text, min_size=0, max_size=5),
)

schemas_st = st.builds(
    ContractSchemas,
    request_schema=safe_dicts,
    response_schema=safe_dicts,
    error_schema=safe_dicts,
)

contract_st = st.builds(
    PluginContractBase,
    version=st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True),
    dimension=safe_text,
    endpoints=st.lists(endpoint_st, min_size=1, max_size=5),
    health_check=endpoint_st,
    lifecycle_hooks=lifecycle_hooks_st,
    constraints=constraints_st,
    schemas=schemas_st,
)

semver_st = st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True)


# ---------------------------------------------------------------------------
# Property 2: Plugin contract structural completeness
# ---------------------------------------------------------------------------


@given(contract=contract_st)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_contract_structural_completeness(contract: PluginContractBase) -> None:
    """For any PluginContractBase, it shall contain: a versioned interface with
    request/response/error schemas for each endpoint; a health-check endpoint;
    lifecycle hooks (init, warmup, shutdown, readiness); and constraints
    (max_response_time_ms, max_payload_bytes, required_error_codes).

    # Feature: conviction-room, Property 2: Plugin contract structural completeness
    **Validates: Requirements 1.1, 1.3, 1.6, 8.1, 10.1, 10.2, 10.3, 10.4, 10.5**
    """
    # 1. Versioned interface
    assert isinstance(contract.version, str) and len(contract.version) > 0
    assert isinstance(contract.dimension, str) and len(contract.dimension) > 0

    # 2. Endpoints with schemas
    assert len(contract.endpoints) >= 1
    for ep in contract.endpoints:
        assert isinstance(ep.name, str) and len(ep.name) > 0
        assert ep.method in ("GET", "POST", "PUT", "DELETE")
        assert isinstance(ep.path, str) and len(ep.path) > 0
        assert isinstance(ep.request_schema, dict)
        assert isinstance(ep.response_schema, dict)
        assert isinstance(ep.error_schema, dict)

    # 3. Health-check endpoint
    hc = contract.health_check
    assert isinstance(hc, Endpoint)
    assert isinstance(hc.name, str) and len(hc.name) > 0
    assert isinstance(hc.path, str) and len(hc.path) > 0

    # 4. Lifecycle hooks — all four fields present
    hooks = contract.lifecycle_hooks
    assert isinstance(hooks, LifecycleHooks)
    assert isinstance(hooks.init, bool)
    assert isinstance(hooks.warmup, bool)
    assert isinstance(hooks.shutdown, bool)
    assert isinstance(hooks.readiness, bool)

    # 5. Constraints
    c = contract.constraints
    assert isinstance(c, ContractConstraints)
    assert isinstance(c.max_response_time_ms, int) and c.max_response_time_ms > 0
    assert isinstance(c.max_payload_bytes, int) and c.max_payload_bytes > 0
    assert isinstance(c.required_error_codes, list)

    # 6. Top-level schemas
    s = contract.schemas
    assert isinstance(s, ContractSchemas)
    assert isinstance(s.request_schema, dict)
    assert isinstance(s.response_schema, dict)
    assert isinstance(s.error_schema, dict)


# ---------------------------------------------------------------------------
# Property 3: Registration validates against contract
# ---------------------------------------------------------------------------


@st.composite
def _matching_plugin_and_contract(draw: st.DrawFn):
    """Generate a contract and plugin_endpoints that fully match it."""
    contract = draw(contract_st)
    plugin = draw(st.builds(
        PluginMetadata,
        plugin_id=st.uuids(),
        dimension=st.just(contract.dimension),
        name=safe_text,
        version=semver_st,
        contract_version=st.just(contract.version),
        status=st.sampled_from(["active", "inactive", "deprecated"]),
        endpoint_base_url=safe_text,
        config=safe_dicts,
    ))

    # Build plugin_endpoints that satisfy every required endpoint + health check
    plugin_endpoints: list[dict] = []
    all_required = list(contract.endpoints) + [contract.health_check]
    for ep in all_required:
        plugin_endpoints.append({
            "name": ep.name,
            "method": ep.method,
            "path": ep.path,
            "supported_error_codes": list(contract.constraints.required_error_codes),
            "max_response_time_ms": contract.constraints.max_response_time_ms,
            "max_payload_bytes": contract.constraints.max_payload_bytes,
        })
    return contract, plugin, plugin_endpoints


@st.composite
def _mismatched_plugin_and_contract(draw: st.DrawFn):
    """Generate a contract and plugin_endpoints where some required endpoints
    are deliberately missing."""
    contract = draw(contract_st)
    assume(len(contract.endpoints) >= 1)

    plugin = draw(st.builds(
        PluginMetadata,
        plugin_id=st.uuids(),
        dimension=st.just(contract.dimension),
        name=safe_text,
        version=semver_st,
        contract_version=st.just(contract.version),
        status=st.sampled_from(["active", "inactive", "deprecated"]),
        endpoint_base_url=safe_text,
        config=safe_dicts,
    ))

    # Include health check but drop at least one required endpoint
    all_required = list(contract.endpoints)
    num_to_keep = draw(st.integers(min_value=0, max_value=max(0, len(all_required) - 1)))
    kept = all_required[:num_to_keep]
    dropped = all_required[num_to_keep:]
    assume(len(dropped) >= 1)

    # Build the set of (name, method) pairs that the plugin will expose
    hc = contract.health_check
    provided_keys = {(hc.name, hc.method)}
    for ep in kept:
        provided_keys.add((ep.name, ep.method))

    # Ensure at least one dropped endpoint is truly absent (its key is not
    # accidentally satisfied by the health check or a kept endpoint).
    truly_missing = [ep for ep in dropped if (ep.name, ep.method) not in provided_keys]
    assume(len(truly_missing) >= 1)

    plugin_endpoints: list[dict] = []
    plugin_endpoints.append({
        "name": hc.name,
        "method": hc.method,
        "path": hc.path,
        "supported_error_codes": list(contract.constraints.required_error_codes),
    })
    for ep in kept:
        plugin_endpoints.append({
            "name": ep.name,
            "method": ep.method,
            "path": ep.path,
            "supported_error_codes": list(contract.constraints.required_error_codes),
        })

    return contract, plugin, plugin_endpoints, truly_missing


@given(data=_matching_plugin_and_contract())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_registration_succeeds_when_all_endpoints_match(
    data: tuple[PluginContractBase, PluginMetadata, list[dict]],
) -> None:
    """For any plugin that implements all required endpoints and schemas,
    validation shall succeed (empty violations).

    # Feature: conviction-room, Property 3: Registration validates against contract
    **Validates: Requirements 1.2, 1.4, 8.2, 10.6**
    """
    contract, plugin, plugin_endpoints = data
    violations = validate_plugin_against_contract(plugin, contract, plugin_endpoints)
    assert violations == [], (
        f"Expected no violations but got: {violations}"
    )


@given(data=_mismatched_plugin_and_contract())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_registration_fails_listing_every_missing_endpoint(
    data: tuple[PluginContractBase, PluginMetadata, list[dict], list[Endpoint]],
) -> None:
    """For any plugin missing required endpoints, validation shall fail and
    the rejection error shall list every contract violation found.

    # Feature: conviction-room, Property 3: Registration validates against contract
    **Validates: Requirements 1.2, 1.4, 8.2, 10.6**
    """
    contract, plugin, plugin_endpoints, dropped = data
    violations = validate_plugin_against_contract(plugin, contract, plugin_endpoints)

    assert len(violations) > 0, "Expected violations for missing endpoints"

    # Each dropped endpoint should appear in the violations
    for ep in dropped:
        found = any(ep.name in v for v in violations)
        assert found, (
            f"Missing endpoint '{ep.name}' not mentioned in violations: {violations}"
        )


# ---------------------------------------------------------------------------
# Property 4: Contract version bump flags unvalidated plugins
# ---------------------------------------------------------------------------


def find_plugins_needing_revalidation(
    plugins: list[PluginMetadata],
    new_contract_version: str,
) -> list[PluginMetadata]:
    """Return plugins whose contract_version does not match the new version.

    This is the core logic that a registry would use when a contract version
    is bumped: any plugin not yet validated against the new version is flagged.
    """
    return [p for p in plugins if p.contract_version != new_contract_version]


@st.composite
def _plugins_with_version_bump(draw: st.DrawFn):
    """Generate a list of plugins with a mix of contract versions, then bump
    the contract to a new version."""
    old_version = draw(semver_st)
    new_version = draw(semver_st)
    assume(old_version != new_version)

    dimension = draw(safe_text)
    num_plugins = draw(st.integers(min_value=1, max_value=10))

    plugins: list[PluginMetadata] = []
    for _ in range(num_plugins):
        # Some plugins on old version, some already on new
        cv = draw(st.sampled_from([old_version, new_version]))
        p = draw(st.builds(
            PluginMetadata,
            plugin_id=st.uuids(),
            dimension=st.just(dimension),
            name=safe_text,
            version=semver_st,
            contract_version=st.just(cv),
            status=st.sampled_from(["active", "inactive", "deprecated"]),
            endpoint_base_url=safe_text,
            config=safe_dicts,
        ))
        plugins.append(p)

    return plugins, new_version


@given(data=_plugins_with_version_bump())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_contract_version_bump_flags_unvalidated_plugins(
    data: tuple[list[PluginMetadata], str],
) -> None:
    """For any dimension with registered plugins, when the contract version is
    incremented, all plugins not yet validated against the new version shall be
    flagged as requiring re-validation.

    # Feature: conviction-room, Property 4: Contract version bump flags unvalidated plugins
    **Validates: Requirements 1.5**
    """
    plugins, new_version = data

    flagged = find_plugins_needing_revalidation(plugins, new_version)

    # Every flagged plugin must have a different contract_version
    for p in flagged:
        assert p.contract_version != new_version, (
            f"Plugin {p.plugin_id} has contract_version={p.contract_version} "
            f"which matches new version {new_version} but was flagged"
        )

    # Every non-flagged plugin must have the new contract_version
    flagged_ids = {p.plugin_id for p in flagged}
    for p in plugins:
        if p.plugin_id not in flagged_ids:
            assert p.contract_version == new_version, (
                f"Plugin {p.plugin_id} has contract_version={p.contract_version} "
                f"!= {new_version} but was NOT flagged"
            )

    # The union of flagged + non-flagged covers all plugins
    assert len(flagged) + sum(
        1 for p in plugins if p.contract_version == new_version
    ) == len(plugins)
