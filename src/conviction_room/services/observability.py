"""Observability service for Conviction Room.

Stores trace events, queries them with filters, and computes aggregate
metrics per plugin or dimension over configurable time windows.

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from uuid import UUID

from conviction_room.models.trace import AggregateMetrics, TraceEvent

# Patterns used to detect PII in error context values.
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(
    r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"
)

# Supported time-window suffixes.
_WINDOW_UNITS = {"h": "hours", "d": "days"}


def _redact_pii(value: object) -> object:
    """Replace email/phone patterns in string values with '[REDACTED]'."""
    if isinstance(value, str):
        value = _EMAIL_RE.sub("[REDACTED]", value)
        value = _PHONE_RE.sub("[REDACTED]", value)
        return value
    if isinstance(value, dict):
        return {k: _redact_pii(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_pii(item) for item in value]
    return value


def _parse_time_window(window: str) -> timedelta:
    """Parse a time-window string like '1h', '24h', '7d' into a timedelta."""
    if len(window) < 2:
        raise ValueError(f"Invalid time window: {window}")
    amount_str, unit = window[:-1], window[-1]
    if unit not in _WINDOW_UNITS:
        raise ValueError(f"Unsupported time-window unit: {unit}")
    return timedelta(**{_WINDOW_UNITS[unit]: int(amount_str)})


class ObservabilityService:
    """In-memory trace store with query and aggregation capabilities."""

    def __init__(self) -> None:
        self._traces: list[TraceEvent] = []

    # ------------------------------------------------------------------
    # emit_trace
    # ------------------------------------------------------------------

    def emit_trace(self, trace: TraceEvent) -> TraceEvent:
        """Store a trace event.

        If the invocation failed and ``error_context`` is present, PII
        (emails and phone numbers) is redacted before storage.
        """
        if not trace.success and trace.error_context is not None:
            trace = trace.model_copy(
                update={"error_context": _redact_pii(trace.error_context)},
            )
        self._traces.append(trace)
        return trace

    # ------------------------------------------------------------------
    # query_traces
    # ------------------------------------------------------------------

    def query_traces(
        self,
        dimension: str | None = None,
        plugin_id: UUID | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        success: bool | None = None,
    ) -> list[TraceEvent]:
        """Return traces matching all supplied filters."""
        results: list[TraceEvent] = []
        for t in self._traces:
            if dimension is not None and t.dimension != dimension:
                continue
            if plugin_id is not None and t.plugin_id != plugin_id:
                continue
            if from_time is not None and t.timestamp < from_time:
                continue
            if to_time is not None and t.timestamp > to_time:
                continue
            if success is not None and t.success != success:
                continue
            results.append(t)
        return results

    # ------------------------------------------------------------------
    # get_trace
    # ------------------------------------------------------------------

    def get_trace(self, trace_id: UUID) -> TraceEvent | None:
        """Return a single trace by ID, or ``None`` if not found."""
        for t in self._traces:
            if t.trace_id == trace_id:
                return t
        return None

    # ------------------------------------------------------------------
    # get_plugin_metrics
    # ------------------------------------------------------------------

    def get_plugin_metrics(
        self,
        plugin_id: UUID,
        time_window: str = "24h",
    ) -> AggregateMetrics:
        """Compute aggregate metrics for a single plugin."""
        delta = _parse_time_window(time_window)
        cutoff = datetime.utcnow() - delta

        matching = [
            t for t in self._traces
            if t.plugin_id == plugin_id and t.timestamp >= cutoff
        ]
        return self._aggregate(matching, plugin_id=plugin_id, time_window=time_window)

    # ------------------------------------------------------------------
    # get_dimension_metrics
    # ------------------------------------------------------------------

    def get_dimension_metrics(
        self,
        dimension: str,
        time_window: str = "24h",
    ) -> AggregateMetrics:
        """Compute aggregate metrics across all plugins for a dimension."""
        delta = _parse_time_window(time_window)
        cutoff = datetime.utcnow() - delta

        matching = [
            t for t in self._traces
            if t.dimension == dimension and t.timestamp >= cutoff
        ]
        # Use a zero UUID as a sentinel for dimension-level aggregation.
        sentinel_id = UUID("00000000-0000-0000-0000-000000000000")
        return self._aggregate(
            matching,
            plugin_id=sentinel_id,
            time_window=time_window,
            dimension_override=dimension,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate(
        traces: list[TraceEvent],
        *,
        plugin_id: UUID,
        time_window: str,
        dimension_override: str | None = None,
    ) -> AggregateMetrics:
        """Build ``AggregateMetrics`` from a list of traces."""
        total = len(traces)
        if total == 0:
            dimension = dimension_override or ""
            return AggregateMetrics(
                plugin_id=plugin_id,
                dimension=dimension,
                time_window=time_window,
                success_rate=0.0,
                mean_latency_ms=0.0,
                p95_latency_ms=0.0,
                mean_cost_usd=0.0,
                total_invocations=0,
            )

        successes = sum(1 for t in traces if t.success)
        latencies = sorted(t.latency_ms for t in traces)
        costs = [t.cost_usd for t in traces]

        # p95: value at the 95th-percentile index.
        p95_index = min(math.ceil(0.95 * total) - 1, total - 1)
        p95_index = max(p95_index, 0)

        dimension = dimension_override or traces[0].dimension

        return AggregateMetrics(
            plugin_id=plugin_id,
            dimension=dimension,
            time_window=time_window,
            success_rate=successes / total,
            mean_latency_ms=sum(latencies) / total,
            p95_latency_ms=latencies[p95_index],
            mean_cost_usd=sum(costs) / total,
            total_invocations=total,
        )
