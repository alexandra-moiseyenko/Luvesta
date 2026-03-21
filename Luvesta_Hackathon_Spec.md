## Product name

**Conviction Room**

## One-line pitch

A Luffa bot + mini app that runs **adversarial due diligence** on an investment thesis: one AI agent builds the strongest bullish case, one red-team agent builds the strongest bearish case, an arbiter synthesizes the evidence into a structured memo and risk model, and the system can continue to **track thesis drift over time** and improve its own research process with a paper-trading/evaluation loop. The bot handles intake, clarification, and ongoing updates; the mini app handles rich evidence navigation, scoring, and thesis history. The Luffa bot SDK and demo support the bot-first part of this architecture, while the public Endless/Luffa docs show QR-based wallet login and component access/payment patterns you can reuse if you later add gated rooms or premium reports. ([GitHub][1])

# 1) Product goals

### Primary goal

Help a user or group make a **better-informed investment decision** by forcing the research process to be adversarial, evidence-based, and explicit about uncertainty.

### Secondary goals

Turn Luffa into the place where:

* the research request starts,

* the clarification happens,

* the report is delivered,

* the thesis is challenged,

* the thesis is tracked,

* and recurring updates arrive.

### Tertiary goal

Create a self-improving loop where the system learns whether its own research outputs were:

* well sourced,

* balanced,

* calibrated,

* and directionally useful over time.

This aligns well with Luffa’s public positioning as an encrypted social platform on Endless and with the bot SDK’s chat-driven interaction model. It also lines up with OpenAI’s public guidance that complex, ambiguous, multistep workflows often work best with a mix of reasoning models for planning/decision-making and faster GPT models for execution. ([Luffa User Guide][2])

# 2) Non-goals

This product does **not**:

* execute trades,

* promise returns,

* provide regulated financial advice,

* manage pooled funds,

* or claim that paper-trading results equal real-world performance.

That last point matters. Real-time paper trading can be a useful simulation environment, but public trading disclaimers explicitly note that hypothetical/simulated results have inherent limitations and do not represent actual trading, liquidity, or real financial risk. So the paper-trading loop here is for **evaluation and calibration**, not “proof of alpha.” ([Alpaca API Docs][3])

# 3) User roles

### Solo user

A person asks the bot to research a stock, ETF, company, sector, or theme.

### Group user

A small Luffa group or channel jointly asks for research, challenges the thesis, and subscribes to updates.

### Power user

A user who wants deep reports, repeat tracking, sector comparisons, and self-improving watchlists.

### Admin / owner

The account responsible for API budgets, research-depth limits, model/provider configuration, and tracking policies.

# 4) Core user stories

### Story A: one-shot research

The user messages the bot:

> “Research ASML for me.”

The bot replies with clarifying questions:

* stock / ETF / sector?

* research depth?

* time horizon?

* what matters most: fundamentals, valuation, sentiment, macro, moat, governance?

When enough information is available, the bot starts the research job and sends a progress message. The user can then open the mini app to see the report assemble in real time.

### Story B: adversarial thesis

The user says:

> “Give me the strongest bull and bear case for Nvidia over the next 12 months.”

The system:

* gathers sources,

* extracts key facts,

* runs bull and bear in parallel,

* runs cross-examination,

* and returns an arbiter memo plus a risk scorecard.

### Story C: challenge and iterate

After seeing the report, the user taps:

* “Red-team harder”

* “Show only primary sources”

* “What would invalidate this thesis?”

* “Compare against AMD”

* “Track this until earnings”

The bot treats those as follow-up research jobs tied to the same thesis object.

### Story D: tracked thesis

The user opts into tracking. The system performs scheduled refreshes, checks for thesis-drift events, and posts a short daily or event-based update in chat.

### Story E: evaluation loop

A tracked thesis is later evaluated:

* what happened,

* what evidence was right,

* what assumptions broke,

* whether the confidence level was calibrated,

* and how the future research pipeline should change.

# 5) Product surfaces

## A. Luffa bot

