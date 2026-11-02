#!/usr/bin/env bash
# Remove everything deploy.sh created (pp-* only). Back to $0.
set -uo pipefail

PROJECT=eternal-nucleus-513516-a2
REGION=us-east4
gcloud config set project "$PROJECT"

for s in pp-party-planner pp-mcp-server pp-budget-agent pp-compliance-agent; do
  gcloud run services delete "$s" --region "$REGION" --quiet
done
gcloud artifacts repositories delete pp-images --location "$REGION" --quiet
gcloud secrets delete pp-google-api-key --quiet
gcloud iam service-accounts delete "pp-runtime@${PROJECT}.iam.gserviceaccount.com" --quiet
