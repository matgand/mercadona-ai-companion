# Frontend Performance & Core Web Vitals (CWV) Audit
## Mercadona AI Shopping Companion & Campaign Library Microservices

**Audit Date:** September 2026  
**Auditor:** Child Subagent 5 (Frontend Performance & Core Web Vitals Specialist)  
**Target Applications:** 
- `mercadona-ai-companion` (Customer Meal Planner: `SERVICE_ROLE=companion`, URL: `https://mercadona-ai-companion-905208270932.europe-west1.run.app`)
- `campaign-library` (Marketing Workspace: `SERVICE_ROLE=campaign-library`, URL: `https://campaign-library-905208270932.europe-west1.run.app`)
**Repository:** `/usr/local/google/home/mgandolfi/mercadona-ai-companion`  
**Target Environment:** Google Cloud Run (Fully Managed, Europe-West1, IAP-Gated)

---

## Executive Summary & Performance Scorecard

This audit evaluates the frontend performance architecture, runtime rendering mechanisms, network payload efficiency, asset delivery pipeline, and Core Web Vitals (CWV) profile across both microservice user interfaces (`/public/index.html` and `/public/marketing.html`).

While the user interface provides a visually refined, high-touch experience connecting Gemini 3.8 Flash, Cookidoo, and the Mercadona catalog, several structural performance bottlenecks severely compromise mobile and desktop Core Web Vitals—specifically **Largest Contentful Paint (LCP)**, **Interaction to Next Paint (INP)**, and **Cumulative Layout Shift (CLS)**.

### Synthetic Core Web Vitals Estimate

| Metric | Target (Good) | Current Estimated (Desktop) | Current Estimated (Mobile 4G) | Health Status | Primary Bottleneck |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **LCP** (Largest Contentful Paint) | $\le 2.5\text{ s}$ | **$2.8\text{ s} - 3.4\text{ s}$** | **$5.2\text{ s} - 7.8\text{ s}$** | 🔴 **POOR** | Render-blocking CSS (70 KB), remote Google Cloud logo external hops, massive unoptimized hero WebP images (1.6K px display vs 118-600 px slot), `Cache-Control: no-store` on static files. |
| **INP** (Interaction to Next Paint) | $\le 200\text{ ms}$ | **$120\text{ ms} - 280\text{ ms}$** | **$350\text{ ms} - 680\text{ ms}$** | 🟡 / 🔴 **NEEDS WORK** | Monolithic `root.innerHTML` teardown/rebuild on every state change; un-debounced regex execution on textarea `input`; full DOM garbage collection cycles. |
| **CLS** (Cumulative Layout Shift) | $\le 0.1$ | **$0.22 - 0.38$** | **$0.28 - 0.45$** | 🔴 **POOR** | Images rendered without explicit `width` and `height` attributes; dynamic injection of auth modal, lockup logos, and catalog cards after initial HTML render. |
| **FCP** (First Contentful Paint) | $\le 1.8\text{ s}$ | **$1.6\text{ s} - 2.1\text{ s}$** | **$3.2\text{ s} - 4.6\text{ s}$** | 🟡 **NEEDS WORK** | Synchronous font stylesheet (`fonts.googleapis.com`) + uncompressed render-blocking `styles.css`. |
| **TTFB** (Time to First Byte) | $\le 800\text{ ms}$ | **$150\text{ ms} - 320\text{ ms}$** | **$450\text{ ms} - 850\text{ ms}$** | 🟢 **GOOD** | Cloud Run HTTP dispatch is fast, but static asset roundtrips lack edge caching and compression. |

---

## 1. Asset Analysis (`/public/`)

The total payload footprint of static files residing in `/usr/local/google/home/mgandolfi/mercadona-ai-companion/public/` is **1,168.36 KB (1.17 MB)** across 14 files.