The bot is the **conversation and workflow surface**:

* intake,

* clarifying questions,

* progress updates,

* quick summaries,

* challenge actions,

* follow-up commands,

* scheduled updates.

This fits the public SDK directly: it supports `receive()`, `send_to_user()`, `send_to_group()`, `run()`, and advanced group messages with buttons, confirms, and @mentions. ([GitHub][1])

## B. Mini app / web UI

The mini app is the **visual intelligence surface**:

* full report view,

* evidence explorer,

* bull vs bear split,

* source-quality grading,

* risk score breakdown,

* confidence history,

* thesis timeline,

* tracked updates,

* optional PDF export.

The public Luffa demo already points toward this mixed architecture: a LangGraph-powered Luffa bot plus a React component for richer interaction. ([GitHub][4])

## C. Backend

Your own backend is the **real product runtime**:

* message intake handler,

* orchestration,

* tool calls,

* model routing,

* persistence,

* scheduler,

* eval loop,

* report generation,

* notifications.

The public bot SDK shows polling and handling messages, which strongly implies backend responsibility for orchestration and state is yours, not Luffa’s. The demo repo also notes that in-memory state should be moved to a database for real-world use. ([GitHub][1])

# 6) High-level architecture

## 6.1 Top-level services

### 1. Luffa Bot Service

Responsibilities:

* poll/receive messages from Luffa,

* parse commands and normal text,

* hold short conversational state,

* ask clarifying questions,

* enqueue jobs,

* return summaries and CTA buttons.

Implementation notes:

* Python service using the Luffa bot SDK.

* Uses `run()` with bounded concurrency and a deduplicated message handler.

* Handles group vs DM context separately. ([GitHub][1])

### 2. Mini App Frontend

Responsibilities:

* display live job status,

* present the final report,

* expose report controls,

* show thesis history,

* show tracked update timeline,

* optionally support premium gating or report unlocks later.

Implementation notes:

* React/JS app.

* Auth/session bootstrapped from Luffa context and/or wallet-linked login if needed.

* If you later use Endless/Luffa marketplace-like wallet flows, the public docs show QR-based login/payment patterns and 5-minute QR expiry behavior. ([docs.endless.link][5])

### 3. API Gateway / Application Server

Responsibilities:

* REST endpoints for job creation, job status, report fetch, source fetch, update history,

* webhook-like internal callbacks from worker stages,

* auth/session management,

* usage metering.

Implementation notes:

* FastAPI is the cleanest match because the public demo already uses that stack with LangGraph. ([GitHub][4])

### 4. Research Orchestrator

Responsibilities:

* build the research plan,

* choose sources,

* launch bull/bear passes,

* run synthesis and scoring,

* manage retries,

* trigger follow-up jobs.

Implementation notes:

* LangGraph-style graph orchestration is a natural fit because the public Luffa demo already uses it for tool-driven chat workflows. ([GitHub][4])

### 5. Worker / Job Runtime

Responsibilities:

* perform source retrieval,

* run model calls,

* scrape and normalize content,

* store artifacts,

* compute scores,

* schedule follow-ups.

Implementation notes:

* Background worker process.

* No need to depend on Luffa for background execution.

### 6. Persistence Layer

Responsibilities:

* users,

* chats,

* jobs,

* reports,

* sources,

* evidence nodes,

* tracked theses,

* eval history,

* cost and depth usage.

Implementation notes:

* Postgres preferred.

* Redis optional for queue/caching.

* SQLite acceptable only for a single-instance prototype.

### 7. Scheduler

Responsibilities:

* daily refreshes,

* event-based rechecks,

* report TTL expiration,

* deferred evaluation,

* “track this thesis” subscriptions.

### 8. Optional Compute Sandbox / OpenClaw Runtime

Responsibilities:

* deeper tool use,

* controlled web search / browser interaction,

* file handling,

* scheduled jobs,

* possible sub-agents.

