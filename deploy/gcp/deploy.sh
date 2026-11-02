#!/usr/bin/env bash
# Deploy the party planner to Cloud Run (zero-cost test setup). See PLAN.md.
# Run from the repo root in Git Bash / WSL:  bash deploy/gcp/deploy.sh
# Not yet run end to end: expect to fix small things on the first pass.
set -euo pipefail

PROJECT=eternal-nucleus-513516-a2
PROJECT_NUMBER=34656130941
REGION=us-east4
SA=pp-runtime@${PROJECT}.iam.gserviceaccount.com
IMAGE=${REGION}-docker.pkg.dev/${PROJECT}/pp-images/party-planner:latest
LABELS=app=party-planner,env=test

gcloud config set project "$PROJECT"

echo "== APIs"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

echo "== service account, registry, secret"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 ||
  gcloud iam service-accounts create pp-runtime --display-name "Party planner runtime"
gcloud artifacts repositories describe pp-images --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create pp-images --repository-format=docker --location "$REGION" --labels "$LABELS"

# GOOGLE_API_KEY from .env: must be a Gemini API key from a project WITHOUT billing (free tier).
KEY=$(grep -E '^GOOGLE_API_KEY=' .env | cut -d= -f2-)
if gcloud secrets describe pp-google-api-key >/dev/null 2>&1; then
  printf %s "$KEY" | gcloud secrets versions add pp-google-api-key --data-file=-
else
  printf %s "$KEY" | gcloud secrets create pp-google-api-key --data-file=- --labels "$LABELS"
fi
gcloud secrets add-iam-policy-binding pp-google-api-key \
  --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor >/dev/null

echo "== build and push"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker build -t "$IMAGE" .
docker push "$IMAGE"

# Cloud Run URLs are deterministic: https://<service>-<project number>.<region>.run.app
url() { echo "https://$1-${PROJECT_NUMBER}.${REGION}.run.app"; }
MCP_URL=$(url pp-mcp-server); BUDGET_URL=$(url pp-budget-agent); COMPLIANCE_URL=$(url pp-compliance-agent)

# $1 name, $2 port, $3 module, $4.. extra env
deploy() {
  local name=$1 port=$2 module=$3; shift 3
  gcloud run deploy "$name" --image "$IMAGE" --region "$REGION" --service-account "$SA" \
    --no-allow-unauthenticated --port "$port" --command python --args "-m,$module" \
    --min-instances 0 --max-instances 1 --cpu 1 --memory 512Mi --timeout 900 --labels "$LABELS" \
    --set-env-vars "^@^BIND_HOST=0.0.0.0@SERVICE_AUTH=true@GOOGLE_GENAI_USE_VERTEXAI=FALSE@MCP_SERVER_URL=${MCP_URL}/mcp@BUDGET_AGENT_URL=${BUDGET_URL}@COMPLIANCE_AGENT_URL=${COMPLIANCE_URL}$*" \
    --set-secrets GOOGLE_API_KEY=pp-google-api-key:latest
}

echo "== deploy backends"
deploy pp-mcp-server 8002 mcp_server "@MCP_SERVER_PORT=8002"
deploy pp-budget-agent 8001 budget_agent "@BUDGET_AGENT_PORT=8001"
deploy pp-compliance-agent 8003 compliance_agent "@COMPLIANCE_AGENT_PORT=8003"

echo "== deploy planner"
deploy pp-party-planner 8000 agents "@PARTY_PLANNER_PORT=8000"

echo "== let the planner call the backends"
for s in pp-mcp-server pp-budget-agent pp-compliance-agent; do
  gcloud run services add-iam-policy-binding "$s" --region "$REGION" \
    --member "serviceAccount:$SA" --role roles/run.invoker >/dev/null
done

echo
echo "Done. Open the planner UI with:"
echo "  gcloud run services proxy pp-party-planner --region $REGION --port 8000"
echo "(needs roles/run.invoker on pp-party-planner for your account; you're likely owner already)"
