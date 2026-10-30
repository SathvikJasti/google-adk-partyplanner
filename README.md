# Party Planner: multi-agent system with ADK, A2A, MCP and OpenTelemetry

An orchestrator agent plans parties by pulling data from an MCP server and
delegating to two specialist agents over A2A. Each component runs as its own
service on its own port, and all of them send traces, metrics and logs to
Grafana through OpenTelemetry.

```
 Browser ──► ADK web UI / REST API   party_planner      :8000
                 │
                 ├── MCP, Streamable HTTP ────────► mcp_server        :8002/mcp
                 ├── A2A, HTTP JSON-RPC + SSE ────► budget_agent      :8001
                 └── A2A, HTTP JSON-RPC + SSE ────► compliance_agent  :8003

 every service ── OTLP/HTTP :4318 ──► OTel Collector ─┬─► Tempo       (traces)
                                                      ├─► Prometheus  (metrics)
                                                      └─► Loki        (logs)
                                                            └─► Grafana :3000
```

| Service | Folder | Port | What it does |
|---|---|---|---|
| `party_planner` | [agents/party_planner/](agents/party_planner/) | 8000 | Orchestrator, the only agent that talks to the user. Uses MCP tools, calls the specialists as tools, and writes the final plan. |
| `budget_agent` | [budget_agent/](budget_agent/) | 8001 | A2A server. Prices each option fully loaded (tax, service charge, fees, contingency) and recommends one. |
| `mcp_server` | [mcp_server/](mcp_server/) | 8002 | MCP server (`MCPServer`, Streamable HTTP). Venues, catering and entertainment data. |
| `compliance_agent` | [compliance_agent/](compliance_agent/) | 8003 | A2A server. Checks permits, curfew, alcohol and supervision rules. |

Each agent has its own `instructions.yaml` (model, description, prompt). The
model is `gemini-3.5-flash-lite`. Shared code lives in [common/](common/):
`config.py` (ports and URLs from env), `telemetry.py` (OTel setup) and
`health.py` (`/health` route).

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Python 3.12+, Docker Desktop, and a Gemini API key.

```powershell
uv sync
Copy-Item .env.example .env   # then set GOOGLE_API_KEY
```

## Run

```powershell
.\scripts\start-all.ps1       # Docker stack + 4 services, each in its own window
.\scripts\stop-all.ps1        # stop the services (add -Observability to stop Docker too)
```

`start-all.ps1 -Background` runs the services hidden, with logs in `.run\*.log`.
`-NoObservability` skips Docker.

To run a single service by hand (from the repo root):

```powershell
uv run python -m mcp_server        # :8002
uv run python -m budget_agent      # :8001
uv run python -m compliance_agent  # :8003
uv run python -m agents            # :8000, ADK web UI + API
```

Start the party planner last, because it calls the other three.

## Talk to the party planner

- **Web UI:** open http://localhost:8000, choose `party_planner`, and chat.
- **API**, for example from another app:

```powershell
$s = Invoke-RestMethod -Method Post http://127.0.0.1:8000/apps/party_planner/users/u1/sessions -ContentType application/json -Body '{}'
$body = @{ appName='party_planner'; userId='u1'; sessionId=$s.id
           newMessage=@{ role='user'; parts=@(@{ text='Plan a birthday in Austin on 2026-12-19, 18:00-22:00, 40 adults, budget 9000, vegetarian, with alcohol.' }) } } | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post http://127.0.0.1:8000/run -ContentType application/json -Body $body
```

Use `/run_sse` instead of `/run` to stream events as they happen.

## Observability (Grafana at http://localhost:3000)

Open **Dashboards → Party Planner → Party Planner - Agents, MCP & LLM**. It shows:

- **Overview:** planning requests, p95 end-to-end latency, 5xx ratio, LLM calls, tokens.
- **Agents & LLM:** agent invocation time, Gemini latency, token usage, and tool execution time.
- **Services, A2A & MCP:** HTTP traffic, A2A round trips, MCP tool calls, compliance results, budget fit.
- **Traces & logs:** service graph, recent requests (click one to open its trace), and logs from all services.

**One user request becomes one trace** across all four services. The W3C
`traceparent` travels in HTTP headers for A2A, and in each MCP message's
`_meta`. In **Explore → Tempo**, a trace shows each LLM call, each MCP
`tools/call`, and each specialist's own LLM and tool spans. From a span,
**Logs for this span** opens the matching Loki lines. In Loki, a log line's
`trace_id` links back to the trace.

Where the data comes from:

| Signal | Source |
|---|---|
| Agent, LLM and tool spans; `gen_ai_*` metrics | ADK and the Google GenAI instrumentation |
| `tools/call` spans on the MCP server | MCP Python SDK (built in) |
| HTTP server spans; `http_server_*` metrics | ASGI middleware ([common/telemetry.py](common/telemetry.py)) |
| Outgoing A2A and MCP calls | httpx instrumentation |
| `mcp_tool_calls`, `budget_evaluations`, `compliance_checks` | Custom counters in each service |
| Service graph, span metrics | Tempo metrics generator |

Backend ports: Prometheus :9090, Tempo :3200, Loki :3100, collector :4317/:4318.
To send telemetry somewhere else (for example Grafana Cloud), change the
exporters in [observability/otel-collector.yaml](observability/otel-collector.yaml).
The services don't need to change.

## Configuration

All settings come from env vars or `.env`; see [.env.example](.env.example).
Every port and service URL can be overridden (`BUDGET_AGENT_URL`,
`MCP_SERVER_URL`, ...), so the same code runs in containers or behind a load
balancer. Prompt and model changes go in each agent's `instructions.yaml`.

## Notes

- The party planner's chat sessions are saved in a local SQLite file
  (`agents/party_planner/.adk/session.db`). The specialists' A2A tasks are
  in-memory, and Grafana uses anonymous admin login. Before a real deployment,
  switch to a shared database (for example Postgres) and turn on authentication.
- Most of a request's time is spent in Gemini calls, about 8–12 per plan.
  Look at the "LLM call latency" panel before tuning anything else.
