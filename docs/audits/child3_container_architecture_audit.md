# Comprehensive Cloud Run Container Architecture & Well-Architected Audit
**Target Codebase**: `mercadona-ai-companion` (`/usr/local/google/home/mgandolfi/mercadona-ai-companion`)  
**Deployment Target**: Google Cloud Run (`europe-west1`, Project: `mercadona-ia-companion`)  
**Author**: Container Architecture & Cloud Security Engineering Audit  
**Date**: September 2026  
**Status**: Critical Architecture Review & Hardening Blueprint  

---

## Executive Summary

An exhaustive container architecture, operational lifecycle, security posture, and deployment topology audit was conducted on the **Mercadona AI Companion** repository. The ecosystem comprises two serverless microservices deployed to Google Cloud Run (`mercadona-ai-companion` and `campaign-library`), connecting 5,000 Thermomix Cookidoo recipes and 1,595 Mercadona products with Google Gemini generative models.

The current implementation exhibits notable functional design choices (in-memory caching for sub-millisecond retrieval, client/server guardrails, dual-service reuse of codebase). However, from a **Production Google Cloud Architecture and Security** standpoint, multiple critical vulnerabilities and operational antipatterns exist:
1. **Container Security**: The container executes as the privileged `root` user (`uid 0`), lacks multi-stage builds, leaves secrets baked in or defaults exposed, and relies on loose version pinning in `requirements.txt`.
2. **Container Lifecycle & Signal Handling**: The entrypoint utilizes standard Python standard library `http.server.ThreadingHTTPServer` without trapping `SIGTERM` or `SIGINT`. During Cloud Run autoscaling scale-down or rolling deployments, incoming and in-flight HTTP requests (such as 15–20s Gemini LLM inference generation) are violently terminated via `SIGKILL` after the 10s shutdown window, causing user-facing 502/504 errors.
3. **Observability & Logging**: While `PYTHONUNBUFFERED=1` is configured, logging is virtually non-existent (relying on a single startup `print` and default `BaseHTTPRequestHandler.log_message` stderr plain-text dumps), failing Google Cloud Logging structured payload requirements (`severity`, `logging.googleapis.com/trace`, `httpRequest`).
4. **Microservice Topology & Dual Deployment**: Both services deploy identical source trees differentiated solely by `SERVICE_ROLE`. Microservice synchronization uses an ephemeral local JSON file write combined with point-to-point HTTP POST calls authenticated via an insecure shared secret or untrusted header, failing completely in multi-instance horizontal scaling. Furthermore, deploying with `--allow-unauthenticated` while attempting application-level verification of `X-Goog-Authenticated-User-Email` introduces a severe spoofing risk if the service is directly reachable outside an authentic IAP/Cloud Load Balancer perimeter.
5. **IAM & Resource Allocation**: Deployments omit `--service-account`, binding Cloud Run directly to the Compute Engine default service account (`PROJECT_NUMBER-compute@developer.gserviceaccount.com` with broad `Editor` rights). Deployments also omit explicit memory, CPU, concurrency, min/max instances, and execution timeouts.

---

## Section 1: Container Image & Security Deep-Dive

### 1.1 Root User Execution (Vulnerability Analysis)
- **Current State**:
  ```dockerfile
  FROM python:3.12-slim
  WORKDIR /app
  ...
  COPY . .
  CMD ["python3", "server.py"]
  ```
  The container has no `USER` instruction, defaulting to `root` (`uid=0, gid=0`).
- **Risk Assessment**:
  In Cloud Run (gVisor container sandbox), running as root violates the principle of least privilege. In the event of a remote code execution (RCE) vulnerability or path traversal vulnerability in third-party libraries (e.g., in dependency parsers or Cookidoo API wrappers), an attacker gains root access within the container mount. While gVisor isolates the host kernel, root within the container allows reading sensitive process memory, modifying binary packages, altering cached files in `/app/data/`, or tampering with runtime configurations.
- **Remediation**:
  Create an unprivileged system user and group (`appuser:appgroup`, UID 10001) with dedicated ownership of `/app` and `/app/data`.

### 1.2 Dependency Management & Pinning
- **Current State (`requirements.txt`)**:
  ```text
  cookidoo-api>=0.13.0
  aiohttp>=3.9.0
  google-genai>=1.0.0
  python-dotenv>=1.0.0
  ```
- **Vulnerabilities**:
  1. Loose `>=` range constraints allow unvetted patch/minor releases during rebuilds. Breaking API changes or compromised upstream wheels can silently break builds or introduce malicious code (supply-chain attack).
  2. Sub-dependencies (transitive dependencies) are entirely unpinned and unhashed (no SHA256 hashes).
  3. No build tools or vulnerability scanning (`pip-audit`, Trivy, Artifact Analysis) integrated in the container build.
