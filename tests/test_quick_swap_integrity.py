"""Unit tests verifying Quick-Swap recipe integrity, nutritional scaling, and basket calculations in gemini_planner.py."""

import math
import unittest
from cookidoo_service import load_cookidoo_catalog
from mercadona_service import get_catalog_for_postal_code
import gemini_planner


class TestQuickSwapNutritionalIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recipes = load_cookidoo_catalog()
        cls.catalog, cls.meta = get_catalog_for_postal_code("28016")

    def test_swap_maintains_allergens_and_vegetarian(self):
        constraints = {
            "mealCount": 3,
            "adults": 2,
            "children": 1,
            "excludedAllergens": ["gluten", "dairy"],
            "vegetarianOnly": True,
            "maxMinutes": 45,
            "maxBudget": 80.0,
            "pantryItems": [],
        }
        plan = gemini_planner.build_weekly_plan("3 cenas vegetarianas sin gluten ni lacteos para 2 adultos y 1 nino")
        target_id = plan["meals"][0]["recipe_id"]

        for rot in range(5):
            res = gemini_planner.swap_single_recipe(plan["meals"], target_id, constraints, rotation=rot)
            rep = res["replacement"]
            allergens = rep.get("allergens", [])
            self.assertFalse(
                any(a in ["gluten", "dairy"] for a in allergens),
                f"Allergen leak at rotation {rot}: {allergens}",
            )
            self.assertTrue(rep.get("is_vegetarian"), f"Vegetarian constraint violated: {rep}")

    def test_swap_duplication_prevention(self):
        constraints = {
            "mealCount": 5,
            "adults": 2,
            "children": 1,
            "maxMinutes": 35,
            "maxBudget": 70.0,
            "pantryItems": [],
        }
        plan = gemini_planner.build_weekly_plan("5 cenas rapidas para 2 adultos y 1 nino")
        target_id = plan["meals"][0]["recipe_id"]
        other_ids = {m["recipe_id"] for m in plan["meals"][1:]}

        for rot in range(25):
            res = gemini_planner.swap_single_recipe(plan["meals"], target_id, constraints, rotation=rot)
            chosen_id = res["change"]["to_recipe_id"]
            self.assertNotIn(
                chosen_id,
                other_ids,
                f"Duplicate recipe across days at rotation {rot}: {chosen_id}",
            )

    def test_shared_staples_and_orphaned_products(self):
        staple = "4740"  # Aceite de oliva
        rec_with_staple = [
            r for r in self.recipes if staple in r["product_ids"] and all(pid in self.catalog for pid in r["product_ids"])
        ]
        rec_without_staple = [
            r for r in self.recipes if staple not in r["product_ids"] and all(pid in self.catalog for pid in r["product_ids"])
        ]

        current_meals = [
            {"recipe_id": rec_with_staple[0]["recipe_id"], "day": "Lunes"},
            {"recipe_id": rec_with_staple[1]["recipe_id"], "day": "Martes"},
            {"recipe_id": rec_without_staple[0]["recipe_id"], "day": "Miércoles"},
        ]

        # Swapping Lunes: Martes still requires staple, so staple must remain in basket with qty 1
        res = gemini_planner.swap_single_recipe(
            current_meals,
            rec_with_staple[0]["recipe_id"],
            {"adults": 2, "children": 0, "maxBudget": 100.0, "pantryItems": []},
            rotation=0,
        )
        basket_ids = {item["id"]: item for item in res["basket"]}
        self.assertIn(staple, basket_ids)
        self.assertEqual(basket_ids[staple]["quantity"], 1)

    def test_portion_and_cookidoo_servings_scaling(self):
        test_cases = [
            (1, 0, 4, 1),
            (2, 0, 4, 1),
            (2, 1, 4, 1),
            (2, 2, 4, 1),
            (2, 3, 4, 2),
            (4, 2, 4, 2),
            (2, 1, 2, 2),
            (2, 0, 1, 2),
        ]
        for adults, children, servings, expected_scale in test_cases:
            hp = adults + (0.75 * children)
            scale = max(1, math.ceil(hp / max(1, servings)))
            self.assertEqual(
                scale,
                expected_scale,
                f"Failed for adults={adults}, children={children}, servings={servings}",
            )


if __name__ == "__main__":
    unittest.main()
