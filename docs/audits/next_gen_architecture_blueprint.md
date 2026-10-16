# Next-Generation Agentic Architecture & Cloud Observability Blueprint
## Mercadona AI Companion & Campaign Library Microservices

**Target Services:** `mercadona-ai-companion` & `campaign-library` (Google Cloud Run)  
**Target Environment:** Google Cloud Platform (`europe-west1`), Project: `mercadona-ia-companion`  
**Lead Architect:** Lead Subagent 5 — Next-Gen Agentic Architecture & Cloud Observability Architect  
**Date:** September 27, 2026  
**Status:** APPROVED FOR PRODUCTION IMPLEMENTATION  

---

## Executive Summary & System Evolution

The **Mercadona AI Companion** currently runs as a pair of containerized Python microservices deployed to Google Cloud Run in `europe-west1`:
1. `mercadona-ai-companion`: The customer-facing weekly menu planner, pairing Gemini 3.8 Flash inference with 5,000+ verified Thermomix Cookidoo recipes, dietary allergen filters, and 1-click Mercadona cart preparation.
2. `campaign-library`: The internal campaign microservice providing marketing banners, seasonal promotions, and dynamic catalog bundle injection.

While the existing prototype successfully validates the product vision, its production viability is bounded by five key architectural constraints:
- **Observability:** Lack of formal SLOs, error budgets, PromQL alerting, and compartmentalized logging.
- **Data & Retrieval:** In-memory static JSON files (`cookidoo_recipes.json` and `mercadona_products.json`) loaded on container boot without live vector similarity, Spanish semantic stemmers, or inventory synchronization across Mercadona fulfillment Colmenas (`mad3`, `vlc1`, `bcn1`).
- **Agentic Footprint:** A single-surface web UI lacking ambient integrations (Google Workspace, WhatsApp voice notes, and Model Context Protocol).
- **Delivery Pipeline:** Imperative, single-stage Docker builds executed via `deploy.sh` with plaintext secrets and immediate 100% traffic cutover.
- **Data Engineering:** Unleveraged Google Cloud Data & AI capabilities available in the environment.

This master blueprint synthesizes five specialized audits and engineering designs produced by dedicated architecture subagents:
- [Child 1 Blueprint: Observability, PromQL SLO Alerting & Cloud Logging](child1_observability_slo_blueprint.md)
- [Child 2 Blueprint: Hybrid Search & Vector RAG on AlloyDB & BigQuery](child2_hybrid_search_rag_blueprint.md)
- [Child 3 Blueprint: Multi-Surface Agentic Integration (ADK, Workspace, WhatsApp, MCP)](child3_multi_surface_agentic_blueprint.md)
- [Child 4 Blueprint: Hardened Containerization, Zero-Downtime CI/CD & Terraform](child4_cicd_cloudbuild_blueprint.md)
- [Child 5 Blueprint: GCP Data Cloud Skills Portfolio Audit & Technical Roadmap](child5_data_cloud_skills_audit.md)

---

## High-Level Target Architecture

```
                                      +--------------------------------------------------------+
                                      |                   Client Surfaces                      |
                                      | - Web App (SSE Stream)   - WhatsApp Cloud API (Voice)  |
                                      | - Telegram Bot (Keybrd)  - MCP Clients (Claude, Jetski)|
                                      +---------------------------+----------------------------+
                                                                  |
                                                                  v
                                      +--------------------------------------------------------+
                                      |        Google Cloud Run (europe-west1, v2 API)         |
                                      |  - Multi-stage Hardened Container (Non-root UID 10001) |
                                      |  - Gunicorn / Uvicorn ASGI Process Manager             |
                                      |  - OpenTelemetry Trace Context (W3C traceparent)       |
                                      |  - AlloyDB Auth Proxy Sidecar Container                |
                                      +---------------------------+----------------------------+
                                           |                      |                      |
            +------------------------------+                      |                      +-----------------------------+
            |                                                     |                                                    |
            v                                                     v                                                    v
+------------------------+                             +------------------------+                           +------------------------+
| Google ADK & Gemini    |                             | AlloyDB for PostgreSQL |                           | Google Workspace APIs  |
| - Gemini 3.8 Flash     |                             | (AlloyDB AI Engine)    |                           | - Google Calendar v3   |
| - Gemini 2.5 Fallback  |                             | - 5,000+ Cookidoo      |                           |   (Dinner scheduling)  |
| - Multimodal Audio In  |                             | - 15,000+ Mercadona    |                           | - Google Keep / Tasks  |
| - Structured Tool JSON |                             | - ScaNN Index (768-dim)|                           |   (Aisle-sorted cart)  |
+------------------------+                             | - Spanish FTS + RRF    |                           +------------------------+
                                                       +-----------+------------+
                                                                   |
                                                      CDC Datastream / Batch
                                                                   v
                                                       +------------------------+
                                                       | Google BigQuery Lake   |
                                                       | - Property Graph (GQL) |
                                                       | - ML.GENERATE_EMBED    |
                                                       | - VECTOR_SEARCH        |
                                                       +------------------------+
```

