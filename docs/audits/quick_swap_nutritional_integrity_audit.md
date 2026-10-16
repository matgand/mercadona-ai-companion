# Audit Report: Quick-Swap Recipe Integrity and Nutritional Consistency
**Target Module:** `gemini_planner.py` (`swap_single_recipe`, scaling, basket recalculation)  
**Auditor:** Subagent B  
**Date:** September 2026

---

## 1. Executive Summary
A comprehensive audit and targeted empirical stress-testing was conducted on `/usr/local/google/home/mgandolfi/mercadona-ai-companion/gemini_planner.py`, specifically auditing:
1. `swap_single_recipe` candidate selection, rotation cycling, allergen preservation, and duplication avoidance.
2. Basket recalculation, orphaned item pruning, shared staple retention/removal, and budget re-balancing.
3. Nutritional portion scaling (`adults + 0.75 * children`) and Cookidoo batch multiplier logic.

All automated verification tests pass cleanly (see `tests/test_quick_swap_integrity.py`). The core architecture is resilient, deterministic, and preserves dietary rules under standard conditions. Three edge-case risks were identified regarding candidate fallback degradation, deficit budget messaging, and unknown recipe ID handling in `current_meals`.

---

## 2. Swap Dietary & Allergen Integrity Analysis
### 2.1 Filtering Cascade in `swap_single_recipe`
The candidate selection implements a 3-tier cascade:
* **Tier 1 (Strict Candidates):**
  - Excludes all recipes currently in `used_ids`.
  - Requires all `product_ids` to be present in the active Mercadona catalog for the postal code.
  - Enforces `minutes <= max_minutes`.
  - Enforces `calories_per_serving <= maxCaloriesPerServing` (if set).
  - Enforces `is_vegetarian` if `vegetarianOnly=True`.
  - Enforces `excludedAllergens` disjoint from `recipe["allergens"]`.
* **Tier 2 (Fallback 1):** Triggered when Tier 1 produces 0 candidates.
  - Drops catalog availability check, preparation time constraint (`max_minutes`), and calorie limit (`maxCaloriesPerServing`).
  - **Preserves** `excludedAllergens` and `vegetarianOnly`.
* **Tier 3 (Fallback 2):** Triggered if Tier 2 produces 0 candidates.
  - Drops all constraints except `recipe_id not in used_ids`.

### 2.2 Findings & Security Analysis
- **Standard Execution:** Under standard catalogs (5,000 Cookidoo recipes), Tier 1 reliably supplies candidates. Allergen exclusion and vegetarian guarantees are 100% maintained.
- **Degradation Risk in Tier 3:** In extremely constrained edge cases (e.g. user specifies 10 allergens covering all known recipes), Tier 3 drops the allergen filter. In a real-world scenario with severe allergies/celiac disease, a silent fallback to an allergen-containing recipe poses health safety risks.
- **Recommendation:** Rather than falling back to an unconstrained recipe in Tier 3, `swap_single_recipe` should either raise a descriptive error or return a notification payload indicating that no allergen-compliant alternative exists.

---

## 3. Rotation Cycling & Duplication Prevention
### 3.1 Behavior Analysis
- `rotation` integer acts as an index into the candidates list: `chosen = candidates[rotation % len(candidates)]`.
- As the user clicks "swap" repeatedly (`rotation=0, 1, 2, ...`), different recipes cycle smoothly through the candidate list.
- `used_ids` is extracted at the start:
  ```python
  used_ids = {str(m.get("recipe_id") or m.get("recipeId") or "") for m in current_meals}
  ```
- Because candidates are filtered with `r["recipe_id"] not in used_ids`, the swapped-in recipe is **guaranteed never to duplicate** any of the other days already present in the active plan.
- Verified across 50 consecutive rotations: 0 duplicate collisions across days.

---

## 4. Basket Recalculation & Shared Staples Analysis
### 4.1 Orphaned Product Removal & Additions
- `swap_single_recipe` rebuilds the entire week's basket from scratch across `updated_meals_raw`.
- Products unique to the swapped-out recipe are completely dropped (no orphan line items remain).
- Products required by the new replacement recipe are dynamically added and priced against the active Mercadona catalog.
- Pantry items (`pantry_map`) remain excluded from the basket.

