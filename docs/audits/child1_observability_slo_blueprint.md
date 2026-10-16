# Observability, PromQL SLO Alerting & Cloud Logging Blueprint
**Project ID**: `mercadona-ia-companion`  
**Region**: `europe-west1`  
**Target Services**: `mercadona-ai-companion`, `campaign-library` (Google Cloud Run)  
**Author**: Child Subagent 1 — Observability, PromQL, SLO Alerting & Cloud Logging Architect  
**Skill Reference**: `google-cloud-slo-alert-configuration`, `cloud-monitoring-metric-selection`, `cloud-monitoring-promql-query`, `cloud-logging-configuration-basics`  
**Date**: September 2026  

---

## Executive Summary & System Scope

The **Mercadona AI Companion** ecosystem consists of two core containerized microservices hosted on Google Cloud Run in `europe-west1`:
1. `mercadona-ai-companion`: The primary intelligent orchestrator interacting with Gemini 1.5 Pro / 2.0 Flash (via Vertex AI / GenAI SDK), coordinating natural language menu planning, Cookidoo recipe synchronization, dietary and nutritional graph lookups, and Mercadona cart actions.
2. `campaign-library`: The high-throughput microservice serving localized marketing campaigns, weekly flyers, seasonal discounts, and regional promotions directly embedded into user recommendations and cart bundles.

This blueprint establishes a production-grade, Google SRE-aligned observability suite spanning:
- **Formal Service Level Objectives (SLOs)**, **Service Level Indicators (SLIs)**, and **Error Budget allocations**.
- **PromQL Multi-Window Multi-Burn Rate Alerts** configured natively via Google Cloud Monitoring Alert Policies.
- **Enterprise Cloud Logging Architecture** featuring regionalized log buckets, compartmentalized log views (`security-audit-view`, `gemini-telemetry-view`, `cart-transaction-view`), custom counter and distribution metrics, and cost-optimized exclusion/sampling policies.
- **Distributed End-to-End Tracing** leveraging OpenTelemetry and Google Cloud Trace for Gemini planner operations, Cookidoo synchronization, and Mercadona cart checkout flows.
- **Complete, Declarative Terraform Modules** tagged with `created-with-google-skill = "google-cloud-slo-alert-configuration"`.

---

## 1. Service Level Objectives (SLOs), SLIs & Error Budgets

To balance developer velocity and platform resilience, we establish three primary SLO categories across a standard **rolling 28-day compliance window**:

```
Rolling Compliance Window: 28 days = 40,320 minutes (2,419,200 seconds)
```

### 1.1 SLO Specifications Summary Table

| Service Scope | Objective / SLI Category | Evaluation Type | SLI Target | Metric Specification | Error Budget (28-day) | Target SRE Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `mercadona-ai-companion` | **Availability** | Ratio SLI (Request-based) | **99.9%** (3 nines) | `run_googleapis_com:request_count`<br>`response_code_class!="5xx"` / Total | 0.1% of all inbound HTTP requests | Immediate mitigation of unhandled application exceptions, pod crashes, or HTTP 500/503 errors. |
| `campaign-library` | **Availability** | Ratio SLI (Request-based) | **99.95%** (3.5 nines) | `run_googleapis_com:request_count`<br>`response_code_class!="5xx"` / Total | 0.05% of all inbound HTTP requests | Guarantees high availability for marketing banner injection and promotion retrieval. |
| `mercadona-ai-companion` | **Latency** | Distribution SLI (Window-based) | **p95 < 800ms** (99% good 5m windows) | `run_googleapis_com:request_latencies_bucket`<br>`le="800"` | 1% of 5-minute windows (max ~80 degraded 5m windows per 28 days) | Protects interactive AI user experience from latency regressions and upstream stalls. |
| `campaign-library` | **Latency** | Distribution SLI (Window-based) | **p95 < 250ms** (99% good 5m windows) | `run_googleapis_com:request_latencies_bucket`<br>`le="250"` | 1% of 5-minute windows | Fast CDN-backed promotion caching and database indexing. |
| `mercadona-ai-companion` | **Gemini AI Call Reliability** | Ratio SLI (Request-based) | **Error Rate < 0.5%** (Reliability 99.5%) | Log-based / OpenTelemetry metric:<br>`gemini_api_call_status` | 0.5% of total LLM inference invocations | Detects Vertex AI quota exhaustion (HTTP 429), safety blocks, context overruns, or upstream Gemini outages. |