This is optional, but OpenClaw’s public tool docs show support for exec/process, browser, web search/fetch, file I/O, message sending, cron/gateway, and sessions/sub-agents. That makes it a plausible optional runtime for your “research pod” concept if you choose to add it. ([GitHub][6])

# 7) End-to-end workflow spec

## Phase 1: intake and scoping

### Inputs

The user can initiate from:

* chat,

* mini app search bar,

* tracked-thesis page,

* compare page.

### Intake fields

The system collects:

* asset type: stock / ETF / sector / company / theme

* symbol / name / region

* research depth: quick / standard / deep / forensic

* time horizon: days / weeks / quarters / long term

* focus areas:

  * fundamentals

  * valuation

  * moat / competition

  * macro exposure

  * sentiment

  * risk

  * catalysts

  * management / governance

* optional user stance:

  * neutral

  * bullish

  * bearish

  * “stress-test my current view”

* optional comparison target

* whether to enable tracking after report

### Intake behavior

The bot should not launch research until required fields are clear enough. That’s not just product taste; OpenAI’s reasoning best-practices guide explicitly notes that reasoning models are especially good for ambiguous tasks and often ask clarifying questions before guessing. ([OpenAI Developers][7])

### Intake outputs

A normalized `ResearchRequest` object is created and stored.

---

## Phase 2: planning and source strategy

### Planner responsibilities

The planner agent converts `ResearchRequest` into:

* a source plan,

* a retrieval budget,

* a model budget,

* a time budget,

* and a workflow plan.

### Source buckets

The plan should classify sources into:

* primary sources

  * investor relations pages

  * earnings transcripts

  * filings

  * company presentations

* secondary reputable sources

  * major news

  * market commentary

  * analyst-like summaries if allowed

* weak or noisy sources

  * social sentiment

  * blogs

  * forums

* market data

  * price history

  * volatility

  * sector relative performance

  * major ratio snapshots

### Planner output

A `ResearchPlan` object:

* `entities`

* `source_targets`

* `risk_dimensions`

* `hypothesis_candidates`

* `search_queries`

* `compare_entities`

* `research_depth_budget`

* `allowed_tools`

---

## Phase 3: source collection and normalization

### Source Collector service

Responsibilities:

* fetch market data,

* fetch news/articles,

* fetch primary-source documents,

* scrape pages,

* deduplicate sources,

* classify by trust level,

* normalize into a unified evidence schema.

### Evidence schema

Each source becomes an `EvidenceItem`:

* `source_id`

* `entity`

* `source_type`

* `publisher`

* `url`

* `retrieved_at`

* `published_at`

* `trust_tier`

* `freshness_score`

* `supports_claims`

* `contradicts_claims`

* `raw_content_ref`

* `summary`

* `quoted_snippets`

* `numeric_facts`

* `tags`

### Context handling strategy

This stage should explicitly decide whether to:

* keep full content,

* keep summary only,

* keep numeric facts only,

* keep claim graph only,

* or drop low-value content.

That context-pruning logic is one of your actual differentiators.

### Storage policy

Persist:

* source metadata,

* clean extracts,

* chunk references,

* summaries,

* citations,

* embeddings if you add retrieval memory later.

Do **not** keep every raw scrape in every prompt.

---

## Phase 4: dual-agent research pass

## 4A. Bull Agent

Mission:

* build the strongest reasonable case **for** the thesis.

Outputs:

* thesis statement,

* key supporting points,

* catalysts,

* upside pathways,

* non-obvious positives,

* evidence-backed metrics,

* confidence by point,

* missing evidence.

## 4B. Bear Agent

Mission:

* build the strongest reasonable case **against** the thesis.

Outputs:

* thesis statement,

* downside scenarios,

* valuation objections,

* balance-sheet / quality concerns,

* governance / competitive / regulatory concerns,

* non-obvious negatives,

* evidence-backed metrics,

* confidence by point,

* missing evidence.

### Required constraints for both

* claims must reference evidence items,

* unsupported claims are marked explicitly,

* confidence is local to each point,

* each claim is tagged as:

  * direct evidence,

  * inferred,

  * disputed,

  * weakly supported.

