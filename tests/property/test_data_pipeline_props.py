# Feature: conviction-room, Property 29: Data pipeline normalizes to EvidenceItem schema
# Feature: conviction-room, Property 30: Data pipeline failover on adapter error
"""
Property tests for Data Pipeline service.

Property 29 — For any raw response dict and adapter name,
              normalize_to_evidence_item always returns a dict with keys
              "source", "content", "metadata", "tags".  The "source" field
              equals the adapter name.  The "tags" list always contains the
              adapter name.  "content" is always a string.  "metadata" is
              always a dict.

Property 30 — When the first adapter raises an exception, the pipeline falls
              over to the next-priority adapter and returns its results.
              When all adapters fail, a PluginError is returned with
              error_code "ALL_ADAPTERS_FAILED".

**Validates: Requirements 8.3, 8.5, 8.6**
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from conviction_room.models.plugin import PluginError
from conviction_room.services.data_pipeline import DataPipelineService
from tests.conftest import safe_text, safe_dicts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_service() -> DataPipelineService:
    """Return a new DataPipelineService with no state."""
    return DataPipelineService()


# Strategy for arbitrary raw response dicts — values can be any JSON-like type
_raw_response_values = st.one_of(
    st.text(min_size=0, max_size=50),
    st.integers(min_value=-1000, max_value=1000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.booleans(),
    st.none(),
    st.lists(st.text(min_size=0, max_size=10), max_size=3),
    st.dictionaries(
        st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L",))),
        st.text(min_size=0, max_size=10),
        max_size=3,
    ),
)

_raw_response_st = st.dictionaries(
    st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "N"))),
    _raw_response_values,
    max_size=8,
)


# ---------------------------------------------------------------------------
# Property 29: Data pipeline normalizes to EvidenceItem schema
# ---------------------------------------------------------------------------


@given(raw_response=_raw_response_st, adapter_name=safe_text)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_normalize_returns_evidence_item_schema(
    raw_response: dict,
    adapter_name: str,
) -> None:
    """For any raw response dict and adapter name, normalize_to_evidence_item
    always returns a dict with keys "source", "content", "metadata", "tags".

    # Feature: conviction-room, Property 29: Data pipeline normalizes to EvidenceItem schema
    **Validates: Requirements 8.3**
    """
    result = DataPipelineService.normalize_to_evidence_item(raw_response, adapter_name)

    # Must have exactly the four required keys
    assert "source" in result, "EvidenceItem must have 'source' key"
    assert "content" in result, "EvidenceItem must have 'content' key"
    assert "metadata" in result, "EvidenceItem must have 'metadata' key"
    assert "tags" in result, "EvidenceItem must have 'tags' key"


@given(raw_response=_raw_response_st, adapter_name=safe_text)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_normalize_source_equals_adapter_name(
    raw_response: dict,
    adapter_name: str,
) -> None:
    """The "source" field always equals the adapter name.

    # Feature: conviction-room, Property 29: Data pipeline normalizes to EvidenceItem schema
    **Validates: Requirements 8.6**
    """
    result = DataPipelineService.normalize_to_evidence_item(raw_response, adapter_name)

    assert result["source"] == adapter_name, (
        f"source should be '{adapter_name}', got '{result['source']}'"
    )


@given(raw_response=_raw_response_st, adapter_name=safe_text)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_normalize_tags_contain_adapter_name(
    raw_response: dict,
    adapter_name: str,
) -> None:
    """The "tags" list always contains the adapter name.

    # Feature: conviction-room, Property 29: Data pipeline normalizes to EvidenceItem schema
    **Validates: Requirements 8.6**
    """
    result = DataPipelineService.normalize_to_evidence_item(raw_response, adapter_name)

    assert isinstance(result["tags"], list), "tags must be a list"
    assert adapter_name in result["tags"], (
        f"tags {result['tags']} must contain adapter name '{adapter_name}'"
    )


@given(raw_response=_raw_response_st, adapter_name=safe_text)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_normalize_content_is_string(
    raw_response: dict,
    adapter_name: str,
) -> None:
    """The "content" field is always a string.

    # Feature: conviction-room, Property 29: Data pipeline normalizes to EvidenceItem schema
    **Validates: Requirements 8.3**
    """
    result = DataPipelineService.normalize_to_evidence_item(raw_response, adapter_name)

    assert isinstance(result["content"], str), (
        f"content must be a string, got {type(result['content'])}"
    )


@given(raw_response=_raw_response_st, adapter_name=safe_text)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_normalize_metadata_is_dict(
    raw_response: dict,
    adapter_name: str,
) -> None:
    """The "metadata" field is always a dict.

    # Feature: conviction-room, Property 29: Data pipeline normalizes to EvidenceItem schema
    **Validates: Requirements 8.3**
    """
    result = DataPipelineService.normalize_to_evidence_item(raw_response, adapter_name)

    assert isinstance(result["metadata"], dict), (
        f"metadata must be a dict, got {type(result['metadata'])}"
    )


# ---------------------------------------------------------------------------
# Property 30: Data pipeline failover on adapter error
# ---------------------------------------------------------------------------


@given(
    category=safe_text,
    query_params=safe_dicts,
    fallback_data=st.lists(safe_dicts, min_size=1, max_size=3),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_failover_to_next_adapter_on_error(
    category: str,
    query_params: dict,
    fallback_data: list[dict],
) -> None:
    """When the first adapter raises an exception, the pipeline falls over to
    the next-priority adapter and returns its results.

    # Feature: conviction-room, Property 30: Data pipeline failover on adapter error
    **Validates: Requirements 8.5**
    """
    svc = _fresh_service()

    # First adapter always raises
    def failing_query(params: dict) -> list[dict]:
        raise RuntimeError("primary adapter down")

    def failing_fetch(ref: str) -> dict:
        raise RuntimeError("primary adapter down")

    # Second adapter returns fallback_data
    def fallback_query(params: dict) -> list[dict]:
        return fallback_data

    def fallback_fetch(ref: str) -> dict:
        return fallback_data[0]

    svc.register_adapter(
        name="primary",
        source_category=category,
        priority=1,
        query_fn=failing_query,
        fetch_fn=failing_fetch,
    )
    svc.register_adapter(
        name="fallback",
        source_category=category,
        priority=2,
        query_fn=fallback_query,
        fetch_fn=fallback_fetch,
    )

    result = svc.query(category, query_params)

    # Should NOT be a PluginError — the fallback should have succeeded
    assert not isinstance(result, PluginError), (
        f"Expected successful fallback, got error: {result}"
    )
    assert isinstance(result, list)
    assert len(result) == len(fallback_data)

    # Each result should be normalized with the fallback adapter name
    for item in result:
        assert item["source"] == "fallback"
        assert "fallback" in item["tags"]


@given(
    category=safe_text,
    query_params=safe_dicts,
    num_adapters=st.integers(min_value=1, max_value=4),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_all_adapters_fail_returns_plugin_error(
    category: str,
    query_params: dict,
    num_adapters: int,
) -> None:
    """When all adapters fail, a PluginError is returned with error_code
    "ALL_ADAPTERS_FAILED".

    # Feature: conviction-room, Property 30: Data pipeline failover on adapter error
    **Validates: Requirements 8.5**
    """
    svc = _fresh_service()

    for i in range(num_adapters):
        def make_failing_query(idx: int):
            def failing_query(params: dict) -> list[dict]:
                raise RuntimeError(f"adapter {idx} down")
            return failing_query

        def make_failing_fetch(idx: int):
            def failing_fetch(ref: str) -> dict:
                raise RuntimeError(f"adapter {idx} down")
            return failing_fetch

        svc.register_adapter(
            name=f"adapter_{i}",
            source_category=category,
            priority=i,
            query_fn=make_failing_query(i),
            fetch_fn=make_failing_fetch(i),
        )

    result = svc.query(category, query_params)

    assert isinstance(result, PluginError), (
        f"Expected PluginError when all adapters fail, got {type(result)}"
    )
    assert result.error_code == "ALL_ADAPTERS_FAILED", (
        f"Expected error_code 'ALL_ADAPTERS_FAILED', got '{result.error_code}'"
    )
