# Feature: conviction-room, Property 1: Domain object JSON round-trip
"""
Property test: for any valid domain object, serializing to JSON via
.model_dump_json() and deserializing via .model_validate_json() produces
an equivalent object.

**Validates: Requirements 1.7, 5.4, 8.7, 9.8**
"""

from typing import Any

from hypothesis import HealthCheck, given, settings

from tests.conftest import all_domain_objects_st


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@given(obj=all_domain_objects_st)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_domain_object_json_roundtrip(obj: Any) -> None:
    """For any valid domain object, serializing to JSON and deserializing back
    produces an equivalent object.

    # Feature: conviction-room, Property 1: Domain object JSON round-trip
    **Validates: Requirements 1.7, 5.4, 8.7, 9.8**
    """
    json_str = obj.model_dump_json()
    restored = type(obj).model_validate_json(json_str)
    assert restored == obj, (
        f"Round-trip failed for {type(obj).__name__}: {obj!r} != {restored!r}"
    )
