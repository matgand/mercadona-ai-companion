# WAF Audit Report: Cloud Run & Gemini API Integration

**Service / Workload**: Mercadona AI Companion & Campaign Library  
**Target Environment**: Google Cloud Run (`europe-west1`), Google Cloud Platform (`mercadona-ia-companion`)  
**Auditor**: Auditor 6 — Cloud Run & Gemini API Integration Specialist  
**Evaluation Standards**:
- Google Cloud Well-Architected Framework (Operational Excellence, Security, Reliability, Performance, Cost Optimization)
- Official Skill: `cloud-run-basics` (`//depot/google3/third_party/skills/skills/cloud/cloud-run-basics/SKILL.md`)
- Official Skill: `gemini-api` (`//depot/google3/third_party/skills/skills/cloud/gemini-api/SKILL.md`)
- Related Audits: [`child3_container_architecture_audit.md`](child3_container_architecture_audit.md)

---

## 1. Executive Summary & Architecture Scorecard

A thorough, line-by-line inspection of the entire codebase was conducted across all core modules:
- Server & Network Layer: `server.py`
- Core LLM Planning Engine: `gemini_planner.py`
- Catalog & Basket Services: `mercadona_service.py`, `cookidoo_service.py`
- Marketing Microservice: `campaign_service.py`
- Packaging & Infrastructure as Code: `Dockerfile`, `deploy.sh`, `requirements.txt`

The application exhibits several commendable architectural decisions:
1. **Pre-LLM Deterministic Guardrails**: `validate_meal_planning_prompt` in `gemini_planner.py` executes strict regex classification against prompt injections, code generation, and off-topic requests before any Gemini API tokens are consumed.
2. **Hybrid LLM + Deterministic Recovery**: If the LLM call times out, encounters quota limits, or returns partial outputs, the application deterministically completes the plan from local validated catalogs (`5,000 Cookidoo recipes` + `Mercadona Tienda API snapshot`).
3. **Dual Execution Mode**: Supports both Google Cloud Enterprise (Vertex AI) with Application Default Credentials (ADC) and Google AI Studio API key fallback.

However, several critical architectural and operational vulnerabilities exist across container security, lifecycle signal handling, cross-region latency, and structured schema validation that must be addressed for enterprise-grade production readiness.

### Architecture Scorecard

| Domain | Pillar | Score (1–5) | Key Findings |
|---|---|:---:|---|
| **Gemini SDK & API** | Reliability & Performance | 3.5 / 5 | Uses modern `google-genai` SDK, but hardcodes `us-central1` (cross-region latency from `europe-west1`), uses deprecated `vertexai=True` instead of `enterprise=True`, omits `response_json_schema`, and includes deprecated `gemini-2.0-flash` in fallback chain. |
| **Container & Security** | Security | 2.0 / 5 | Runs as `root` (UID 0), no multi-stage build, unpinned dependencies (`>=`), bakes corporate emails in Dockerfile `ENV`, and accepts unverified `X-Goog-Authenticated-User-Email` on unauthenticated Cloud Run endpoints. |
| **Process Lifecycle** | Reliability | 2.5 / 5 | No `SIGTERM`/`SIGINT` handling in `ThreadingHTTPServer`; scale-down and rolling deployments cause immediate connection abortion and HTTP 502/504 errors on long LLM requests. |
| **Observability & Logging** | Operational Excellence | 2.5 / 5 | `PYTHONUNBUFFERED=1` is enabled, but logs are unstructured plaintext `print()` statements without Cloud Logging JSON format, severity levels, or trace context correlation. Critical errors are silently swallowed with `except Exception: pass`. |
| **IAM & Sizing** | Least Privilege & Cost | 2.0 / 5 | `deploy.sh` omits `--service-account` (defaults to Compute Engine default service account with Project Editor role), omits CPU/memory bounds, and omits concurrency/min-instances tuning. Ephemeral local disk is used for stateful campaigns. |

