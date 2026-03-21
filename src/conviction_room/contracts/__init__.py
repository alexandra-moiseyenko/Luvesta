"""Plugin contract definitions for Conviction Room."""

from conviction_room.contracts.base import (
    ContractConstraints,
    ContractSchemas,
    Endpoint,
    LifecycleHooks,
    PluginContractBase,
)
from conviction_room.contracts.context_memory import context_memory_contract
from conviction_room.contracts.data_provider import data_provider_contract
from conviction_room.contracts.model_provider import model_provider_contract
from conviction_room.contracts.orchestration import orchestration_contract
from conviction_room.contracts.persistence import persistence_contract
from conviction_room.contracts.retrieval import retrieval_contract
from conviction_room.contracts.validator import validate_plugin_against_contract

__all__ = [
    "ContractConstraints",
    "ContractSchemas",
    "Endpoint",
    "LifecycleHooks",
    "PluginContractBase",
    "context_memory_contract",
    "data_provider_contract",
    "model_provider_contract",
    "orchestration_contract",
    "persistence_contract",
    "retrieval_contract",
    "validate_plugin_against_contract",
]
