"""Unit tests for the DataPipelineService.

Covers: registration, query routing, normalization, failover, and fetch.
Requirements: 8.1, 8.2, 8.3, 8.5, 8.6
"""

from __future__ import annotations

import pytest

from conviction_room.models.plugin import PluginError
from conviction_room.services.data_pipeline import DataPipelineService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_query(params: dict) -> list[dict]:
    """Adapter that returns a single result."""
    return [{"content": f"result for {params.get('q', '?')}", "metadata": {"k": "v"}}]


def _ok_fetch(ref: str) -> dict:
    return {"content": f"doc-{ref}", "metadata": {"ref": ref}}


def _failing_query(params: dict) -> list[dict]:
    raise RuntimeError("adapter down")


def _failing_fetch(ref: str) -> dict:
    raise TimeoutError("adapter timeout")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegisterAdapter:
    def test_register_and_query(self):
        svc = DataPipelineService()
        svc.register_adapter("alpha", "market_data", 1, _ok_query, _ok_fetch)
        result = svc.query("market_data", {"q": "AAPL"})
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["source"] == "alpha"

    def test_priority_ordering(self):
        """Lower priority number is tried first."""
        call_order: list[str] = []

        def make_query(name: str):
            def fn(params: dict) -> list[dict]:
                call_order.append(name)
                return [{"content": name}]
            return fn

        svc = DataPipelineService()
        svc.register_adapter("low_pri", "cat", 10, make_query("low_pri"), _ok_fetch)
        svc.register_adapter("high_pri", "cat", 1, make_query("high_pri"), _ok_fetch)

        result = svc.query("cat", {})
        assert isinstance(result, list)
        # high_pri should be called first and succeed
        assert call_order == ["high_pri"]
        assert result[0]["source"] == "high_pri"


class TestQueryFailover:
    def test_failover_to_next_adapter(self):
        svc = DataPipelineService()
        svc.register_adapter("bad", "news", 1, _failing_query, _failing_fetch)
        svc.register_adapter("good", "news", 2, _ok_query, _ok_fetch)

        result = svc.query("news", {"q": "test"})
        assert isinstance(result, list)
        assert result[0]["source"] == "good"

    def test_all_adapters_fail(self):
        svc = DataPipelineService()
        svc.register_adapter("bad1", "news", 1, _failing_query, _failing_fetch)
        svc.register_adapter("bad2", "news", 2, _failing_query, _failing_fetch)
        svc.register_adapter("bad3", "news", 3, _failing_query, _failing_fetch)

        result = svc.query("news", {"q": "test"})
        assert isinstance(result, PluginError)
        assert result.error_code == "ALL_ADAPTERS_FAILED"

    def test_no_adapters_registered(self):
        svc = DataPipelineService()
        result = svc.query("unknown", {})
        assert isinstance(result, PluginError)
        assert result.error_code == "NO_ADAPTER"

    def test_max_failover_attempts_respected(self):
        """Only MAX_FAILOVER_ATTEMPTS failover attempts are made."""
        call_count = 0

        def counting_fail(params: dict) -> list[dict]:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        svc = DataPipelineService()
        for i in range(5):
            svc.register_adapter(f"bad{i}", "cat", i, counting_fail, _failing_fetch)

        result = svc.query("cat", {})
        assert isinstance(result, PluginError)
        # 1 initial + 2 failover = 3 total attempts max
        assert call_count <= 3


class TestFetch:
    def test_fetch_success(self):
        svc = DataPipelineService()
        svc.register_adapter("alpha", "market_data", 1, _ok_query, _ok_fetch)

        result = svc.fetch("market_data", "doc123")
        assert isinstance(result, dict)
        assert result["source"] == "alpha"
        assert "doc123" in result["content"]

    def test_fetch_failover(self):
        svc = DataPipelineService()
        svc.register_adapter("bad", "filings", 1, _ok_query, _failing_fetch)
        svc.register_adapter("good", "filings", 2, _ok_query, _ok_fetch)

        result = svc.fetch("filings", "ref1")
        assert isinstance(result, dict)
        assert result["source"] == "good"

    def test_fetch_no_adapter(self):
        svc = DataPipelineService()
        result = svc.fetch("unknown", "ref")
        assert isinstance(result, PluginError)
        assert result.error_code == "NO_ADAPTER"


class TestNormalize:
    def test_basic_normalization(self):
        raw = {"content": "hello", "metadata": {"k": 1}, "tags": ["finance"]}
        item = DataPipelineService.normalize_to_evidence_item(raw, "my_adapter")
        assert item["source"] == "my_adapter"
        assert item["content"] == "hello"
        assert item["metadata"] == {"k": 1}
        assert "my_adapter" in item["tags"]
        assert "finance" in item["tags"]

    def test_missing_fields_default(self):
        raw = {}
        item = DataPipelineService.normalize_to_evidence_item(raw, "adapter_x")
        assert item["source"] == "adapter_x"
        assert item["content"] == ""
        assert item["metadata"] == {}
        assert item["tags"] == ["adapter_x"]

    def test_non_string_content_coerced(self):
        raw = {"content": 42}
        item = DataPipelineService.normalize_to_evidence_item(raw, "a")
        assert item["content"] == "42"

    def test_non_dict_metadata_wrapped(self):
        raw = {"metadata": "flat_value"}
        item = DataPipelineService.normalize_to_evidence_item(raw, "a")
        assert item["metadata"] == {"raw": "flat_value"}

    def test_adapter_tag_not_duplicated(self):
        raw = {"tags": ["my_adapter"]}
        item = DataPipelineService.normalize_to_evidence_item(raw, "my_adapter")
        assert item["tags"].count("my_adapter") == 1
