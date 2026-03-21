# Conviction Room

**Conviction Room** is a modular, plugin-based architecture designed for adversarial financial research and automated AI agents. It provides a robust, swappable ecosystem where every architectural dimension of an AI agent can be plugged in, evaluated, and benchmarked independently.

Instead of a monolithic application, Conviction Room represents an advanced framework that breaks down the AI product pipeline into **19 independently swappable dimensions** (e.g., Orchestration style, Retrieval stack, Model strategy). This approach allows you to benchmark performance, track costs, and autonomously select the optimal architecture configuration using AI-testable experiments.

---

## 🚀 Core Features

### 🧩 Plugin-Based Architecture & strict Contracts
Every functionality is governed by strict, versioned OpenAPI-compatible **Plugin Contracts**. Whether it's the Orchestration layer, Retrieval, Context Memory, or Persistence, you can swap implementations (Plugins) easily without modifying the consuming code.

### 📊 Automated Benchmarking & AI-Testing
Conviction Room features a powerful **Test Harness and Benchmark Orchestrator**:
- **Fully-automatable Experiments**: Run tests comparing different LLM models or retrieval strategies. 
- **AI-driven Selection**: Compare metrics like latency, cost, and citation coverage against a Golden Dataset.
- **Auto-Promotion**: Autonomously promote winning architecture configurations to active status based on regression runs and statistical bounds.

### 💰 Cost & Token Budget Governance
An integrated **Cost Governor** ensures token usage and API costs remain strictly within defined limits per run or period. Benchmark experiments that exceed budgets are safely terminated to prevent overspending.

### 🗂️ Unified Data Pipeline & Adapters
A flexible **Data Pipeline** standardizes financial data ingestion into a universal `EvidenceItem` schema. Readily swap between Data Provider Adapters (e.g., Alpha Vantage, SEC EDGAR, Yahoo Finance) to seamlessly fall back to different sources if rate-limited.

### 🗺️ Dimension Dependency Graph
A built-in **Dependency Graph** tracks the relationships between dimensions, categorizing them into foundation, mid-tier, and leaf tiers. This ensures system stability by blocking tests if upstream requirements remain unresolved.

---

## 📚 Key Concepts

- **Dimension**: One of the 19 architecture decision areas (e.g., "Retrieval stack").
- **Plugin Registry**: Central catalog that tracks available plugins, configurations, and health statuses per Dimension.
- **Test Harness**: The infrastructure that performs contract validations, benchmark runs, and regression tests.
- **Experiment**: A structured comparison of multiple plugins within a Dimension, evaluated by metrics like `latency_p95`, `cost_per_run`, and `citation_coverage`.
- **Golden Dataset**: Curated input/output sets for reproducible, deterministic comparisons.

---

## 🛠️ Essential Subsystem Contracts

Conviction Room defines strict Plugin Contracts for its highest-priority subsystems out of the box:

1. **Orchestration**: Execute workflows, track stage progress, and cancel operations.
2. **Retrieval**: Search and retrieve ranked evidence, and track caching/source quality.
3. **Model/Provider**: Process prompts, retrieve precise token/cost usage, and list available capabilities.
4. **Context/Memory**: Store and compress contextual artifacts dynamically.
5. **Persistence**: Unified CRUD boundaries for Research Requests, Tracked Theses, and Final Reports.

---

## 🛤️ Roadmap & Automation Mode
Ultimately, Conviction Room serves as an environment that optimizes itself. By leveraging **Experiment Policies**, developers can schedule tournaments evaluating new data providers or LLMs. Metrics are gathered, and if a new option dramatically outperforms the active one within budget bounds, the framework can pivot architecture choices dynamically or propose recommendations for human review.

---

*This repository implements the spec for the Conviction Room architecture layer. The project behavior, UI/UX, and data models are defined alongside the core plugin environment.*
