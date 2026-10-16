# Comprehensive Audit & Target Cloud Architecture Report
**Project**: Mercadona AI Companion (`/usr/local/google/home/mgandolfi/mercadona-ai-companion`)  
**Auditor**: Child 5 — Data Pipeline & Scalable Cloud Architecture Auditor  
**Date**: September 27, 2026  
**Status**: Completed  

---

## 1. Executive Summary

This audit delivers an end-to-end evaluation of the Mercadona AI Companion's current data pipeline, specifically inspecting `scripts/build_full_catalog.py`, existing JSON data assets (`mercadona_products.json`, `cookidoo_recipes.json`), and the surrounding system design. 

While the current script succeeded in bootstrapping an initial catalog of 1,595 products and 5,000 recipes, the audit identified **severe structural bottlenecks, silent failure modes, regulatory health risks, and data corruption vulnerabilities** that make the current implementation unsuitable for production:
1. **Critical Health & Compliance Risk (EU Regulation 1169/2011)**: Allergen inference relies on brittle substring heuristics against product titles (e.g. `apio` matching `tapioca`, `pan ` missing compound words, and a blanket `"vegetal"` negative check that incorrectly strips dairy allergens from pizzas and sandwiches). Over 950 products currently lack verified allergen declarations, and official Mercadona API product detail endpoints are bypassed.
2. **Silent Ingestion & Non-Atomic Data Loss**: Broad `except Exception` blocks suppress API schema drift, HTTP 429/500 errors, and timeouts. File writing calls `Path.write_text` directly on multi-megabyte production JSON files without atomic staging (`tempfile` + `os.replace`), risking total zero-byte catalog truncation upon process crash or SIGTERM.
3. **Data Quality & Synthetic Fallbacks**: Missing prices silently default to `1.50€`, and recipe calories are fabricated using MD5 hash pseudo-random arithmetic (`240 + (hash % 140)`), undermining user trust for dietary planning.
4. **Fragile Scraping & Algolia Truncation**: Algolia API credentials are regex-scraped from Vorwerk's Next.js HTML bundles (`__NEXT_DATA__`). Querying solely across `difficulty` levels risks silent drop of recipes exceeding Algolia's 1,000-hit cap.
5. **Architectural Gap**: The system currently runs as a local, synchronous, non-versioned batch job tied to a single Madrid warehouse (`mad3`), lacking regional multi-warehouse support, automated quality validation gates, and real-time synchronization.

To solve these deficiencies, this report defines:
- **Part I**: Code quality, resilience, and data cleaning audit of `scripts/build_full_catalog.py`.
- **Part II**: Empirical data profiling and anomalies detected in existing datasets.
- **Part III**: Target Google Cloud Enterprise Architecture (Cloud Run, Cloud Tasks, GCS Bronze Lakehouse, BigQuery Medallion, Dataplex Auto-Profiling, and Vertex AI Vector Search).
- **Part IV**: Concrete remediation, refactoring patterns, and a 5-phase migration roadmap.

---

## 2. Code Quality, Resilience & Data Cleaning Audit

### 2.1 Deep Code Review of `build_full_catalog.py`

#### A. File I/O and Concurrency Flaws
- **Non-Atomic File Overwrite (Lines 491–498)**:
  ```python
  PRODUCTS_PATH.write_text(json.dumps(list(products.values()), ensure_ascii=False, indent=2), encoding="utf-8")
  RECIPES_PATH.write_text(json.dumps(recipes, ensure_ascii=False, indent=2), encoding="utf-8")
  ```
  `Path.write_text` truncates existing files immediately on open. If an unhandled exception, SIGKILL, memory exhaustion (OOM), or server power failure occurs during `json.dumps` serialization, the entire primary database is wiped to 0 bytes.
- **Synchronous, Blocking HTTP Execution (Lines 103–134, 290–301)**:
  Requests are executed sequentially with `urllib.request.urlopen` and fixed blocking timeouts (`timeout=8`, `timeout=15`). A single unresponsive socket blocks the entire ingestion process. There is no connection pooling, HTTP/2 multiplexing, or keep-alive reuse.