- **Remediation**:
  Implement a deterministic lockfile (e.g., via `pip-tools` or `uv.lock`) with cryptographic hashes (`--require-hashes`) and automated vulnerability scanning in Artifact Registry / Cloud Build.

### 1.3 Container Layers & Build Hygiene
- **Current State**:
  - Base image: `python:3.12-slim` (Debian-based).
  - Single-stage build copying all workspace artifacts: `COPY . .` copies `.git`, test files, documentation, and raw caches into the production image.
  - Environment variable secrets: `ENV ALLOWED_USERS="..."` hardcodes user emails directly into image metadata layers, exposing internal organizational information to anyone with image pull permissions.
- **Remediation**:
  Use a multi-stage Dockerfile or strict `.dockerignore` to strip `.git`, `.venv`, `tests/`, `docs/`, and temporary caches. Move configuration and user allowlists strictly to Cloud Run environment variables or Secret Manager, not baked Dockerfile `ENV`.

---

## Section 2: Process Execution, Server Engine & Signals Handling

### 2.1 The Cloud Run Termination Lifecycle
Google Cloud Run orchestrates dynamic scaling. When an instance is targeted for scale-down, replacement, or deployment:
1. Cloud Run stops routing new incoming requests to the instance.
2. Cloud Run sends a `SIGTERM` signal to the process with PID 1.
3. The instance enters a **grace period** (default 10 seconds, configurable up to service timeout) to finish processing in-flight requests and exit cleanly (`exit 0`).
4. If the process does not terminate within the grace period, Cloud Run delivers `SIGKILL`, immediately destroying the container and abruptly aborting active TCP streams.

### 2.2 Analysis of Current Process Execution
- **Dockerfile Entrypoint**:
  ```dockerfile
  CMD ["python3", "server.py"]
  ```
  Because the exec form `["python3", "server.py"]` is used (rather than the shell form `CMD python3 server.py`), `python3` correctly runs as PID 1.
- **Server Engine Flaws in `server.py`**:
  ```python
  def run_server() -> None:
      port = int(os.environ.get("PORT", "8080"))
      server = ThreadingHTTPServer(("0.0.0.0", port), CompanionRequestHandler)
      print(f"Mercadona Service ({SERVICE_ROLE}) listening on http://0.0.0.0:{port}")
      server.serve_forever()
  ```
  1. **No Signal Handlers**: Neither `signal.signal(signal.SIGTERM, ...)` nor `signal.signal(signal.SIGINT, ...)` is registered.
  2. **`ThreadingHTTPServer.serve_forever()` Behavior**: In Python, when `SIGTERM` is received by default, Python terminates abruptly with exit code 143 (`128 + 15`), terminating daemon threads instantly without draining socket connections.
  3. **In-Flight Gemini Invocations**: Generating a full 5-day meal plan via `build_weekly_plan` with constraint validation and Mercadona catalog matching takes between 6 to 18 seconds. If a scale-down event occurs while an inference request is in progress, the client experiences an unhandled dropped socket (`HTTP 502 Bad Gateway` from the Cloud Run frontend proxy).
  4. **Production Server Suitability**: `ThreadingHTTPServer` is a toy development server from Python's standard library. It lacks keep-alive connection pooling optimization, HTTP/2 multiplexing, backpressure, and request queue management. It creates unbounded OS threads for concurrent requests, presenting a severe memory exhaustion risk under concurrent load.
- **Remediation**:
  Migrate to an enterprise ASGI/WSGI production server (such as `Uvicorn` with `FastAPI` or `Starlette`, or `Gunicorn` with Uvicorn worker class). If remaining on pure Python standard library in the interim, implement explicit `signal.SIGTERM` trapping that triggers `server.shutdown()`, waits for active worker threads to drain, and flushes data before exiting cleanly.

---

## Section 3: Unbuffered Logging & Cloud Logging Observability

### 3.1 Unbuffered I/O
- **Current State**: `ENV PYTHONUNBUFFERED=1` is correctly declared in `Dockerfile`. This ensures Python does not buffer stdout/stderr streams, which is mandatory in containerized environments to prevent delayed log emission.

