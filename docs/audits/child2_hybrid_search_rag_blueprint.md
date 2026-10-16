# Architectural Blueprint: Hybrid Search & Vector RAG for Mercadona & Cookidoo
**Author**: Child Subagent 2 (AlloyDB & BigQuery Hybrid Search & Vector RAG Architect)  
**Date**: September 27, 2026  
**Target Workload**: Semantic matching across 5,000+ Cookidoo Spanish recipes and 15,000+ Mercadona product SKUs  
**Target Services**: Cloud Run (`mercadona-ai-companion`), AlloyDB for PostgreSQL, BigQuery ML / Vector Search  

---

## Executive Summary

The **Mercadona AI Companion** requires high-accuracy, sub-100ms semantic retrieval and deterministic inventory mapping between culinary concepts (Cookidoo recipes with complex ingredient lines, dietary constraints, and preparation steps) and supermarket retail items (Mercadona product catalog with EANs, warehouse-specific inventory, package sizing, and allergen declarations).

This blueprint provides:
1. **Dual-Engine Architecture Comparison**: Real-time OLTP serving via **AlloyDB for PostgreSQL** with **AlloyDB AI (`pgvector` + Google ScaNN index + Hybrid BM25/FTS search)** versus batch/analytical orchestration via **BigQuery Vector Search (`VECTOR_SEARCH` + `text-embedding-005`)**.
2. **Exact PostgreSQL SDL/DDL Schemas for AlloyDB**: Production-ready definitions for `recipes`, `mercadona_products`, `recipe_product_mappings`, and a unified **Hybrid Search SQL function** implementing Reciprocal Rank Fusion (RRF) and weighted Cosine similarity + `ts_rank_cd`.
3. **BigQuery ML Embedding Generation & Vector Search**: Production queries for `ML.GENERATE_EMBEDDING` with `text-embedding-005`, batch matching with `VECTOR_SEARCH`, and automated sync pipelines.
4. **End-to-End Culinary RAG Pipeline**: Step-by-step resolution from Cookidoo ingredient text to Mercadona SKUs with **pantry subtraction**, **dietary & allergen filtering (14 EU allergens)**, **pack-size/unit conversion**, and **substitutability ranking**.
5. **Zero-Trust Enterprise Network & Security Topology**: Cloud Run microservice configuration using **Private Service Connect (PSC)**, **Direct VPC Egress**, **AlloyDB Auth Proxy sidecar container**, and least-privilege IAM (`roles/alloydb.client`, `alloydbiamuser`).

---

## 1. Architectural Comparison & Dual-Engine Blueprint

### 1.1 Dual-Engine Strategy: Hot Path (AlloyDB) vs Analytical Path (BigQuery)

| Dimension | Hot Path: AlloyDB for PostgreSQL (AlloyDB AI) | Analytical / Batch Path: BigQuery Vector Search |
| :--- | :--- | :--- |
| **Primary Workload** | Interactive API requests, live menu generation, 1-click cart assembly, user pantry filtering, and low-latency transactional serving. | Nightly batch catalog embedding, cross-catalog matrix recalculations, drift analysis, recommendation training, and enterprise reporting. |
| **Latency SLA** | **< 15 ms** index scan; **< 60 ms** end-to-end hybrid query execution. | **1.5 s – 5.0 s** per query (managed slot architecture optimized for massive scans). |
| **Throughput / Concurrency** | High concurrency (1,000+ QPS) with connection pooling and AlloyDB read pool autoscaling. | High data parallelism, batch analytical jobs, periodic cron triggers. |
| **Vector Index Type** | **ScaNN (Scalable Nearest Neighbors)** via `alloydb_scann` extension (up to 4x QPS and 3x faster index build than HNSW/IVFFlat). | **IVF (Inverted File)** vector index built natively on BigQuery columns. |
| **Lexical Search (BM25 / FTS)** | Native PostgreSQL `tsvector` / `tsquery` with Spanish dictionaries (`spanish` snowball stemmer) and GIN indexes. | BigQuery Search indexes (`SEARCH()` function) across text columns. |
| **Hybrid Fusion Method** | **Reciprocal Rank Fusion (RRF)** or linear weighted normalization inside PostgreSQL SQL/PLpgSQL functions. | BigQuery SQL queries joining vector distance ranking with `SEARCH_SCORE` rank. |
| **Cost Profile** | Continuous compute (vCPU/RAM hourly billing for Primary + Read Pool instances). | Serverless consumption-based billing ($6.25 per TB scanned or BigQuery Editions slot reservations). |
| **Data Freshness** | Real-time (immediate ACID updates upon Mercadona price or warehouse availability changes). | Near real-time to periodic (streaming ingest or scheduled Dataform/Cloud Composer sync). |

