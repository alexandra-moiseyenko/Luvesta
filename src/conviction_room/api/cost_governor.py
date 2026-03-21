"""Cost Governor FastAPI routes.

Exposes endpoints for budget management, cost ledger queries,
pre-flight budget checks, and cost recording.

Requirements: 7.2, 7.5
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from conviction_room.models.cost import CostBudget, CostRecord, CostSummary
from conviction_room.models.plugin import PluginError
from conviction_room.services.cost_governor import CostGovernorService

router = APIRouter(prefix="/cost", tags=["cost-governor"])

# Module-level service instance
_cost_service = CostGovernorService()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class BudgetCheckRequest(BaseModel):
    """Request body for POST /cost/check."""

    dimension: str
    estimated_cost: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _error_response(error: PluginError) -> dict:
    """Convert a PluginError to a serialisable dict."""
    return error.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/budget")
def get_all_budgets() -> list[CostBudget]:
    """Return all current budgets."""
    return list(_cost_service._budgets.values())


@router.get("/budget/{scope}")
def get_budget(
    scope: str,
    dimension: str | None = Query(default=None),
    period: str | None = Query(default=None),
) -> CostBudget:
    """Return the budget for a specific scope."""
    budget = _cost_service.get_budget(scope, dimension=dimension, period=period)
    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.put("/budget/{scope}")
def set_budget(scope: str, budget: CostBudget) -> CostBudget:
    """Set or update a budget for the given scope."""
    if budget.scope != scope:
        raise HTTPException(
            status_code=400,
            detail=f"Scope in URL ({scope}) does not match body ({budget.scope})",
        )
    return _cost_service.set_budget(budget)


@router.get("/ledger")
def get_ledger(
    dimension: str | None = Query(default=None),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
) -> list[CostRecord]:
    """Query cost ledger entries with optional filters."""
    return _cost_service.get_ledger(
        dimension=dimension,
        from_time=from_time,
        to_time=to_time,
    )


@router.post("/check")
def check_budget(body: BudgetCheckRequest) -> dict:
    """Pre-flight budget check.

    Returns ``{"approved": true}`` if the estimated cost is within budget,
    or raises HTTP 403 with the budget-exceeded error details.
    """
    error = _cost_service.check_budget(body.dimension, body.estimated_cost)
    if error is not None:
        raise HTTPException(status_code=403, detail=_error_response(error))
    return {"approved": True}


@router.post("/record", status_code=201)
def record_cost(record: CostRecord) -> CostRecord:
    """Record an invocation cost entry in the ledger."""
    return _cost_service.record_cost(record)