---

## Section 1: Observability, PromQL SLO Alerting & Cloud Logging Suite

### 1.1 Service Level Objectives (SLOs) & Error Budgets (Rolling 28 Days)

| Service Scope | Objective / SLI Category | Evaluation Type | Target | Metric Specification | Error Budget (28 Days) | Action on Burn |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `mercadona-ai-companion` | **Availability** | Ratio (Request-based) | **99.9%** | `run_googleapis_com:request_count{response_code_class!="5xx"}` / Total | 0.10% (~40 min downtime) | Fast Burn paged via PagerDuty |
| `campaign-library` | **Availability** | Ratio (Request-based) | **99.95%** | `run_googleapis_com:request_count{response_code_class!="5xx"}` / Total | 0.05% (~20 min downtime) | Fast Burn paged via PagerDuty |
| `mercadona-ai-companion` | **Latency** | Window-based (5m) | **p95 < 800ms** | 99% of 5-min windows satisfy `histogram_quantile(0.95, ...)` | 1% of windows (~80 windows) | Slow Burn ticket to sprint backlog |
| `campaign-library` | **Latency** | Window-based (5m) | **p95 < 250ms** | 99% of 5-min windows satisfy `histogram_quantile(0.95, ...)` | 1% of windows (~80 windows) | Slow Burn ticket to sprint backlog |
| `mercadona-ai-companion` | **Gemini Call Reliability** | Ratio (Invocation) | **> 99.5%** | Successful LLM responses / Total inference attempts | 0.50% error budget | Automatic fallback to `gemini-2.5-flash` |

### 1.2 Multi-Window Multi-Burn Rate PromQL Formulas

Following Google SRE best practices, alerts require simultaneous burn across a long window (alert duration) and a short window (confirmation of ongoing burn):

#### Fast Burn Alert (Burn Rate = 14.4, consumes 2% budget in 1 hour):
```promql
(
  (
    sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion",service_name="mercadona-ai-companion",response_code_class="5xx"}[1h]))
    /
    sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion",service_name="mercadona-ai-companion"}[1h]))
  ) > (14.4 * (1 - 0.999))
)
and
(
  (
    sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion",service_name="mercadona-ai-companion",response_code_class="5xx"}[5m]))
    /
    sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion",service_name="mercadona-ai-companion"}[5m]))
  ) > (14.4 * (1 - 0.999))
)
```

#### Slow Burn Alert (Burn Rate = 1.0, consumes 10% budget in 3 days):
```promql
(
  (
    sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion",service_name="mercadona-ai-companion",response_code_class="5xx"}[3d]))
    /
    sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion",service_name="mercadona-ai-companion"}[3d]))
  ) > (1.0 * (1 - 0.999))
)
and
(
  (
    sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion",service_name="mercadona-ai-companion",response_code_class="5xx"}[6h]))
    /
    sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion",service_name="mercadona-ai-companion"}[6h]))
  ) > (1.0 * (1 - 0.999))
)
```

### 1.3 Cloud Logging Architecture
- **Regionalized Storage:** Dedicated log bucket `mercadona-logs-europe-west1` with 365-day retention and Observability Analytics enabled.
- **Compartmentalized Log Views:**
  - `security-audit-view`: Captures Google Identity auth tokens, session validations, and unauthorized access attempts.
  - `gemini-telemetry-view`: Isolates prompt tokens, candidate tokens, inference duration, model fallbacks, and safety blocks.
  - `cart-transaction-view`: Tracks Mercadona headless cart compilation, Postal Code resolution (`28016` $\to$ `mad3`), and out-of-stock items.
- **Cost-Optimization Sinks:** Excludes 100% of Cloud Run uptime health checks (`/healthz` user-agent `GoogleHC/*`) and samples `DEBUG` level logs by 90% via `sample(insertId, 0.90)`.

---

## Section 2: Hybrid Search & Vector RAG on AlloyDB & BigQuery

### 2.1 Dual-Engine Serving vs Analytical Partitioning