```
                                  +-------------------------------------------------+
                                  |            Cloud Run Microservice               |
                                  |         (mercadona-ai-companion)                |
                                  +-------------------------------------------------+
                                           |                                |
                   Interactive Hot Path    |                                |  Batch & Analytics
                  (< 50ms User Latency)    |                                |  (Nightly Sync / Heavy BI)
                                           v                                v
                   +----------------------------------+          +----------------------------------+
                   |    AlloyDB for PostgreSQL        |          |      Google BigQuery             |
                   |        (AlloyDB AI)              |          |      (Vector Search)             |
                   | - pgvector + ScaNN Index         |  CDC /   | - ML.GENERATE_EMBEDDING          |
                   | - Spanish FTS (tsvector)         |  Datastream - text-embedding-005            |
                   | - Hybrid RRF / Score Fusion      |--------->| - VECTOR_SEARCH()                |
                   | - ACID Product Inventory & Carts |          | - Cross-catalog matrix analysis  |
                   | - Warehouse (wh) availability    |          | - Offline evaluation & reporting |
                   +----------------------------------+          +----------------------------------+
```

### 1.2 AlloyDB AI & ScaNN Index Optimization

AlloyDB AI introduces Google's proprietary **ScaNN (Scalable Nearest Neighbors)** algorithm directly into the PostgreSQL engine:
- **Index Type**: `scann`
- **Distance Metric**: `cosine` or `l2` (for 768-dimensional normalized embeddings generated by `text-embedding-005`, `cosine` and `inner_product` yield identical ranking, with `inner_product` providing highest instruction efficiency).
- **Partitioning & Quantization**: ScaNN uses vector quantization and anisotropic vector quantization, compressing vectors to fit entirely in the database cache while preserving recall > 95%.

---

## 2. Exact PostgreSQL SDL/DDL Schemas for AlloyDB

### 2.1 Database Initialization & Extension Configuration

```sql
-- Connect to primary AlloyDB instance as administrative user
-- Extensions required: vector (pgvector), alloydb_scann (Google ScaNN), pg_trgm (trigram matching)
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "alloydb_scann";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- Custom Spanish text search configuration ignoring accents
CREATE TEXT SEARCH CONFIGURATION spanish_unaccent (COPY = spanish);
ALTER TEXT SEARCH CONFIGURATION spanish_unaccent
    ALTER MAPPING FOR hword, hword_part, word
    WITH unaccent, spanish_stem;
```

### 2.2 Table Schemas

