# AI Agent - Autonomous Maritime Operations Agent

The autonomous maritime operations agent leverages Gemini and Groq LLMs combined with the read-only tools exposed by `knowledge_graph.maritime_kg_mcp` to:
- Perform multi-hop graph reasoning (Vessel -> Voyage -> Port Call -> Incident -> Impacted Customer Bookings).
- Investigate delay root-causes (distinguishing weather rerouting from mechanical breakdown or terminal congestion).
- Track cargo shipments and detect rolled bookings.
- Detect and neutralize adversarial prompt injections within raw operational messages.