```
/usr/local/google/home/mgandolfi/mercadona-ai-companion/public/
├── app.js                              (73.63 KB uncompressed | 18.93 KB gzip)
├── marketing.js                        (31.77 KB uncompressed |  8.29 KB gzip)
├── styles.css                          (69.96 KB uncompressed | 14.25 KB gzip)
├── index.html                          ( 1.42 KB uncompressed |  0.64 KB gzip)
├── marketing.html                      ( 1.46 KB uncompressed |  0.66 KB gzip)
├── favicon.ico                         (14.73 KB)
├── favicon.png                         ( 1.73 KB)
├── brand/
│   ├── google-cloud.svg                ( 4.20 KB)
│   └── mercadona.svg                   ( 7.49 KB)
└── meals/
    ├── birthday-cake.webp              (125.30 KB | 1599x1600 px)
    ├── chickpea-spinach-tomato-rice.webp (205.01 KB | 1536x1024 px)
    ├── christmas-roast-turkey.webp     (178.60 KB | 1600x1600 px)
    ├── lemon-hake-potatoes.webp        (174.17 KB | 1536x1024 px)
    ├── pasta-chickpea-salad.webp       ( 87.84 KB | 1600x1600 px)
    └── quick-broccoli-salad.webp       (191.05 KB | 1600x1596 px)
```

### 1.1 Fonts Delivery Architecture
- **Implementation:** Both `index.html` (L12-14) and `marketing.html` (L12-14) import:
  ```html
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;600;700&family=Geist:wght@300;400;500;600;700;800&display=swap" rel="stylesheet" />
  ```
- **Performance Findings:**
  1. **Render-Blocking Webfont CSS:** The `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?...">` is synchronous and parser-blocking. The browser cannot render text until the CSS definition is fetched, resolved, and parsed.
  2. **Double DNS/TLS Roundtrip:** Even with `preconnect`, connecting to `fonts.googleapis.com` (for the CSS) and then to `fonts.gstatic.com` (for the `.woff2` font files) introduces 2 DNS lookups, 2 TLS handshakes, and 2 roundtrip negotiations before font bytes arrive.
  3. **FOUT / FOIT Flash:** With `display=swap`, text first renders in fallback system fonts (`-apple-system, BlinkMacSystemFont, sans-serif`), and once the Geist binary arrives, the entire page reflows, causing layout shifts.
  4. **Self-Hosting Opportunity:** Geist and Geist Mono are open-source fonts. Self-hosting them directly from `/public/fonts/` with immutable `Cache-Control` headers eliminates 100% of third-party DNS/TLS handshakes and protects user privacy from third-party IP leakage.

### 1.2 Image Assets (`/brand/`, `/meals/`, `favicons`)
- **Dimension vs. Display Mismatch (Critical Waste):**
  - The 6 meal hero images are stored at massive source dimensions: **$1536 \times 1024\text{ px}$ to $1600 \times 1600\text{ px}$**, with file sizes ranging between **87.84 KB and 205.01 KB** (total: 962 KB).
  - However, in `app.js` and `styles.css`:
    - In `.discovery-campaign-card img`, the display box is fixed to **$118 \times 136\text{ px}$** (retina 2x is only $236 \times 272\text{ px}$). The browser downloads an image 40 times larger than the rendering container.
    - In `.featured-campaign-card img`, the desktop container is at most $650 \times 590\text{ px}$.
    - In `.meal-image img` (recipe cards in the meal grid), the display container is approximately $400 \times 266\text{ px}$.
- **Absence of Responsive `srcset` & `sizes`:**
  - Zero images utilize `srcset` or `<picture>`. Both mobile clients on 375px screens and desktop clients download the full 1600px desktop asset.
- **Lazy Loading Implementation Gaps:**
  - In `app.js` (L914, L1004, L1371, L1448), `loading="lazy"` is correctly added to recipe card images and catalog thumbnails.
  - However, in `app.js` (L1211, L1247) and `marketing.js` (L646), campaign discovery cards omit `loading="lazy"`.
  - Conversely, the LCP candidate (`featuredCampaign.imageUrl` at L1211) should have `fetchpriority="high"` rather than lazy loading, to guarantee immediate network prioritization.
- **Missing Explicit Width & Height Attributes:**
  - Neither `app.js` nor `marketing.js` assigns `width` and `height` attributes to `<img>` tags. As images stream in over the network, aspect ratios cannot be reserved by the browser's layout engine before image headers load, driving substantial Cumulative Layout Shift (CLS).
