#!/usr/bin/env bash
set -euo pipefail

# Automated deployment script for Google Cloud Run
SERVICE_NAME="${SERVICE_NAME:-mercadona-ai-companion}"
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

echo "==> Habilitando APIs necesarias en ${PROJECT_ID} (Cloud Run, Cloud Build, Artifact Registry)..."
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski" \
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project "${PROJECT_ID}"

echo "==> Desplegando ${SERVICE_NAME} en Google Cloud Run (Proyecto: ${PROJECT_ID}, Región: ${REGION})..."
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski" \
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars="^;^GEMINI_MODEL=${GEMINI_MODEL};ALLOWED_USERS=${ALLOWED_USERS};GEMINI_API_KEY=${GEMINI_API_KEY:-}"

echo "==> ¡Despliegue completado!"