### 3.2 Log Formatting & Cloud Logging Ingestion
- **Current Deficiencies**:
  1. **Plain-Text Unstructured Output**: The application emits unstructured strings via `print()` or standard `BaseHTTPRequestHandler.log_message()` stderr prints:
     `"127.0.0.1 - - [27/Sep/2026 22:08:43] "GET /api/catalog HTTP/1.1" 200 -`
  2. **Missing Google Cloud Logging Special Fields**:
     Google Cloud Logging relies on JSON-formatted stdout to parse metadata. Without structured JSON, all logs appear as `DEFAULT` or `INFO` severity, even fatal unhandled exceptions.
     The following key fields are absent:
     - `severity`: Log levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
     - `message`: Human-readable summary.
     - `logging.googleapis.com/trace`: Correlating log entries with Cloud Trace spans across microservices.
     - `httpRequest`: Request protocol, status code, latency, user agent, and response size.
     - `serviceContext`: Service name and release version.
  3. **Silent Exception Swallowing**:
     Across `server.py` and `campaign_service.py`, exceptions are caught with `except Exception:` and silenced without logging:
     ```python
     except Exception:
         continue # or pass
     ```
     This creates black-box failure modes where network partitions, Gemini API quota limits, and sync failures vanish without a trace.
- **Remediation**:
  Implement a structured JSON logging handler writing directly to `sys.stdout` formatting according to Google Cloud Logging specification, extracting `X-Cloud-Trace-Context` headers for distributed tracing.

---

## Section 4: Architecture & Deployment Topology Evaluation

### 4.1 Single Codebase, Dual-Service Deployment Antipattern
- **Observation**:
  `deploy.sh` deploys the entire repository twice:
  - Instance 1: `mercadona-ai-companion` with `SERVICE_ROLE=companion`
  - Instance 2: `campaign-library` with `SERVICE_ROLE=campaign-library`
- **Architectural Implications**:
  - *Advantages*: Single Git repository, zero drift between shared data structures (`cookidoo_recipes.json`, `mercadona_products.json`, Gemini prompts).
  - *Severe Disadvantages*:
    1. Redundant footprint: Both containers carry all assets (HTML, static images, marketing UI, client UI, all backend modules) even though each service only serves half of the routes.
    2. Shared State Anti-Pattern: `campaign-library` writes local state to disk (`data/campaigns.json` via `save_local_campaigns`). Cloud Run containers have an ephemeral, in-memory writable filesystem (`tmpfs`). Any changes written to disk are lost when the container recycles, restarts, or scales to 0!
    3. Split-Brain Condition: In a multi-container deployment (e.g., 3 instances of `campaign-library` and 5 instances of `mercadona-ai-companion`), updating a campaign on instance A only writes to instance A's local container memory. The other instances continue serving stale data.

### 4.2 Point-to-Point Microservice Sync Flaws
- **Analysis of `/api/campaigns/sync` and `push_sync_to_peer_services`**:
  ```python
  def push_sync_to_peer_services(campaigns):
      # Pushes via HTTP POST to COMPANION_APP_URL/api/campaigns/sync
  ```
  - When `push_sync_to_peer_services` calls `https://mercadona-ai-companion-...run.app/api/campaigns/sync`, Google Cloud Run Load Balancer routes that request to **exactly ONE** container instance!
  - If `mercadona-ai-companion` has 4 instances running, instance 1 receives the push and updates its local disk/RAM. Instances 2, 3, and 4 receive nothing.
  - End users accessing instances 2, 3, and 4 see old campaigns, creating inconsistent state across user sessions.
- **Remediation**:
  Decouple state from local disk. Store campaign definitions and user sessions in an external serverless persistence tier (Google Cloud Firestore in Datastore mode, Cloud Storage bucket with object versioning, or Memorystore Redis), using Cloud Pub/Sub or Firestore real-time listeners for change notifications.

### 4.3 Direct `--allow-unauthenticated` vs IAP Spoofing Risk
- **Current Deployment Flags**:
  ```bash
  gcloud run deploy ... --allow-unauthenticated --no-invoker-iam-check
  ```
- **Code Authentication Logic**:
  ```python
  def _get_iap_email(self):
      iap_email = self.headers.get("X-Goog-Authenticated-User-Email", "").strip()
      if iap_email:
          return iap_email.split(":")[-1].strip().lower()
      return None
  ```
- **Security Vulnerability (Critical)**:
  `--allow-unauthenticated` opens the Cloud Run default URL (`*.run.app`) directly to the public internet without requiring Cloud IAM authentication.
  When an HTTP request is made directly to the Cloud Run `.run.app` URL by a malicious user:
  - If the service is not strictly gated behind an external HTTPS Application Load Balancer with IAP, or if direct ingress to `.run.app` is permitted (`--ingress all`), **an external attacker can inject `X-Goog-Authenticated-User-Email: accounts.google.com:mgandolfi@google.com` as a plain HTTP request header**.
  - `_get_iap_email()` trusts this header without validating the cryptographic **IAP JWT signature** (`X-Goog-IAP-JWT-Assertion`).
  - The attacker bypasses authentication completely and acts as an authorized administrator!