---

## 2. Gemini API & SDK Integration Deep-Dive

### 2.1 SDK Usage: `google-genai` vs Direct REST Calls
The codebase declares `google-genai>=1.0.0` in `requirements.txt`. Both `gemini_planner.py` (lines 459–464) and `campaign_service.py` (lines 332–337) import and instantiate:
```python
from google import genai
from google.genai import types

project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID") or "mercadona-ia-companion"
client = genai.Client(vertexai=True, project=project_id, location="us-central1")
```

#### Deficiencies Identified:
1. **Deprecated Kwarg (`vertexai=True`)**:
   Under the Gemini Enterprise Agent Platform guidelines, `genai.Client(enterprise=True, ...)` or zero-argument initialization `genai.Client()` with `GOOGLE_GENAI_USE_ENTERPRISE=true` is the canonical standard. While `vertexai=True` is aliased in 1.x, it represents legacy naming.
2. **Cross-Region Latency & Data Residency**:
   Cloud Run runs in `europe-west1` (Belgium). The Gemini client hardcodes `location="us-central1"`. Every planning turn introduces transatlantic latency (~110–130ms RTT) and routes European grocery and household data outside the EU.
   - *Fix*: Use `location="global"` (for global endpoint dynamic capacity routing) or set `GOOGLE_CLOUD_LOCATION="europe-west1"`.
3. **Client Instantiation Inside Request Path**:
   `genai.Client(...)` is instantiated inside `_call_gemini_flash_selector` and `_call_gemini_campaign_generator` on each request, forcing redundant credential checks and connection pool setups.
   - *Fix*: Cache a thread-safe singleton client at module initialization.
4. **Asymmetric AI Studio REST Fallback**:
   `gemini_planner.py` implements direct REST fallback via `urllib.request` to Google AI Studio if Vertex AI fails. However, `campaign_service.py` only implements Vertex AI without AI Studio fallback. Both should use a unified generation abstraction.

### 2.2 System Instruction Design & Grounding
- **Planner Prompt**: Correctly sets the persona ("planificador oficial de menús semanales de Mercadona × Thermomix Cookidoo") and binds the candidate set strictly to provided `candidates`.
- **Campaign Prompt**: Establishes marketing copiloting roles and profiles ("Familias", "Saludables", "Rutina rápida", "Ahorro").
- **Flaws Identified**:
  - *Hardcoded Model Name in Prompt*: Instructions explicitly include string `"impulsado por Gemini 3.8 Flash"`. If the fallback model (`gemini-2.5-flash`) executes, the prompt contains an internal contradiction.
  - *Day Count Assumption*: The instruction specifies `"en orden de Lunes a Viernes"` (assuming 5 days), but users can request 1 to 7 days (`mealCount`).
  - *Missing Negative Constraints*: Does not explicitly forbid markdown wrapping (e.g. ````json ... ````) or inventing IDs outside `candidates`.

### 2.3 Response Schema Validation & Structured Outputs
- **Current State**: Uses `response_mime_type="application/json"`, but **omits `response_json_schema`**.
- **Impact**: Without schema enforcement, Gemini may output unexpected keys, nested formats, or conversational prefixes. Furthermore, `json.loads(resp.text)` will throw an unhandled `JSONDecodeError` if the model includes markdown backticks, leading to immediate silent fallback.
- **Remediation**: Pass Pydantic models via `types.GenerateContentConfig(response_json_schema=WeeklyPlanSelection)`.

### 2.4 Temperature, Token Bounds & Decoding Parameters
- Planner uses `temperature=0.2` (optimal for strict candidate selection).
- Campaign generator uses `temperature=0.35` (appropriate for copywriting).
- **Missing Limits**: `max_output_tokens` is omitted in both modules. Unbounded token limits introduce latency risks and streaming stalls. `max_output_tokens=1024` should be set.

