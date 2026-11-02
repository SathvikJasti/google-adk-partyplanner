# Party planner on GCP: how it runs and why

This is a **test deployment** to learn how the system behaves on GCP. It is built to cost
nothing and to need no extra IAM rights on a shared project. It is not production, and
section 6 says what would change for production.

- GCP project: `eternal-nucleus-513516-a2` (shared), region `us-east4`
- Service: `pp-party-planner` (Cloud Run), image `us-east4-docker.pkg.dev/eternal-nucleus-513516-a2/pp-images/party-planner`
- URL: https://pp-party-planner-34656130941.us-east4.run.app

## 1. What is running

One Cloud Run service with **four containers in one instance**, all from the same image
(the `SERVICE` env var chooses which program a container runs):

| Container | Port | Reachable from | Role |
|---|---|---|---|
| `planner` (module `agents`) | 8000 | Public | ADK web UI and API. The only agent that talks to users. |
| `mcp` (`mcp_server`) | 8002 | Planner only | MCP server (Streamable HTTP, `/mcp`): venues, catering, entertainment, and a live weather forecast from the public Open-Meteo API (`get_weather_forecast`). |
| `budget` (`budget_agent`) | 8001 | Planner only | A2A agent: prices options, recommends one. |
| `compliance` (`compliance_agent`) | 8003 | Planner only | A2A agent: permits, curfew, alcohol, supervision. |

The containers of an instance share a network, so the planner reaches the others at
`127.0.0.1:8001-8003`. These are the defaults in `common/config.py`, so no env vars are needed.

```
Browser ─HTTPS─► run.app URL ─► planner :8000 ─┬─ MCP ► 127.0.0.1:8002/mcp
                                               ├─ A2A ► 127.0.0.1:8001   (budget)
                                               └─ A2A ► 127.0.0.1:8003   (compliance)
planner, budget, compliance ─► Gemini API (outbound HTTPS)
all containers ─► logs: Cloud Logging;  traces/metrics/logs: OTLP ─► tunnel ─► Grafana on a dev PC
```

The only call that leaves GCP's own network (besides Gemini) is the MCP server's weather
lookup: `geocoding-api.open-meteo.com` and `api.open-meteo.com`, free, no key, 5 s timeout. It
only has forecasts for about the next 16 days, so for later dates the tool returns
`available=false` and the planner says no forecast exists.

A request: the user message reaches the planner, which asks Gemini what to do, calls MCP
tools for data, delegates to the budget and compliance agents over A2A (JSON-RPC, SSE
streaming), and writes the final plan.

## 2. Decisions and why

| Decision | Why | What it costs us |
|---|---|---|
| **Free-tier only, scale to zero** (min 0, max 1 instance) | The goal is to test, not to run a service. Cloud Run's free tier covers a few users. | First request after idle is slow (cold start, 4 containers). |
| **One service with sidecars, not four services** | Separate private services need `roles/run.invoker` granted to a service account. Developer accounts on this project can't change IAM, so that was impossible. Sidecars need no IAM and no public URLs, and they are still separate processes talking HTTP/A2A, as in the original design. | The agents can't scale or deploy separately, share CPU and memory, and a crash in one container restarts the instance. |
| **Max 1 instance** | ADK sessions are in memory. With 2+ instances, a follow-up message can hit an instance that doesn't know the session. It also caps cost. | No horizontal scaling. A restart or scale-to-zero loses sessions. |
| **Gemini API key (free tier), not Vertex AI** | Vertex bills per token. A free-tier AI Studio key costs nothing. The key must come from a project without billing. | Rate limits and occasional 503/429. Free-tier data may be used by Google. |
| **Key stored as a plain env var** | Secret Manager access also needs IAM rights we don't have. | Anyone who can view the service config can read it. Rotate it when the test ends. |
| **Retries on every Gemini call** (`common/llm.py`) | One planning request makes many model calls, and a single "503 high demand" failed the whole request. 6 attempts with backoff, about a minute. | A request can take longer when the model is busy. |
| **Region `us-east4`** | Closest to the team (New York). | None. |
| **Public URL for the planner** | The project owner granted `allUsers` the invoker role so the UI opens in a browser without the `gcloud` proxy. | The ADK UI has no login. Anyone with the link can use it and spend our Gemini quota. Don't share the link. |
| **Image built on a dev PC, not Cloud Build** | The Cloud Build service account lacks storage permissions on this project, and we can't grant them. Docker build and push to Artifact Registry works. | Needs Docker on whoever deploys. |
| **ADK origin allow-list** (`ALLOW_ORIGINS`) | ADK's dev UI rejects requests whose browser Origin doesn't match the server host. Behind a proxy that gave a blank page (403 on every script). | One more env var to keep right. |