```sql
-- 1. Cookidoo Recipes Table
CREATE TABLE IF NOT EXISTS recipes (
    id VARCHAR(64) PRIMARY KEY,                  -- e.g. 'r123456'
    title VARCHAR(255) NOT NULL,
    clean_description TEXT,
    source VARCHAR(32) DEFAULT 'cookidoo',
    minutes INT NOT NULL DEFAULT 30,
    calories_per_serving INT NOT NULL DEFAULT 350,
    servings INT NOT NULL DEFAULT 4,
    ingredients JSONB NOT NULL,                   -- Array of {raw: string, name: string, quantity: float, unit: string, optional: bool}
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,     -- Array of preparation instructions
    dietary_flags JSONB NOT NULL DEFAULT '{}'::jsonb, -- {"gluten_free": true, "dairy_free": false, "vegan": false}
    embedding vector(768) NOT NULL,              -- text-embedding-005 generated representation
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Mercadona Product Catalog Table
CREATE TABLE IF NOT EXISTS mercadona_products (
    id VARCHAR(64) PRIMARY KEY,                  -- Mercadona item ID (e.g. '3400')
    ean VARCHAR(32) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    brand VARCHAR(128) DEFAULT 'Hacendado',
    category VARCHAR(128) NOT NULL,
    subcategory VARCHAR(128),
    price NUMERIC(10, 2) NOT NULL,
    unit_price NUMERIC(10, 2),
    unit_size VARCHAR(64),                        -- e.g. '1 kg', 'Pack 6 x 100 g'
    package_type VARCHAR(64),                     -- 'tray', 'bottle', 'brick', 'bag'
    net_weight_grams NUMERIC(10, 2),              -- Normalized weight in grams for pack calculation
    is_approx_size BOOLEAN DEFAULT FALSE,
    share_url TEXT,
    thumbnail_url TEXT,
    warehouses TEXT[] NOT NULL DEFAULT '{mad3}',  -- Array of warehouse codes where SKU is in stock
    allergen_tags JSONB NOT NULL DEFAULT '{}'::jsonb, -- {"gluten": false, "crustaceans": false, "milk": true}
    embedding vector(768) NOT NULL,              -- text-embedding-005 generated representation
    fts_tokens tsvector GENERATED ALWAYS AS (
        to_tsvector('spanish_unaccent', coalesce(display_name, '') || ' ' || coalesce(category, '') || ' ' || coalesce(brand, ''))
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Cache & Grounding Mapping Table (Recipe Ingredient -> Mercadona SKU)
CREATE TABLE IF NOT EXISTS recipe_product_mappings (
    id BIGSERIAL PRIMARY KEY,
    recipe_id VARCHAR(64) REFERENCES recipes(id) ON DELETE CASCADE,
    ingredient_name VARCHAR(255) NOT NULL,
    product_id VARCHAR(64) REFERENCES mercadona_products(id) ON DELETE RESTRICT,
    confidence_score NUMERIC(5, 4) NOT NULL,      -- Matching confidence (0.0000 - 1.0000)
    match_strategy VARCHAR(32) NOT NULL,          -- 'exact', 'hybrid_scann', 'llm_validated'
    substitutable BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_recipe_ingredient UNIQUE (recipe_id, ingredient_name, product_id)
);
```

### 2.3 Indexes for High-QPS Hybrid Retrieval

```sql
-- AlloyDB ScaNN Index on Mercadona Products (Cosine distance)
-- num_leaves: ~4 * sqrt(15,000) ~= 500; quantizer: sq8
CREATE INDEX IF NOT EXISTS idx_mercadona_products_scann
ON mercadona_products
USING scann (embedding vector_cosine_ops)
WITH (num_leaves = 500, quantizer = 'sq8');

-- AlloyDB ScaNN Index on Recipes
CREATE INDEX IF NOT EXISTS idx_recipes_scann
ON recipes
USING scann (embedding vector_cosine_ops)
WITH (num_leaves = 300, quantizer = 'sq8');

-- Full-Text Search GIN Index
CREATE INDEX IF NOT EXISTS idx_mercadona_products_fts
ON mercadona_products
USING gin (fts_tokens);

-- Trigram Index for fuzzy typo-tolerant ingredient matching
CREATE INDEX IF NOT EXISTS idx_mercadona_products_trgm
ON mercadona_products
USING gin (display_name gin_trgm_ops);

-- B-Tree Indexes on Warehouse and Filter Columns
CREATE INDEX IF NOT EXISTS idx_mercadona_products_warehouses
ON mercadona_products
USING gin (warehouses);

CREATE INDEX IF NOT EXISTS idx_mercadona_products_category
ON mercadona_products (category);
```

### 2.4 Hybrid Search SQL Function: Reciprocal Rank Fusion (RRF) & Weighted Scoring

