#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/google-cloud-sdk/bin:$PATH"

# Automated deployment script for Google Cloud Run (both mercadona-ai-companion and campaign-library microservices)
SERVICE_NAME="${SERVICE_NAME:-mercadona-ai-companion}"
CAMPAIGN_SERVICE_NAME="${CAMPAIGN_SERVICE_NAME:-campaign-library}"
REGION="${REGION:-europe-west1}"
PROJECT_ID="${PROJECT_ID:-mercadona-ia-companion}"
ACCOUNT="${ACCOUNT:-mattia@mgandolfi.altostrat.com}"
ALLOWED_USERS="${ALLOWED_USERS:-matgand@gmail.com,mgandolfi@google.com,andrea.anaut@gmail.com,mattia@mgandolfi.altostrat.com}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"

echo "==> Configurando proyecto '${PROJECT_ID}' y cuenta '${ACCOUNT}'..."
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski" \
gcloud config set account "${ACCOUNT}"

CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski" \
gcloud config set project "${PROJECT_ID}"

PROJECT_NUMBER=$(CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski" gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
COMPANION_URL="https://${SERVICE_NAME}-${PROJECT_NUMBER}.${REGION}.run.app"
CAMPAIGN_LIBRARY_URL="https://${CAMPAIGN_SERVICE_NAME}-${PROJECT_NUMBER}.${REGION}.run.app"
SESSION_SECRET="${SESSION_SECRET:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"

echo "==> Desplegando microservicio 1/2: ${CAMPAIGN_SERVICE_NAME} en Google Cloud Run (${REGION})..."
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski" \
gcloud run deploy "${CAMPAIGN_SERVICE_NAME}" \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --no-invoker-iam-check \
  --iap \
  --quiet \
  --set-env-vars="^;^SERVICE_ROLE=campaign-library;GOOGLE_CLOUD_PROJECT=${PROJECT_ID};GEMINI_MODEL=${GEMINI_MODEL};ALLOWED_USERS=${ALLOWED_USERS};COMPANION_APP_URL=${COMPANION_URL};CAMPAIGN_LIBRARY_URL=${CAMPAIGN_LIBRARY_URL};SESSION_SECRET=${SESSION_SECRET};GEMINI_API_KEY=${GEMINI_API_KEY:-}"

echo "==> Desplegando microservicio 2/2: ${SERVICE_NAME} en Google Cloud Run (${REGION})..."
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski" \
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --no-invoker-iam-check \
  --iap \
  --quiet \
  --set-env-vars="^;^SERVICE_ROLE=companion;GOOGLE_CLOUD_PROJECT=${PROJECT_ID};GEMINI_MODEL=${GEMINI_MODEL};ALLOWED_USERS=${ALLOWED_USERS};COMPANION_APP_URL=${COMPANION_URL};CAMPAIGN_LIBRARY_URL=${CAMPAIGN_LIBRARY_URL};SESSION_SECRET=${SESSION_SECRET};GEMINI_API_KEY=${GEMINI_API_KEY:-}"

echo "==> ¡Despliegue completado!"
echo "    - Mercadona AI Companion: ${COMPANION_URL}"
echo "    - Campaign Library:       ${CAMPAIGN_LIBRARY_URL}"