- **Remediation**:
  1. Cryptographically verify the `X-Goog-IAP-JWT-Assertion` header using Google public keys (`https://www.gstatic.com/iap/verify/public_key-jwk`) and verify the `aud` claim matches the expected project number and backend service ID.
  2. In Cloud Run, set `--ingress internal-and-cloud-load-balancing` so the service cannot be reached directly via `run.app` bypassing IAP.
  3. Deploy with `--no-allow-unauthenticated` and configure IAP with service account invoker IAM bindings.

---

## Section 5: IAM Service Account & Resource Sizing Audit

### 5.1 Service Account Least Privilege Violation
- **Current State in `deploy.sh`**:
  No `--service-account` parameter is passed in `gcloud run deploy`.
- **Impact**:
  Cloud Run automatically attaches the **Default Compute Engine service account**:
  `[PROJECT_NUMBER]-compute@developer.gserviceaccount.com`
  By default, Google Cloud grants this service account the primitive `Editor` (`roles/editor`) role on the entire GCP project!
  This permits:
  - Full read/write/delete access across all Cloud Storage buckets, BigQuery datasets, Cloud SQL instances, and Secret Manager secrets in the project.
  - Potential lateral privilege escalation across the cloud environment.
- **Remediation**:
  Create dedicated runtime service accounts with minimal required permissions:
  - Service Account: `sa-mercadona-companion@mercadona-ia-companion.iam.gserviceaccount.com`
  - Assigned Roles:
    - `roles/aiplatform.user` (to call Gemini models via Vertex AI)
    - `roles/logging.logWriter` (to write structured application logs)
    - `roles/monitoring.metricWriter` (for telemetry)
    - `roles/secretmanager.secretAccessor` (if reading API keys or secrets)

### 5.2 Compute Resource Sizing & Concurrency
- **Missing Parameters in `deploy.sh`**:
  - `--memory`: Defaults to 512MiB. In-memory caching of 5,000 Cookidoo recipes and 1,595 Mercadona products plus Python runtime overhead consumes ~280–380MiB. Under heavy concurrency, memory spikes will trigger Linux OOM kills.
  - `--cpu`: Defaults to 1 vCPU.
  - `--concurrency`: Defaults to 80 concurrent requests per instance. With Python standard `ThreadingHTTPServer` and GIL contention, 80 concurrent requests will cause CPU starvation and timeout spikes.
  - `--min-instances`: Not set (defaults to 0). Cold starts with Python runtime initialization and JSON catalog parsing take 3.5 to 5.0 seconds.
  - `--max-instances`: Not set (defaults to 100). Exposes the project to runaway billing if subjected to denial-of-service traffic.
  - `--timeout`: Defaults to 300s (5 minutes). Generative prompts should time out gracefully at 30–60 seconds.
  - `--cpu-throttling`: By default, Cloud Run throttles CPU outside of request processing. Any background sync or async tasks freeze unless `--no-cpu-throttling` is specified.

---

## Section 6: Well-Architected Framework Gap Analysis & Concrete Hardening Plan