```
+-----------------------------------------------------------------------------------------------+
|                                         DUAL-ENGINE MATRIX                                    |
+----------------------------------------+------------------------------------------------------+
| Feature                                | Online Hot Path: AlloyDB for PostgreSQL (AlloyDB AI) | Analytical / Batch Path: BigQuery ML |
+----------------------------------------+------------------------------------------------------+
| Primary Responsibility                 | Real-time user queries, 1-click cart assembly        | Nightly embedding sync, drift audit  |
| Latency SLA                            | < 15ms vector scan; < 50ms hybrid execution          | 1.5s - 5.0s per batch scan           |
| Vector Index Architecture              | Google ScaNN (alloydb_scann) 768-dim                 | BigQuery IVF (Inverted File)         |
| Lexical Engine                         | PostgreSQL tsvector (Spanish Snowball dictionary)    | BigQuery SEARCH() text analyzer      |
| Concurrency Target                     | 1,000+ QPS with connection pooling                   | Serverless slot batch execution      |
+----------------------------------------+------------------------------------------------------+
```

### 2.2 AlloyDB Production Schema & ScaNN Index

```sql
-- Enable Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS alloydb_scann;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Mercadona Product Catalog (Live Inventory)
CREATE TABLE mercadona_products (
    id VARCHAR(64) PRIMARY KEY,
    ean VARCHAR(32) NOT NULL,
    display_name TEXT NOT NULL,
    category TEXT NOT NULL,
    price_cents INT NOT NULL,
    unit_price_cents INT NOT NULL,
    unit_size_grams NUMERIC(10,2),
    warehouse VARCHAR(16) NOT NULL, -- e.g. mad3, vlc1, bcn1
    is_available BOOLEAN DEFAULT TRUE,
    allergens_bitmask INT DEFAULT 0,
    embedding vector(768),
    fts_tokens tsvector GENERATED ALWAYS AS (
        to_tsvector('spanish', coalesce(display_name, '') || ' ' || coalesce(category, ''))
    ) STORED
);

-- Google ScaNN Vector Index (L2 distance / Cosine)
CREATE INDEX idx_products_scann ON mercadona_products 
USING scann (embedding cosine_distance) 
WITH (num_leaves = 500, quantizer = 'sq8');

-- GIN Spanish Full-Text Index
CREATE INDEX idx_products_fts ON mercadona_products USING gin(fts_tokens);
```

### 2.3 Hybrid Search SQL Function (Reciprocal Rank Fusion k=60)

```sql
CREATE OR REPLACE FUNCTION hybrid_search_products(
    query_text TEXT,
    query_embedding vector(768),
    target_warehouse VARCHAR(16),
    excluded_allergens_mask INT,
    limit_count INT DEFAULT 5
)
RETURNS TABLE (
    product_id VARCHAR(64),
    display_name TEXT,
    price_cents INT,
    rrf_score DOUBLE PRECISION
) AS $$
WITH vector_matches AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> query_embedding) AS v_rank
    FROM mercadona_products
    WHERE warehouse = target_warehouse 
      AND is_available = TRUE 
      AND (allergens_bitmask & excluded_allergens_mask) = 0
    LIMIT 50
),
text_matches AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(fts_tokens, plainto_tsquery('spanish', query_text)) DESC) AS t_rank
    FROM mercadona_products
    WHERE warehouse = target_warehouse 
      AND is_available = TRUE 
      AND fts_tokens @@ plainto_tsquery('spanish', query_text)
    LIMIT 50
)
SELECT 
    p.id, 
    p.display_name, 
    p.price_cents,
    COALESCE(1.0 / (60 + v.v_rank), 0.0) + COALESCE(1.0 / (60 + t.t_rank), 0.0) AS rrf_score
FROM mercadona_products p
LEFT JOIN vector_matches v ON p.id = v.id
LEFT JOIN text_matches t ON p.id = t.id
WHERE v.id IS NOT NULL OR t.id IS NOT NULL
ORDER BY rrf_score DESC
LIMIT limit_count;
$$ LANGUAGE SQL STABLE;
```

---

## Section 3: Multi-Surface Agentic Integration Blueprint