### 2.5 Model Selection & Fallback Chain
- Primary: `gemini-3.8-flash` (compliant with current recommendation).
- Fallback: `gemini-2.5-flash` (supported stable version).
- Tertiary: `gemini-2.0-flash` (line 465 in `gemini_planner.py` and line 338 in `campaign_service.py`).
  - *Finding*: `gemini-2.0-*` is deprecated per the `gemini-api` skill. Replace with `gemini-3.5-flash-lite`.

---

## 3. Cloud Run Container Architecture Deep-Dive

### 3.1 Container Security & Dockerfile Review
```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    GEMINI_MODEL=gemini-3.8-flash \
    ALLOWED_USERS="matgand@gmail.com,mgandolfi@google.com,andrea.anaut@gmail.com,mattia@mgandolfi.altostrat.com"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python3", "server.py"]
```
#### Deficiencies Identified:
1. **Root User Execution (Critical Security Vulnerability)**:
   The container does not specify `USER`. All processes execute as `root` (UID 0). While gVisor isolates the host kernel, any path traversal or dependency exploit provides root within the container filesystem.
2. **Hardcoded Secrets & Identifiers in Image Layers**:
   `ENV ALLOWED_USERS="..."` bakes corporate emails directly into the container image manifest. Anyone with pull access to Artifact Registry can read these emails.
3. **No Multi-Stage Build & Bloated Context**:
   `COPY . .` copies `.git`, documentation, scratch files, and tests into production. A `.dockerignore` file is omitted.
4. **Unpinned Dependencies**:
   `requirements.txt` specifies minimum bounds (`>=`) rather than pinned versions with hashes, exposing builds to upstream dependency poisoning.

### 3.2 Process Execution & Signal Handling
- **Exec Form**: `CMD ["python3", "server.py"]` runs Python directly as PID 1, allowing OS signals to reach Python.
- **Missing SIGTERM Trapping (Severe Reliability Defect)**:
  `server.py` runs `ThreadingHTTPServer.serve_forever()`. When Cloud Run scales down or rolls out a revision, it transmits `SIGTERM` followed by a 10s grace period. Because `ThreadingHTTPServer` does not trap `SIGTERM`, active connections running Gemini calls (6–18s) are abruptly killed, returning HTTP 502 Bad Gateway to users.
- **Inadequate Web Server Engine**:
  Python standard library `ThreadingHTTPServer` spawns a raw thread per connection without HTTP/2 support, keep-alive pooling, or connection queuing. Under concurrent traffic, Python's Global Interpreter Lock (GIL) and memory footprint will thrash.

### 3.3 Logging & Cloud Logging Observability
- `ENV PYTHONUNBUFFERED=1` is correctly configured.
- However, logging relies on raw `print()` statements and `BaseHTTPRequestHandler.log_message()` to stderr.
- Logs lack Google Cloud Logging JSON formatting (`severity`, `logging.googleapis.com/trace`, `message`, `httpRequest`).
- **Silent Failure Masking**:
  Extensive use of `except Exception: pass` and `continue` across `campaign_service.py` (lines 169, 221, 250, 282, 355) and `server.py` suppresses 403 Forbidden, 429 Rate Limit, and network partition errors.

### 3.4 Architecture, Statefulness & Microservice Topology
1. **Stateless Cloud Run vs. Local Disk Antipattern (Critical Reliability Defect)**:
   In `campaign_service.py`, campaigns are stored in `data/campaigns.json` using local disk I/O (`save_local_campaigns`). In Cloud Run, the local filesystem is ephemeral and in-memory (`tmpfs`). When an instance scales to zero or restarts, all new marketing campaigns are erased.
2. **Broken Horizontal Peer Sync**:
   `push_sync_to_peer_services` executes an HTTP POST to `/api/campaigns/sync`. In Cloud Run, this POST reaches only **one single instance** behind the load balancer, leaving all other instances in the revision out of sync (split-brain state).
   - *Fix*: Externalize campaigns to Google Cloud Firestore or Cloud Storage with Cloud Storage FUSE / Pub/Sub notifications.