- **Remote Fallback Anti-Pattern in `renderGoogleCloudLockup()`:**
  - Lines 680–682 of `app.js` load an external 1280px Google Sites raster image:
    ```javascript
    src="https://sites.google.com/u/0/sitesv-images-rt/AMxu72ubGyFeeA9phYacPQqAz0Bq475_...=w1280"
    onerror="this.onerror=null;this.src='/brand/google-cloud.svg';"
    ```
  - **Severe Overhead:** This forces an external HTTP request to `sites.google.com`. If blocked, delayed, or corporate-firewalled, it stalls until timeout before falling back via `onerror` to the local `/brand/google-cloud.svg` (which is only 4.2 KB!).
  - **Remediation:** Remove the external Google Sites URL completely; load the local vector SVG directly with zero external latency.

### 1.3 Script Loading Performance
- **Implementation in `index.html`:**
  ```html
  <script src="https://accounts.google.com/gsi/client" async defer></script>
  ...
  <body class="antialiased">
    <div id="app-root"></div>
    <script src="/app.js?v=iap-2026-v3"></script>
  </body>
  ```
- **Performance Findings:**
  1. `app.js` (73.6 KB) is placed at the bottom of the body without `defer` or `module`. Placing scripts at the end of `<body>` delays script fetching until after the HTML parser reaches the bottom. 
  2. With `<script defer src="/app.js">` in `<head>`, script fetching begins in parallel with HTML parsing while maintaining execution order.
  3. `https://accounts.google.com/gsi/client` correctly specifies `async defer`, avoiding parser blocking.
  4. Script sizes are unminified: `app.js` contains 1,821 lines of readable code (73.6 KB), compressible to ~18.9 KB via gzip, but served raw without compression (see Section 3).

### 1.4 CSS Loading & Tailwind Architecture
- **Implementation:** `<link rel="stylesheet" href="/styles.css?v=iap-2026-v3" />` in `<head>`.
- **Performance Findings:**
  1. `styles.css` is **69.96 KB** (14.25 KB gzip). It contains the entire unpurged Tailwind v4 runtime engine and reset layers (Line 2 is 61,763 characters long).
  2. **Unused CSS Deadweight:** Static analysis of `styles.css` reveals 379 class rules, but only 180 classes are actually referenced in HTML/JS templates (52.5% of declared utility classes are completely unused in the runtime).
  3. **Critical Path Blocking:** The stylesheet is render-blocking. FCP cannot occur until `styles.css` is completely transferred and computed into CSSOM.
  4. **Critical CSS Extraction:** The above-the-fold layout styles (brand bar, hero skeleton, empty state container) total less than 4 KB and can be inlined directly in `<style>` inside `<head>`.

---

## 2. Client-Side Rendering Architecture (`app.js` & `marketing.js`)

Both microservices utilize an imperative, zero-dependency vanilla JavaScript rendering architecture based on an event-driven model.

```mermaid
flowchart TD
    StateChange[User Action / API Response / State Mutation] --> CallRender[Execute monolithic render]
    CallRender --> StringConcat[Construct 1,500+ lines of HTML string template]
    StringConcat --> InnerHTML[Assign root.innerHTML = fullHTML]
    InnerHTML --> DOMDestruction[Destroy existing DOM Subtree & Nodes]
    DOMDestruction --> DOMRebuild[Browser parses HTML & builds brand new DOM]
    DOMRebuild --> CSSOMRecalc[Full CSSOM Re-calculation & Layout Reflow]
    DOMRebuild --> BindEvents[Execute bindEvents - querySelectorAll & addEventListener]
    DOMRebuild --> ImageReeval[Re-evaluate image resources & scroll positions]
```

### 2.1 The Monolithic String Replacement Anti-Pattern (`root.innerHTML = ...`)
- **Mechanism:** In `app.js` (L1496–1525):
  ```javascript
  function render() {
    const root = document.getElementById("app-root");
    if (!root) return;
    root.innerHTML = `
      ${renderAuthModal()}
      <main class="app-shell">
        ${renderHeader()}
        ${state.activeTab === "catalog" ? renderCatalogView() : ...}
      </main>
      ${state.toast ? ... : ""}
    `;
    bindEvents();
  }
  ```