- **Arbitrary Delay Sleep Without Jitter (Line 134)**:
  `time.sleep(0.05)` is a crude rate-limiting mechanism that does not respect upstream rate headers (`Retry-After`) and fails to adapt when HTTP 429 (Too Many Requests) is returned.

#### B. Exception Handling & Silent Failures
- **Broad Catch-All Suppressing Fatal Errors (Lines 132–134, 330–332)**:
  ```python
  except Exception as exc:
      print(f"Warning fetching subcategory {subcat_id}: {exc}")
  # and
  except Exception as exc:
      print(f"Warning querying {cat_id} ({diff}): {exc}")
      continue
  ```
  The script catches all exceptions indiscriminately. If Mercadona changes API routes, Cookidoo revokes API tokens, or Cloudflare/Akamai returns HTTP 403 Forbidden, the script merely logs a stdout warning, continues looping, and writes incomplete/corrupted datasets to disk as if the run succeeded.
- **Fragile Algolia Credential Scraping (Lines 265–278)**:
  ```python
  m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', txt)
  if not m:
      raise RuntimeError("Could not find __NEXT_DATA__ on cookidoo.es")
  nd = json.loads(m.group(1))
  pp = nd["props"]["pageProps"]
  return pp["algoliaAppId"], pp["algoliaApiKeyData"]["apiKey"]
  ```
  Scraping `__NEXT_DATA__` from an HTML payload breaks as soon as Vorwerk migrates the page to React Server Components (Next.js App Router streaming chunks) or relocates public search keys.

#### C. Algolia Pagination & 1,000-Hit Cap Risk (Lines 324–333)
```python
for diff in ["easy", "medium", "advanced"]:
    filters = ["language:es", "countries:ES", f"categories.id:{cat_id}", f"difficulty:{diff}"]
    hits = query_algolia_batch(app_id, api_key, filters, hits_per_page=1000)
```
Algolia strictly caps query results at 1,000 hits per query. Assuming that splitting by `difficulty` guarantees `< 1000` items is unsafe. For large categories (e.g. *Platos principales: carne* or *Platos de pasta y arroz*), easy recipes frequently exceed 1,000. Because the script does not inspect `nbHits` or paginate via `page` / `cursor`, any recipes beyond hit #1000 are silently dropped.

---

## 3. Data Integrity, Schema Validation & Regulatory Compliance

### 3.1 Allergen Inference vs. EU Regulation 1169/2011
Regulation (EU) No 1169/2011 mandates exact, verifiable information on 14 major food allergens. The current script attempts to infer allergens through crude substring matching in `infer_product_allergens` (lines 59–92):

```python
# Problematic substring matching
if any(w in n for w in ("apio",)):
    found.append("Contiene apio y productos derivados.")
if any(w in n for w in ("vino", "vinagre", "sidra", "cava")):
    found.append("Contiene dióxido de azufre y sulfitos.")
```

#### Identified Allergen Failure Modes:
1. **Dangerous False Positives**:
   - `"apio"` matches `"tapioca"`, incorrectly warning celiacs/users about celery allergens.
   - `"vino"` matches `"bovino"`, flagging fresh beef products as containing sulfites.
2. **Life-Threatening False Negatives**:
   - `"vegetal"` negative check: If a product name contains `"vegetal"`, dairy detection is suppressed (`"vegetal" not in n`). A "Sandwich vegetal con queso y huevo" or "Pizza vegetal cuatro quesos" is erroneously labeled as dairy/lactose-free!
   - Gluten heuristics only look for `"pan "`, `"harina de trigo"`, missing rye (`centeno`), barley (`cebada`), spelt (`espelta`), oats (`avena`), kamut, semolina (`sémola`), and malt extract (`extracto de malta`).
   - Tree nuts check checks for `"nuez"`, `"almendra"`, but misses macadamia, pecan (`pecana`), and Brazil nuts.
