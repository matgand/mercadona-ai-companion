# Subagent B Audit Report: Malformed Payload and Input Fuzzing for `campaign_service.py`

**Target Component**: `campaign_service.py` (Mercadona Marketing Campaign Library)  
**Auditor**: Subagent B (Malformed Payload and Input Fuzzing Auditor)  
**Date**: September 27, 2026  
**Scope**: Input validation, boundary conditions, malformed payload handling, type coercion, normalization logic, Gemini LLM response parsing, persistence resilience, and microservice sync payloads.

---

## Executive Summary

An exhaustive security, fuzzing, and boundary condition audit was conducted on `campaign_service.py`. The module is responsible for managing marketing campaign lifecycles, parsing natural-language campaign briefs via Gemini 3.8 Flash, enriching campaign records, and synchronizing state across Cloud Run microservices.

Our fuzzing tests identified **9 distinct flaws and vulnerabilities**, ranging from **High** to **Low** severity. Most critically:
1. A **single malformed record** in `data/campaigns.json` causes total campaign catalog failure (complete data blindness / denial-of-service where all campaigns disappear).
2. Unhandled numeric type casting in `_enrich_campaign` causes unhandled exceptions on standard string or float inputs (`"5.0"`, `"invalid"`).
3. Negative values (`-5` meals, `-50€` budget, `-15` minutes) bypass default guards and persist into storage.
4. Overly permissive substring matching (`"min"`) causes severe categorization collisions (e.g., `"vitaminas"` and `"dominical"` wrongly categorized as `"Rutina rápida"`).
5. Unrecognized campaign statuses in `normalize_status` silently default to `"Activa"`, creating a severe business risk where disabled or paused campaigns are published live to customers.

---

## Detailed Vulnerability & Flaw Catalog

### 1. [HIGH] Single Corrupted Item in `campaigns.json` Causes Total Campaign Service Outage (Data Blindness)

- **Location**: `campaign_service.py`, lines 160–170 (`load_local_campaigns`)
- **Code Snippet**:
  ```python
  def load_local_campaigns() -> list[dict[str, Any]]:
      with _LOCK:
          if not CAMPAIGNS_FILE.is_file():
              return []
          try:
              raw = json.loads(CAMPAIGNS_FILE.read_text(encoding="utf-8"))
              if isinstance(raw, list):
                  return [_enrich_campaign(item) for item in raw]
          except Exception:
              pass
          return []
  ```
- **Proof of Vulnerability**:
  When `load_local_campaigns()` parses `campaigns.json`, it runs a list comprehension over all items. If even **one** item out of dozens has an invalid type (such as `mealCount: "invalid"` or a non-dict element), `_enrich_campaign(item)` throws an unhandled exception (`ValueError` or `AttributeError`). The broad `except Exception:` block catches this and returns `[]`.
  - **Fuzzing Execution Result**:
    ```python
    fake_json = json.dumps([valid_campaign, {"id": "bad", "mealCount": "invalid_string"}])
    # Result: load_local_campaigns() -> []
    ```
- **Cascading Failure**:
  If an API operation or sync event triggers `save_local_campaigns([])` following this load failure, `campaigns.json` is completely overwritten with an empty array `[]`, causing **permanent data loss** of all existing campaigns.
- **Recommended Mitigation**:
  Enrich records on an item-by-item basis. Log errors for corrupted records and skip them, returning all valid records rather than dropping the entire database.

---

### 2. [HIGH] Unhandled Type Coercion Crashes in `_enrich_campaign`

- **Location**: `campaign_service.py`, lines 147–150
- **Code Snippet**:
  ```python
  "mealCount": int(c.get("mealCount") or 5),
  "maxBudget": float(c.get("maxBudget") or 60),
  "maxMinutes": int(c.get("maxMinutes") or 25),
  "maxCaloriesPerServing": int(c["maxCaloriesPerServing"]) if c.get("maxCaloriesPerServing") else None,
  ```
- **Proof of Vulnerability**:
  - **Non-numeric strings**: If `c.get("mealCount")` is `"cinco"` or `"abc"`, `int("abc")` raises `ValueError: invalid literal for int() with base 10: 'abc'`.
  - **Float strings**: If frontend or external sync sends `"5.0"` or `"25.0"` as strings, `int("5.0")` raises `ValueError: invalid literal for int() with base 10: '5.0'`.
  - **Non-dict input**: Calling `_enrich_campaign(None)` raises `AttributeError: 'NoneType' object has no attribute 'get'`.
  - **Non-scalar types**: Passing a non-empty list `mealCount=[5]` raises `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'list'`.
