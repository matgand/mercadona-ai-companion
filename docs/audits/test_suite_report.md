# Comprehensive Automated Test Suite Report
**Mercadona AI Companion & Campaign Library Microservices**  
**Role:** Lead Subagent 1: Automated Test Suite Architect  
**Date:** September 27, 2026  
**Status:** ✅ **302 / 302 Tests Passing (100% Pass Rate)**  
**Target Environment:** Python 3.11+ Standard Library (`unittest`, `unittest.mock`)  
**Production Code Integrity:** 100% Intact (Zero modifications to existing production application files)

---

## Executive Summary

An enterprise-grade, comprehensive automated test suite and fuzzing audit architecture was planned, implemented, and executed across all backend Python modules of the **Mercadona AI Companion** repository.

Five specialized subagent teams were spawned in parallel (`Model: "flash"`) to develop zero-dependency unit tests adhering to Google's testing best practices (`unit_test` skill). Each subagent authored dedicated test suites, executed iterative test verification, spawned sub-auditors to stress-test boundary and adversarial conditions, and produced detailed audit logs.

### Key Metrics
| Metric | Value |
|---|---|
| **Total Test Files** | 8 test suites |
| **Total Test Cases** | **302 tests** |
| **Pass Rate** | **100.0% (302 passed, 0 failures, 0 errors)** |
| **Execution Duration** | 13.60s (entire consolidated test suite) |
| **Modules Covered** | `mercadona_service.py`, `cookidoo_service.py`, `campaign_service.py`, `gemini_planner.py`, `server.py`, `scripts/build_full_catalog.py` |
| **External Dependencies** | 0 (Pure Python standard library `unittest` & `unittest.mock`) |
| **Production Code Diff** | 0 lines modified (`git status` clean on production modules) |

---

## Test Suites & Coverage Breakdown

### 1. Mercadona Tienda Service (`test_mercadona_service.py`, `test_mercadona_security.py`, `test_mercadona_stress_fuzz.py`)
- **Total Tests:** 117 tests (40 service + 36 security + 41 stress/fuzz)
- **Status:** ✅ 117 / 117 Passed (100%)
- **Coverage Areas:**
  - **Postal Code & Warehouse Resolution:** Validation of Spanish 5-digit postal codes (`28001`, `46001`, `08001`), prefix mapping to Mercadona distribution hubs/warehouses (`wh=bcn1`, `mad1`, `vlc1`), regex sanitization of non-numeric inputs, and graceful fallback to defaults (`28016`).
  - **Diacritics & Unicode Normalization:** Accurate handling of Spanish accents, diacritics (`á`, `é`, `í`, `ó`, `ú`, `ü`, `ñ`), and uppercase conversion (`normalize_spanish_text`).
  - **Catalog Lookup & Dietary Filters:** Exact and fuzzy matching, category navigation, dietary filtering (`sin gluten`, `sin lactosa`), and price calculations.
  - **1-Click Cart Preparation:** Product quantity bundling, substitution and unavailable item fallbacks, and total price aggregation.
  - **API Resiliency & Session Security:** Mocking HTTP 404/500/timeout responses, session persistence, JWT base64 claim decoding, and cURL / HAR credential ingestion.
  - **Throughput & Stress:** Verified JWT decoding at 409,000+ ops/sec, cURL parsing at 74,000+ ops/sec, and thread safety across 50 concurrent workers.

### 2. Cookidoo Recipe Service (`test_cookidoo_service.py`)
- **Total Tests:** 41 tests
- **Status:** ✅ 41 / 41 Passed (100%)
- **Coverage Areas:**
  - **Catalog Loading & Caching:** Loading all 5,000 recipes from `data/cookidoo_recipes.json` in 45ms; in-memory cache hits in 0.046ms (~1,000x speedup).
  - **Trademark & Description Sanitization:** Deterministic sanitization of "Receta oficial de Thermomix Cookidoo" boilerplate without ReDoS vulnerability; verified against 1MB payloads and 50,000 nested parenthetical injection attacks.
  - **Dietary & Attribute Filtering:** Filtering by tags (`is_vegetarian`, `is_gluten_free`, `is_quick`, prep times, difficulty).
  - **Ingredient Extraction & Normalization:** Robust parsing of quantities, units, and ingredient strings.
  - **Data Integrity Audit:** Audited referential integrity across 29,192 ingredient references against 261 distinct Mercadona SKUs in `mercadona_products.json`.

