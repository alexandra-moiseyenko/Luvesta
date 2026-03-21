"""Unit tests for dimension-specific contract validation.

Validates: Requirements 10.6
"""

from __future__ import annotations

import uuid

import pytest

from conviction_room.contracts import (
    context_memory_contract,
    data_provider_contract,
    model_provider_contract,
    orchestration_contract,
    persistence_contract,
    retrieval_contract,
    validate_plugin_against_contract,
)
from conviction_room.contracts.base import PluginContractBase
from conviction_room.models.plugin import PluginMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plugin(dimension: str, contract_version: str) -> PluginMetadata:
    """Create a minimal PluginMetadata for the given dimension/version."""
    return PluginMetadata(
        plugin_id=uuid.uuid4(),
        dimension=dimension,
        name=f"test-{dimension}-plugin",
        version="0.1.0",
        contract_version=contract_version,
        status="inactive",
        endpoint_base_url="http://localhost:9000",
    )


def _all_endpoints_for(contract: PluginContractBase) -> list[dict]:
    """Build a plugin_endpoints list that satisfies every required endpoint + health."""
    error_codes = list(contract.constraints.required_error_codes)
    eps: list[dict] = []
    for ep in contract.endpoints:
        eps.append({
            "name": ep.name,
            "method": ep.method,
            "supported_error_codes": error_codes,
        })
    # health check
    hc = contract.health_check
    eps.append({
        "name": hc.name,
        "method": hc.method,
        "supported_error_codes": error_codes,
    })
    return eps


def _endpoints_missing_one(contract: PluginContractBase, missing_name: str) -> list[dict]:
    """Build a plugin_endpoints list that omits the endpoint with *missing_name*."""
    eps = _all_endpoints_for(contract)
    return [ep for ep in eps if ep["name"] != missing_name]


# ===================================================================
# 1. Orchestration contract
# ===================================================================

class TestOrchestrationContract:
    """Tests for the orchestration dimension contract."""

    def test_defines_all_required_endpoints(self):
        contract = orchestration_contract()
        names = {ep.name for ep in contract.endpoints}
        assert names == {"execute_workflow", "stage_status", "cancel"}

    def test_full_plugin_validates_successfully(self):
        contract = orchestration_contract()
        plugin = _make_plugin("orchestration", contract.version)
        eps = _all_endpoints_for(contract)
        violations = validate_plugin_against_contract(plugin, contract, eps)
        assert violations == []

    def test_missing_endpoint_produces_violation(self):
        contract = orchestration_contract()
        plugin = _make_plugin("orchestration", contract.version)
        eps = _endpoints_missing_one(contract, "cancel")
        violations = validate_plugin_against_contract(plugin, contract, eps)
        assert len(violations) > 0
        assert any("cancel" in v for v in violations)


# ===================================================================
# 2. Retrieval contract
# ===================================================================

class TestRetrievalContract:
    """Tests for the retrieval dimension contract."""

    def test_defines_all_required_endpoints(self):
        contract = retrieval_contract()
        names = {ep.name for ep in contract.endpoints}
        assert names == {"search", "fetch_document", "source_stats"}

    def test_full_plugin_validates_successfully(self):
        contract = retrieval_contract()
        plugin = _make_plugin("retrieval", contract.version)
        eps = _all_endpoints_for(contract)
        violations = validate_plugin_against_contract(plugin, contract, eps)
        assert violations == []

    def test_missing_endpoint_produces_violation(self):
        contract = retrieval_contract()
        plugin = _make_plugin("retrieval", contract.version)
        eps = _endpoints_missing_one(contract, "search")
        violations = validate_plugin_against_contract(plugin, contract, eps)
        assert len(violations) > 0
        assert any("search" in v for v in violations)


# ===================================================================
# 3. Model/Provider contract
# ===================================================================