This is where structured outputs matter. OpenAI’s Structured Outputs feature is explicitly designed to keep model outputs aligned to a supplied JSON schema, which is exactly what you want for claim objects, risk dimensions, source objects, and final report sections. ([OpenAI Developers][8])

---

## Phase 5: cross-examination

### Bull attacks Bear

The bull side attempts to:

* refute weak bearish arguments,

* downgrade outdated bearish evidence,

* identify overgeneralization,

* identify double-counting of risks,

* argue why the downside is already priced in.

### Bear attacks Bull

The bear side attempts to:

* expose narrative speculation,

* challenge unsupported optimism,

* identify concentration or dependency risk,

* attack overreliance on one catalyst,

* expose valuation fragility.

### Cross-exam output

A `DebateMatrix` object:

* bullish claim

* bearish rebuttal

* bullish defense

* unresolved status

* source references

* arbiter note

This is the stage that makes the product feel more like an actual decision engine and less like a summarizer.

---

## Phase 6: arbiter and risk synthesis

### Arbiter mission

Produce a single structured output that answers:

* what is the best balanced reading of the evidence?

* what are the strongest arguments on each side?

* what remains unresolved?

* what would change the conclusion?

* how risky is this thesis, and in what specific ways?

### Risk model

Instead of one magic number, the arbiter outputs a multi-axis score:

* valuation risk

* business quality risk

* leverage / liquidity risk

* governance risk

* macro sensitivity

* narrative / sentiment volatility

* catalyst dependency

* evidence-quality risk

* thesis fragility

### Final verdict types

Possible verdicts:

* strong bull but high fragility

* balanced / unclear

* cautious positive

* cautious negative

* avoid until key unknown resolves

* thesis invalidated by insufficient evidence

### Final memo structure

* one-paragraph thesis

* one-paragraph anti-thesis

* balanced verdict

* risk scorecard

* top evidence

* unresolved questions

* what to watch next

* what would falsify this thesis

* whether tracking is recommended

---

## Phase 7: report generation and delivery

### Bot output

The bot sends:

* short thesis summary

* top 3 bull points

* top 3 bear points

* overall risk posture

* buttons:

  * Open full report

  * Track thesis

  * Red-team harder

  * Compare another asset

  * Show primary sources only

The SDK supports advanced group messages with buttons, which makes this interaction style a good fit for Luffa chat UX. ([GitHub][1])

### Mini app output

The app shows:

* report header

* confidence badge

* risk wheel / score bars

* side-by-side bull vs bear panels

* evidence explorer

* timeline of source freshness

* catalyst calendar

* tracked updates feed

* evaluation history

* optional PDF export

### PDF output

Optional, not primary:

* clean exported research memo,

* citations appendix,

* “paper-trading disclaimer” if simulated outcomes are shown.

---

## Phase 8: tracking mode

### User action

The user taps “Track thesis”.

### Tracking config

User chooses:

* daily / event-based / earnings-only

* summary length

* notification cadence

* whether to rerun bull and bear fully or partially

* stop date or open-ended watch

### Tracking pipeline

Scheduler wakes:

* refresh sources,

* detect meaningful new events,

* rerun targeted research,

* compare new evidence against prior thesis,

* update risk and confidence,

* send short digest in chat,

* update mini app timeline.

### Drift detection

The system explicitly measures:

* has the bull case strengthened?

* has the bear case strengthened?

* did a key assumption break?

* did evidence quality improve or worsen?

* did confidence move without enough new evidence?

### Tracked output example

“Your tracked ASML thesis weakened today because the strongest prior bullish catalyst has slipped, while two new bearish data points appeared. Confidence dropped from 0.71 to 0.56.”

This is where the product becomes truly agentic rather than just a report generator.

---

## Phase 9: paper trading + autoresearch evaluation loop

### Purpose

Not “prove profitability.”

Purpose:

* measure calibration,

* measure thesis discipline,

* measure whether the research process is improving.

### Paper-trade object