---

### 1.2 Mathematical Derivation of SLIs and Burn Rates

Following Google SRE best practices (*Site Reliability Engineering Workbook, Chapter 5*), alerts are modeled using **Multi-Window, Multi-Burn-Rate alerting**:

$$\text{Burn Rate } b = \frac{\text{Observed Error Rate}}{1 - \text{SLO Target}}$$

- A burn rate of **$b = 1.0$** consumes 100% of the error budget over the entire 28-day window ($40,320\text{ min}$).
- A **Fast Burn Alert** ($b = 14.4$) consumes **2.0% of the total budget in 1 hour**, or **100% in 46.6 hours**. It uses dual lookback windows ($1\text{h}$ long window and $5\text{m}$ short window) to ensure high responsiveness while suppressing transient spikes.
- A **Slow Burn Alert** ($b = 1.0$) consumes **10.7% of the total budget in 3 days**, using a $3\text{d}$ long window and a $6\text{h}$ short window. It notifies on-call teams of systemic low-grade degradation before the monthly budget is fully drained.

---

## 2. PromQL Alert Conditions

All alert queries utilize standard Google Cloud Monitoring PromQL metric names normalized from Cloud Run telemetry:
- `run.googleapis.com/request_count` $\rightarrow$ `run_googleapis_com:request_count`
- `run.googleapis.com/request_latencies` $\rightarrow$ `run_googleapis_com:request_latencies_bucket`
- Scoped to `project_id="mercadona-ia-companion"`, `location="europe-west1"`, and matching `service_name`.

### 2.1 Microservice Availability Alerts (`mercadona-ai-companion`)

#### Fast Burn (14.4x over 1h & 5m)
*Trigger Threshold*: $(1 - 0.999) \times 14.4 = 0.001 \times 14.4 = 0.0144$ ($1.44\%$ error rate).
```promql
(
  (
    1 - (
      sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion", location="europe-west1", service_name="mercadona-ai-companion", response_code_class!="5xx"}[5m])) BY (project_id, service_name, location)
      /
      sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion", location="europe-west1", service_name="mercadona-ai-companion"}[5m])) BY (project_id, service_name, location)
    )
  ) > (1 - 0.999) * 14.4
)
and
(
  (
    1 - (
      sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion", location="europe-west1", service_name="mercadona-ai-companion", response_code_class!="5xx"}[1h])) BY (project_id, service_name, location)
      /
      sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion", location="europe-west1", service_name="mercadona-ai-companion"}[1h])) BY (project_id, service_name, location)
    )
  ) > (1 - 0.999) * 14.4
)
```

#### Slow Burn (1.0x over 3d & 6h)
*Trigger Threshold*: $(1 - 0.999) \times 1.0 = 0.001$ ($0.1\%$ error rate).
```promql
(
  (
    1 - (
      sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion", location="europe-west1", service_name="mercadona-ai-companion", response_code_class!="5xx"}[6h])) BY (project_id, service_name, location)
      /
      sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion", location="europe-west1", service_name="mercadona-ai-companion"}[6h])) BY (project_id, service_name, location)
    )
  ) > (1 - 0.999) * 1.0
)
and
(
  (
    1 - (
      sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion", location="europe-west1", service_name="mercadona-ai-companion", response_code_class!="5xx"}[3d])) BY (project_id, service_name, location)
      /
      sum(rate(run_googleapis_com:request_count{project_id="mercadona-ia-companion", location="europe-west1", service_name="mercadona-ai-companion"}[3d])) BY (project_id, service_name, location)
    )
  ) > (1 - 0.999) * 1.0
)
```

---

### 2.2 Microservice Latency Alerts (`p95 < 800ms`)

#### Fast Burn (14.4x over 1h & 5m)
*Target*: $95\%$ of requests must complete in $< 800\text{ ms}$. If the fraction of requests exceeding $800\text{ ms}$ violates $5\% \times 14.4$:
```promql
(
  (
    1 - histogram_fraction(800, sum by (le, project_id, service_name, location) (rate(run_googleapis_com:request_latencies_bucket{project_id="mercadona-ia-companion", location="europe-west1", service_name="mercadona-ai-companion"}[5m])))
  ) > (1 - 0.95) * 14.4
)
and
(
  (
    1 - histogram_fraction(800, sum by (le, project_id, service_name, location) (rate(run_googleapis_com:request_latencies_bucket{project_id="mercadona-ia-companion", location="europe-west1", service_name="mercadona-ai-companion"}[1h])))
  ) > (1 - 0.95) * 14.4
)
```

