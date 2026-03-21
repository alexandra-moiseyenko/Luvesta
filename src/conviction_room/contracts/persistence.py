"""Persistence dimension plugin contract (Dimension 12).

Endpoints: CRUD + query for each core entity:
  ResearchRequest, EvidenceItem, Claim, FinalReport, TrackedThesis

Pattern per entity:
  POST   /{entity}         — create
  GET    /{entity}/{id}    — read
  PUT    /{entity}/{id}    — update
  DELETE /{entity}/{id}    — delete
  POST   /{entity}/query   — query

Requirements: 10.5
"""

from __future__ import annotations

from conviction_room.contracts.base import (
    ContractConstraints,
    ContractSchemas,
    Endpoint,
    LifecycleHooks,
    PluginContractBase,
)

CORE_ENTITIES = [
    "research_request",
    "evidence_item",
    "claim",
    "final_report",
    "tracked_thesis",
]


def _entity_endpoints(entity: str) -> list[Endpoint]:
    """Generate CRUD + query endpoints for a single entity."""
    return [
        Endpoint(
            name=f"create_{entity}",
            method="POST",
            path=f"/{entity}",
            request_schema={"type": "object", "description": f"Create {entity}"},
            response_schema={"type": "object", "description": entity},
            error_schema={"type": "object"},
        ),
        Endpoint(
            name=f"read_{entity}",
            method="GET",
            path=f"/{entity}/{{id}}",
            request_schema={},
            response_schema={"type": "object", "description": entity},
            error_schema={"type": "object"},
        ),
        Endpoint(
            name=f"update_{entity}",
            method="PUT",
            path=f"/{entity}/{{id}}",
            request_schema={"type": "object", "description": f"Update {entity}"},
            response_schema={"type": "object", "description": entity},
            error_schema={"type": "object"},
        ),
        Endpoint(
            name=f"delete_{entity}",
            method="DELETE",
            path=f"/{entity}/{{id}}",
            request_schema={},
            response_schema={"type": "object", "description": "DeleteResult"},
            error_schema={"type": "object"},
        ),
        Endpoint(
            name=f"query_{entity}",
            method="POST",
            path=f"/{entity}/query",
            request_schema={"type": "object", "description": f"Query {entity}"},
            response_schema={"type": "array", "description": f"{entity}[]"},
            error_schema={"type": "object"},
        ),
    ]


def persistence_contract(version: str = "1.0.0") -> PluginContractBase:
    """Return a PluginContractBase for the Persistence dimension."""
    endpoints: list[Endpoint] = []
    for entity in CORE_ENTITIES:
        endpoints.extend(_entity_endpoints(entity))

    return PluginContractBase(
        version=version,
        dimension="persistence",
        endpoints=endpoints,
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
            max_response_time_ms=3000,
            max_payload_bytes=10_485_760,
            required_error_codes=["INVALID_INPUT", "TIMEOUT", "INTERNAL"],
        ),
        schemas=ContractSchemas(
            request_schema={"type": "object"},
            response_schema={"type": "object"},
            error_schema={"type": "object"},
        ),
    )