- **Consequences for Runtime Performance:**
  1. **Complete DOM Subtree Destruction:** Every time `render()` runs (tab switches, campaign selections, prompt updates, cart syncing, toast popups), the entire DOM tree inside `#app-root` (often hundreds of DOM nodes) is destroyed and re-parsed.
  2. **Layout Thrashing & Recalculation:** The browser must discard all computed styles, re-calculate layout geometries for the entire tree, and re-paint the window.
  3. **Focus Invalidation & Input Loss:** If a re-render is triggered while an input has focus, focus is stripped, text selection is cleared, and cursor position is reset unless manually restored.
  4. **Image Flashing:** When `root.innerHTML` is replaced, existing `HTMLImageElement` nodes are destroyed. Even if cached in memory by the browser, layout boxes collapse to $0\times0$ and expand again when new image elements are bound, inducing visual flicker and CLS.

### 2.2 Event Listener Leaks & Lifecycle Management
- **Audit of Event Binding:**
  - `bindEvents()` runs immediately after `root.innerHTML = ...`. Because `root.innerHTML` completely replaces the DOM nodes, event listeners registered on old nodes are detached and garbage collected along with the discarded nodes.
  - However, this introduces substantial **Garbage Collection (GC) Pressure**:
    - Each call to `bindEvents()` allocates dozens of closures (`logoutBtn`, `data-tab` nodes, `data-campaign-id` nodes, `data-swap-recipe` buttons, `data-recipe-idx` buttons, `data-rescue-action` buttons).
    - In long sessions where users explore recipes, swap meals, or search the catalog, frequent GC pauses cause frame drops (jank) during smooth scrolling and animations.
  - **Event Delegation Solution:** Rather than querying and binding listeners to dozens of individual card elements after every render, a single delegated listener attached to `#app-root` using `e.target.closest('[data-action]')` eliminates repetitive event attachment and reduces memory allocation.

### 2.3 Input Responsiveness & Typing Latency in Prompt Textarea
- In `app.js` (L1604–1623):
  ```javascript
  promptArea.addEventListener("input", (e) => {
    state.prompt = e.target.value;
    state.detectedPills = detectPillsClientSide(state.prompt);
    const pillRow = document.getElementById("constraint-pills-row");
    if (pillRow) {
      pillRow.innerHTML = state.detectedPills.map((p) => `<span>${escapeHtml(p)}</span>`).join("");
    }
    const check = validateMealPlanningPrompt(state.prompt);
    const guardBanner = document.getElementById("scope-guard-banner");
    if (guardBanner) {
      guardBanner.style.display = check.valid ? "none" : "block";
    }
    const submitBtn = document.getElementById("planner-submit-btn");
    if (submitBtn) {
      submitBtn.disabled = state.loading || !check.valid;
    }
  });
  ```
- **Performance Findings:**
  1. **Targeted DOM Mutation (Positive):** Notice that on `promptArea.input`, `render()` is intentionally bypassed, and only `#constraint-pills-row`, `#scope-guard-banner`, and `#planner-submit-btn` are updated directly! This is an excellent micro-optimization that preserves keystroke smoothness.
  2. **Heavy Regex Computation on Keystrokes:** However, on **every single keystroke**:
     - `detectPillsClientSide()` runs 8 complex regular expressions, string parsing, and allergy label checks.
     - `validateMealPlanningPrompt()` runs `OFF_TOPIC_REGEX` (a massive regex checking 50+ keywords) and `MEAL_PLANNING_DOMAIN_REGEX` (an even larger regex checking 100+ ingredient and dietary terms).
     - On low-end mobile devices, executing these multiple multi-branch regexes synchronously on each keystroke blocks the Main Thread for 15–40 ms per character, degrading **INP**.
  3. **Debouncing Recommendation:** The text validation and pill extraction should be debounced with a $150\text{ ms}$ trailing timer, updating UI state only when typing pauses.

---

## 3. Network, Headers & Caching Architecture (`server.py`)

A critical bottleneck identified in the audit lies in the static file serving configuration within `server.py`.

### 3.1 Static File Serving Headers in `server.py`
In `server.py` (L301–307):
```python
ctype, _ = mimetypes.guess_type(str(file_path))
...
data = file_path.read_bytes()
self.send_response(200)
self.send_header("Content-Type", ctype or "application/octet-stream")
self.send_header("Content-Length", str(len(data)))
self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
self._add_cors_headers()
self.end_headers()
self.wfile.write(data)
```

