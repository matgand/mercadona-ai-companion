"""Unit and integration tests for the 6 El Corte Inglés Strategic Features:
1. WhatsApp Integration (Option B Real Webhook: Meta Cloud API + Twilio TwiML + Live State Sync)
2. Automatic Traditional Counter Preparation Notes & Multi-Tray Splitting
3. 3-Way Basket Tier Switcher (Marca ECI / Bio & Ecológicos / Club del Gourmet & Sumiller IA)
4. Fridge & Pantry Vision (Multimodal Gemini & 1-Click Demo Presets)
5. El Corte Inglés Ecosystem (ECI Plus Free Shipping Progress, Click & Car, Per-Day Diners Scaling)
6. Retail Media Sponsored SKUs & First-Party Culinary Intent ('Demand Sensing') Analytics
"""

import datetime
import json
import threading
import urllib.request
import unittest
import cookidoo_service
import gemini_planner
import whatsapp_service
import campaign_service
import server


class TestECIStrategicFeatures(unittest.TestCase):
    def setUp(self):
        whatsapp_service.update_whatsapp_config(reset_chat=True)
        self.plan = gemini_planner.build_weekly_plan(
            "5 cenas variadas con pescado y verdura para 2 adultos y 1 niño en menos de 25 minutos bajo 65€",
            postal_code="28001",
        )

    def tearDown(self):
        whatsapp_service.update_whatsapp_config(reset_chat=True)
        cookidoo_service.clear_cookidoo_session()

    def test_1_whatsapp_webhook_meta_verification_and_twilio_post(self):
        """Verifies Option B Real Webhook GET verification (Meta), empty initial chat, and POST handling (Twilio & Meta)."""
        init_state = whatsapp_service.get_whatsapp_state()
        self.assertEqual(init_state.get("messages"), [])

        status, body = whatsapp_service.verify_whatsapp_webhook_get(
            {
                "hub.mode": ["subscribe"],
                "hub.verify_token": [whatsapp_service.DEFAULT_VERIFY_TOKEN],
                "hub.challenge": ["987654321"],
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, "987654321")

        # Sync plan to WhatsApp session
        whatsapp_service.sync_active_plan_to_whatsapp(self.plan, postal_code="28001")

        # Twilio form-urlencoded webhook POST
        raw_twilio = "From=whatsapp%3A%2B34600123456&Body=Hoy+vienen+6+invitados+el+jueves".encode("utf-8")
        p_status, p_ct, p_body = whatsapp_service.handle_whatsapp_webhook_post(
            raw_twilio, "application/x-www-form-urlencoded"
        )
        self.assertEqual(p_status, 200)
        self.assertIn("text/xml", p_ct)
        self.assertIn("<Response><Message>", p_body.decode("utf-8"))

        # Verify that Thursday diners scaled to 6 in active plan
        state = whatsapp_service.get_whatsapp_state()
        active_plan = state.get("active_plan") or {}
        thursday_meal = next((m for m in active_plan.get("meals", []) if m.get("day") == "Jueves"), None)
        if thursday_meal:
            self.assertEqual(thursday_meal.get("active_diners"), 6)

        # Verify swapping Wednesday specifically for a fish dinner strictly returns a fish recipe (is_fish=True)
        res_fish = whatsapp_service.process_whatsapp_user_message(
            "Cambia el miércoles por una cena rápida de pescado",
            current_plan_override=active_plan,
        )
        wed_meal = next((m for m in res_fish["plan"]["meals"] if m["day"] == "Miércoles"), None)
        self.assertIsNotNone(wed_meal)
        self.assertTrue(wed_meal.get("is_fish"), f"Expected fish recipe for Wednesday, got: {wed_meal.get('name')}")
        self.assertNotIn("pollo", wed_meal.get("name", "").lower())
        self.assertNotIn("alitas", wed_meal.get("name", "").lower())

    def test_2_counter_prep_notes_and_cut_overrides(self):
        """Verifies automatic traditional counter preparation notes (Pescadería, Carnicería, Frutería)."""
        basket = self.plan.get("basket", [])
        counter_items = [item for item in basket if item.get("counter_prep")]
        self.assertGreater(len(counter_items), 0, "Expected at least one counter item with preparation note")

        sample_item = counter_items[0]
        cp = sample_item["counter_prep"]
        self.assertIn("department", cp)
        self.assertIn("note", cp)
        self.assertIn("options", cp)
        self.assertTrue(len(cp["options"]) >= 2)

        # Test overriding a cut via recalculate_plan_basket
        chosen_cut = cp["options"][-1]
        recalc = gemini_planner.recalculate_plan_basket(
            self.plan,
            basket_tier="ahorro",
            custom_counter_cuts={str(sample_item["id"]): chosen_cut},
            postal_code="28001",
        )
        updated_item = next(
            (i for i in recalc["basket"] if str(i["id"]) == str(sample_item["id"])),
            None,
        )
        self.assertIsNotNone(updated_item)
        self.assertEqual(updated_item["counter_prep"]["selected_cut"], chosen_cut)

    def test_3_basket_tiers_and_sommelier_ia(self):
        """Verifies 3-Way Basket Tier Switcher (ahorro, bio, gourmet) and AI Sommelier pairing."""
        recalc_bio = gemini_planner.recalculate_plan_basket(
            self.plan,
            basket_tier="bio",
            postal_code="28001",
        )
        self.assertEqual(recalc_bio["basket_tier"], "bio")
        self.assertGreaterEqual(recalc_bio.get("upgraded_count", 0), 1)

        recalc_gourmet = gemini_planner.recalculate_plan_basket(
            self.plan,
            basket_tier="gourmet",
            include_sommelier_item=True,
            postal_code="28001",
        )
        self.assertEqual(recalc_gourmet["basket_tier"], "gourmet")
        self.assertIsNotNone(recalc_gourmet.get("sommelier_pairing"))
        self.assertIn("title", recalc_gourmet["sommelier_pairing"])
        self.assertIn("tasting_note", recalc_gourmet["sommelier_pairing"])
        self.assertTrue(recalc_gourmet["sommelier_pairing"]["included"])

    def test_4_fridge_vision_presets_and_analysis(self):
        """Verifies Multimodal Fridge & Pantry Vision analysis and zero-waste deduction."""
        for preset_id in ("nevera_mediterranea", "nevera_familiar", "nevera_verde"):
            res = gemini_planner.analyze_fridge_vision(preset_id=preset_id, postal_code="28001")
            self.assertIn("fridge_vision", res)
            self.assertIn("updated_prompt", res)
            self.assertIn("plan", res)
            fv = res["fridge_vision"]
            self.assertGreater(len(fv["detected_items"]), 0)
            self.assertGreater(fv.get("estimated_savings_eur", 0), 0)

    def test_5_eci_ecosystem_plus_and_diners_scaling(self):
        """Verifies El Corte Inglés Plus threshold status and per-day guest scaling."""
        eci_plus = self.plan.get("eci_plus_status")
        self.assertIsNotNone(eci_plus)
        self.assertEqual(eci_plus["free_delivery_threshold"], 50.0)
        self.assertIn("free_delivery_unlocked", eci_plus)
        self.assertIn("click_and_car_unlocked", eci_plus)

        # Scale Friday meal to 8 diners ("Hoy vienen invitados")
        recalc_guests = gemini_planner.recalculate_plan_basket(
            self.plan,
            basket_tier="ahorro",
            day_servings={"Viernes": 8},
            postal_code="28001",
        )
        friday_meal = next((m for m in recalc_guests["meals"] if m["day"] == "Viernes"), None)
        self.assertIsNotNone(friday_meal)
        self.assertEqual(friday_meal["active_diners"], 8)
        self.assertGreaterEqual(recalc_guests["total"], self.plan["total"])

    def test_6_retail_media_and_demand_sensing_analytics(self):
        """Verifies Retail Media sponsored badges and First-Party Demand Sensing analytics."""
        analytics = campaign_service.get_demand_sensing_analytics()
        self.assertIn("kpis", analytics)
        self.assertIn("top_postal_zones", analytics)
        self.assertIn("dietary_signals", analytics)
        self.assertIn("retail_media_sponsors", analytics)
        self.assertGreaterEqual(len(analytics["top_postal_zones"]), 3)
        self.assertGreaterEqual(len(analytics["retail_media_sponsors"]), 3)

    def test_7_live_http_endpoints_in_server(self):
        """Starts ThreadingHTTPServer on an ephemeral port and tests all new HTTP endpoints."""
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.CompanionRequestHandler)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            base = f"http://127.0.0.1:{port}"
            # 1. GET /api/whatsapp/webhook (Meta Hub Challenge)
            req_url = (
                f"{base}/api/whatsapp/webhook?hub.mode=subscribe"
                f"&hub.verify_token={whatsapp_service.DEFAULT_VERIFY_TOKEN}&hub.challenge=112233"
            )
            with urllib.request.urlopen(req_url, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertEqual(resp.read().decode("utf-8"), "112233")

            # 2. POST /api/whatsapp/webhook (Twilio TwiML)
            twilio_req = urllib.request.Request(
                f"{base}/api/whatsapp/webhook",
                data=b"From=whatsapp%3A%2B34600112233&Body=Modo+Gourmet",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urllib.request.urlopen(twilio_req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                xml_out = resp.read().decode("utf-8")
                self.assertIn("<Response><Message>", xml_out)

            # 3. GET /api/campaigns/analytics
            with urllib.request.urlopen(f"{base}/api/campaigns/analytics", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("kpis", data)
                self.assertIn("top_postal_zones", data)

            # 4. GET /api/fridge-vision/presets
            with urllib.request.urlopen(f"{base}/api/fridge-vision/presets", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                pdata = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(len(pdata.get("presets", [])), 3)

            # 5. POST /api/cookidoo/session & POST /api/cookidoo/schedule-week
            session_req = urllib.request.Request(
                f"{base}/api/cookidoo/session",
                data=json.dumps({"action": "connect", "demo_mode": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(session_req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                sdata = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(sdata.get("connected"))

            sched_req = urllib.request.Request(
                f"{base}/api/cookidoo/schedule-week",
                data=json.dumps(
                    {
                        "meals": self.plan.get("meals", []),
                        "week_mode": "current",
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(sched_req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                wdata = json.loads(resp.read().decode("utf-8"))
                self.assertIn(wdata.get("status"), ("week_scheduled", "live_week_scheduled"))
                self.assertEqual(wdata.get("scheduled_count"), 5)
                self.assertEqual(len(wdata.get("days", [])), 5)
                # Ensure all 5 days have distinct consecutive ISO calendar_date values
                dates = [d.get("calendar_date") for d in wdata.get("days", [])]
                self.assertEqual(len(set(dates)), 5)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_8_cookidoo_day_by_day_weekly_scheduling(self):
        """Verifies Cookidoo account linking, single-day recipe scheduling, full 5-day 'Mi Semana' scheduling, and verified recipe photos."""
        # Verify r396142 (Tortilla francesa rellena de espinacas y queso con tomates cherry) has its real JSON-LD image and no bogus 'fish' allergen
        catalog = cookidoo_service.load_cookidoo_catalog()
        r396142 = next((r for r in catalog if r.get("recipe_id") == "r396142"), None)
        self.assertIsNotNone(r396142)
        self.assertIn("8F828FCA-BB6E-43C8-81B5-0EEF7BEFD43D", r396142.get("image_url", ""))
        self.assertNotIn("10f2f654d594982786a238004247ba76ea5e7d1d", r396142.get("image_url", ""))
        self.assertNotIn("fish", r396142.get("allergens", []))

        # Verify demo_mode=False requires valid credentials
        with self.assertRaises(ValueError):
            cookidoo_service.verify_and_save_cookidoo_session(email="", password="", demo_mode=False)

        status = cookidoo_service.verify_and_save_cookidoo_session(demo_mode=True)
        self.assertTrue(status.get("connected"))
        self.assertEqual(status.get("planner_url"), "https://cookidoo.es/planning/es-ES/my-week")

        # Single recipe on Wednesday
        wed_res = cookidoo_service.send_recipe_to_thermomix(
            recipe_id=self.plan["meals"][2]["recipe_id"],
            day_name="Miércoles",
            week_mode="next",
        )
        self.assertIn(wed_res.get("status"), ("handoff_ready", "scheduled_in_calendar", "live_synced"))
        self.assertEqual(wed_res.get("day"), "Miércoles")
        self.assertIn("calendar_date", wed_res)
        self.assertEqual(wed_res.get("planner_url"), "https://cookidoo.es/planning/es-ES/my-week")

        # Full week via WhatsApp command "cmd:cookidoo"
        wa_res = whatsapp_service.process_whatsapp_user_message(
            "cmd:cookidoo",
            current_plan_override=self.plan,
        )
        self.assertEqual(wa_res.get("action"), "schedule_cookidoo_week")
        self.assertIn("cookidoo_scheduled_week", wa_res["plan"])
        self.assertEqual(len(wa_res["plan"]["cookidoo_scheduled_week"]["days"]), 5)
        self.assertEqual(
            wa_res["plan"]["cookidoo_scheduled_week"].get("planner_url"),
            "https://cookidoo.es/planning/es-ES/my-week",
        )

    def test_9_complex_prompt_quotas_day_exclusions_kid_friendly_and_unlike(self):
        """Verifies pasta cap, Monday pasta exclusion, meat & fish counts, kid-friendly safety, randomized likes, and un-liking."""
        prompt = (
            "Planifica 5 cenas entre semana para 2 adultos y 2 niños. "
            "Incluye una cena de carne, dos de pescado y usa la pasta que ya tengo en casa. "
            "No propongas recetas con pasta más de dos veces, y nunca los lunes"
        )
        c = gemini_planner.parse_constraints(prompt)
        self.assertEqual(c["adults"], 2)
        self.assertEqual(c["children"], 2)
        self.assertTrue(c["kidFriendly"])
        self.assertEqual(c["requiredMeatCount"], 1)
        self.assertEqual(c["requiredFishCount"], 2)
        self.assertEqual(c["maxPastaCount"], 2)
        self.assertIn("pasta", c["dayExclusions"].get("Lunes", []))
        self.assertNotIn("gluten", c["excludedAllergens"])

        plan = gemini_planner.build_weekly_plan(prompt, postal_code="28016", variety_seed="test_complex_1")
        meals = plan["meals"]
        self.assertEqual(len(meals), 5)
        # Monday is never pasta
        self.assertEqual(meals[0]["day"], "Lunes")
        self.assertFalse(meals[0]["is_pasta"], f"Monday should not be pasta, got: {meals[0]['name']}")
        # Total pasta count is between 1 and 2
        pasta_count = sum(1 for m in meals if m["is_pasta"])
        self.assertGreaterEqual(pasta_count, 1)
        self.assertLessEqual(pasta_count, 2)
        # Fish count >= 2, Meat count >= 1
        fish_count = sum(1 for m in meals if m["is_fish"])
        meat_count = sum(1 for m in meals if m["is_meat"])
        self.assertGreaterEqual(fish_count, 2)
        self.assertGreaterEqual(meat_count, 1)
        # All meals are kid-safe (no calamares en salsa americana)
        for m in meals:
            self.assertNotIn("calamares", m["name"].lower())
            self.assertTrue(gemini_planner._is_kid_safe_recipe(m))

        # Test Like + randomization + Un-like persistence
        liked_id = meals[0]["recipe_id"]
        prefs_up = gemini_planner.record_recipe_vote("test_user@example.com", liked_id, "up")
        self.assertIn(liked_id, prefs_up["liked"])

        # Across 6 different variety seeds, a single liked recipe should NOT be forced into 100% of menus
        appearances = 0
        for i in range(6):
            p_i = gemini_planner.build_weekly_plan(
                prompt,
                postal_code="28016",
                variety_seed=f"rand_seed_{i}",
                liked_recipe_ids=[liked_id],
                user_email="test_user@example.com",
            )
            if any(m["recipe_id"] == liked_id for m in p_i["meals"]):
                appearances += 1
        self.assertLess(appearances, 6, "Liked recipe should be randomized and not forced into every single menu")

        # Un-liking via vote='none' and via build_weekly_plan(liked_recipe_ids=[]) removes the recipe cleanly
        prefs_none = gemini_planner.record_recipe_vote("test_user@example.com", liked_id, "none")
        self.assertNotIn(liked_id, prefs_none["liked"])
        plan_after_unlike = gemini_planner.build_weekly_plan(
            prompt,
            postal_code="28016",
            variety_seed="after_unlike",
            liked_recipe_ids=[],
            user_email="test_user@example.com",
        )
        self.assertNotIn(liked_id, plan_after_unlike["recipe_preferences"]["liked"])

    def test_10_cookidoo_resync_replaces_old_recipes_on_day(self):
        """Verifies that re-syncing a day or weekly plan deletes previously scheduled recipes from Cookidoo Mi Semana and Shopping List."""
        calls = []

        def fake_urlopen(req, timeout=15):
            method = req.get_method()
            url = req.full_url
            body = json.loads(req.data.decode("utf-8")) if req.data else None
            calls.append((method, url, body))

            class FakeResp:
                status = 200

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *args):
                    pass

                def read(self_inner):
                    if method == "PUT" and url.endswith("/planning/es-ES/api/my-day"):
                        # Simulate Cookidoo additive PUT response returning both old and new recipe on that day
                        return json.dumps(
                            {
                                "content": {
                                    "id": body["dayKey"],
                                    "recipes": [
                                        {"id": "r_old_monday"},
                                        {"id": body["recipeIds"][0]},
                                    ],
                                }
                            }
                        ).encode("utf-8")
                    return b"{}"

            return FakeResp()

        orig_urlopen = urllib.request.urlopen
        try:
            urllib.request.urlopen = fake_urlopen
            removed_ids = cookidoo_service._cookidoo_replace_calendar_day_stdlib(
                access_token="fake_token",
                target_date=datetime.date(2026, 10, 19),
                desired_recipe_ids=["r_new_monday"],
                preloaded_week_map={
                    "2026-10-19": {
                        "recipes": ["r_old_monday", "r_another_old"],
                        "custom_recipes": [],
                    }
                },
                previously_scheduled_ids=["r_old_monday"],
            )
            self.assertIn("r_old_monday", removed_ids)
            self.assertIn("r_another_old", removed_ids)
            self.assertNotIn("r_new_monday", removed_ids)

            delete_urls = [u for (m, u, _) in calls if m == "DELETE"]
            self.assertIn(
                "https://cookidoo.es/planning/es-ES/api/my-day/2026-10-19/recipes/r_old_monday",
                delete_urls,
            )
            self.assertIn(
                "https://cookidoo.es/planning/es-ES/api/my-day/2026-10-19/recipes/r_another_old",
                delete_urls,
            )

            cookidoo_service._cookidoo_remove_shopping_list_recipes_stdlib(
                access_token="fake_token",
                recipe_ids=removed_ids,
            )
            post_Shopping_remove = [
                (m, u, b)
                for (m, u, b) in calls
                if m == "POST" and u.endswith("/shopping/es-ES/recipes/remove")
            ]
            self.assertEqual(len(post_Shopping_remove), 1)
            self.assertEqual(
                set(post_Shopping_remove[0][2]["recipeIDs"]),
                {"r_old_monday", "r_another_old"},
            )
        finally:
            urllib.request.urlopen = orig_urlopen

    def test_11_security_hardening_regression_suite(self):
        """Verifies credential protection, token encryption at rest, webhook token non-disclosure, SSRF guard, and auth gates."""
        # 1. Cookidoo password scrubbing & OAuth token encryption at rest
        enc = cookidoo_service._encrypt_secret("secret_oauth_token_123")
        self.assertTrue(enc.startswith("enc:v1:"))
        self.assertNotIn("secret_oauth_token_123", enc)
        self.assertEqual(cookidoo_service._decrypt_secret(enc), "secret_oauth_token_123")

        # Attempting to save a real password in _save_cookidoo_sessions must scrub the password and encrypt tokens on disk
        cookidoo_service._save_cookidoo_sessions(
            {
                "sec_test@example.com": {
                    "connected": True,
                    "email": "sec_test@example.com",
                    "password": "MySuperSecretPassword!99",
                    "access_token": "live_access_tok_abc",
                    "refresh_token": "live_refresh_tok_xyz",
                    "auth_mode": "live_api",
                }
            }
        )
        raw_disk = cookidoo_service.COOKIDOO_SESSION_FILE.read_text(encoding="utf-8")
        self.assertNotIn("MySuperSecretPassword!99", raw_disk)
        self.assertNotIn("live_access_tok_abc", raw_disk)
        self.assertNotIn("live_refresh_tok_xyz", raw_disk)
        self.assertIn("enc:v1:", raw_disk)

        loaded = cookidoo_service._load_cookidoo_sessions().get("sec_test@example.com") or {}
        self.assertIsNone(loaded.get("password"))
        self.assertEqual(loaded.get("access_token"), "live_access_tok_abc")
        self.assertEqual(loaded.get("refresh_token"), "live_refresh_tok_xyz")

        # 2. WhatsApp webhook GET without params must NOT leak the verify_token
        wa_status, wa_body = whatsapp_service.verify_whatsapp_webhook_get({})
        self.assertEqual(wa_status, 200)
        self.assertNotIn(whatsapp_service.DEFAULT_VERIFY_TOKEN, wa_body)

        # 3. Meta Cloud API SSRF / path-traversal guard on phone_number_id
        whatsapp_service.update_whatsapp_config(
            phone_number_id="../../etc/passwd",
            access_token="valid_token",
        )
        ssrf_res = whatsapp_service._send_meta_cloud_api_message(
            recipient_phone="+34600112233",
            reply_text="test",
        )
        self.assertFalse(ssrf_res["dispatched"])
        self.assertEqual(ssrf_res["reason"], "invalid_phone_number_id")

        # 4. SERVICE_ROLE normalization supports both 'campaign-library' and 'marketing'
        self.assertTrue(campaign_service.is_campaign_library_role("campaign-library"))
        self.assertTrue(campaign_service.is_campaign_library_role("marketing"))
        self.assertFalse(campaign_service.is_campaign_library_role("companion"))


if __name__ == "__main__":
    unittest.main()
