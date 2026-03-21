# Feature: conviction-room, Property 18: Golden dataset entries validate against dimension schema
# Feature: conviction-room, Property 19: Golden dataset versioning preserves history
# Feature: conviction-room, Property 20: Golden datasets include required edge cases
"""
Property tests for Golden Dataset management.

Property 18 — For any golden dataset entry, its input_payload shall validate
              against the corresponding dimension's Plugin_Contract input schema,
              and the entry shall include scenario metadata and expected output
              characteristics.
Property 19 — For any golden dataset update, the new version number shall equal
              the prior version plus one, and the prior version shall remain
              retrievable.
Property 20 — For any golden dataset, it shall contain entries tagged as:
              empty_input, maximum-size input, malformed_input, and
              known_failure_mode trigger.

**Validates: Requirements 5.2, 5.3, 5.5**
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from conviction_room.models.golden import GoldenDataset, GoldenDatasetEntry
from conviction_room.models.plugin import PluginError
from conviction_room.services.golden_dataset import (
    REQUIRED_EDGE_CASE_TAGS,
    GoldenDatasetService,
)
from tests.conftest import golden_dataset_entry_st, safe_dicts, safe_text


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _schema_and_matching_entry(draw: st.DrawFn):
    """Generate a JSON schema with required keys and an entry whose
    input_payload contains all those keys (valid case)."""
    num_keys = draw(st.integers(min_value=1, max_value=5))
    keys = draw(
        st.lists(
            st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L",))),
            min_size=num_keys,
            max_size=num_keys,
            unique=True,
        )
    )
    schema = {"required": keys}
    payload = {k: draw(safe_text) for k in keys}
    entry = GoldenDatasetEntry(
        entry_id=uuid4(),
        input_payload=payload,
        expected_output=draw(st.none() | safe_dicts),
        quality_bounds=draw(st.none() | safe_dicts),
        scenario_description=draw(safe_text),
        tags=draw(st.lists(safe_text, max_size=3)),
    )
    return schema, entry


@st.composite
def _schema_and_incomplete_entry(draw: st.DrawFn):
    """Generate a JSON schema with required keys and an entry whose
    input_payload is missing at least one required key."""
    num_keys = draw(st.integers(min_value=2, max_value=5))
    keys = draw(
        st.lists(
            st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L",))),
            min_size=num_keys,
            max_size=num_keys,
            unique=True,
        )
    )
    schema = {"required": keys}
    # Include only a strict subset of the required keys
    num_present = draw(st.integers(min_value=0, max_value=num_keys - 1))
    present_keys = keys[:num_present]
    payload = {k: draw(safe_text) for k in present_keys}
    entry = GoldenDatasetEntry(
        entry_id=uuid4(),
        input_payload=payload,
        scenario_description=draw(safe_text),
        tags=draw(st.lists(safe_text, max_size=3)),
    )
    missing_keys = set(keys) - set(present_keys)
    return schema, entry, missing_keys


def _make_dataset_with_all_tags(
    dimension: str,
    version: int = 1,
    extra_entries: list[GoldenDatasetEntry] | None = None,
) -> GoldenDataset:
    """Build a GoldenDataset that has all four required edge-case tags."""
    entries: list[GoldenDatasetEntry] = []
    for tag in sorted(REQUIRED_EDGE_CASE_TAGS):
        entries.append(
            GoldenDatasetEntry(
                entry_id=uuid4(),
                input_payload={"data": "value"},
                scenario_description=f"Edge case: {tag}",
                tags=[tag],
            )
        )
    if extra_entries:
        entries.extend(extra_entries)
    return GoldenDataset(
        dataset_id=uuid4(),
        dimension=dimension,
        version=version,
        entries=entries,
        created_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Property 18: Golden dataset entries validate against dimension schema
# ---------------------------------------------------------------------------


@given(data=_schema_and_matching_entry())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_valid_entry_has_no_violations(data: tuple) -> None:
    """validate_entry_against_schema returns no violations when the entry's
    input_payload contains all required keys from the schema.

    # Feature: conviction-room, Property 18: Golden dataset entries validate against dimension schema
    **Validates: Requirements 5.2**
    """
    schema, entry = data
    violations = GoldenDatasetService.validate_entry_against_schema(entry, schema)
    assert violations == [], (
        f"Expected no violations for a complete entry but got: {violations}"
    )


@given(data=_schema_and_incomplete_entry())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_incomplete_entry_reports_violations(data: tuple) -> None:
    """validate_entry_against_schema returns violations listing every missing
    required key when the entry's input_payload is incomplete.

    # Feature: conviction-room, Property 18: Golden dataset entries validate against dimension schema
    **Validates: Requirements 5.2**
    """
    schema, entry, missing_keys = data
    violations = GoldenDatasetService.validate_entry_against_schema(entry, schema)
    assert len(violations) == len(missing_keys), (
        f"Expected {len(missing_keys)} violations but got {len(violations)}: {violations}"
    )
    for key in missing_keys:
        assert any(key in v for v in violations), (
            f"Missing key '{key}' not mentioned in violations: {violations}"
        )


# ---------------------------------------------------------------------------
# Property 19: Golden dataset versioning preserves history
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
    new_entries=st.lists(golden_dataset_entry_st, min_size=1, max_size=3),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_versioning_increments_and_preserves_prior(
    dimension: str,
    new_entries: list[GoldenDatasetEntry],
) -> None:
    """For any golden dataset update, the new version number shall equal the
    prior version plus one, and the prior version shall remain retrievable.

    # Feature: conviction-room, Property 19: Golden dataset versioning preserves history
    **Validates: Requirements 5.3**
    """
    svc = GoldenDatasetService()

    # Create the original dataset (with all required tags)
    original = _make_dataset_with_all_tags(dimension)
    result = svc.create(original)
    assert isinstance(result, GoldenDataset), f"Create failed: {result}"

    old_version = result.version
    old_id = result.dataset_id

    # Update the dataset
    updated = svc.update(old_id, new_entries)
    assert isinstance(updated, GoldenDataset), f"Update failed: {updated}"

    # New version = old version + 1
    assert updated.version == old_version + 1, (
        f"Expected version {old_version + 1} but got {updated.version}"
    )

    # Prior version ID points to the original
    assert updated.prior_version_id == old_id, (
        f"Expected prior_version_id={old_id} but got {updated.prior_version_id}"
    )

    # The old version is still retrievable
    old_dataset = svc.get(old_id)
    assert old_dataset is not None, "Prior version should still be retrievable"
    assert old_dataset.version == old_version


# ---------------------------------------------------------------------------
# Property 20: Golden datasets include required edge cases
# ---------------------------------------------------------------------------


@given(dimension=safe_text)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_dataset_with_all_tags_accepted(dimension: str) -> None:
    """create() accepts a dataset that includes entries tagged with all four
    required edge-case tags.

    # Feature: conviction-room, Property 20: Golden datasets include required edge cases
    **Validates: Requirements 5.5**
    """
    svc = GoldenDatasetService()
    dataset = _make_dataset_with_all_tags(dimension)
    result = svc.create(dataset)
    assert isinstance(result, GoldenDataset), (
        f"Expected accepted dataset but got error: {result}"
    )


@given(
    dimension=safe_text,
    tags_to_remove=st.lists(
        st.sampled_from(sorted(REQUIRED_EDGE_CASE_TAGS)),
        min_size=1,
        max_size=len(REQUIRED_EDGE_CASE_TAGS),
        unique=True,
    ),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_dataset_missing_required_tags_rejected(
    dimension: str,
    tags_to_remove: list[str],
) -> None:
    """create() rejects a dataset that is missing one or more of the four
    required edge-case tags (empty_input, max_size, malformed_input,
    known_failure_mode).

    # Feature: conviction-room, Property 20: Golden datasets include required edge cases
    **Validates: Requirements 5.5**
    """
    svc = GoldenDatasetService()

    # Build entries that cover only the tags NOT removed
    remaining_tags = REQUIRED_EDGE_CASE_TAGS - set(tags_to_remove)
    entries: list[GoldenDatasetEntry] = []
    for tag in sorted(remaining_tags):
        entries.append(
            GoldenDatasetEntry(
                entry_id=uuid4(),
                input_payload={"data": "value"},
                scenario_description=f"Edge case: {tag}",
                tags=[tag],
            )
        )
    # Ensure at least one entry so the dataset isn't trivially empty
    if not entries:
        entries.append(
            GoldenDatasetEntry(
                entry_id=uuid4(),
                input_payload={"data": "value"},
                scenario_description="Some scenario",
                tags=["other_tag"],
            )
        )

    dataset = GoldenDataset(
        dataset_id=uuid4(),
        dimension=dimension,
        version=1,
        entries=entries,
        created_at=datetime.utcnow(),
    )

    result = svc.create(dataset)
    assert isinstance(result, PluginError), (
        f"Expected rejection for missing tags {tags_to_remove} but dataset was accepted"
    )
    assert result.error_code == "MISSING_REQUIRED_TAGS"
    # Each removed tag should be mentioned in the error details
    for tag in tags_to_remove:
        assert any(tag in detail for detail in result.details), (
            f"Removed tag '{tag}' not mentioned in error details: {result.details}"
        )