#### Critical Bottlenecks:
1. **Aggressive Disabling of Browser Caching (`no-store, no-cache, must-revalidate, max-age=0`):**
   - Every single asset—including `styles.css` (70 KB), `app.js` (74 KB), `mercadona.svg` (7.5 KB), and all 6 WebP meal images (~962 KB)—is served with `Cache-Control: no-store`.
   - **Impact:** The browser is strictly prohibited from storing any asset in the disk or memory cache. When a user navigates between `/` and `/marketing`, reloads the page, or opens a new tab, **1.17 MB of assets must be re-downloaded over the network every time**.
   - Because the query strings are already versioned in HTML (e.g. `styles.css?v=iap-2026-v3`, `app.js?v=iap-2026-v3`, `favicon.png?v=mercadona-basket-2026`), static assets should be served with immutable long-term caching:
     ```http
     Cache-Control: public, max-age=31536000, immutable
     ```
2. **Absence of `ETag` and `Last-Modified` Headers:**
   - No conditional HTTP validation (`304 Not Modified`) is supported. Even if `Cache-Control: no-cache` were used, without `ETag` or `If-None-Match`, full 200 responses with whole file bodies are always returned.
3. **Complete Absence of HTTP Compression (Gzip / Brotli):**
   - `server.py` relies on standard `http.server.BaseHTTPRequestHandler` and outputs raw uncompressed bytes (`self.wfile.write(data)`).
   - Neither gzip nor brotli compression is negotiated, regardless of `Accept-Encoding: gzip, deflate, br`.
   - **Transfer Size Comparison:**

| Asset | Raw Size | Gzip Size | Brotli Size (est.) | Wasteful Overhead |
| :--- | :--- | :--- | :--- | :--- |
| `app.js` | 73.63 KB | **18.93 KB** | **15.40 KB** | **+290% wire payload** |
| `marketing.js` | 31.77 KB | **8.29 KB** | **6.90 KB** | **+283% wire payload** |
| `styles.css` | 69.96 KB | **14.25 KB** | **11.20 KB** | **+391% wire payload** |
| `index.html` | 1.42 KB | **0.64 KB** | **0.55 KB** | **+122% wire payload** |
| `mercadona.svg` | 7.49 KB | **2.61 KB** | **2.15 KB** | **+187% wire payload** |
| **Total Core Code Assets** | **184.27 KB** | **44.72 KB** | **36.20 KB** | **+312% wire payload** |

### 3.2 Dynamic API Payload Sizing
An empirical measurement of the dynamic JSON endpoints was conducted:

| Endpoint | Content | Raw JSON Size | Gzip Size | Latency Impact |
| :--- | :--- | :--- | :--- | :--- |
| `/api/catalog?postal_code=28016` | 1,595 products + 5,000 Cookidoo recipes | **6,022.00 KB (5.88 MB)** | **961.40 KB** | **Severe:** Over 6 MB uncompressed JSON transferred when user clicks "Catálogo" or "Fuentes". Freezes mobile browser during JSON parsing! |
| `/api/campaigns` | 7 marketing campaigns | **6.20 KB** | **2.10 KB** | Minimal, highly efficient. |
| `/api/auth/session` | User session & IAP status | **0.65 KB** | **0.32 KB** | Fast and lightweight. |
| `/api/plan` (POST) | Weekly plan with 5 recipes & cart | **8.40 KB** | **2.60 KB** | Highly responsive. |

#### Critical Finding on `/api/catalog`:
- When clicking "Catálogo y Fuentes de Datos" (`loadCatalogTab()`), the client requests `/api/catalog`, which serializes the entire 5,000-recipe Cookidoo database (5.3 MB) and all 1,595 Mercadona products (747 KB) in one monolithic response.
- At 6 MB of raw text, `JSON.parse()` on a mobile device consumes 150–350 ms of CPU execution time, generating noticeable freezing and memory spikes.
- **Optimization:** Implement server-side pagination (`/api/catalog?page=1&limit=24&category=...`) and projection (return only IDs, names, prices, and thumbnails, omitting recipe instruction text until a recipe modal is opened).

---

## 4. Core Web Vitals (CWV) Detailed Diagnostic