### 3.1 Google Agent Development Kit (ADK) Engine
The application transitions from imperative functions into a stateful, tool-calling ADK agent:
- **Core State Machine:** `AgentSessionState` managing user ID, session token, postal code, active Colmena warehouse, 7-day lunch/dinner slot dictionary, pantry exclusions, and accumulated budget.
- **Dual-Model Inference Architecture:** Primary execution on `gemini-3.8-flash` with thinking budget enabled; instant fallback to `gemini-2.5-flash` on rate limits or API latency degradation.
- **Typed Tool Boundaries:**
  - `get_recipe(recipe_id: str)`: Fetches Thermomix steps, ingredients, and nutritional metadata.
  - `search_mercadona(query: str, postal_code: str)`: Invokes the AlloyDB hybrid search function.
  - `build_cart(recipe_ids: list[str], pantry_items: list[str])`: Aggregates, subtracts pantry goods, and generates the Mercadona checkout payload.
  - `export_calendar(weekly_plan: dict)`: Pushes calendar invitations to the user's primary calendar.
  - `add_keep_notes(shopping_list: dict)`: Generates structured checklist notes grouped by supermarket aisle.

### 3.2 Omnichannel Messaging Gateways (WhatsApp & Telegram)
- **Zero-STT Multimodal Voice Input:** Incoming voice notes (OGG/Opus from WhatsApp or Telegram) are passed directly to Gemini 3.8 Flash's native audio encoder. This bypasses fragile Speech-to-Text pipelines and directly extracts dietary intents, diner counts, and recipe requests from Spanish spoken audio.
- **Interactive Messaging Actions:** Cloud Run webhooks return WhatsApp interactive button carousels:
  - `[ 🍳 A mi Thermomix ]`: Invokes Vorwerk API to push recipe to TM6 screen.
  - `[ 🛒 Comprar en Mercadona ]`: Returns instant headless cart URL with all ingredients loaded.
  - `[ 📅 Sincronizar Google ]`: Exports schedule to Google Calendar.

### 3.3 Model Context Protocol (MCP) Server (`mercadona-companion-mcp`)
Exposes the companion's culinary intelligence to developer AI agents (Jetski, Gemini CLI, Claude, Claude Code) via standard JSON-RPC 2.0 over Stdio and Server-Sent Events (SSE):
- `cookidoo_search`: Search 5,000+ Spanish recipes with dietary filtering.
- `mercadona_catalog_query`: Real-time stock, pricing, and pack-size lookups by postal code.
- `cart_builder`: Generates optimized shopping cart bundles with pantry deduction.

---

## Section 4: Hardened Containerization, Zero-Downtime CI/CD & Terraform

### 4.1 Production Multi-Stage `Dockerfile`
Remediates critical security flaws: eliminates root execution (enforcing `appuser:appgroup` UID 10001), separates build wheels from the final runtime layer, and runs Gunicorn with Uvicorn workers:

```dockerfile
# Stage 1: Build virtualenv & wheels
FROM python:3.12-slim AS builder
WORKDIR /build
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt gunicorn uvicorn[standard]

# Stage 2: Hardened, Minimal Runtime
FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 PATH="/home/appuser/.local/bin:$PATH"
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /home/appuser -m appuser
COPY --from=builder --chown=appuser:appgroup /root/.local /home/appuser/.local
COPY --chown=appuser:appgroup . .
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8080", "--timeout", "120", "server:app"]
```

### 4.2 Declarative Zero-Downtime Cloud Build Pipeline (`cloudbuild.yaml`)
1. **Parallel Unit Testing:** Runs pytest suites before building container layers.
2. **Layer Caching:** Utilizes Docker BuildKit cache from Google Artifact Registry.
3. **Vulnerability Scanning:** Hooks into Google Container Analysis for automated CVE scanning.
4. **Zero-Downtime Canary Rollout:**
   - Deploys candidate revision with `--no-traffic`.
   - Runs automated smoke tests against the private tag URL (`https://candidate---mercadona-ai-companion-xxx.a.run.app/healthz`).
   - Shifts 10% traffic to candidate for a 15-minute soak window while monitoring PromQL 5xx error rate.
   - Automatically cuts over to 100% traffic if error rate remains below 0.1%.

### 4.3 Declarative Infrastructure as Code (Terraform)
All infrastructure is declared under Terraform, eliminating manual drift:
- `artifact_registry.tf`: Regional OCI Docker repository with automated 30-day untagged image cleanup.
- `secret_manager.tf`: Native GCP Secret Manager integration for `GEMINI_API_KEY`, `SESSION_SECRET`, and Google OAuth client credentials.
- `cloudrun.tf`: Configures Cloud Run v2 services (`google_cloud_run_v2_service`) with `min_instance_count = 1` (zero cold-start latency), memory 1Gi, 1 vCPU, execution environment `gen2`, and PSC Direct VPC Egress for secure AlloyDB connectivity.

---

## Section 5: GCP Data Cloud Skills Portfolio Roadmap

The 33 installed Data Cloud skills under `/usr/local/google/home/mgandolfi/.gemini/config/skills/` are organized into a phased transformation roadmap:

```
+----------------------------------------------------------------------------------------------------+
|                                    DATA CLOUD ROADMAP PHASES                                       |
+----------------------------------------------------------------------------------------------------+
| Phase 0: Pre-Flight Governance & Security Baseline                                                 |
| -> Skills: google-cloud-auth-verification, enforcing-resource-attribution,                         |
|            gcs-security-assessment, accidental-data-loss-prevention                                |
| -> Outcome: Zero plaintext credentials, mandatory datacloud:jetski attribution tags,              |
|             SAIF-compliant storage policies.                                                       |
+----------------------------------------------------------------------------------------------------+
| Phase 1: Storage Architecture & Raw Ingestion Pipeline                                             |
| -> Skills: google-cloud-storage-bucket-architect, bigquery-data-transfer-service, gcp-dataflow      |
| -> Outcome: Automated daily ingestion of Mercadona postal code catalogs (Colmenas mad3, vlc1,      |
|             bcn1) and raw Cookidoo scrapers into Cloud Storage and BigQuery landing tables.         |
+----------------------------------------------------------------------------------------------------+
| Phase 2: Data Cleansing, Schema Mapping & Property Graph                                           |
| -> Skills: data-autocleaning, schema-mapping, dataform-bigquery, bigquery-graph                    |
| -> Outcome: Dataplex-profiled data quality, unit normalization (grams/ml), allergen bitmasking,    |
|             and creation of BigQuery ISO GQL Property Graph (Recipes -> Ingredients -> SKUs).      |
+----------------------------------------------------------------------------------------------------+
| Phase 3: Vector ML, Semantic Search & Cloud Composer Orchestration                                |
| -> Skills: bigquery-ai-ml, ml-best-practices, gcp-managed-airflow-dag-authoring,                   |
|            gcp-pipeline-orchestration, gcp-composer-troubleshooting                                |
| -> Outcome: Scheduled Cloud Composer DAGs generating text-embedding-005 embeddings, syncing        |
|             AlloyDB ScaNN indexes, and recalculating weekly marketing campaigns.                   |
+----------------------------------------------------------------------------------------------------+
```

---

## Consolidated Engineering Implementation Checklist

To operationalize this next-gen architecture, engineering teams should execute the following sequence:

1. **Infrastructure Provisioning (Terraform):**
   - [ ] Apply `artifact_registry.tf` to establish `europe-west1-docker.pkg.dev/mercadona-ia-companion/companion-docker`.
   - [ ] Apply `secret_manager.tf` and migrate `GEMINI_API_KEY` and `SESSION_SECRET` out of `deploy.sh`.
   - [ ] Provision AlloyDB cluster `mercadona-db-cluster` with AlloyDB AI enabled and Private Service Connect (PSC).
   - [ ] Apply `cloudrun.tf` declaring Cloud Run v2 services with AlloyDB Auth Proxy sidecars.

2. **Observability Deployment:**
   - [ ] Apply `monitoring_slo.tf` creating PromQL alerts tagged with `created-with-google-skill = "google-cloud-slo-alert-configuration"`.
   - [ ] Configure `google_logging_project_bucket_config` for regional `europe-west1` log analytics.
   - [ ] Attach `security-audit-view`, `gemini-telemetry-view`, and `cart-transaction-view` to log buckets.

3. **Data Pipeline & Vector Database Setup:**
   - [ ] Execute AlloyDB DDL scripts creating `mercadona_products`, `recipes`, and `hybrid_search_products` function.
   - [ ] Deploy Cloud Composer DAG `daily_mercadona_catalog_sync.py` to scrape and embed updated grocery prices.
   - [ ] Run BigQuery ISO GQL graph compilation creating `mercadona_culinary_graph`.

4. **Multi-Surface & ADK Agent Activation:**
   - [ ] Wrap `gemini_planner.py` with Google ADK `AgentSessionState` and typed Pydantic tool models.
   - [ ] Enable WhatsApp Cloud API webhook receiver at `POST /api/webhook/whatsapp` on Cloud Run.
   - [ ] Launch `mercadona-companion-mcp` for developer pair programming workflows.

5. **CI/CD Cutover:**
   - [ ] Replace `Dockerfile` with multi-stage non-root container.
   - [ ] Connect repository to Google Cloud Build trigger with automated canary traffic routing.
   - [ ] Retire imperative `deploy.sh`.

---
*Blueprint synthesized from Child Subagents 1-5 audits. Full detailed engineering specs are available in `docs/audits/child1_*.md` through `docs/audits/child5_*.md`.*
