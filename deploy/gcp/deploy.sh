#!/usr/bin/env bash
# Deploy the party planner to Cloud Run as ONE service with four containers (zero-cost test).
# The planner is the ingress container; MCP server and both A2A agents are sidecars that it
# reaches on 127.0.0.1:8001-8003, so no service-to-service IAM is needed. Needs gcloud and a
# running Docker. Run from the repo root:  bash deploy/gcp/deploy.sh   (key read from .env)
set -euo pipefail

PROJECT=eternal-nucleus-513516-a2
REGION=us-east4
SA=pp-runtime@${PROJECT}.iam.gserviceaccount.com
IMAGE=${REGION}-docker.pkg.dev/${PROJECT}/pp-images/party-planner:latest

gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com
gcloud artifacts repositories describe pp-images --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create pp-images --repository-format=docker --location "$REGION" --labels app=party-planner,env=test

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker build --provenance=false -t "$IMAGE" .
docker push "$IMAGE"

# Free-tier Gemini key (from a project without billing). A plain env var, because Secret Manager
# access needs IAM rights; rotate it when done.
KEY=$(grep -E '^GOOGLE_API_KEY=' .env | cut -d= -f2- | tr -d '"'"'")

# Telemetry goes to the local Grafana stack through a tunnel (see deploy/gcp/telemetry.md):
# TUNNEL_URL=https://xxxx.trycloudflare.com bash deploy/gcp/deploy.sh   (omit to deploy without telemetry)
# Token comes from observability/.env. Uses ^@^ as the list delimiter because values contain commas.
OTEL=""
if [ -n "${TUNNEL_URL:-}" ]; then
  TOKEN=$(grep -E '^OTEL_INGEST_TOKEN=' observability/.env | cut -d= -f2)
  OTEL="@OTEL_EXPORTER_OTLP_ENDPOINT=${TUNNEL_URL}@OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf@OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer%20${TOKEN}@OTEL_RESOURCE_ATTRIBUTES=service.namespace=party-planner,deployment.environment=gcp@OTEL_METRIC_EXPORT_INTERVAL=10000@OTEL_TRACES_SAMPLER=always_on@OTEL_BSP_SCHEDULE_DELAY=500@OTEL_BLRP_SCHEDULE_DELAY=500@OTEL_SEMCONV_STABILITY_OPT_IN=http@OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT"
fi
# Origins the ADK web UI accepts: localhost on any port (gcloud run services proxy) and the service URL.
ORIGINS="regex:https?://(localhost|127[.]0[.]0[.]1)(:[0-9]+)?,https://pp-party-planner-34656130941.${REGION}.run.app"
env_for() { echo "^@^SERVICE=$1@GOOGLE_API_KEY=$KEY@GOOGLE_GENAI_USE_VERTEXAI=FALSE@ALLOW_ORIGINS=$ORIGINS$OTEL"; }

gcloud run deploy pp-party-planner --region "$REGION" --service-account "$SA"   --min-instances 0 --max-instances 1 --timeout 900 --labels app=party-planner,env=test   --container planner --image "$IMAGE" --port 8000 --cpu 1 --memory 1Gi --set-env-vars "$(env_for agents)"   --container mcp --image "$IMAGE" --cpu 0.5 --memory 512Mi --set-env-vars "$(env_for mcp_server)"   --container budget --image "$IMAGE" --cpu 0.5 --memory 512Mi --set-env-vars "$(env_for budget_agent)"   --container compliance --image "$IMAGE" --cpu 0.5 --memory 512Mi --set-env-vars "$(env_for compliance_agent)"

echo "Open the UI with: gcloud run services proxy pp-party-planner --region $REGION --port 8080"
