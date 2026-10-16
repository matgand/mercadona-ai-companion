#!/usr/bin/env bash
# Deploys the 2 Cloud Run Microservices for Mercadona AI Meal Planner:
#   1. campaign-library (Library & Campaign Manager AI Microservice)
#   2. mercadona-ai-companion (Main Customer Companion App)
# Both services enforce Google Identity-Aware Proxy (IAP), Cloud Run IAM invoker checks,
# and a shared cryptographic SESSION_SECRET for internal service-to-service sync.

set -euo pipefail
export PATH="$HOME/google-cloud-sdk/bin:$PATH"
export CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski"

PROJECT_ID="${PROJECT_ID:-mercadona-ia-companion}"
ACCOUNT="${ACCOUNT:-mattia@mgandolfi.altostrat.com}"
REGION="${REGION:-europe-west1}"
COMPANION_SERVICE="${SERVICE_NAME:-mercadona-ai-companion}"
LIBRARY_SERVICE="${LIBRARY_SERVICE_NAME:-campaign-library}"

gcloud config set account "$ACCOUNT" >/dev/null
gcloud config set project "$PROJECT_ID" >/dev/null

DEFAULT_ALLOWED="matgand@gmail.com,mgandolfi@google.com,andrea.anaut@gmail.com,mattia@mgandolfi.altostrat.com,barea@google.com,estherarribas@google.com,iolalla@google.com,jamarmu@google.com,lauramarse@google.com,cmartintomas@google.com,veronicapg@google.com,mikelju@gmail.com"
ALLOWED_USERS="${ALLOWED_USERS:-$DEFAULT_ALLOWED}"

if [[ -z "${SESSION_SECRET:-}" ]]; then
  SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
fi

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
IAP_SA="service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com"
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "================================================================================"
echo "1/2 Deploying Microservice 1: ${LIBRARY_SERVICE} (Library & Campaign Manager)"
echo "    Project: ${PROJECT_ID} | Region: ${REGION}"
echo "================================================================================"

gcloud beta run deploy "$LIBRARY_SERVICE" \
  --quiet \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --source . \
  --no-build \
  --base-image python312 \
  --command "python3" \
  --args="server.py" \
  --platform managed \
  --iap \
  --invoker-iam-check \
  --memory 512Mi \
  --cpu 1 \
  --timeout 60s \
  --update-env-vars="^;^SERVICE_ROLE=campaign-library;GOOGLE_CLOUD_PROJECT=${PROJECT_ID};GCP_PROJECT_ID=${PROJECT_ID};GCP_LOCATION=${REGION};ALLOWED_USERS=${ALLOWED_USERS};ENFORCE_IAP_JWT=1;HIDE_ALLOWED_USERS_UNAUTHED=1;ALLOW_LOCAL_DEV_FALLBACK=0;SESSION_SECRET=${SESSION_SECRET}"

LIBRARY_URL="$(gcloud run services describe "$LIBRARY_SERVICE" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)')"
echo "Library Service URL: ${LIBRARY_URL}"

echo "================================================================================"
echo "2/2 Deploying Microservice 2: ${COMPANION_SERVICE} (Customer Companion App)"
echo "================================================================================"

gcloud beta run deploy "$COMPANION_SERVICE" \
  --quiet \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --source . \
  --no-build \
  --base-image python312 \
  --command "python3" \
  --args="server.py" \
  --platform managed \
  --iap \
  --invoker-iam-check \
  --memory 512Mi \
  --cpu 1 \
  --timeout 60s \
  --update-env-vars="^;^SERVICE_ROLE=companion;CAMPAIGN_LIBRARY_URL=${LIBRARY_URL};GOOGLE_CLOUD_PROJECT=${PROJECT_ID};GCP_PROJECT_ID=${PROJECT_ID};GCP_LOCATION=${REGION};ALLOWED_USERS=${ALLOWED_USERS};ENFORCE_IAP_JWT=1;HIDE_ALLOWED_USERS_UNAUTHED=1;ALLOW_LOCAL_DEV_FALLBACK=0;SESSION_SECRET=${SESSION_SECRET}"

COMPANION_URL="$(gcloud run services describe "$COMPANION_SERVICE" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)')"

# Link Companion URL back to Campaign Library for bi-directional push sync
gcloud run services update "$LIBRARY_SERVICE" \
  --quiet \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --update-env-vars="COMPANION_APP_URL=${COMPANION_URL}"

echo "================================================================================"
echo "Configuring Defense-in-Depth IAM & IAP Accessors"
echo "================================================================================"
for SVC in "$COMPANION_SERVICE" "$LIBRARY_SERVICE"; do
  # Ensure allUsers cannot invoke the service directly bypassing IAP
  gcloud run services remove-iam-policy-binding "$SVC" \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --member="allUsers" \
    --role="roles/run.invoker" --quiet >/dev/null 2>&1 || true

  # Grant invoker strictly to IAP Service Agent and peer Cloud Run Service Account
  for SA in "$IAP_SA" "$COMPUTE_SA"; do
    gcloud run services add-iam-policy-binding "$SVC" \
      --project "$PROJECT_ID" \
      --region "$REGION" \
      --member="serviceAccount:${SA}" \
      --role="roles/run.invoker" --quiet >/dev/null
  done
done

for SVC in "$COMPANION_SERVICE" "$LIBRARY_SERVICE"; do
  gcloud beta iap web add-iam-policy-binding \
    --quiet \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --resource-type=cloud-run \
    --service="$SVC" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/iap.httpsResourceAccessor" >/dev/null
done

IFS=',' read -ra USER_LIST <<< "$ALLOWED_USERS"
for EMAIL in "${USER_LIST[@]}"; do
  CLEAN_EMAIL="$(echo "$EMAIL" | xargs)"
  if [[ -n "$CLEAN_EMAIL" ]]; then
    for SVC in "$COMPANION_SERVICE" "$LIBRARY_SERVICE"; do
      gcloud beta iap web add-iam-policy-binding \
        --quiet \
        --project="$PROJECT_ID" \
        --region="$REGION" \
        --resource-type=cloud-run \
        --service="$SVC" \
        --member="user:${CLEAN_EMAIL}" \
        --role="roles/iap.httpsResourceAccessor" >/dev/null
    done
  fi
done

echo ""
echo "Both microservices deployed and secured with Google Cloud IAP + IAM Defense-in-Depth:"
echo "  - Companion App:    ${COMPANION_URL}"
echo "  - Campaign Library: ${LIBRARY_URL}"
