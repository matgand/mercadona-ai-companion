#!/usr/bin/env bash
set -euo pipefail

# Automated deployment script for Google Cloud Run
SERVICE_NAME="${SERVICE_NAME:-mercadona-ai-companion}"
REGION="${REGION:-europe-west1}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
ALLOWED_USERS="${ALLOWED_USERS:-matgand@gmail.com,mgandolfi@google.com,andrea.anaut@gmail.com}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "Error: Define PROJECT_ID o configura 'gcloud config set project <PROJECT_ID>'."
  exit 1
fi

echo "==> Desplegando ${SERVICE_NAME} en Google Cloud Run (Proyecto: ${PROJECT_ID}, Región: ${REGION})..."

CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski" \
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars="GEMINI_MODEL=${GEMINI_MODEL},ALLOWED_USERS=${ALLOWED_USERS},GEMINI_API_KEY=${GEMINI_API_KEY:-}"

echo "==> ¡Despliegue completado!"