- **Fuzzing Test Results**:
  ```python
  _enrich_campaign({'mealCount': '5.0'})         # -> ValueError: invalid literal for int() with base 10: '5.0'
  _enrich_campaign({'maxMinutes': '25.0'})       # -> ValueError: invalid literal for int() with base 10: '25.0'
  _enrich_campaign({'maxCaloriesPerServing': '450.0'}) # -> ValueError: invalid literal for int() with base 10: '450.0'
  _enrich_campaign({'maxBudget': 'abc'})         # -> ValueError: could not convert string to float: 'abc'
  ```
- **Recommended Mitigation**:
  Implement a safe parsing helper `_safe_int(val, default, min_val, max_val)` and `_safe_float(val, default, min_val, max_val)` that safely handles strings, floats, floats-in-strings, and types without raising unhandled exceptions.

---

### 3. [MEDIUM] Boundary Violations: Negative Values and Unbounded Values Persist into Storage

- **Location**: `campaign_service.py`, lines 147–150
- **Code Snippet**:
  ```python
  "mealCount": int(c.get("mealCount") or 5),
  "maxBudget": float(c.get("maxBudget") or 60),
  "maxMinutes": int(c.get("maxMinutes") or 25),
  "maxCaloriesPerServing": int(c["maxCaloriesPerServing"]) if c.get("maxCaloriesPerServing") else None,
  ```
- **Proof of Vulnerability**:
  Because Python's `or` operator checks truthiness, negative numbers are truthy and completely bypass default fallbacks:
  - `mealCount = -5` -> `int(-5 or 5)` yields `-5`.
  - `maxBudget = -50` -> `float(-50 or 60)` yields `-50.0`.
  - `maxMinutes = -15` -> `int(-15 or 25)` yields `-15`.
  - `maxCaloriesPerServing = -500` -> `int(-500)` yields `-500`.
  - Unbounded inputs (e.g. `mealCount = 10000000000` or `maxBudget = 1e12`) are accepted without sanity clamping.
  - Zero values: Because `0` is falsy, setting `maxBudget = 0` (e.g. for a 100% zero-cost pantry campaign) is unintentionally reset to `60.0`.
- **Fuzzing Test Results**:
  ```python
  res = _enrich_campaign({'mealCount': -5, 'maxBudget': -50.0, 'maxMinutes': -10, 'maxCaloriesPerServing': -500})
  # res['mealCount']              == -5
  # res['maxBudget']              == -50.0
  # res['maxMinutes']             == -10
  # res['maxCaloriesPerServing']  == -500
  ```
- **Recommended Mitigation**:
  Clamp values to reasonable domain ranges:
  - `mealCount`: Integer between 1 and 14 (default 5)
  - `maxBudget`: Float between 10.0 and 500.0 € (default 60.0)
  - `maxMinutes`: Integer between 10 and 120 minutes (default 25)
  - `maxCaloriesPerServing`: Integer between 200 and 2000 kcal (or None)

---

### 4. [MEDIUM] Non-String Arguments to `normalize_category` and `normalize_status` Cause Unhandled `AttributeError`

- **Location**: `campaign_service.py`, lines 96–128
- **Code Snippet**:
  ```python
  def normalize_category(raw: str | None) -> str:
      if not raw:
          return "Familias"
      val = raw.strip()  # <--- CRASHES if raw is int, bool, list, dict
  ```
- **Proof of Vulnerability**:
  When `raw` is a truthy non-string (e.g., `123`, `True`), `if not raw:` evaluates to `False`. The next line calls `raw.strip()`, which immediately crashes with `AttributeError: 'int' object has no attribute 'strip'`.
- **Trigger Vectors**:
  - Gemini returns structured JSON with integer or boolean categories (e.g. `{"category": 1}`).
  - Client sends `/api/campaigns/update` with `{"category": 123}` or `{"status": 1}`.