3. **Bypassing Official Mercadona Declarations**:
   Mercadona's API provides structured nutritional facts and certified allergen statements on individual product endpoints (`/api/products/{id}/`). The script completely bypasses these endpoints and applies speculative heuristics.

### 3.2 Arbitrary Fallback Values & Synthetic Data
1. **Hardcoded Price Fallback (`1.50€`) (Lines 112–115)**:
   ```python
   try:
       unit_price = float(pi.get("unit_price") or 1.50)
   except Exception:
       unit_price = 1.50
   ```
   If price metadata is missing or restructured, the item is forced to `1.50€`. Expensive meats, wines, and seafood will be calculated at 1.50€, corrupting recipe cost estimates and basket budget optimization.
2. **Fabricated Caloric Content (Lines 432–441)**:
   ```python
   h_seed = int(hashlib.md5(rid.encode("utf-8")).hexdigest()[:6], 16)
   if "low_calories" in nut_goals or "low_fat" in nut_goals:
       cal = 240 + (h_seed % 140)
   ...
   ```
   Calories are generated from MD5 hash pseudo-random arithmetic rather than real nutritional data. Presenting simulated calories in a health and meal-planning assistant is a major data integrity violation.
3. **Hardcoded Ingredient Fallbacks (Lines 237–260)**:
   If fewer than 3 ingredients map to products, the script injects arbitrary items: chicken breast (`3400`) or olive oil (`4740`). This causes chicken or olive oil to appear in recipes that do not include them.

### 3.3 Schema Drift and Heterogeneity in Existing Data Files
An audit of `data/mercadona_products.json` revealed severe schema drift between the initial 101 products and the 1,494 newly appended products:

| Field | Initial 101 Products | Appended 1,494 Products | Data Completeness |
| :--- | :--- | :--- | :--- |
| `id` | Present | Present | 100.0% |
| `name` | Present | Present | 100.0% |
| `unit_price` | Present | Present | 100.0% |
| `unit` | Present | Present | 100.0% |
| `thumbnail` | Present | Present | 100.0% |
| `share_url` | Present | Present | 100.0% |
| `allergens` | Present (Verified) | Inferred / Missing | 100.0% (39.4% inferred, 59.7% missing) |
| `available` | Missing | Present | 93.7% |
| `warehouse` | Missing | Present (`"mad3"`) | 93.7% |
| `categories` | Present | **MISSING** | 6.3% |
| `ingredients`| Present | **MISSING** | 6.1% |
| `packaging`  | Present | **MISSING** | 6.1% |
| `unit_size`  | Present | **MISSING** | 6.1% |
| `size_format`| Present | **MISSING** | 6.3% |

**Consequence**: The catalog has two incompatible schemas within a single JSON array, violating Google Cloud Data Autocleaning rules for schema alignment and causing downstream UI crashes when accessing `.ingredients` or `.categories`.

---

## 4. Findings Summary & Severity Matrix

| ID | Issue Description | Location | Severity | Impact |
| :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | Substring allergen inference causes dangerous false positives/negatives | `build_full_catalog.py:59-92` | **CRITICAL** | Severe health/allergy safety hazard under EU 1169/2011 |
| **DAT-01** | Non-atomic JSON file truncation risks zero-byte catalog wipe | `build_full_catalog.py:491-498` | **CRITICAL** | Production data loss upon crash or cancellation |
| **DAT-02** | Hardcoded `1.50€` price fallback corrupts budget calculations | `build_full_catalog.py:112-115` | **HIGH** | Inaccurate recipe basket costs and cart totals |
| **DAT-03** | Fabricated calories via MD5 hash pseudo-random numbers | `build_full_catalog.py:432-441` | **HIGH** | Falsified nutritional values in user meal plans |
| **OPS-01** | Blind `except Exception` hides upstream 403/429/500 failures | `build_full_catalog.py:132, 330`| **HIGH** | Silent pipeline failures and incomplete data ingestion |
| **OPS-02** | Algolia 1,000-hit cap drops recipes without pagination | `build_full_catalog.py:326-333` | **HIGH** | Catalog truncation and missing recipe inventory |
| **DAT-04** | Schema drift between initial and appended products | `mercadona_products.json` | **MEDIUM** | Inconsistent object models breaking frontend consumers |
| **PERF-01**| Synchronous sequential HTTP requests without connection pooling | `build_full_catalog.py:100-135` | **MEDIUM** | Slow execution, high latency, vulnerable to network drops |
| **DAT-05** | Accidental product injection in recipe fallbacks | `build_full_catalog.py:237-260` | **MEDIUM** | Unrelated products (chicken, oil) forced into recipes |
| **OPS-03** | Hardcoded warehouse dependency (`mad3`) | `build_full_catalog.py:101, 130`| **MEDIUM** | Inability to support non-Madrid users and warehouses |

