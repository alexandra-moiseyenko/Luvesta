"""Contract validation logic for Conviction Room plugins.

Validates that a plugin satisfies its dimension's contract by checking
endpoints, health check, contract version, required error codes, and
constraints.
"""

from __future__ import annotations

from conviction_room.contracts.base import PluginContractBase
from conviction_room.models.plugin import PluginMetadata


def validate_plugin_against_contract(
    plugin: PluginMetadata,
    contract: PluginContractBase,
    plugin_endpoints: list[dict],
) -> list[str]:
    """Validate a plugin against its dimension contract.

    Args:
        plugin: The plugin's metadata.
        contract: The contract the plugin should satisfy.
        plugin_endpoints: The plugin's actual endpoint definitions. Each dict
            should have at least ``name`` and ``method`` keys.

    Returns:
        A list of violation strings. An empty list means the plugin is valid.
    """
    violations: list[str] = []

    # 1. Contract version match
    if plugin.contract_version != contract.version:
        violations.append(
            f"Contract version mismatch: plugin declares '{plugin.contract_version}' "
            f"but contract requires '{contract.version}'"
        )

    # 2. Required endpoints — check by (name, method)
    plugin_ep_set = {
        (ep.get("name", ""), ep.get("method", "").upper())
        for ep in plugin_endpoints
    }
    for required_ep in contract.endpoints:
        key = (required_ep.name, required_ep.method)
        if key not in plugin_ep_set:
            violations.append(
                f"Missing required endpoint: {required_ep.method} {required_ep.path} "
                f"(name='{required_ep.name}')"
            )

    # 3. Health check endpoint
    hc = contract.health_check
    hc_key = (hc.name, hc.method)
    if hc_key not in plugin_ep_set:
        violations.append(
            f"Missing health check endpoint: {hc.method} {hc.path} "
            f"(name='{hc.name}')"
        )

    # 4. Required error codes
    plugin_error_codes: set[str] = set()
    for ep in plugin_endpoints:
        codes = ep.get("supported_error_codes", [])
        if isinstance(codes, list):
            plugin_error_codes.update(codes)

    for code in contract.constraints.required_error_codes:
        if code not in plugin_error_codes:
            violations.append(f"Missing required error code: '{code}'")

    # 5. Constraints — check plugin-declared limits are within contract limits
    for ep in plugin_endpoints:
        ep_response_time = ep.get("max_response_time_ms")
        if ep_response_time is not None and ep_response_time > contract.constraints.max_response_time_ms:
            violations.append(
                f"Endpoint '{ep.get('name', '?')}' max_response_time_ms "
                f"({ep_response_time}) exceeds contract limit "
                f"({contract.constraints.max_response_time_ms})"
            )

        ep_payload = ep.get("max_payload_bytes")
        if ep_payload is not None and ep_payload > contract.constraints.max_payload_bytes:
            violations.append(
                f"Endpoint '{ep.get('name', '?')}' max_payload_bytes "
                f"({ep_payload}) exceeds contract limit "
                f"({contract.constraints.max_payload_bytes})"
            )

    return violations
