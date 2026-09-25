#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/google-cloud-sdk/bin:$PATH"

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

echo "==> Habilitando APIs necesarias en ${PROJECT_ID} (Cloud Run, Cloud Build, Artifact Registry, Vertex AI)..."
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski" \
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  --project "${PROJECT_ID}"

echo "==> Configurando permisos IAM para Cloud Build y Vertex AI en la cuenta de servicio por defecto..."
PROJECT_NUMBER=$(CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski" gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for ROLE in \
  "roles/storage.admin" \
  "roles/artifactregistry.writer" \
  "roles/logging.logWriter" \
  "roles/aiplatform.user"; do
  CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski" \
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="${ROLE}" \
    --condition=None \
    --quiet >/dev/null
done

echo "==> Desplegando ${SERVICE_NAME} en Google Cloud Run (Proyecto: ${PROJECT_ID}, Región: ${REGION})..."
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.jetski" \
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --no-invoker-iam-check \
  --quiet \
  --set-env-vars="^;^GOOGLE_CLOUD_PROJECT=${PROJECT_ID};GEMINI_MODEL=${GEMINI_MODEL};ALLOWED_USERS=${ALLOWED_USERS};GEMINI_API_KEY=${GEMINI_API_KEY:-}"

echo "==> ¡Despliegue completado!"