---

## 5. Target Google Cloud Enterprise Architecture

To transform this fragile local scraper into a scalable, resilient, event-driven data platform, the following target architecture is designed adhering to Google Cloud best practice skills (`bigquery-basics`, `data-autocleaning`, `gcs-security-assessment`).

```
 +---------------------------------------------------------------------------------------------------+
 |                                   GOOGLE CLOUD PLATFORM (TARGET)                                  |
 |                                                                                                   |
 |  [Cloud Scheduler]                                                                                |
 |          | (Hourly incremental / Daily full crawl)                                                |
 |          v                                                                                        |
 |  [Cloud Workflows]                                                                                |
 |          | (Fan-out by Category & Warehouse: mad3, vlc1, bcn1, sev1)                              |
 |          v                                                                                        |
 |  [Cloud Tasks] (Rate Limiter: 5 req/sec max dispatch, exponential backoff + jitter)                |
 |          |                                                                                        |
 |          v                                                                                        |
 |  [Cloud Run: Ingestion Microservice] <==== [Secret Manager: Algolia / Mercadona API Keys]         |
 |          |                                                                                        |
 |          +-----------------------+ (Stream raw JSONL + hash)                                      |
 |                                  v                                                                |
 |                      [GCS Bronze Lakehouse] (gs://mercadona-lake-raw/)                            |
 |                      - Uniform Bucket-Level Access (UBLA)                                         |
 |                      - CMEK Cloud KMS Encryption                                                  |
 |                      - Lifecycle: 30-day versioning, 90-day Nearline                              |
 |                                  |                                                                |
 |                                  | (Object Finalized Event)                                       |
 |                                  v                                                                |
 |                             [Eventarc]                                                            |
 |                                  |                                                                |
 |                                  v                                                                |
 |                      [BigQuery ELT Lakehouse]                                                     |
 |                      +------------------------------------------------------+                     |
 |                      | Bronze: raw_products_stream (Partition by IngestDate)|                     |
 |                      +------------------------------------------------------+                     |
 |                                  | (Scheduled SQL Transformation)                                 |
 |                                  v                                                                |
 |                      +------------------------------------------------------+                     |
 |                      | Silver: products_curated & recipes_curated           |                     |
 |                      | - Partition: warehouse_id, updated_at                |                     |
 |                      | - Cluster: category, allergens                       |                     |
 |                      +------------------------------------------------------+                     |
 |                                  |                                                                |
 |                                  v                                                                |
 |                      +------------------------------------------------------+                     |
 |                      | [Dataplex Data Quality & Auto-Profiling Scan]        |                     |
 |                      | - Null check: unit_price, product_id, name           |                     |
 |                      | - Allergen coherence validation                      |                     |
 |                      | - Anomaly detection (>1% null surge -> Quarantine)   |                     |
 |                      +------------------------------------------------------+                     |
 |                                  |                                                                |
 |                                  v                                                                |
 |                      +------------------------------------------------------+                     |
 |                      | Gold: v_active_products & v_curated_recipes          |                     |
 |                      +------------------------------------------------------+                     |
 |                                  |                                                                |
 |                 +----------------+----------------+                                               |
 |                 v                                 v                                               |
 |      [Vertex AI Embeddings]             [CDC / Cloud Function]                                    |
 |      (text-embedding-005)                         |                                               |
 |                 v                                 v                                               |
 |   [Vertex AI Vector Search]              [Firestore Native Cache]                                 |
 |   (ScaNN Nearest Neighbor Index)         (Sub-10ms App State & Stock)                             |
 |                 |                                 |                                               |
 +-----------------|---------------------------------|-----------------------------------------------+
                   |                                 |
                   v                                 v
        [Mercadona AI Companion Web App (React / Node.js Serverless on Cloud Run)]
```