```sql
CREATE OR REPLACE FUNCTION match_mercadona_products_hybrid(
    query_text TEXT,
    query_embedding vector(768),
    warehouse_code TEXT DEFAULT 'mad3',
    excluded_allergens TEXT[] DEFAULT '{}',
    match_limit INT DEFAULT 5,
    vector_weight FLOAT DEFAULT 0.65,
    fts_weight FLOAT DEFAULT 0.35,
    rrf_k INT DEFAULT 60
)
RETURNS TABLE (
    product_id VARCHAR(64),
    display_name VARCHAR(255),
    brand VARCHAR(128),
    category VARCHAR(128),
    price NUMERIC(10, 2),
    unit_size VARCHAR(64),
    vector_similarity FLOAT,
    fts_rank FLOAT,
    hybrid_score FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH vector_candidates AS (
        SELECT 
            p.id,
            1.0 - (p.embedding <=> query_embedding) AS sim,
            ROW_NUMBER() OVER (ORDER BY p.embedding <=> query_embedding ASC) AS v_rank
        FROM mercadona_products p
        WHERE p.warehouses @> ARRAY[warehouse_code]
          AND NOT (p.allergen_tags ?| excluded_allergens)
        ORDER BY p.embedding <=> query_embedding ASC
        LIMIT 50
    ),
    fts_candidates AS (
        SELECT 
            p.id,
            ts_rank_cd(p.fts_tokens, plainto_tsquery('spanish_unaccent', query_text)) AS rank,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(p.fts_tokens, plainto_tsquery('spanish_unaccent', query_text)) DESC
            ) AS f_rank
        FROM mercadona_products p
        WHERE p.fts_tokens @@ plainto_tsquery('spanish_unaccent', query_text)
          AND p.warehouses @> ARRAY[warehouse_code]
          AND NOT (p.allergen_tags ?| excluded_allergens)
        ORDER BY rank DESC
        LIMIT 50
    ),
    combined AS (
        SELECT 
            COALESCE(vc.id, fc.id) AS id,
            COALESCE(vc.sim, 0.0) AS sim,
            COALESCE(fc.rank, 0.0) AS rank,
            -- Reciprocal Rank Fusion (RRF) combined with linear feature weighting
            (COALESCE(1.0 / (rrf_k + vc.v_rank), 0.0) * vector_weight) +
            (COALESCE(1.0 / (rrf_k + fc.f_rank), 0.0) * fts_weight) AS score
        FROM vector_candidates vc
        FULL OUTER JOIN fts_candidates fc ON vc.id = fc.id
    )
    SELECT 
        p.id AS product_id,
        p.display_name,
        p.brand,
        p.category,
        p.price,
        p.unit_size,
        c.sim::FLOAT AS vector_similarity,
        c.rank::FLOAT AS fts_rank,
        c.score::FLOAT AS hybrid_score
    FROM combined c
    JOIN mercadona_products p ON p.id = c.id
    ORDER BY c.score DESC
    LIMIT match_limit;
END;
$$;
```

---

## 3. BigQuery ML Embedding Generation & Vector Search

BigQuery Vector Search provides managed vector index support and direct integration with Vertex AI Foundation models via BigQuery ML.

### 3.1 BigQuery Connection & Model Setup

```sql
-- Step 1: Create BigQuery Cloud Resource Connection
-- Run via bq CLI or Cloud Console:
-- bq mk --connection --location=EU --project_id=mercadona-companion-prod --connection_type=CLOUD_RESOURCE vertex-ai-conn

-- Step 2: Grant Vertex AI User to Connection Service Agent
-- gcloud projects add-iam-policy-binding mercadona-companion-prod \
--     --member="serviceAccount:bqcx-XXXXXX@gcp-sa-bigquery-condel.iam.gserviceaccount.com" \
--     --role="roles/aiplatform.user"

-- Step 3: Define remote embedding model in BigQuery
CREATE OR REPLACE MODEL `mercadona_catalog.text_embedding_model`
REMOTE WITH CONNECTION `EU.vertex-ai-conn`
OPTIONS (ENDPOINT = 'text-embedding-005');
```

### 3.2 Product Embedding Generation Query (`ML.GENERATE_EMBEDDING`)

```sql
-- Generate 768-dim embeddings for all Mercadona products
CREATE OR REPLACE TABLE `mercadona_catalog.mercadona_products_embedded` AS
SELECT 
    id,
    ean,
    display_name,
    category,
    price,
    unit_size,
    ml_generate_embedding_result AS embedding
FROM ML.GENERATE_EMBEDDING(
    MODEL `mercadona_catalog.text_embedding_model`,
    (
        SELECT 
            id,
            ean,
            display_name,
            category,
            price,
            unit_size,
            CONCAT(
                'Producto de supermercado: ', display_name, 
                '. Categoría: ', category, 
                '. Formato: ', coalesce(unit_size, 'estándar')
            ) AS content
        FROM `mercadona_catalog.mercadona_products_raw`
    ),
    STRUCT(TRUE AS flatten_json_output, 'SEMANTIC_SIMILARITY' AS task_type, 768 AS output_dimensionality)
);
```