```mermaid
gantt
    title Desktop Loading & Rendering Timeline (Current vs Optimized)
    dateFormat X
    axisFormat %s ms

    section Current (Cold)
    HTML Document Request           :0, 180
    styles.css Download (70KB raw)  :180, 480
    Google Fonts CSS Download       :180, 520
    app.js Download (74KB raw)      :480, 820
    Remote Cloud Logo Network Hop   :820, 1600
    LCP Meal Image Download (175KB) :820, 2400
    Parse & Execute app.js          :1600, 1850
    First Contentful Paint (FCP)    :milestone, 1850, 0
    Largest Contentful Paint (LCP)  :milestone, 2400, 0

    section Optimized (Target)
    HTML Document (with Critical CSS):0, 120
    First Contentful Paint (FCP)    :milestone, 130, 0
    app.js (gzip 18KB defer)        :120, 320
    Local SVG Cloud Logo (0ms hop)  :130, 140
    Hero Image (resized 38KB WebP)  :130, 580
    Largest Contentful Paint (LCP)  :milestone, 580, 0
```

### 4.1 Largest Contentful Paint (LCP)
- **Current Performance:** ~2.8s (Desktop) / ~5.2s (Mobile 4G).
- **LCP Element Identified:**
  - On the main planner page (`/`): The hero meal image inside the featured campaign card (`.featured-campaign-card img`, e.g. `/meals/lemon-hake-potatoes.webp` or `/meals/christmas-roast-turkey.webp`).
  - On the marketing portal (`/marketing`): The hero banner background inside `.marketing-hero`.
- **Causes of Delay:**
  1. **Discovery Delay:** The browser parser does not know the featured meal image URL from `index.html`. It must wait for `styles.css` to load, then `app.js` to execute, then `fetch("/api/campaigns")` to resolve, then `render()` to inject the `<img>` tag into the DOM.
  2. **Image Over-sizing:** Serving a 1.6K WebP file (174 KB) rather than an appropriately sized container image (40 KB).
  3. **No Preload Hint:** Neither `<link rel="preload">` nor `fetchpriority="high"` is utilized.

### 4.2 Interaction to Next Paint (INP)
- **Current Performance:** ~150ms (Desktop) / ~450ms (Mobile 4G).
- **Key Culprits:**
  1. **Full-page DOM re-generation on state mutations:** Changing a campaign or toggling an allergen destroys and re-creates all elements on the page, blocking the Main Thread for 80–220 ms.
  2. **Un-debounced validation and pill extraction:** Real-time character keystroke handling in `#planner-request` runs heavy regex logic synchronously.
  3. **Garbage Collection Jitters:** Continuous tearing down and re-binding of DOM event closures produces frequent micro-stalls.

### 4.3 Cumulative Layout Shift (CLS)
- **Current Performance:** Estimated 0.25 to 0.35 (Target: $<0.1$).
- **Key Shift Contributors:**
  1. **Unsized Images:** `<img>` tags lack native `width` and `height` attributes or CSS `aspect-ratio` placeholders before network arrival.
  2. **Client-Side Auth Gate Insertion:** `renderAuthModal()` is injected conditionally after the auth status is verified. The page renders initially, and if the user is unauthenticated or restricted by IAP, an overlay card is dynamically injected over the layout.
  3. **Dynamic Font Swap:** System font to Geist webfont switch triggers horizontal line-height re-wraps across headings (`h1` has `clamp(64px, 7vw, 108px)` font size).

---

## 5. Architectural Optimization Roadmap & Concrete Solutions

To transform the frontend into a best-in-class, sub-second web experience capable of achieving **95+ on Google Lighthouse** and **all-green Core Web Vitals**, the following 6-step engineering plan is recommended.

### Optimization 1: Enable Compression & Cache-Control in `server.py`
Upgrade the static file serving handler to support automatic gzip compression and cache headers.