### 5.1 Storage & Lakehouse Layer (Medallion Pattern)

#### A. GCS Bronze Lakehouse Specification (`gcs-security-assessment` compliant)
- **Bucket**: `gs://mercadona-lake-raw/`
- **Security Controls**:
  - **Uniform Bucket-Level Access (UBLA)**: Enabled (no object-level ACLs).
  - **Public Access Prevention**: Enforced (`enforced`).
  - **CMEK**: Encrypted with regional Cloud KMS key (`projects/mercadona-ai/locations/europe-west1/keyRings/catalog-ring/cryptoKeys/lakehouse-key`).
  - **Lifecycle Policy**: Delete non-current object versions after 30 days; transition raw bronze archives to Nearline storage after 90 days.
  - **Partition Path Structure**:
    ```
    gs://mercadona-lake-raw/source=mercadona/warehouse={wh}/year={YYYY}/month={MM}/day={DD}/cat_{id}.jsonl.gz
    gs://mercadona-lake-raw/source=cookidoo/year={YYYY}/month={MM}/day={DD}/cat_{id}_{diff}.jsonl.gz
    ```

#### B. BigQuery Silver & Gold Table Definitions (`bigquery-basics` compliant)

```sql
-- Silver Table: Curated Products
CREATE OR REPLACE TABLE `mercadona_curated.products` (
  product_id STRING NOT NULL,
  warehouse_id STRING NOT NULL,
  name STRING NOT NULL,
  unit_price NUMERIC NOT NULL,
  unit_size NUMERIC,
  size_format STRING,
  packaging STRING,
  unit STRING,
  thumbnail_url STRING,
  share_url STRING,
  declared_allergens STRING,
  inferred_allergens ARRAY<STRING>,
  allergens_inferred BOOL NOT NULL,
  ingredients_text STRING,
  categories ARRAY<STRING>,
  is_available BOOL NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  raw_payload_hash BYTES NOT NULL
)
PARTITION BY DATE(updated_at)
CLUSTER BY warehouse_id, is_available;

-- Silver Table: Curated Recipes
CREATE OR REPLACE TABLE `mercadona_curated.recipes` (
  recipe_id STRING NOT NULL,
  cookidoo_id STRING NOT NULL,
  name STRING NOT NULL,
  original_name STRING,
  description STRING,
  category STRING,
  is_dinner BOOL,
  minutes INT64,
  calories_per_serving INT64, -- NULL if unverified, no synthetic hashes
  cookidoo_servings INT64,
  is_vegetarian BOOL NOT NULL,
  is_fish BOOL NOT NULL,
  allergens ARRAY<STRING>,
  product_ids ARRAY<STRING>,
  ingredients ARRAY<STRING>,
  estimated_cost NUMERIC,
  cookidoo_url STRING,
  image_url STRING,
  updated_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(updated_at)
CLUSTER BY is_vegetarian, is_fish, category;
```

### 5.2 Automated Data Quality Gates (`data-autocleaning` compliant)
Using **Dataplex Data Quality** and BigQuery validation assertions before publishing to Gold serving views:
1. **Zero-Null Price Rule**: `unit_price IS NOT NULL AND unit_price > 0.00`. If any active item lacks a price, fail the batch. Never impute `1.50€`.
2. **Allergen Integrity Gate**:
   - `allergens` array must contain zero `NULL` items (`ARRAY_FILTER(allergens, e -> e IS NOT NULL)`).
   - If product name contains `"leche"`, `"queso"`, or `"yogur"`, declared or inferred allergens must include `"dairy"` (unless certified `"sin lactosa"`).
   - If product name contains `"sin gluten"`, `"gluten"` must not be present in allergens.