### 3.3 BigQuery Vector Index Creation

```sql
-- Create an Inverted File (IVF) index on the embedding column
CREATE VECTOR INDEX IF NOT EXISTS product_embedding_idx
ON `mercadona_catalog.mercadona_products_embedded`(embedding)
OPTIONS (
    index_type = 'IVF',
    distance_type = 'COSINE',
    ivf_options = '{"num_lists": 256}'
);
```

### 3.4 Batch Recipe-to-Catalog Vector Search (`VECTOR_SEARCH`)

```sql
-- Match Cookidoo recipe ingredients against the entire Mercadona catalog in batch
WITH recipe_ingredients_embedded AS (
    SELECT 
        r.id AS recipe_id,
        r.title AS recipe_title,
        ing.name AS ingredient_name,
        emb.ml_generate_embedding_result AS ingredient_embedding
    FROM `mercadona_catalog.recipes_raw` r,
    UNNEST(r.ingredients) AS ing
    CROSS JOIN ML.GENERATE_EMBEDDING(
        MODEL `mercadona_catalog.text_embedding_model`,
        (SELECT CONCAT('Ingrediente culinario: ', ing.name) AS content),
        STRUCT(TRUE AS flatten_json_output, 'RETRIEVAL_QUERY' AS task_type, 768 AS output_dimensionality)
    ) emb
)
SELECT 
    query.recipe_id,
    query.recipe_title,
    query.ingredient_name,
    base.id AS matched_product_id,
    base.display_name AS matched_product_name,
    base.price AS product_price,
    1.0 - distance AS cosine_similarity
FROM VECTOR_SEARCH(
    TABLE `mercadona_catalog.mercadona_products_embedded`,
    'embedding',
    TABLE recipe_ingredients_embedded,
    'ingredient_embedding',
    top_k => 3,
    distance_type => 'COSINE',
    options => '{"fraction_lists_to_search": 0.15}'
);
```

---

## 4. End-to-End RAG Pipeline for Recipe-to-Product Mapping

The runtime pipeline bridges culinary descriptions with physical supermarket purchasing:

```
[Cookidoo Recipe] 
   --> 1. Ingredient Extraction & Entity Normalization (Quantities, Units, Stems)
   --> 2. User Pantry Inventory Subtraction (Match & Deduct known staples)
   --> 3. Dietary & Allergen Constraint Validation (14 EU Allergens Gating)
   --> 4. Hybrid Search Query Generation (Vector Embedding + Spanish FTS)
   --> 5. AlloyDB ScaNN + BM25 Candidate Retrieval (Top 5 items / warehouse)
   --> 6. Pack-Size Sizing & Unit Conversion (Calculate required integer packages)
   --> 7. Substitution & Price Optimizer (Gemini 3.8 Flash structured adjudication)
   --> [Mercadona 1-Click Cart Ready]
```

### 4.1 Step 1: Ingredient Extraction & Entity Normalization
Cookidoo ingredients often contain cooking preparation notes (e.g., *"300 g de pechuga de pollo cortada en dados de 2 cm"*).
- The pipeline strips culinary preparation clauses using deterministic regex and Spanish POS tokenization:
  - Raw: `"300 g de pechuga de pollo cortada en dados de 2 cm"`
  - Normalized Entity: `"pechuga de pollo"`
  - Parsed Quantity: `300.0`, Unit: `"grams"`.

### 4.2 Step 2: User Pantry Inventory Subtraction
The system compares normalized entities against the user's active pantry inventory (`user_pantry` table or local session storage):
- If the user has `"pechuga de pollo"` in stock with remaining quantity $\ge 300\text{ g}$, the item is marked as `IN_PANTRY` and omitted from the final purchase cart.
- If pantry quantity is partial (e.g., $100\text{ g}$ available), the required cart quantity is adjusted ($200\text{ g}$ remaining).
- Basic pantry staples (salt, water, basic olive oil) are checked against a standard threshold flag.

