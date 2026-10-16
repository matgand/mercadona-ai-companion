# Subagent A: Security, Authentication Bypass, and Path Traversal Audit Report

**Target Services:** `server.py` (Mercadona AI Companion & Campaign Library Microservices)  
**Test Suite Target:** `tests/test_server_api.py`  
**Auditor:** Subagent A (Security, Authentication Bypass, and Path Traversal Auditor)  
**Date:** September 2026  
**Status:** Audit Completed — Remediations Proposed

---

## 1. Executive Summary

This security audit conducted an exhaustive source code review and adversarial threat analysis of `server.py` and its corresponding test suite `tests/test_server_api.py`. The service operates in dual roles (`companion` and `campaign-library`), handling consumer meal planning, Cookidoo/Thermomix integration, Mercadona cart creation, and marketing campaign lifecycle management.

While `server.py` implements commendable defensive patterns—such as constant-time comparison (`hmac.compare_digest`), bounded payload ingestion (512 KB), and strict path canonicalization against directory traversal—several critical vulnerabilities and architecture weaknesses were uncovered:
1. **Critical Authentication Bypass Risk via Spoofed IAP Headers:** `server.py` trusts `X-Goog-Authenticated-User-Email` directly without verifying the cryptographic `X-Goog-IAP-JWT-Assertion` token. If the service is accessed directly (e.g., standard Cloud Run URLs without strict internal/load-balancer ingress restriction), any untrusted client can impersonate an allowlisted user by simply forging this header.
2. **Hardcoded HMAC Secret & Static Token Generation:** The default `SESSION_SECRET` fallback allows immediate offline computation and forgery of both session cookies and the internal microservice sync token (`X-Internal-Sync-Token`).
3. **OAuth2 ID Token Confused Deputy / Audience Bypass:** When `GOOGLE_CLIENT_ID` is empty or unset, `verify_google_id_token()` skips audience validation, allowing any valid Google ID token issued for any other app to authenticate.
4. **Session Token Design Weaknesses:** Tokens lack server-side expiration timestamps and nonces, rendering valid sessions non-expiring on the server, while session cookies omit the `Secure` flag.
5. **Permissive CORS Wildcard (`*`):** Wildcard origins on sensitive endpoints enable cross-origin interactions and bearer-token replay across untrusted origins.
6. **Information Disclosure:** `/api/auth/session` exposes the entire user allowlist to unauthenticated clients.

---

## 2. Findings Matrix

| ID | Title | Severity | Impact | Exploitability |
|---|---|---|---|---|
| **SEC-01** | Header-Based IAP Authentication Bypass (Missing JWT Verification) | **CRITICAL** | Complete Auth Bypass / Account Takeover | High (if direct ingress reachable) |
| **SEC-02** | Known Default `SESSION_SECRET` & Static Sync Token Derivation | **HIGH** | Arbitrary Session Forgery / Sync Manipulation | High (in default/dev deployments) |
| **SEC-03** | Google OAuth2 ID Token Confused Deputy (Unenforced Audience) | **HIGH** | Privilege Escalation via 3rd-Party Google Tokens | Medium |
| **SEC-04** | Session Tokens Lack Server-Side Expiration & `Secure` Cookie Flag | **MEDIUM** | Indefinite Session Validity / Insecure Transport | Medium |
| **SEC-05** | Overly Permissive CORS Policy (`Access-Control-Allow-Origin: *`) | **MEDIUM** | Cross-Origin Data Leakage / CSRF Amplification | Medium |
| **SEC-06** | Information Disclosure: Unauthenticated Allowlist Enumeration | **LOW** | Reconnaissance / Targeted Phishing | High |
| **SEC-07** | Inconsistent Authorization on Campaign Endpoints (GET vs POST) | **LOW** | Unauthenticated Campaign Intel Disclosure | High |
| **SEC-08** | Static File Path Traversal Defense-in-Depth Hardening | **INFO** | Path Traversal Resilience (Prefix Boundary check) | Low (Currently Mitigated) |