- **Fuzzing Test Results**:
  ```python
  normalize_category(123)   # -> AttributeError: 'int' object has no attribute 'strip'
  normalize_category(True)  # -> AttributeError: 'bool' object has no attribute 'strip'
  normalize_status(123)     # -> AttributeError: 'int' object has no attribute 'strip'
  normalize_status(True)    # -> AttributeError: 'bool' object has no attribute 'strip'
  ```
- **Recommended Mitigation**:
  Add an explicit type check and coercion:
  ```python
  if not isinstance(raw, str):
      raw = str(raw) if raw is not None else ""
  ```

---

### 5. [MEDIUM] Greedy Substring Matching in `normalize_category` Causes False-Positive Classifications

- **Location**: `campaign_service.py`, line 105
- **Code Snippet**:
  ```python
  if "rapida" in low or "rápida" in low or "rutina" in low or "expres" in low or "convenience" in low or "min" in low:
      return "Rutina rápida"
  ```
- **Proof of Vulnerability**:
  The condition `"min" in low` matches any word containing the letters "min".
- **Fuzzing Execution Results**:
  - `normalize_category("vitaminas")` -> `"Rutina rápida"` (should be `"Saludables"`)
  - `normalize_category("dominical")` -> `"Rutina rápida"` (should be `"Familias"`)
  - `normalize_category("administrador")` -> `"Rutina rápida"`
  - `normalize_category("terminar")` -> `"Rutina rápida"`
  - `normalize_category("determinado")` -> `"Rutina rápida"`
- **Recommended Mitigation**:
  Replace substring `"min" in low` with regex word boundary matching: `re.search(r"\b\d+\s*min\b|\bminutos?\b", low)`.

---

### 6. [MEDIUM] Unknown Statuses Silently Default to "Activa" (Accidental Publishing Hazard)

- **Location**: `campaign_service.py`, lines 112–128 (`normalize_status`)
- **Code Snippet**:
  ```python
  def normalize_status(raw: str | None) -> str:
      if not raw:
          return "Activa"
      ...
      return "Activa"  # <--- Catch-all default
  ```
- **Proof of Vulnerability**:
  If an operator or system passes an unmapped status like `"inactiva"`, `"pausada"`, `"cancelada"`, `"deleted"`, `"pendiente"`, or `"pending"`, the function silently returns `"Activa"`.
  - When an admin attempts to deactivate a campaign via `update_campaign_record(cid, {"status": "inactiva"})`, the campaign is normalized to `"Activa"` and remains live in production.
- **Recommended Mitigation**:
  Default unrecognized or pending statuses to `"Borrador"` (Draft) or raise a validation error instead of promoting them to `"Activa"`.

---

### 7. [MEDIUM] `save_local_campaigns` and Microservice Sync Payloads Lack Structure Validation & Atomicity

- **Location**: `campaign_service.py`, lines 173–178, 226–252
- **Code Snippet**:
  ```python
  def save_local_campaigns(campaigns: list[dict[str, Any]]) -> list[dict[str, Any]]:
      enriched = [_enrich_campaign(c) for c in campaigns]
      with _LOCK:
          DATA_DIR.mkdir(parents=True, exist_ok=True)
          CAMPAIGNS_FILE.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
      return enriched
  ```
- **Proof of Vulnerability**:
  - If `campaigns` is not a list (e.g. `None` or `{"id": "c1"}`), it throws `TypeError` or `AttributeError`.
  - Direct file overwriting with `CAMPAIGNS_FILE.write_text()` is not atomic. If the Cloud Run instance experiences a SIGKILL, container scale-down, or I/O failure during `write_text()`, the JSON file will be corrupted or left as a 0-byte file.
  - In `push_sync_to_peer_services`, if any object contains non-JSON-serializable data, `json.dumps()` raises an unhandled `TypeError`.
- **Recommended Mitigation**:
  1. Validate that input is a list of dictionaries before processing.
  2. Implement atomic file writes using a temporary file in the same directory followed by `os.replace`.

---

### 8. [LOW] Missing XSS / Script Sanitization on Free-Form Text Fields

- **Location**: `campaign_service.py`, lines 136–157, 405–445
- **Proof of Vulnerability**:
  Inputs from Gemini or client update requests containing HTML tags (e.g., `<script>alert(1)</script>`, `<img src=x onerror=alert(1)>`) are passed directly through `str(c.get("title"))`, `str(c.get("badge"))`, etc.
  While backend JSON persistence is safe from SQLi/command injection, if frontend templates render these campaign fields without HTML escaping (e.g. using `v-html`, `[innerHTML]`, or unescaped Jinja/template literals), Stored Cross-Site Scripting (XSS) will trigger in the marketing portal.