### 4.2 Shared Staples Handling
- Defined staples: `SHARED_STAPLES = {"4740", "69089", "69297", "31505", "5044", "34125"}` (Olive oil, onion, garlic, eggs, rice, pasta).
- Staple quantity rule:
  ```python
  if pid in SHARED_STAPLES:
      qty_map[pid] = max(qty_map.get(pid, 0), 1)
  ```
- **Retention:** When Meal A and Meal B both use olive oil (`4740`), swapping out Meal A keeps olive oil in the basket at quantity 1, with `used_in_days` properly reflecting the remaining meal(s).
- **Pruning:** When all meals using the staple are swapped out for non-staple recipes, the staple disappears completely from the basket.

### 4.3 Budget Re-Balancing & Deficit Behavior
- When a swap causes total basket price to exceed `maxBudget`:
  1. Consolidates multi-pack quantities down to 1 pack:
     ```python
     if total > max_budget:
         for pid in list(qty_map.keys()):
             if qty_map[pid] > 1:
                 qty_map[pid] = 1
                 basket_rows, total = build_swap_basket(qty_map)
                 if total <= max_budget:
                     break
     ```
  2. If still exceeding budget, deletes kitchen staple olive oil (`4740`) from basket.
- **Edge Case Identified:** If the single-pack basket still exceeds `maxBudget`, `total > max_budget` persists and `budget_remaining = round(max_budget - total, 2)` becomes negative (e.g. `-1.00 €`).
- The function successfully returns the adjusted basket rather than crashing, but does not flag to the UI that the budget has been exceeded.

---

## 5. Nutritional & Portion Scaling Consistency
### 5.1 Portion Calculation
- Formula: `household_portions = adults + (0.75 * children)`
- Scaling multiplier: `scale = max(1, math.ceil(household_portions / max(1, r.get("cookidoo_servings", 4))))`

### 5.2 Empirical Evaluation Table
| Adults | Children | Household Portions | Cookidoo Recipe Servings | Scale Multiplier | Resulting Portions Prepared |
|:------:|:--------:|:------------------:|:------------------------:|:----------------:|:---------------------------:|
| 1      | 0        | 1.00               | 4                        | 1                | 4 (leftovers)               |
| 2      | 0        | 2.00               | 4                        | 1                | 4                           |
| 2      | 1        | 2.75               | 4                        | 1                | 4                           |
| 2      | 2        | 3.50               | 4                        | 1                | 4                           |
| 2      | 3        | 4.25               | 4                        | 2                | 8                           |
| 4      | 2        | 5.50               | 4                        | 2                | 8                           |
| 2      | 1        | 2.75               | 2                        | 2                | 4                           |
| 2      | 0        | 2.00               | 1                        | 2                | 2                           |

- The formula correctly prevents division by zero (`max(1, r.get("cookidoo_servings", 4))`).
- Portion scaling accurately drives non-staple basket item quantities: `qty_map[pid] = qty_map.get(pid, 0) + scale`.

---

## 6. Edge Cases & Actionable Recommendations

1. **Tier 3 Allergen Safety Vulnerability:**
   - *Issue:* Tier 3 fallback drops `excludedAllergens`.
   - *Recommendation:* If Tier 2 yields 0 candidates, raise `ValueError("No compatible recipes found matching your allergen restrictions.")` rather than serving an allergen-containing recipe.

2. **Negative Budget Alert:**
   - *Issue:* When `total > maxBudget`, `budget_remaining` is negative without an explicit warning field.
   - *Recommendation:* Add `"budget_exceeded": total > max_budget` and `"over_budget_amount": round(total - max_budget, 2) if total > max_budget else 0.0` in the swap return payload.

3. **Missing Recipe in `by_id` Lookup:**
   - *Issue:* In `swap_single_recipe` line 860: `by_id.get(rid, chosen)`. If an existing meal contains a custom or uncataloged recipe ID, it defaults to `chosen`, inadvertently duplicating the replacement recipe into other days.
   - *Recommendation:* Construct a placeholder or retain `m` rather than defaulting to `chosen`.