---

## 3. Detailed Security Findings

### SEC-01: Header-Based IAP Authentication Bypass (Missing JWT Verification)
- **Severity:** CRITICAL (CVSS 9.1: AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N)
- **Location:** `server.py` lines 120–124, 134–137:
  ```python
  def _get_iap_email(self) -> str | None:
      iap_email = self.headers.get("X-Goog-Authenticated-User-Email", "").strip()
      if iap_email:
          return iap_email.split(":")[-1].strip().lower()
      return None
  ```
- **Vulnerability Mechanics:**
  When deploying behind Google Cloud Identity-Aware Proxy (IAP), Google strips incoming client headers and injects `X-Goog-Authenticated-User-Email` and `X-Goog-IAP-JWT-Assertion`. However, if the Cloud Run service is reachable directly via its `*.run.app` URL (e.g., if Cloud Run Ingress is set to "All" rather than "Internal and Cloud Load Balancing"), external clients can directly provide `X-Goog-Authenticated-User-Email: accounts.google.com:mgandolfi@google.com`.
  Because `_get_authenticated_user()` checks `_get_iap_email()` first and immediately returns the parsed email if it exists in `allowed`, an external attacker gains immediate, full access as `mgandolfi@google.com`, `matgand@gmail.com`, or any other allowlisted user.
- **Impact:** Complete bypass of authentication. Attacker can access Mercadona cart creation, Thermomix Cookidoo triggers, and marketing campaign modification.
- **Remediation:**
  1. Validate the cryptographic signature of the `X-Goog-IAP-JWT-Assertion` header using Google public keys (`https://www.gstatic.com/iap/verify/public_key-jwk`) and verify the JWT audience matches the expected project number and backend service ID (`/projects/{PROJECT_NUMBER}/apps/{PROJECT_ID}` or `/projects/{PROJECT_NUMBER}/global/backendServices/{SERVICE_ID}`).
  2. Enforce Cloud Run Ingress restriction: `gcloud run services update --ingress=internal-and-cloud-load-balancing`.
  3. If running locally or without IAP, only accept IAP headers if an explicit environment variable `ENFORCE_IAP=false` is set or reject plain headers without JWT verification.

---

### SEC-02: Known Default `SESSION_SECRET` & Static Sync Token Derivation
- **Severity:** HIGH (CVSS 8.1: AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N)
- **Location:** `server.py` lines 55, 87, 95, 126–129:
  ```python
  SESSION_SECRET = os.environ.get("SESSION_SECRET", "mercadona-companion-secret-key-2026")
  ...
  def _is_internal_service_sync(self) -> bool:
      expected = hashlib.sha256(f"internal-sync:{SESSION_SECRET}".encode("utf-8")).hexdigest()[:32]
      provided = self.headers.get("X-Internal-Sync-Token", "").strip()
      return bool(provided and hmac.compare_digest(provided, expected))
  ```
- **Vulnerability Mechanics:**
  1. If `SESSION_SECRET` is not explicitly set in the deployment environment, the default string `"mercadona-companion-secret-key-2026"` is active.
  2. Anyone with access to the source code can immediately forge:
     - Session token for `matgand@gmail.com`: `matgand@gmail.com|d29d402ff6c4f0b207bdfb16f8561495`
     - Internal sync token: `7ea734e89e96c9d67f930d51226c0b9a`
  3. The internal sync token is derived via a single SHA256 of `internal-sync:{SESSION_SECRET}`. This reuses the session secret for service-to-service authentication without key separation or rotation.
  4. Truncation to 32 hex characters (128 bits) unnecessarily discards half of the SHA-256 entropy.
- **Remediation:**
  1. Enforce that `SESSION_SECRET` must be set via environment variable in production; raise an error or warn aggressively on startup if default or short (< 32 chars) keys are detected.
  2. Separate internal synchronization credentials: use a dedicated `INTERNAL_SYNC_SECRET` instead of deriving from `SESSION_SECRET`.
  3. Use full 64-character SHA-256 hex digest for both session signatures and sync tokens.