class TestModelProviderContract:
    """Tests for the model/provider dimension contract."""

    def test_defines_all_required_endpoints(self):
        contract = model_provider_contract()
        names = {ep.name for ep in contract.endpoints}
        assert names == {"complete", "usage", "models"}

    def test_full_plugin_validates_successfully(self):
        contract = model_provider_contract()
        plugin = _make_plugin("model_provider", contract.version)
        eps = _all_endpoints_for(contract)
        violations = validate_plugin_against_contract(plugin, contract, eps)
        assert violations == []

    def test_missing_endpoint_produces_violation(self):
        contract = model_provider_contract()
        plugin = _make_plugin("model_provider", contract.version)
        eps = _endpoints_missing_one(contract, "complete")
        violations = validate_plugin_against_contract(plugin, contract, eps)
        assert len(violations) > 0
        assert any("complete" in v for v in violations)


# ===================================================================
# 4. Context/Memory contract
# ===================================================================

class TestContextMemoryContract:
    """Tests for the context/memory dimension contract."""

    def test_defines_all_required_endpoints(self):
        contract = context_memory_contract()
        names = {ep.name for ep in contract.endpoints}
        assert names == {"store", "retrieve", "summarize"}

    def test_full_plugin_validates_successfully(self):
        contract = context_memory_contract()
        plugin = _make_plugin("context_memory", contract.version)
        eps = _all_endpoints_for(contract)
        violations = validate_plugin_against_contract(plugin, contract, eps)
        assert violations == []

    def test_missing_endpoint_produces_violation(self):
        contract = context_memory_contract()
        plugin = _make_plugin("context_memory", contract.version)
        eps = _endpoints_missing_one(contract, "retrieve")
        violations = validate_plugin_against_contract(plugin, contract, eps)
        assert len(violations) > 0
        assert any("retrieve" in v for v in violations)


# ===================================================================
# 5. Persistence contract (25 endpoints: CRUD + query × 5 entities)
# ===================================================================

class TestPersistenceContract:
    """Tests for the persistence dimension contract."""

    ENTITIES = [
        "research_request",
        "evidence_item",
        "claim",
        "final_report",
        "tracked_thesis",
    ]

    def test_defines_all_required_endpoints(self):
        contract = persistence_contract()
        names = {ep.name for ep in contract.endpoints}
        expected = set()
        for entity in self.ENTITIES:
            for op in ("create", "read", "update", "delete", "query"):
                expected.add(f"{op}_{entity}")
        assert names == expected
        assert len(names) == 25

    def test_full_plugin_validates_successfully(self):
        contract = persistence_contract()
        plugin = _make_plugin("persistence", contract.version)
        eps = _all_endpoints_for(contract)
        violations = validate_plugin_against_contract(plugin, contract, eps)
        assert violations == []

    def test_missing_endpoint_produces_violation(self):
        contract = persistence_contract()
        plugin = _make_plugin("persistence", contract.version)
        eps = _endpoints_missing_one(contract, "create_claim")
        violations = validate_plugin_against_contract(plugin, contract, eps)
        assert len(violations) > 0
        assert any("create_claim" in v for v in violations)


# ===================================================================
# 6. Data Provider contract
# ===================================================================

class TestDataProviderContract:
    """Tests for the data provider adapter dimension contract."""

    def test_defines_all_required_endpoints(self):
        contract = data_provider_contract()
        names = {ep.name for ep in contract.endpoints}
        assert names == {"query", "fetch", "provider_health"}

    def test_full_plugin_validates_successfully(self):
        contract = data_provider_contract()
        plugin = _make_plugin("data_provider", contract.version)
        eps = _all_endpoints_for(contract)
        violations = validate_plugin_against_contract(plugin, contract, eps)
        assert violations == []

    def test_missing_endpoint_produces_violation(self):
        contract = data_provider_contract()
        plugin = _make_plugin("data_provider", contract.version)
        eps = _endpoints_missing_one(contract, "fetch")
        violations = validate_plugin_against_contract(plugin, contract, eps)
        assert len(violations) > 0
        assert any("fetch" in v for v in violations)