## 3. Why OpenTelemetry, Prometheus, Tempo, Loki and Grafana run on a laptop

- **Cloud Run can't host them for free.** It has no persistent disk, and idle instances are
  stopped, so Tempo, Prometheus and Loki would lose their data. Keeping them on a VM costs
  about $30 a month, against a zero-cost goal.
- **So the stack runs locally** (`observability/docker-compose.yml`), and the cloud service
  sends OpenTelemetry to it over a free Cloudflare tunnel. Your existing dashboards work with
  `deployment_environment = gcp`.
- **Security:** only the collector's port 4319 is exposed through the tunnel, and it requires
  a bearer token (`OTEL_INGEST_TOKEN` in `observability/.env`, gitignored). Port 4318 stays
  open for local runs.
- **Limits:** telemetry only flows while the PC, Docker and tunnel are up. The tunnel URL
  changes on every restart, so you redeploy with the new URL. Steps are in
  [deploy/gcp/telemetry.md](../deploy/gcp/telemetry.md).
- **Why `OTEL_TRACES_SAMPLER=always_on`:** Cloud Run's front end marks requests "not sampled",
  and the default sampler then drops almost every span. Without this setting traces look empty.
- **Cloud Logging** also works without any of this. Every container's stdout lands there.

## 4. How to check what the agents are calling

**Fastest: the ADK UI.** Open the service URL, send a message, and use the **Events** and
**Traces** tabs to see each tool call and agent hand-off.

**Grafana (best view).** Run the stack locally, set the tunnel up, then
**Explore → Tempo**. Useful queries:
```
{resource.deployment.environment="gcp"}                                  # all cloud traces
{resource.service.name="party_planner" && name=~"MCP send.*"}            # MCP calls
{name=~"execute_tool.*"}                                                 # every tool the agents ran
{resource.service.name="budget_agent"}                                   # spans inside the budget agent
```
Span names to know: `invoke_agent <name>`, `execute_tool <tool>`, `MCP send tools/call
<tool>`, `a2a.client...send_message_streaming` (planner calling an agent),
`generate_content gemini-...` (a model call). The HTTP client spans (`GET`, `POST`) carry the
URL called in the `url.full` attribute, for example calls to the public weather API:
`{resource.service.name="mcp_server" && span.url.full=~".*open-meteo.*"}`. One request is a single trace across all four services.

**Cloud Logging (no setup).** Console → Logging → Logs Explorer:
```
resource.type="cloud_run_revision"
resource.labels.service_name="pp-party-planner"
textPayload:"HTTP Request"
```
The HTTP client library logs every call, for example
`HTTP Request: POST http://127.0.0.1:8001/ "HTTP/1.1 200 OK"`. The port tells you who was
called: 8001 budget, 8002 MCP, 8003 compliance. From a terminal:
`gcloud run services logs read pp-party-planner --region us-east4 --limit 100`.

**Agent cards** (what an A2A agent advertises) are at `/.well-known/agent-card.json` on its
port. The sidecars aren't reachable from outside, so read them from a local run
(`uv run python -m budget_agent`, then `curl localhost:8001/.well-known/agent-card.json`).

## 5. Operating it

| Task | How |
|---|---|
| Deploy or update | `bash deploy/gcp/deploy.sh` (needs `gcloud`, Docker, and `GOOGLE_API_KEY` in `.env`). Add `TUNNEL_URL=https://<x>.trycloudflare.com` for telemetry. |
| Open the UI | The service URL. If public access is removed: `gcloud run services proxy pp-party-planner --region us-east4 --port 8080`, then http://localhost:8080 |
| See logs | Section 4, or the **Logs** tab of the service in the console |
| Remove everything | `bash deploy/gcp/teardown.sh` (service, image repo, secret, service account) |

Everything we created is named `pp-*` and labelled `app=party-planner`, so it is easy to
find in the shared project.

## 6. Known limits, and what production would change

| Now | For production |
|---|---|
| Sidecars, 1 instance | Separate Cloud Run services per agent with ID-token auth between them (`common/auth.py` and `SERVICE_AUTH=true` are already in the code), which needs the invoker role granted |
| In-memory sessions | A persistent session service (Cloud SQL or Vertex AI sessions) so instances can scale out |
| Public planner with no login | IAP or authenticated access |
| API key in an env var | Secret Manager |
| Telemetry through a laptop tunnel | A hosted backend (Google Cloud Trace/Monitoring/Logging, or Grafana Cloud) |
| Free-tier Gemini key | Vertex AI with a service account |
| Image built on a PC | Cloud Build or CI with the right roles |

Original plan (before we hit the IAM limits): [deploy/gcp/PLAN.md](../deploy/gcp/PLAN.md).