3. **Threshold Anomaly Gate**:
   - Alert and quarantine batch if `NULL` count in critical attributes increases by > 1.0% compared to the prior Dataplex profiling baseline.
   - Quarantine invalid records into `mercadona_curated.quarantined_records` without stopping serving for previously verified records.

### 5.3 Real-Time Serving & AI Search
1. **Vertex AI Vector Search**:
   - Ingest recipe text representations (name, description, ingredients) into `text-embedding-005` to generate 768-dimensional embeddings.
   - Deploy a ScaNN Approximate Nearest Neighbor index on Vertex AI Vector Search.
   - Replace brittle keyword token mappers with semantic embedding similarity: map natural recipe ingredient strings (e.g., "1 chalota picada finamente") to the nearest Mercadona SKU embedding with cosine similarity thresholding (>0.82).
2. **Firestore Native Cache**:
   - Maintain sub-10ms localized catalogs partitioned by `warehouses/{warehouseId}/products/{productId}`.
   - Update Firestore via BigQuery Change Data Capture (CDC) or Cloud Run micro-events, ensuring real-time pricing and stock synchronization for user carts.

### 5.4 Security, IAM & Governance
- **Least Privilege Workload Identity**:
  - `sa-mercadona-crawler`: Granted only `roles/storage.objectCreator` on `gs://mercadona-lake-raw` and `roles/secretmanager.secretAccessor` on required credentials.
  - `sa-data-pipeline`: Granted `roles/bigquery.dataEditor` and `roles/dataplex.metadataEditor`.
- **Resource Attribution**: All jobs, buckets, and services enforce mandatory labels:
  `env=production`, `service=mercadona-companion`, `component=data-pipeline`, `cost-center=ai-engineering`.

---

## 6. Local Refactoring: Immediate Code Hardening

Until the Cloud Lakehouse is fully provisioned, `scripts/build_full_catalog.py` must be immediately patched with the following critical safeguards:

### Pattern 1: Atomic File Writing Safeguard
```python
import os
import tempfile
from pathlib import Path

def atomic_write_json(target_path: Path, data: Any) -> None:
    """Safely writes JSON data to a temporary file before atomic renaming, preventing zero-byte corruption."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        "w",
        dir=target_path.parent,
        delete=False,
        encoding="utf-8"
    )
    try:
        json.dump(data, temp_file, ensure_ascii=False, indent=2)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        os.replace(temp_file.name, target_path)
    except Exception:
        if os.path.exists(temp_file.name):
            os.remove(temp_file.name)
        raise
```

### Pattern 2: Word-Boundary & Regulatory-Aware Allergen Extraction
```python
import re

ALLERGEN_PATTERNS = {
    "dairy": [r"\bleche\b", r"\bqueso\b", r"\byogur\b", r"\bmantequilla\b", r"\bnata\b", r"\bmozzarella\b"],
    "gluten": [r"\btrigo\b", r"\bcebada\b", r"\bcenteno\b", r"\bespelta\b", r"\bavena\b", r"\bpan\b", r"\bmacarr(on|ones)\b"],
    "celery": [r"\bapio\b"], # Requires word boundary; tapioca will NOT match
    "fish": [r"\bmerluza\b", r"\bsalm[oó]n\b", r"\bbacalao\b", r"\bat[uú]n\b", r"\bpescado\b"],
    "crustaceans": [r"\blangostino\b", r"\bgamba\b", r"\bcamar[oó]n\b"],
    "molluscs": [r"\bmejill[oó]n\b", r"\balmeja\b", r"\bcalamar\b", r"\bpulpo\b"],
    "nuts": [r"\bnuez\b", r"\bnueces\b", r"\balmendra\b", r"\bavellana\b", r"\bpistacho\b"],
    "peanuts": [r"\bcacahuete\b", r"\bman[ií]\b"],
    "eggs": [r"\bhuevo\b", r"\bhuevos\b", r"\bmayonesa\b"],
    "sulphites": [r"\bvino\b", r"\bvinagre\b", r"\bsidra\b", r"\bcava\b"], # \bvino\b prevents matching 'bovino'
}

def clean_allergens(name: str, raw_ingredients: str = "") -> dict[str, Any]:
    text = f"{name} {raw_ingredients}".lower()
    inferred: list[str] = []
    
    # Check each allergen with strict boundary regex
    for allergen, patterns in ALLERGEN_PATTERNS.items():
        if any(re.search(pat, text) for pat in patterns):
            # Check for negative certifications
            if allergen == "dairy" and "sin lactosa" in text:
                continue
            if allergen == "gluten" and "sin gluten" in text:
                continue
            inferred.append(allergen)
            
    return {
        "allergens": sorted(inferred),
        "allergens_inferred": True,
        "disclaimer": "Información estimada mediante análisis de ingredientes. Consulte siempre el envase físico."
    }
```

