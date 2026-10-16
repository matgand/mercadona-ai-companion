"""Comprehensive unit test suite for campaign_service.py.

Covers:
- Campaign CRUD operations (list, get, create, update, delete/status transitions: Activa, Planificada, Borrador, Terminada).
- Category validation (VALID_CATEGORIES: Familias, Saludables, Rutina rápida, Ahorro, plus synonyms and fallbacks).
- Profile metadata handling (PROFILES_METADATA, default constraints, budget multipliers, ID to category mappings).
- Concurrency locking with _LOCK (simultaneous reads/writes without data corruption).
- Gemini campaign generation prompt creation and response parsing (mocking Gemini LLM API calls and fallbacks).
- Sync logic between campaigns and peer services / main companion menu plans (headers, tokens, HTTP error handling).
- Persistence handling with temporary files/mocking CAMPAIGNS_FILE so real data/campaigns.json is never modified.
- Error handling, malformed payloads, edge cases, and boundary values.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import campaign_service


class BaseCampaignServiceTestCase(unittest.TestCase):
    """Base test case setting up isolated temporary campaign data storage."""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp(prefix="test_campaigns_")
        self.temp_campaigns_file = Path(self.temp_dir) / "campaigns.json"
        self.temp_data_dir = Path(self.temp_dir)

        # Sample initial campaigns
        self.sample_campaigns = [
            {
                "id": "familias-semana-resuelta",
                "title": "Tu semana familiar, resuelta",
                "tagline": "Cinco cenas familiares variadas en Thermomix.",
                "category": "Familias",
                "occasion": "Familias",
                "profileId": "familias",
                "badge": "Recomendado para Familias",
                "status": "Activa",
                "imageUrl": "/meals/lemon-hake-potatoes.webp",
                "seedPrompt": "Planifica 5 cenas entre semana para 2 adultos y 1 niño.",
                "mealCount": 5,
                "maxBudget": 65.0,
                "maxMinutes": 25,
                "maxCaloriesPerServing": None,
                "eligibleHouseholds": "420k hogares",
                "whyProfile": "Diseñada para el perfil Familias.",
                "updatedAt": "2026-09-26T10:00:00Z",
            },
            {
                "id": "saludables-ligeras-equilibradas",
                "title": "Cenas ligeras y equilibradas",
                "tagline": "Cinco cenas saludables con control de calorías.",
                "category": "Saludables",
                "occasion": "Saludables",
                "profileId": "saludables",
                "badge": "Objetivo Saludable · ≤ 450 kcal",
                "status": "Planificada",
                "imageUrl": "/meals/pasta-chickpea-salad.webp",
                "seedPrompt": "Planifica 5 cenas saludables para 2 adultos.",
                "mealCount": 5,
                "maxBudget": 60.0,
                "maxMinutes": 30,
                "maxCaloriesPerServing": 450,
                "eligibleHouseholds": "310k hogares",
                "whyProfile": "Adaptada al perfil Saludables.",
                "updatedAt": "2026-09-26T10:05:00Z",
            },
            {
                "id": "rutina-rapida-25min",
                "title": "Cena lista en menos de 25 minutos",
                "tagline": "Cinco cenas exprés para semanas intensas.",
                "category": "Rutina rápida",
                "occasion": "Rutina rápida",
                "profileId": "rutina-rapida",
                "badge": "Ideal para semanas con prisa",
                "status": "Borrador",
                "imageUrl": "/meals/quick-broccoli-salad.webp",
                "seedPrompt": "Planifica 5 cenas rápidas para 2 adultos.",
                "mealCount": 5,
                "maxBudget": 50.0,
                "maxMinutes": 25,
                "maxCaloriesPerServing": None,
                "eligibleHouseholds": "295k hogares",
                "whyProfile": "Pensada para el perfil Rutina rápida.",
                "updatedAt": "2026-09-26T10:10:00Z",
            },
            {
                "id": "ahorro-despensa-inteligente",
                "title": "Aprovecha tu despensa",
                "tagline": "Menú semanal de máximo ahorro.",
                "category": "Ahorro",
                "occasion": "Ahorro",
                "profileId": "ahorro",
                "badge": "Máximo ahorro",
                "status": "Terminada",
                "imageUrl": "/meals/chickpea-spinach-tomato-rice.webp",
                "seedPrompt": "Planifica 5 cenas económicas para 2 adultos y 2 niños.",
                "mealCount": 5,
                "maxBudget": 48.0,
                "maxMinutes": 30,
                "maxCaloriesPerServing": None,
                "eligibleHouseholds": "255k hogares",
                "whyProfile": "Optimizada para el perfil Ahorro.",
                "updatedAt": "2026-09-26T10:15:00Z",
            },
        ]

        self.temp_campaigns_file.write_text(
            json.dumps(self.sample_campaigns, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Patch paths in campaign_service
        self.orig_campaigns_file = campaign_service.CAMPAIGNS_FILE
        self.orig_data_dir = campaign_service.DATA_DIR
        campaign_service.CAMPAIGNS_FILE = self.temp_campaigns_file
        campaign_service.DATA_DIR = self.temp_data_dir

    def tearDown(self):
        campaign_service.CAMPAIGNS_FILE = self.orig_campaigns_file
        campaign_service.DATA_DIR = self.orig_data_dir
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()


class TestCategoryValidation(BaseCampaignServiceTestCase):
    """Tests category normalization, mapping, and validation."""

    def test_valid_categories_constant(self):
        self.assertEqual(
            campaign_service.VALID_CATEGORIES,
            ["Familias", "Saludables", "Rutina rápida", "Ahorro"],
        )

    def test_normalize_category_exact_matches(self):
        for cat in campaign_service.VALID_CATEGORIES:
            self.assertEqual(campaign_service.normalize_category(cat), cat)

    def test_normalize_category_synonyms_and_keywords(self):
        test_cases = [
            ("salud", "Saludables"),
            ("healthy lifestyle", "Saludables"),
            ("Comida Ligera", "Saludables"),
            ("bajas calorías", "Saludables"),
            ("control de kcal", "Saludables"),
            ("rutina express", "Rutina rápida"),
            ("recetas rapidas", "Rutina rápida"),
            ("en 15 min", "Rutina rápida"),
            ("convenience meal", "Rutina rápida"),
            ("ahorro mensual", "Ahorro"),
            ("comida barata", "Ahorro"),
            ("economico", "Ahorro"),
            ("presupuesto ajustado", "Ahorro"),
            ("aprovechamiento despensa", "Ahorro"),
            ("familia numerosa", "Familias"),
            ("desconocido total", "Familias"),
            ("", "Familias"),
            (None, "Familias"),
        ]
        for raw, expected in test_cases:
            with self.subTest(raw=raw, expected=expected):
                self.assertEqual(campaign_service.normalize_category(raw), expected)

    def test_category_and_profile_id_mappings(self):
        self.assertEqual(campaign_service.CATEGORY_TO_PROFILE_ID["Familias"], "familias")
        self.assertEqual(campaign_service.CATEGORY_TO_PROFILE_ID["Saludables"], "saludables")
        self.assertEqual(campaign_service.CATEGORY_TO_PROFILE_ID["Rutina rápida"], "rutina-rapida")
        self.assertEqual(campaign_service.CATEGORY_TO_PROFILE_ID["Rutína rápida"], "rutina-rapida")
        self.assertEqual(campaign_service.CATEGORY_TO_PROFILE_ID["Ahorro"], "ahorro")

        self.assertEqual(campaign_service.PROFILE_ID_TO_CATEGORY["familias"], "Familias")
        self.assertEqual(campaign_service.PROFILE_ID_TO_CATEGORY["family-explorer"], "Familias")
        self.assertEqual(campaign_service.PROFILE_ID_TO_CATEGORY["saludables"], "Saludables")
        self.assertEqual(campaign_service.PROFILE_ID_TO_CATEGORY["healthy-couple"], "Saludables")
        self.assertEqual(campaign_service.PROFILE_ID_TO_CATEGORY["rutina-rapida"], "Rutina rápida")
        self.assertEqual(campaign_service.PROFILE_ID_TO_CATEGORY["convenience-professional"], "Rutina rápida")
        self.assertEqual(campaign_service.PROFILE_ID_TO_CATEGORY["ahorro"], "Ahorro")


class TestStatusValidation(BaseCampaignServiceTestCase):
    """Tests status normalization, lifecycle states, and CSS class mappings."""

    def test_valid_statuses_constant(self):
        self.assertEqual(
            campaign_service.VALID_STATUSES,
            ["Activa", "Planificada", "Borrador", "Terminada"],
        )

    def test_normalize_status_exact_matches(self):
        for status in campaign_service.VALID_STATUSES:
            self.assertEqual(campaign_service.normalize_status(status), status)

    def test_normalize_status_synonyms_and_fallbacks(self):
        test_cases = [
            ("active", "Activa"),
            ("live", "Activa"),
            ("publicada", "Activa"),
            ("scheduled", "Planificada"),
            ("programada", "Planificada"),
            ("draft", "Borrador"),
            ("completed", "Terminada"),
            ("archived", "Terminada"),
            ("finalizada", "Terminada"),
            ("archivada", "Terminada"),
            ("unknown_status", "Activa"),
            ("", "Activa"),
            (None, "Activa"),
        ]
        for raw, expected in test_cases:
            with self.subTest(raw=raw, expected=expected):
                self.assertEqual(campaign_service.normalize_status(raw), expected)

    def test_status_to_css_class_mapping(self):
        self.assertEqual(campaign_service.STATUS_TO_CSS_CLASS["Activa"], "live")
        self.assertEqual(campaign_service.STATUS_TO_CSS_CLASS["Planificada"], "scheduled")
        self.assertEqual(campaign_service.STATUS_TO_CSS_CLASS["Borrador"], "draft")
        self.assertEqual(campaign_service.STATUS_TO_CSS_CLASS["Terminada"], "archived")


class TestProfileMetadata(BaseCampaignServiceTestCase):
    """Tests profile metadata definitions and attribute completeness."""

    def test_profiles_metadata_structure(self):
        self.assertEqual(len(campaign_service.PROFILES_METADATA), 4)
        profile_ids = {p["id"] for p in campaign_service.PROFILES_METADATA}
        self.assertEqual(profile_ids, {"familias", "saludables", "rutina-rapida", "ahorro"})

        required_keys = {"id", "name", "category", "household", "primaryNeed", "eligibleHouseholds", "icon"}
        for prof in campaign_service.PROFILES_METADATA:
            for k in required_keys:
                self.assertIn(k, prof)
                self.assertTrue(str(prof[k]).strip())


class TestEnrichCampaign(BaseCampaignServiceTestCase):
    """Tests _enrich_campaign function filling missing defaults and sanitizing fields."""

    def test_enrich_campaign_full(self):
        raw = {
            "id": "custom-id",
            "title": "Custom Title",
            "tagline": "Custom Tagline",
            "category": "Saludables",
            "badge": "Custom Badge",
            "status": "Planificada",
            "imageUrl": "/meals/custom.webp",
            "seedPrompt": "Custom Prompt",
            "mealCount": 7,
            "maxBudget": 75.0,
            "maxMinutes": 20,
            "maxCaloriesPerServing": 400,
            "eligibleHouseholds": "350k hogares",
            "whyProfile": "Custom Why",
            "updatedAt": "2026-09-27T12:00:00Z",
        }
        enriched = campaign_service._enrich_campaign(raw)
        self.assertEqual(enriched["id"], "custom-id")
        self.assertEqual(enriched["title"], "Custom Title")
        self.assertEqual(enriched["tagline"], "Custom Tagline")
        self.assertEqual(enriched["category"], "Saludables")
        self.assertEqual(enriched["occasion"], "Saludables")
        self.assertEqual(enriched["profileId"], "saludables")
        self.assertEqual(enriched["badge"], "Custom Badge")
        self.assertEqual(enriched["status"], "Planificada")
        self.assertEqual(enriched["statusClass"], "scheduled")
        self.assertEqual(enriched["mealCount"], 7)
        self.assertEqual(enriched["maxBudget"], 75.0)
        self.assertEqual(enriched["maxMinutes"], 20)
        self.assertEqual(enriched["maxCaloriesPerServing"], 400)
        self.assertEqual(enriched["whyProfile"], "Custom Why")

    def test_enrich_campaign_empty_dict_defaults(self):
        enriched = campaign_service._enrich_campaign({})
        self.assertEqual(enriched["id"], "campaign-1")
        self.assertEqual(enriched["title"], "Campaña Semanal Mercadona")
        self.assertEqual(enriched["category"], "Familias")
        self.assertEqual(enriched["profileId"], "familias")
        self.assertEqual(enriched["status"], "Activa")
        self.assertEqual(enriched["statusClass"], "live")
        self.assertEqual(enriched["mealCount"], 5)
        self.assertEqual(enriched["maxBudget"], 60.0)
        self.assertEqual(enriched["maxMinutes"], 25)
        self.assertIsNone(enriched["maxCaloriesPerServing"])
        self.assertEqual(enriched["eligibleHouseholds"], "420k hogares")
        self.assertTrue(enriched["whyProfile"].startswith("Diseñada para el perfil Familias"))

    def test_enrich_campaign_derived_from_profile_id(self):
        raw = {"profileId": "ahorro"}
        enriched = campaign_service._enrich_campaign(raw)
        self.assertEqual(enriched["category"], "Ahorro")
        self.assertEqual(enriched["profileId"], "ahorro")
        self.assertEqual(enriched["eligibleHouseholds"], "255k hogares")


class TestLocalPersistenceAndCRUD(BaseCampaignServiceTestCase):
    """Tests load, save, list, get, create, update, and delete/status transitions."""

    def test_load_local_campaigns_success(self):
        campaigns = campaign_service.load_local_campaigns()
        self.assertEqual(len(campaigns), 4)
        self.assertEqual(campaigns[0]["id"], "familias-semana-resuelta")
        self.assertEqual(campaigns[1]["id"], "saludables-ligeras-equilibradas")

    def test_load_local_campaigns_file_missing(self):
        if self.temp_campaigns_file.exists():
            self.temp_campaigns_file.unlink()
        campaigns = campaign_service.load_local_campaigns()
        self.assertEqual(campaigns, [])

    def test_load_local_campaigns_corrupt_json(self):
        self.temp_campaigns_file.write_text("NOT_VALID_JSON{", encoding="utf-8")
        campaigns = campaign_service.load_local_campaigns()
        self.assertEqual(campaigns, [])

    def test_load_local_campaigns_non_list_json(self):
        self.temp_campaigns_file.write_text('{"key": "value"}', encoding="utf-8")
        campaigns = campaign_service.load_local_campaigns()
        self.assertEqual(campaigns, [])

    def test_save_local_campaigns_persists_to_disk(self):
        new_list = [
            {
                "id": "test-camp",
                "title": "Test Title",
                "category": "Ahorro",
                "status": "Activa",
            }
        ]
        saved = campaign_service.save_local_campaigns(new_list)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["id"], "test-camp")

        # Verify disk
        disk_data = json.loads(self.temp_campaigns_file.read_text(encoding="utf-8"))
        self.assertEqual(len(disk_data), 1)
        self.assertEqual(disk_data[0]["id"], "test-camp")
        self.assertEqual(disk_data[0]["category"], "Ahorro")
        self.assertEqual(disk_data[0]["profileId"], "ahorro")

    def test_update_campaign_record_success(self):
        with patch("campaign_service.push_sync_to_peer_services") as mock_sync:
            updated = campaign_service.update_campaign_record(
                "familias-semana-resuelta",
                {
                    "title": "Nuevo Título Familiar",
                    "status": "Terminada",
                    "maxBudget": 70.0,
                    "category": "Ahorro",
                },
            )
            self.assertEqual(updated["title"], "Nuevo Título Familiar")
            self.assertEqual(updated["status"], "Terminada")
            self.assertEqual(updated["statusClass"], "archived")
            self.assertEqual(updated["maxBudget"], 70.0)
            self.assertEqual(updated["category"], "Ahorro")
            self.assertEqual(updated["profileId"], "ahorro")
            mock_sync.assert_called_once()

        # Check persisted file
        persisted = campaign_service.load_local_campaigns()
        target = next(c for c in persisted if c["id"] == "familias-semana-resuelta")
        self.assertEqual(target["title"], "Nuevo Título Familiar")
        self.assertEqual(target["status"], "Terminada")

    def test_update_campaign_record_not_found(self):
        with self.assertRaises(ValueError) as ctx:
            campaign_service.update_campaign_record("non-existent-id", {"status": "Activa"})
        self.assertIn("no encontrada", str(ctx.exception))

    def test_all_status_transitions_via_update(self):
        cid = "familias-semana-resuelta"
        for st in ["Borrador", "Planificada", "Activa", "Terminada"]:
            with patch("campaign_service.push_sync_to_peer_services"):
                res = campaign_service.update_campaign_record(cid, {"status": st})
                self.assertEqual(res["status"], st)


class TestConcurrencyLocking(BaseCampaignServiceTestCase):
    """Tests thread-safety and race condition prevention with _LOCK."""

    def test_concurrent_read_write_consistency(self):
        errors: list[Exception] = []
        iterations = 25

        def writer_thread(tid: int):
            try:
                for i in range(iterations):
                    camps = campaign_service.load_local_campaigns()
                    camps.append(
                        {
                            "id": f"thread-{tid}-{i}",
                            "title": f"Camp Thread {tid} {i}",
                            "category": "Familias",
                            "status": "Activa",
                        }
                    )
                    campaign_service.save_local_campaigns(camps)
            except Exception as e:
                errors.append(e)

        def reader_thread():
            try:
                for _ in range(iterations):
                    camps = campaign_service.load_local_campaigns()
                    self.assertIsInstance(camps, list)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer_thread, args=(1,)),
            threading.Thread(target=writer_thread, args=(2,)),
            threading.Thread(target=reader_thread),
            threading.Thread(target=reader_thread),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Encountered concurrency errors: {errors}")
        final_campaigns = campaign_service.load_local_campaigns()
        self.assertGreater(len(final_campaigns), 4)


class TestCoverImageAndCategoryInference(BaseCampaignServiceTestCase):
    """Tests heuristic cover image selection and category inference from briefs."""

    def test_select_cover_image_for_brief_keywords(self):
        cases = [
            ("Cena ligera con salmón fresco y sopa de kale", "Saludables", "/meals/salmon-kale-soup.webp"),
            ("Merluza al horno con patatas al limón", "Familias", "/meals/lemon-hake-potatoes.webp"),
            ("Guiso de lentejas de otoño", "Familias", "/meals/Stewed-lentils.webp"),
            ("Wrap de pavo y aguacate sin gluten", "Saludables", "/meals/turkey-avocado-wraps.webp"),
            ("Arroz con espinacas y garbanzos de despensa", "Ahorro", "/meals/chickpea-spinach-tomato-rice.webp"),
            ("Ensalada exprés con brócoli en 20 min", "Rutina rápida", "/meals/quick-broccoli-salad.webp"),
            ("Ensalada fresca y ligera para el verano", "Saludables", "/meals/pasta-chickpea-salad.webp"),
        ]
        for brief, cat, expected in cases:
            with self.subTest(brief=brief, cat=cat):
                self.assertEqual(
                    campaign_service._select_cover_image_for_brief(brief, cat),
                    expected,
                )

    def test_select_cover_image_cookidoo_catalog_match(self):
        mock_recipes = [
            {"id": "c-1", "name": "Risotto de Setas Silvestres", "image_url": "https://assets.tmx/setas.webp"}
        ]
        with patch("campaign_service.load_cookidoo_catalog", return_value=mock_recipes):
            res = campaign_service._select_cover_image_for_brief("Campaña con risotto y setas", "Familias")
            self.assertEqual(res, "https://assets.tmx/setas.webp")

    def test_select_cover_image_category_default_fallback(self):
        with patch("campaign_service.load_cookidoo_catalog", side_effect=RuntimeError("DB offline")):
            self.assertEqual(
                campaign_service._select_cover_image_for_brief("algo generico", "Ahorro"),
                "/meals/chickpea-spinach-tomato-rice.webp",
            )
            self.assertEqual(
                campaign_service._select_cover_image_for_brief("algo generico", "Rutina rápida"),
                "/meals/quick-broccoli-salad.webp",
            )
            self.assertEqual(
                campaign_service._select_cover_image_for_brief("algo generico", "Saludables"),
                "/meals/pasta-chickpea-salad.webp",
            )
            self.assertEqual(
                campaign_service._select_cover_image_for_brief("algo generico", "Familias"),
                "/meals/lemon-hake-potatoes.webp",
            )

    def test_infer_category_from_brief(self):
        cases = [
            ("Cenas con presupuesto bajo y ahorro de 40€", None, "Ahorro"),
            ("Cenas saludables y bajas en calorías", None, "Saludables"),
            ("Cenas rápidas exprés en 15 min", None, "Rutina rápida"),
            ("Cenas para niños y toda la familia", None, "Familias"),
            ("Cena normal sin palabras clave", "Rutina rápida", "Rutina rápida"),
            ("Cena normal sin palabras clave", None, "Familias"),
        ]
        for brief, hint, expected in cases:
            with self.subTest(brief=brief, hint=hint):
                self.assertEqual(
                    campaign_service._infer_category_from_brief(brief, hint),
                    expected,
                )


class TestGeminiCampaignGenerator(BaseCampaignServiceTestCase):
    """Tests Gemini LLM API generation, parsing, error recovery, and fallbacks."""

    @patch("campaign_service.push_sync_to_peer_services")
    def test_call_gemini_campaign_generator_success(self, mock_push):
        mock_google = MagicMock()
        mock_genai = MagicMock()
        mock_types = MagicMock()
        mock_client = MagicMock()

        mock_genai.Client.return_value = mock_client
        mock_genai.types = mock_types
        mock_google.genai = mock_genai

        mock_resp = MagicMock()
        mock_resp.text = json.dumps(
            {
                "title": "Sabores del Mediterráneo",
                "tagline": "Cinco cenas equilibradas con pescado fresco.",
                "category": "Saludables",
                "badge": "Mediterráneo · ≤ 450 kcal",
                "seedPrompt": "Planifica 5 cenas saludables de pescado.",
                "whyProfile": "Impulsa la pescadería de Mercadona.",
            }
        )
        mock_client.models.generate_content.return_value = mock_resp

        modules_patch = {
            "google": mock_google,
            "google.genai": mock_genai,
            "google.genai.types": mock_types,
        }
        with patch.dict("sys.modules", modules_patch):
            res = campaign_service._call_gemini_campaign_generator("Brief de prueba", "Saludables", {})
            self.assertIsNotNone(res)
            self.assertEqual(res["title"], "Sabores del Mediterráneo")
            self.assertEqual(res["category"], "Saludables")
            self.assertIn("Gemini 3.8 Flash", res["model_used"])

    @patch("campaign_service.push_sync_to_peer_services")
    def test_call_gemini_campaign_generator_api_failure_returns_none(self, mock_push):
        mock_google = MagicMock()
        mock_genai = MagicMock()
        mock_types = MagicMock()
        mock_client = MagicMock()

        mock_genai.Client.return_value = mock_client
        mock_genai.types = mock_types
        mock_google.genai = mock_genai
        mock_client.models.generate_content.side_effect = Exception("Vertex AI 429 Quota Exceeded")

        modules_patch = {
            "google": mock_google,
            "google.genai": mock_genai,
            "google.genai.types": mock_types,
        }
        with patch.dict("sys.modules", modules_patch):
            res = campaign_service._call_gemini_campaign_generator("Brief de prueba", "Saludables", {})
            self.assertIsNone(res)

    def test_call_gemini_campaign_generator_missing_sdk(self):
        with patch.dict("sys.modules", {"google": None}):
            res = campaign_service._call_gemini_campaign_generator("Brief de prueba", "Saludables", {})
            self.assertIsNone(res)


class TestGenerateCampaignFromBrief(BaseCampaignServiceTestCase):
    """Tests the full generate_campaign_from_brief pipeline with both Gemini and fallbacks."""

    def test_generate_campaign_empty_brief_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            campaign_service.generate_campaign_from_brief("   ")
        self.assertIn("lenguaje natural", str(ctx.exception))

    def test_generate_campaign_invalid_scope_prompt(self):
        with patch("campaign_service.validate_meal_planning_prompt", return_value=(False, "Tema fuera de alcance")):
            with self.assertRaises(ValueError) as ctx:
                campaign_service.generate_campaign_from_brief("Explica cómo arreglar un coche")
            self.assertIn("fuera de alcance", str(ctx.exception))

    @patch("campaign_service.push_sync_to_peer_services")
    @patch("campaign_service._call_gemini_campaign_generator")
    def test_generate_campaign_with_gemini_result(self, mock_gemini, mock_push):
        mock_gemini.return_value = {
            "title": "Cenas Saludables Mediterráneas",
            "tagline": "Cinco recetas frescas con ingredientes de temporada.",
            "category": "Saludables",
            "badge": "Saludables · ≤ 400 kcal",
            "seedPrompt": "Planifica 5 cenas saludables en 20 minutos.",
            "whyProfile": "Diseñada para perfiles saludables.",
        }

        created = campaign_service.generate_campaign_from_brief(
            brief="Crea un menú saludable de 5 cenas ligeras",
            category_hint="Saludables",
            initial_status="Planificada",
        )

        self.assertEqual(created["title"], "Cenas Saludables Mediterráneas")
        self.assertEqual(created["category"], "Saludables")
        self.assertEqual(created["status"], "Planificada")
        self.assertEqual(created["statusClass"], "scheduled")
        self.assertEqual(created["maxCaloriesPerServing"], 450)
        self.assertTrue(created["id"].startswith("cenas-saludables-mediterr"))
        mock_push.assert_called_once()

        # Ensure it was persisted
        persisted = campaign_service.load_local_campaigns()
        self.assertEqual(persisted[0]["id"], created["id"])

    @patch("campaign_service.push_sync_to_peer_services")
    @patch("campaign_service._call_gemini_campaign_generator", return_value=None)
    def test_generate_campaign_deterministic_fallback_ahorro(self, mock_gemini, mock_push):
        created = campaign_service.generate_campaign_from_brief(
            brief="Crea una campaña semanal de ahorro para 4 personas con presupuesto de 40 euros y pasta que tengo en casa",
            category_hint="Ahorro",
            initial_status="Activa",
        )

        self.assertEqual(created["category"], "Ahorro")
        self.assertEqual(created["profileId"], "ahorro")
        self.assertEqual(created["status"], "Activa")
        self.assertEqual(created["maxBudget"], 40.0)
        self.assertIn("Ahorro", created["badge"])
        self.assertIn("presupuesto", created["seedPrompt"])
        mock_push.assert_called_once()

    @patch("campaign_service.push_sync_to_peer_services")
    @patch("campaign_service._call_gemini_campaign_generator", return_value=None)
    def test_generate_campaign_deterministic_fallback_rutina_rapida(self, mock_gemini, mock_push):
        created = campaign_service.generate_campaign_from_brief(
            brief="Cenas super rápidas exprés en 15 minutos sin complicaciones",
            category_hint=None,
        )

        self.assertEqual(created["category"], "Rutina rápida")
        self.assertEqual(created["profileId"], "rutina-rapida")
        self.assertEqual(created["maxMinutes"], 15)
        self.assertEqual(created["badge"], "Exprés · ≤ 15 min")


class TestPeerServicesSync(BaseCampaignServiceTestCase):
    """Tests microservice-to-microservice sync logic and token headers."""

    def test_get_service_headers_token_generation(self):
        with patch.dict(os.environ, {"SESSION_SECRET": "test-secret"}):
            hdrs = campaign_service._get_service_headers("https://remote-service.run.app")
            self.assertEqual(hdrs["User-Agent"], "MercadonaCampaignSync/1.0")
            self.assertEqual(hdrs["Accept"], "application/json")
            self.assertIn("X-Internal-Sync-Token", hdrs)
            self.assertEqual(len(hdrs["X-Internal-Sync-Token"]), 32)

    @patch("urllib.request.urlopen")
    def test_get_service_headers_with_metadata_identity_token(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"mock-id-token-abc"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        hdrs = campaign_service._get_service_headers("https://remote-service.run.app")
        self.assertEqual(hdrs.get("Authorization"), "Bearer mock-id-token-abc")

    @patch("urllib.request.urlopen")
    def test_push_sync_to_peer_services_campaign_library_role(self, mock_urlopen):
        env = {
            "SERVICE_ROLE": "campaign-library",
            "COMPANION_APP_URL": "https://companion-app.run.app",
        }
        with patch.dict(os.environ, env):
            campaign_service.push_sync_to_peer_services(self.sample_campaigns)
            mock_urlopen.assert_called()
            call_args, call_kwargs = mock_urlopen.call_args
            req = call_args[0]
            self.assertEqual(req.get_full_url(), "https://companion-app.run.app/api/campaigns/sync")
            self.assertEqual(req.get_method(), "POST")

    @patch("urllib.request.urlopen")
    def test_push_sync_to_peer_services_companion_app_role(self, mock_urlopen):
        env = {
            "SERVICE_ROLE": "companion-app",
            "CAMPAIGN_LIBRARY_URL": "https://campaign-library.run.app",
        }
        with patch.dict(os.environ, env):
            campaign_service.push_sync_to_peer_services(self.sample_campaigns)
            mock_urlopen.assert_called()
            req = mock_urlopen.call_args[0][0]
            self.assertEqual(req.get_full_url(), "https://campaign-library.run.app/api/campaigns/sync")

    @patch("urllib.request.urlopen", side_effect=Exception("Network connection failed"))
    def test_push_sync_resilient_to_network_failure(self, mock_urlopen):
        env = {
            "SERVICE_ROLE": "companion-app",
            "CAMPAIGN_LIBRARY_URL": "https://campaign-library.run.app",
        }
        with patch.dict(os.environ, env):
            # Must not raise an uncaught exception
            campaign_service.push_sync_to_peer_services(self.sample_campaigns)


class TestFetchCampaignsRemoteOrLocal(BaseCampaignServiceTestCase):
    """Tests fetching campaigns from remote microservice or local fallback."""

    def test_fetch_from_remote_when_service_is_library_returns_local(self):
        env = {
            "SERVICE_ROLE": "campaign-library",
            "CAMPAIGN_LIBRARY_URL": "https://remote-library.run.app",
        }
        with patch.dict(os.environ, env):
            result = campaign_service.fetch_campaigns_from_remote_or_local()
            self.assertEqual(len(result), 4)

    @patch("urllib.request.urlopen")
    def test_fetch_from_remote_success(self, mock_urlopen):
        env = {
            "SERVICE_ROLE": "companion-app",
            "CAMPAIGN_LIBRARY_URL": "https://remote-library.run.app",
        }
        remote_data = {
            "campaigns": [
                {
                    "id": "remote-1",
                    "title": "Remote Campaign",
                    "category": "Saludables",
                    "status": "Activa",
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(remote_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, env):
            result = campaign_service.fetch_campaigns_from_remote_or_local()
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["id"], "remote-1")

            # Check that it was saved locally
            local = campaign_service.load_local_campaigns()
            self.assertEqual(len(local), 1)
            self.assertEqual(local[0]["id"], "remote-1")

    @patch("urllib.request.urlopen", side_effect=Exception("HTTP 500 error"))
    def test_fetch_from_remote_failure_falls_back_to_local(self, mock_urlopen):
        env = {
            "SERVICE_ROLE": "companion-app",
            "CAMPAIGN_LIBRARY_URL": "https://remote-library.run.app",
        }
        with patch.dict(os.environ, env):
            result = campaign_service.fetch_campaigns_from_remote_or_local()
            self.assertEqual(len(result), 4)
            self.assertEqual(result[0]["id"], "familias-semana-resuelta")


if __name__ == "__main__":
    unittest.main()
