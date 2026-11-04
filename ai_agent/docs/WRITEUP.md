# Maritime Operations Assistant

**Time:** 3 days from analysis to report delivery (≈ 50 h of focused work).

**Repository:** [Gokul-panneerselvam/maritime-assistant](https://github.com/Gokul-panneerselvam/maritime-assistant)

**Design files:** [Knowledge graph schema](../../knowledge_graph/design/kg_schema_design.md) · [Ingestion pipeline](../../knowledge_graph/design/pipeline_architecture_design.md) · [Agent](DESIGN.md) · [Evaluation report](EVALUATION.md)

**Run records (with LangSmith traces):** [Evaluation execution log](EVALUATION_EXECUTIONS.md) (12 questions) · [Ingestion sample run](../../knowledge_graph/SAMPLE_INGESTION_RUN.md) (3 messages)

## 1. Design

Three layers with one-way dependencies: **KG → KG MCP → agent**.

- **KG (Neo4j)** ([schema](../../knowledge_graph/design/kg_schema_design.md), [ingestion](../../knowledge_graph/design/pipeline_architecture_design.md), [sample run](../../knowledge_graph/SAMPLE_INGESTION_RUN.md)): 13 labels, 28+ edge types, 14 uniqueness constraints. CSVs load deterministically. Messages load through an LLM ingestion agent that tags trust tiers T1–T4 and quarantines prompt injection (`is_malicious`; 1 caught in the Kaimon forward).
- **KG MCP (FastMCP)** ([code](../../knowledge_graph/maritime_kg_mcp)): nine curated read tools (voyage, vessel, port, incident, cargo, booking, message, schema, scan) plus three guarded primitives: `execute_read_query` (rejects CREATE/MERGE/SET/DELETE/DROP and mutating procedures, strips comments, forces a LIMIT), `create_nodes` (create-only, rejects duplicates) and `update_nodes` (update-only). Tools take a `DatabaseClientProtocol`, not a driver.
- **Agent (LangGraph)** ([design](DESIGN.md)): guardrail → entity resolver → planner → ReAct researcher → deterministic validator. The resolver canonicalises vessels, ports (UN/LOCODE) and technical-manager companies and resolves dates against the fixed snapshot. Answers are split into confirmed facts, unverified reports and inferences, with citations re-fetched from Neo4j.

**One tool layer, two consumers.** The ingestion agent imports the same tool functions in-process and uses all three primitives, so the LLM writes its own Cypher for ingestion behind the validators. The research agent reaches them over HTTP and filters out the write and raw-Cypher tools; it answers only through the curated tools.

## 2. Trade-Offs

| Decision | Chosen | Why / cost |
| :-- | :-- | :-- |
| Store | **Neo4j** over an in-memory graph library | Chosen for Cypher: declarative multi-hop queries (class and manager scopes, citation lookups) that an LLM can also write, instead of learning the graph operations of one in-memory library. At ~1.5k rows an in-memory graph would be faster and simpler. Cost: a service to run, and a query-injection surface that needed the read-only validator and create-only/update-only tools. |
| Decoupling | **One KG MCP server** instead of framework-native tools | The KG tools are implemented once and exposed as an MCP server that any MCP-compatible agent can use, instead of separate LangChain-native tool sets per workflow. Each consumer gets only the tools it needs: the research agent the nine read tools over MCP; ingestion read, create and update (today it calls the same tool functions in-process, wrapped as LangChain tools, not over the MCP URL). Cost: a network hop for the agent, the allowlist is applied by the client rather than the server, and the tools are still Cypher, so a new store needs a Cypher-compatible backend. |

## 3. Evaluation and Failures by Type

12 questions (5 reference, 5 parallel, 2 guardrail), scored per node (guardrail, resolver, planner, tool errors) and on the answer (rules plus LLM judge). Run 1: **2/12** (9 of the 10 failures were infrastructure). Final live run: **12/12, average 90%**, but see the caveats below.

| Failure type | Cases | Outcome |
| :-- | :-- | :-- |
| Resolver over-clarifies ("current voyage") | Q1, Q6 (26%) | Prompt rule added; now 88% and 92% |
| **Schema cannot express a false premise** | Q3, Q8 (50%, 65%) | **Fixed**: now 84–96% and 93% |
| Tool-argument validation errors | 17 of 76 calls | Open as the known failure |

**Fixes the failures led to.**

- **Resolver prompt rule:** a descriptive voyage reference on a named vessel ("current voyage") never triggers a clarification question. Q1 and Q6 went from 26% to 88% and 92%.
- **`false_premises` in the researcher schema:** mapped through to `false_premises_detected` and the `FALSE_PREMISE` status, with the structure and rules documented in the researcher prompt. Q3 and Q8 now return `FALSE_PREMISE` with the correction and citations (Q3 84–96%, Q8 93%), the status check passes, and the frontend's existing premise banner has data to show.

## 4. Known Failures

- **Tool-call argument errors:** 17 of 76 researcher tool calls (22%) failed input validation in the final run (10 in `get_voyage_context`, 4 in `search_messages`, 2 in `search_incident_history`, 1 in `get_vessel_context`). The likely cause is that the prompt's tool inputs do not match the real tool schemas (for example a `limit` above the maximum of 25). The researcher retries and still answered all 12 questions, but each error costs time.

## 5. Next Steps

1. Ingest the 45 `extra/` messages: batch them, and `MERGE` onto canonical IDs so the LLM cannot mint duplicates.
2. Generate the researcher prompt's tool signatures from the MCP schemas to remove the tool errors.
3. Add confidence scores to resolution, a different judge model, and N≥5 runs per question.

## 6. AI Tools

- **Claude:** Business and domain research, evaluation dataset preparation, documentation, and general research.
- **Antigravity:** Development. Design decisions, workflows, the coding plan and the technical stack were defined and verified before any code was generated, and the generated code was reviewed manually.
