"""Retrieval dimension plugin contract (Dimension 10).

Endpoints:
- search: accept a query, return ranked EvidenceItems
- fetch_document: retrieve a specific source by reference
- source_stats: return counts and quality distribution

Requirements: 10.2
"""

from __future__ import annotations

from conviction_room.contracts.base import (
    ContractConstraints,
    ContractSchemas,
    Endpoint,
    LifecycleHooks,
    PluginContractBase,
)


def retrieval_contract(version: str = "1.0.0") -> PluginContractBase:
    """Return a PluginContractBase for the Retrieval dimension."""
    return PluginContractBase(
        version=version,
        dimension="retrieval",
        endpoints=[
            Endpoint(
                name="search",
                method="POST",
                path="/search",
                request_schema={"type": "object", "description": "SearchQuery"},
                response_schema={"type": "array", "description": "EvidenceItem[]"},
                error_schema={"type": "object"},
            ),
            Endpoint(
                name="fetch_document",
                method="GET",
                path="/fetch_document/{ref}",
                request_schema={},
                response_schema={"type": "object", "description": "Document"},
                error_schema={"type": "object"},
            ),
            Endpoint(
                name="source_stats",
                method="GET",
                path="/source_stats",
                request_schema={},
                response_schema={"type": "object", "description": "SourceStats"},
                error_schema={"type": "object"},
            ),
        ],
        health_check=Endpoint(
            name="health",
            method="GET",
            path="/health",
            request_schema={},
            response_schema={"type": "object"},
            error_schema={"type": "object"},
        ),
        lifecycle_hooks=LifecycleHooks(
            init=True, warmup=True, shutdown=True, readiness=True,
        ),
        constraints=ContractConstraints(
            max_response_time_ms=5000,
            max_payload_bytes=5_242_880,
            required_error_codes=["INVALID_INPUT", "TIMEOUT", "INTERNAL"],
        ),
        schemas=ContractSchemas(
            request_schema={"type": "object"},
            response_schema={"type": "object"},
            error_schema={"type": "object"},
        ),
    )