---

### SEC-03: Google OAuth2 ID Token Confused Deputy (Unenforced Audience)
- **Severity:** HIGH (CVSS 7.5: AV:N/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:N)
- **Location:** `server.py` lines 56, 108–109:
  ```python
  GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
  ...
  if GOOGLE_CLIENT_ID and data.get("aud") != GOOGLE_CLIENT_ID:
      return None
  ```
- **Vulnerability Mechanics:**
  If `GOOGLE_CLIENT_ID` is empty (the default if unset), the conditional `if GOOGLE_CLIENT_ID` evaluates to `False`. The server then accepts **any** valid Google ID token for an allowlisted email (`email_verified: true`), regardless of what Google OAuth application (`aud`) issued the token!
  In a Confused Deputy scenario, an attacker who controls a separate, benign Google Sign-In application could trick an allowlisted user (e.g., `mgandolfi@google.com`) into logging into their app. The attacker receives a legitimate Google ID token where `aud` is the attacker's app client ID, but `email` is `mgandolfi@google.com`. Because `GOOGLE_CLIENT_ID` is unconfigured, the attacker can replay that token to `/api/auth/login` on the companion server and authenticate successfully.
- **Remediation:**
  Enforce `GOOGLE_CLIENT_ID` check strictly:
  ```python
  if not GOOGLE_CLIENT_ID:
      # In production, refuse to verify ID tokens without an expected audience
      return None
  if data.get("aud") != GOOGLE_CLIENT_ID:
      return None
  ```

---

### SEC-04: Session Tokens Lack Server-Side Expiration & `Secure` Cookie Flag
- **Severity:** MEDIUM (CVSS 5.3: AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:N)
- **Location:** `server.py` lines 85–98, 362:
  ```python
  def sign_session_email(email: str) -> str:
      clean = email.strip().lower()
      sig = hmac.new(SESSION_SECRET.encode("utf-8"), clean.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
      return f"{clean}|{sig}"
  ...
  cookie = f"mercadona_session={signed}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800"
  ```
- **Vulnerability Mechanics:**
  1. The session token format is `email|sig`. There is **no timestamp, no expiration time, and no session ID/nonce**.
  2. The browser cookie header has `Max-Age=604800`, but client-side cookie expiry can be overridden or captured tokens can be replayed directly in HTTP requests indefinitely. The server has no mechanism to expire or revoke a compromised token.
  3. The `Secure` flag is missing from `Set-Cookie`. Although Cloud Run runs over HTTPS, missing `Secure` exposes the cookie to accidental transmission over plaintext HTTP during local redirects or development networks.
- **Remediation:**
  1. Pack a timestamp into the session token: `email|timestamp|sig`, where `sig = HMAC(secret, f"{email}|{timestamp}")`.
  2. Reject tokens where `current_time - timestamp > 7 * 86400`.
  3. Append `Secure;` to the cookie definition (or conditionally enable if `os.environ.get("DEV_INSECURE_COOKIES")` is not set).

---

### SEC-05: Overly Permissive CORS Policy (`Access-Control-Allow-Origin: *`)
- **Severity:** MEDIUM (CVSS 5.3: AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N)
- **Location:** `server.py` lines 159–163, 170:
  ```python
  def _add_cors_headers(self) -> None:
      self.send_header("Access-Control-Allow-Origin", "*")
      self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
      self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
  ```
- **Vulnerability Mechanics:**
  Wildcard CORS (`*`) is attached to all responses, including authenticated ones. While browsers block credentialed (`withCredentials: true`) requests with wildcard origin, requests authenticating via `Authorization: Bearer <Google_ID_Token>` can be triggered and read from arbitrary third-party web pages.
- **Remediation:**
  Restrict `Access-Control-Allow-Origin` to known trusted origins (e.g., the Companion App URL and Campaign Library URL), or reflect `Origin` only if it matches approved patterns.