### 3. Campaign Library Service (`test_campaign_service.py`)
- **Total Tests:** 41 tests
- **Status:** ✅ 41 / 41 Passed (100%)
- **Coverage Areas:**
  - **CRUD Operations & Lifecycle State Machine:** Full lifecycle transitions across `Activa`, `Planificada`, `Borrador`, `Terminada`.
  - **Category & Profile Metadata:** Validation of `VALID_CATEGORIES` (`Familias`, `Saludables`, `Rutina rápida`, `Ahorro`) and `PROFILES_METADATA` household demographics.
  - **Thread Concurrency:** Stress testing multi-threaded reads/writes using `_LOCK`.
  - **Gemini LLM Prompting & Schema Generation:** Mocking Google GenAI SDK and REST API fallbacks, rate limit throttling (429), and deterministic offline fallbacks.
  - **Microservice Synchronization:** Inter-service synchronization token verification (`SESSION_SECRET` HMAC SHA-256) and Cloud Run IAP compatibility.

### 4. Gemini Planner Engine (`test_gemini_planner.py`, `test_gemini_planner_audit.py`, `test_quick_swap_integrity.py`)
- **Total Tests:** 52 tests (36 core + 12 adversarial audit + 4 nutritional integrity)
- **Status:** ✅ 52 / 52 Passed (100%)
- **Coverage Areas:**
  - **Prompt Validation & Guardrails:** Rejection of empty/short inputs, jailbreak/DAN attacks, system prompt extraction, code requests, and off-topic topics.
  - **Constraint Parsing:** Person counts, meal counts [1-7], prep time ceilings [5-120 min], caloric caps [100-1500 kcal], budget limits [10-500 €], dietary restrictions (`vegetarianOnly`, `requiredFish`), and all EU-14 allergens.
  - **Model Fallback Mechanism:** Primary model (`gemini-3.8-flash`) automatic fallback to `gemini-2.5-flash` on HTTP 429/503 or quota limits, with offline deterministic fallback.
  - **Quick-Swap Recipe Engine:** Replacement preserving day sequencing, strict adherence to dietary filters, orphan ingredient basket pruning, and rotation cycling.
  - **Portion & Budget Calculation:** Household portion formula (`adults + 0.75 * children`), staple item deduplication (garlic, onion, olive oil), and budget cap enforcement.

### 5. Server API & Microservices (`test_server_api.py`)
- **Total Tests:** 51 tests
- **Status:** ✅ 51 / 51 Passed (100%)
- **Coverage Areas:**
  - **Google Identity & OAuth:** Tokeninfo verification, audience enforcement, verified email check, IAP email header validation (`X-Goog-Authenticated-User-Email`), HMAC SHA-256 session token generation and constant-time verification (`hmac.compare_digest`).
  - **Allowlist Access Control:** Strict gating for authorized accounts:
    - `matgand@gmail.com`
    - `mgandolfi@google.com`
    - `andrea.anaut@gmail.com`
    - `mattia@mgandolfi.altostrat.com`
    - Unauthenticated/unauthorized requests rejected with HTTP 401/403.
  - **Dual Microservice Roles:** Correct behavior under `SERVICE_ROLE=companion` vs `SERVICE_ROLE=campaign-library`.
  - **All REST Endpoints:** Health checks, user sessions, plan generation, recipe swap, Cookidoo handoff, cart sync, and campaign management.
  - **Path Traversal Security:** Rejection of directory traversal attacks (`/../../server.py`, `%2e%2e`, `/....//....//`, `/subdir/../../`).
  - **Catalog Builder Algorithm:** Testing `scripts/build_full_catalog.py` allergen inference heuristics, text normalization, and product tree parsing.

---

## Detailed Consolidated Test Results Matrix