If enabled, each thesis can create a simulated position object:

* asset

* direction

* conviction

* thesis open date

* evaluation horizon

* exit conditions

* risk warnings

* thesis invalidation triggers

### Simulation engine

A paper-trading environment can be connected or simulated. Alpaca publicly describes paper trading as a real-time simulation environment where you can test with real-time market data, reset often, and simulate end-to-end flow without routing orders to a live exchange. That is a good model for your eval loop. ([Alpaca API Docs][3])

### Evaluation dimensions

Do not optimize only for PnL. Optimize on:

* source quality

* evidence coverage

* contradiction coverage

* calibration quality

* thesis stability

* warning usefulness

* downside detection

* event anticipation

* drift-detection accuracy

### Autoresearch loop

At fixed checkpoints, the system compares:

* predicted key risks vs actual observed events

* confidence vs uncertainty realized

* what evidence mattered vs what was noise

* whether bull/bear prompts need adjustment

* whether source-weighting rules should change

* whether risk-bucket weighting should change

### Disclosure policy

Any display of simulated performance should be clearly labeled as hypothetical/simulated because public CFTC language explicitly warns that simulated results have inherent limitations, do not represent actual trading, and may fail to capture market factors like liquidity or the psychology of real risk. ([Legal Information Institute][9])

# 8) Data model

## Core entities

### User

* `user_id`

* `luffa_user_id`

* `display_name`

* `plan_tier`

* `default_preferences`

* `wallet_address` (optional)

* `created_at`

### Conversation

* `conversation_id`

* `type` (dm/group)

* `luffa_channel_id`

* `participants`

* `latest_job_id`

### ResearchRequest

* `request_id`

* `user_id`

* `conversation_id`

* `entity_name`

* `symbol`

* `asset_type`

* `depth`

* `time_horizon`

* `focus_areas`

* `initial_prompt`

* `status`

* `created_at`

### ResearchJob

* `job_id`

* `request_id`

* `state`

* `progress`

* `worker_id`

* `started_at`

* `ended_at`

* `cost_estimate`

* `actual_cost`

### EvidenceItem

* `evidence_id`

* `job_id`

* `source_type`

* `publisher`

* `url`

* `published_at`

* `trust_tier`

* `freshness_score`

* `relevance_score`

* `content_hash`

* `summary`

* `raw_blob_ref`

### Claim

* `claim_id`

* `job_id`

* `side` (bull/bear/arbiter)

* `text`

* `confidence`

* `support_type`

* `evidence_refs`

* `risk_dimension_refs`

### DebateEdge

* `edge_id`

* `from_claim_id`

* `to_claim_id`

* `relation` (supports/refutes/qualifies)

### RiskScore

* `job_id`

* `valuation`

* `quality`

* `leverage`

* `governance`

* `macro`

* `sentiment`

* `fragility`

* `evidence_quality`

* `overall`

### FinalReport

* `report_id`

* `job_id`

* `verdict`

* `summary`

* `bull_summary`

* `bear_summary`

* `arbiter_summary`

* `falsification_conditions`

* `watch_items`

* `report_json`

* `pdf_url` (optional)

### TrackedThesis

* `tracked_id`

* `report_id`

* `frequency`

* `event_rules`

* `active`

* `next_run_at`

### ThesisUpdate

* `update_id`

* `tracked_id`

* `delta_summary`

* `risk_delta`

* `confidence_delta`

* `trigger_reason`

* `created_at`

### EvalRun

* `eval_id`

* `tracked_id`

* `paper_trade_ref`

* `calibration_score`

* `outcome_summary`

* `prompt_version`

* `policy_changes`

# 9) Agent graph spec

## 9.1 Planner node

Input:

* ResearchRequest

  Output:

* ResearchPlan

## 9.2 Data fetch node

Input:

* ResearchPlan

  Output:

* MarketSnapshot + RawSourceSet

## 9.3 Source normalizer node

Input:

* RawSourceSet

  Output:

* EvidenceStore + EvidenceGraph

