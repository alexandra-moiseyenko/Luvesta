"""Orchestration dimension plugin contract (Dimension 6).

Endpoints:
- execute_workflow: accept a ResearchRequest, return a FinalReport
- stage_status: return current stage and progress for a job
- cancel: abort an in-progress workflow

Requirements: 10.1
"""

from __future__ import annotations

from conviction_room.contracts.base import (
    ContractConstraints,
    ContractSchemas,
    Endpoint,
    LifecycleHooks,
    PluginContractBase,
)


def orchestration_contract(version: str = "1.0.0") -> PluginContractBase:
    """Return a PluginContractBase for the Orchestration dimension."""
    return PluginContractBase(
        version=version,
        dimension="orchestration",
        endpoints=[
            Endpoint(
                name="execute_workflow",
                method="POST",
                path="/execute_workflow",
                request_schema={"type": "object", "description": "ResearchRequest"},
                response_schema={"type": "object", "description": "FinalReport"},
                error_schema={"type": "object"},
            ),
            Endpoint(
                name="stage_status",
                method="GET",
                path="/stage_status/{job_id}",
                request_schema={},
                response_schema={"type": "object", "description": "StageStatus"},
                error_schema={"type": "object"},
            ),
            Endpoint(
                name="cancel",
                method="POST",
                path="/cancel/{job_id}",
                request_schema={},
                response_schema={"type": "object", "description": "CancelResult"},
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
            max_response_time_ms=30000,
            max_payload_bytes=10_485_760,
            required_error_codes=["INVALID_INPUT", "TIMEOUT", "INTERNAL"],
        ),
        schemas=ContractSchemas(
            request_schema={"type": "object"},
            response_schema={"type": "object"},
            error_schema={"type": "object"},
        ),
    )
