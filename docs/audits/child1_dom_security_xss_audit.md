# Frontend DOM Security, XSS & Authentication State Audit
**Repository**: `/usr/local/google/home/mgandolfi/mercadona-ai-companion`  
**Target Services**: Mercadona AI Shopping Companion (`app.js`, `index.html`) & Campaign Library (`marketing.js`, `marketing.html`)  
**Auditor**: Child Subagent 1 — DOM Security, XSS & Auth State Auditor  
**Audit Scope**: Client-Side DOM Manipulations, XSS Vector Analysis, URL & Deep-Link Routing, Google OAuth / GSI Integration, Mercadona & Cookidoo Credential Handling, CSP / SRI / Framing Controls  
**Date**: September 2026  

---

## Executive Summary

A comprehensive, defense-in-depth security audit of the frontend presentation layer and associated client-server interaction patterns was conducted across:
- `public/index.html` (29 lines)
- `public/marketing.html` (28 lines)
- `public/app.js` (1,821 lines)
- `public/marketing.js` (812 lines)
- Related backend authentication, CORS, and header delivery routines in `server.py`, `mercadona_service.py`, and `campaign_service.py`.

### Key Findings Summary
1. **Critical Defenses Absent**: The application lacks a **Content Security Policy (CSP)** entirely, provides no framing restrictions (**Clickjacking / UI Redressing** vulnerability via missing `X-Frame-Options` and `frame-ancestors`), sets permissive wildcard CORS (`Access-Control-Allow-Origin: *`) across all API and static responses, and lacks **Subresource Integrity (SRI)** on third-party dependencies.
2. **Incomplete HTML Entity Encoding in `escapeHtml()`**: Both `app.js` (lines 196–202) and `marketing.js` (lines 67–73) employ a naive four-character sanitization routine (`&`, `<`, `>`, `"`). Single quotes (`'`), backticks (``` ` ```), and forward slashes (`/`) are omitted, leaving attribute contexts vulnerable to breakout when single quotes are utilized.
3. **Unescaped Dynamic Interpolations in Template Literals**: Multiple dynamic fields sourced from external APIs or backend LLM outputs (`p.constraints.maxCaloriesPerServing`, `selected.maxCaloriesPerServing`, `r.calories_per_serving`, `r.minutes`, `meal.cookidoo_servings`, `item.quantity`) are directly interpolated into `root.innerHTML` without passing through `escapeHtml()`, creating potential stored/DOM XSS vectors.
4. **Unvalidated Protocol Handlers on Dynamic Links & `window.open()`**: Links such as `state.campaignLibraryUrl`, `mState.companionAppUrl`, `item.share_url`, and the `window.open(cookidooUrl, ...)` handler in `sendToThermomix()` lack scheme and origin validation (e.g., verifying `https:` and trusted domain prefixes), presenting potential Open Redirect and `javascript:` pseudo-protocol execution vectors.
5. **Ghost Google Identity Services (GSI) Dependency**: `index.html` synchronously fetches the external script `https://accounts.google.com/gsi/client`, yet `google.accounts.id` is never initialized or referenced anywhere in `app.js`. This creates an unnecessary third-party supply chain risk with no SRI or CSP gating.
6. **High-Risk Third-Party Credential Handling in Frontend DOM**: The interface instructs users to extract authentication tokens from DevTools using "Copy as cURL" and paste them into a `<textarea>`. Plaintext Mercadona Bearer tokens, refresh tokens, and Cookidoo passwords reside unencrypted in JavaScript heap state (`state.mercadonaAuthInput`, `state.cookidooPassword`), making them immediately accessible to memory scrapers or any script execution vector.

---

## 1. Vulnerability Matrix & Threat Landscape

The following matrix classifies all identified findings in accordance with OWASP Top 10 (2021) and Common Weakness Enumeration (CWE) standards:

| ID | Vulnerability Classification | CWE | Severity | CVSS v3.1 | Primary Files & Line References | Impact |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **VULN-01** | Missing Content Security Policy (CSP) & Permissive Wildcard CORS | CWE-358, CWE-942 | **HIGH** | 7.5 | `index.html:1-29`, `marketing.html:1-28`, `server.py:160` | Arbitrary script execution if any injection vector exists; resource exfiltration |
| **VULN-02** | Missing Clickjacking Defense (`X-Frame-Options` / `frame-ancestors`) | CWE-1021 | **MEDIUM** | 6.5 | `server.py:164-175, 301-306`, `index.html`, `marketing.html` | UI redressing; malicious sites can frame the app to force 1-click Mercadona cart actions |
| **VULN-03** | Incomplete Entity Encoding in `escapeHtml()` | CWE-79, CWE-116 | **MEDIUM** | 6.1 | `app.js:196-202`, `marketing.js:67-73` | Single-quote attribute breakout in dynamically generated markup |
| **VULN-04** | Unescaped API Variables in Template Literal DOM Sinks | CWE-79 | **HIGH** | 7.2 | `app.js:859, 930, 1013, 1458, 1460`, `marketing.js:659` | Direct DOM XSS via unescaped integers/strings from backend/Gemini payloads |
| **VULN-05** | Unvalidated Scheme & Origin on External Links and `window.open` | CWE-601, CWE-79 | **MEDIUM** | 5.4 | `app.js:518, 754, 1009`, `marketing.js:356, 362, 673` | Execution of `javascript:` URLs or redirection to malicious phishing targets |
| **VULN-06** | Unused Google Identity Services (GSI) Script Without SRI | CWE-829, CWE-353 | **LOW** | 3.7 | `index.html:22` | Third-party supply chain risk; phantom dependency; potential script hijacking |
| **VULN-07** | In-Memory Plaintext Credential Handling (Mercadona JWT & Cookidoo) | CWE-312, CWE-532 | **HIGH** | 7.1 | `app.js:520-527, 871-885, 1081-1086, 1675-1702` | Credential leakage via DOM scraping, XSS exfiltration, or malicious browser extensions |
| **VULN-08** | Inline Event Handler Violating CSP Directives | CWE-79 | **LOW** | 3.5 | `app.js:682`, `marketing.js:95` | Blocks strict CSP deployment; potential secondary DOM injection point |
| **VULN-09** | Full DOM Replacement via `root.innerHTML` (State Destruction) | CWE-400 | **LOW** | 2.5 | `app.js:1500`, `marketing.js:352` | Focus loss, input state desynchronization, potential DOM clobbering |
| **VULN-10** | Missing Client-Side Session Expiry & 401/403 Handling | CWE-613 | **MEDIUM** | 4.3 | `app.js:438-465`, `marketing.js:208-240` | Degraded UX; stale session actions fail silently or display confusing error notices |

---

## 2. DOM Manipulation & Cross-Site Scripting (XSS) Deep Dive

### 2.1 Incomplete Entity Encoding in `escapeHtml()`
In both `public/app.js` and `public/marketing.js`, the core sanitization mechanism is defined as:

```javascript
// public/app.js (lines 196-202) & public/marketing.js (lines 67-73)
function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
```

#### Vulnerability Analysis:
1. **Omission of Single Quotes (`'`)**: Single quotes are neither converted to `&#39;` nor `&#x27;`. While the current template literals predominantly wrap attributes in double quotes (`"`), any attribute rendered in single quotes (e.g. `data-param='${escapeHtml(value)}'`) is immediately vulnerable to attribute breakout via input containing a single quote `'`.
2. **Omission of Backticks (``` ` ```)**: In ES6 template literal contexts and older Internet Explorer / legacy rendering modes, unescaped backticks can cause execution leakage.
3. **Omission of Forward Slash (`/`)**: Forward slashes are not escaped to `&#x2F;`, which allows closing HTML tags if an attribute is unquoted or if a browser attempts lenient attribute recovery.

#### Attack Scenario:
If an attribute were ever authored as:
```javascript
`<button data-user='${escapeHtml(username)}' onclick='showUser(this)'>`
```
An attacker inputting `admin' autofocus onfocus='alert(document.domain)' ` would achieve instant script execution.

---

### 2.2 Unescaped Dynamic Interpolations in Template Literals
Both applications construct complex HTML trees via template literals assigned directly to `root.innerHTML`. While most user-entered strings pass through `escapeHtml()`, several variables bypass sanitization under the assumption that they are strictly numeric or pre-sanitized.

#### 1. Plan Constraints: `p.constraints.maxCaloriesPerServing`
- **Location**: `public/app.js`, line 859
```javascript
// public/app.js:859
${p.constraints.maxCaloriesPerServing ? `<span>✓ ≤ ${p.constraints.maxCaloriesPerServing} kcal / ración</span>` : ""}
```
- **Source**: Returned from `/api/plan`, which extracts constraints using Vertex AI Gemini inference or regex parsing (`gemini_planner.py`).
- **Defect**: If the Gemini response returns a string containing HTML entities (e.g., `"450<img src=x onerror=alert(1)>"`) or if an adversary modifies a stored plan payload, the raw HTML is parsed and executed directly by `root.innerHTML`.

#### 2. Selected Campaign: `selected.maxCaloriesPerServing`
- **Location**: `public/marketing.js`, line 659
```javascript
// public/marketing.js:659
${selected.maxCaloriesPerServing ? `<span>≤ ${selected.maxCaloriesPerServing} kcal</span>` : ""}
```
- **Source**: Sourced from `/api/campaigns` or user edits in the Campaign Library form.
- **Defect**: When editing or generating a campaign in `marketing.js`, `/api/campaigns/update` accepts any arbitrary JSON update payload without schema validation. An unescaped `maxCaloriesPerServing` field renders straight into the DOM.

#### 3. Cookidoo Recipe Catalog: `r.calories_per_serving` & `r.minutes`
- **Location**: `public/app.js`, lines 1458 & 1460
```javascript
// public/app.js:1458-1460
<div class="meal-meta">
  <span>${r.minutes} min</span>
  <span>${formatEUR(r.estimated_cost)}</span>
  <span class="meal-calories">${r.calories_per_serving} kcal/ración</span>
</div>
```
- **Contrast**: In `renderExperiencePanel()` (line 926), `Math.round(meal.calories_per_serving)` is used, which forces a numeric type. However, in `renderSourcesView()` (line 1460), `${r.calories_per_serving}` is inserted raw. If the recipe catalog contains malformed or injected data, it triggers DOM injection.

#### 4. Meal Servings: `meal.cookidoo_servings`
- **Location**: `public/app.js`, line 930
```javascript
// public/app.js:930
<span>${meal.cookidoo_servings} ${meal.cookidoo_servings === 1 ? "ración" : "raciones"}</span>
```
- **Defect**: Inserted directly into the Cookidoo metadata card without `escapeHtml()` or numeric conversion.

#### 5. Basket Item Quantity: `item.quantity`
- **Location**: `public/app.js`, line 1013
```javascript
// public/app.js:1013
<span>
  ${item.quantity} × ${escapeHtml(item.unit)} (${formatEUR(item.unit_price)}/ud)
  ${item.used_in_days && item.used_in_days.length ? ` · Para: ${escapeHtml(item.used_in_days.join(", "))}` : ""}
</span>
```
- **Defect**: While `item.unit` and `item.used_in_days` are explicitly escaped, `${item.quantity}` is not. If the quantity is deserialized as a string payload from a modified cart response, it executes directly.

---

### 2.3 Inline Event Handlers Violating CSP Directives
In both `app.js` and `marketing.js`, `renderGoogleCloudLockup()` injects an inline `onerror` attribute:

```javascript
// public/app.js:680-684 & public/marketing.js:93-97
<img
  class="gcloud-logo-img"
  src="https://sites.google.com/u/0/sitesv-images-rt/AMxu72ubGyFeeA9phYacPQqAz0Bq475_Kn_Ew-K2e82TOf1XvvIgqx0SgKPxoxr76yQOZ3GjLwqgKYBCv-A8bD7jTlrwIOQ80rsyBj6sLAPUqNen1DEfVbwYXXHl1NGnv3DM4WgLo2J7Ictra80hTtgZ-YV7pus7pIzo0jdkio0hKt7Ptht4DduV_j3ePk7wavS1OjWhN59Ze9BsiiPKqzVpRwB6kFOyroijkcomHFDsON8=w1280"
  onerror="this.onerror=null;this.src='/brand/google-cloud.svg';"
  alt="Google Cloud"
/>
```

#### Implications:
1. **CSP Incompatibility**: Any modern, secure Content Security Policy that forbids `'unsafe-inline'` script execution will block this inline handler, causing broken images when network access to `sites.google.com` is restricted or offline.
2. **Fragility**: Statically packaging official SVG brand assets locally (e.g. `/brand/google-cloud.svg`) is standard practice, eliminating the remote HTTP dependency and inline script handler simultaneously.

---

## 3. URL Handling, Deep Links & Open Redirect Audit

### 3.1 Unvalidated Protocol Handlers on Dynamic Links
In multiple locations, links are dynamically constructed using strings retrieved from backend APIs or application state:

```javascript
// public/app.js:754
<a href="${escapeHtml(state.campaignLibraryUrl || "/marketing")}">Campaign Library</a>

// public/marketing.js:356, 362, 364
<a class="brand-lockup" href="${escapeHtml(mState.companionAppUrl)}" aria-label="Google Cloud y Mercadona">
<a href="${escapeHtml(mState.companionAppUrl)}">Experiencia Cliente (Planificador)</a>
<a href="${escapeHtml(mState.companionAppUrl)}/#for-you">Ver «Más ideas para tu semana» ↗</a>

// public/marketing.js:673
<a class="campaign-hero-button preview-cta" href="${escapeHtml(mState.companionAppUrl)}/?campaign=${encodeURIComponent(selected.id)}#for-you">
```

#### Mechanism:
- `escapeHtml()` converts `<`, `>`, `"`, and `&` to safe HTML entities.
- However, `escapeHtml()` does **NOT** sanitize URL schemes. If `state.campaignLibraryUrl` or `mState.companionAppUrl` contains `javascript:alert(document.domain)` or `data:text/html,...`, clicking these links results in immediate arbitrary script execution within the origin.
- Furthermore, if an attacker tampers with environment configurations or poisons API responses, users can be redirected to an external credential harvesting site.

---

### 3.2 Dynamic `window.open()` in Thermomix Handoff
In `public/app.js`:

```javascript
// public/app.js:516-519
async function sendToThermomix(recipeId, cookidooUrl, recipeName) {
  // Open the official Cookidoo recipe page in a new tab immediately on user click
  window.open(cookidooUrl, "_blank", "noopener,noreferrer");
  ...
}

// public/app.js:950-953
<button
  type="button"
  class="thermomix-send-btn ${isSent ? "sent" : ""}"
  data-thermomix-id="${escapeHtml(meal.recipe_id)}"
  data-thermomix-url="${escapeHtml(meal.cookidoo_url)}"
  data-thermomix-name="${escapeHtml(meal.name)}"
>
```

#### Analysis:
- `data-thermomix-url` is extracted on line 1661: `btn.getAttribute("data-thermomix-url")`.
- It is passed directly to `window.open(cookidooUrl, "_blank", "noopener,noreferrer")`.
- While `"noopener,noreferrer"` correctly protects the `window.opener` object from reverse tab-nabbing, `window.open()` performs no validation to ensure `cookidooUrl` begins with `https://cookidoo.es/` or `https://www.cookidoo.es/`.
- If an injected recipe record provides a malicious URL, users clicking "Envía a tu Thermomix" will be directed to an untrusted external site.

---

### 3.3 Query Parameter & Hash Routing Analysis

#### Query Parameter Parsing (`window.location.search`)
In `public/app.js`:
```javascript
// public/app.js:319-326
const params = new URLSearchParams(window.location.search);
const requestedId = params.get("campaign");
const activeList = getActiveCampaigns();
const target =
  (requestedId && state.campaigns.find((c) => c.id === requestedId)) ||
  activeList.find((c) => c.id === state.selectedCampaignId) ||
  activeList.find((c) => c.profileId === state.profileId) ||
  activeList[0];
```
- **Security Assessment**: **SAFE**. `requestedId` is purely used as a lookup key against the internally populated `state.campaigns` list. It is never reflected into the DOM, never evaluated with `eval()`, and cannot cause DOM XSS.

#### Fragment Routing (`window.location.hash`)
- **Observation**: The navigation bar uses hash anchors (`#for-you`, `#planner`, `#catalog`, `#sources`). Tab switching is bound to `click` event listeners on `[data-tab]`.
- **Defect**: On initial page load, `window.location.hash` is completely ignored. If a user visits `https://<host>/#catalog`, the application initializes in the `"planner"` state, creating a state mismatch between the browser address bar and the active UI.

---

## 4. Google OAuth & Identity-Aware Proxy (IAP) Integration Audit

### 4.1 Phantom Dependency: Unused GSI Client Library
In `public/index.html`:
```html
<!-- public/index.html:22 -->
<script src="https://accounts.google.com/gsi/client" async defer></script>
```

#### Detailed Findings:
1. **Zero Invocation in Code**: A comprehensive search across `public/app.js` and `public/marketing.js` revealed zero occurrences of `google.accounts.id.initialize`, `google.accounts.id.renderButton`, or `google.accounts.id.prompt`.
2. **Missing Subresource Integrity (SRI)**: The script tag does not specify an `integrity` hash or `crossorigin="anonymous"`.
3. **Missing from Marketing App**: `public/marketing.html` does not include this script tag at all, demonstrating architectural inconsistency between the companion app and the marketing portal.
4. **Supply Chain Surface**: Loading an unused third-party JavaScript bundle from `accounts.google.com` consumes network bandwidth and broadens the attack surface for zero functional benefit.

---

### 4.2 Authentication Flow Mismatch & Broken Re-Login
Both `app.js` (lines 689–735) and `marketing.js` (lines 102–148) render an authentication gate when `state.auth.authenticated === false`:

```html
<!-- public/app.js:721-727 -->
<a
  href="/_gcp_iap/clear_login_cookie"
  class="primary-button"
  style="width: 100%; justify-content: center; text-decoration: none; margin-top: 8px;"
>
  Iniciar sesión con cuenta de Google (IAP)
</a>
```

#### Defect Analysis:
1. **Infrastructure Coupling**: `/_gcp_iap/clear_login_cookie` is an internal endpoint managed exclusively by Google Cloud Identity-Aware Proxy at the HTTPS Load Balancer layer.
2. **Local Development Failure**: When running the application locally via `server.py` (e.g. `http://localhost:8080`), clicking this button requests `http://localhost:8080/_gcp_iap/clear_login_cookie`, which returns `404 Endpoint no encontrado`.
3. **Dead Backend Endpoint**: `server.py` implements a complete `/api/auth/login` endpoint (lines 314–364) capable of verifying Google Identity JWT tokens (`verify_google_id_token()`) and issuing signed HMAC session cookies (`mercadona_session`). However, because the frontend GSI button was never implemented, this endpoint is completely unreachable from the UI.

---

### 4.3 Session Expiration & Lifecycle UX
1. **Window Focus Incomplete**: Line 1818 in `app.js` listens to `window.focus`:
   ```javascript
   window.addEventListener("focus", () => {
     fetchCampaignsFromLibrary();
   });
   ```
   It refreshes campaigns, but **never checks session validity** via `checkSession()`. If the user's IAP login or cookie expired while the tab was backgrounded, the user is unaware until an API call fails.
2. **Missing 401/403 Error Interceptor**: When an API call like `/api/plan` or `/api/mercadona/cart` returns 401 or 403, the application merely displays a generic toast or updates `state.error`:
   ```javascript
   // public/app.js:450
   state.error = data.error || "No se pudo generar el menú semanal.";
   ```
   It fails to reset `state.auth.authenticated = false`, leaving the user trapped in an error state without presenting the re-authentication modal.

---

## 5. Third-Party Credential Handling: Mercadona & Cookidoo

### 5.1 Ingestion of Raw Mercadona Developer Auth Tokens
The application provides a feature allowing users to sync meal plans directly with their live cart on `tienda.mercadona.es`.

```html
<!-- public/app.js:1076-1086 -->
<ol style="font-size:12px; color:var(--muted); margin: 0 0 12px 18px; padding:0; line-height:1.55;">
  <li>Inicia sesión en tienda.mercadona.es en tu navegador.</li>
  <li>Abre las herramientas de desarrollador (F12 → pestaña Network), haz clic derecho sobre cualquier petición a /api/ y elige Copy → Copy as cURL (o pega directamente tu Bearer token JWT / refresh_token).</li>
  <li>Pégalo aquí abajo...</li>
</ol>
<textarea
  id="mercadona-auth-input"
  rows="3"
  placeholder="Pega aquí el comando 'Copy as cURL' de tienda.mercadona.es..."
>${escapeHtml(state.mercadonaAuthInput)}</textarea>
```

#### Security Risks:
1. **Over-Privileged Credential Ingestion**: A full `curl` command contains not only Mercadona API authorization headers, but also browser session cookies, device identifiers, anti-CSRF tokens, and user metadata.
2. **Token Lifetime**: Mercadona JWTs typically remain valid for **up to 6 weeks**, and refresh tokens have indefinite or multi-month lifespans.
3. **Client-Side Heap Retention**: The raw string is preserved in JavaScript memory (`state.mercadonaAuthInput`). If any malicious script, rogue third-party dependency, or browser extension executes in the page context, it can inspect the `state` object or query `#mercadona-auth-input` to exfiltrate the user's live Mercadona account token.
4. **Social Engineering Surface**: Instructing everyday retail users to open browser Developer Tools and execute "Copy as cURL" bypasses all standard browser security boundaries and habituates users to dangerous self-XSS / paste-jacking practices.

---

### 5.2 Cookidoo Credentials in Client-Side Memory
Lines 871–885 in `public/app.js` allow configuring Cookidoo account credentials:

```html
<!-- public/app.js:880-881 -->
<input type="email" id="cookidoo-email-input" placeholder="Email de Cookidoo" value="${escapeHtml(state.cookidooEmail)}" ... />
<input type="password" id="cookidoo-pass-input" placeholder="Contraseña de Cookidoo" value="${escapeHtml(state.cookidooPassword)}" ... />
```

```javascript
// public/app.js:520-527
const res = await fetch("/api/cookidoo/send", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    recipe_id: recipeId,
    cookidoo_email: state.cookidooEmail,
    cookidoo_password: state.cookidooPassword,
  }),
});
```

#### Security Risks:
1. **Plaintext Password in JavaScript Memory**: `state.cookidooPassword` retains the user's master Cookidoo password in plaintext within heap memory throughout the session.
2. **Transmission Vulnerability**: Every invocation of "Envía a tu Thermomix" re-transmits the plaintext password in a JSON request body.
3. **Recommended Pattern**: Passwords should never reside in frontend client state. The user should authenticate against an isolated backend session endpoint that exchanges credentials for a scoped, ephemeral session token or cookie.

---

## 6. Content Security Policy (CSP), SRI & Iframe Sandboxing

### 6.1 Content Security Policy (CSP) Assessment
- **Status**: **MISSING (CRITICAL DEFECT)**.
- Neither `public/index.html` nor `public/marketing.html` defines a `<meta http-equiv="Content-Security-Policy">` element.
- `server.py` does not issue a `Content-Security-Policy` HTTP response header.

#### Consequence:
Without CSP:
- The browser will load and execute scripts from **any** origin.
- The browser will send fetch/XHR requests to **any** external domain, enabling data exfiltration.
- Web workers, iframes, inline styles, and eval scripts operate without browser-enforced constraints.

---

### 6.2 Framing & Clickjacking Defense Assessment
- **Status**: **MISSING (HIGH DEFECT)**.
- `server.py` does **NOT** emit `X-Frame-Options: DENY` or `X-Frame-Options: SAMEORIGIN`.
- There is no CSP `frame-ancestors 'none'` directive.

#### Attack Scenario (Clickjacking Cart Manipulation):
1. An attacker sets up `https://evil-attacker.com/free-thermomix`.
2. The page loads `https://mercadona-ai-companion-...run.app` inside a transparent `<iframe>` styled with `opacity: 0.001` positioned over a decoy "Claim Free Thermomix" button.
3. An authenticated user clicking the decoy button inadvertently clicks `#oneclick-mercadona-cart-btn` ("Añadir al carrito de Mercadona (1-Click)"), executing an unwanted high-value transaction in their Mercadona account.

---

### 6.3 Cross-Origin Resource Sharing (CORS) Audit
In `server.py`:
```python
# server.py:159-163
def _add_cors_headers(self) -> None:
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
```
- **Defect**: `Access-Control-Allow-Origin: *` is unconditionally sent on **every response**, including `/api/auth/session`, `/api/mercadona/session`, `/api/plan`, and static files.
- While browsers restrict credentialed requests (`withCredentials: true`) when `Access-Control-Allow-Origin: *` is present, uncredentialed data or endpoints accepting Bearer tokens via `Authorization` header can be queried cross-origin by any third-party website.
- CORS should be restricted specifically to authorized domains:
  - `https://mercadona-ai-companion-905208270932.europe-west1.run.app`
  - `https://campaign-library-905208270932.europe-west1.run.app`
  - Authorized custom domains and localhost for local testing.

---

### 6.4 Additional Missing HTTP Security Headers
Inspection of `_send_json()` and static file handlers in `server.py` confirms the absence of:
1. `X-Content-Type-Options: nosniff` (leaves the application vulnerable to MIME-sniffing attacks).
2. `Referrer-Policy: strict-origin-when-cross-origin` (may leak full URLs including query parameters to external sites).
3. `Permissions-Policy: camera=(), microphone=(), geolocation=()` (fails to disable unneeded browser APIs).
4. `Strict-Transport-Security: max-age=31536000; includeSubDomains` (HSTS).

---

## 7. Concrete Remediation Plan & Hardened Implementation

To achieve full compliance with Google Cloud Security and OWASP standards, the following mitigations are provided as concrete, drop-in engineering solutions.

### 7.1 Hardened `escapeHtml()` Implementation
Replace the existing four-character replacement with an industry-standard entity encoder that escapes single quotes, backticks, and forward slashes:

```javascript
/**
 * Hardened HTML Entity Encoder conforming to OWASP XSS Prevention Cheat Sheet.
 * Safely encodes &, <, >, ", ', `, and / to prevent attribute and tag breakout.
 */
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/`/g, "&#96;")
    .replace(/\//g, "&#x2F;");
}
```

---

### 7.2 Strict URL Sanitizer for Links & `window.open()`
Add a strict URL validation helper to ensure that any URL passed to an `href` or `window.open()` is strictly limited to safe `https:` or relative paths, and matches an allowed domain whitelist:

```javascript
/**
 * Validates and sanitizes URLs to prevent 'javascript:' pseudo-protocols
 * and open redirect vulnerabilities.
 * @param {string} url - Candidate URL
 * @param {string[]} allowedPrefixes - List of approved domain or path prefixes
 * @returns {string} Safe sanitized URL or '#' fallback
 */
function sanitizeUrl(url, allowedPrefixes = []) {
  if (!url || typeof url !== "string") return "#";
  const trimmed = url.trim();

  // Allow relative URLs starting with / (excluding protocol-relative //)
  if (trimmed.startsWith("/") && !trimmed.startsWith("//")) {
    return escapeHtml(trimmed);
  }

  try {
    const parsed = new URL(trimmed, window.location.origin);
    if (parsed.protocol !== "https:") {
      console.warn("Blocked non-HTTPS URL scheme:", parsed.protocol);
      return "#";
    }

    if (allowedPrefixes.length > 0) {
      const isAllowed = allowedPrefixes.some(
        (prefix) => trimmed.startsWith(prefix) || parsed.origin === prefix
      );
      if (!isAllowed) {
        console.warn("Blocked untrusted external origin:", parsed.origin);
        return "#";
      }
    }

    return escapeHtml(trimmed);
  } catch (e) {
    return "#";
  }
}
```

#### Application in `sendToThermomix`:
```javascript
async function sendToThermomix(recipeId, cookidooUrl, recipeName) {
  const safeCookidooUrl = sanitizeUrl(cookidooUrl, [
    "https://cookidoo.es",
    "https://www.cookidoo.es",
  ]);
  if (safeCookidooUrl !== "#") {
    window.open(safeCookidooUrl, "_blank", "noopener,noreferrer");
  }
  ...
}
```

---

### 7.3 Production Content Security Policy (CSP) & HTTP Headers
Update `server.py` to inject comprehensive security headers on every response (both API JSON and static assets).

```python
# Recommended server.py header hardening
SECURITY_HEADERS = {
    # 1. Content Security Policy: Restricts scripts, styles, images, and fonts to trusted origins.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://prod-w-cookidoo.vorwerk-digital.com https://prod-eu-central-1-vorwerk-digital.s3.eu-central-1.amazonaws.com https://prod-eu-central-1-vorwerk-digital.s3.amazonaws.com https://prod-diet-assets.mercadona.es https://prod-mercadona.imgix.net; "
        "connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none';"
    ),
    # 2. Prevent clickjacking / framing
    "X-Frame-Options": "DENY",
    # 3. Prevent MIME-sniffing
    "X-Content-Type-Options": "nosniff",
    # 4. Strict referrer policy
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # 5. Disable unneeded browser APIs
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    # 6. HTTP Strict Transport Security
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
}

def _add_security_headers(self) -> None:
    for header, value in SECURITY_HEADERS.items():
        self.send_header(header, value)
```

---

### 7.4 Removal of Dead GSI Script & Addition of SRI
1. In `public/index.html`, remove the unused Google GSI client script:
   ```html
   <!-- REMOVE LINE 22 -->
   <!-- <script src="https://accounts.google.com/gsi/client" async defer></script> -->
   ```
2. If Google Sign-In is later re-introduced for non-IAP local environments, specify the official SRI hash and initialize it properly via JavaScript.

---

### 7.5 Secure Session-Brokered Mercadona & Cookidoo Storage
Instead of storing plaintext credentials in the client DOM:
1. **Backend Session Storage**: When the user links their Mercadona or Cookidoo credentials, the backend validates and stores the encrypted tokens in the user's server-side session.
2. **Zero Plaintext in DOM**: The frontend only receives:
   ```json
   {
     "connected": true,
     "customer_id": "123456",
     "masked_token": "eyJhbGciOi…89ABCD"
   }
   ```
3. Input textareas and password fields must immediately clear (`state.mercadonaAuthInput = ""`, `state.cookidooPassword = ""`) upon submission.

---

## 8. Verification & Audit Testing Checklist

Before deploying frontend revisions, execute the following security verification tests:

| Test Case | Description | Expected Result | Command / Method |
| :--- | :--- | :--- | :--- |
| **TC-01** | Attribute Breakout via Single Quote | `escapeHtml("foo' onclick='alert(1)")` must encode single quote as `&#39;` | Unit test in `tests/test_xss_sanitization.js` |
| **TC-02** | Gemini Prompt Injection Rendering | Send plan containing `<script>alert(1)</script>` in `maxCaloriesPerServing` | Value is escaped as `&lt;script&gt;` in DOM; script does not execute |
| **TC-03** | Clickjacking / Iframe Test | Attempt embedding `http://localhost:8080` in an `<iframe>` | Browser blocks framing due to `X-Frame-Options: DENY` |
| **TC-04** | CSP Header Verification | Inspect `curl -I http://localhost:8080/` | `Content-Security-Policy` header is present and valid |
| **TC-05** | `javascript:` URL Blocking in `window.open` | Pass `javascript:alert(1)` to `sendToThermomix()` | URL is blocked by `sanitizeUrl()`; window does not open |
| **TC-06** | CORS Header Isolation | Send request with `Origin: https://malicious-site.com` | Server rejects or does not reflect wildcard origin for sensitive endpoints |
| **TC-07** | Stale Session 401 Interception | Mock 401 on `/api/plan` | UI resets `state.auth.authenticated = false` and displays re-auth modal |

---

## Conclusion
The frontend applications for Mercadona AI Shopping Companion and Campaign Library exhibit strong baseline architectural design, structured component rendering, and proactive client-side prompt validation. Implementing the defense-in-depth mitigations detailed in this report—specifically a strict Content Security Policy, comprehensive HTML entity encoding, origin-restricted URL handling, Clickjacking prevention headers, and credential isolation—will bring the platform into full alignment with Google Cloud production security standards.