| Pillar | Current Architecture Gaps | Hardening Solution |
| :--- | :--- | :--- |
| **Security** | 1. Container runs as root (`uid 0`).<br>2. Transitive dependencies unpinned.<br>3. `--allow-unauthenticated` with unverified `X-Goog-Authenticated-User-Email` header spoofing.<br>4. Default Compute Engine service account (`roles/editor`).<br>5. Hardcoded `SESSION_SECRET` fallback in code. | 1. Add `USER appuser` in Dockerfile.<br>2. Pin lockfile with cryptographic hashes.<br>3. Verify `X-Goog-IAP-JWT-Assertion` cryptographically and restrict ingress to `internal-and-cloud-load-balancing`.<br>4. Create dedicated least-privilege IAM service account.<br>5. Store secrets in Secret Manager. |
| **Reliability** | 1. No `SIGTERM` trap for graceful container draining.<br>2. `ThreadingHTTPServer` drops in-flight connections on scale-down.<br>3. Local JSON file state (`campaigns.json`) lost on scale-to-zero or container restart.<br>4. Point-to-point HTTP sync hits only 1 random container instance in multi-instance pools. | 1. Register signal handlers for `SIGTERM`/`SIGINT` with graceful server shutdown and active request draining.<br>2. Migrate state to Cloud Firestore / Cloud Storage.<br>3. Adopt asynchronous event-driven synchronization or centralized database lookup. |
| **Operational Excellence** | 1. Plain text stderr logs without severity levels.<br>2. No Cloud Trace correlation.<br>3. Silent `except Exception: pass` concealing errors.<br>4. Lack of automated CI/CD container vulnerability scanning. | 1. Structured JSON logging with `severity`, `logging.googleapis.com/trace`, and `httpRequest`.<br>2. Proper error logging with stack traces.<br>3. Continuous automated scanning in Cloud Build. |
| **Performance** | 1. Standard library `ThreadingHTTPServer` suffers from thread spawning overhead and GIL bottlenecks.<br>2. Concurrency defaulted to 80, exceeding Python single-process capacity.<br>3. Cold start delays (3–5s) due to unprimed catalog loading. | 1. Sizing: `--concurrency 20`, `--memory 1Gi`, `--cpu 1`.<br>2. Pre-parse and serialize catalogs during container build or prime on startup.<br>3. Set `--min-instances 1` for zero cold-start latency on primary user endpoints. |
| **Cost Optimization** | 1. Unbounded `--max-instances` risks uncontrolled autoscaling.<br>2. Two independent Cloud Run services running identical code and duplicate catalog copies in memory. | 1. Set explicit `--max-instances 10`.<br>2. Unify microservice deployment or deploy distinct optimized container images with trimmed dependencies. |

---

## Section 7: Implementation Blueprints

### 7.1 Production-Hardened `Dockerfile`
```dockerfile
# Stage 1: Build & Dependency Resolution
FROM python:3.12-slim AS builder

WORKDIR /build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Minimal Distroless / Hardened Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Security: Create dedicated unprivileged non-root user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /app appuser

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source code with non-root ownership
COPY --chown=appuser:appgroup . .

# Ensure data directory is writable by appuser
RUN mkdir -p /app/data && chown -R appuser:appgroup /app/data

# Drop privileges
USER appuser:appgroup

EXPOSE 8080

# Run server with exec form so python receives SIGTERM (PID 1)
CMD ["python3", "server.py"]
```

### 7.2 Graceful Shutdown & Structured Logging (`server.py` enhancements)
```python
import json
import logging
import os
import signal
import sys
import threading
import time
from http.server import ThreadingHTTPServer

class CloudLoggingFormatter(logging.Formatter):
    """Formats log records as structured JSON for Google Cloud Logging."""
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "timestamp": {"seconds": int(time.time()), "nanos": 0},
            "logging.googleapis.com/sourceLocation": {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            },
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

def run_server() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), CompanionRequestHandler)
    
    # Graceful shutdown event
    shutdown_event = threading.Event()

    def handle_sigterm(signum, frame):
        sys.stdout.write(json.dumps({"severity": "INFO", "message": "Received SIGTERM. Initiating graceful drain..."}) + "\n")
        sys.stdout.flush()
        # Shutdown server socket in background thread to unblock serve_forever
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    sys.stdout.write(json.dumps({
        "severity": "INFO",
        "message": f"Mercadona Service ({SERVICE_ROLE}) listening on port {port}",
    }) + "\n")
    sys.stdout.flush()

    server.serve_forever()
    server.server_close()
    sys.stdout.write(json.dumps({"severity": "INFO", "message": "Server stopped cleanly."}) + "\n")
    sys.stdout.flush()
```

### 7.3 Production-Hardened `deploy.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-mercadona-ia-companion}"
REGION="${REGION:-europe-west1}"
SERVICE_ACCOUNT="sa-mercadona-companion@${PROJECT_ID}.iam.gserviceaccount.com"

# Deploy campaign-library with least privilege and deterministic resource bounds
gcloud run deploy campaign-library \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --ingress internal-and-cloud-load-balancing \
  --no-allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --concurrency 20 \
  --min-instances 0 \
  --max-instances 10 \
  --timeout 60 \
  --set-env-vars="SERVICE_ROLE=campaign-library,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GEMINI_MODEL=gemini-3.8-flash"

# Deploy mercadona-ai-companion with warmed instance
gcloud run deploy mercadona-ai-companion \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --ingress internal-and-cloud-load-balancing \
  --no-allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --concurrency 20 \
  --min-instances 1 \
  --max-instances 10 \
  --timeout 60 \
  --set-env-vars="SERVICE_ROLE=companion,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GEMINI_MODEL=gemini-3.8-flash"
```