## 9.4 Bull node

Input:

* EvidenceStore

  Output:

* BullClaimSet

## 9.5 Bear node

Input:

* EvidenceStore

  Output:

* BearClaimSet

## 9.6 Cross-exam node

Input:

* BullClaimSet + BearClaimSet

  Output:

* DebateMatrix

## 9.7 Arbiter node

Input:

* DebateMatrix + EvidenceStore + MarketSnapshot

  Output:

* RiskScore + FinalReportDraft

## 9.8 Quality controller node

Checks:

* missing citations

* unsupported score buckets

* shallow evidence base

* duplicate claims

* stale-source overload

* inconsistent verdict vs evidence

## 9.9 Report formatter node

Input:

* FinalReportDraft

  Output:

* FinalReport JSON + UI-ready sections + optional PDF

## 9.10 Tracker node

Input:

* TrackedThesis

  Output:

* ThesisUpdate / re-run

## 9.11 Eval node

Input:

* historical thesis + subsequent outcomes + paper-trade record

  Output:

* EvalRun + prompt/rule recommendations

# 10) Model strategy

A very sensible model split is:

* **fast cheaper model** for extraction, classification, chunk triage, and low-risk summarization,

* **strong reasoning model** for planning, cross-exam, arbitration, and risk synthesis.

That is not arbitrary — OpenAI’s public reasoning guide explicitly recommends mixing GPT models for fast execution with o-series reasoning models for planning, ambiguity handling, and complex multistep decisions. ([OpenAI Developers][7])

### Recommended prompting pattern

* planner gets explicit objective + budget + schema

* fetch/normalize stages use structured outputs

* bull/bear use identical schemas to force comparability

* arbiter receives both sides plus rules for uncertainty and source weighting

* quality controller checks schema validity and support coverage

### Why structured outputs are mandatory

The mini app needs stable objects, not prose soup. OpenAI’s Structured Outputs documentation says the feature ensures model responses conform to a supplied JSON schema, supports explicit refusals, and simplifies prompting. That makes it a strong fit for your evidence items, claim objects, risk buckets, and final report sections. ([OpenAI Developers][8])

# 11) Context management spec

This is one of the most important technical parts of your idea.

## 11.1 Context layers

### Layer A: raw source cache

Full scraped/raw content stored outside prompts.

### Layer B: normalized source summaries

Short summaries plus source metadata.

### Layer C: extracted facts

Numeric facts, event facts, management statements, ratio snapshots.

### Layer D: evidence graph

Claims and edges linking support/refutation.

### Layer E: working prompt context

Only the minimum relevant subset for each node.

## 11.2 Compression policies

Each source can be:

* retained raw,

* summarized,

* fact-extracted,

* embedded only,

* or dropped.

## 11.3 Rehydration policies

If an agent encounters a weakly supported claim, it can:

* request full-source rehydration,

* request a fresh scrape,

* request additional sources,

* or mark uncertainty rather than bluff.

## 11.4 Memory policies

Persistent memory should store:

* user preferences,

* tracked theses,

* prior risk models,

* prompt versions,

* and eval outcomes,

  not giant prompt transcripts forever.

# 12) Research-depth tiers

## Quick

Goal:

* under a few minutes

* basic market snapshot

* 5–10 sources

* one bull pass

* one bear pass

* short memo

## Standard

Goal:

* fuller balanced report

* broader source set

* cross-exam

* risk scorecard

* thesis watch suggestions

## Deep

Goal:

* larger source budget

* more primary sources

* stronger cross-exam

* deeper source-quality weighting

* more detailed memo

* optional comparison target

## Forensic

Goal:

* maximum adversarial rigor

* emphasis on source trust, governance, accounting, and assumption testing

* event calendar and falsification tree

* best suited for tracked theses, not casual queries

# 13) Mini app information architecture

## Screen 1: Home / search

* search bar

* recent theses

* watchlist

* sample prompts

* research depth selector

## Screen 2: Live job

* job status

* current stage

* source count

* estimated cost band

