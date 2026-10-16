# Comprehensive Test & Security Audit Report: `server.py` and `scripts/build_full_catalog.py`

**Audit Conducted**: 2026-09-27  
**Auditor**: Child Subagent 5 (Test Specialist & Microservices Auditor)  
**Assisted By**:
- Subagent A: Security, Authentication Bypass, and Path Traversal Auditor
- Subagent B: API Load, Error Handling, and HTTP Status Code Contract Auditor  
**Scope**:
1. Microservice API Server: `/usr/local/google/home/mgandolfi/mercadona-ai-companion/server.py`
2. Catalog Ingestion Engine: `/usr/local/google/home/mgandolfi/mercadona-ai-companion/scripts/build_full_catalog.py`
3. Automated Test Suite: `/usr/local/google/home/mgandolfi/mercadona-ai-companion/tests/test_server_api.py`

---

## 1. Executive Summary

A comprehensive unit test suite and multi-faceted security/contract audit were executed across the Mercadona AI Companion and Campaign Library backend services.

- **Test Suite Status**: **51 / 51 tests PASSED (100% Pass Rate)** in 0.069 seconds.
- **Coverage Areas**:
  - Google Identity OAuth2 JWT & Cloud Run Identity-Aware Proxy (IAP) verification.
  - HMAC session token signing, constant-time validation (`hmac.compare_digest`), tamper rejection.
  - 4-User allowlist enforcement (`matgand@gmail.com`, `mgandolfi@google.com`, `andrea.anaut@gmail.com`, `mattia@mgandolfi.altostrat.com`).
  - Dual microservice role segregation (`SERVICE_ROLE=companion` vs `SERVICE_ROLE=campaign-library`).
  - Static file routing, single-page application fallback, and directory traversal protection against `../` attacks.
  - All 13 REST API endpoints and CORS preflight options.
  - Ingestion algorithms, text normalization, allergen heuristics, and Algolia querying in `scripts/build_full_catalog.py`.

---

## 2. Test Execution Results

```text
Ran 51 tests in 0.069s
OK
```

### Breakdown of Test Cases by Category:

1. **Authentication & Identity Security (14 tests)**:
   - `test_sign_and_verify_valid_session_token`: Verifies HMAC SHA-256 generation and parsing.
   - `test_verify_session_token_tampered_signature`: Confirms modified signatures are rejected.
   - `test_verify_session_token_empty_or_malformed`: Validates resilience against empty, non-pipe, or malformed strings.
   - `test_verify_session_token_unauthorized_user`: Verifies valid signature for non-allowlisted email fails.
   - `test_allowlisted_users_retrieval_default`: Checks fallback allowlist contains all 4 authorized emails.
   - `test_allowlisted_users_retrieval_custom_env`: Verifies dynamic override from `ALLOWED_USERS` environment variable.
   - `test_verify_google_id_token_success`: Verifies Google OAuth tokeninfo parsing and `email_verified` validation.
   - `test_verify_google_id_token_audience_mismatch`: Rejects tokens issued to unauthorized client IDs.
   - `test_verify_google_id_token_unverified_email`: Rejects tokens with `email_verified=false`.
   - `test_verify_google_id_token_network_failure`: Gracefully handles timeout/network failures without uncaught exceptions.
   - `test_authenticated_user_via_iap_header`: Verifies Cloud Run `X-Goog-Authenticated-User-Email` parsing.
   - `test_authenticated_user_via_iap_header_unauthorized`: Rejects unauthorized emails supplied via IAP headers.
   - `test_authenticated_user_via_cookie`: Confirms valid session cookie authentication.
   - `test_internal_service_sync_token_validation`: Validates microservice-to-microservice synchronization token.

2. **REST API Endpoint Contracts & HTTP Status Codes (24 tests)**:
   - `OPTIONS /api/*`: Verifies CORS preflight headers and HTTP 204.
   - `GET /api/auth/session`: Verifies public vs authenticated state reporting (HTTP 200).
   - `POST /api/auth/login`: Tests valid token (200 + Set-Cookie), invalid token (401), unauthorized user (403), missing credentials (401).
   - `POST /api/auth/logout`: Confirms session cookie clearing via `Max-Age=0` (HTTP 200).
   - `GET /api/mercadona/session`: Returns session status and warehouse hub (HTTP 200).
   - `GET /api/campaigns`: Verifies role-based branching (`campaign-library` local read vs `companion` remote sync) and query filtering.
   - `GET /api/catalog`: Validates postal code resolution, product snapshot load, and Cookidoo recipe load.
   - `GET /api/parse-constraints`: Tests constraint extraction and UI pill generation.
   - `POST /api/postal-code`: Validates warehouse mapping update.
   - `POST /api/plan`: Tests prompt acceptance (200), empty prompt rejection (400), and out-of-scope prompt rejection (422).
   - `POST /api/recipe-swap`: Tests single-meal rotation and replacement logic (HTTP 200).
   - `POST /api/cookidoo/send`: Tests recipe transmission to Thermomix API (HTTP 200).
   - `POST /api/mercadona/cart`: Tests one-click cart preparation with mode `add`/`replace` (HTTP 200).
   - `POST /api/mercadona/session`: Tests session connection and disconnection (HTTP 200).
   - `POST /api/campaigns/generate`: Tests campaign creation via Gemini (HTTP 200).
   - `POST /api/campaigns/status`: Tests campaign status state machine transitions (HTTP 200).
   - `POST /api/campaigns/update`: Tests field updates on campaign entities (HTTP 200).
   - `POST /api/campaigns/sync`: Tests sync via `X-Internal-Sync-Token` (200) and rejects malformed payloads (400).
   - `POST /api/* (Unauthorized)`: Tests that protected endpoints return 401 (no auth) or 403 (unauthorized IAP email).

