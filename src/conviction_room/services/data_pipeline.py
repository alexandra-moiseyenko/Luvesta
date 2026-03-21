"""Data Pipeline service for Conviction Room.

Manages data provider adapters, routes queries to the appropriate adapter
by source category and priority, normalizes all responses to the
EvidenceItem schema, and implements failover on adapter errors.

Requirements: 8.1, 8.2, 8.3, 8.5, 8.6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from conviction_room.models.plugin import PluginError

# Maximum number of failover attempts when an adapter errors/times out.
MAX_FAILOVER_ATTEMPTS = 2


@dataclass
class AdapterEntry:
    """Internal record for a registered data provider adapter."""

    name: str
    source_category: str
    priority: int  # lower number = higher priority
    query_fn: Callable[[dict], list[dict]]
    fetch_fn: Callable[[str], dict]


class DataPipelineService:
    """In-memory data pipeline that routes queries through registered adapters.

    Adapters are grouped by *source_category* and ordered by *priority*.
    On query, the pipeline tries the highest-priority adapter first and
    falls over to the next one on error (up to ``MAX_FAILOVER_ATTEMPTS``).
    All results are normalized to the EvidenceItem schema.
    """

    def __init__(self) -> None:
        # source_category -> sorted list of AdapterEntry (by priority asc)
        self._adapters: dict[str, list[AdapterEntry]] = {}

    # ------------------------------------------------------------------
    # register_adapter
    # ------------------------------------------------------------------

    def register_adapter(
        self,
        name: str,
        source_category: str,
        priority: int,
        query_fn: Callable[[dict], list[dict]],
        fetch_fn: Callable[[str], dict],
    ) -> None:
        """Register a data provider adapter.

        Parameters
        ----------
        name:
            Human-readable adapter identifier (e.g. ``"alpha_vantage"``).
        source_category:
            The category this adapter serves (e.g. ``"market_data"``).
        priority:
            Numeric priority — lower values are tried first.
        query_fn:
            ``(query_params: dict) -> list[dict]`` — search for data.
        fetch_fn:
            ``(ref: str) -> dict`` — fetch a specific document.
        """
        entry = AdapterEntry(
            name=name,
            source_category=source_category,
            priority=priority,
            query_fn=query_fn,
            fetch_fn=fetch_fn,
        )
        bucket = self._adapters.setdefault(source_category, [])
        bucket.append(entry)
        # Keep sorted by priority (ascending — lowest number first).
        bucket.sort(key=lambda e: e.priority)

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------

    def query(
        self,
        source_category: str,
        query_params: dict,
    ) -> list[dict] | PluginError:
        """Query data from the highest-priority adapter for *source_category*.

        On adapter error, fails over to the next-priority adapter (up to
        ``MAX_FAILOVER_ATTEMPTS`` total failover attempts).  All raw
        results are normalized to the EvidenceItem schema.

        Returns a list of EvidenceItem dicts on success, or a
        ``PluginError`` if all adapters fail.
        """
        adapters = self._adapters.get(source_category)
        if not adapters:
            return PluginError(
                error_code="NO_ADAPTER",
                message=f"No adapters registered for source category '{source_category}'",
                details=[],
            )

        last_error: Exception | None = None
        attempts = 0

        for adapter in adapters:
            if attempts > MAX_FAILOVER_ATTEMPTS:
                break
            try:
                raw_results = adapter.query_fn(query_params)
                return [
                    self.normalize_to_evidence_item(item, adapter.name)
                    for item in raw_results
                ]
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                attempts += 1

        return PluginError(
            error_code="ALL_ADAPTERS_FAILED",
            message=(
                f"All adapters for '{source_category}' failed after "
                f"{attempts} attempt(s)"
            ),
            details=[str(last_error)] if last_error else [],
        )

    # ------------------------------------------------------------------
    # fetch
    # ------------------------------------------------------------------

    def fetch(
        self,
        source_category: str,
        ref: str,
    ) -> dict | PluginError:
        """Fetch a specific document via the highest-priority adapter.

        Uses the same failover logic as :meth:`query`.
        """
        adapters = self._adapters.get(source_category)
        if not adapters:
            return PluginError(
                error_code="NO_ADAPTER",
                message=f"No adapters registered for source category '{source_category}'",
                details=[],
            )

        last_error: Exception | None = None
        attempts = 0

        for adapter in adapters:
            if attempts > MAX_FAILOVER_ATTEMPTS:
                break
            try:
                raw = adapter.fetch_fn(ref)
                return self.normalize_to_evidence_item(raw, adapter.name)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                attempts += 1

        return PluginError(
            error_code="ALL_ADAPTERS_FAILED",
            message=(
                f"All adapters for '{source_category}' failed after "
                f"{attempts} attempt(s)"
            ),
            details=[str(last_error)] if last_error else [],
        )

    # ------------------------------------------------------------------
    # normalize_to_evidence_item
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_to_evidence_item(raw_response: dict, adapter_name: str) -> dict:
        """Normalize a raw provider response to the EvidenceItem schema.

        EvidenceItem schema::

            {
                "source": str,       # adapter name
                "content": str,      # main content
                "metadata": dict,    # additional metadata from provider
                "tags": list[str]    # tags including adapter name
            }

        The method extracts ``content`` and ``metadata`` from the raw
        response, falling back to sensible defaults when keys are absent.
        The adapter name is always included in ``tags``.
        """
        content = raw_response.get("content", "")
        if not isinstance(content, str):
            content = str(content)

        metadata = raw_response.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {"raw": metadata}

        existing_tags: list[str] = raw_response.get("tags", [])
        if not isinstance(existing_tags, list):
            existing_tags = []

        tags = list(existing_tags)
        if adapter_name not in tags:
            tags.append(adapter_name)

        return {
            "source": adapter_name,
            "content": content,
            "metadata": metadata,
            "tags": tags,
        }