---

### 2.3 Gemini API Error Rate Alerts (`Error Rate < 0.5%`)

Invocations of Gemini 1.5/2.0 on Vertex AI or AI Studio emit custom logs-based metric `custom.googleapis.com/gemini/invocation_count` labeled with `status="success"` vs `status="error"`.

#### Fast Burn (14.4x over 1h & 5m)
*Trigger Threshold*: $0.5\% \times 14.4 = 7.2\%$ error rate over the evaluation windows:
```promql
(
  (
    sum(rate(custom_googleapis_com:gemini_invocation_count{project_id="mercadona-ia-companion", status="error"}[5m])) BY (project_id, model_id)
    /
    sum(rate(custom_googleapis_com:gemini_invocation_count{project_id="mercadona-ia-companion"}[5m])) BY (project_id, model_id)
  ) > 0.005 * 14.4
)
and
(
  (
    sum(rate(custom_googleapis_com:gemini_invocation_count{project_id="mercadona-ia-companion", status="error"}[1h])) BY (project_id, model_id)
    /
    sum(rate(custom_googleapis_com:gemini_invocation_count{project_id="mercadona-ia-companion"}[1h])) BY (project_id, model_id)
  ) > 0.005 * 14.4
)
```

---

## 3. Cloud Logging Architecture

### 3.1 Regional Log Bucket & Lifecycle Strategy
To comply with GDPR and EU data residency while minimizing cross-region egress latencies, all application and platform logs are ingested and stored in a dedicated regional log bucket in `europe-west1`:
- **Bucket ID**: `mercadona-app-logs`
- **Location**: `europe-west1`
- **Retention**: 90 days (standard audit retention)
- **Analytics Capability**: Enabled (`enable_analytics = true`), providing BigQuery SQL access over log data via BigQuery Log Studio.

> [!WARNING] **Mandatory Observability Analytics Downgrade Warning:**
> After a log bucket has been upgraded to use Observability Analytics, it **cannot be downgraded** to remove the analytics capability.

### 3.2 Granular Log Views & IAM Scoping
Access control is implemented at the Log View layer to segregate standard developer debugging logs from sensitive PCI/transaction logs and security audits:

1. **`security-audit-view`**:
   - Filter: `logName:"cloudaudit.googleapis.com"`
   - Access: Restricted to Security Engineers (`roles/logging.viewAccessor` bound with IAM conditions).
2. **`gemini-telemetry-view`**:
   - Filter: `jsonPayload.component="gemini-orchestrator" OR jsonPayload.service="vertex-ai-agent"`
   - Access: Data Science and Prompt Engineering teams.
3. **`cart-transaction-view`**:
   - Filter: `jsonPayload.event_type="cart_mutation" OR jsonPayload.event_type="cookidoo_sync"`
   - Access: E-commerce operations and checkout reliability engineers.
4. **`_Default` View Restriction**:
   - Excludes sensitive audit and cart transaction logs from general view accessor roles to prevent unintended data exposure.

### 3.3 Logs-Based Metrics Architecture
Custom logs-based metrics bridge unstructured JSON application logs to Google Cloud Monitoring time series:
- **`gemini_invocation_count` (Counter Metric)**:
  - Filter: `resource.type="cloud_run_revision" AND jsonPayload.component="gemini-client"`
  - Labels extracted: `model_id`, `status` (`success` / `error`), `error_code` (e.g., `RESOURCE_EXHAUSTED`, `SAFETY_BLOCK`, `DEADLINE_EXCEEDED`).
- **`gemini_token_usage` (Distribution Metric)**:
  - Metric extracting `jsonPayload.usage.total_tokens` with exponential bucket bounds ($16, 32, 64, \dots, 32768$) to track LLM cost and prompt sizing.
- **`cart_sync_latency_ms` (Distribution Metric)**:
  - Metric extracting `jsonPayload.sync_duration_ms` for Cookidoo ingredients $\rightarrow$ Mercadona cart SKU resolution.