| Test Module | File Path | Test Count | Pass Rate | Duration |
|---|---|---|---|---|
| **Mercadona Service** | [`tests/test_mercadona_service.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/tests/test_mercadona_service.py) | 40 | 100% | 0.42s |
| **Mercadona Security** | [`tests/test_mercadona_security.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/tests/test_mercadona_security.py) | 36 | 100% | 0.72s |
| **Mercadona Stress & Fuzz** | [`tests/test_mercadona_stress_fuzz.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/tests/test_mercadona_stress_fuzz.py) | 41 | 100% | 1.25s |
| **Cookidoo Service** | [`tests/test_cookidoo_service.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/tests/test_cookidoo_service.py) | 41 | 100% | 0.25s |
| **Campaign Service** | [`tests/test_campaign_service.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/tests/test_campaign_service.py) | 41 | 100% | 0.11s |
| **Gemini Planner** | [`tests/test_gemini_planner.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/tests/test_gemini_planner.py) | 36 | 100% | 0.02s |
| **Gemini Adversarial Audit** | [`tests/test_gemini_planner_audit.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/tests/test_gemini_planner_audit.py) | 12 | 100% | 0.01s |
| **Quick-Swap Integrity** | [`tests/test_quick_swap_integrity.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/tests/test_quick_swap_integrity.py) | 4 | 100% | 0.01s |
| **Server REST API & OAuth** | [`tests/test_server_api.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/tests/test_server_api.py) | 51 | 100% | 0.07s |
| **TOTAL CONSOLIDATED** | `tests/test_*.py` | **302** | **100%** | **13.60s** |

---

## High-Priority Audit Findings & Recommendations

From the specialized auditor subagents, the following key findings have been documented in the individual reports under `docs/audits/`:

1. **Spanish Contraction Gap in Allergen Parser (`gemini_planner.py`) [HIGH RISK]**:
   - *Detail:* Spanish speakers frequently say "alérgico **al** pescado" or "intolerancia **al** gluten". The regex `alérgico a` misses the contraction `al` (`a + el`), causing masculine allergen clauses to be skipped unless phrased as "alérgica a".
   - *Recommendation:* Update regex pattern to `r"(?:al[ée]rgic[oa]s?\s+(?:a|al)|intolerantes?\s+(?:a|al))\s+([a-záéíóúñ\s]+)"`.

2. **Tier-3 Quick-Swap Allergen Filter Relaxation (`gemini_planner.py`) [HIGH RISK]**:
   - *Detail:* If an excessively constrained user swaps a meal and Tiers 1 and 2 return 0 candidates, Tier 3 falls back without applying the allergen exclusion list.
   - *Recommendation:* Never drop allergen filters in fallback tiers; instead raise or return an explicit user warning if no allergen-safe alternatives exist.

3. **Data Integrity & False-Positive Allergen Tags (`data/cookidoo_recipes.json`) [MEDIUM RISK]**:
   - *Detail:* Auditing 29,192 ingredient mappings revealed that the ingredient "chile" (chili pepper) matched "Mejillón de Chile" SKU `62401`, mis-tagging 40 vegetarian recipes with mollusc allergens. In addition, "vinagre" matched "Boquerones en vinagre" SKU `80405` in lentil dish `r729125`.
   - *Recommendation:* Add word-boundary and category-scoped matching in `scripts/build_full_catalog.py` to prevent produce ingredients from matching seafood SKUs.

4. **Multi-Worker Concurrency & Atomic File Writes (`campaign_service.py`) [MEDIUM RISK]**:
   - *Detail:* `_LOCK = threading.Lock()` is effective within a single Python process, but multiple Cloud Run worker processes require file-level locks (`fcntl.flock`) or database-backed persistence to prevent race conditions during concurrent marketing edits.
   - *Recommendation:* Implement atomic write replacement (`tempfile` + `os.replace`) to protect `campaigns.json` against truncated writes during sudden restarts.

---

## Instructions for Running Tests

To run the full test suite locally at any time:
```bash
cd /usr/local/google/home/mgandolfi/mercadona-ai-companion
python3 -m unittest discover -s tests -p "test_*.py"
```

To run individual module test suites:
```bash
python3 -m unittest tests/test_mercadona_service.py
python3 -m unittest tests/test_cookidoo_service.py
python3 -m unittest tests/test_campaign_service.py
python3 -m unittest tests/test_gemini_planner.py
python3 -m unittest tests/test_server_api.py
```