```python
# Recommended server.py static serving handler update
import gzip

STATIC_CACHE_EXTENSIONS = {".css", ".js", ".svg", ".webp", ".png", ".ico", ".woff2"}

def serve_static_file(self, file_path: Path):
    ctype, _ = mimetypes.guess_type(str(file_path))
    raw_data = file_path.read_bytes()
    
    # 1. Header Caching Policy
    if file_path.suffix in STATIC_CACHE_EXTENSIONS:
        # Cache versioned assets for 1 year; immutable
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        etag = hashlib.md5(raw_data).hexdigest()
        self.send_header("ETag", f'"{etag}"')
        
        # Check conditional GET
        if self.headers.get("If-None-Match") == f'"{etag}"':
            self.send_response(304)
            self.end_headers()
            return
    else:
        # HTML files: check on revalidation
        self.send_header("Cache-Control", "public, max-age=0, must-revalidate")

    # 2. HTTP Gzip Compression
    accept_encoding = self.headers.get("Accept-Encoding", "")
    if "gzip" in accept_encoding and file_path.suffix in {".css", ".js", ".html", ".svg", ".json"}:
        compressed = gzip.compress(raw_data, compresslevel=6)
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(compressed)))
        self.end_headers()
        self.wfile.write(compressed)
    else:
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(raw_data)))
        self.end_headers()
        self.wfile.write(raw_data)
```

### Optimization 2: Responsive Image Pipeline & Dimension Attributes
1. **Generate Multi-Resolution Assets:** Generate optimized thumbnails for meal cards:
   - `meals/thumbnails/lemon-hake-potatoes-400w.webp` (~25 KB)
   - `meals/thumbnails/lemon-hake-potatoes-800w.webp` (~55 KB)
   - `meals/lemon-hake-potatoes-1600w.webp` (~174 KB)
2. **Apply Explicit Dimensions and Aspect Ratios in HTML:**
   ```html
   <!-- Example meal card image markup -->
   <img
     src="/meals/thumbnails/lemon-hake-potatoes-400w.webp"
     srcset="/meals/thumbnails/lemon-hake-potatoes-400w.webp 400w, /meals/thumbnails/lemon-hake-potatoes-800w.webp 800w"
     sizes="(max-width: 720px) 100vw, (max-width: 1100px) 50vw, 400px"
     width="400"
     height="266"
     style="aspect-ratio: 3/2; object-fit: cover;"
     alt="Merluza al limón con patatas panadera"
     loading="lazy"
     decoding="async"
   />
   ```
3. **LCP Hero Preload & High Priority:**
   For the default featured campaign, add a priority preload hint in `<head>` of `index.html`:
   ```html
   <link rel="preload" as="image" href="/meals/thumbnails/lemon-hake-potatoes-800w.webp" type="image/webp" fetchpriority="high" />
   ```

### Optimization 3: Eliminate Remote Logo Latency
In `app.js` and `marketing.js`, replace the external `sites.google.com` fallback with the local SVG directly:
```javascript
// High-performance, zero-latency local vector SVG
function renderGoogleCloudLockup() {
  return `
    <span class="gcloud-lockup-badge" aria-label="Google Cloud">
      <img
        class="gcloud-logo-img"
        src="/brand/google-cloud.svg"
        width="118"
        height="24"
        alt="Google Cloud"
        decoding="async"
      />
    </span>
  `;
}
```

### Optimization 4: CSS Optimization & Tailwind Purging
1. **Purge Unused Tailwind Layers:** Run Tailwind build with content purging across `app.js`, `marketing.js`, and HTML files to prune unused rules. This reduces `styles.css` from **70 KB down to ~12 KB uncompressed (3.2 KB gzip)**.
2. **Inline Critical CSS:** Extract core container styles into `<head>` to unblock First Contentful Paint:
   ```html
   <style>
     :root { --ink:#11110f; --paper:#f7f7f2; --green:#008f61; }
     body { background: var(--paper); color: var(--ink); margin: 0; font-family: system-ui, sans-serif; }
     .app-shell { min-height: 100vh; padding: 0 4vw 36px; }
     .brand-bar { display: flex; align-items: center; justify-content: space-between; min-height: 92px; border-bottom: 1px solid #deded7; }
   </style>
   ```

### Optimization 5: DOM Componentization & Incremental Updates
Replace full `root.innerHTML` destructions with targeted region re-renders:
1. **Container Isolation:** Split `#app-root` into 4 permanent container nodes:
   ```html
   <div id="auth-modal-root"></div>
   <header id="header-root"></header>
   <main id="main-content-root"></main>
   <div id="toast-root"></div>
   ```