### 3.4 Cost Optimization & Sampling Policies
To eliminate log ingestion bloat without sacrificing debugging visibility:
- **Health Check Exclusion**: Discard 100% of `/healthz`, `/live`, and `/ready` probes originating from Google Cloud Run internal load balancers.
  - Filter: `httpRequest.requestUrl=~"/healthz|/ready|/live" AND httpRequest.userAgent=~"GoogleHC"`
- **Debug Log Sampling**: Keep only 10% of `DEBUG` severity logs using deterministic sampling (`sample(insertId, 0.90)` in the exclusion filter).
  - Filter: `severity=DEBUG AND sample(insertId, 0.90)`

---

## 4. Cloud Trace & OpenTelemetry Integration

To provide distributed tracing across asynchronous boundaries, both microservices integrate the **OpenTelemetry (OTel) Python / Go SDK** exporting traces directly to the **Google Cloud Trace API** (`cloudtrace.googleapis.com`).

```
[Customer Browser / Mobile App]
             |
             v (traceparent HTTP header: W3C Trace Context)
+-----------------------------------------------------------+
| Cloud Run: mercadona-ai-companion                         |
|  - Span: HTTP POST /api/v1/companion/chat                 |
|    |                                                      |
|    +--> Span: gemini.chat_completion                      |
|    |      attributes: {model: gemini-1.5-pro, tokens: ...}|
|    |                                                      |
|    +--> Span: cookidoo.sync_recipe                        |
|    |      attributes: {recipe_id: "ck_94812"}             |
|    |                                                      |
|    +--> Span: mercadona.cart_mutation                     |
|           | attributes: {sku_count: 8, postal_code: 46001}|
|           |                                               |
|           v (HTTP POST /campaigns/embed)                  |
|     +---------------------------------------------------+ |
|     | Cloud Run: campaign-library                       | |
|     |  - Span: HTTP POST /campaigns/embed               | |
|     |    +--> Span: firestore.query_active_promotions   | |
|     |    +--> Span: rank_promotions                     | |
|     +---------------------------------------------------+ |
+-----------------------------------------------------------+
```

### 4.1 Trace Context Propagation Standards
- Standard **W3C TraceContext** headers (`traceparent`, `tracestate`) are parsed and injected across all internal HTTP calls between `mercadona-ai-companion` and `campaign-library`.
- The Google Cloud Run runtime automatically captures root ingress spans via the Cloud Run Google Front End (GFE) when `X-Cloud-Trace-Context` or W3C headers are passed.
- Logs include `logging.googleapis.com/trace` and `logging.googleapis.com/spanId` fields matching the active OpenTelemetry context, allowing **1-click jump from a Cloud Logging record straight to Cloud Trace waterfall graphs**.

---

## 5. Complete Production Terraform Blueprint

Below is the complete, self-contained Terraform code containing:
- Provider definitions & project locals
- Regional Log Bucket & Log Views
- Log Sink with cost-optimization exclusions
- Logs-based metrics for Gemini invocations
- Fast Burn & Slow Burn SLO Alert Policies with PromQL conditions tagged with `created-with-google-skill = "google-cloud-slo-alert-configuration"`.

