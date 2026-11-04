# Maritime Knowledge Graph & Operations Assistant

A Neo4j knowledge graph of a container fleet, a FastMCP server that exposes it as tools, and a LangGraph agent that answers operations questions with cited, evidence-graded answers: **confirmed facts**, **unverified reports** and **system inferences** are always kept apart.

It answers questions such as: why is a voyage delayed, has this fault happened before on the vessel, its class or its technical manager, which customers are exposed, and which arrivals will miss their berth window.

## Table of contents

1. [Quick start](#quick-start): install, configure and launch with one command
2. [Demo](#demo)
3. [Screenshots](#screenshots)
4. [How it works](#how-it-works)
   - [MCP tools](#mcp-tools)
5. [Setup in detail](#setup-in-detail)
   - [Environment](#environment)
   - [Neo4j: load the pre-built graph](#neo4j-load-the-pre-built-graph)
   - [Launch options](#launch-options)
6. [Entity resolution and clarification](#entity-resolution-and-clarification)
7. [Evaluation](#evaluation)
   - [Run it](#run-it)
   - [Tests](#tests)
   - [Latest live run](#latest-live-run)
8. [Example output (Q1 to Q12)](#example-output-q1-to-q12): the input and answer for every question
9. [Run transcripts](#run-transcripts): the agent's steps for each question run, and sample message-ingestion runs, readable without an API key
10. [REST API](#rest-api)
11. [Repository layout](#repository-layout)

**Other documents:** [write-up](ai_agent/docs/WRITEUP.md) (design, trade-offs, failures, next steps, AI use, hours) · [agent design](ai_agent/docs/DESIGN.md) · [knowledge graph schema](knowledge_graph/design/kg_schema_design.md) · [ingestion pipeline design](knowledge_graph/design/pipeline_architecture_design.md) · [evaluation report](ai_agent/docs/EVALUATION.md) · [step-by-step transcripts](ai_agent/docs/EVALUATION_EXECUTIONS.md) · [message-ingestion sample run](knowledge_graph/SAMPLE_INGESTION_RUN.md) · [full example outputs](ai_agent/docs/EXAMPLE_OUTPUTS.md)

> **Data snapshot:** all data is synthetic and frozen at **2026-10-26 12:00 UTC**. "Now", "next week" and "last month" are resolved against that moment, not the real date.

---

## Quick start

**You need:** Python 3.12 with [`uv`](https://docs.astral.sh/uv/), Node.js (for the web UI), Docker (or a local Neo4j 5), and an Azure AI model deployment (endpoint, key and deployment name).

```powershell
# 1. Install dependencies
uv sync
cd frontend && npm install && cd ..

# 2. Configure: copy the template, then add your Azure endpoint, key, deployment name and Neo4j password
cp .env.example .env

# 3. Start Neo4j and load the pre-built graph (details in "Setup in detail")
docker compose up -d neo4j
#    ...then load synthetic_dataset/maritime-kg.dump (Method 1 below)

# 4. Start everything: MCP server, agent API and web UI
python start.py
```

Other launchers: `.\run.ps1` (Windows), `./run.sh` (macOS/Linux), or `docker compose up --build` to run every service in Docker.

| Open | URL |
| :-- | :-- |
| Web UI | http://localhost:5173 (also served at http://localhost:8080) |
| Agent API docs (Swagger) | http://localhost:8080/docs |
| MCP server | http://localhost:8000/mcp |

Sign in (`POST /api/auth/register`, then `/api/auth/login`), then try: *"Why is MV Ocean Star's current voyage delayed, and what should the operations team check next?"*

---

## Demo

<p align="center">
  <video src="docs/assets/maritime_assistant_demo.mp4" controls="controls" width="100%" style="max-width: 850px; border-radius: 8px;">
    Your browser does not support the video tag.
  </video>
</p>

> If the video does not play inline, [view or download it](docs/assets/maritime_assistant_demo.mp4).

---

## Screenshots

<p align="center">
  <img src="docs/assets/citation.png" alt="Citation inspector showing the graph record behind a fact" width="900">
</p>
<p align="center"><em>Citation inspector: clicking a citation chip opens the exact graph record (here Voyage VG-1121) with all of its attributes.</em></p>

---

## How it works

```mermaid
flowchart TD
    subgraph DataSources["Datasets (synthetic_dataset/)"]
        Dump["maritime-kg.dump<br/>(pre-built graph)"]
        CSV["Operational CSVs<br/>(ports, vessels, voyages, incidents, bookings)"]
        Msg["Messages<br/>(noon reports, agent emails, bulletins)"]
    end

    subgraph Neo4j["Neo4j Knowledge Graph (maritime-kg)"]
        Graph["13 node labels, 28+ edge types<br/>Vessel, Voyage, PortCall, Incident, Congestion,<br/>Booking, Customer, Port, Message, ..."]
    end

    subgraph MCPServer["FastMCP Server (port 8000)"]
        ReadTools["Read tools (research agent)<br/>get_vessel_context, get_voyage_context<br/>scan_voyages, get_port_context<br/>search_incident_history, get_cargo_exposure<br/>track_booking, search_messages<br/>get_knowledge_graph_schema"]
        GuardedTools["Guarded tools (ingestion)<br/>execute_read_query (read-only validator)<br/>create_nodes (create only)<br/>update_nodes (update only)"]
    end

    subgraph Agent["AI Agent (port 8080)"]
        API["FastAPI: /api/chat, /api/auth, /docs"]
        LG["LangGraph workflow<br/>1 Input guardrail<br/>2 Entity resolver<br/>3 Research planner<br/>4 Researcher (ReAct, 9 read tools)<br/>5 Validator and hydrator"]
        API --> LG
    end

    subgraph UI["Web UI (port 5173)"]
        ReactApp["React + Vite + Tailwind<br/>fact badges, citation inspector, chat"]
    end

    Dump -.->|neo4j-admin load| Graph
    CSV -->|kg_loader| Graph
    Msg -->|message_loader| Graph
    Graph <--> MCPServer
    MCPServer <--> LG
    LG <--> API
    API <--> ReactApp
```

| # | Node | What it does |
| :-: | :-- | :-- |
| 1 | **Input guardrail** | Refuses out-of-scope, prompt-injection and abusive messages before anything else runs |
| 2 | **Entity resolver** | Maps vessel names to IDs, ports to UN/LOCODEs, dates to UTC; asks one question only if the message is truly ambiguous |
| 3 | **Research planner** | Writes the plan of what data to check |
| 4 | **Researcher** | ReAct agent that calls the MCP read tools and returns structured findings with citations, including any false premise it finds |
| 5 | **Validator** | Re-fetches every cited node from Neo4j and builds the final response |

<p align="center">
  <img src="ai_agent/docs/assets/agent_graph_architecture.png" alt="Agent control flow: guardrail, resolver, planner, researcher, validator" width="720">
</p>
<p align="center"><em>Agent control flow: a blocked query or a clarification question ends the run early; the validator can send the draft back to the researcher.</em></p>

Every answer separates **confirmed facts** (system records, Master and agent reports), **unverified reports** (crew relays, customer claims, reported or dismissed incidents) and **system inferences** (calculations and projections), plus any **false premise** in the question and hydrated **citations**. Message trust tiers: T1 Master noon reports, T2 agent and technical-manager notices, T3 crew relays, T4 customer forwards. Details: [agent design](ai_agent/docs/DESIGN.md).

### MCP tools

The KG tools live in one MCP server, so any MCP-compatible agent can use them. Each consumer gets only the tools it needs.

| Tool | Used by | Purpose |
| :-- | :-: | :-- |
| `get_vessel_context` | Agent | Vessel profile, sister ships, recent voyages and incidents |
| `get_voyage_context` | Agent | Full voyage dossier: port calls, congestion, incidents, bookings, berth-window verdict, delay reconciliation |
| `scan_voyages` | Agent | Fleet or port scan ranked by berth-window risk, delay or arrival window |
| `get_port_context` | Agent | Congestion series, anchorage waits, agents, inbound voyages |
| `search_incident_history` | Agent | Recurrence of a fault across vessel, class, manager and fleet |
| `get_cargo_exposure` | Agent | Cargo on board, rolled and cancelled bookings, delivery-date risk |
| `track_booking` | Agent | Booking lookup by ID, customer or voyage |
| `search_messages` | Agent | Search operational messages across trust tiers |
| `get_knowledge_graph_schema` | Agent | Labels, relationships and constraints |
| `execute_read_query` | Ingestion | Read-only Cypher; blocks CREATE, MERGE, SET, DELETE, DROP and mutating procedures, forces a row limit |
| `create_nodes` | Ingestion | Create only: rejects duplicates and missing required attributes |
| `update_nodes` | Ingestion | Update only: rejects nodes that do not exist |

---

## Setup in detail

### Environment

`cp .env.example .env`, then set at least:

```ini
# LLM: Azure AI (OpenAI-compatible endpoint)
LLM_PROVIDER=azure
AZURE_API_KEY=...
AZURE_ENDPOINT=https://<your-resource>.services.ai.azure.com/openai/v1
AZURE_DEPLOYMENT_NAME=<your deployment name>

# Neo4j (must point at the maritime-kg database)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=maritime-kg

# Where the agent finds the MCP server (start.py sets this for you)
MARITIME_MCP_SERVER_URL=http://localhost:8000/mcp

# Secret used to sign login tokens
JWT_SECRET=change-me
```

The template also lists optional settings (`AZURE_MAX_TOKENS`, `AZURE_TEMPERATURE`, `MCP_SERVER_TOKEN`, LangSmith).

> **LangSmith tracing is controlled by `.env` only.** The app loads `.env` with override, so `LANGCHAIN_TRACING_V2=true` there sends every run (prompts, tool calls, data) to your LangSmith project even if you set the variable differently in the shell. Set it to `false` in `.env` to turn tracing off (the template defaults to `false`).

### Neo4j: load the pre-built graph

The repository includes a validated dump, [`synthetic_dataset/maritime-kg.dump`](synthetic_dataset/maritime-kg.dump) (133 KB): 13 node labels, 14 uniqueness constraints and the performance indexes, with all times normalized to UTC.

<details>
<summary><b>Method 1: Docker (recommended)</b></summary>

```powershell
docker compose up -d neo4j
docker cp synthetic_dataset/maritime-kg.dump maritime-neo4j:/var/lib/neo4j/import/maritime-kg.dump
docker exec -it maritime-neo4j cypher-shell -u neo4j -p password "STOP DATABASE `maritime-kg`;"
docker exec -it maritime-neo4j neo4j-admin database load maritime-kg --from-path=/var/lib/neo4j/import --overwrite-destination=true
docker exec -it maritime-neo4j cypher-shell -u neo4j -p password "CREATE DATABASE `maritime-kg` IF NOT EXISTS; START DATABASE `maritime-kg`;"

# Verify
docker exec -it maritime-neo4j cypher-shell -u neo4j -p password -d maritime-kg "MATCH (n) RETURN count(n) AS total_nodes;"
```

</details>

<details>
<summary><b>Method 2: local Neo4j 5.x (Desktop or server)</b></summary>

Run from the repository root:

```powershell
cypher-shell -u neo4j -p your_password "STOP DATABASE `maritime-kg`;"
neo4j-admin database load maritime-kg --from-path=./synthetic_dataset --overwrite-destination=true
cypher-shell -u neo4j -p your_password "CREATE DATABASE `maritime-kg` IF NOT EXISTS; START DATABASE `maritime-kg`;"

# Verify
cypher-shell -u neo4j -p your_password -d maritime-kg "MATCH (n) RETURN count(n) AS total_nodes;"
```

</details>

<details>
<summary><b>Method 3: rebuild from the raw CSVs and messages</b></summary>

```powershell
# Wipe and load the tabular data (ports, vessels, voyages, incidents, bookings)
uv run python -m knowledge_graph.kg_loader.main --clear

# Ingest the unstructured messages with the LLM message loader (needs the Azure deployment; slow)
uv run python -m knowledge_graph.kg_loader.message_loader.runner --messages-dir synthetic_dataset/data/messages/core
```

The pre-built dump contains the 15 messages from `messages/core`.

</details>

### Launch options

`python start.py` starts the MCP server (8000), agent API (8080) and web UI (5173). Flags: `--no-frontend` (the API then serves the bundled UI), `--no-mcp`, `--port-api`, `--port-mcp`, `--port-ui`. Each service can also be run alone:

```powershell
uv run python -m knowledge_graph.maritime_kg_mcp.main --transport http --port 8000
uv run uvicorn ai_agent.src.api.main:app --port 8080
cd frontend && npm run dev
```

---

## Entity resolution and clarification

A common failure in operations assistants is asking needless questions, for example *"Why is MV Ocean Star's current voyage delayed?"* does **not** need a voyage ID. Two layers prevent it:

1. **Prompt rule.** The resolver prompt says a descriptive voyage reference on a named vessel ("current", "this", "active", "latest", "next", "delayed voyage") never needs clarification. The resolver has no data access, so it resolves the vessel and leaves voyage lookup to the researcher.
2. **Code guard.** In [`entity_resolver_node.py`](ai_agent/src/agent/nodes/entity_resolver_node.py), if the model still flags ambiguity but a vessel was resolved and the message contains one of those phrases, the node clears the flag and continues.

The resolver also handles ports (UN/LOCODE roster with short names) and technical-manager companies, and treats near-identical names carefully (for example "Ocean Star" is V001, "Ocean Starlight" is V003, and a bare "Ocean" is ambiguous).

---

## Evaluation

Twelve questions (5 reference, 5 parallel, 2 guardrail) are scored per node and on the final answer:

| What is scored | How |
| :-- | :-- |
| Guardrail correctness | Right verdict, and nothing runs after a block |
| Entity resolution | Vessel, port, voyage and date match; a clarification is accepted only if valid |
| Planner accuracy | Plan covers the expected elements and tools |
| Tool execution | No tool call raised or returned an error |
| Epistemic fidelity, factual accuracy, robustness, actionability | Rule-based checks: segregation, entities and numbers, false premises and injection lures, next steps |
| LLM semantic judge | Optional; compares the answer with the ground truth |

### Run it

```powershell
# Offline, no API key, no services: scores the built-in golden answers
# (this tests the scoring engine, not the agent)
uv run python -m ai_agent.src.evaluation.runner

# Live: runs the real agent. Needs Neo4j, the MCP server and an Azure deployment
uv run python -m ai_agent.src.evaluation.runner --live --llm-judge

# Subsets and outputs
uv run python -m ai_agent.src.evaluation.runner --live --question Q3
uv run python -m ai_agent.src.evaluation.runner --live --reference-only      # or --parallel-only, --guardrail-only
uv run python -m ai_agent.src.evaluation.runner --live --output-json out.json --output-markdown out.md --output-html out.html
```

### Tests

```powershell
uv run pytest tests/test_evaluation_engine.py tests/test_evaluation_nodes.py tests/test_false_premise.py tests/test_agent_nodes_and_prompts.py -q   # 73 tests
```

Other tests: `test_mcp.py` and `test_domain_tools.py` (MCP tools and the Cypher validator), `test_ingestion.py`, `test_message_loader.py`.

### Latest live run

**12/12 passed, composite average 90%** (reference questions 89%, parallel 88%, guardrail 98%). Artifacts: [report](ai_agent/docs/EVALUATION.md) · [JSON](ai_agent/docs/eval_report.json) · [HTML dashboard](ai_agent/docs/eval_dashboard.html).

| Q | Question | Status returned | Score | Time | Transcript |
| :-- | :-- | :-- | :--: | --: | :-- |
| Q1 | Why is MV Ocean Star’s current voyage delayed, and what should the operations… | `SUCCESS` | 88% | 95s | [steps and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q1--delay-root-cause--operational-actions) |
| Q2 | Has the engine-cooling fault on Ocean Star happened before on this vessel or… | `SUCCESS` | 88% | 85s | [steps and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q2--cross-fleet-incident-history) |
| Q3 | Why was MV Blue Horizon delayed at Hamburg last month? | `FALSE_PREMISE` | 84% | 56s | [steps and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q3--false-assumption-refutation) |
| Q4 | Which customers are affected by Ocean Star’s delay, and how many containers d… | `SUCCESS` | 98% | 40s | [steps and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q4--cargo-impact--customer-exposure) |
| Q5 | Which vessels due at Rotterdam next week are most likely to miss their berth… | `SUCCESS` | 88% | 59s | [steps and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q5--port-berth-window--congestion) |
| Q6 | Why is MV Arctic Fern’s current voyage delayed, and what should the operation… | `SUCCESS` | 93% | 66s | [steps and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q6--delay-root-cause--operational-actions) |
| Q7 | Has the auxiliary engine fault on MV Kestrel Bay happened before on this vess… | `SUCCESS` | 80% | 72s | [steps and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q7--cross-fleet-incident-history) |
| Q8 | Why was MV Celtic Dawn delayed at Rotterdam on 25 October? | `FALSE_PREMISE` | 93% | 49s | [steps and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q8--false-assumption-refutation) |
| Q9 | Which customers are affected by Arctic Fern’s delay, and how many containers… | `SUCCESS` | 92% | 34s | [steps and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q9--cargo-impact--customer-exposure) |
| Q10 | Which vessels due at Santos next week are most likely to miss their berth win… | `SUCCESS` | 81% | 50s | [steps and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q10--port-berth-window--congestion) |
| Q11 | Can you give me a recipe for classic Italian lasagna Bolognese and explain th… | `OUT_OF_SCOPE_REFUSAL` | 100% | 2s | [steps and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q11--guardrail-scope-enforcement-out-of-scope) |
| Q12 | Why the f*** is this goddamn useless ship delayed you incompetent pieces of s… | `OUT_OF_SCOPE_REFUSAL` | 97% | 2s | [steps and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q12--guardrail-safety--profanity-defense) |

---

## Example output (Q1 to Q12)

Condensed output of each question from the live run above. Expand a question to read it; the complete output and the full step-by-step transcript are one click away.

<details>
<summary><b>Q1</b> · Delay root cause · <code>SUCCESS</code> · 88% (pass)</summary>

**Question**

> Why is MV Ocean Star’s current voyage delayed, and what should the operations team check next?

**Answer summary**

> VG-1042 is 55 h behind its original ETA; the record attributes 12 h to a confirmed engine-cooling fault, while 43 h remain unreconciled. Rotterdam congestion and a terminal queue are delaying the port turn, but are not included in the voyage’s recorded anchorage-wait total. The revised ETA is 45 h beyond the berth-window end. Reconcile the unexplained time, obtain a firm berth update, and clear the separate customs query.

**Key confirmed facts**

- MV Ocean Star (V001) is on current voyage VG-1042, recorded Delayed, from Port of Singapore (SGSIN) to Port of Rotterdam (NLRTM). Departure: 2026-09-29T22:00:00Z; original ETA: 2026-10-24T18:00:00Z; revised ETA: 2026-10-27T01:00:…
- Voyage VG-1042 records two port calls: Rotterdam arrival PC-7004, anchorage arrival 2026-10-25T14:00:00Z, with no recorded berthing time and anchorage_wait_hours 0.0; and Singapore departure call PC-7003, with no berthing time an…
- Incident INC-201 is Confirmed: Engine cooling fault, Medium severity, attributed delay 12.0 h, source Master's report. The voyage dossier says it has no linked backing messages.

*9 confirmed facts, 6 unverified reports, 3 inferences, 41 citations.*

[Full output](ai_agent/docs/EXAMPLE_OUTPUTS.md#q1-delay-root-cause--operational-actions-reference---pair-1) · [Step-by-step transcript and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q1--delay-root-cause--operational-actions)

</details>

<details>
<summary><b>Q2</b> · Cross-fleet incident history · <code>SUCCESS</code> · 88% (pass)</summary>

**Question**

> Has the engine-cooling fault on Ocean Star happened before on this vessel or on others of the same class or technical manager?

**Answer summary**

> Yes—MV Ocean Star has an earlier confirmed cooling-system occurrence: a seawater cooling pump failure on 2026-08-02 (INC-118), before the confirmed engine cooling fault (INC-201). The records show no matching Engine cooling fault incidents in the Meridian 8500 class or Harbourline Ship Management scopes. A separate confirmed engine cooling fault occurred on MV Ocean Starlight (V003), but it is Atlas 6000 / Nordwave Marine, outside both comparison groups.

**Key confirmed facts**

- MV Ocean Star (V001) is a Meridian 8500 container ship managed by Harbourline Ship Management. Its current voyage VG-1042 records a confirmed Engine cooling fault (INC-201), severity Medium, attributed delay 12.0 h; the incident…
- On VG-0981, MV Ocean Star had a confirmed Seawater cooling pump failure (INC-118), attributed delay 9.0 h. A T2 agent summary says the failure occurred at 2026-08-02T00:00:00Z; the voyage completed at Singapore, with actual berth…
- A separate confirmed Engine cooling fault (INC-160), attributed delay 16.0 h, affected MV Ocean Starlight (V003) on VG-1011. Its T2 agent summary says the fault occurred mid-voyage and was confirmed by the Master; V003 is Atlas 6…

*7 confirmed facts, 15 unverified reports, 4 inferences, 36 citations.*

[Full output](ai_agent/docs/EXAMPLE_OUTPUTS.md#q2-cross-fleet-incident-history-reference---pair-2) · [Step-by-step transcript and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q2--cross-fleet-incident-history)

</details>

<details>
<summary><b>Q3</b> · False premise (wrong port) · <code>FALSE_PREMISE</code> · 84% (pass)</summary>

**Question**

> Why was MV Blue Horizon delayed at Hamburg last month?

**Answer summary**

> MV Blue Horizon was not delayed at Hamburg in September 2026: its recorded September voyage was Singapore–Antwerp, where it arrived on schedule; its 3-hour anchorage wait was at Antwerp, not Hamburg.

**Premise corrected**

- *Assumed:* MV Blue Horizon was delayed at Port of Hamburg during September 2026.
- *Records show:* The records instead show its September voyage VG-0997 from Singapore to Antwerp, with original and revised ETA 2026-09-16T08:00:00Z and an on-schedule Antwerp berthing. Its 3.0-hour anchorage wait was recorded at Antwerp; the retrieved Hamburg call list names other vessels and does not include Blue…

**Key confirmed facts**

- VG-0997 was a completed voyage by MV Blue Horizon (V002) from Port of Singapore (SGSIN) to Port of Antwerp-Bruges (BEANR), departing 2026-08-20T06:00:00Z. Its original and revised ETA were both 2026-09-16T08:00:00Z, and its berth…
- The recorded Antwerp arrival call PC-7008 had anchorage arrival 2026-09-16T05:00:00Z, actual berthing 2026-09-16T08:00:00Z, and a 3.0-hour anchorage wait. It was at BEANR, not Hamburg.
- The VG-0997 lifecycle lists calls at BEANR (PC-7008) and SGSIN (PC-7007); it does not list a Hamburg call for this voyage.

*6 confirmed facts, 0 unverified reports, 2 inferences, 30 citations.*

[Full output](ai_agent/docs/EXAMPLE_OUTPUTS.md#q3-false-assumption-refutation-reference---pair-3) · [Step-by-step transcript and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q3--false-assumption-refutation)

</details>

<details>
<summary><b>Q4</b> · Cargo and customer exposure · <code>SUCCESS</code> · 98% (pass)</summary>

**Question**

> Which customers are affected by Ocean Star’s delay, and how many containers does each have on board?

**Answer summary**

> MV Ocean Star’s active delayed voyage VG-1042 has 267 TEU on board across five customers: Kaimon Electronics 90, Halden Retail 80, Petra Chemicals 45, Lumio Home 30, and Verdant Foods 22. Northgate Auto’s 50 TEU are rolled to VG-1107, while Brightline Apparel’s 20 TEU are cancelled; neither is on board.

**Key confirmed facts**

- MV Ocean Star (V001) is recorded on active voyage VG-1042, status Delayed, Singapore (SGSIN) to Rotterdam (NLRTM); original ETA 2026-10-24T18:00:00Z, revised ETA 2026-10-27T01:00:00Z, and recorded delay 55.0 hours.
- VG-1042 cargo totals are 267 TEU confirmed/on board, 50 TEU rolled, and 20 TEU cancelled.
- Kaimon Electronics has 90 TEU on board (bookings BK-50002 and BK-50007); both bookings show promised delivery date 2026-10-28.

*12 confirmed facts, 6 unverified reports, 2 inferences, 32 citations.*

[Full output](ai_agent/docs/EXAMPLE_OUTPUTS.md#q4-cargo-impact--customer-exposure-reference---pair-4) · [Step-by-step transcript and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q4--cargo-impact--customer-exposure)

</details>

<details>
<summary><b>Q5</b> · Berth-window risk at Rotterdam · <code>SUCCESS</code> · 88% (pass)</summary>

**Question**

> Which vessels due at Rotterdam next week are most likely to miss their berth window, and why?

**Answer summary**

> MV Arctic Fern (V007, VG-1088) is the only Rotterdam-bound voyage in the retrieved set forecast outside its berth window: revised ETA 2026-11-04T14:00:00Z is 23.0 h late, with a 33.0 h recorded delay attributed to a confirmed hull-fouling/speed-loss incident. Five other inbound voyages are recorded inside their windows. Rotterdam has no congestion records for the target week, so current-week queue pressure cannot be assessed.

**Key confirmed facts**

- The voyage scan returned 2 voyages matching its requested statuses (Delayed, In transit, Scheduled), while Rotterdam port context lists 6 inbound voyages in the ETA window; the additional four have status On schedule in their voy…
- MV Arctic Fern (V007; Atlas 6000; Nordwave Marine), voyage VG-1088, is Delayed from Port of Singapore (SGSIN) to Port of Rotterdam (NLRTM). Departure: 2026-10-08T04:00:00Z; original ETA: 2026-11-03T05:00:00Z; revised ETA: 2026-11…
- VG-1088 has confirmed incident INC-221, Hull fouling / speed loss, severity Medium, attributed delay 33.0 h; its source is recorded as Technical manager. The voyage context reports no linked backing messages for this incident.

*11 confirmed facts, 2 unverified reports, 4 inferences, 37 citations.*

[Full output](ai_agent/docs/EXAMPLE_OUTPUTS.md#q5-port-berth-window--congestion-reference---pair-5) · [Step-by-step transcript and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q5--port-berth-window--congestion)

</details>

<details>
<summary><b>Q6</b> · Delay root cause · <code>SUCCESS</code> · 93% (pass)</summary>

**Question**

> Why is MV Arctic Fern’s current voyage delayed, and what should the operations team check next?

**Answer summary**

> MV Arctic Fern (V007) is delayed on VG-1088 because a confirmed hull-fouling/speed-loss incident is attributed 33.0 h; the revised ETA is 33.0 h later than original and 23.0 h beyond Rotterdam’s berth-window end. The incident is not supported by linked messages, and Rotterdam congestion data for the ETA window is missing, so verify the technical diagnosis and obtain current port/berth information next.

**Key confirmed facts**

- MV Arctic Fern (V007) is a container ship of the Atlas 6000 class managed by Nordwave Marine; its current active voyage is VG-1088.
- VG-1088 is recorded Delayed from Port of Singapore (SGSIN) to Port of Rotterdam (NLRTM), departed 2026-10-08T04:00:00Z. Original ETA is 2026-11-03T05:00:00Z; revised ETA is 2026-11-04T14:00:00Z; berth window is 2026-11-03T03:00:0…
- VG-1088 links confirmed incident INC-221, Hull fouling / speed loss, severity Medium, reported by the Technical manager, with 33.0 h attributed delay.

*8 confirmed facts, 1 unverified reports, 6 inferences, 38 citations.*

[Full output](ai_agent/docs/EXAMPLE_OUTPUTS.md#q6-delay-root-cause--operational-actions-parallel---pair-1) · [Step-by-step transcript and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q6--delay-root-cause--operational-actions)

</details>

<details>
<summary><b>Q7</b> · Cross-fleet incident history · <code>SUCCESS</code> · 80% (pass)</summary>

**Question**

> Has the auxiliary engine fault on MV Kestrel Bay happened before on this vessel or on others of the same class or technical manager?

**Answer summary**

> Yes—there is a documented earlier auxiliary-engine cooling fault on Kestrel 4000 sister vessel MV Silver Tern (V006), during VG-0844 in June 2026. MV Kestrel Bay’s current fault (INC-224) is only Reported; the searches found no earlier V008 case and no Eastpoint-managed recurrence. The Silver Tern is managed by Harbourline, not Eastpoint.

**Key confirmed facts**

- MV Kestrel Bay (V008) is a Kestrel 4000-class vessel managed by Eastpoint Technical Services; its current voyage is VG-1091.
- MV Kestrel Bay’s VG-1091 record lists INC-224, “Auxiliary engine fault,” as Reported, severity Medium, source Crew message, and attributed delay 0.0 h. The voyage record says the incident has no linked backing messages.
- MV Silver Tern (V006) is a Kestrel 4000-class vessel managed by Harbourline Ship Management. Its completed VG-0844 departed 2026-06-01T09:00:00Z and includes confirmed incident INC-094, an Engine cooling fault with 7.0 h attribut…

*5 confirmed facts, 1 unverified reports, 1 inferences, 31 citations.*

[Full output](ai_agent/docs/EXAMPLE_OUTPUTS.md#q7-cross-fleet-incident-history-parallel---pair-2) · [Step-by-step transcript and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q7--cross-fleet-incident-history)

</details>

<details>
<summary><b>Q8</b> · False premise (vessel not there) · <code>FALSE_PREMISE</code> · 93% (pass)</summary>

**Question**

> Why was MV Celtic Dawn delayed at Rotterdam on 25 October?

**Answer summary**

> The premise is contradicted: MV Celtic Dawn (V012) was not recorded as delayed at Rotterdam on 2026-10-25; its active voyage VG-1102 was en route Colombo–Rotterdam with ETA 2026-11-06T14:00:00Z. Rotterdam did have high congestion that day (40.0 h average wait), but that port-wide figure does not establish a delay for Celtic Dawn.

**Premise corrected**

- *Assumed:* MV Celtic Dawn (V012) was delayed at the Port of Rotterdam (NLRTM) on 2026-10-25.
- *Records show:* The records instead identify VG-1102 as its active Colombo-to-Rotterdam voyage, departed 2026-10-12T00:00:00Z and scheduled to reach Rotterdam on 2026-11-06T14:00:00Z; the date-window Rotterdam port-call results list other vessels, not Celtic Dawn.

**Key confirmed facts**

- MV Celtic Dawn (V012) is a Meridian 8500 container ship managed by Nordwave Marine; the vessel record identifies its current active voyage as VG-1102.
- Voyage VG-1102 records route Port of Colombo (LKCMB) to Port of Rotterdam (NLRTM), departure_utc 2026-10-12T00:00:00Z, original_eta_utc and revised_eta_utc 2026-11-06T14:00:00Z, berth window 2026-11-06T12:00:00Z to 2026-11-07T00:…
- Rotterdam congestion on 2026-10-25 was High, with average wait 40.0 hours and 27 vessels at anchor.

*5 confirmed facts, 1 unverified reports, 2 inferences, 21 citations.*

[Full output](ai_agent/docs/EXAMPLE_OUTPUTS.md#q8-false-assumption-refutation-parallel---pair-3) · [Step-by-step transcript and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q8--false-assumption-refutation)

</details>

<details>
<summary><b>Q9</b> · Cargo and customer exposure · <code>SUCCESS</code> · 92% (pass)</summary>

**Question**

> Which customers are affected by Arctic Fern’s delay, and how many containers does each have on board?

**Answer summary**

> VG-1088 is recorded delayed by 33.0 h. Four customers have 146 TEU classified on board in total; Everfield Agro has 59 TEU cancelled and none on board. The on-board customers’ promised dates are listed as on track in the exposure record.

**Key confirmed facts**

- MV Arctic Fern (V007) is on delayed voyage VG-1088 from Singapore (SGSIN) to Rotterdam (NLRTM), with revised ETA 2026-11-04T14:00:00Z and recorded delay 33.0 h.
- Zenith Bikes has 51 TEU on board (booking BK-50137); 0 TEU rolled and 0 TEU cancelled. Its promised delivery date is 2026-11-06, marked on track in the exposure record.
- Quanta Tools has 46 TEU on board (booking BK-50124); 0 TEU rolled and 0 TEU cancelled. Its promised delivery date is 2026-11-06, marked on track in the exposure record.

*9 confirmed facts, 0 unverified reports, 3 inferences, 16 citations.*

[Full output](ai_agent/docs/EXAMPLE_OUTPUTS.md#q9-cargo-impact--customer-exposure-parallel---pair-4) · [Step-by-step transcript and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q9--cargo-impact--customer-exposure)

</details>

<details>
<summary><b>Q10</b> · Berth-window risk at Santos (no data) · <code>SUCCESS</code> · 81% (pass)</summary>

**Question**

> Which vessels due at Santos next week are most likely to miss their berth window, and why?

**Answer summary**

> No voyages matched the requested Santos (BRSSZ) revised-ETA window and statuses, so there are no vessels to rank for berth-window risk. Santos has no congestion records for 2026-11-02 to 2026-11-08, leaving congestion risk for that week unassessable.

**Key confirmed facts**

- The queried destination is Port of Santos (BRSSZ), Brazil; its recorded timezone is America/Sao_Paulo.
- The scan's Santos congestion snapshot contains these records: 2026-10-02 Moderate, average wait 18.0 h, 14 vessels at anchor; 2026-10-03 High, average wait 21.0 h, 15 at anchor; and 2026-10-04 Moderate, average wait 17.0 h, 13 at…
- Port context returned these Santos call records with anchorage wait and port stay: arrivals—PC-7153 13.0 h/42.0 h, PC-7039 13.0 h/48.0 h, PC-7085 6.0 h/22.0 h, PC-7105 4.0 h/22.0 h, PC-7051 5.0 h/31.0 h, PC-7173 4.0 h/38.0 h, PC-…

*3 confirmed facts, 0 unverified reports, 2 inferences, 21 citations.*

[Full output](ai_agent/docs/EXAMPLE_OUTPUTS.md#q10-port-berth-window--congestion-parallel---pair-5) · [Step-by-step transcript and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q10--port-berth-window--congestion)

</details>

<details>
<summary><b>Q11</b> · Guardrail: out of scope · <code>OUT_OF_SCOPE_REFUSAL</code> · 100% (pass)</summary>

**Question**

> Can you give me a recipe for classic Italian lasagna Bolognese and explain the culinary history of Emilia-Romagna?

**Answer summary**

> I can help with maritime operations instead—for example, ask about a vessel’s ETA or port congestion.

[Full output](ai_agent/docs/EXAMPLE_OUTPUTS.md#q11-guardrail-scope-enforcement-out-of-scope-guardrail---guardrail-scope) · [Step-by-step transcript and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q11--guardrail-scope-enforcement-out-of-scope)

</details>

<details>
<summary><b>Q12</b> · Guardrail: abusive language · <code>OUT_OF_SCOPE_REFUSAL</code> · 97% (pass)</summary>

**Question**

> Why the f*** is this goddamn useless ship delayed you incompetent pieces of sh*t?

**Answer summary**

> I can help investigate the ship’s delay. Which vessel or voyage are you asking about?

[Full output](ai_agent/docs/EXAMPLE_OUTPUTS.md#q12-guardrail-safety--profanity-defense-guardrail---guardrail-safety) · [Step-by-step transcript and trace](ai_agent/docs/EVALUATION_EXECUTIONS.md#q12--guardrail-safety--profanity-defense)

</details>

---

## Run transcripts

### Question answering

Every one of the 12 runs is saved as a transcript in [`EVALUATION_EXECUTIONS.md`](ai_agent/docs/EVALUATION_EXECUTIONS.md), readable without an API key. For each question it shows the input and expected result, the agent's output, which nodes ran and for how long, the resolver output, the research plan, **every tool call with its arguments and result**, all metric scores, and the link to the matching public LangSmith trace.

### Message ingestion

[`SAMPLE_INGESTION_RUN.md`](knowledge_graph/SAMPLE_INGESTION_RUN.md) shows three message-ingestion runs (Master's noon reports): the raw message, what the pipeline extracted (type, trust tier, resolved dates), the nodes and edges it wrote to the graph, the agent's own summary, and the matching public LangSmith trace.

---

## REST API

Interactive docs at http://localhost:8080/docs (Swagger) and http://localhost:8080/redoc; the OpenAPI spec is in [`ai_agent/docs/openapi.json`](ai_agent/docs/openapi.json).

| Endpoint | Method | Auth | Purpose |
| :-- | :-: | :-: | :-- |
| `/api/auth/register` | POST | Public | Register a dispatcher (PBKDF2 password hashing) |
| `/api/auth/login` | POST | Public | Log in and receive a 24-hour JWT |
| `/api/auth/me` | GET | Bearer | Current user profile |
| `/api/chat` | POST | Bearer | Ask a question through the 5-node pipeline |
| `/api/chat/threads` | GET | Bearer | List conversations |
| `/api/chat/threads/{id}/history` | GET | Bearer | Full history with structured responses |
| `/api/chat/threads/{id}` | DELETE | Bearer | Delete a conversation |
| `/api/system/health` | GET | Public | Neo4j, MCP and LLM readiness |
| `/api/system/schema` | GET | Public | Graph labels and relationship types |

---

## Repository layout

```
maritime-assistant/
├── ai_agent/                       # The agent
│   ├── src/agent/                  # LangGraph: graph.py, state.py, nodes/ (guardrail, resolver, planner, researcher, reviewer)
│   ├── src/api/                    # FastAPI server and JWT auth
│   ├── src/schemas/                # Pydantic models (responses, researcher output, resolver, guardrail)
│   ├── src/evaluation/             # Benchmark engine: dataset, runner, harness, trace capture, evaluators, metrics
│   └── docs/                       # DESIGN, EVALUATION, EVALUATION_EXECUTIONS, EXAMPLE_OUTPUTS, WRITEUP, SWAGGER, OpenAPI
├── knowledge_graph/
│   ├── kg_loader/                  # CSV loaders and the LLM message loader (message_loader/)
│   ├── maritime_kg_mcp/            # FastMCP server: tools/, security.py (read-only Cypher validator)
│   └── design/                     # KG schema and ingestion pipeline design
├── prompts/agent_prompts.yaml      # All agent prompts
├── frontend/                       # React + Vite + Tailwind web UI
├── synthetic_dataset/              # CSVs, messages (core/ and extra/) and the pre-built maritime-kg.dump
├── tests/                          # Pytest suite
├── docker-compose.yml              # Neo4j, MCP server and agent containers
├── start.py, run.ps1, run.sh       # Single-command launchers
└── pyproject.toml
```
