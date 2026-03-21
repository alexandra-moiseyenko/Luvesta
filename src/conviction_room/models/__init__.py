"""Pydantic data models for Conviction Room."""

from conviction_room.models.automation import ExperimentPolicy
from conviction_room.models.benchmark import (
    BenchmarkRun,
    BenchmarkSuite,
    EvaluationMetric,
    Experiment,
    ExperimentResults,
    PluginScore,
)
from conviction_room.models.cost import CostBudget, CostRecord, CostSummary
from conviction_room.models.golden import GoldenDataset, GoldenDatasetEntry
from conviction_room.models.graph import DimensionGraph, DimensionNode
from conviction_room.models.plugin import PluginError, PluginMetadata
from conviction_room.models.test_report import RegressionResult, TestReport
from conviction_room.models.testability import TestabilityClassification
from conviction_room.models.trace import AggregateMetrics, TraceEvent

__all__ = [
    # plugin
    "PluginMetadata",
    "PluginError",
    # graph
    "DimensionNode",
    "DimensionGraph",
    # benchmark
    "EvaluationMetric",
    "BenchmarkSuite",
    "BenchmarkRun",
    "Experiment",
    "ExperimentResults",
    "PluginScore",
    # cost
    "CostBudget",
    "CostRecord",
    "CostSummary",
    # golden
    "GoldenDatasetEntry",
    "GoldenDataset",
    # test_report
    "TestReport",
    "RegressionResult",
    # trace
    "TraceEvent",
    "AggregateMetrics",
    # testability
    "TestabilityClassification",
    # automation
    "ExperimentPolicy",
]