2. **Targeted Subtree Updates:** When changing active tab, mutate only `#main-content-root`. When updating cart status, mutate only `#basket-section`.
3. **Event Delegation Pattern:**
   ```javascript
   // Bind once at boot
   document.getElementById('app-root').addEventListener('click', (e) => {
     const actionBtn = e.target.closest('[data-action]');
     if (!actionBtn) return;
     const action = actionBtn.getAttribute('data-action');
     const id = actionBtn.getAttribute('data-id');
     handleAction(action, id);
   });
   ```

### Optimization 6: Catalog API Pagination & Lazy Loading
Update `/api/catalog` in `server.py` to support query parameters:
```
GET /api/catalog?page=1&limit=24&category=pescaderia&postal_code=28016
```
- Returns 24 products per page (~8 KB JSON) instead of 1,595 products + 5,000 recipes (6 MB JSON).
- The full Cookidoo catalog is only loaded on-demand when the user searches recipes, not on initial catalog tab switch.

---

## 6. Implementation Impact Matrix

| Area | Quick Win (Low Effort, High Impact) | Architectural (Medium-High Effort) | Expected CWV Improvement |
| :--- | :--- | :--- | :--- |
| **Network & Caching** | Add `Cache-Control: public, max-age=31536000, immutable` and gzip compression to `server.py`. | Deploy Google Cloud CDN / Cloud Armor in front of Cloud Run to terminate caching at the global edge. | **FCP:** $-55\%$  <br>**LCP:** $-40\%$  <br>**Bandwidth:** $-75\%$ |
| **Image Delivery** | Replace remote Google Sites logo URL with local SVG. Add `width`, `height`, and `decoding="async"`. | Implement automated image resizing pipeline (`thumbnails/` at 400w and 800w) with `<picture>` `srcset`. | **CLS:** Drops to $\le 0.04$  <br>**LCP:** $-1.2\text{ s}$ |
| **Fonts** | Self-host Geist fonts locally in `/public/fonts/`; add `font-display: optional` or preload. | Preload critical woff2 subsets in HTML headers. | **FCP:** $-350\text{ ms}$  <br>**CLS:** Eliminates font-swap shift. |
| **JavaScript & DOM** | Debounce prompt validation ($150\text{ ms}$). Apply event delegation to `#app-root`. | Transition from monolithic `root.innerHTML` to component-scoped rendering or lightweight DOM diffing (Morphdom / Preact). | **INP:** Drops to $<80\text{ ms}$ (Good)  <br>Eliminates frame drops. |
| **Data APIs** | Paginate `/api/catalog` with limit/offset and lightweight JSON schema projections. | Cache compiled catalog responses in server memory with TTL. | **Memory:** $-90\%$  <br>**Tab Switch Delay:** $1.4\text{ s} \to 80\text{ ms}$ |

---

## 7. Verification Checklist & Command Reference

To verify improvements following roadmap execution, run the following audit checks:

```bash
# 1. Verify Gzip compression and Caching headers on static assets
curl -I -H "Accept-Encoding: gzip" https://mercadona-ai-companion-905208270932.europe-west1.run.app/styles.css

# Expected Headers:
# Content-Encoding: gzip
# Cache-Control: public, max-age=31536000, immutable
# ETag: "..."

# 2. Check total transfer weight of client-side code bundle
curl -s -H "Accept-Encoding: gzip" https://mercadona-ai-companion-905208270932.europe-west1.run.app/app.js | wc -c
# Target: < 20,000 bytes (gzip)

# 3. Check /api/catalog payload sizing
curl -s -H "Accept-Encoding: gzip" "https://mercadona-ai-companion-905208270932.europe-west1.run.app/api/catalog?postal_code=28016&limit=24" | wc -c
# Target: < 15,000 bytes (gzip)

# 4. Measure Lighthouse Core Web Vitals via Chrome DevTools or CLI
npx lighthouse https://mercadona-ai-companion-905208270932.europe-west1.run.app/ \
  --only-categories=performance \
  --preset=desktop \
  --output=json \
  --output-path=./lighthouse-report.json
```

---
*Report compiled autonomously by Child Subagent 5 for the Mercadona AI Companion engineering team.*
