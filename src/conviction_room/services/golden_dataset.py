"""Golden Dataset management service for Conviction Room.

Manages curated, versioned golden datasets used for deterministic plugin
validation and regression testing.  Datasets are stored in-memory and
validated for required edge-case tags on creation.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from conviction_room.models.golden import GoldenDataset, GoldenDatasetEntry
from conviction_room.models.plugin import PluginError

# Tags that every golden dataset must include at least one entry for.
REQUIRED_EDGE_CASE_TAGS: set[str] = frozenset(
    {"empty_input", "max_size", "malformed_input", "known_failure_mode"}
)


class GoldenDatasetService:
    """In-memory golden dataset store.

    Stores datasets in a ``dict[UUID, GoldenDataset]`` and provides
    create, get, update (versioned), list, and schema-validation methods.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, GoldenDataset] = {}

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------

    def create(self, dataset: GoldenDataset) -> GoldenDataset | PluginError:
        """Store a new golden dataset.

        Validates that the dataset contains at least one entry tagged with
        each of the required edge-case tags (``empty_input``, ``max_size``,
        ``malformed_input``, ``known_failure_mode``).  Returns a
        ``PluginError`` if any required tags are missing.
        """
        missing = self._check_required_tags(dataset)
        if missing:
            return PluginError(
                error_code="MISSING_REQUIRED_TAGS",
                message="Golden dataset is missing required edge-case tags",
                dimension=dataset.dimension,
                details=[f"Missing tag: {tag}" for tag in sorted(missing)],
            )

        self._store[dataset.dataset_id] = dataset
        return dataset

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------

    def get(self, dataset_id: UUID) -> GoldenDataset | None:
        """Return a golden dataset by ID, or ``None`` if not found."""
        return self._store.get(dataset_id)

    # ------------------------------------------------------------------
    # update  (version increment, prior version retained)
    # ------------------------------------------------------------------

    def update(
        self,
        dataset_id: UUID,
        new_entries: list[GoldenDatasetEntry],
    ) -> GoldenDataset | PluginError:
        """Create a new version of an existing dataset.

        Increments the version number, sets ``prior_version_id`` to the
        original dataset's ID, and stores the new dataset alongside the
        old one (which is retained for regression comparison).

        Returns the new ``GoldenDataset`` or a ``PluginError`` if the
        original dataset is not found.
        """
        original = self._store.get(dataset_id)
        if original is None:
            return PluginError(
                error_code="DATASET_NOT_FOUND",
                message=f"Golden dataset {dataset_id} not found",
                details=[],
            )

        new_dataset = GoldenDataset(
            dataset_id=uuid4(),
            dimension=original.dimension,
            version=original.version + 1,
            entries=new_entries,
            created_at=datetime.utcnow(),
            prior_version_id=original.dataset_id,
        )

        self._store[new_dataset.dataset_id] = new_dataset
        return new_dataset

    # ------------------------------------------------------------------
    # list_datasets
    # ------------------------------------------------------------------

    def list_datasets(
        self, dimension: str | None = None,
    ) -> list[GoldenDataset]:
        """List all datasets, optionally filtered by dimension."""
        if dimension is None:
            return list(self._store.values())
        return [
            ds for ds in self._store.values() if ds.dimension == dimension
        ]

    # ------------------------------------------------------------------
    # validate_entry_against_schema
    # ------------------------------------------------------------------

    @staticmethod
    def validate_entry_against_schema(
        entry: GoldenDatasetEntry,
        schema: dict,
    ) -> list[str]:
        """Validate that *entry.input_payload* conforms to *schema*.

        For simplicity, checks that all ``required`` keys listed in the
        JSON schema are present in the payload.  Returns a list of
        violation strings (empty means valid).
        """
        violations: list[str] = []
        required_keys: list[str] = schema.get("required", [])
        for key in required_keys:
            if key not in entry.input_payload:
                violations.append(
                    f"Missing required key '{key}' in input_payload"
                )
        return violations

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_required_tags(dataset: GoldenDataset) -> set[str]:
        """Return the set of required edge-case tags not covered by any entry."""
        present_tags: set[str] = set()
        for entry in dataset.entries:
            present_tags.update(entry.tags)
        return REQUIRED_EDGE_CASE_TAGS - present_tags