3. **Insecure Application-Level IAP Header Trust**:
   `deploy.sh` uses `--allow-unauthenticated --no-invoker-iam-check`. `server.py` trusts `X-Goog-Authenticated-User-Email` directly without verifying the cryptographic signature `X-Goog-IAP-JWT-Assertion`. Anyone hitting the `.run.app` endpoint can spoof this header and bypass authentication.

### 3.5 IAM Least Privilege & Resource Sizing (`deploy.sh`)
- **Missing Service Account**:
  `deploy.sh` does not specify `--service-account`. It defaults to `PROJECT_NUMBER-compute@developer.gserviceaccount.com`, which carries the `roles/editor` role project-wide.
  - *Fix*: Create and bind a dedicated service account: `sa-mercadona-companion@mercadona-ia-companion.iam.gserviceaccount.com` with `roles/aiplatform.user` and `roles/logging.logWriter`.
- **Missing Resource Flags**:
  - No `--memory` (defaults to 512MiB, high risk of OOM during 5,000-recipe catalog scans).
  - No `--cpu` (defaults to 1 vCPU).
  - No `--concurrency` (defaults to 80, far too high for Python ThreadingHTTPServer GIL). Recommended: `concurrency=20`.
  - No `--min-instances` (defaults to 0, inducing 3–5s cold start penalties). Recommended: `min-instances=1`.
  - No `--max-instances` (defaults to 100, risking runaway bills during attack). Recommended: `max-instances=10`.

---

## 4. Well-Architected Framework Recommendations

```
+-----------------------------------------------------------------------------------+
|               Google Cloud Well-Architected Hardening Roadmap                     |
+-----------------------------------------------------------------------------------+
| 1. SECURITY                                                                       |
|    - Switch Dockerfile to unprivileged user (UID 10001: appuser).                 |
|    - Cryptographically verify `X-Goog-IAP-JWT-Assertion` public key certificates. |
|    - Deploy dedicated Least-Privilege Service Account (`sa-mercadona-companion`). |
|    - Remove emails from Dockerfile `ENV`; inject via Secret Manager / Runtime env.|
+-----------------------------------------------------------------------------------+
| 2. RELIABILITY                                                                    |
|    - Implement SIGTERM/SIGINT signal handling for zero-downtime draining (10s).   |
|    - Externalize campaign storage from ephemeral local disk to Cloud Firestore.   |
|    - Enforce Pydantic schema validation (`response_json_schema`) on Gemini calls. |
|    - Upgrade fallback model from deprecated `gemini-2.0-flash` to `gemini-3.5`.   |
+-----------------------------------------------------------------------------------+
| 3. PERFORMANCE & LATENCY                                                          |
|    - Change Gemini client location from `us-central1` to `global` / `europe-west1`|
|    - Cache singleton `genai.Client` to reuse HTTP connection pools.               |
|    - Replace standard `ThreadingHTTPServer` with production ASGI/WSGI (Uvicorn).  |
|    - Set `--min-instances=1` and `--concurrency=20` on Cloud Run.                 |
+-----------------------------------------------------------------------------------+
| 4. OPERATIONAL EXCELLENCE & OBSERVABILITY                                         |
|    - Replace raw `print()` with Cloud Logging Structured JSON.                    |
|    - Eliminate silent `except Exception: pass` blocks; log error payloads.        |
+-----------------------------------------------------------------------------------+
```

---

## 5. Concrete Code Implementation Blueprints