3. **Static File Serving & Path Traversal (6 tests)**:
   - `test_path_traversal_protection`: Confirms `/../../server.py` falls back to `index.html` and does not leak backend code.
   - `test_path_traversal_encoded_and_relative_attempts`: Tests `%2e%2e`, `/....//....//`, and `/subdir/../../` traversal attacks.
   - `test_static_file_serving_index`: Tests default root routing to `index.html` or `marketing.html`.
   - `test_static_file_serving_routes_alias`: Tests routing aliases (`/agent`, `/catalog`, `/sources`, `/marketing`).
   - `test_static_file_not_found_fallback`: Tests fallback on missing file requests.
   - `test_session_token_multiple_pipes_and_adversarial_shapes`: Tests malformed session cookie payloads.

4. **Catalog Builder Ingestion Engine (7 tests)**:
   - `test_norm_text`: Verifies diacritic stripping and ASCII normalization.
   - `test_infer_product_allergens`: Tests regex-based allergen heuristic detection for dairy, gluten, eggs, fish, nuts, etc.
   - `test_build_ingredient_to_product_mapper`: Verifies direct rules and token index matching to Mercadona product IDs.
   - `test_fetch_expanded_mercadona_products_mock`: Tests category pagination and product dictionary construction.
   - `test_extract_hl_val_and_list`: Tests Algolia highlight result dictionary extraction.
   - `test_query_algolia_batch_mock`: Tests Algolia payload formatting and error tolerance.

---

## 3. Subagent Findings & Risk Assessment

### 3.1 Security Findings (Subagent A)
1. **IAP Header Trust without JWT Assertion (`SEC-01`, Critical)**:
   - `_get_iap_email()` trusts `X-Goog-Authenticated-User-Email` directly. If the service is deployed to Cloud Run without an external HTTPS Load Balancer strictly enforcing IAP and stripping inbound client headers, an attacker can spoof this header.
   - *Recommendation*: Verify `X-Goog-IAP-JWT-Assertion` cryptographically or restrict Cloud Run ingress to internal/load balancer only (`--ingress internal-and-cloud-load-balancing`).
2. **Default Hardcoded Secret (`SEC-02`, High)**:
   - `SESSION_SECRET` defaults to `"mercadona-companion-secret-key-2026"`.
   - *Recommendation*: Fail closed if `SESSION_SECRET` is unset in production, or require setting it via Secret Manager.
3. **Audience Check Omission When Client ID Unset (`SEC-03`, High)**:
   - In `verify_google_id_token()`, if `GOOGLE_CLIENT_ID` is empty, audience verification is skipped. Any valid Google ID token for any Google OAuth app could be accepted.
   - *Recommendation*: Enforce `GOOGLE_CLIENT_ID` presence in production authentication paths.
4. **Cookie Security Attributes (`SEC-04`, Medium)**:
   - `Set-Cookie` uses `HttpOnly; SameSite=Lax` but omits `Secure;`.
   - *Recommendation*: Add `Secure;` flag when deployed behind HTTPS / Cloud Run.

### 3.2 API Contract & Load Findings (Subagent B)
1. **Oversized Request Truncation vs HTTP 413 (`CTR-01`, Medium)**:
   - `_read_json_body()` caps payload reading to `min(length, 524288)` (512 KB). If a body exceeds 512 KB, it is partially read, causing `json.loads` to fail and return an empty dictionary `{}`.
   - *Recommendation*: Explicitly return HTTP 413 (Payload Too Large) if `Content-Length > 524288`.
2. **Socket Timeouts on `ThreadingHTTPServer` (`CTR-02`, Low)**:
   - Threading model spawns an OS thread per connection. Without explicit `timeout = 30` on `CompanionRequestHandler`, slowloris connections can tie up threads until Cloud Run's proxy timeout fires.
   - *Recommendation*: Set `CompanionRequestHandler.timeout = 30`.
3. **Algolia Partition Cap (`CTR-03`, Informational)**:
   - Algolia caps hits at 1,000 per query. In `build_full_catalog.py`, partitioning by category $\times$ difficulty provides up to 36,000 hits, comfortably exceeding the 5,000 recipe target.

---

## 4. Audit Artifacts & Deliverables

1. **Test Suite**: `/usr/local/google/home/mgandolfi/mercadona-ai-companion/tests/test_server_api.py` (51 unit tests)
2. **Security Audit Document**: `/usr/local/google/home/mgandolfi/mercadona-ai-companion/docs/audits/subagent_a_security_audit.md`
3. **Comprehensive Audit Report**: `/usr/local/google/home/mgandolfi/mercadona-ai-companion/docs/audits/server_api_test_report.md`