### Pattern 3: Algolia Resilient Pagination
```python
def fetch_all_algolia_hits(app_id: str, api_key: str, base_filters: list[str]) -> list[dict[str, Any]]:
    hits = []
    page = 0
    while True:
        payload = {
            "query": "",
            "page": page,
            "hitsPerPage": 100,
            "facetFilters": base_filters,
        }
        res = query_algolia(app_id, api_key, payload)
        batch = res.get("hits", [])
        if not batch:
            break
        hits.extend(batch)
        page += 1
        nb_pages = res.get("nbPages", 0)
        if page >= nb_pages or page >= 10: # Respect 1000 hit ceiling
            if res.get("nbHits", 0) > len(hits):
                logger.warning("Query truncated by Algolia cap: %d total hits", res.get("nbHits"))
            break
    return hits
```

---

## 7. Migration & Implementation Roadmap

| Phase | Milestone | Deliverables | Target Timeline |
| :--- | :--- | :--- | :--- |
| **Phase 1: Remediation & Hardening** | Local Script Hardening | - Implement atomic writes (`atomic_write_json`).<br>- Replace substring regex with word boundaries.<br>- Eliminate synthetic calories and `1.50€` fallbacks.<br>- Align product schemas (`mercadona_products.json`). | Immediate (Sprint 1) |
| **Phase 2: Lakehouse Provisioning** | GCP Storage & BigQuery Setup | - Provision `gs://mercadona-lake-raw` with UBLA, CMEK, and lifecycle rules.<br>- Deploy BigQuery datasets (`mercadona_raw`, `mercadona_curated`).<br>- Configure Dataplex data quality scan rules. | Sprint 2 |
| **Phase 3: Serverless Scraping** | Cloud Run & Cloud Tasks | - Containerize scraper microservice on Cloud Run.<br>- Set up Cloud Tasks queue with 5 req/sec rate limit.<br>- Move Algolia / Cookidoo credentials to Secret Manager. | Sprint 3 |
| **Phase 4: Semantic Search & AI** | Vertex AI Vector Search | - Embed recipe descriptions and ingredient strings with `text-embedding-005`.<br>- Deploy ScaNN vector index on Vertex AI Vector Search.<br>- Replace heuristic string mapper with cosine vector matching. | Sprint 4 |
| **Phase 5: Real-Time Serving** | Firestore CDC & Production Cutover | - Stream active curated products to Firestore for sub-10ms cache.<br>- Connect web companion frontend to Cloud Run / Firestore APIs.<br>- Decommission local scraping scripts. | Sprint 5 |

---

## 8. Conclusion & Sign-Off

The existing data ingestion script served well as a local prototype, but its silent failure modes, non-atomic writes, and heuristic allergen guesswork pose operational and safety risks. Implementing the immediate code hardening refactors eliminates catastrophic data wipeouts and false allergen classifications, while the Google Cloud target architecture establishes a foundation for an enterprise-ready, real-time, AI-driven Mercadona Companion.