---

### SEC-06: Information Disclosure: Unauthenticated Allowlist Enumeration
- **Severity:** LOW (CVSS 3.7: AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N)
- **Location:** `server.py` lines 196–214:
  ```python
  if path == "/api/auth/session":
      user = self._get_authenticated_user()
      iap_email = self._get_iap_email()
      self._send_json(
          200,
          {
              "authenticated": bool(user),
              "user": user,
              "iap_email": iap_email,
              "auth_mode": "iap",
              "allowed_users": get_allowed_users(),
              ...
  ```
- **Vulnerability Mechanics:**
  Any unauthenticated client sending `GET /api/auth/session` receives the full `allowed_users` list: `["matgand@gmail.com", "mgandolfi@google.com", "andrea.anaut@gmail.com", "mattia@mgandolfi.altostrat.com"]`.
  This leaks internal email addresses and organization domains to unauthorized observers.
- **Remediation:**
  Only include `allowed_users` in the response when `user is not None` (i.e. caller is already authenticated) or omit entirely from public client payloads.

---

### SEC-07: Inconsistent Authorization on Campaign Endpoints
- **Severity:** LOW (CVSS 4.3: AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N)
- **Location:** `server.py` lines 221–248 (GET unauthenticated) vs lines 385–438 (POST authenticated):
  - `GET /api/campaigns` returns all campaigns (including draft, paused, and active marketing data) to any anonymous caller.
  - Line 384 comments state: *"Require real Google Cloud IAP / verified Google authentication for BOTH main app AND Campaign Library"*, but this check is only implemented in `do_POST`.
- **Remediation:**
  If campaigns contain proprietary marketing plans and briefs, apply `_get_authenticated_user()` check to `GET /api/campaigns` as well.

---

### SEC-08: Path Traversal & Static Serving Analysis
- **Severity:** INFORMATIONAL / DEFENSE-IN-DEPTH
- **Location:** `server.py` lines 283–286:
  ```python
  file_path = (PUBLIC_DIR / rel).resolve()
  if not str(file_path).startswith(str(PUBLIC_DIR)) or not file_path.is_file():
      file_path = PUBLIC_DIR / default_html
  ```
- **Analysis:**
  - **Good:** Canonicalization via `.resolve()` resolves `..`, `.`, and symbolic links.
  - **Good:** Traversal attempts like `/../../etc/passwd` fail the prefix check and safely fall back to serving `default_html` (`index.html` or `marketing.html`) without throwing unhandled exceptions or crashing the server.
  - **Subtle Edge Case:** `str(file_path).startswith(str(PUBLIC_DIR))` has a classic directory boundary flaw if a directory exists at `public_private` or `public2`. For instance, if `PUBLIC_DIR` is `/app/public`, a path resolving to `/app/public_secret/file.txt` matches `.startswith("/app/public")`.
  - **Remediation:**
    Use `PUBLIC_DIR.resolve()` with a trailing slash or Python 3.9+ `file_path.is_relative_to(PUBLIC_DIR)`:
    ```python
    try:
        file_path.relative_to(PUBLIC_DIR)
    except ValueError:
        file_path = PUBLIC_DIR / default_html
    ```

---

## 4. Evaluation of Test Suite (`tests/test_server_api.py`)

The test suite in `tests/test_server_api.py` contains 49 tests. While foundational scenarios are covered, there are significant gaps regarding edge cases and adversarial inputs:

### Existing Strengths
- Tests basic HMAC tampering (`deadbeef` signature).
- Tests empty and pipe-less malformed tokens.
- Tests tokeninfo success, audience mismatch, unverified email, and network failure.
- Tests path traversal with `/../../server.py`.
- Tests basic unauthenticated 401 and unauthorized IAP 403.

### Critical Test Suite Blind Spots & Missing Adversarial Tests
1. **IAP Header Spoofing Blind Spot:**
   - Currently, `test_authenticated_user_via_iap_header` simply tests that setting `X-Goog-Authenticated-User-Email` authenticates the user. It does not test or flag whether unauthenticated external callers can forge this header.