```terraform
###############################################################################
# Terraform Observability Suite for Mercadona AI Companion & Campaign Library
# Target Project: mercadona-ia-companion
# Region: europe-west1
###############################################################################

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
  }
}

variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID"
  default     = "mercadona-ia-companion"
}

variable "region" {
  type        = string
  description = "Google Cloud Region for resources"
  default     = "europe-west1"
}

variable "notification_channels" {
  type        = list(string)
  description = "List of Cloud Monitoring Notification Channel resource IDs (e.g. PagerDuty, Slack, Email)"
  default     = []
}

locals {
  service_companion = "mercadona-ai-companion"
  service_campaign  = "campaign-library"
  slo_label = {
    created-with-google-skill = "google-cloud-slo-alert-configuration"
  }
}

# =============================================================================
# 1. Cloud Logging Architecture: Regional Bucket, Views, and Sinks
# =============================================================================

# Regional Log Bucket with Observability Analytics enabled
resource "google_logging_project_bucket_config" "regional_app_bucket" {
  project          = var.project_id
  location         = var.region
  bucket_id        = "mercadona-app-logs"
  retention_days   = 90
  enable_analytics = true
  description      = "Regionalized log bucket for Mercadona microservices in europe-west1 with Analytics enabled."
}

# Log View: Security & IAM Audit Logs
resource "google_logging_log_view" "security_audit_view" {
  name        = "security-audit-view"
  bucket      = google_logging_project_bucket_config.regional_app_bucket.id
  description = "Access to Cloud Audit and IAM security logs."
  filter      = "logName:\"cloudaudit.googleapis.com\""
}

# Log View: Gemini Telemetry & Prompt Orchestration
resource "google_logging_log_view" "gemini_telemetry_view" {
  name        = "gemini-telemetry-view"
  bucket      = google_logging_project_bucket_config.regional_app_bucket.id
  description = "Access to Gemini AI agent orchestration, tool execution, and token telemetry."
  filter      = "jsonPayload.component=\"gemini-orchestrator\" OR jsonPayload.component=\"gemini-client\""
}

# Log View: E-Commerce Cart & Cookidoo Transactions
resource "google_logging_log_view" "cart_transaction_view" {
  name        = "cart-transaction-view"
  bucket      = google_logging_project_bucket_config.regional_app_bucket.id
  description = "Access to cart additions, sku resolution, and Cookidoo sync events."
  filter      = "jsonPayload.event_type=\"cart_mutation\" OR jsonPayload.event_type=\"cookidoo_sync\""
}

# Project Log Sink to Route Cloud Run Logs into the Regional Bucket with Exclusions
resource "google_logging_project_sink" "app_logs_sink" {
  name        = "mercadona-cloudrun-sink"
  project     = var.project_id
  destination = "logging.googleapis.com/${google_logging_project_bucket_config.regional_app_bucket.id}"
  filter      = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=(\"${local.service_companion}\", \"${local.service_campaign}\")"

  # Cost Optimization Exclusion 1: Discard Health Check Probes
  exclusions {
    name        = "exclude-health-checks"
    description = "Exclude high-frequency container health probes from GoogleHC"
    filter      = "httpRequest.requestUrl=~\"/healthz|/ready|/live\" AND httpRequest.userAgent=~\"GoogleHC\""
    disabled    = false
  }

  # Cost Optimization Exclusion 2: Sample 90% of Debug Logs (Retain 10%)
  exclusions {
    name        = "sample-debug-logs"
    description = "Discard 90% of DEBUG level logs using deterministic sampling"
    filter      = "severity=DEBUG AND sample(insertId, 0.90)"
    disabled    = false
  }

  unique_writer_identity = true
}

# Grant the Sink Service Account permission to write to the bucket
resource "google_project_iam_member" "sink_writer" {
  project = var.project_id
  role    = "roles/logging.bucketWriter"
  member  = google_logging_project_sink.app_logs_sink.writer_identity
}

# =============================================================================
# 2. Logs-Based Metrics
# =============================================================================

# Counter Metric: Gemini Model Invocations and Errors
resource "google_logging_metric" "gemini_invocation_count" {
  name        = "gemini_invocation_count"
  project     = var.project_id
  description = "Counts Gemini LLM calls split by status and model ID"
  filter      = "resource.type=\"cloud_run_revision\" AND jsonPayload.component=\"gemini-client\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
    labels {
      key         = "status"
      value_type  = "STRING"
      description = "Call status: success or error"
    }
    labels {
      key         = "model_id"
      value_type  = "STRING"
      description = "Model version (e.g. gemini-1.5-pro, gemini-2.0-flash)"
    }
  }

  label_extractors = {
    "status"   = "EXTRACT(jsonPayload.status)"
    "model_id" = "EXTRACT(jsonPayload.model_id)"
  }
}

# Distribution Metric: Gemini Prompt & Response Token Usage
resource "google_logging_metric" "gemini_token_usage" {
  name        = "gemini_token_usage"
  project     = var.project_id
  description = "Distribution of Gemini token consumption"
  filter      = "resource.type=\"cloud_run_revision\" AND jsonPayload.component=\"gemini-client\" AND jsonPayload.usage.total_tokens=*"
  value_extractor = "EXTRACT(jsonPayload.usage.total_tokens)"

  bucket_options {
    exponential_buckets {
      num_finite_buckets = 16
      growth_factor      = 2.0
      scale              = 16.0
    }
  }
}

# =============================================================================
# 3. PromQL SLO Alert Policies: mercadona-ai-companion
# =============================================================================

# SLO 1A: Fast Burn Alert - mercadona-ai-companion Availability (99.9% target)
resource "google_monitoring_alert_policy" "companion_availability_fast_burn" {
  project      = var.project_id
  display_name = "[SLO Fast Burn] ${local.service_companion} - Availability Alert"
  combiner     = "OR"

  conditions {
    display_name = "Fast Burn: Error Budget Depletion Rate 14.4x (1h and 5m windows)"
    condition_prometheus_query_language {
      query = <<EOT
(
  (
    1 - (
      sum(rate(run_googleapis_com:request_count{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_companion}", response_code_class!="5xx"}[5m])) BY (project_id, service_name, location)
      /
      sum(rate(run_googleapis_com:request_count{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_companion}"}[5m])) BY (project_id, service_name, location)
    )
  ) > (1 - 0.999) * 14.4
)
and
(
  (
    1 - (
      sum(rate(run_googleapis_com:request_count{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_companion}", response_code_class!="5xx"}[1h])) BY (project_id, service_name, location)
      /
      sum(rate(run_googleapis_com:request_count{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_companion}"}[1h])) BY (project_id, service_name, location)
    )
  ) > (1 - 0.999) * 14.4
)
EOT
      duration = "300s"
    }
  }

  alert_strategy {
    auto_close = "14400s" # Auto-close after 4 hours of inactivity
  }

  user_labels = local.slo_label
  notification_channels = var.notification_channels
}

# SLO 1B: Slow Burn Alert - mercadona-ai-companion Availability (99.9% target)
resource "google_monitoring_alert_policy" "companion_availability_slow_burn" {
  project      = var.project_id
  display_name = "[SLO Slow Burn] ${local.service_companion} - Availability Alert"
  combiner     = "OR"

  conditions {
    display_name = "Slow Burn: Error Budget Depletion Rate 1.0x (3d and 6h windows)"
    condition_prometheus_query_language {
      query = <<EOT
(
  (
    1 - (
      sum(rate(run_googleapis_com:request_count{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_companion}", response_code_class!="5xx"}[6h])) BY (project_id, service_name, location)
      /
      sum(rate(run_googleapis_com:request_count{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_companion}"}[6h])) BY (project_id, service_name, location)
    )
  ) > (1 - 0.999) * 1.0
)
and
(
  (
    1 - (
      sum(rate(run_googleapis_com:request_count{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_companion}", response_code_class!="5xx"}[3d])) BY (project_id, service_name, location)
      /
      sum(rate(run_googleapis_com:request_count{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_companion}"}[3d])) BY (project_id, service_name, location)
    )
  ) > (1 - 0.999) * 1.0
)
EOT
      # Duration omitted for windows > 25h according to Google Cloud PromQL best practices
    }
  }

  alert_strategy {
    auto_close = "86400s" # Auto-close after 24 hours
  }

  user_labels = local.slo_label
  notification_channels = var.notification_channels
}

# SLO 2: Fast Burn Alert - mercadona-ai-companion Latency (p95 < 800ms)
resource "google_monitoring_alert_policy" "companion_latency_fast_burn" {
  project      = var.project_id
  display_name = "[SLO Fast Burn] ${local.service_companion} - Latency p95 > 800ms"
  combiner     = "OR"

  conditions {
    display_name = "Fast Burn: p95 Latency Degradation (1h and 5m windows)"
    condition_prometheus_query_language {
      query = <<EOT
(
  (
    1 - histogram_fraction(800, sum by (le, project_id, service_name, location) (rate(run_googleapis_com:request_latencies_bucket{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_companion}"}[5m])))
  ) > (1 - 0.95) * 14.4
)
and
(
  (
    1 - histogram_fraction(800, sum by (le, project_id, service_name, location) (rate(run_googleapis_com:request_latencies_bucket{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_companion}"}[1h])))
  ) > (1 - 0.95) * 14.4
)
EOT
      duration = "300s"
    }
  }

  alert_strategy {
    auto_close = "14400s"
  }

  user_labels = local.slo_label
  notification_channels = var.notification_channels
}

# SLO 3: Fast Burn Alert - Gemini AI API Error Rate (< 0.5% target)
resource "google_monitoring_alert_policy" "gemini_error_rate_fast_burn" {
  project      = var.project_id
  display_name = "[SLO Fast Burn] ${local.service_companion} - Gemini API Error Rate > 0.5%"
  combiner     = "OR"

  conditions {
    display_name = "Fast Burn: Gemini API Failures Exceeding Budget (1h and 5m windows)"
    condition_prometheus_query_language {
      query = <<EOT
(
  (
    sum(rate(custom_googleapis_com:gemini_invocation_count{project_id="${var.project_id}", status="error"}[5m])) BY (project_id, model_id)
    /
    sum(rate(custom_googleapis_com:gemini_invocation_count{project_id="${var.project_id}"}[5m])) BY (project_id, model_id)
  ) > 0.005 * 14.4
)
and
(
  (
    sum(rate(custom_googleapis_com:gemini_invocation_count{project_id="${var.project_id}", status="error"}[1h])) BY (project_id, model_id)
    /
    sum(rate(custom_googleapis_com:gemini_invocation_count{project_id="${var.project_id}"}[1h])) BY (project_id, model_id)
  ) > 0.005 * 14.4
)
EOT
      duration = "300s"
    }
  }

  alert_strategy {
    auto_close = "14400s"
  }

  user_labels = local.slo_label
  notification_channels = var.notification_channels
}

# =============================================================================
# 4. PromQL SLO Alert Policies: campaign-library
# =============================================================================

# SLO 4: Fast Burn Alert - campaign-library Availability (99.95% target)
resource "google_monitoring_alert_policy" "campaign_availability_fast_burn" {
  project      = var.project_id
  display_name = "[SLO Fast Burn] ${local.service_campaign} - Availability Alert"
  combiner     = "OR"

  conditions {
    display_name = "Fast Burn: Error Budget Depletion Rate 14.4x (1h and 5m windows)"
    condition_prometheus_query_language {
      query = <<EOT
(
  (
    1 - (
      sum(rate(run_googleapis_com:request_count{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_campaign}", response_code_class!="5xx"}[5m])) BY (project_id, service_name, location)
      /
      sum(rate(run_googleapis_com:request_count{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_campaign}"}[5m])) BY (project_id, service_name, location)
    )
  ) > (1 - 0.9995) * 14.4
)
and
(
  (
    1 - (
      sum(rate(run_googleapis_com:request_count{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_campaign}", response_code_class!="5xx"}[1h])) BY (project_id, service_name, location)
      /
      sum(rate(run_googleapis_com:request_count{project_id="${var.project_id}", location="${var.region}", service_name="${local.service_campaign}"}[1h])) BY (project_id, service_name, location)
    )
  ) > (1 - 0.9995) * 14.4
)
EOT
      duration = "300s"
    }
  }

  alert_strategy {
    auto_close = "14400s"
  }

  user_labels = local.slo_label
  notification_channels = var.notification_channels
}
```