- **Recommended Mitigation**:
  Sanitize or strip HTML tags from editorial fields (`title`, `tagline`, `badge`, `whyProfile`) using `html.escape` or regex tag stripping upon ingestion.

---

### 9. [LOW] Missing Maximum Length Limit on Campaign Brief Inputs

- **Location**: `campaign_service.py`, lines 368–374 (`generate_campaign_from_brief`)
- **Proof of Vulnerability**:
  While `brief.strip()` verifies that the string is non-empty and `validate_meal_planning_prompt` checks domain patterns, there is no upper-bound character limit check on `brief`. An adversarial user could pass a 10MB brief, causing excessive CPU consumption in regular expression evaluation, string allocations, and token quota exhaustion when sending payloads to Gemini.
- **Recommended Mitigation**:
  Enforce a sensible length limit (e.g., `if len(clean_brief) > 2000: raise ValueError("El brief no puede superar los 2000 caracteres.")`).

---

## Remediation & Mitigation Recommendations

Below is the concrete code patch for `campaign_service.py`:

```python
import html
import tempfile

def _safe_int(val: Any, default: int, min_val: int = 1, max_val: int = 100) -> int:
    try:
        if val is None:
            return default
        num = int(float(str(val).strip()))
        return max(min_val, min(max_val, num))
    except (ValueError, TypeError, OverflowError):
        return default

def _safe_float(val: Any, default: float, min_val: float = 0.0, max_val: float = 10000.0) -> float:
    try:
        if val is None:
            return default
        num = float(str(val).strip())
        return max(min_val, min(max_val, num))
    except (ValueError, TypeError, OverflowError):
        return default

def normalize_category(raw: Any) -> str:
    if not raw or not isinstance(raw, str):
        raw = str(raw or "").strip()
    val = raw.strip()
    if not val:
        return "Familias"
    if val in VALID_CATEGORIES:
        return val
    low = val.lower().replace("í", "i").replace("á", "a")
    if "salud" in low or "health" in low or "liger" in low or "kcal" in low or "calor" in low:
        return "Saludables"
    # Fix: Use word boundary / digits for minute check instead of substring "min"
    if "rapida" in low or "rápida" in low or "rutina" in low or "expres" in low or "convenience" in low or re.search(r"\b\d+\s*min\b|\bminutos?\b", low):
        return "Rutina rápida"
    if "ahorro" in low or "despensa" in low or "econom" in low or "barat" in low or "presupuesto" in low:
        return "Ahorro"
    return "Familias"

def normalize_status(raw: Any) -> str:
    if not raw or not isinstance(raw, str):
        raw = str(raw or "").strip()
    val = raw.strip()
    if not val:
        return "Activa"
    if val in VALID_STATUSES:
        return val
    low = val.lower()
    if low in ("activa", "active", "live", "publicada"):
        return "Activa"
    if low in ("planificada", "scheduled", "programada"):
        return "Planificada"
    if low in ("borrador", "draft", "inactiva", "pausada", "cancelada", "pending"):
        return "Borrador"
    if low in ("terminada", "completed", "archived", "finalizada", "archivada"):
        return "Terminada"
    return "Borrador"  # Safe default to Borrador rather than Activa

def load_local_campaigns() -> list[dict[str, Any]]:
    with _LOCK:
        if not CAMPAIGNS_FILE.is_file():
            return []
        try:
            raw = json.loads(CAMPAIGNS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                res: list[dict[str, Any]] = []
                for item in raw:
                    if isinstance(item, dict):
                        try:
                            res.append(_enrich_campaign(item))
                        except Exception:
                            continue  # Skip corrupt item, do not wipe entire list
                return res
        except Exception:
            pass
        return []

def save_local_campaigns(campaigns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(campaigns, list):
        return load_local_campaigns()
    enriched = [_enrich_campaign(c) for c in campaigns if isinstance(c, dict)]
    with _LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        # Atomic write pattern
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(DATA_DIR), prefix="campaigns_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(enriched, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(CAMPAIGNS_FILE))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    return enriched
```