* partial outputs as they arrive

## Screen 3: Final report

* thesis verdict banner

* confidence summary

* risk score bars

* bull column

* bear column

* arbiter summary

* watch items

* buttons for next actions

## Screen 4: Evidence explorer

* source list with filters

* primary vs secondary toggle

* freshness slider

* trust-tier filter

* click into claim-to-source mapping

## Screen 5: Debate view

* bull claim

* bear rebuttal

* arbiter note

* unresolved questions

## Screen 6: Tracking view

* timeline of updates

* confidence drift

* risk drift

* event markers

* compare current vs original thesis

## Screen 7: Eval / paper-trade view

* hypothetical position info

* outcome vs thesis

* calibration notes

* what the system learned

# 14) Chat UX spec

## Commands

* `/research <symbol/company/theme>`

* `/compare <a> vs <b>`

* `/track <symbol>`

* `/redteam <symbol>`

* `/sources <symbol>`

* `/thesis <tracked_id>`

* `/stoptracking <tracked_id>`

## Buttons

The SDK supports button-based advanced messages, so the chat UX should rely heavily on them. ([GitHub][1])

Suggested buttons:

* Start research

* Quick / Standard / Deep

* Bull only

* Bear only

* Full debate

* Open report

* Track thesis

* Compare

* Red-team again

## Group behavior

In a group:

* the bot addresses the requester,

* posts a condensed summary,

* allows other users to challenge or request follow-ups,

* preserves the thesis as a shared room artifact.

# 15) Security and privacy spec

Luffa publicly describes itself as an end-to-end encrypted social platform on Endless and says message content remains inaccessible to intermediary nodes, including the platform itself, during transmission. That is a strong messaging/privacy story at the transport/platform layer. But once your bot processes content and stores research state on your backend, **your app** becomes responsible for retention, redaction, and access control. ([Luffa User Guide][2])

## Policies

* store minimum necessary user text

* encrypt sensitive report artifacts at rest

* separate chat metadata from report contents

* optionally allow “ephemeral mode” where full report artifacts expire

* redact personal identifiers from stored prompts when possible

* let users delete tracked theses and their history

# 16) Optional Luffa / Endless business extensions

If you later want a stronger LuffaNation/business angle without changing the core product, there are several plausible add-ons.

## Premium reports / premium rooms

The Endless component marketplace docs describe QR-based login, component purchase, API-key-based access, HTTP component routing, and MCP/SSE component invocation patterns. That gives you a template for packaging the research engine as a purchasable component or gated service later. ([docs.endless.link][5])

## Sponsored premium actions

Endless supports sponsored contract functions at the contract level, where the contract can pay gas for a transaction; the docs also warn that access control is crucial and sponsored functions should be direct entry points only. That makes sponsored unlocks or subsidized premium actions possible later, though it is not required for the core LuffaNator build. ([docs.endless.link][10])

## Multisig research groups

Endless publicly documents K-of-N multisig authentication and a multisig user guide for threshold-based signing and execution. That creates a future path for premium research clubs or shared paid rooms, though for the hackathon prototype I’d keep it out of the critical path. ([docs.endless.link][11])

# 17) Outcome definitions

## Outcome A: Demo-complete

By demo time, the system can:

* accept a request in Luffa chat,

* ask clarifying questions,

* run the adversarial research pipeline,

* display a rich report in the mini app,

* return a concise summary in chat,

* and let the user opt into tracking.

That is the minimum “this is real” outcome.

## Outcome B: Strong sponsor-native outcome

In addition to A:

* tracking updates are posted back into Luffa automatically,

* the report is revisitable,

* the user can challenge the thesis from chat,

* and the bot / mini app feel like two halves of one product.

That is the outcome that feels most Luffa-native.

## Outcome C: Winner-level outcome

In addition to B:

* the product exposes thesis drift over time,

* shows claim-to-source traceability,

* has a clean risk model,

* and demonstrates the beginnings of a self-improving eval loop.

That is the version that feels like more than “chatbot with a dashboard.”