### 4.3 Step 3: Dietary & Allergen Constraint Enforcement
Strict gating against the **14 EU Regulated Allergens**:
1. Gluten, 2. Crustaceans, 3. Eggs, 4. Fish, 5. Peanuts, 6. Soybeans, 7. Milk/Lactose, 8. Nuts, 9. Celery, 10. Mustard, 11. Sesame seeds, 12. Sulphites, 13. Lupin, 14. Molluscs.
- Any Mercadona candidate SKU containing `allergen_tags ? user_allergen_key` is hard-filtered at the SQL query level before candidate scoring.
- If no direct allergen-free match exists, the pipeline triggers a certified gluten-free or lactose-free substitution lookup (e.g., `"pasta sin gluten Hacendado"` SKU `35777`).

### 4.4 Step 4 & 5: Hybrid Retrieval Execution
- Generates 768-dim query embedding using Vertex AI `text-embedding-005`.
- Calls `match_mercadona_products_hybrid(normalized_name, query_vector, user_warehouse, excluded_allergens, 5)`.
- AlloyDB returns top 5 candidate SKUs with Cosine Similarity, FTS Rank, and RRF Hybrid Score.

### 4.5 Step 6: Pack-Size & Unit Optimization Logic
Supermarket products are sold in discrete packages (e.g., tray of $500\text{ g}$, brick of $1\text{ L}$, pack of $6\text{ eggs}$).
- Formula for quantity calculation:
  $$\text{Units to Buy} = \left\lceil \frac{\text{Required Recipe Quantity}}{\text{Net Weight per Package}} \right\rceil$$
- Example: Recipe calls for $300\text{ g}$ of chicken breast. Mercadona SKU `3400` has `net_weight_grams = 500`. Required units = $\lceil 300 / 500 \rceil = 1$ tray. Excess ($200\text{ g}$) is recorded for weekly meal reuse.

### 4.6 Step 7: LLM Grounding & Validation Loop
For ambiguous matches (where hybrid score $< 0.82$), candidate products and the ingredient requirement are submitted to Gemini 3.8 Flash with JSON schema output enforcement:
```json
{
  "ingredient": "tomate triturado",
  "selected_sku": "16044",
  "match_confidence": 0.98,
  "is_substitute": false,
  "reasoning": "Exact match for canned crushed tomato Hacendado 400g"
}
```

---

## 5. Enterprise Network, PSC, and AlloyDB Auth Proxy Sidecar Configuration

To ensure strict zero-trust security and complete network isolation without exposing database endpoints to the public internet:

### 5.1 Network Architecture Principles
- **No Public IP**: The AlloyDB cluster is provisioned strictly with **Private IP**.
- **Private Service Connect (PSC)**: Recommended over Private Services Access (PSA) for modern multi-VPC designs, preventing IP space overlapping and simplifying service attachments.
- **Serverless VPC Access / Direct VPC Egress**: Configured on Cloud Run (`mercadona-ai-companion`) so container traffic routes directly into the VPC network without leaving the Google backbone.
- **Sidecar Auth Proxy**: Cloud Run multi-container pattern runs `alloydb-auth-proxy` alongside the Python API container, enabling mutual TLS (mTLS) with ephemeral certificates and automatic rotation.
- **Least-Privilege IAM Authentication**: Cloud Run service account is granted `roles/alloydb.client` and database user role `alloydbiamuser`. Static passwords are removed.

### 5.2 IAM Roles & Service Account Provisioning

