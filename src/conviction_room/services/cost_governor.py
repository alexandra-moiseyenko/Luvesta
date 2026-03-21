"""Cost Governor service for Conviction Room.

Tracks token usage, API call count, and estimated dollar cost for every
plugin invocation and benchmark run.  Enforces budget ceilings, emits
80 % threshold warnings, and exposes ledger / summary queries.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from conviction_room.models.cost import CostBudget, CostRecord, CostSummary
from conviction_room.models.plugin import PluginError

logger = logging.getLogger(__name__)

# Rough heuristic: 1 token ≈ 4 bytes of payload.
_BYTES_PER_TOKEN_ESTIMATE = 4


class CostGovernorService:
    """In-memory cost governance.

    Stores budgets and ledger entries in plain dicts/lists and provides
    pre-flight budget checks, cost recording, and summary queries.
    """

    def __init__(self) -> None:
        # Budget storage keyed by (scope, dimension, period).
        # dimension and period may be None depending on scope.
        self._budgets: dict[tuple[str, str | None, str | None], CostBudget] = {}

        # Ordered list of all cost ledger entries.
        self._ledger: list[CostRecord] = []

        # Warning events emitted when spend crosses 80 % of a budget.
        # Each entry is a dict with budget key + details for testability.
        self.warning_events: list[dict[str, Any]] = []

        # Track which budget keys have already fired the 80 % warning
        # so we emit it at most once per budget.
        self._warned_keys: set[tuple[str, str | None, str | None]] = set()

    # ------------------------------------------------------------------
    # Budget key helper
    # ------------------------------------------------------------------

    @staticmethod
    def _budget_key(
        scope: str,
        dimension: str | None = None,
        period: str | None = None,
    ) -> tuple[str, str | None, str | None]:
        return (scope, dimension, period)

    # ------------------------------------------------------------------
    # set_budget
    # ------------------------------------------------------------------

    def set_budget(self, budget: CostBudget) -> CostBudget:
        """Set or update a budget.  Returns the stored budget."""
        key = self._budget_key(budget.scope, budget.dimension, budget.period)
        self._budgets[key] = budget
        # Reset warning flag when budget is (re)set.
        self._warned_keys.discard(key)
        return budget

    # ------------------------------------------------------------------
    # get_budget
    # ------------------------------------------------------------------

    def get_budget(
        self,
        scope: str,
        dimension: str | None = None,
        period: str | None = None,
    ) -> CostBudget | None:
        """Return the budget for the given scope, or ``None``."""
        return self._budgets.get(self._budget_key(scope, dimension, period))

    # ------------------------------------------------------------------
    # check_budget
    # ------------------------------------------------------------------

    def check_budget(
        self,
        dimension: str,
        estimated_cost: float,
    ) -> PluginError | None:
        """Pre-flight budget check.

        Iterates over all applicable budgets for *dimension* and rejects
        the invocation if the estimated cost would push spend over the
        ceiling.  Also emits a warning event when spend crosses 80 %.

        Returns ``None`` if the invocation is approved, or a
        ``PluginError`` with ``error_code="BUDGET_EXCEEDED"`` otherwise.
        """
        for key, budget in self._budgets.items():
            if not self._budget_applies(key, dimension):
                continue

            current_spend = self._current_spend_for_budget(key)

            # 80 % warning (emit before rejection check so we warn even
            # on the call that will be rejected).
            self._maybe_emit_warning(key, budget, current_spend + estimated_cost)

            if current_spend + estimated_cost > budget.max_dollar_cost:
                return PluginError(
                    error_code="BUDGET_EXCEEDED",
                    message=(
                        f"Estimated cost ${estimated_cost:.4f} would exceed "
                        f"budget for scope={budget.scope} "
                        f"(current=${current_spend:.4f}, "
                        f"ceiling=${budget.max_dollar_cost:.4f})"
                    ),
                    dimension=dimension,
                )

        return None

    # ------------------------------------------------------------------
    # record_cost
    # ------------------------------------------------------------------

    def record_cost(self, record: CostRecord) -> CostRecord:
        """Record a cost ledger entry.

        If the plugin did not report token usage (``token_count == 0``),
        estimate from ``dollar_cost`` using a rough heuristic and set
        ``is_estimated = True``.
        """
        if record.token_count == 0:
            # Estimate tokens from dollar cost (very rough: $0.002 / 1K tokens).
            estimated_tokens = max(1, int(record.dollar_cost / 0.000002))
            record = record.model_copy(
                update={"token_count": estimated_tokens, "is_estimated": True},
            )
            logger.warning(
                "Plugin %s did not report token usage for dimension '%s'; "
                "estimated %d tokens (is_estimated=True)",
                record.plugin_id,
                record.dimension,
                estimated_tokens,
            )

        self._ledger.append(record)

        # Check 80 % warnings after recording.
        for key, budget in self._budgets.items():
            if self._budget_applies(key, record.dimension):
                spend = self._current_spend_for_budget(key)
                self._maybe_emit_warning(key, budget, spend)

        return record

    # ------------------------------------------------------------------
    # get_ledger
    # ------------------------------------------------------------------

    def get_ledger(
        self,
        dimension: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> list[CostRecord]:
        """Query cost ledger entries with optional filters."""
        results: list[CostRecord] = []
        for entry in self._ledger:
            if dimension is not None and entry.dimension != dimension:
                continue
            if from_time is not None and entry.timestamp < from_time:
                continue
            if to_time is not None and entry.timestamp > to_time:
                continue
            results.append(entry)
        return results

    # ------------------------------------------------------------------
    # get_summary
    # ------------------------------------------------------------------

    def get_summary(
        self,
        scope: str,
        dimension: str | None = None,
        period: str | None = None,
    ) -> CostSummary | PluginError:
        """Return a ``CostSummary`` for the given scope.

        Invariants:
        - ``current_spend + remaining_budget == total_ceiling``
        - ``sum(breakdown_by_dimension.values()) == current_spend``
        - ``sum(breakdown_by_plugin.values()) == current_spend``
        """
        key = self._budget_key(scope, dimension, period)
        budget = self._budgets.get(key)
        if budget is None:
            return PluginError(
                error_code="BUDGET_NOT_FOUND",
                message=f"No budget found for scope={scope}, dimension={dimension}, period={period}",
            )

        current_spend = self._current_spend_for_budget(key)
        remaining = max(0.0, budget.max_dollar_cost - current_spend)

        # Build breakdowns.
        by_dimension: dict[str, float] = {}
        by_plugin: dict[str, float] = {}
        for entry in self._ledger:
            if not self._budget_applies(key, entry.dimension):
                continue
            by_dimension[entry.dimension] = (
                by_dimension.get(entry.dimension, 0.0) + entry.dollar_cost
            )
            pid = str(entry.plugin_id)
            by_plugin[pid] = by_plugin.get(pid, 0.0) + entry.dollar_cost

        # Simple linear projection: if we've spent X so far, project
        # the same rate for the remaining budget window.  For simplicity
        # projected_spend == current_spend (no time-window info stored).
        projected_spend = current_spend

        return CostSummary(
            scope=scope,
            current_spend=current_spend,
            remaining_budget=remaining,
            projected_spend=projected_spend,
            breakdown_by_dimension=by_dimension,
            breakdown_by_plugin=by_plugin,
        )

    # ==================================================================
    # Private helpers
    # ==================================================================

    def _budget_applies(
        self,
        key: tuple[str, str | None, str | None],
        dimension: str,
    ) -> bool:
        """Return True if the budget identified by *key* applies to *dimension*."""
        scope, budget_dim, _period = key
        if scope == "global_period":
            return True
        if scope == "dimension_period":
            return budget_dim == dimension
        if scope == "benchmark_run":
            # benchmark_run budgets apply to the specific dimension.
            return budget_dim is None or budget_dim == dimension
        return False

    def _current_spend_for_budget(
        self,
        key: tuple[str, str | None, str | None],
    ) -> float:
        """Sum dollar_cost of ledger entries that fall under *key*."""
        total = 0.0
        for entry in self._ledger:
            if self._budget_applies(key, entry.dimension):
                total += entry.dollar_cost
        return total

    def _maybe_emit_warning(
        self,
        key: tuple[str, str | None, str | None],
        budget: CostBudget,
        spend: float,
    ) -> None:
        """Emit a warning event if *spend* crosses 80 % of the budget ceiling."""
        threshold = budget.max_dollar_cost * 0.8
        if spend >= threshold and key not in self._warned_keys:
            self._warned_keys.add(key)
            event = {
                "type": "BUDGET_WARNING_80_PERCENT",
                "scope": budget.scope,
                "dimension": budget.dimension,
                "period": budget.period,
                "current_spend": spend,
                "ceiling": budget.max_dollar_cost,
                "threshold_pct": 0.8,
                "timestamp": datetime.utcnow().isoformat(),
            }
            self.warning_events.append(event)
            logger.warning(
                "Cost warning: spend $%.4f has crossed 80%% of $%.4f ceiling "
                "for scope=%s dimension=%s",
                spend,
                budget.max_dollar_cost,
                budget.scope,
                budget.dimension,
            )