## Outcome D: Moonshot outcome

In addition to C:

* optional wallet-linked premium access,

* optional publishable component / service packaging,

* optional sponsored actions,

* optional paper-trading-backed calibration screen,

* optional OpenClaw-powered deep runtime.

# 18) Success metrics

## Product metrics

* % of requests that complete successfully

* time to first useful clarification

* time to first summary

* report open rate from chat

* % of users who choose tracking

* repeat use on tracked theses

## Research-quality metrics

* citation coverage

* primary-source ratio

* contradiction coverage

* unresolved-question quality

* falsification-condition presence

* confidence calibration score

## System metrics

* average job runtime by depth tier

* token cost per stage

* failure rate by source type

* tracker notification success rate

* queue latency

* stale report rate

## Sponsor-fit metrics

* % of core flow completed in chat

* number of meaningful bot interactions per thesis

* number of follow-up actions triggered from Luffa

* ratio of bot-originated updates to user-originated refreshes

# 19) Demo script spec

## Demo setup

* Have one prepared thesis already tracked.

* Have one fresh thesis ready to research live.

* Have the mini app loaded.

* Have a fallback canned source set if live retrieval fails.

## Live flow

1. In Luffa chat, type: “Research ASML for me.”

2. Bot asks two clarifying questions.

3. You choose Standard depth.

4. Bot starts job and posts progress.

5. Open mini app and show:

   * live source collection

   * bull/bear stages

   * report view

6. Return to chat and show the concise summary.

7. Tap “Track thesis.”

8. Switch to an already-tracked thesis and show:

   * drift update

   * changed risk score

   * why it changed

9. Optional: open eval view and show how the system graded its previous thesis.

## Demo message

The key message is:

“Luffa isn’t just the place where you ask a question. It’s where the research is scoped, debated, delivered, tracked, and improved over time.”

# 20) Final scope statement

If you ignore ambition and write the full intended system, the product is:

**A Luffa-native adversarial due-diligence platform with a bot for intake and tracking, a mini app for report intelligence, a backend research orchestration engine, a persistent evidence graph, a multi-axis risk model, and a paper-trading-backed autoresearch evaluation loop.**

And if you want the sharpest one-sentence spec:

**Conviction Room is a chat-native research operator that turns ambiguous investment questions into structured adversarial memos, then tracks thesis drift and learns which research patterns actually held up over time.**

If you want, I’ll do the next layer down and write the **exact JSON schemas, DB schema, API endpoints, and agent node contracts**.

[1]: https://github.com/sabma-labs/luffa-bot-python-sdk "GitHub - sabma-labs/luffa-bot-python-sdk: Luffa Bot · GitHub"

[2]: https://userguide.luffa.im/ "What is Luffa? | Luffa User Guide"

[3]: https://docs.alpaca.markets/docs/paper-trading?utm_source=chatgpt.com "Paper Trading - Alpaca Docs"

[4]: https://github.com/sabma-labs/luffa-bot-demo?utm_source=chatgpt.com "sabma-labs/luffa-bot-demo: This is a ..."

[5]: https://docs.endless.link/endless/component-marketplace/user-guide "User Guide | Endless"

[6]: https://github.com/openclaw/openclaw/blob/main/docs/tools/index.md "openclaw/docs/tools/index.md at main · openclaw/openclaw · GitHub"

[7]: https://developers.openai.com/api/docs/guides/reasoning-best-practices/ "Reasoning best practices | OpenAI API"

[8]: https://developers.openai.com/api/docs/guides/structured-outputs/ "Structured model outputs | OpenAI API"

[9]: https://www.law.cornell.edu/cfr/text/17/4.41?utm_source=chatgpt.com "17 CFR § 4.41 - Advertising by commodity pool operators ... - LII"

[10]: https://docs.endless.link/endless/devbuild/technical-documentation/sponsored-transaction "Sponsored Transaction | Endless"

[11]: https://docs.endless.link/endless/devbuild/technical-documentation/endless-account "Endless Account | Endless"