```bash
# 1. Create dedicated Cloud Run service account
gcloud iam service-accounts create sa-mercadona-api \
    --description="Service account for Mercadona AI Companion Cloud Run" \
    --display-name="Mercadona API Runner"

# 2. Grant least-privilege connection role (roles/alloydb.client)
# WARNING: Never grant roles/alloydb.admin to runtime service accounts!
gcloud projects add-iam-policy-binding mercadona-companion-prod \
    --member="serviceAccount:sa-mercadona-api@mercadona-companion-prod.iam.gserviceaccount.com" \
    --role="roles/alloydb.client"

# 3. Grant serviceUsageConsumer for Google APIs
gcloud projects add-iam-policy-binding mercadona-companion-prod \
    --member="serviceAccount:sa-mercadona-api@mercadona-companion-prod.iam.gserviceaccount.com" \
    --role="roles/serviceusage.serviceUsageConsumer"

# 4. Register the IAM Database User in AlloyDB
# Note: IAM database users cannot be created using standard SQL alone!
# They MUST be registered via the control plane first:
gcloud alloydb users create sa-mercadona-api@mercadona-companion-prod.iam \
    --cluster=mercadona-alloydb-cluster \
    --region=europe-west1 \
    --type=IAM_USER

# 5. Connect to AlloyDB via psql as postgres administrator to grant database privileges
# Standard PostgreSQL roles and privileges apply:
# GRANT ALL PRIVILEGES ON DATABASE mercadona_db TO "sa-mercadona-api@mercadona-companion-prod.iam";
# GRANT alloydbiamuser TO "sa-mercadona-api@mercadona-companion-prod.iam";
```

### 5.3 Cloud Run Multi-Container Service Specification (`service.yaml`)

This declarative YAML deploys the application and the AlloyDB Auth Proxy as a co-located sidecar container with Direct VPC Egress:

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: mercadona-ai-companion
  namespace: 'mercadona-companion-prod'
  annotations:
    run.googleapis.com/launch-stage: BETA
    run.googleapis.com/ingress: all
spec:
  template:
    metadata:
      annotations:
        # Enforce Direct VPC Egress routing all traffic through the private subnet
        run.googleapis.com/network-interfaces: '[{"network":"default","subnetwork":"cloud-run-subnet"}]'
        run.googleapis.com/vpc-access-egress: all-traffic
        autoscaling.knative.dev/minScale: "1"
        autoscaling.knative.dev/maxScale: "20"
    spec:
      serviceAccountName: sa-mercadona-api@mercadona-companion-prod.iam.gserviceaccount.com
      containers:
        # Container 1: Application Web Service
        - name: app
          image: europe-west1-docker.pkg.dev/mercadona-companion-prod/companion-repo/api:latest
          ports:
            - containerPort: 8080
          env:
            - name: DB_HOST
              value: "127.0.0.1"          # Connects locally to the Auth Proxy sidecar
            - name: DB_PORT
              value: "5432"
            - name: DB_NAME
              value: "mercadona_db"
            - name: DB_USER
              value: "sa-mercadona-api@mercadona-companion-prod.iam"
            - name: USE_IAM_AUTH
              value: "true"
            - name: GEMINI_MODEL
              value: "gemini-3.8-flash"
          resources:
            limits:
              cpu: "2"
              memory: "2Gi"
          startupProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5

        # Container 2: AlloyDB Auth Proxy Sidecar
        - name: alloydb-auth-proxy
          image: gcr.io/alloydb-connectors/alloydb-auth-proxy:latest
          args:
            # Format: projects/<PROJECT>/locations/<REGION>/clusters/<CLUSTER>/instances/<INSTANCE>
            - "projects/mercadona-companion-prod/locations/europe-west1/clusters/mercadona-alloydb-cluster/instances/mercadona-primary"
            - "--address=127.0.0.1"
            - "--port=5432"
            - "--auto-iam-authn"           # Enables automatic OAuth token injection for IAM user
            - "--structured-logging"
          resources:
            limits:
              cpu: "1"
              memory: "512Mi"
          restartPolicy: Always
```

---

## 6. Implementation & Operational Recommendations

1. **Read Pool Autoscaling**: For high seasonal demand (e.g., holiday grocery spikes), enable **read pool autoscaling** (currently in Preview) on the AlloyDB cluster to dynamically handle vector query bursts without manual provisioning.
2. **Discrete Backup Management**: Ensure automated daily backups are configured. Note that discrete backups in AlloyDB exist independently of the source cluster and remain intact even if the primary instance or cluster is deleted.
3. **Continuous Accuracy Audits**: Schedule nightly BigQuery jobs comparing the AlloyDB candidate mappings with user checkout conversions to identify false positive product matches and automatically calibrate the RRF parameter weights ($k=60$, vector weight $0.65$, FTS weight $0.35$).