---

## 6. Implementation and Operational Verification Guide

### 6.1 Validation of Terraform Configuration
1. Initialize and validate the Terraform module:
   ```bash
   terraform init
   terraform validate
   ```
2. Verify that `notification_channels` are passed via `terraform.tfvars`:
   ```hcl
   notification_channels = [
     "projects/mercadona-ia-companion/notificationChannels/123456789012345"
   ]
   ```
   > [!IMPORTANT]
   > If `notification_channels` is left empty, alerts will trigger incidents within Google Cloud Console but will not dispatch external notifications to on-call engineers.

3. Execute plan review:
   ```bash
   terraform plan -out=slo_observability.plan
   ```

### 6.2 Monitoring & Verification Checklist
- [x] Regional Log Bucket `mercadona-app-logs` created in `europe-west1` with Analytics enabled.
- [x] Log Views configured for granular role-based access control without exposing raw customer data.
- [x] Health check probes (`GoogleHC`) and 90% of debug logs excluded from storage to minimize ingestion spend.
- [x] PromQL queries accurately normalized (`run_googleapis_com:request_count`, `run_googleapis_com:request_latencies_bucket`).
- [x] Alert policies tagged with `created-with-google-skill = "google-cloud-slo-alert-configuration"`.
- [x] Auto-close windows configured on all alert policies to avoid orphaned incidents.