2. **Missing Google OAuth2 Empty `GOOGLE_CLIENT_ID` Test:**
   - Tests do not cover the security hazard when `GOOGLE_CLIENT_ID` is empty string (confused deputy bypass).
3. **Session Token Adversarial Edge Cases:**
   - Multiple pipe characters (e.g. `user|evil|sig`).
   - Signature length mismatch (truncated, padded, or uppercase hex).
   - Replay / expiration testing (currently impossible because no timestamp exists).
4. **Static File Serving Edge Cases:**
   - Encoded traversal sequences (`%2e%2e%2f`, `%252e%252e%252f`).
   - Null-byte injection (`index.html%00.png`).
   - Windows-style backslash traversal (`\..\..\etc\passwd`).
   - Directory requests (`/` vs `/images/`).
5. **CORS Edge Cases:**
   - Verification that CORS headers are not allowing credentialed exfiltration.
6. **Internal Sync Token Edge Cases:**
   - Default secret predictability test.
   - Timing attack / empty token / invalid hex token handling.
7. **Allowlist Normalization Edge Cases:**
   - Mixed-case emails (`MatGand@Gmail.Com`).
   - Whitespace padding (` matgand@gmail.com `).
   - Subdomain matching / malicious lookalike domains (`matgand@gmail.com.attacker.com`).

---

## 5. Recommended Code Fixes & Hardening Plan

### 5.1 Hardened `server.py` Patch (Authentication & Security)

```python
# 1. Enforce GOOGLE_CLIENT_ID in production
def verify_google_id_token(id_token: str) -> str | None:
    """Verifies a Google Identity Services JWT against Google's tokeninfo endpoint."""
    if not GOOGLE_CLIENT_ID:
        # Require CLIENT_ID to prevent Confused Deputy attacks
        return None
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(id_token)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mercadona-AI-Companion"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("aud") != GOOGLE_CLIENT_ID:
                return None
            if data.get("email_verified") in ("true", True):
                return str(data.get("email", "")).strip().lower()
    except Exception:
        return None
    return None

# 2. Time-bounded, Tamper-resistant Session Tokens with Full 64-char SHA256 HMAC
SESSION_TTL_SECONDS = 7 * 86400  # 7 days

def sign_session_email(email: str) -> str:
    clean = email.strip().lower()
    ts = str(int(time.time()))
    payload = f"{clean}:{ts}"
    sig = hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}|{sig}"

def verify_session_token(token: str | None) -> str | None:
    if not token or "|" not in token:
        return None
    payload, sig = token.rsplit("|", 1)
    if ":" not in payload:
        return None
    email, ts_str = payload.split(":", 1)
    try:
        ts = int(ts_str)
        if time.time() - ts > SESSION_TTL_SECONDS or ts > time.time() + 300:
            return None  # Expired or from future
    except ValueError:
        return None
    expected = hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected) and email in get_allowed_users():
        return email
    return None

# 3. Secure Path Traversal Verification
def _resolve_safe_static_file(rel: str, default_html: str) -> Path:
    file_path = (PUBLIC_DIR / rel).resolve()
    try:
        file_path.relative_to(PUBLIC_DIR)
        if not file_path.is_file():
            return PUBLIC_DIR / default_html
        return file_path
    except ValueError:
        return PUBLIC_DIR / default_html

# 4. Strict IAP JWT verification header check
# In Cloud Run with IAP, require X-Goog-IAP-JWT-Assertion in production or flag untrusted direct requests.
```

---

## 6. Conclusion

The application architecture demonstrates good security hygiene with allowlist validation, HMAC verification, and path containment. However, the identified vulnerabilities around **IAP header spoofing**, **confused deputy OAuth token acceptance**, **default session secret re-use**, and **session tokens without expiration** should be addressed before enterprise deployment. Detailed unit tests covering these adversarial edge cases should be integrated into `test_server_api.py`.
