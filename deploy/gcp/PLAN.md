# GCP deployment plan (zero-cost test setup)

> **As deployed (2026-11-02):** one Cloud Run service, `pp-party-planner`, with four containers
> from one image: the planner (ingress, :8000) plus the MCP server and both A2A agents as
> sidecars reached on 127.0.0.1:8001-8003. The account used couldn't grant IAM roles, so the
> separate-service design below (private services calling each other) wasn't possible. Sidecars
> keep the agents as separate processes talking HTTP/A2A, need no IAM and no public URLs.
> The Gemini key is a plain env var (no Secret Manager rights). See [deploy.sh](deploy.sh).
> The sections below describe the original plan.

Project: `eternal-nucleus-513516-a2` (number `34656130941`), **shared**.
Region: **us-east4** (Northern Virginia, the closest region to New York).
Goal: try the system on GCP as the only user, paying nothing.

## 1. Architecture

```
 you ── gcloud run services proxy (IAM, localhost:8000)
          │
          ▼
 pp-party-planner (Cloud Run :8000) ── Gemini API (free-tier key from Secret Manager)
      ├─ MCP  ─► pp-mcp-server        (Cloud Run :8002, private)
      ├─ A2A  ─► pp-budget-agent      (Cloud Run :8001, private)
      └─ A2A  ─► pp-compliance-agent  (Cloud Run :8003, private)

 logs ── stdout ──► Cloud Logging (free allotment)
 traces/metrics ── OTLP (optional) ──► Grafana Cloud free tier, if you have one
```

Four Cloud Run services built from **one image** (`Dockerfile` at the repo
root; the service is chosen by the command). Backends are private; the
planner calls them with Google ID tokens (`common/auth.py`, enabled by
`SERVICE_AUTH=true`).

## 2. How each part stays free

| Item | Choice | Cost |
|---|---|---|
| Compute | Cloud Run, min instances 0, max instances 1 per service | Inside the monthly free tier (2M requests, 180k vCPU-s, 360k GiB-s) for single-user testing. |
| Gemini | **Gemini API key on the free tier** (the `GOOGLE_API_KEY` you already use), not Vertex AI | Free, rate-limited. Vertex AI bills per token, so I'm not using it. The key must come from a project **without billing** (AI Studio makes these), or calls turn paid. |
| Key storage | Secret Manager (one secret) | Free up to 6 active secret versions. |
| Observability | No VM. stdout goes to Cloud Logging; OTLP export is off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set | Free. A VM running the Grafana stack costs about $30/month, so it's out. |
| Images | Artifact Registry repo `pp-images`, built locally with Docker (not Cloud Build) | First 0.5 GB free, then $0.10/GB-month. The image may be near that size, so worst case is cents per month; teardown deletes the repo. |
| Network | Default Cloud Run URLs, no VPC, no load balancer, no static IP | Free. Egress between services is tiny (1 GB/month free). |

Safety net: a **$1 budget alert** on the project. Budgets only email you; they
don't stop spending. What actually caps it is max-instances 1, no VM, and the
teardown in section 7 when you're done.

Caveat: Cloud Run needs billing enabled on the project even when you stay in
the free tier. Check that the shared project's billing account is acceptable
to whoever owns it.

## 3. Using your existing Grafana

- The Grafana on your laptop (`observability/docker-compose.yml`) can't be
  reached from Cloud Run, because it's behind your machine's localhost.
- If you have a **Grafana Cloud** account, it's a drop-in: set
  `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS` (Grafana
  Cloud's OTLP endpoint and token) on the four services. No code change. The
  free tier is enough for this test. Please tell me if you have one.
- **Decision: no Grafana Cloud account, so use Google Cloud observability.** Logs in Cloud Logging, request metrics in Cloud Monitoring, request traces in Cloud Trace, all automatic on Cloud Run and free at this volume. Detailed OTel spans (LLM and tool calls) can be exported to Cloud Trace later with a small code change.

Run everything from **Cloud Shell** in the console (gcloud and Docker preinstalled, free): upload or clone the repo, create `.env` with `GOOGLE_API_KEY`, run `deploy.sh`, then `gcloud run services proxy pp-party-planner --region us-east4 --port 8080` and open Web Preview on port 8080.

## 4. Isolation inside the shared project

GCP projects have no sub-folders, so everything is namespaced:
- names start with `pp-`, labels `app=party-planner`
- one service account `pp-runtime`, with access only to what it needs
- teardown deletes only `pp-*` resources

A real GCP Folder holds projects. If you'd rather not share at all, create a
new project inside a folder and rerun the same steps with its ID.

## 5. Code changes (done in this repo, tested locally)

- [common/config.py](../../common/config.py): `SERVICE_AUTH` flag and `card_address()`.
- [budget_agent/agent.py](../../budget_agent/agent.py), [compliance_agent/agent.py](../../compliance_agent/agent.py): the agent card now publishes the service's own public URL, taken from `BUDGET_AGENT_URL` / `COMPLIANCE_AGENT_URL`. Locally nothing changes. With the Cloud Run URL set, the card shows `https://…run.app:443`.
- [common/auth.py](../../common/auth.py) (new) and [agents/party_planner/agent.py](../../agents/party_planner/agent.py): ID-token auth for the A2A and MCP calls, active only when `SERVICE_AUTH=true`.
- [common/telemetry.py](../../common/telemetry.py): with no `OTEL_EXPORTER_OTLP_ENDPOINT`, it skips OTLP exporters and logs to the console, instead of failing against a missing collector.
- [Dockerfile](../../Dockerfile) and [.dockerignore](../../.dockerignore) (new).

Not yet verified: the Docker build and the full Cloud Run run (`gcloud` isn't
installed on this machine). The first deploy will show any remaining issues.

## 6. Steps

**Prerequisites (you):** install the [gcloud CLI](https://cloud.google.com/sdk/docs/install),
run `gcloud auth login`, and make sure your account can enable APIs and create
Cloud Run services here (Cloud Run Admin, Artifact Registry Admin, Secret
Manager Admin, Service Account Admin, Service Usage Admin).

Then run [deploy.sh](deploy.sh) (Git Bash or WSL), which does, in order:

1. Enable APIs (Cloud Run, Artifact Registry, Secret Manager).
2. Create `pp-runtime`, the `pp-images` repo, and the `pp-google-api-key` secret (from your `.env`).
3. `docker build`, then push to `us-east4-docker.pkg.dev/eternal-nucleus-513516-a2/pp-images/party-planner`.
4. Deploy the three backends private, then the planner private, all `--max-instances=1`.
5. Grant `pp-runtime` invoker on the three backends.
6. Print the proxy command.

**Verify:**
```
gcloud run services proxy pp-party-planner --region us-east4 --port 8000
# open http://localhost:8000 and ask for a party plan
gcloud run services logs read pp-party-planner --region us-east4
```
Check each agent card at `…/.well-known/agent-card.json` shows its HTTPS URL.

## 7. Teardown (back to $0)

[teardown.sh](teardown.sh) deletes the four services, the image repo, the secret,
and the service account.

## 8. Known limits (fine for a test)

- ADK sessions are in memory. With one instance they work, but a restart or
  scale-to-zero loses them. Persistent sessions stay in deferred Phase 6.
- The first request after idle has a cold start of a few seconds.
- Free-tier Gemini limits can return 429s on long multi-agent runs; retry later.
- The MCP server's host check (`streamable_http_app(host=BIND_HOST)`) may reject
  the `run.app` Host header; `BIND_HOST=0.0.0.0` should disable it. Check this
  on first deploy.

## 9. Open questions

None blocking.