### Blueprint A: Production Multi-Stage Hardened `Dockerfile`
```dockerfile
# Multi-stage build for minimal attack surface
FROM python:3.12-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Final runtime image
FROM python:3.12-slim

WORKDIR /app

# Create dedicated non-root application user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /app appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    GOOGLE_GENAI_USE_ENTERPRISE=true \
    GOOGLE_CLOUD_LOCATION=global

COPY --from=builder /install /usr/local
COPY --chown=appuser:appgroup . /app

# Drop root privileges
USER appuser:appgroup

EXPOSE 8080
CMD ["python3", "server.py"]
```

### Blueprint B: Graceful Signal Handling & Structured Logging in `server.py`
```python
import logging
import signal
import sys
import threading
from http.server import ThreadingHTTPServer

class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": self.formatTime(record, self.datefmt),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(StructuredJsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("mercadona-server")

def run_server() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), CompanionRequestHandler)
    
    # Graceful SIGTERM/SIGINT shutdown handler
    def handle_shutdown(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful drain...")
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info(f"Mercadona Service ({SERVICE_ROLE}) listening on port {port}")
    server.serve_forever()
    server.server_close()
    logger.info("Server successfully shut down.")
```

### Blueprint C: Enterprise Gemini Client & Structured Schema in `gemini_planner.py`
```python
import os
import logging
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

logger = logging.getLogger("gemini-planner")

_CLIENT: genai.Client | None = None

def get_gemini_client() -> genai.Client:
    global _CLIENT
    if _CLIENT is None:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or "mercadona-ia-companion"
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
        # Follows official Gemini Enterprise Agent Platform guidelines
        _CLIENT = genai.Client(enterprise=True, project=project_id, location=location)
    return _CLIENT

class WeeklyPlanSelection(BaseModel):
    headline: str = Field(description="Título editorial en español para el menú semanal")
    summary: str = Field(description="Resumen explicativo del menú y ahorro de despensa")
    selected_recipe_ids: list[str] = Field(description="Array de strings con los recipe_id seleccionados")

def call_gemini_selector(prompt: str, constraints: dict, candidates: list[dict]) -> dict | None:
    client = get_gemini_client()
    for model_name in [MODEL_PRIMARY, MODEL_FALLBACK, "gemini-3.5-flash-lite"]:
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=json.dumps({"prompt": prompt, "constraints": constraints, "candidates": candidates[:30]}),
                config=types.GenerateContentConfig(
                    system_instruction="Eres el planificador oficial de menús semanales de Mercadona...",
                    temperature=0.2,
                    max_output_tokens=1024,
                    response_mime_type="application/json",
                    response_json_schema=WeeklyPlanSelection,
                ),
            )
            if resp and resp.text:
                return json.loads(resp.text)
        except Exception as exc:
            logger.warning(f"Error calling {model_name}: {exc}")
            continue
    return None
```

### Blueprint D: Hardened Production `deploy.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-mercadona-ai-companion}"
CAMPAIGN_SERVICE_NAME="${CAMPAIGN_SERVICE_NAME:-campaign-library}"
REGION="${REGION:-europe-west1}"
PROJECT_ID="${PROJECT_ID:-mercadona-ia-companion}"
SA_NAME="sa-mercadona-companion"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Deploy with Least Privilege Service Account, Resource Bounds & Concurrency tuning
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --service-account "${SA_EMAIL}" \
  --cpu=1 \
  --memory=1Gi \
  --concurrency=20 \
  --min-instances=1 \
  --max-instances=10 \
  --timeout=60s \
  --set-env-vars="SERVICE_ROLE=companion,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=global,GEMINI_MODEL=gemini-3.8-flash"
```

---

## 6. Conclusion
The Mercadona AI Companion demonstrates exceptional domain modeling and robust deterministic pre-filtering and post-recovery logic. By resolving the container security posture (non-root user), implementing graceful SIGTERM signal draining, aligning the Gemini SDK with enterprise standards (`enterprise=True`, `location="global"`, Pydantic `response_json_schema`), and binding a least-privilege service account, the architecture will fully comply with Google Cloud Well-Architected Framework standards.
