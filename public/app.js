/**
 * Mercadona AI Shopping Companion — Frontend Application
 * Powered by Google Gemini · Cookidoo API (Thermomix) · Mercadona ES API (tienda.mercadona.es)
 */

const PROFILES = [
  {
    id: "familias",
    name: "Familias",
    shortName: "Familias",
    household: "2 adultos · 1–2 niños",
    primaryNeed: "Variedad, platos para todos los gustos, ahorro y planificación sin fricción",
    icon: "FA",
  },
  {
    id: "saludables",
    name: "Saludables",
    shortName: "Saludables",
    household: "1–2 adultos",
    primaryNeed: "Nutrición transparente, productos frescos de temporada y control de calorías",
    icon: "SA",
  },
  {
    id: "rutina-rapida",
    name: "Rutina rápida",
    shortName: "Rutina rápida",
    household: "1–2 adultos",
    primaryNeed: "Rapidez entre semana (≤ 25 min), simplicidad en Thermomix y cero complicaciones",
    icon: "RR",
  },
  {
    id: "ahorro",
    name: "Ahorro",
    shortName: "Ahorro",
    household: "2 adultos · 1–2 niños",
    primaryNeed: "Presupuesto ajustado, máximo aprovechamiento de despensa y cero desperdicio",
    icon: "AH",
  },
];

const DEFAULT_CAMPAIGNS = [
  {
    id: "familias-semana-resuelta",
    title: "Tu semana familiar, resuelta",
    tagline: "Cinco cenas familiares variadas en Thermomix. Una sola cesta en Mercadona. Más tiempo libre.",
    category: "Familias",
    occasion: "Familias",
    profileId: "familias",
    badge: "Recomendado para Familias",
    status: "Activa",
    imageUrl: "/meals/lemon-hake-potatoes.webp",
    seedPrompt:
      "Planifica 5 cenas entre semana para 2 adultos y 1 niño. Mantén el presupuesto bajo 65€, prepara cada receta en 25 minutos o menos, incluye una cena de pescado y usa la pasta que ya tengo en casa.",
    mealCount: 5,
    maxBudget: 65,
    maxMinutes: 25,
    maxCaloriesPerServing: null,
  },
  {
    id: "saludables-ligeras-equilibradas",
    title: "Cenas ligeras y equilibradas",
    tagline: "Cinco cenas saludables diseñadas por nutricionistas con calorías y presupuesto bajo control.",
    category: "Saludables",
    occasion: "Saludables",
    profileId: "saludables",
    badge: "Objetivo Saludable · ≤ 450 kcal",
    status: "Activa",
    imageUrl: "/meals/pasta-chickpea-salad.webp",
    seedPrompt:
      "Planifica 5 cenas saludables para 2 adultos. Mantén el presupuesto bajo 60€, máximo 30 minutos por receta y menos de 450 kcal por ración.",
    mealCount: 5,
    maxBudget: 60,
    maxMinutes: 30,
    maxCaloriesPerServing: 450,
  },
  {
    id: "rutina-rapida-25min",
    title: "Cena lista en menos de 25 minutos",
    tagline: "Cinco cenas exprés para semanas intensas sin renunciar a comer casero.",
    category: "Rutina rápida",
    occasion: "Rutina rápida",
    profileId: "rutina-rapida",
    badge: "Ideal para semanas con prisa",
    status: "Activa",
    imageUrl: "/meals/quick-broccoli-salad.webp",
    seedPrompt:
      "Planifica 5 cenas rápidas para 2 adultos. Presupuesto máximo de 50€, máximo 25 minutos por receta, sin frutos secos y usa las espinacas y el arroz que ya tengo en casa.",
    mealCount: 5,
    maxBudget: 50,
    maxMinutes: 25,
    maxCaloriesPerServing: null,
  },
  {
    id: "ahorro-despensa-inteligente",
    title: "Aprovecha tu despensa, compra solo lo justo",
    tagline: "Menú semanal de máximo ahorro y cero desperdicio que descuenta lo que ya tienes en casa.",
    category: "Ahorro",
    occasion: "Ahorro",
    profileId: "ahorro",
    badge: "Máximo ahorro · Cero desperdicio",
    status: "Activa",
    imageUrl: "/meals/chickpea-spinach-tomato-rice.webp",
    seedPrompt:
      "Planifica 5 cenas económicas para 2 adultos y 2 niños con presupuesto máximo de 48€, en 30 minutos o menos, sin lactosa y usa los huevos y las patatas que ya tengo en casa.",
    mealCount: 5,
    maxBudget: 48,
    maxMinutes: 30,
    maxCaloriesPerServing: null,
  },
];

const FOLLOW_UP_PROMPTS = [
  "Haz el menú sin gluten y máximo 400 kcal por ración",
  "Incluye pescado y usa el arroz y las espinacas que ya tengo en casa",
  "Reduce el presupuesto por debajo de 45€ en 25 minutos o menos",
];

const state = {
  auth: {
    checked: false,
    authenticated: false,
    user: null,
    iapEmail: null,
    allowedUsers: [],
    googleClientId: "",
    error: "",
  },
  campaignLibraryUrl: "https://campaign-library-66087676067.europe-west1.run.app",
  campaigns: [...DEFAULT_CAMPAIGNS],
  activeTab: "planner", // "planner" | "catalog" | "sources"
  profileId: "familias",
  selectedCampaignId: DEFAULT_CAMPAIGNS[0].id,
  prompt: DEFAULT_CAMPAIGNS[0].seedPrompt,
  detectedPills: [
    "5 cenas",
    "≤ 25 min",
    "≤ €65",
    "2 adultos + 1 niño",
    "Incluye pescado",
    "En casa: pasta",
  ],
  postalCode: "28001",
  warehouse: "mad1",
  centerName: "Madrid · Colmena Mercadona Online (mad1)",
  deliveryAvailable: true,
  verifyingStock: false,
  lastStockVerifiedAt: null,
  catalogSource: "live",
  loading: false,
  swappingRecipeId: null,
  error: null,
  plan: null,
  previousPlan: null,
  varietyCounter: 1,
  showTrace: false,
  sentThermomixIds: {},
  cookidooModalOpen: false,
  cookidooEmail: "",
  cookidooPassword: "",
  cookidooVerifying: false,
  cookidooVerifyError: "",
  cookidooSchedulingWeek: false,
  cookidooWeekMode: "current", // "current" | "next"
  cookidooSession: {
    connected: false,
    live_authenticated: false,
    email: null,
    masked_email: null,
    device_name: null,
    auth_mode: null,
    planner_url: "https://cookidoo.es/planning/es-ES/my-week",
    last_scheduled_week: null,
    week_preview_current: null,
    week_preview_next: null,
  },
  cookidooScheduledResult: null,
  diaSession: {
    connected: false,
    customer_id: null,
    warehouse: null,
    has_refresh_token: false,
    masked_token: null,
  },
  diaModalOpen: false,
  diaAuthInput: "",
  diaSyncMode: "add", // "add" | "replace"
  diaVerifying: false,
  diaVerifyError: "",
  cartAddedResult: null,
  addingToCart: false,
  catalogData: null,
  catalogSearch: "",
  catalogPage: 1,
  recipesSearch: "",
  recipesPage: 1,
  recipePreferences: {
    liked: [],
    disliked: [],
  },
  videoModalOpen: false,
  whatsappOpen: false,
  whatsappConfigOpen: false,
  whatsappSending: false,
  whatsappListeningVoice: false,
  whatsappInput: "",
  whatsappState: {
    webhook_url: `${window.location.origin}/api/whatsapp/webhook`,
    verify_token: "mercadona-whatsapp-2026",
    phone_number_id: "",
    has_access_token: false,
    recipient_phone: "+34 600 000 000",
    webhook_stats: { total_received: 0 },
    plan_version: 1,
    messages: [],
    share_wa_url: "https://wa.me/",
  },
  fridgeVisionLoading: false,
  fridgeVisionResult: null,
  recalculatingBasket: false,
  deliveryMode: "home_delivery", // "home_delivery" | "click_and_car"
  selectedClickCarSlot: "Hoy 18:00 – 20:00 h (Tramo Mercadona Online)",
  toast: null,
};

const RECIPE_PREFS_STORAGE_KEY = "eci_recipe_preferences_v2";
const ACTIVE_PLAN_STORAGE_KEY = "eci_active_plan_v5";

function loadLocalRecipePreferences() {
  try {
    window.localStorage.removeItem("dia_active_plan_v1");
    window.localStorage.removeItem("eci_active_plan_v1");
    window.localStorage.removeItem("eci_active_plan_v2");
    window.localStorage.removeItem("eci_active_plan_v3");
    window.localStorage.removeItem("eci_active_plan_v4");
    const raw = window.localStorage.getItem(RECIPE_PREFS_STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    const liked = Array.isArray(parsed?.liked) ? parsed.liked.map(String) : [];
    const disliked = Array.isArray(parsed?.disliked) ? parsed.disliked.map(String) : [];
    const dislikedSet = new Set(disliked);
    state.recipePreferences = {
      liked: Array.from(new Set(liked)).filter((id) => !dislikedSet.has(id)),
      disliked: Array.from(new Set(disliked)),
    };
  } catch (e) {
    // Ignore localStorage parse errors
  }
}

function saveLocalRecipePreferences(prefs) {
  const liked = Array.isArray(prefs?.liked) ? prefs.liked.map(String) : [];
  const disliked = Array.isArray(prefs?.disliked) ? prefs.disliked.map(String) : [];
  const dislikedSet = new Set(disliked);
  state.recipePreferences = {
    liked: Array.from(new Set(liked)).filter((id) => !dislikedSet.has(id)),
    disliked: Array.from(new Set(disliked)),
  };
  try {
    window.localStorage.setItem(RECIPE_PREFS_STORAGE_KEY, JSON.stringify(state.recipePreferences));
  } catch (e) {
    // Ignore localStorage write errors
  }
}

loadLocalRecipePreferences();

function saveLocalActivePlan() {
  try {
    window.localStorage.removeItem("dia_active_plan_v1");
    if (!state.plan) {
      window.localStorage.removeItem(ACTIVE_PLAN_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(
      ACTIVE_PLAN_STORAGE_KEY,
      JSON.stringify({
        savedAt: Date.now(),
        plan: state.plan,
        prompt: state.prompt,
        postalCode: state.postalCode,
        warehouse: state.warehouse,
        profileId: state.profileId,
        selectedCampaignId: state.selectedCampaignId,
        detectedPills: state.detectedPills,
      })
    );
  } catch (e) {
    // Ignore storage quota or private mode errors
  }
}

function restoreLocalActivePlan() {
  try {
    window.localStorage.removeItem("dia_active_plan_v1");
    window.localStorage.removeItem("eci_active_plan_v1");
    window.localStorage.removeItem("eci_active_plan_v2");
    window.localStorage.removeItem("eci_active_plan_v3");
    window.localStorage.removeItem("eci_active_plan_v4");
    const raw = window.localStorage.getItem(ACTIVE_PLAN_STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    const maxAgeMs = 12 * 60 * 60 * 1000; // 12 hours
    if (!parsed || !parsed.plan || !parsed.savedAt || Date.now() - parsed.savedAt > maxAgeMs) {
      window.localStorage.removeItem(ACTIVE_PLAN_STORAGE_KEY);
      return;
    }
    state.plan = parsed.plan;
    if (state.plan && Array.isArray(state.plan.meals)) {
      state.plan.meals.forEach((m) => {
        m.liked_by_user = state.recipePreferences.liked.includes(m.recipe_id);
      });
    }
    if (parsed.prompt) state.prompt = parsed.prompt;
    if (parsed.postalCode) state.postalCode = parsed.postalCode;
    if (parsed.warehouse) state.warehouse = parsed.warehouse;
    if (parsed.profileId) state.profileId = parsed.profileId;
    if (parsed.selectedCampaignId) state.selectedCampaignId = parsed.selectedCampaignId;
    if (Array.isArray(parsed.detectedPills) && parsed.detectedPills.length > 0) {
      state.detectedPills = parsed.detectedPills;
    }
  } catch (e) {
    // Ignore storage read errors
  }
}

function buildDiaBookmarkletHref() {
  const appOrigin = window.location.origin;
  return (
    `javascript:(function(){` +
    `try{` +
    `if(location.hostname.indexOf("mercadona.es")===-1){` +
    `if(confirm("Para vincular tu carrito, primero debes estar en tienda.mercadona.es con tu sesion iniciada. ¿Quieres abrir tienda.mercadona.es ahora? Cuando estes alli, vuelve a pulsar este marcador.")){` +
    `location.href="https://tienda.mercadona.es/";` +
    `}` +
    `return;` +
    `}` +
    `var raw=localStorage.getItem("MO-user");` +
    `var parsed=null;` +
    `try{parsed=raw?JSON.parse(raw):null;}catch(e){}` +
    `if(!raw||!parsed||(!parsed.token&&!parsed.refreshToken)){` +
    `alert("No se ha detectado una sesion iniciada en tienda.mercadona.es. Por favor, inicia sesion en tu cuenta de Mercadona y vuelve a pulsar este marcador.");` +
    `return;` +
    `}` +
    `var payload=JSON.stringify({mo_user:parsed,cookie:document.cookie||"",ts:Date.now()});` +
    `var b64=btoa(unescape(encodeURIComponent(payload))).split("+").join("-").split("/").join("_").split("=").join("");` +
    `location.href=${JSON.stringify(appOrigin)}+"/#mercadona_connect="+b64;` +
    `}catch(err){` +
    `alert("Error al leer la sesion de Mercadona: "+err.message);` +
    `}` +
    `})();`
  );
}

function buildDiaConsoleSnippet() {
  const appOrigin = window.location.origin;
  return `(function(){var r=localStorage.getItem("MO-user");if(!r){alert("Inicia sesion primero en tienda.mercadona.es");return;}var p=JSON.stringify({mo_user:JSON.parse(r),cookie:document.cookie||""});var b=btoa(unescape(encodeURIComponent(p))).split("+").join("-").split("/").join("_").split("=").join("");location.href=${JSON.stringify(appOrigin)}+"/#mercadona_connect="+b;})();`;
}

function buildPrecreatedCartBookmarkletHref(cartResult) {
  const script = cartResult && (cartResult.mercadona_browser_sync_script || cartResult.dia_browser_sync_script || cartResult.eci_browser_sync_script);
  if (!script) {
    return buildDiaBookmarkletHref();
  }
  return "javascript:" + encodeURIComponent(script);
}

async function verifyLiveBasketStock() {
  if (!state.plan || !Array.isArray(state.plan.basket) || state.verifyingStock) return;
  state.verifyingStock = true;
  render();
  try {
    const productIds = state.plan.basket.map((b) => b.product_id || b.id).filter(Boolean);
    const res = await fetch("/api/eci/verify-stock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        postal_code: state.postalCode,
        product_ids: productIds,
      }),
    });
    const data = await res.json();
    if (res.ok && Array.isArray(data.items)) {
      const byId = {};
      data.items.forEach((it) => {
        byId[it.id] = it;
      });
      let replacedCount = 0;
      state.plan.basket = state.plan.basket.map((item) => {
        const check = byId[item.product_id];
        if (!check) return { ...item, stock_verified_live: true };
        if (!check.in_stock && check.replacement) {
          replacedCount += 1;
          const rep = check.replacement;
          const newTotal = Number((rep.price * item.quantity).toFixed(2));
          return {
            ...item,
            product_id: rep.id,
            name: rep.name,
            unit_price: rep.price,
            line_total: newTotal,
            unit: rep.unit || item.unit,
            thumbnail: rep.thumbnail || item.thumbnail,
            share_url: rep.share_url || item.share_url,
            substituted_from: item.name,
            stock_verified_live: true,
          };
        }
        return {
          ...item,
          unit_price: check.price || item.unit_price,
          line_total: Number(((check.price || item.unit_price) * item.quantity).toFixed(2)),
          stock_verified_live: true,
        };
      });
      state.plan.total = Number(
        state.plan.basket.reduce((acc, it) => acc + Number(it.line_total || 0), 0).toFixed(2)
      );
      state.lastStockVerifiedAt = new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
      if (data.center_name) state.centerName = data.center_name;
      if (typeof data.delivery_available === "boolean") state.deliveryAvailable = data.delivery_available;
      saveLocalActivePlan();
      showToast(
        `✓ Stock en tiempo real verificado (CP ${data.postal_code})`,
        replacedCount > 0
          ? `Se verificaron ${data.verified_count} productos en ${data.center_name || data.warehouse} y se sustituyeron automáticamente ${replacedCount} agotados.`
          : `Los ${data.verified_count} productos de tu cesta están en stock para envío en ${data.center_name || data.warehouse}.`
      );
    }
  } catch (err) {
    showToast("Error al verificar stock", "No se pudo consultar el stock en vivo en este momento.");
  } finally {
    state.verifyingStock = false;
    render();
  }
}

async function voteRecipe(recipeId, voteType, recipeName) {
  if (!recipeId || state.loading || state.swappingRecipeId) return;
  const mealInPlan = state.plan?.meals?.find((m) => m.recipe_id === recipeId);
  const isCurrentlyLiked =
    state.recipePreferences.liked.includes(recipeId) || Boolean(mealInPlan?.liked_by_user);
  const isCurrentlyDisliked = state.recipePreferences.disliked.includes(recipeId);

  let effectiveVote = voteType;
  if (voteType === "up" && isCurrentlyLiked) {
    effectiveVote = "none";
  } else if (voteType === "down" && isCurrentlyDisliked) {
    effectiveVote = "none";
  }

  const liked = state.recipePreferences.liked.filter((id) => id !== recipeId);
  const disliked = state.recipePreferences.disliked.filter((id) => id !== recipeId);
  if (effectiveVote === "up") {
    liked.push(recipeId);
  } else if (effectiveVote === "down") {
    disliked.push(recipeId);
  }
  saveLocalRecipePreferences({ liked, disliked });

  if (state.plan && Array.isArray(state.plan.meals)) {
    state.plan.meals.forEach((m) => {
      if (m.recipe_id === recipeId) {
        m.liked_by_user = effectiveVote === "up";
      }
    });
    state.plan.recipe_preferences = {
      liked: [...state.recipePreferences.liked],
      disliked: [...state.recipePreferences.disliked],
    };
    saveLocalActivePlan();
  }
  render();

  try {
    const res = await fetch("/api/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recipe_id: recipeId, vote: effectiveVote }),
    });
    if (res.ok) {
      const serverPrefs = await res.json();
      saveLocalRecipePreferences(serverPrefs);
      if (state.plan && Array.isArray(state.plan.meals)) {
        state.plan.meals.forEach((m) => {
          m.liked_by_user = state.recipePreferences.liked.includes(m.recipe_id);
        });
        saveLocalActivePlan();
      }
    }
  } catch (e) {
    // Keep local preferences if network request fails
  }

  if (effectiveVote === "up") {
    showToast(
      `👍 Añadida a tus favoritas (pulsa 👍 de nuevo para quitarla)`,
      `'${recipeName}' e ingredientes similares se usarán como inspiración en futuros menús sin repetir siempre el mismo plato.`
    );
    render();
  } else if (effectiveVote === "none") {
    showToast(`👍 Like eliminado`, `Se ha quitado '${recipeName}' de tus recetas favoritas.`);
    render();
  } else if (effectiveVote === "down") {
    // Automatically replace the disliked recipe in the active menu
    await swapRecipe(recipeId, { autoFromDislike: true, dislikedRecipeName: recipeName });
  }
}

async function clearRecipePreferences() {
  saveLocalRecipePreferences({ liked: [], disliked: [] });
  try {
    await fetch("/api/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "clear" }),
    });
  } catch (e) {
    // Ignore error
  }
  showToast("Preferencias reiniciadas", "Se ha limpiado tu historial de recetas favoritas y descartadas.");
  render();
}

async function fetchWhatsAppState({ silent = false } = {}) {
  try {
    const res = await fetch("/api/whatsapp/state");
    if (!res.ok) return;
    const data = await res.json();
    const prevVersion = state.whatsappState?.plan_version || 1;
    state.whatsappState = {
      ...state.whatsappState,
      ...data,
    };
    if (data.active_plan && data.plan_version && data.plan_version > prevVersion) {
      state.plan = data.active_plan;
      saveLocalActivePlan();
      if (!silent) {
        showToast(
          "💬 Menú sincronizado desde WhatsApp",
          "Se han aplicado los cambios recibidos por el Webhook de WhatsApp Business en tiempo real."
        );
      }
      render();
    } else if (!silent) {
      render();
    }
  } catch (e) {
    // Ignore background poll errors
  }
}

async function sendWhatsAppMessage(rawText, options = {}) {
  const text = String(rawText ?? state.whatsappInput ?? "").trim();
  const imageBase64 = options.imageBase64 || null;
  if ((!text && !imageBase64) || state.whatsappSending) return;

  state.whatsappSending = true;
  if (!options.keepInput) {
    state.whatsappInput = "";
  }
  render();

  try {
    const res = await fetch("/api/whatsapp/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        type: options.type || (imageBase64 ? "image" : "text"),
        imageBase64,
        postalCode: state.postalCode,
        currentPlan: state.plan,
      }),
    });
    const data = await res.json();
    if (res.ok) {
      if (data.plan) {
        state.previousPlan = state.plan;
        state.plan = data.plan;
        if (data.plan.cookidoo_scheduled_week) {
          state.cookidooScheduledResult = data.plan.cookidoo_scheduled_week;
          (data.plan.cookidoo_scheduled_week.days || []).forEach((d) => {
            if (d.recipe_id) {
              state.sentThermomixIds[d.recipe_id] = d.short_label || d.day || true;
            }
          });
        }
        saveLocalActivePlan();
      }
      state.whatsappState = {
        ...state.whatsappState,
        messages: data.messages || state.whatsappState.messages,
        plan_version: data.plan_version || state.whatsappState.plan_version,
        share_wa_url: data.share_wa_url || state.whatsappState.share_wa_url,
        webhook_url: data.webhook_url || state.whatsappState.webhook_url,
        webhook_stats: data.webhook_stats || state.whatsappState.webhook_stats,
      };
      if (data.action && data.action !== "view_menu") {
        showToast(
          "💬 Cambio aplicado desde WhatsApp",
          `Tu menú semanal y tu cesta de Mercadona (${formatEUR(state.plan?.total || 0)}) se han actualizado en vivo.`
        );
      }
    }
  } catch (e) {
    showToast("Error en WhatsApp Copilot", "No se pudo procesar el mensaje en este momento.");
  } finally {
    state.whatsappSending = false;
    render();
    setTimeout(() => {
      const chatBox = document.getElementById("wa-chat-messages");
      if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;
    }, 50);
  }
}

async function simulateExternalWebhookPost(provider = "twilio") {
  if (state.whatsappSending) return;
  state.whatsappSending = true;
  render();
  try {
    let res;
    if (provider === "twilio") {
      const formBody = new URLSearchParams({
        From: "whatsapp:+34600123456",
        Body: "Cambia el miércoles por pescado y el viernes somos 6 personas",
      }).toString();
      res = await fetch("/api/whatsapp/webhook", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formBody,
      });
    } else {
      const metaPayload = {
        object: "whatsapp_business_account",
        entry: [
          {
            id: "ECI_WABA_2026",
            changes: [
              {
                field: "messages",
                value: {
                  messages: [
                    {
                      from: "34600998877",
                      type: "interactive",
                      interactive: {
                        button_reply: { id: "cmd:gourmet", title: "🥂 Modo Gourmet" },
                      },
                    },
                  ],
                },
              },
            ],
          },
        ],
      };
      res = await fetch("/api/whatsapp/webhook", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(metaPayload),
      });
    }
    if (res && res.ok) {
      await fetchWhatsAppState({ silent: true });
      if (state.whatsappState.active_plan) {
        state.plan = state.whatsappState.active_plan;
        saveLocalActivePlan();
      }
      showToast(
        provider === "twilio"
          ? "✓ Webhook Twilio TwiML ejecutado en vivo"
          : "✓ Webhook Meta Cloud API ejecutado en vivo",
        "El endpoint /api/whatsapp/webhook ha procesado el evento externo y sincronizado el menú semanal."
      );
    }
  } catch (e) {
    showToast("Error en prueba de Webhook", "No se pudo invocar /api/whatsapp/webhook.");
  } finally {
    state.whatsappSending = false;
    render();
    setTimeout(() => {
      const chatBox = document.getElementById("wa-chat-messages");
      if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;
    }, 60);
  }
}

async function saveWhatsAppConfig(configUpdates) {
  try {
    const res = await fetch("/api/whatsapp/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(configUpdates),
    });
    if (res.ok) {
      const data = await res.json();
      state.whatsappState = {
        ...state.whatsappState,
        ...data,
      };
      if (configUpdates && configUpdates.reset_chat) {
        showToast("Conversación vaciada", "El historial de mensajes de WhatsApp se ha limpiado.");
      } else {
        showToast(
          "Configuración de Webhook guardada",
          "Los parámetros de WhatsApp Business Cloud API / Twilio están activos."
        );
      }
      render();
    }
  } catch (e) {
    showToast("Error al actualizar WhatsApp", "Inténtalo de nuevo.");
  }
}

function startWhatsAppVoiceNote() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    try {
      const recognition = new SpeechRecognition();
      recognition.lang = "es-ES";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      state.whatsappListeningVoice = true;
      render();
      recognition.onresult = (event) => {
        const transcript = event.results?.[0]?.[0]?.transcript || "";
        state.whatsappListeningVoice = false;
        if (transcript) {
          sendWhatsAppMessage(`🎤 "${transcript}"`, { type: "audio" });
        } else {
          render();
        }
      };
      recognition.onerror = () => {
        state.whatsappListeningVoice = false;
        sendWhatsAppMessage(
          '🎤 "Oye, el viernes vienen amigos a cenar, pon raciones para 6 personas y cambia el miércoles por pescado"',
          { type: "audio" }
        );
      };
      recognition.onend = () => {
        if (state.whatsappListeningVoice) {
          state.whatsappListeningVoice = false;
          render();
        }
      };
      recognition.start();
      return;
    } catch (e) {
      // Fallback below
    }
  }
  sendWhatsAppMessage(
    '🎤 "Oye, el viernes vienen amigos a cenar, pon raciones para 6 personas y cambia el miércoles por pescado"',
    { type: "audio" }
  );
}

async function recalculateBasket(options = {}) {
  if (!state.plan || state.recalculatingBasket) return;
  state.recalculatingBasket = true;
  render();
  try {
    const res = await fetch("/api/basket/recalculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        currentPlan: state.plan,
        postalCode: state.postalCode,
        basketTier: options.basketTier !== undefined ? options.basketTier : state.plan.basket_tier,
        dayServings: options.dayServings !== undefined ? options.dayServings : state.plan.day_servings,
        customCounterCuts:
          options.customCounterCuts !== undefined ? options.customCounterCuts : state.plan.custom_counter_cuts,
        includeSommelierItem:
          options.includeSommelierItem !== undefined
            ? options.includeSommelierItem
            : Boolean(state.plan.sommelier_pairing?.included),
      }),
    });
    const data = await res.json();
    if (res.ok && data.meals) {
      state.plan = data;
      state.cartAddedResult = null;
      saveLocalActivePlan();
      if (options.toastTitle) {
        showToast(options.toastTitle, options.toastBody || `Cesta actualizada: ${formatEUR(data.total)}`);
      }
    }
  } catch (e) {
    showToast("Error al recalcular cesta", "No se pudo actualizar la cesta en este momento.");
  } finally {
    state.recalculatingBasket = false;
    render();
  }
}

async function runFridgeVision({ imageBase64 = null, mimeType = "image/jpeg", presetId = null } = {}) {
  if (state.fridgeVisionLoading) return;
  state.fridgeVisionLoading = true;
  render();
  try {
    const res = await fetch("/api/fridge-vision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        imageBase64,
        mimeType,
        presetId,
        currentPrompt: state.prompt,
        postalCode: state.postalCode,
        currentPlan: state.plan,
      }),
    });
    const data = await res.json();
    if (res.ok && data.plan) {
      state.fridgeVisionResult = data.fridge_vision;
      state.prompt = data.updated_prompt || state.prompt;
      state.detectedPills = data.plan.constraint_pills || detectPillsClientSide(state.prompt);
      state.previousPlan = state.plan;
      state.plan = data.plan;
      saveLocalActivePlan();
      const kwList = (data.fridge_vision?.keywords || []).join(", ");
      showToast(
        `📸 Nevera Vision aplicada (-${formatEUR(data.fridge_vision?.estimated_savings_eur || 8.45)})`,
        `Google Gemini ha detectado: ${kwList}. Se han priorizado recetas que los aprovechan y se han descontado de tu cesta Mercadona.`
      );
      setTimeout(() => {
        document.querySelector(".experience-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 120);
    } else {
      showToast("Error en Nevera Vision", data.error || "No se pudo analizar la imagen.");
    }
  } catch (e) {
    showToast("Error en Nevera Vision", "No se pudo conectar con Google Gemini Multimodal.");
  } finally {
    state.fridgeVisionLoading = false;
    render();
  }
}

function formatWhatsAppMarkdown(raw) {
  const escaped = escapeHtml(raw || "");
  return escaped
    .replace(/\*([^*\n]+)\*/g, "<strong>$1</strong>")
    .replace(/_([^_\n]+)_/g, "<em>$1</em>")
    .replace(/\n/g, "<br />");
}

function getActiveCampaigns() {
  const active = (state.campaigns || []).filter((c) => !c.status || c.status === "Activa");
  return active.length > 0 ? active : DEFAULT_CAMPAIGNS;
}

function formatEUR(value) {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(Number(value || 0));
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sanitizeUrl(url, fallback = "#") {
  const raw = String(url ?? "").trim();
  if (!raw) return fallback;
  if (raw.startsWith("/") && !raw.startsWith("//")) return raw;
  try {
    const parsed = new URL(raw, window.location.origin);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      return parsed.href;
    }
  } catch (e) {
    // Ignore malformed URL
  }
  return fallback;
}

function showToast(title, body) {
  state.toast = { title, body };
  render();
  setTimeout(() => {
    if (state.toast && state.toast.title === title) {
      state.toast = null;
      render();
    }
  }, 5500);
}

const OFF_TOPIC_REGEX = /\b(?:ignora\s+(?:las\s+|tus\s+)?instrucciones|olvida\s+(?:las\s+|tus\s+)?instrucciones|ignore\s+(?:all\s+|previous\s+)?instructions|system\s+prompt|act[uú]a\s+como|jailbreak|python|javascript|typescript|java\b|c\+\+|html|css|sql\b|react\b|c[oó]digo|script\b|algoritmo|compilar|regex|ecuaci[oó]n|derivada|integral\s+de|matem[aá]ticas|teorema|poema|poes[ií]a|chiste|canci[oó]n|novela|ensayo\s+sobre|redacci[oó]n|curr[ií]culum|hor[oó]scopo|traduce|traducir|resumen\s+del\s+libro|presidente|elecciones|pol[ií]tica|gobierno|ministro|diputado|f[uú]tbol|real\s+madrid|barcelona\s+fc|champions\s+league|mundial\s+de|nba\b|f[oó]rmula\s*1|capital\s+de|qui[eé]n\s+gan[oó]|qui[eé]n\s+fue|qui[eé]n\s+es\s+el|cu[aá]ntos\s+habitantes|qu[eé]\s+tiempo\s+hace|pron[oó]stico\s+del\s+tiempo|clima\s+en|bitcoin|criptomoneda|ethereum|bolsa\s+de\s+valores|hipoteca|declaraci[oó]n\s+de\s+la\s+renta)\b/i;

const MEAL_PLANNING_DOMAIN_REGEX = /(?:\b(?:cena|cenas|comida|comidas|men[uú]|men[uú]s|plan|planifica\w*|semana\w*|d[ií]as?|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|desayuno|almuerzo|merienda|plato|platos|receta|recetas|raci[oó]n|raciones|dinner\w*|meal\w*|weekly|recipe\w*|cocin\w*|prepar\w*|thermomix|cookidoo|varoma|horno|vapor|plancha|guiso|estofado|asad\w*|saltead\w*|minutos?|mins?|r[aá]pid\w*|f[aá]cil\w*|expr[eé]s|dia|alacena|lactea|cesta|carrito|compra\w*|presupuesto|euros?|eur|ahorr\w*|barat\w*|econ[oó]mic\w*|adultos?|ni[ñn]os?|familia\w*|personas?|pareja|casa|despensa|nevera|tengo|aprovech\w*|ingredientes?|kcal|calor[ií]as?|saludable\w*|san[oa]s?|liger[oa]s?|dieta|nutrici[oó]n|prote[ií]nas?|fibra|vegetarian[oa]s?|vegan[oa]s?|alergi\w*|al[eé]rgic\w*|intoleran\w*|sin\s+gluten|cel[ií]ac\w*|sin\s+lactosa|l[aá]cteos?|frutos?\s+secos?|cacahuetes?|mariscos?|crust[aá]ceos?|moluscos?|soja|s[eé]samo|apio|mostaza|altramuces|sulfitos|pollo|pavo|ternera|cerdo|carne|pescado|merluza|salm[oó]n|bacalao|at[uú]n|dorada|lubina|gambas?|langostinos?|mejill\w*|calamar\w*|sepia|pulpo|huevos?|leche|queso|yogur|nata|mantequilla|pasta|macarrones|espaguetis|tallarines|fideos|lasa[ñn]a|[ñn]oquis|arroz|risotto|paella|quinoa|cusc[uú]s|avena|pan|harina|pizza|quiche|empanada|fajitas?|tacos?|wraps?|tortilla|lentejas|garbanzos|alubias|jud[ií]as|guisantes|tofu|edamame|verduras?|hortalizas?|ensaladas?|sopas?|cremas?|pur[eé]s?|caldos?|gazpacho|salmorejo|pisto|patatas?|boniato|tomates?|cebollas?|ajos?|pimientos?|zanahorias?|calabac[ií]n|berenjenas?|espinacas?|br[oó]coli|coliflor|kale|esp[aá]rragos?|champi[ñn]\w*|setas|aguacates?|pepinos?|lechuga|brotes|aceitunas?|aceite|lim[oó]n|naranja|manzanas?|pl[aá]tanos?|mango|fresas?|frutas?|jam[oó]n|beicon|chorizo|lomo|solomillo|carrilleras?|alb[oó]ndigas?|hamburguesas?|croquetas?|salsa|curry|pesto|hummus)\b|€)/i;

const OUT_OF_SCOPE_PROMPT_MESSAGE =
  "Esta petición no está relacionada con la planificación de menús semanales. Por favor, indica tus preferencias de comidas, ingredientes, número de días, miembros de la familia, alergias, tiempo de cocina o presupuesto en Mercadona.";

function validateMealPlanningPrompt(text) {
  const cleaned = String(text || "").trim();
  if (cleaned.length < 4) {
    return { valid: false, message: OUT_OF_SCOPE_PROMPT_MESSAGE };
  }
  if (OFF_TOPIC_REGEX.test(cleaned)) {
    return { valid: false, message: OUT_OF_SCOPE_PROMPT_MESSAGE };
  }
  if (!MEAL_PLANNING_DOMAIN_REGEX.test(cleaned)) {
    return { valid: false, message: OUT_OF_SCOPE_PROMPT_MESSAGE };
  }
  return { valid: true, message: "" };
}

function sanitizeRecipeDescription(desc) {
  const raw = String(desc || "").trim();
  const stripped = raw
    .replace(/^Receta\s+oficial\s+de\s+Thermomix\s+Cookidoo\s*(?:\([^)]*\))?\s*(?:con\s+)?/i, "")
    .trim();
  if (stripped && stripped !== raw) {
    return `Plato casero elaborado con ${stripped.charAt(0).toLowerCase() + stripped.slice(1)}`;
  }
  return stripped;
}

function detectPillsClientSide(text) {
  const pills = [];
  const mMeals = text.match(
    /\b(one|two|three|four|five|six|seven|un|una|uno|dos|tres|cuatro|cinco|seis|siete|[1-7])\s+(?:(?:weekday|weeknight|vegetarian|quick|healthy|family|rápidas|rapidas|saludables|familiares|entre\s+semana)\s+){0,3}(?:dinners?|meals?|cenas?|comidas?|días?|dias?)\b/i
  );
  const wordMap = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, un: 1, una: 1, uno: 1, dos: 2, tres: 3, cuatro: 4, cinco: 5, seis: 6, siete: 7 };
  const mealCount = mMeals ? wordMap[mMeals[1].toLowerCase()] || Number(mMeals[1]) || 5 : 5;
  pills.push(`${mealCount} ${mealCount === 1 ? "cena" : "cenas"}`);

  const mMin = text.match(/\b(\d{1,3})\s*(?:minutes?|mins?|minutos?|min)\b/i);
  const isQuick = /\b(?:r[aá]pid[oa]s?|expr[eé]s|quick)\b/i.test(text);
  pills.push(`≤ ${mMin ? mMin[1] : isQuick ? 25 : 30} min`);

  const mCal = text.match(/\b(\d{2,4})\s*(?:kcal|calorías|calorias|calories|cal)\b/i);
  if (mCal) pills.push(`≤ ${mCal[1]} kcal/ración`);

  const mBud = text.match(/(?:€\s*(\d+(?:[.,]\d{1,2})?)|(\d+(?:[.,]\d{1,2})?)\s*(?:€|euros?|eur))/i);
  pills.push(`≤ €${mBud ? mBud[1] || mBud[2] : 65}`);

  const mAdults = text.match(/\b(one|two|three|four|five|six|un|una|uno|dos|tres|cuatro|cinco|seis|[1-6])\s+(?:adults?|adultos?)\b/i);
  const mKids = text.match(/\b(one|two|three|four|five|six|un|una|uno|dos|tres|cuatro|cinco|seis|[1-6])\s+(?:children|child|kids?|niños?|ninos?|niñas?|hijos?|peques)\b/i);
  const adults = mAdults ? wordMap[mAdults[1].toLowerCase()] || Number(mAdults[1]) || 2 : 2;
  const kids = mKids ? wordMap[mKids[1].toLowerCase()] || Number(mKids[1]) || 0 : mAdults ? 0 : 1;
  pills.push(`${adults} ${adults === 1 ? "adulto" : "adultos"}${kids > 0 ? ` + ${kids} ${kids === 1 ? "niño" : "niños"}` : ""}`);

  if (
    kids > 0 ||
    /\b(?:ni[ñn]os?\s+peque[ñn]os?|peques|beb[eé]s?|infantil\w*|apt[oa]s?\s+para\s+ni[ñn]os?|suaves?\s+para\s+ni[ñn]os?)\b/i.test(text)
  ) {
    pills.push("👶 Recetas aptas para niños");
  }

  if (/\b(?:vegetariano|vegetariana|vegetarian|sin\s+carne)\b/i.test(text)) {
    pills.push("Vegetariano");
  } else {
    const mMeatCnt = text.match(/\b(one|two|three|four|five|un|una|uno|dos|tres|cuatro|cinco|[1-5])\s+(?:(?:cenas?|comidas?|platos?|recetas?)\s+)?(?:de\s+|con\s+)(?:carne|pollo|pavo|ternera|cerdo|meat)\b/i);
    if (mMeatCnt) {
      const mc = wordMap[mMeatCnt[1].toLowerCase()] || Number(mMeatCnt[1]) || 1;
      pills.push(`${mc} ${mc === 1 ? "cena" : "cenas"} de carne`);
    }
  }

  const mFishCnt = text.match(/\b(one|two|three|four|five|un|una|uno|dos|tres|cuatro|cinco|[1-5])\s+(?:(?:cenas?|comidas?|platos?|recetas?)\s+)?(?:de\s+|con\s+)(?:pescados?|merluza|salm[oó]n|salmon|fish)\b/i);
  if (mFishCnt && !/\bsin\s+pescado\b/i.test(text)) {
    const fc = wordMap[mFishCnt[1].toLowerCase()] || Number(mFishCnt[1]) || 1;
    pills.push(fc > 1 ? `${fc} cenas de pescado` : "Incluye pescado");
  } else if (/\b(?:pescado|merluza|salmón|salmon|fish)\b/i.test(text) && !/\bsin\s+pescado\b/i.test(text)) {
    pills.push("Incluye pescado");
  }

  const mMaxPasta =
    text.match(/\bno\s+(?:propongas|pongas|incluyas|repitas|quiero)?[^.!?,]{0,45}?\b(?:pasta|macarrones|espaguetis)\b[^.!?,]{0,30}?\bm[aá]s\s+de\s+(one|two|three|four|un|una|uno|dos|tres|cuatro|[1-4])/i) ||
    text.match(/\b(?:m[aá]ximo|como\s+mucho|no\s+m[aá]s\s+de)\s+(one|two|three|four|un|una|uno|dos|tres|cuatro|[1-4])\s*(?:veces|d[ií]as|cenas|platos|recetas)?\s*(?:de\s+|con\s+)?(?:pasta|macarrones|espaguetis)\b/i);
  if (mMaxPasta) {
    const mp = wordMap[mMaxPasta[1].toLowerCase()] || Number(mMaxPasta[1]) || 2;
    pills.push(`Máx. ${mp} de pasta`);
  }

  const mDayNever = text.match(/\b(?:nunca|no|sin)\s+(?:pasta\s+)?(?:el\s+|los\s+)?(lunes|martes|mi[eé]rcoles|miercoles|jueves|viernes)\b/i);
  if (mDayNever && /\bpasta\b/i.test(text)) {
    const dayRaw = mDayNever[1].toLowerCase();
    const dayCap = dayRaw.startsWith("mier") || dayRaw.startsWith("miér") ? "Miércoles" : dayRaw.charAt(0).toUpperCase() + dayRaw.slice(1);
    pills.push(`${dayCap}: sin pasta`);
  }

  const algChecks = [
    ["Sin gluten", /\b(?:sin\s+gluten|gluten[- ]free|celiac|celíac)\b/i],
    ["Sin lactosa / lácteos", /\b(?:sin\s+lactosa|sin\s+lácteos|sin\s+lacteos|sin\s+leche|dairy[- ]free)\b/i],
    ["Sin frutos secos", /\b(?:sin\s+frutos\s+secos|sin\s+nueces|sin\s+almendras|nut[- ]free)\b/i],
    ["Sin huevo", /\b(?:sin\s+huevos?|egg[- ]free)\b/i],
    ["Sin marisco", /\b(?:sin\s+marisco|sin\s+crustáceos|sin\s+gambas)\b/i],
  ];
  for (const [label, rx] of algChecks) {
    if (rx.test(text)) pills.push(label);
  }

  const mPantry =
    text.match(/\b(?:usa|usar|utiliza|aprovecha|use)\s+(?:el|la|los|las|the)?\s*([^.!?;]+?)\s+(?:que\s+)?(?:ya\s+)?(?:tengo|tenemos|i\s+already\s+have|we\s+have)/i) ||
    text.match(/\b(?:ya\s+tengo|tengo\s+en\s+casa)\s+([^.!?;]+)/i);
  if (mPantry) {
    const clean = mPantry[1]
      .replace(/\b(?:el|la|los|las|the|en\s+casa)\b/gi, "")
      .trim();
    if (clean) pills.push(`En casa: ${clean}`);
  }
  return pills;
}

async function fetchCampaignsFromLibrary() {
  let loaded = null;
  try {
    const localRes = await fetch("/api/campaigns");
    if (localRes.ok) {
      const localData = await localRes.json();
      if (localData.campaign_library_url) {
        state.campaignLibraryUrl = localData.campaign_library_url;
      }
      if (Array.isArray(localData.campaigns) && localData.campaigns.length > 0) {
        loaded = localData.campaigns;
      }
    }
  } catch (e) {
    // Keep default campaigns
  }

  if (loaded && loaded.length > 0) {
    state.campaigns = loaded;
    const params = new URLSearchParams(window.location.search);
    const requestedId = params.get("campaign");
    const activeList = getActiveCampaigns();
    const target =
      (requestedId && state.campaigns.find((c) => c.id === requestedId)) ||
      activeList.find((c) => c.id === state.selectedCampaignId) ||
      activeList.find((c) => c.profileId === state.profileId) ||
      activeList[0];

    if (target) {
      const prevId = state.selectedCampaignId;
      state.selectedCampaignId = target.id;
      if (requestedId && target.profileId) {
        state.profileId = target.profileId;
      }
      if (prevId !== target.id || requestedId) {
        state.prompt = target.seedPrompt;
        state.detectedPills = detectPillsClientSide(state.prompt);
      }
    }
    render();
  }
}

async function consumeDiaConnectHash() {
  const hash = String(window.location.hash || "");
  const match = hash.match(/(?:mercadona_connect|eci_connect|dia_connect)=([A-Za-z0-9+/=_-]+)/);
  if (!match) return false;

  const rawConnectToken = `#mercadona_connect=${match[1]}`;
  // Immediately clean URL hash so the token does not remain in the address bar
  try {
    window.history.replaceState(null, document.title, window.location.pathname + window.location.search);
  } catch (e) {
    window.location.hash = "";
  }

  state.diaAuthInput = rawConnectToken;
  await connectDiaSession({ fromBookmarklet: true });
  return true;
}

async function checkSession() {
  if (!state.plan) {
    restoreLocalActivePlan();
  }
  try {
    const res = await fetch("/api/auth/session");
    const data = await res.json();
    state.auth.checked = true;
    state.auth.authenticated = Boolean(data.authenticated);
    state.auth.user = data.user || null;
    state.auth.iapEmail = data.iap_email || null;
    state.auth.allowedUsers = data.allowed_users || state.auth.allowedUsers;
    state.auth.googleClientId = data.google_client_id || "";
    if (data.campaign_library_url) {
      state.campaignLibraryUrl = data.campaign_library_url;
    }
    if (data.dia_session) {
      state.diaSession = {
        ...state.diaSession,
        ...data.dia_session,
      };
      if (data.dia_session.warehouse) {
        state.warehouse = data.dia_session.warehouse;
      }
      if (data.dia_session.postal_code) {
        state.postalCode = data.dia_session.postal_code;
      }
    }
    if (data.cookidoo_session) {
      state.cookidooSession = {
        ...state.cookidooSession,
        ...data.cookidoo_session,
      };
      if (data.cookidoo_session.email && !state.cookidooEmail) {
        state.cookidooEmail = data.cookidoo_session.email;
      }
      if (data.cookidoo_session.last_scheduled_week && !state.cookidooScheduledResult) {
        state.cookidooScheduledResult = data.cookidoo_session.last_scheduled_week;
        (data.cookidoo_session.last_scheduled_week.days || []).forEach((d) => {
          if (d.recipe_id) {
            state.sentThermomixIds[d.recipe_id] = d.short_label || d.day || true;
          }
        });
      }
    }
    if (data.recipe_preferences) {
      let hasLocalPrefs = false;
      try {
        hasLocalPrefs = Boolean(window.localStorage.getItem(RECIPE_PREFS_STORAGE_KEY));
      } catch (e) {
        hasLocalPrefs = false;
      }
      const nextLiked = hasLocalPrefs ? state.recipePreferences.liked : data.recipe_preferences.liked || [];
      const nextDisliked = hasLocalPrefs ? state.recipePreferences.disliked : data.recipe_preferences.disliked || [];
      saveLocalRecipePreferences({ liked: nextLiked, disliked: nextDisliked });
      if (state.plan && Array.isArray(state.plan.meals)) {
        state.plan.meals.forEach((m) => {
          m.liked_by_user = state.recipePreferences.liked.includes(m.recipe_id);
        });
      }
    }
    render();
  } catch (err) {
    state.auth.checked = true;
    render();
  }
  await consumeDiaConnectHash();
  await fetchCampaignsFromLibrary();
  await fetchWhatsAppState({ silent: true });
}

async function logoutUser() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch (err) {
    // Ignore local session clear error before IAP sign-out redirect
  }
  window.location.href = "/_gcp_iap/clear_login_cookie";
}

async function updatePostalCode(newPc) {
  const clean = String(newPc || "").replace(/\D/g, "").slice(0, 5);
  if (clean.length !== 5) {
    showToast("Código postal inválido", "Introduce un código postal español de 5 dígitos (ej. 28016).");
    return;
  }
  state.postalCode = clean;
  try {
    const res = await fetch("/api/postal-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ postal_code: clean }),
    });
    const data = await res.json();
    if (res.ok) {
      state.postalCode = data.postal_code;
      state.warehouse = data.warehouse;
      state.centerName = data.center_name || data.warehouse;
      state.deliveryAvailable = data.delivery_available !== false;
      state.catalogData = null;
      showToast(
        `Código Postal ${data.postal_code} activo`,
        data.message || `Conectado en tiempo real al centro '${state.centerName}' de Mercadona.`
      );
      if (state.plan) {
        await generatePlan(state.prompt);
      } else {
        render();
      }
    }
  } catch (err) {
    render();
  }
}

async function generatePlan(promptText) {
  if (!state.auth.authenticated) {
    render();
    return;
  }
  const msg = (promptText || state.prompt || "").trim();
  if (!msg || state.loading) return;

  const domainCheck = validateMealPlanningPrompt(msg);
  if (!domainCheck.valid) {
    state.error = domainCheck.message;
    showToast("Petición fuera de alcance", domainCheck.message);
    render();
    return;
  }

  state.loading = true;
  state.error = null;
  state.cartAddedResult = null;
  state.lastSwapChange = null;
  state.cookidooScheduledResult = null;
  state.sentThermomixIds = {};
  state.varietyCounter += 1;
  render();

  try {
    const res = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: msg,
        postalCode: state.postalCode,
        currentPlan: state.plan,
        varietySeed: `${state.profileId}:${state.selectedCampaignId}:${state.varietyCounter}:${Date.now().toString(36)}`,
        likedRecipeIds: state.recipePreferences.liked,
        dislikedRecipeIds: state.recipePreferences.disliked,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      state.error = data.error || "No se pudo generar el menú semanal.";
      state.loading = false;
      render();
      return;
    }
    state.previousPlan = state.plan;
    state.plan = data;
    state.postalCode = data.postal_code || state.postalCode;
    state.warehouse = data.warehouse || state.warehouse;
    state.detectedPills = data.constraint_pills || state.detectedPills;
    if (data.cookidoo_session) {
      state.cookidooSession = {
        ...state.cookidooSession,
        ...data.cookidoo_session,
      };
      if (data.cookidoo_session.email && !state.cookidooEmail) {
        state.cookidooEmail = data.cookidoo_session.email;
      }
    }
    if (data.recipe_preferences) {
      saveLocalRecipePreferences(data.recipe_preferences);
    }
    saveLocalActivePlan();
  } catch (err) {
    state.error = err.message || "Error al conectar con el planificador Google Gemini.";
  } finally {
    state.loading = false;
    render();
  }
}

async function swapRecipe(recipeId, options = {}) {
  if (!state.plan || state.loading || state.swappingRecipeId) return;
  state.swappingRecipeId = recipeId;
  state.cartAddedResult = null;
  render();

  try {
    const res = await fetch("/api/recipe-swap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        currentMeals: state.plan.meals.map((m) => ({
          day: m.day,
          recipe_id: m.recipe_id,
          recipeId: m.recipe_id,
        })),
        targetRecipeId: recipeId,
        constraints: state.plan.constraints,
        postalCode: state.postalCode,
        rotation: state.varietyCounter++,
        likedRecipeIds: state.recipePreferences.liked,
        dislikedRecipeIds: state.recipePreferences.disliked,
      }),
    });
    const data = await res.json();
    if (res.ok && data.replacement) {
      state.previousPlan = state.plan;
      state.lastSwapChange = data.change;
      delete state.sentThermomixIds[recipeId];
      state.plan = {
        ...state.plan,
        meals: state.plan.meals.map((m) => (m.recipe_id === recipeId ? data.replacement : m)),
        basket: data.basket,
        total: data.total,
        budget_remaining: data.budget_remaining,
        basket_tier: data.basket_tier || state.plan.basket_tier || "ahorro",
        upgraded_count: data.upgraded_count ?? state.plan.upgraded_count ?? 0,
        counter_notes_count: data.counter_notes_count ?? state.plan.counter_notes_count ?? 0,
        sommelier_pairing: data.sommelier_pairing || state.plan.sommelier_pairing,
        retail_media_summary: data.retail_media_summary || state.plan.retail_media_summary,
        eci_plus_status: data.eci_plus_status || state.plan.eci_plus_status,
      };
      if (data.cookidoo_session) {
      state.cookidooSession = {
        ...state.cookidooSession,
        ...data.cookidoo_session,
      };
      if (data.cookidoo_session.email && !state.cookidooEmail) {
        state.cookidooEmail = data.cookidoo_session.email;
      }
      if (data.cookidoo_session.last_scheduled_week && !state.cookidooScheduledResult) {
        state.cookidooScheduledResult = data.cookidoo_session.last_scheduled_week;
        (data.cookidoo_session.last_scheduled_week.days || []).forEach((d) => {
          if (d.recipe_id) {
            state.sentThermomixIds[d.recipe_id] = d.short_label || d.day || true;
          }
        });
      }
    }
    if (data.recipe_preferences) {
        saveLocalRecipePreferences(data.recipe_preferences);
      }
      saveLocalActivePlan();
      if (options.autoFromDislike) {
        showToast(
          `👎 Receta descartada y sustituida (${data.change.day})`,
          `No volveremos a proponerte '${options.dislikedRecipeName || data.change.from_recipe_name}'. La hemos cambiado por '${data.change.to_recipe_name}' (${formatEUR(data.total)}).`
        );
      } else {
        showToast(
          `Cambio rápido (${data.change.day})`,
          `Se sustituyó solo esta receta por '${data.change.to_recipe_name}' y se actualizó la cesta (${formatEUR(data.total)}).`
        );
      }
    } else {
      showToast("Error en Cambio rápido", data.error || "No se pudo cambiar la receta.");
    }
  } catch (err) {
    showToast("Error en Cambio rápido", "No se pudo encontrar otra receta con las mismas restricciones.");
  } finally {
    state.swappingRecipeId = null;
    render();
  }
}

async function sendToThermomix(recipeId, cookidooUrl, recipeName, dayName = "Lunes") {
  // Open the official Cookidoo recipe page in a new tab immediately on user click
  const safeUrl = sanitizeUrl(cookidooUrl, "");
  if (safeUrl) {
    window.open(safeUrl, "_blank", "noopener,noreferrer");
  }
  try {
    const res = await fetch("/api/cookidoo/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recipe_id: recipeId,
        day: dayName,
        week_mode: state.cookidooWeekMode || "current",
        cookidoo_email: state.cookidooEmail,
        cookidoo_password: state.cookidooPassword,
      }),
    });
    const data = await res.json();
    state.sentThermomixIds[recipeId] = data.short_label || dayName || true;
    showToast(
      `Planificada en Thermomix (${data.short_label || dayName})`,
      data.message || `Receta '${recipeName}' asignada al ${dayName} en Cookidoo.`
    );
    render();
  } catch (err) {
    state.sentThermomixIds[recipeId] = dayName || true;
    render();
  }
}

async function connectCookidooSession({ demoMode = false } = {}) {
  if (state.cookidooVerifying) return;
  const domEmail = document.getElementById("cookidoo-email-input")?.value;
  const domPass = document.getElementById("cookidoo-pass-input")?.value;
  if (typeof domEmail === "string") state.cookidooEmail = domEmail;
  if (typeof domPass === "string") state.cookidooPassword = domPass;

  const email = (state.cookidooEmail || "").trim();
  const password = (state.cookidooPassword || "").trim();
  if (!demoMode && (!email || !email.includes("@"))) {
    state.cookidooVerifyError = "Introduce el email de tu cuenta de Cookidoo (cookidoo.es).";
    showToast("Email de Cookidoo requerido", state.cookidooVerifyError);
    render();
    return;
  }
  if (!demoMode && !password) {
    state.cookidooVerifyError = "Introduce la contraseña de tu cuenta de Cookidoo (cookidoo.es) para sincronizar tu calendario real.";
    showToast("Contraseña de Cookidoo requerida", state.cookidooVerifyError);
    render();
    return;
  }
  state.cookidooVerifying = true;
  state.cookidooVerifyError = "";
  render();
  let linkedLive = false;
  try {
    const res = await fetch("/api/cookidoo/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cookidoo_email: email,
        cookidoo_password: password,
        demo_mode: demoMode,
      }),
    });
    const data = await res.json();
    if (res.ok && data.connected) {
      state.cookidooSession = {
        ...state.cookidooSession,
        ...data,
      };
      if (data.email) state.cookidooEmail = data.email;
      // Clear plaintext password from JS memory immediately after OAuth2 token exchange succeeds
      state.cookidooPassword = "";
      const passEl = document.getElementById("cookidoo-pass-input");
      if (passEl) passEl.value = "";
      state.cookidooVerifyError = "";
      state.cookidooModalOpen = false;
      linkedLive = Boolean(data.auth_mode === "live_api" || data.live_authenticated);
      showToast(
        linkedLive ? "✓ Cuenta real de Cookidoo® autenticada" : "⚡ Perfil Demo de Cookidoo® activado",
        data.message || `Tu cuenta (${data.masked_email || data.email}) ya está conectada.`
      );
    } else {
      state.cookidooVerifyError = data.error || "No se pudo iniciar sesión en Cookidoo.es. Comprueba tu email y contraseña.";
      state.cookidooModalOpen = true;
      showToast("Error de acceso en Cookidoo.es", state.cookidooVerifyError);
    }
  } catch (err) {
    state.cookidooVerifyError = "Error de conexión al verificar credenciales en Cookidoo.";
    showToast("Error al conectar con Cookidoo", "Inténtalo de nuevo.");
  } finally {
    state.cookidooVerifying = false;
    render();
  }
  if (linkedLive && state.plan && Array.isArray(state.plan.meals)) {
    await scheduleWeekInCookidoo();
  }
}

async function disconnectCookidooSession() {
  try {
    const res = await fetch("/api/cookidoo/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "disconnect" }),
    });
    if (res.ok) {
      const data = await res.json();
      state.cookidooSession = {
        ...state.cookidooSession,
        ...data,
        connected: false,
        live_authenticated: false,
      };
      state.cookidooPassword = "";
      state.cookidooVerifyError = "";
      state.cookidooScheduledResult = null;
      state.sentThermomixIds = {};
      showToast("Cuenta Cookidoo desvinculada", "Se ha desconectado tu sesión de Cookidoo.");
      render();
    }
  } catch (err) {
    render();
  }
}

async function scheduleWeekInCookidoo() {
  if (!state.plan || !Array.isArray(state.plan.meals) || state.cookidooSchedulingWeek) return;
  const domEmail = document.getElementById("cookidoo-email-input")?.value;
  const domPass = document.getElementById("cookidoo-pass-input")?.value;
  if (typeof domEmail === "string" && domEmail.trim()) state.cookidooEmail = domEmail.trim();
  if (typeof domPass === "string" && domPass.trim()) state.cookidooPassword = domPass.trim();

  state.cookidooSchedulingWeek = true;
  state.cookidooVerifyError = "";
  render();
  try {
    const res = await fetch("/api/cookidoo/schedule-week", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        meals: state.plan.meals,
        week_mode: state.cookidooWeekMode || "current",
        cookidoo_email: state.cookidooEmail,
        cookidoo_password: state.cookidooPassword,
      }),
    });
    const data = await res.json();
    if (res.ok && data.schedule) {
      state.cookidooScheduledResult = data.schedule;
      state.cookidooPassword = "";
      if (data.cookidoo_session) {
        state.cookidooSession = {
          ...state.cookidooSession,
          ...data.cookidoo_session,
        };
      }
      state.sentThermomixIds = {};
      (data.schedule.days || []).forEach((d) => {
        if (d.recipe_id) {
          state.sentThermomixIds[d.recipe_id] = d.short_label || d.day;
        }
      });
      if (data.live_api_synced) {
        showToast(
          "📅 ¡Menú sincronizado en tu cuenta real de Cookidoo.es!",
          data.message || "Las 5 recetas ya están disponibles día por día en tu calendario real «Mi Semana» de Cookidoo."
        );
      } else {
        state.cookidooModalOpen = true;
        showToast(
          "⚡ Vista previa generada · Vincula tu cuenta real de Cookidoo.es",
          "Introduce tu email y contraseña reales de Cookidoo en el panel desplegado para escribir las 5 recetas en tu cuenta de cookidoo.es."
        );
      }
    } else {
      state.cookidooModalOpen = true;
      state.cookidooVerifyError = data.error || "No se pudo sincronizar la semana con Cookidoo.";
      showToast("Error al planificar en Cookidoo", state.cookidooVerifyError);
    }
  } catch (err) {
    showToast("Error al planificar en Cookidoo", "No se pudo conectar con el servicio de Cookidoo.");
  } finally {
    state.cookidooSchedulingWeek = false;
    render();
  }
}

async function connectDiaSession(options = {}) {
  const input = (state.diaAuthInput || "").trim();
  if (!input) {
    state.diaVerifyError =
      "Usa el botón 1-Click en tu barra de marcadores desde tienda.mercadona.es o pega tu sesión abajo.";
    render();
    return;
  }
  state.diaVerifying = true;
  state.diaVerifyError = "";
  render();
  try {
    const res = await fetch("/api/dia/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        auth_input: input,
        postal_code: state.postalCode,
      }),
    });
    const data = await res.json();
    if (res.ok && data.connected) {
      state.diaSession = {
        connected: true,
        customer_id: data.customer_id,
        warehouse: data.warehouse || state.warehouse,
        postal_code: data.postal_code || state.postalCode,
        has_refresh_token: Boolean(data.has_refresh_token),
        masked_token: data.masked_token,
      };
      if (data.warehouse) {
        state.warehouse = data.warehouse;
      }
      if (data.postal_code) {
        state.postalCode = data.postal_code;
      }
      state.diaAuthInput = "";
      state.diaModalOpen = false;
      try {
        window.localStorage.setItem("dia_session_sync_v1", String(Date.now()));
      } catch (e) {}
      showToast(
        options.fromBookmarklet
          ? "¡Cuenta de Mercadona vinculada en 1-Click!"
          : "Cuenta de Mercadona conectada",
        data.message || "Tu carrito de tienda.mercadona.es ya está vinculado y listo para sincronizar."
      );
      if (options.fromBookmarklet && state.plan) {
        setTimeout(() => {
          document.getElementById("dia-cart-section")?.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 180);
      }
    } else {
      state.diaModalOpen = true;
      state.diaVerifyError = data.error || "No se pudo verificar el token con tienda.mercadona.es.";
      if (options.fromBookmarklet) {
        showToast("No se pudo vincular automáticamente", state.diaVerifyError);
      }
    }
  } catch (err) {
    state.diaModalOpen = true;
    state.diaVerifyError = err.message || "Error al conectar con tienda.mercadona.es.";
  } finally {
    state.diaVerifying = false;
    render();
  }
}

async function disconnectDiaSession() {
  try {
    await fetch("/api/dia/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "disconnect" }),
    });
    state.diaSession = {
      connected: false,
      customer_id: null,
      warehouse: null,
      postal_code: null,
      has_refresh_token: false,
      masked_token: null,
    };
    state.cartAddedResult = null;
    try {
      window.localStorage.setItem("dia_session_sync_v1", String(Date.now()));
    } catch (e) {}
    showToast("Sesión desvinculada", "Se ha desvinculado tu sesión de tienda.mercadona.es.");
    render();
  } catch (err) {
    render();
  }
}

async function addBasketToDiaOneClick() {
  if (!state.plan || state.addingToCart) return;
  state.addingToCart = true;
  state.diaVerifyError = "";
  render();
  try {
    const res = await fetch("/api/dia/cart", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        basket: state.plan.basket,
        postal_code: state.postalCode,
        dia_auth: state.diaAuthInput || undefined,
        mode: state.diaSyncMode || "add",
      }),
    });
    const data = await res.json();
    if (res.ok) {
      state.cartAddedResult = data;
      if (data.live_synced) {
        state.diaSession = {
          ...state.diaSession,
          connected: true,
          customer_id: data.customer_id || state.diaSession.customer_id,
          warehouse: data.warehouse || state.warehouse,
          postal_code: data.postal_code || state.postalCode,
        };
        if (data.warehouse) {
          state.warehouse = data.warehouse;
        }
        if (data.postal_code) {
          state.postalCode = data.postal_code;
        }
        state.diaAuthInput = "";
        state.diaModalOpen = false;
        showToast("¡Añadido a tu carrito real de Mercadona!", data.message);
      } else {
        if (data.auth_error) {
          state.diaModalOpen = true;
          state.diaVerifyError = data.auth_error;
        }
        showToast("¡Cesta pre-creada en Mercadona!", data.message);
      }
    }
  } catch (err) {
    showToast("Error al sincronizar carrito", "Inténtalo de nuevo en unos segundos.");
  } finally {
    state.addingToCart = false;
    render();
  }
}

async function loadCatalogTab() {
  state.activeTab = "catalog";
  render();
  if (!state.catalogData) {
    const res = await fetch(`/api/catalog?postal_code=${encodeURIComponent(state.postalCode)}`);
    if (res.ok) {
      state.catalogData = await res.json();
      render();
    }
  }
}

async function loadSourcesTab() {
  state.activeTab = "sources";
  render();
  if (!state.catalogData) {
    const res = await fetch(`/api/catalog?postal_code=${encodeURIComponent(state.postalCode)}`);
    if (res.ok) {
      state.catalogData = await res.json();
      render();
    }
  }
}

function renderGoogleCloudLockup(white = false) {
  const src = white ? "/brand/google-cloud-white.svg?v=mercadona-md3-2026" : "/brand/google-cloud.svg?v=mercadona-brand-2026";
  return `
    <span class="gcloud-lockup-badge" aria-label="Google Cloud">
      <img
        class="gcloud-logo-img"
        src="${src}"
        alt="Google Cloud"
      />
    </span>
  `;
}

function renderAuthModal() {
  if (!state.auth.checked || state.auth.authenticated) return "";
  const detectedAccount = state.auth.iapEmail
    ? `<div class="auth-error-msg" role="alert" style="margin-bottom: 14px;">La cuenta autenticada (<strong>${escapeHtml(state.auth.iapEmail)}</strong>) no está en la allowlist de este proyecto.</div>`
    : "";
  return `
    <div class="auth-gate-overlay" role="dialog" aria-modal="true" aria-labelledby="auth-gate-title">
      <div class="auth-gate-card">
        <div class="brand-lockup" style="margin-bottom: 18px;">
          ${renderGoogleCloudLockup()}
          <span class="brand-divider"></span>
          <img class="mercadona-logo" src="/brand/mercadona.svg?v=mercadona-brand-2026" alt="Mercadona" style="width: 125px;" />
        </div>
        <p class="eyebrow" style="margin-bottom: 6px;">Protegido por Google Cloud Identity-Aware Proxy (IAP)</p>
        <h2 id="auth-gate-title">Autenticación Google obligatoria</h2>
        <p>
          El acceso a esta aplicación en Cloud Run está protegido mediante <strong>Google Cloud Identity-Aware Proxy (IAP)</strong> y restringido exclusivamente a las ${state.auth.allowedUsers.length} cuentas de Google autorizadas en la allowlist:
        </p>
        ${detectedAccount}
        <div class="allowed-users-box" aria-label="Cuentas de Google en la allowlist de IAP">
          <span>Allowlist oficial de Identity-Aware Proxy (solo lectura)</span>
          ${state.auth.allowedUsers
            .map(
              (email) => `
            <div class="allowed-user-btn" style="cursor: default; pointer-events: none;">
              <strong>${escapeHtml(email)}</strong>
              <small style="color: var(--muted);">Autorizado en IAM / IAP</small>
            </div>
          `
            )
            .join("")}
        </div>
        <a
          href="/_gcp_iap/clear_login_cookie"
          class="primary-button"
          style="width: 100%; justify-content: center; text-decoration: none; margin-top: 8px;"
        >
          Iniciar sesión con cuenta de Google (IAP)
        </a>
        ${
          state.auth.error
            ? `<div class="auth-error-msg" role="alert">${escapeHtml(state.auth.error)}</div>`
            : ""
        }
      </div>
    </div>
  `;
}

function renderHeader() {
  const activeProfile = PROFILES.find((p) => p.id === state.profileId) || PROFILES[0];
  const userInitial = state.auth.user ? state.auth.user.charAt(0).toUpperCase() : "G";

  return `
    <header class="brand-bar companion-brand-bar">
      <a href="#for-you" class="brand-lockup" id="nav-home-logo" aria-label="Google Cloud y Mercadona">
        ${renderGoogleCloudLockup(true)}
        <span class="brand-divider" aria-hidden="true"></span>
        <img class="mercadona-logo" src="/brand/mercadona.svg?v=mercadona-brand-2026" alt="Mercadona" />
      </a>
      <nav class="top-navigation" aria-label="Navegación principal">
        <a href="#for-you" data-tab="planner" ${state.activeTab === "planner" ? 'aria-current="page"' : ""}>Para ti</a>
        <a href="#planner" data-tab="planner">Mi semana</a>
        <a href="#catalog" data-tab="catalog" ${state.activeTab === "catalog" ? 'aria-current="page"' : ""}>Catálogo Mercadona</a>
        <a href="#sources" data-tab="sources" ${state.activeTab === "sources" ? 'aria-current="page"' : ""}>Cookidoo &amp; APIs</a>
        <a href="${escapeHtml(state.campaignLibraryUrl || "/marketing")}">Campaign Library</a>
      </nav>
      <div class="header-controls">
        <button
          type="button"
          id="header-whatsapp-btn"
          class="dia-header-pill whatsapp-header-pill ${state.whatsappOpen ? "is-connected" : ""}"
          title="Abrir Copiloto de WhatsApp Business Mercadona (Webhook Meta / Twilio en vivo)"
        >
          <span aria-hidden="true">💬</span>
          <span>WhatsApp Copilot</span>
        </button>

        <form id="postal-code-form" class="postal-selector" title="Configura tu código postal para consultar disponibilidad en tiempo real en Mercadona">
          <label for="header-pc-input">CP</label>
          <input id="header-pc-input" type="text" maxlength="5" value="${escapeHtml(state.postalCode)}" aria-label="Código postal" />
          <span class="wh-pill">(${escapeHtml(state.warehouse)})</span>
          <button type="submit">Actualizar</button>
        </form>
        <button
          type="button"
          id="header-dia-connect-btn"
          class="dia-header-pill ${state.diaSession.connected ? "is-connected" : ""}"
          title="${
            state.diaSession.connected
              ? `Carrito de tienda.mercadona.es vinculado (Cliente ${state.diaSession.customer_id || "activo"})`
              : "Vincular tu cuenta de tienda.mercadona.es en 1-Click"
          }"
        >
          <span class="dia-header-dot"></span>
          <span>${state.diaSession.connected ? "Carrito Mercadona ✓" : "Vincular Carrito"}</span>
        </button>
        <label class="profile-selector">
          <span>Perfil</span>
          <select id="profile-select" aria-label="Seleccionar perfil familiar">
            ${PROFILES.map(
              (p) => `<option value="${p.id}" ${p.id === activeProfile.id ? "selected" : ""}>${escapeHtml(p.name)}</option>`
            ).join("")}
          </select>
        </label>
        ${
          state.auth.authenticated
            ? `
          <div class="user-auth-pill" title="${escapeHtml(state.auth.user)}">
            <span class="user-avatar">${escapeHtml(userInitial)}</span>
            <span class="user-email-text">${escapeHtml(state.auth.user)}</span>
            <button type="button" id="logout-btn">Salir</button>
          </div>
        `
            : ""
        }
      </div>
    </header>
  `;
}

function renderDiaConnectBox() {
  if (!state.diaModalOpen) return "";
  const bookmarkletHref = buildDiaBookmarkletHref();
  const forceManualOpen = Boolean(state.diaVerifyError || state.diaAuthInput);
  return `
    <div id="dia-connect-box" class="dia-connect-panel">
      <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px; flex-wrap:wrap; margin-bottom:10px;">
        <div>
          <strong style="font-size:13.5px; display:block; color:var(--ink);">
            🛒 1-Click a tu Cesta de Mercadona (Sin extensiones externas)
          </strong>
          <span style="font-size:12px; color:var(--muted);">
            ${
              state.diaSession.connected
                ? `Sesión activa vinculada: Cesta ${escapeHtml(state.diaSession.customer_id || "activa")} · Centro ${escapeHtml(state.diaSession.warehouse || state.warehouse)} (CP ${escapeHtml(state.postalCode)})`
                : "Pre-creamos tu cesta directamente en el servidor de Mercadona (api/tienda.mercadona.es/api) y la sincronizamos en 1-Click sin instalar extensiones."
            }
          </span>
        </div>
        <div style="display:flex; align-items:center; gap:12px;">
          ${
            state.diaSession.connected
              ? `<button type="button" class="text-button" id="disconnect-dia-session-btn" style="color:#b42318; font-size:12px;">Desvincular sesión actual</button>`
              : ""
          }
          <button type="button" class="text-button" id="close-dia-modal-btn" style="font-size:12px;">Cerrar ✕</button>
        </div>
      </div>

      ${
        state.diaVerifyError
          ? `<div style="color:#b42318; background:#fef3f2; border:1px solid #fecdca; padding:9px 12px; font-size:12px; border-radius:3px; margin-bottom:12px;">${escapeHtml(state.diaVerifyError)}</div>`
          : ""
      }

      <div class="dia-bookmarklet-steps">
        <div class="dia-step-card">
          <span class="dia-step-num">1</span>
          <div>
            <strong>Arrastra el marcador 1-Click (o copia el conector rápido)</strong>
            <p>Sin extensiones de Chrome: arrastra este botón verde a tu barra de marcadores (<code>Ctrl+Shift+B</code> / <code>⌘+Shift+B</code>) o copia el comando de 1-Click.</p>
            <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-top:8px;">
              <a
                href="${escapeHtml(bookmarkletHref)}"
                id="dia-bookmarklet-link"
                class="dia-bookmarklet-btn"
                draggable="true"
                title="Arrástrame a tu barra de marcadores y púlsame cuando estés en tienda.mercadona.es"
              >
                🔗 Vincular Cesta Mercadona
              </a>
              <button
                type="button"
                class="secondary-button"
                id="copy-dia-connector-btn"
                style="padding: 7px 11px; font-size: 11.5px; margin-top: 0; min-height: 36px;"
                title="Copia este comando para pegarlo en la Consola de tienda.mercadona.es"
              >
                📋 Copiar conector 1-Click
              </button>
            </div>
          </div>
        </div>

        <div class="dia-step-card">
          <span class="dia-step-num">2</span>
          <div>
            <strong>Abre Mercadona y pulsa el marcador</strong>
            <p>
              Entra en <a href="https://tienda.mercadona.es/" target="_blank" rel="noreferrer" style="text-decoration:underline; font-weight:700; color:var(--green-dark);">tienda.mercadona.es ↗</a> y haz clic en el marcador <strong>“🔗 Vincular Cesta Mercadona”</strong>.
            </p>
            <p style="margin-top:4px; font-size:11.5px; color:var(--muted);">
              Tu cookie de pedido (<code>MO-user</code>) y tu centro logístico (<code>${escapeHtml(state.warehouse)}</code>) quedarán sincronizados para añadir toda la compra en 1 solo click desde el servidor.
            </p>
          </div>
        </div>
      </div>

      <details ${forceManualOpen ? "open" : ""} style="margin-top:12px; border-top:1px solid #c8dad2; padding-top:10px;">
        <summary style="font-size:12px; font-weight:600; color:var(--ink); cursor:pointer;">
          ¿Prefieres pegar tu cookie <code>MO-user</code> o un cURL manualmente?
        </summary>
        <div style="margin-top:10px;">
          <div style="font-size:11.5px; color:var(--muted); line-height:1.55; margin-bottom:10px; background:#ffffff; border:1px solid #d2e2db; padding:10px 12px; border-radius:3px;">
            <strong style="color:var(--ink); display:block; margin-bottom:4px;">Vinculación directa mediante Cookie o cURL de <code>tienda.mercadona.es</code>:</strong>
            • En <code>tienda.mercadona.es</code>, pulsa <code>F12</code> → <strong>Application → Cookies</strong>, copia el valor de <strong><code>MO-user</code></strong> (o cualquier <em>Copy as cURL</em> de <code>tienda.mercadona.es/api</code>) y pégalo abajo.
          </div>
          <textarea
            id="dia-auth-input"
            rows="3"
            placeholder="Pega aquí tu cookie MO-user, JSON de sesión o comando Copy as cURL de tienda.mercadona.es..."
            style="width:100%; border:1px solid var(--line); background:#fff; padding:10px; font-size:12px; font-family:monospace; border-radius:2px; margin-bottom:10px;"
          >${escapeHtml(state.diaAuthInput)}</textarea>
          <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
            <button
              type="button"
              class="primary-button"
              id="verify-dia-session-btn"
              style="padding: 8px 14px; font-size: 12px;"
              ${state.diaVerifying ? "disabled" : ""}
            >
              ${state.diaVerifying ? "Verificando con Mercadona..." : "Verificar y vincular cesta Mercadona"}
            </button>
          </div>
        </div>
      </details>
    </div>
  `;
}

function renderExperiencePanel() {
  if (state.loading) {
    return `
      <div class="loading-state" aria-live="polite">
        <div class="loading-orbit"><span></span></div>
        <p class="empty-kicker">Google Gemini trabajando</p>
        <h2>Elaborando menú con Google Gemini</h2>
        <p>Verificando restricciones nutricionales, alérgenos, recetas de Thermomix y stock en tiempo real en Mercadona para el CP ${escapeHtml(state.postalCode)} (${escapeHtml(state.warehouse)}).</p>
        <div class="loading-steps">
          <span>Analizando condiciones del prompt con Google Gemini</span>
          <span>Seleccionando recetas compatibles del catálogo de Cookidoo</span>
          <span>Mapeando ingredientes al catálogo real de Mercadona (CP ${escapeHtml(state.postalCode)})</span>
        </div>
      </div>
    `;
  }

  if (state.error) {
    return `
      <div class="error-state" role="alert">
        <p class="empty-kicker">Atención en la planificación</p>
        <h2>Ajusta alguna condición de tu petición</h2>
        <p>${escapeHtml(state.error)}</p>
        <button type="button" class="secondary-button" id="retry-plan-btn">Reintentar planificación</button>
      </div>
    `;
  }

  if (!state.plan) {
    return `
      ${renderDiaConnectBox()}
      <div class="empty-state">
        <div class="abstract-basket" aria-hidden="true">
          <span class="basket-handle"></span>
          <span class="produce produce-one"></span>
          <span class="produce produce-two"></span>
          <span class="produce produce-three"></span>
        </div>
        <p class="empty-kicker">Una sola petición en lenguaje natural</p>
        <h2>5 cenas en Thermomix. Una cesta exacta en Mercadona.</h2>
        <p>
          El asistente interpreta tus condiciones con Google Gemini, selecciona recetas reales de tu Thermomix, descuenta lo que ya tienes en casa y mapea todos los ingredientes al catálogo y a la disponibilidad en tiempo real de Mercadona.
        </p>
        <ol class="flow-list">
          <li><span>01</span> Entiende tu familia, presupuesto, tiempo, calorías, alergias y despensa</li>
          <li><span>02</span> Elige recetas de Cookidoo cuyos ingredientes están disponibles en Mercadona</li>
          <li><span>03</span> Envía las recetas a tu Thermomix y añade la compra al carrito en 1 click</li>
        </ol>
      </div>
    `;
  }

  const p = state.plan;
  const rawModelLabel = String(p.model || "Google Gemini").replace(/\s*\(.*?\)/g, "").trim();
  const cleanModelLabel = /gemini/i.test(rawModelLabel) ? "Google Gemini" : rawModelLabel;
  const cleanPlanSummary = String(p.summary || "").replace(/Gemini\s*(?:3\.8\s*Flash|2\.5(?:\s*Flash)?)/gi, "Google Gemini");
  const cookidooHasPendingSwap =
    Array.isArray(state.cookidooScheduledResult?.days) &&
    Array.isArray(p.meals) &&
    p.meals.some((m, i) => state.cookidooScheduledResult.days[i]?.recipe_id !== m.recipe_id);
  return `
    <div class="plan-state">
      <div class="plan-heading">
        <div>
          <p class="empty-kicker">Tu menú semanal de ${p.meals.length} cenas</p>
          <h2>${escapeHtml(p.headline)}</h2>
          <p>${escapeHtml(cleanPlanSummary)}</p>
        </div>
        <div class="live-badge">
          <span></span>
          ${escapeHtml(cleanModelLabel)}
        </div>
      </div>

      <div class="validation-ribbon" aria-label="Validaciones deterministas completadas">
        <span>✓ Recetas Cookidoo verificadas</span>
        <span>✓ Stock Mercadona CP ${escapeHtml(p.postal_code)} (${escapeHtml(p.warehouse)})</span>
        <span>✓ Alérgenos declarados comprobados</span>
        <span>✓ Presupuesto recalculado (${formatEUR(p.total)})</span>
        ${p.constraints.maxCaloriesPerServing ? `<span>✓ ≤ ${p.constraints.maxCaloriesPerServing} kcal / ración</span>` : ""}
      </div>

      <div class="cookidoo-week-sync-bar" role="region" aria-label="Sincronización con calendario Mi Semana de Cookidoo">
        <div class="cookidoo-week-sync-main">
          <div class="cookidoo-week-sync-info">
            <div class="cookidoo-week-sync-title-row">
              <span class="cookidoo-tm-badge">Thermomix® · Cookidoo®</span>
              <strong>Planificación por día en «Mi Semana»</strong>
              <button type="button" class="cookidoo-account-pill ${state.cookidooSession?.auth_mode === "live_api" ? "connected" : ""}" id="toggle-cookidoo-creds-btn">
                ${
                  state.cookidooSession?.auth_mode === "live_api"
                    ? `✓ Cuenta real vinculada (${escapeHtml(state.cookidooSession.masked_email || state.cookidooSession.email || "Cookidoo.es")})`
                    : state.cookidooSession?.connected
                      ? `⚡ Modo Demo (${escapeHtml(state.cookidooSession.masked_email || "Simulación")}) · Conectar cuenta real`
                      : "🔗 Vincular cuenta Cookidoo®"
                }
              </button>
            </div>
            <p class="cookidoo-week-sync-desc">
              Cuando el menú te parezca bien, envíalo de una sola vez a tu Thermomix® asignando cada receta a su día exacto (<strong>Lunes a Viernes</strong>) en el calendario <em>Mi Semana</em>.
            </p>
          </div>
          <div class="cookidoo-week-sync-actions">
            <div class="cookidoo-week-mode-group" role="group" aria-label="Seleccionar semana a planificar">
              <button
                type="button"
                class="cookidoo-week-mode-btn ${state.cookidooWeekMode !== "next" ? "active" : ""}"
                data-cookidoo-week="current"
              >
                Semana actual (Lun–Vie)
              </button>
              <button
                type="button"
                class="cookidoo-week-mode-btn ${state.cookidooWeekMode === "next" ? "active" : ""}"
                data-cookidoo-week="next"
              >
                Próxima semana (Lun–Vie)
              </button>
            </div>
            <button
              type="button"
              class="cookidoo-schedule-all-btn ${state.cookidooScheduledResult?.live_api_synced && !cookidooHasPendingSwap ? "scheduled" : ""}"
              id="schedule-cookidoo-week-btn"
              ${state.cookidooSchedulingWeek ? "disabled" : ""}
            >
              ${
                state.cookidooSchedulingWeek
                  ? "⏳ Planificando los 5 días en Cookidoo..."
                  : state.cookidooScheduledResult?.live_api_synced && cookidooHasPendingSwap
                    ? `🔄 Sincronizar cambios en tu Cookidoo.es (sustituir receta anterior)`
                    : state.cookidooScheduledResult?.live_api_synced
                      ? `✓ ${p.meals.length} cenas sincronizadas en tu Cookidoo.es · Actualizar`
                      : `📅 Confirmar y planificar las ${p.meals.length} cenas por día en Mi Semana`
              }
            </button>
          </div>
        </div>

        ${
          state.cookidooModalOpen
            ? `
          <div class="cookidoo-account-drawer">
            <div class="cookidoo-account-drawer-head">
              <div>
                <strong>Vincular cuenta real de Cookidoo® (Vorwerk / Thermomix® TM6 · TM7)</strong>
                <p>
                  Introduce el email y la contraseña de tu cuenta de <strong>cookidoo.es</strong>. Nos autenticamos directamente vía OAuth2 + PKCE con Vorwerk y programamos cada cena en su fecha exacta (<code>PUT /planning/es-ES/api/my-day</code>) dentro de tu calendario <strong>Mi Semana</strong>.
                </p>
              </div>
              ${
                state.cookidooSession?.auth_mode === "live_api"
                  ? `<span class="cookidoo-status-tag connected">● Conectado en vivo (${escapeHtml(state.cookidooSession.device_name || "API Oficial Cookidoo.es")})</span>`
                  : state.cookidooSession?.connected
                    ? `<span class="cookidoo-status-tag">⚡ Modo Demo (introduce tu contraseña para sincronización real)</span>`
                    : `<span class="cookidoo-status-tag">○ Sin vincular</span>`
              }
            </div>
            ${
              state.cookidooVerifyError
                ? `<div style="background:#fef2f2; border:1px solid #fecaca; color:#b91c1c; padding:9px 12px; border-radius:6px; font-size:12.5px; font-weight:600; margin-bottom:10px;">⚠️ ${escapeHtml(state.cookidooVerifyError)}</div>`
                : ""
            }
            <div class="cookidoo-account-inputs">
              <input type="email" id="cookidoo-email-input" placeholder="Email de tu cuenta Cookidoo.es (ej. usuario@correo.es)" value="${escapeHtml(state.cookidooEmail)}" autocomplete="username" />
              <input type="password" id="cookidoo-pass-input" placeholder="Contraseña de Cookidoo.es" value="${escapeHtml(state.cookidooPassword)}" autocomplete="current-password" />
              <button type="button" class="cookidoo-connect-btn primary" id="connect-cookidoo-btn" ${state.cookidooVerifying ? "disabled" : ""}>
                ${state.cookidooVerifying ? "Autenticando en Cookidoo.es..." : "Vincular cuenta real y sincronizar"}
              </button>
              <button type="button" class="cookidoo-connect-btn secondary" id="connect-cookidoo-demo-btn" ${state.cookidooVerifying ? "disabled" : ""}>
                ⚡ Simular en Modo Demo (sin cuenta)
              </button>
              ${
                state.cookidooSession?.connected
                  ? `<button type="button" class="cookidoo-disconnect-btn" id="disconnect-cookidoo-btn">Desvincular</button>`
                  : ""
              }
            </div>
          </div>
        `
            : ""
        }

        ${
          state.cookidooScheduledResult && Array.isArray(state.cookidooScheduledResult.days)
            ? `
          <div class="cookidoo-schedule-strip" role="status">
            <div class="cookidoo-schedule-strip-header">
              <div>
                <span class="cookidoo-schedule-badge">
                  ${
                    state.cookidooScheduledResult.live_api_synced
                      ? `✓ Sincronizado en vivo con Cookidoo.es · ${escapeHtml(state.cookidooScheduledResult.week_range_label || "")}`
                      : `⚡ Vista previa en Modo Demo · ${escapeHtml(state.cookidooScheduledResult.week_range_label || "")}`
                  }
                </span>
                <strong>${escapeHtml(state.cookidooScheduledResult.message || "Menú semanal asignado día por día en tu calendario Cookidoo®")}</strong>
              </div>
              <div class="cookidoo-schedule-links">
                <a href="${escapeHtml(sanitizeUrl(state.cookidooScheduledResult.planner_url, "https://cookidoo.es/planning/es-ES/my-week"))}" target="_blank" rel="noopener noreferrer" class="cookidoo-planner-link">
                  Abrir «Mi Semana» en Cookidoo.es ↗
                </a>
                ${
                  state.cookidooScheduledResult.ics_calendar_url
                    ? `<a href="${escapeHtml(state.cookidooScheduledResult.ics_calendar_url)}" download="mi-semana-thermomix-mercadona.ics" class="cookidoo-ics-link">⬇ Descargar calendario (.ics)</a>`
                    : ""
                }
              </div>
            </div>
            <div class="cookidoo-day-chips">
              ${state.cookidooScheduledResult.days
                .map(
                  (d) => `
                <div class="cookidoo-day-chip">
                  <div class="cookidoo-day-chip-top">
                    <span class="cookidoo-day-chip-date">📅 ${escapeHtml(d.short_label || d.day)}</span>
                    <span class="cookidoo-day-chip-check">${state.cookidooScheduledResult.live_api_synced ? "✓ En tu Cookidoo.es" : "📅 Día asignado"}</span>
                  </div>
                  <strong class="cookidoo-day-chip-name">${escapeHtml(d.name)}</strong>
                  <span class="cookidoo-day-chip-meta">Cookidoo ${escapeHtml(d.cookidoo_id || d.recipe_id)} · ${d.minutes || 25} min</span>
                </div>
              `
                )
                .join("")}
            </div>
          </div>
        `
            : ""
        }
      </div>

      ${
        state.lastSwapChange
          ? `
        <div class="plan-delta" role="status" style="margin-bottom: 16px;">
          <div>
            <span>Cambio rápido aplicado</span>
            <strong>Solo se ha cambiado la cena del ${escapeHtml(state.lastSwapChange.day)}</strong>
          </div>
          <div class="plan-delta-facts">
            <span>Anterior: ${escapeHtml(state.lastSwapChange.from_recipe_name)}</span>
            <span>Nueva: ${escapeHtml(state.lastSwapChange.to_recipe_name)}</span>
            <span>Cesta recalculada: ${formatEUR(p.total)}</span>
          </div>
        </div>
      `
          : ""
      }

      <div class="meal-grid">
        ${p.meals
          .map((meal, idx) => {
            const isSwapping = state.swappingRecipeId === meal.recipe_id;
            const sentVal = state.sentThermomixIds[meal.recipe_id];
            const isSent = Boolean(sentVal);
            const sentDayLabel = typeof sentVal === "string" ? sentVal : meal.day;
            const isLiked = state.recipePreferences.liked.includes(meal.recipe_id);
            const isDisliked = state.recipePreferences.disliked.includes(meal.recipe_id);
            const showKidBadge = Boolean(
              meal.is_kid_friendly && (p.constraints?.kidFriendly || Number(p.constraints?.children || 0) > 0)
            );
            return `
            <article class="meal-card" aria-busy="${isSwapping}">
              <figure class="meal-image">
                <img src="${escapeHtml(sanitizeUrl(meal.image_url, "/meals/lemon-hake-potatoes.webp"))}" alt="${escapeHtml(meal.image_alt)}" loading="lazy" onerror="this.onerror=null;this.src='/meals/lemon-hake-potatoes.webp';" />
                ${isLiked ? `<span class="meal-fav-badge">★ Favorita</span>` : ""}
                <div class="meal-vote-overlay" role="group" aria-label="Valorar receta ${escapeHtml(meal.name)}">
                  <button
                    type="button"
                    class="meal-vote-btn vote-up ${isLiked ? "active" : ""}"
                    data-vote-recipe="${escapeHtml(meal.recipe_id)}"
                    data-vote-type="up"
                    data-vote-name="${escapeHtml(meal.name)}"
                    title="${isLiked ? "Quitar de favoritas (volver a pulsar para desmarcar)" : "Me gusta: usar como inspiración en futuros menús"}"
                    aria-pressed="${isLiked}"
                    ${isSwapping ? "disabled" : ""}
                  >
                    <span aria-hidden="true">👍</span>
                  </button>
                  <button
                    type="button"
                    class="meal-vote-btn vote-down ${isDisliked ? "active" : ""}"
                    data-vote-recipe="${escapeHtml(meal.recipe_id)}"
                    data-vote-type="down"
                    data-vote-name="${escapeHtml(meal.name)}"
                    title="No me gusta: no volver a proponer y sustituir ahora por otra receta"
                    aria-pressed="${isDisliked}"
                    ${isSwapping ? "disabled" : ""}
                  >
                    <span aria-hidden="true">👎</span>
                  </button>
                </div>
              </figure>
              <div class="meal-card-body">
                <div class="meal-card-topline">
                  <div class="meal-number">0${idx + 1}</div>
                  <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                    ${showKidBadge ? `<span class="meal-kid-badge" title="Receta suave sin picante ni alcohol, ideal para niños pequeños">👶 Ideal niños</span>` : ""}
                    <div class="meal-day">${escapeHtml(meal.day)}</div>
                  </div>
                </div>
                <h3>${escapeHtml(meal.name)}</h3>
                <p>${escapeHtml(sanitizeRecipeDescription(meal.description))}</p>
                <div class="meal-meta">
                  <span>${meal.minutes} min</span>
                  <span>${formatEUR(meal.estimated_cost)}</span>
                  <span class="meal-calories">${Math.round(meal.calories_per_serving)} kcal/ración</span>
                </div>
                <div class="cookidoo-meta">
                  <span>Cookidoo ${escapeHtml(meal.cookidoo_id)}</span>
                  <span>${meal.cookidoo_servings} ${meal.cookidoo_servings === 1 ? "ración" : "raciones"} base</span>
                </div>
                <div class="meal-diners-scaler" role="group" aria-label="Comensales para ${escapeHtml(meal.day)}">
                  <span class="diners-label">👥 Comensales ${escapeHtml(meal.day)}:</span>
                  <div class="diners-pills">
                    ${[2, 3, 4, 6, 8]
                      .map((num) => {
                        const currentDiners = Number(
                          (p.day_servings && p.day_servings[meal.day]) ||
                            meal.active_diners ||
                            (p.constraints?.adults || 2) + (p.constraints?.children || 1)
                        );
                        const isActive = currentDiners === num;
                        return `<button type="button" class="diner-pill-btn ${isActive ? "active" : ""}" data-scale-day="${escapeHtml(meal.day)}" data-scale-diners="${num}" title="Ajustar ingredientes de ${escapeHtml(meal.day)} para ${num} personas (${num >= 6 ? "¡Hoy vienen invitados!" : "ración familiar"})" ${state.recalculatingBasket ? "disabled" : ""}>${num}p</button>`;
                      })
                      .join("")}
                  </div>
                </div>
                ${
                  meal.uses_from_home && meal.uses_from_home.length > 0
                    ? `<div class="reuse-note">Ya en casa (no se compra): ${escapeHtml(meal.uses_from_home.join(", "))}</div>`
                    : ""
                }
                <div class="meal-card-actions">
                  <button
                    type="button"
                    class="quick-swap-button"
                    data-swap-recipe="${escapeHtml(meal.recipe_id)}"
                    title="Cambiar solo esta receta sin regenerar el resto del menú semanal"
                    ${isSwapping ? "disabled" : ""}
                  >
                    ${isSwapping ? "Cambiando..." : "Cambio rápido"}
                    <span aria-hidden="true">↻</span>
                  </button>
                  <button
                    type="button"
                    class="thermomix-send-btn ${isSent ? "sent" : ""}"
                    data-thermomix-id="${escapeHtml(meal.recipe_id)}"
                    data-thermomix-url="${escapeHtml(sanitizeUrl(meal.cookidoo_url, "https://cookidoo.es"))}"
                    data-thermomix-name="${escapeHtml(meal.name)}"
                    data-thermomix-day="${escapeHtml(meal.day)}"
                    title="Asignar ${escapeHtml(meal.name)} al ${escapeHtml(meal.day)} en tu calendario Mi Semana de Cookidoo®"
                  >
                    ${isSent ? `Planificada (${escapeHtml(sentDayLabel)})` : `Planificar el ${escapeHtml(meal.day)}`}
                    <span aria-hidden="true">${isSent ? "✓" : "📅"}</span>
                  </button>
                </div>
                <p class="quick-swap-helper">
                  <strong>Cambio rápido</strong> sustituye solo esta cena manteniendo el resto del menú. <strong>Planificar el ${escapeHtml(meal.day)}</strong> programa la receta (${escapeHtml(meal.cookidoo_id)}) en ese día concreto de tu calendario <em>Mi Semana</em> de Cookidoo®.
                </p>
              </div>
            </article>
          `;
          })
          .join("")}
      </div>

      <p class="cookidoo-handoff-note">
        “Envía a tu Thermomix” conecta con la receta oficial en <strong>cookidoo.es</strong> y con <code>miaucl/cookidoo-api</code> para que puedas enviarla en un solo click a tu cuenta de Cookidoo.
      </p>

      <div class="basket-section" id="dia-cart-section">
        <div class="basket-tier-switcher" role="group" aria-label="Seleccionar gama de productos Mercadona">
          <div class="basket-tier-header">
            <div>
              <span class="eyebrow" style="margin-bottom:2px;">Personalización de Gama · Mercadona</span>
              <strong>Elige el nivel de tu cesta semanal en 1 clic</strong>
            </div>
            ${
              p.counter_notes_count
                ? `<span class="counter-summary-pill">🔪 ${p.counter_notes_count} notas de mostrador incluidas</span>`
                : ""
            }
          </div>
          <div class="basket-tier-buttons">
            <button
              type="button"
              class="tier-switch-btn ${(p.basket_tier || "ahorro") === "ahorro" ? "active" : ""}"
              data-basket-tier="ahorro"
              ${state.recalculatingBasket ? "disabled" : ""}
            >
              <span class="tier-icon">🏷️</span>
              <div>
                <strong>Hacendado (Ahorro)</strong>
                <small>Marca Hacendado · Mejor relación calidad-precio</small>
              </div>
            </button>
            <button
              type="button"
              class="tier-switch-btn ${p.basket_tier === "bio" ? "active" : ""}"
              data-basket-tier="bio"
              ${state.recalculatingBasket ? "disabled" : ""}
            >
              <span class="tier-icon">🌱</span>
              <div>
                <strong>Frescos Natur &amp; Bio</strong>
                <small>Huevos camperos, Verduras frescas &amp; Integral</small>
              </div>
            </button>
            <button
              type="button"
              class="tier-switch-btn ${p.basket_tier === "gourmet" ? "active" : ""}"
              data-basket-tier="gourmet"
              ${state.recalculatingBasket ? "disabled" : ""}
            >
              <span class="tier-icon">🥂</span>
              <div>
                <strong>Selección &amp; Bodega Mercadona</strong>
                <small>Ibéricos, AOVE Gran Selección + Sumiller IA</small>
              </div>
            </button>
          </div>
        </div>

        ${
          p.sommelier_pairing
            ? `
          <div class="sommelier-card ${p.sommelier_pairing.included ? "is-included" : ""}">
            <div class="sommelier-card-main">
              <span class="sommelier-icon" aria-hidden="true">🍷</span>
              <div class="sommelier-copy">
                <div class="sommelier-kicker">
                  <span>${escapeHtml(p.sommelier_pairing.title || "Sumiller IA · Bodega Mercadona")}</span>
                  <span class="sommelier-day-pill">Maridaje para el ${escapeHtml(p.sommelier_pairing.paired_with_day || "Viernes")}</span>
                </div>
                <strong>${escapeHtml(p.sommelier_pairing.wine_name)}</strong>
                <p>${escapeHtml(p.sommelier_pairing.tasting_note)}</p>
              </div>
            </div>
            <div class="sommelier-card-action">
              <span class="sommelier-price">+${formatEUR(p.sommelier_pairing.price || 5.65)}</span>
              <button
                type="button"
                id="toggle-sommelier-btn"
                class="sommelier-toggle-btn ${p.sommelier_pairing.included ? "active" : ""}"
                ${state.recalculatingBasket ? "disabled" : ""}
              >
                ${p.sommelier_pairing.included ? "✓ Incluido en tu cesta" : "+ Añadir maridaje Gourmet"}
              </button>
            </div>
          </div>
        `
            : ""
        }

        <div class="basket-header">
          <div>
            <p class="empty-kicker">Mapping al catálogo de Mercadona</p>
            <h3>${p.basket.length} productos de Mercadona · ${formatEUR(p.total)}</h3>
            <div class="catalog-source-badge">
              <span></span>
              Mercadona ${p.catalog_source === "live" ? "catálogo en tiempo real" : "snapshot verificado"} · CP ${escapeHtml(p.postal_code)} (${escapeHtml(p.warehouse)})
            </div>
            <div class="catalog-source-badge cookidoo-source">
              <span></span>
              Cookidoo catálogo oficial verificado
            </div>
            <div style="margin-top:10px; display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
              <button
                type="button"
                class="stock-verify-btn"
                id="verify-live-stock-btn"
                ${state.verifyingStock ? "disabled" : ""}
              >
                ${state.verifyingStock ? "⟳ Comprobando stock en tiempo real en Mercadona..." : `🔄 Verificar stock en vivo (CP ${escapeHtml(p.postal_code)})`}
              </button>
              <button
                type="button"
                class="stock-verify-btn whatsapp-sync-inline-btn"
                id="open-whatsapp-from-basket-btn"
              >
                💬 Enviar / Editar menú por WhatsApp
              </button>
              ${
                state.lastStockVerifiedAt
                  ? `<span class="stock-live-pill">✓ Stock verificado a las ${escapeHtml(state.lastStockVerifiedAt)} en ${escapeHtml(state.centerName || p.warehouse)}</span>`
                  : `<span class="stock-live-pill">✓ Filtrado por disponibilidad CP ${escapeHtml(p.postal_code)} (${escapeHtml(state.centerName || p.warehouse)})</span>`
              }
            </div>
          </div>
          <div class="budget-remaining">
            ${
              p.budget_remaining >= 0
                ? `${formatEUR(p.budget_remaining)} bajo tu límite`
                : `${formatEUR(Math.abs(p.budget_remaining))} sobre el límite`
            }
          </div>
        </div>

        <div class="basket-list">
          ${p.basket
            .map((item) => {
              const cp = item.counter_prep;
              const rm = item.retail_media_promo;
              const pidKey = item.base_product_id || item.product_id || item.id;
              return `
            <div class="basket-row ${cp ? "has-counter-note" : ""} ${item.is_sommelier_pairing ? "is-sommelier-row" : ""}">
              <div class="basket-product-mark" aria-hidden="true">
                ${
                  item.thumbnail
                    ? `<img src="${escapeHtml(sanitizeUrl(item.thumbnail, ""))}" alt="" loading="lazy" />`
                    : escapeHtml(item.name.charAt(0))
                }
              </div>
              <div class="basket-product-copy">
                <div class="basket-item-badges">
                  ${item.tier_badge ? `<span class="basket-tier-pill">${escapeHtml(item.tier_badge)}</span>` : ""}
                  ${
                    rm
                      ? `<span class="basket-rm-pill" title="${escapeHtml(rm.campaign_tag || "")}">🎯 ${escapeHtml(rm.badge)} (-${formatEUR(rm.discount_eur)})</span>`
                      : ""
                  }
                </div>
                <a href="${escapeHtml(sanitizeUrl(item.share_url, "https://tienda.mercadona.es/"))}" target="_blank" rel="noreferrer">
                  ${escapeHtml(item.name)} <span aria-hidden="true">↗</span>
                </a>
                <span>
                  ${item.quantity} × ${escapeHtml(item.unit)} (${formatEUR(item.unit_price)}/ud)
                  ${
                    item.used_in_days && item.used_in_days.length
                      ? ` · Para: ${escapeHtml(item.used_in_days.join(", "))}`
                      : ""
                  }
                  ${
                    item.upgraded_from
                      ? ` · <em>Mejorado desde: ${escapeHtml(item.upgraded_from)}</em>`
                      : ""
                  }
                </span>
                ${
                  cp
                    ? `
                  <div class="counter-prep-box">
                    <div class="counter-prep-header">
                      <span class="counter-dept-badge">${escapeHtml(cp.icon || "🔪")} ${escapeHtml(cp.department)}</span>
                      ${
                        cp.multi_tray
                          ? `<span class="counter-multitray-badge">📦 División automática en bandejas por día</span>`
                          : `<span class="counter-thermomix-badge">⚡ Corte adaptado a Thermomix®</span>`
                      }
                    </div>
                    <p class="counter-prep-note-text">${escapeHtml(cp.note)}</p>
                    ${
                      Array.isArray(cp.options) && cp.options.length > 0
                        ? `
                      <label class="counter-cut-selector-label">
                        <span>Personalizar preparación en mostrador:</span>
                        <select class="counter-cut-select" data-counter-pid="${escapeHtml(pidKey)}" ${state.recalculatingBasket ? "disabled" : ""}>
                          ${cp.options
                            .map(
                              (opt) =>
                                `<option value="${escapeHtml(opt)}" ${opt === cp.selected_cut ? "selected" : ""}>${escapeHtml(opt)}</option>`
                            )
                            .join("")}
                        </select>
                      </label>
                    `
                        : ""
                    }
                  </div>
                `
                    : ""
                }
              </div>
              <strong>${formatEUR(item.line_total)}</strong>
            </div>
          `;
            })
            .join("")}
        </div>

        <div class="eci-ecosystem-bar">
          <div class="eci-plus-progress-card">
            <div class="eci-plus-top">
              <strong>🚚 Logística Mercadona Online · Colmena &amp; Reparto Refrigerado</strong>
              <span class="eci-plus-pill ${p.eci_plus_status?.free_delivery_unlocked ? "unlocked" : ""}">
                ${p.eci_plus_status?.free_delivery_unlocked ? "✓ Envío GRATIS desbloqueado" : "Umbral envío gratis: 50,00 €"}
              </span>
            </div>
            <p>${escapeHtml(p.eci_plus_status?.eci_plus_message || `Conectado al centro ${state.centerName || p.warehouse} (CP ${p.postal_code}).`)}</p>
            <div class="eci-plus-bar-track" aria-hidden="true">
              <div class="eci-plus-bar-fill" style="width: ${Math.min(100, Math.round((Number(p.total || 0) / 50) * 100))}%;"></div>
            </div>
          </div>

          <div class="eci-delivery-mode-selector">
            <button
              type="button"
              class="delivery-mode-btn ${state.deliveryMode === "home_delivery" ? "active" : ""}"
              data-delivery-mode="home_delivery"
            >
              <span>🏠 Envío a Domicilio Hoy/Mañana</span>
              <small>Reparto refrigerado desde ${escapeHtml(state.centerName || p.warehouse)}</small>
            </button>
            <button
              type="button"
              class="delivery-mode-btn ${state.deliveryMode === "click_and_car" ? "active" : ""}"
              data-delivery-mode="click_and_car"
            >
              <span>🏪 Recogida Express / Taquilla Mercadona</span>
              <small>Preparación en tu supermercado Mercadona sin esperas</small>
            </button>
          </div>

          ${
            state.deliveryMode === "click_and_car"
              ? `
            <div class="click-and-car-slots">
              <span>Horario reservado en Recogida Mercadona (${escapeHtml(state.centerName || p.warehouse)}):</span>
              <div class="slot-pills">
                ${(
                  p.eci_plus_status?.click_and_car_slots || [
                    "Hoy 18:00 – 20:00 h (Tramo Mercadona Online)",
                    "Mañana 10:00 – 12:00 h (Tramo Mercadona Online)",
                    "Mañana 17:00 – 19:00 h (Tramo Mercadona Online)",
                  ]
                )
                  .map(
                    (slot) => `
                  <button
                    type="button"
                    class="slot-pill-btn ${state.selectedClickCarSlot === slot ? "active" : ""}"
                    data-clickcar-slot="${escapeHtml(slot)}"
                  >
                    ${escapeHtml(slot)}
                  </button>
                `
                  )
                  .join("")}
              </div>
            </div>
          `
              : ""
          }
        </div>

        <div class="allergen-note">
          <span>i</span>
          <p>${escapeHtml(p.allergen_notice)}</p>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; padding: 14px 0 10px; border-top: 1px solid var(--line); flex-wrap: wrap; gap: 10px; margin-top: 10px;">
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${state.diaSession.connected ? "#008f61" : "#9aa5a0"};"></span>
            <span style="font-size:12px; color:var(--ink); font-weight:600;">
              ${
                state.diaSession.connected
                  ? `Sesión Mercadona conectada (Cliente ${escapeHtml(state.diaSession.customer_id || "activo")} · ${escapeHtml(state.diaSession.warehouse || p.warehouse)}${state.diaSession.has_refresh_token ? " · Auto-refresh activo" : ""})`
                  : "Sincronización directa con tu carrito real de tienda.mercadona.es"
              }
            </span>
          </div>
          <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
            <label style="font-size:12px; color:var(--muted); display:flex; align-items:center; gap:6px;">
              Modo:
              <select id="dia-sync-mode-select" style="border:1px solid var(--line); background:#fff; padding:4px 8px; font-size:12px; border-radius:2px;">
                <option value="add" ${state.diaSyncMode === "add" ? "selected" : ""}>Sumar a mi carrito actual</option>
                <option value="replace" ${state.diaSyncMode === "replace" ? "selected" : ""}>Reemplazar mi carrito</option>
              </select>
            </label>
            <button type="button" class="text-button" id="toggle-dia-session-btn">
              ${
                state.diaModalOpen
                  ? "Ocultar configuración Mercadona"
                  : state.diaSession.connected
                  ? "Cambiar / Desvincular cuenta Mercadona"
                  : "🔗 Vincular cuenta Mercadona (1-Click)"
              }
            </button>
          </div>
        </div>

        ${renderDiaConnectBox()}

        <div class="dia-oneclick-bar">
          <div>
            <strong style="display:block; font-size:15px; margin-bottom:4px;">
              Añadir todos los productos al carrito de Mercadona
            </strong>
            <span style="font-size:12px; color:var(--muted);">
              ${
                state.diaSession.connected
                  ? `Se inyectarán directamente los ${p.basket.length} productos (${formatEUR(p.total)}) en tu carrito real de tienda.mercadona.es.`
                  : `Sincroniza los ${p.basket.length} productos disponibles en el CP ${escapeHtml(p.postal_code)} (${escapeHtml(p.warehouse)}) por ${formatEUR(p.total)}.`
              }
            </span>
          </div>
          <button
            type="button"
            class="dia-oneclick-btn"
            id="oneclick-dia-cart-btn"
            ${state.addingToCart ? "disabled" : ""}
          >
            ${
              state.addingToCart
                ? "Sincronizando con Mercadona..."
                : state.cartAddedResult && state.cartAddedResult.live_synced
                ? "✓ Añadidos a tu carrito real de Mercadona"
                : "Añadir al carrito de Mercadona (1-Click)"
            }
            <span aria-hidden="true">→</span>
          </button>
        </div>

        ${
          state.cartAddedResult
            ? `
          <div class="confirmation-state" role="status" style="margin-top:14px; flex-direction:column; align-items:stretch; gap:12px; padding:18px 20px;">
            <div style="display:flex; align-items:flex-start; gap:14px;">
              <span style="flex-shrink:0; width:34px; height:34px; border-radius:50%; background:var(--green); color:#fff; display:grid; place-items:center; font-weight:800;">✓</span>
              <div style="flex:1;">
                <strong style="font-size:14px; display:block; color:var(--ink);">${escapeHtml(state.cartAddedResult.message)}</strong>
                <p style="margin-top:4px; font-size:12px; color:var(--muted);">
                  Centro asignado: <strong>${escapeHtml(state.cartAddedResult.center_name || state.centerName || state.cartAddedResult.warehouse)}</strong> · CP <strong>${escapeHtml(state.cartAddedResult.postal_code)}</strong> · Total cesta: <strong>${escapeHtml(String(state.cartAddedResult.remote_cart_total || formatEUR(state.cartAddedResult.total)))}</strong>
                </p>
              </div>
            </div>
            ${
              state.cartAddedResult.live_synced && !state.cartAddedResult.precreated_cart_only
                ? `
              <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap; padding-top:8px; border-top:1px solid #b6d8c9;">
                <a
                  href="https://tienda.mercadona.es/"
                  target="_blank"
                  rel="noreferrer"
                  class="dia-oneclick-btn"
                  style="min-height:40px; font-size:12.5px; padding:0 16px; text-decoration:none;"
                >
                  Abrir mi cesta en Mercadona ↗
                </a>
                <span style="font-size:11.5px; color:var(--green-dark); font-weight:600;">
                  ✓ Tus ${escapeHtml(String(state.cartAddedResult.remote_products_count || state.cartAddedResult.unique_products))} productos ya están en tu sesión vinculada.
                </span>
              </div>
            `
                : `
              <div style="background:#ffffff; border:1px solid #b6d8c9; border-radius:4px; padding:14px 16px; display:grid; gap:10px;">
                <div style="font-size:12px; color:var(--ink); line-height:1.5;">
                  <strong>Opción A — Marcador 1-Click sin extensiones (Instantáneo):</strong>
                  Arrastra el botón verde <strong>“🛒 Cargar Cesta Mercadona (${escapeHtml(String(state.cartAddedResult.unique_products))} prod.)”</strong> a tu barra de marcadores, abre <a href="https://tienda.mercadona.es/" target="_blank" rel="noreferrer" style="color:var(--green-dark); font-weight:700; text-decoration:underline;">tienda.mercadona.es ↗</a> y púlsalo para activar la cesta que nuestro servidor acaba de pre-crear (ID <code>${escapeHtml(String((state.cartAddedResult.precreated_attempt_id || "").slice(0, 18)))}...</code>).
                </div>
                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                  <a
                    href="${escapeHtml(buildPrecreatedCartBookmarkletHref(state.cartAddedResult))}"
                    id="precreated-cart-bookmarklet"
                    class="dia-bookmarklet-btn"
                    draggable="true"
                    title="Arrástrame a tu barra de marcadores y púlsame en tienda.mercadona.es"
                  >
                    🛒 Cargar Cesta Mercadona (${escapeHtml(String(state.cartAddedResult.unique_products))} prod.)
                  </a>
                  <button
                    type="button"
                    class="secondary-button compact"
                    id="copy-dia-script-btn"
                    style="margin-top:0; min-height:36px; font-size:11.5px; padding:0 14px;"
                  >
                    📋 Copiar comando 1-Click y abrir Mercadona Online ↗
                  </button>
                  <a
                    href="https://tienda.mercadona.es/"
                    target="_blank"
                    rel="noreferrer"
                    style="font-size:12px; font-weight:700; color:var(--green-dark); text-decoration:underline;"
                  >
                    Ir a tienda.mercadona.es ↗
                  </a>
                </div>
              </div>
            `
            }
          </div>
        `
            : ""
        }

        <div class="follow-up-row">
          <span>Prueba a ajustar tu menú</span>
          ${FOLLOW_UP_PROMPTS.map(
            (fp) => `<button type="button" class="followup-btn" data-followup="${escapeHtml(fp)}">${escapeHtml(fp)}</button>`
          ).join("")}
        </div>
      </div>
    </div>
  `;
}

function renderPlannerView() {
  const activeProfile = PROFILES.find((p) => p.id === state.profileId) || PROFILES[0];
  const activeCampaigns = getActiveCampaigns();
  const featuredCampaign =
    state.campaigns.find((c) => c.id === state.selectedCampaignId) ||
    activeCampaigns.find((c) => c.profileId === state.profileId) ||
    activeCampaigns[0];

  return `
    <section class="personalised-hero" id="for-you">
      <div class="personalised-copy">
        <p class="eyebrow">Personalizado para tu familia</p>
        <h1>Deja de llenar carritos. Empieza a planificar semanas.</h1>
        <p class="hero-subtitle">
          Diseñado por nutricionistas expertos. A la medida de tu dieta y tu bolsillo. Te lo lleva Mercadona.
        </p>
        <div class="profile-explanation">
          <span class="profile-monogram" aria-hidden="true">${escapeHtml(activeProfile.icon)}</span>
          <div>
            <strong>${escapeHtml(activeProfile.name)}</strong>
            <p>${escapeHtml(activeProfile.household)} · ${escapeHtml(activeProfile.primaryNeed)}</p>
          </div>
        </div>
      </div>

      <article class="featured-campaign-card">
        <figure>
          <img src="${escapeHtml(sanitizeUrl(featuredCampaign.imageUrl, "/meals/lemon-hake-potatoes.webp"))}" alt="${escapeHtml(featuredCampaign.title)}" />
        </figure>
        <div class="featured-campaign-overlay">
          <span class="campaign-badge">${escapeHtml(featuredCampaign.badge)}</span>
          <h2>${escapeHtml(featuredCampaign.title)}</h2>
          <p>${escapeHtml(featuredCampaign.tagline)}</p>
          <div class="campaign-facts light">
            <span>${featuredCampaign.mealCount} cenas</span>
            <span>≤ ${featuredCampaign.maxMinutes} min</span>
            <span>≤ €${Number(featuredCampaign.maxBudget).toFixed(2)}</span>
          </div>
          <button class="campaign-hero-button" type="button" id="hero-personalise-btn">
            Personalizar esta semana <span aria-hidden="true">→</span>
          </button>
        </div>
      </article>
    </section>

    <section class="campaign-discovery" aria-labelledby="campaign-discovery-title">
      <div class="campaign-discovery-heading">
        <div>
          <p class="eyebrow">Más ideas para tu semana</p>
          <h2 id="campaign-discovery-title">Olvida el buscador. Elije una de nuestras propuestas.</h2>
        </div>
        <span>${activeCampaigns.length} propuestas semanales activas</span>
      </div>
      <div class="campaign-card-grid">
        ${activeCampaigns
          .map(
            (c) => `
          <button
            type="button"
            class="discovery-campaign-card ${c.id === featuredCampaign.id ? "selected" : ""}"
            data-campaign-id="${escapeHtml(c.id)}"
            aria-pressed="${c.id === featuredCampaign.id}"
          >
            <img src="${escapeHtml(sanitizeUrl(c.imageUrl, "/meals/lemon-hake-potatoes.webp"))}" alt="" />
            <span class="discovery-campaign-copy">
              <small>${escapeHtml(c.category || c.occasion)}</small>
              <strong>${escapeHtml(c.title)}</strong>
              <span>${c.mealCount} cenas · ≤ ${c.maxMinutes} min · ≤ €${Number(c.maxBudget).toFixed(2)}</span>
            </span>
            <span class="discovery-arrow" aria-hidden="true">↗</span>
          </button>
        `
          )
          .join("")}
      </div>
    </section>

    <section class="hero-grid planner-journey" id="planner">
      <div class="hero-copy">
        <p class="eyebrow">Hazlo a tu medida</p>
        <h1>Los planes cambian. Tu menú semanal también.</h1>
        <p class="hero-subtitle">
          Empieza a partir de la propuesta de Mercadona y añade una alergia, un objetivo de calorías, un presupuesto más ajustado, un ingrediente que ya tengas en casa o un cambio de planes.
        </p>
        <div class="selected-campaign-context">
          <span>Punto de partida</span>
          <strong>${escapeHtml(featuredCampaign.title)} · CP ${escapeHtml(state.postalCode)} (${escapeHtml(state.warehouse)})</strong>
        </div>

        <form class="planner-form" id="planner-form">
          <label for="planner-request">¿Cómo quieres tu menú semanal de cenas?</label>
          <textarea
            id="planner-request"
            rows="5"
            maxlength="4000"
            placeholder="Ej.: Planifica 5 cenas para 2 adultos y 1 niño con presupuesto máximo de 65€, menos de 500 kcal por receta, en 25 minutos o menos, sin frutos secos y usando la pasta que ya tengo en casa."
          >${escapeHtml(state.prompt)}</textarea>

          <div
            id="scope-guard-banner"
            class="scope-hint"
            role="alert"
            style="${validateMealPlanningPrompt(state.prompt).valid ? "display:none;" : "display:block;"}"
          >
            ${escapeHtml(OUT_OF_SCOPE_PROMPT_MESSAGE)}
          </div>

          <div class="constraint-row" id="constraint-pills-row" aria-label="Condiciones detectadas">
            ${state.detectedPills.map((pill) => `<span>${escapeHtml(pill)}</span>`).join("")}
          </div>

          <div class="kid-friendly-helper-row">
            <button
              type="button"
              id="toggle-kid-friendly-prompt-btn"
              class="kid-friendly-chip-btn ${/\b(?:ni[ñn]os?\s+peque[ñn]os?|apt[oa]s?\s+para\s+ni[ñn]os?|suaves?\s+para\s+ni[ñn]os?|infantil)\b/i.test(state.prompt) ? "active" : ""}"
              title="Añade o activa la preferencia de platos suaves sin picante ni alcohol pensados para niños pequeños"
            >
              👶 ${/\b(?:ni[ñn]os?\s+peque[ñn]os?|apt[oa]s?\s+para\s+ni[ñn]os?|suaves?\s+para\s+ni[ñn]os?|infantil)\b/i.test(state.prompt) ? "Modo niños pequeños activo (sin picante ni alcohol)" : "Priorizar recetas suaves para niños pequeños"}
            </button>
          </div>

          ${
            state.recipePreferences.liked.length > 0 || state.recipePreferences.disliked.length > 0
              ? `
            <div class="recipe-prefs-bar" role="status">
              <div class="recipe-prefs-counts">
                <span class="pref-pill liked">👍 ${state.recipePreferences.liked.length} ${state.recipePreferences.liked.length === 1 ? "receta favorita" : "recetas favoritas"}</span>
                <span class="pref-pill disliked">👎 ${state.recipePreferences.disliked.length} ${state.recipePreferences.disliked.length === 1 ? "receta descartada" : "recetas descartadas"}</span>
                <span style="color:var(--muted);">Se tendrán en cuenta al generar o cambiar recetas</span>
              </div>
              <button type="button" class="text-button" id="clear-recipe-prefs-btn" style="font-size:12px;">
                Limpiar historial de gustos
              </button>
            </div>
          `
              : ""
          }

          <div class="form-actions">
            <button
              class="primary-button"
              id="planner-submit-btn"
              type="submit"
              ${state.loading || !validateMealPlanningPrompt(state.prompt).valid ? "disabled" : ""}
            >
              ${state.loading ? "Elaborando menú con Google Gemini" : "Generar mi menú semanal"}
              <span aria-hidden="true">↗</span>
            </button>
            ${
              state.plan
                ? `<button class="text-button" type="button" id="reset-plan-btn">Reiniciar</button>`
                : ""
            }
          </div>
        </form>

        <div class="fridge-vision-standalone-card" aria-label="Nevera y Despensa Vision">
          <div class="fridge-vision-clean-header">
            <div class="fridge-vision-title-group">
              <span class="fridge-vision-badge-pill">📸 Nevera &amp; Despensa Vision</span>
              <strong>¿Tienes frescos en la nevera? Aprovéchalos y descuéntalos de tu cesta</strong>
              <p>Sube una foto de tu nevera o prueba un ejemplo rápido con Google Gemini Multimodal.</p>
            </div>
            <div>
              <input type="file" id="fridge-photo-input" accept="image/*" capture="environment" style="display:none;" />
              <button
                type="button"
                id="upload-fridge-photo-btn"
                class="fridge-upload-btn"
                ${state.fridgeVisionLoading ? "disabled" : ""}
              >
                ${state.fridgeVisionLoading ? "⟳ Analizando nevera..." : "📷 Subir foto de mi nevera"}
              </button>
            </div>
          </div>

          <div class="fridge-presets-clean-row">
            <span class="fridge-preset-label">O prueba un ejemplo en 1 clic:</span>
            <button type="button" class="fridge-preset-chip" data-fridge-preset="nevera_mediterranea" ${state.fridgeVisionLoading ? "disabled" : ""}>
              🥗 Mediterránea (Calabacín, Huevos, Espinacas)
            </button>
            <button type="button" class="fridge-preset-chip" data-fridge-preset="nevera_familiar" ${state.fridgeVisionLoading ? "disabled" : ""}>
              🍗 Familiar (Pollo, Zanahorias, Pimiento)
            </button>
            <button type="button" class="fridge-preset-chip" data-fridge-preset="nevera_verde" ${state.fridgeVisionLoading ? "disabled" : ""}>
              🥦 Veggie (Brócoli, Tomate, Aguacate)
            </button>
          </div>

          ${
            state.plan?.fridge_vision || state.fridgeVisionResult
              ? (() => {
                  const fv = state.plan?.fridge_vision || state.fridgeVisionResult;
                  return `
                <div class="fridge-vision-result-banner" role="status">
                  <div class="fv-result-header">
                    <strong>✓ ${escapeHtml(fv.title || "Nevera analizada con Google Gemini Vision")}</strong>
                    <span class="fv-savings-badge">Ahorro directo: -${formatEUR(fv.estimated_savings_eur || 8.45)}</span>
                  </div>
                  <div class="fv-items-grid">
                    ${(fv.detected_items || [])
                      .map(
                        (it) => `
                      <span class="fridge-item-pill">
                        <strong>✓ ${escapeHtml(it.name)}</strong> · <small>${escapeHtml(it.freshness || "Priorizado")}</small>
                      </span>
                    `
                      )
                      .join("")}
                  </div>
                </div>
              `;
                })()
              : ""
          }
        </div>

        <div class="trust-note">
          <span class="trust-icon">✓</span>
          <p>
            Las recetas, fotos de portada y valores nutricionales provienen de <strong>Cookidoo</strong>. Los nombres de producto, formatos, precios y disponibilidad en tiempo real provienen de la API de <strong>Mercadona (tienda.mercadona.es)</strong>.
          </p>
        </div>
      </div>

      <div class="experience-panel ${state.plan ? "has-plan" : ""}">
        ${renderExperiencePanel()}
      </div>
    </section>

    <section class="md3-pillars-section" aria-label="Ecosistema conectado">
      <div class="md3-pillars-grid">
        <article class="md3-pillar-card">
          <div class="md3-pillar-top">
            <span class="md3-pillar-icon" aria-hidden="true">✨</span>
            <span class="md3-pillar-chip">IA Generativa</span>
          </div>
          <h3>Google Gemini</h3>
          <p>Interpreta en español tus raciones, presupuesto, calorías, alergias e ingredientes que ya tienes en casa.</p>
        </article>
        <article class="md3-pillar-card">
          <div class="md3-pillar-top">
            <span class="md3-pillar-icon" aria-hidden="true">🍲</span>
            <span class="md3-pillar-chip">Thermomix®</span>
          </div>
          <h3>5.000 Recetas Cookidoo®</h3>
          <p>Platos oficiales verificados con tiempos reales, valores nutricionales y envío directo a tu Thermomix.</p>
        </article>
        <article class="md3-pillar-card">
          <div class="md3-pillar-top">
            <span class="md3-pillar-icon" aria-hidden="true">🛍️</span>
            <span class="md3-pillar-chip">API Mercadona Tienda</span>
          </div>
          <h3>Stock Real por Código Postal</h3>
          <p>Mapeo exacto a 1.595 productos de Mercadona (Hacendado y frescos) con precios y disponibilidad en tu centro logístico.</p>
        </article>
      </div>
    </section>
  `;
}

function renderCatalogView() {
  const data = state.catalogData;
  const allProducts = data?.products || [];
  const q = state.catalogSearch.trim().toLowerCase();
  const filtered = allProducts.filter(
    (p) => !q || p.name.toLowerCase().includes(q) || p.id.includes(q)
  );
  const pageSize = 30;
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const curPage = Math.min(Math.max(1, state.catalogPage), totalPages);
  const startIdx = (curPage - 1) * pageSize;
  const pageItems = filtered.slice(startIdx, startIdx + pageSize);

  return `
    <section class="source-section" style="max-width:1480px; margin:0 auto; padding: 48px 0;">
      <p class="eyebrow">API de Mercadona (tienda.mercadona.es) · CP ${escapeHtml(state.postalCode)} (${escapeHtml(state.warehouse)})</p>
      <h1 style="font-size: clamp(42px, 5vw, 72px); margin-bottom: 18px;">Catálogo de Productos de Mercadona (${allProducts.length})</h1>
      <p class="hero-subtitle">
        Productos verificados en la API de Mercadona (<code>tienda.mercadona.es/api/v1/plp-back/reduced</code>, <code>/api/v1/pdp-back/&lt;sku&gt;</code> y <code>Parse.bot Dia ES API</code> (tienda <code>${escapeHtml(state.warehouse)}</code>)) utilizados para el mapping de las 5.000 recetas.
      </p>
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px; margin-bottom: 24px;">
        <div style="flex:1; min-width: 280px; max-width: 480px;">
          <input
            type="search"
            id="catalog-filter-input"
            placeholder="Buscar entre ${allProducts.length} productos de Mercadona (ej. Dia Nuestra Alacena, salmón, 3400)..."
            value="${escapeHtml(state.catalogSearch)}"
            style="width:100%; border:1px solid var(--line); background:#fff; padding:12px 14px; font-size:14px; border-radius:3px;"
          />
        </div>
        <div style="font-size:13px; color:var(--muted);">
          Mostrando <strong>${filtered.length ? startIdx + 1 : 0}–${Math.min(startIdx + pageSize, filtered.length)}</strong> de <strong>${filtered.length}</strong> productos
        </div>
      </div>
      <div class="basket-list" style="background:#fff; border:1px solid var(--line); padding: 12px 24px;">
        ${
          !data
            ? `<p style="padding:24px 0;">Cargando catálogo de Mercadona...</p>`
            : pageItems
                .map(
                  (p) => `
              <div class="basket-row">
                <div class="basket-product-mark">
                  ${p.thumbnail ? `<img src="${escapeHtml(sanitizeUrl(p.thumbnail, ""))}" alt="" loading="lazy" />` : escapeHtml(p.name.charAt(0))}
                </div>
                <div class="basket-product-copy">
                  <a href="${escapeHtml(sanitizeUrl(p.share_url, "https://tienda.mercadona.es/"))}" target="_blank" rel="noreferrer">
                    ${escapeHtml(p.name)} <span aria-hidden="true">↗</span>
                  </a>
                  <span>ID: <code>${escapeHtml(p.id)}</code> · Formato: ${escapeHtml(p.unit)} · Alérgenos: ${escapeHtml(p.allergens)}</span>
                </div>
                <strong>${formatEUR(p.unit_price)}</strong>
              </div>
            `
                )
                .join("")
        }
      </div>
      ${
        totalPages > 1
          ? `
        <div class="catalog-pagination">
          <button type="button" id="cat-prev-btn" ${curPage <= 1 ? "disabled" : ""}>← Anterior</button>
          <span>Página <strong>${curPage}</strong> de <strong>${totalPages}</strong></span>
          <button type="button" id="cat-next-btn" ${curPage >= totalPages ? "disabled" : ""}>Siguiente →</button>
        </div>
      `
          : ""
      }
    </section>
  `;
}

function renderSourcesView() {
  const allRecipes = state.catalogData?.recipes || [];
  const q = state.recipesSearch.trim().toLowerCase();
  const filtered = allRecipes.filter(
    (r) =>
      !q ||
      r.name.toLowerCase().includes(q) ||
      r.cookidoo_id.toLowerCase().includes(q) ||
      (r.category && r.category.toLowerCase().includes(q)) ||
      (r.ingredients && r.ingredients.some((i) => i.toLowerCase().includes(q)))
  );
  const pageSize = 24;
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const curPage = Math.min(Math.max(1, state.recipesPage), totalPages);
  const startIdx = (curPage - 1) * pageSize;
  const pageItems = filtered.slice(startIdx, startIdx + pageSize);

  return `
    <section class="source-section" style="max-width:1480px; margin:0 auto; padding: 48px 0;">
      <p class="eyebrow">Transparencia e Integraciones · Cookidoo España</p>
      <h1 style="font-size: clamp(42px, 5vw, 72px); margin-bottom: 18px;">Catálogo de Recetas de Cookidoo (${allRecipes.length})</h1>
      <p class="hero-subtitle">
        Las ${allRecipes.length} recetas de Cookidoo España conectadas mediante <code>miaucl/cookidoo-api</code> con foto de portada oficial, calorías, tiempo de preparación y mapping al catálogo de Mercadona.
      </p>
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px; margin-bottom: 24px;">
        <div style="flex:1; min-width: 280px; max-width: 520px;">
          <input
            type="search"
            id="recipes-filter-input"
            placeholder="Buscar entre las ${allRecipes.length} recetas por plato, ingrediente o ID (ej. merluza, lentejas, r55690)..."
            value="${escapeHtml(state.recipesSearch)}"
            style="width:100%; border:1px solid var(--line); background:#fff; padding:12px 14px; font-size:14px; border-radius:3px;"
          />
        </div>
        <div style="font-size:13px; color:var(--muted);">
          Mostrando <strong>${filtered.length ? startIdx + 1 : 0}–${Math.min(startIdx + pageSize, filtered.length)}</strong> de <strong>${filtered.length}</strong> recetas
        </div>
      </div>
      <div class="meal-grid" style="border-top:1px solid var(--line);">
        ${
          !state.catalogData
            ? `<p style="padding:24px;">Cargando las 5.000 recetas de Cookidoo España...</p>`
            : pageItems
                .map(
                  (r, idx) => `
          <article class="meal-card">
            <figure class="meal-image">
              <img src="${escapeHtml(sanitizeUrl(r.image_url, "/meals/lemon-hake-potatoes.webp"))}" alt="${escapeHtml(r.name)}" loading="lazy" onerror="this.onerror=null;this.src='/meals/lemon-hake-potatoes.webp';" />
            </figure>
            <div class="meal-card-body">
              <div class="meal-card-topline">
                <div class="meal-number">#${String(startIdx + idx + 1).padStart(2, "0")}</div>
                <div class="meal-day">${escapeHtml(r.cookidoo_id)}</div>
              </div>
              <h3>${escapeHtml(r.name)}</h3>
              <p>${escapeHtml(sanitizeRecipeDescription(r.description))}</p>
              <div class="meal-meta">
                <span>${r.minutes} min</span>
                <span>${formatEUR(r.estimated_cost)}</span>
                <span class="meal-calories">${r.calories_per_serving} kcal/ración</span>
              </div>
              <div class="meal-card-actions" style="grid-template-columns: 1fr;">
                <button
                  type="button"
                  class="thermomix-send-btn"
                  data-thermomix-id="${escapeHtml(r.recipe_id)}"
                  data-thermomix-url="${escapeHtml(sanitizeUrl(r.cookidoo_url, "https://cookidoo.es"))}"
                  data-thermomix-name="${escapeHtml(r.name)}"
                >
                  Envía a tu Thermomix (${escapeHtml(r.cookidoo_id)})
                  <span aria-hidden="true">↗</span>
                </button>
              </div>
            </div>
          </article>
        `
                )
                .join("")
        }
      </div>
      ${
        totalPages > 1
          ? `
        <div class="catalog-pagination">
          <button type="button" id="rec-prev-btn" ${curPage <= 1 ? "disabled" : ""}>← Anterior</button>
          <span>Página <strong>${curPage}</strong> de <strong>${totalPages}</strong> (${filtered.length} recetas)</span>
          <button type="button" id="rec-next-btn" ${curPage >= totalPages ? "disabled" : ""}>Siguiente →</button>
        </div>
      `
          : ""
      }
    </section>
  `;
}

function renderWhatsAppDrawer() {
  if (!state.whatsappOpen) return "";
  const ws = state.whatsappState || {};
  const messages = Array.isArray(ws.messages) ? ws.messages : [];
  const stats = ws.webhook_stats || {};
  const shareUrl = ws.share_wa_url || "https://wa.me/";
  const webhookUrl = ws.webhook_url || `${window.location.origin}/api/whatsapp/webhook`;

  return `
    <div class="wa-drawer-backdrop" id="wa-drawer-backdrop" role="dialog" aria-modal="true" aria-labelledby="wa-drawer-title">
      <aside class="wa-drawer-panel">
        <header class="wa-drawer-header">
          <div class="wa-header-brand">
            <div class="wa-avatar">MER</div>
            <div>
              <div style="display:flex; align-items:center; gap:6px;">
                <h2 id="wa-drawer-title">Mercadona</h2>
                <span class="wa-verified-check" title="Cuenta de empresa verificada de WhatsApp Business">✓</span>
              </div>
              <p>Asistente IA Cookidoo × Mercadona · En línea (Sincronización en vivo)</p>
            </div>
          </div>
          <div class="wa-header-actions">
            ${
              messages.length > 0
                ? `<button
              type="button"
              id="wa-clear-chat-btn"
              class="wa-header-btn"
              title="Vaciar conversación de WhatsApp"
            >
              🗑️ Vaciar
            </button>`
                : ""
            }
            <button
              type="button"
              id="wa-toggle-config-btn"
              class="wa-header-btn ${state.whatsappConfigOpen ? "active" : ""}"
              title="Ver URL del Webhook Real (Meta Cloud API / Twilio TwiML)"
            >
              ⚙️ Webhook Real
            </button>
            <button type="button" id="wa-close-drawer-btn" class="wa-close-btn" aria-label="Cerrar WhatsApp">✕</button>
          </div>
        </header>

        <div class="wa-subbar">
          <span class="wa-sync-indicator">
            <span class="wa-live-dot"></span>
            Webhook Bidireccional Activo · Eventos: <strong>${Number(stats.total_received || 0)}</strong>
          </span>
          <a
            href="${escapeHtml(sanitizeUrl(shareUrl, "https://wa.me/"))}"
            target="_blank"
            rel="noopener noreferrer"
            class="wa-real-phone-link"
            title="Abrir este menú semanal directamente en la app de WhatsApp de tu teléfono o WhatsApp Web"
          >
            📲 Abrir en mi WhatsApp (wa.me) ↗
          </a>
        </div>

        ${
          state.whatsappConfigOpen
            ? `
          <div class="wa-webhook-config-panel">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <strong>🔗 Opción B Activa: Endpoint de Webhook Real (Meta Cloud API &amp; Twilio TwiML)</strong>
              <span class="wa-badge-ready">HTTP GET + POST Listo</span>
            </div>
            <p style="font-size:11.5px; color:#344054; margin-bottom:10px; line-height:1.45;">
              Este endpoint público en Cloud Run acepta tanto <strong>Meta WhatsApp Cloud API</strong> (JSON + validación <code>hub.verify_token</code>) como <strong>Twilio WhatsApp Sandbox</strong> (<code>application/x-www-form-urlencoded</code> con respuesta instantánea <code>TwiML XML</code>). Cualquier mensaje recibido desde tu móvil actualiza automáticamente el menú semanal en esta pantalla.
            </p>
            <div class="wa-webhook-field-row">
              <label>Callback Webhook URL:</label>
              <div style="display:flex; gap:6px;">
                <input type="text" readonly value="${escapeHtml(webhookUrl)}" id="wa-webhook-url-input" />
                <button type="button" id="wa-copy-webhook-url-btn" class="secondary-button compact" style="margin:0; min-height:30px; padding:0 10px; font-size:11px;">📋 Copiar URL</button>
              </div>
            </div>
            <div class="wa-webhook-field-row">
              <label>Verify Token (Meta):</label>
              <div style="display:flex; gap:6px;">
                <input type="text" readonly value="${escapeHtml(ws.verify_token || "mercadona-whatsapp-2026")}" id="wa-verify-token-input" />
                <button type="button" id="wa-copy-verify-token-btn" class="secondary-button compact" style="margin:0; min-height:30px; padding:0 10px; font-size:11px;">📋 Copiar Token</button>
              </div>
            </div>
            <div class="wa-webhook-sim-row">
              <span>Disparar prueba real contra <code>POST /api/whatsapp/webhook</code>:</span>
              <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:6px;">
                <button type="button" id="wa-sim-twilio-btn" class="wa-sim-btn" ${state.whatsappSending ? "disabled" : ""}>
                  ⚡ Probar Webhook Twilio (TwiML)
                </button>
                <button type="button" id="wa-sim-meta-btn" class="wa-sim-btn" ${state.whatsappSending ? "disabled" : ""}>
                  ⚡ Probar Webhook Meta Cloud API (JSON)
                </button>
              </div>
            </div>
          </div>
        `
            : ""
        }

        <div class="wa-chat-messages" id="wa-chat-messages">
          <div class="wa-encryption-pill">
            🔒 Los mensajes se procesan con Google Gemini y sincronizan tu menú semanal y tu cesta de Mercadona en vivo.
          </div>
          ${
            messages.length === 0 && !state.whatsappSending
              ? `
            <div class="wa-empty-state">
              <div class="wa-empty-icon">💬</div>
              <strong>Aún no hay mensajes en esta conversación</strong>
              <p>Escribe un mensaje abajo o pulsa cualquiera de las sugerencias rápidas para ver o modificar tu menú semanal en vivo.</p>
            </div>
          `
              : ""
          }
          ${messages
            .map((m) => {
              const isUser = m.sender === "user";
              return `
              <div class="wa-msg-row ${isUser ? "wa-msg-user" : "wa-msg-bot"}">
                <div class="wa-bubble ${isUser ? "wa-bubble-user" : "wa-bubble-bot"}">
                  <div class="wa-bubble-text">${formatWhatsAppMarkdown(m.text)}</div>
                  <div class="wa-bubble-meta">
                    <span>${escapeHtml(m.timestamp || "Ahora")}</span>
                    ${isUser ? `<span class="wa-ticks">✓✓</span>` : ""}
                  </div>
                </div>
                ${
                  !isUser && Array.isArray(m.buttons) && m.buttons.length > 0
                    ? `
                  <div class="wa-interactive-buttons">
                    ${m.buttons
                      .map(
                        (btn) => `
                      <button
                        type="button"
                        class="wa-interactive-btn"
                        data-wa-quick="${escapeHtml(btn.id || btn.title)}"
                        ${state.whatsappSending ? "disabled" : ""}
                      >
                        ${escapeHtml(btn.title)}
                      </button>
                    `
                      )
                      .join("")}
                  </div>
                `
                    : ""
                }
              </div>
            `;
            })
            .join("")}
          ${
            state.whatsappSending
              ? `
            <div class="wa-msg-row wa-msg-bot">
              <div class="wa-bubble wa-bubble-bot">
                <div class="wa-bubble-text"><em>Escribiendo y recalculando cesta en Mercadona...</em></div>
              </div>
            </div>
          `
              : ""
          }
        </div>

        <div class="wa-quick-prompts" role="group" aria-label="Acciones rápidas de WhatsApp">
          <button type="button" class="wa-chip" data-wa-quick="Ver mi menú semanal">📋 Ver menú</button>
          <button type="button" class="wa-chip" data-wa-quick="Cambia el miércoles por una cena rápida de pescado">🐟 Miércoles pescado</button>
          <button type="button" class="wa-chip" data-wa-quick="El viernes somos 6 personas">👥 Viernes 6 personas</button>
          <button type="button" class="wa-chip" data-wa-quick="cmd:cookidoo">📅 Planificar en Cookidoo</button>
          <button type="button" class="wa-chip" data-wa-quick="cmd:gourmet">🥂 Selección & Bodega</button>
          <button type="button" class="wa-chip" data-wa-quick="cmd:cart">🛒 Carrito 1-Click Mercadona</button>
        </div>

        <form class="wa-input-bar" id="wa-chat-form">
          <button
            type="button"
            id="wa-voice-note-btn"
            class="wa-icon-btn ${state.whatsappListeningVoice ? "listening" : ""}"
            title="Enviar nota de voz en español (ej. 'El viernes vienen invitados, pon para 6 personas')"
            ${state.whatsappSending ? "disabled" : ""}
          >
            🎤
          </button>
          <input
            type="text"
            id="wa-chat-input"
            placeholder="Escribe un mensaje (ej. «cambia el jueves por salmón» o «viernes 6 personas»)..."
            value="${escapeHtml(state.whatsappInput)}"
            autocomplete="off"
          />
          <button type="submit" class="wa-send-btn" ${state.whatsappSending ? "disabled" : ""}>
            Enviar ➤
          </button>
        </form>
      </aside>
    </div>
  `;
}

function renderFloatingWhatsAppButton() {
  if (state.whatsappOpen) return "";
  return `
    <button
      type="button"
      id="floating-whatsapp-btn"
      class="wa-floating-fab"
      title="Abrir Asistente WhatsApp Business Mercadona (Sincronizado en vivo)"
    >
      <span class="wa-fab-icon">💬</span>
      <span class="wa-fab-copy">
        <strong>WhatsApp Mercadona</strong>
        <small>Menú &amp; Cesta en vivo</small>
      </span>
    </button>
  `;
}

function renderVideoModal() {
  if (!state.videoModalOpen) return "";
  return `
    <div class="md3-video-modal-backdrop" id="video-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="video-modal-title">
      <div class="md3-video-modal-card">
        <div class="md3-video-modal-header">
          <div>
            <span class="md3-pillar-chip">Vídeo Presentación · Locución en Español + Música</span>
            <h2 id="video-modal-title">Mercadona · AI Meal Planner</h2>
          </div>
          <button type="button" class="md3-video-close-btn" id="close-video-modal-btn" aria-label="Cerrar vídeo">✕ Cerrar</button>
        </div>
        <div class="md3-video-player-wrap">
          <video
            id="demo-video-player"
            src="/demo.mp4?v=eci-2026-es3"
            controls
            autoplay
            playsinline
          ></video>
        </div>
        <div class="md3-video-modal-footer">
          <span>🔊 Incluye locución en español de España (Gemini TTS) y música ambiental de fondo.</span>
          <a href="/demo.mp4?v=eci-2026-es3" download="Supermercado_El_Corte_Ingles_AI_Meal_Planner_Demo.mp4" class="secondary-button compact">⬇ Descargar MP4</a>
        </div>
      </div>
    </div>
  `;
}

function render() {
  const root = document.getElementById("app-root");
  if (!root) return;

  root.innerHTML = `
    ${renderAuthModal()}
    ${renderVideoModal()}
    ${renderWhatsAppDrawer()}
    ${renderFloatingWhatsAppButton()}
    <main class="app-shell">
      ${renderHeader()}
      ${
        state.activeTab === "catalog"
          ? renderCatalogView()
          : state.activeTab === "sources"
          ? renderSourcesView()
          : renderPlannerView()
      }
    </main>
    ${
      state.toast
        ? `
      <div class="toast-banner" role="status">
        <strong>${escapeHtml(state.toast.title)}</strong>
        <span>${escapeHtml(state.toast.body)}</span>
      </div>
    `
        : ""
    }
  `;

  bindEvents();
}

function bindEvents() {
  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", logoutUser);
  }

  const videoDemoBtn = document.getElementById("header-video-demo-btn");
  if (videoDemoBtn) {
    videoDemoBtn.addEventListener("click", () => {
      state.videoModalOpen = true;
      render();
      const vid = document.getElementById("demo-video-player");
      if (vid) {
        vid.muted = false;
        vid.volume = 1.0;
        vid.play().catch(() => {});
      }
    });
  }
  const closeVideoBtn = document.getElementById("close-video-modal-btn");
  if (closeVideoBtn) {
    closeVideoBtn.addEventListener("click", () => {
      const vid = document.getElementById("demo-video-player");
      if (vid) vid.pause();
      state.videoModalOpen = false;
      render();
    });
  }
  const videoBackdrop = document.getElementById("video-modal-backdrop");
  if (videoBackdrop) {
    videoBackdrop.addEventListener("click", (e) => {
      if (e.target === videoBackdrop) {
        const vid = document.getElementById("demo-video-player");
        if (vid) vid.pause();
        state.videoModalOpen = false;
        render();
      }
    });
  }

  // Navigation tabs
  document.querySelectorAll("[data-tab]").forEach((link) => {
    link.addEventListener("click", (e) => {
      const tab = link.getAttribute("data-tab");
      if (tab === "catalog") {
        e.preventDefault();
        loadCatalogTab();
      } else if (tab === "sources") {
        e.preventDefault();
        loadSourcesTab();
      } else {
        state.activeTab = "planner";
        render();
      }
    });
  });

  // Postal code form
  const pcForm = document.getElementById("postal-code-form");
  if (pcForm) {
    pcForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = document.getElementById("header-pc-input");
      if (input) updatePostalCode(input.value);
    });
  }

  // Profile selector
  const profileSelect = document.getElementById("profile-select");
  if (profileSelect) {
    profileSelect.addEventListener("change", (e) => {
      state.profileId = e.target.value;
      const activeList = getActiveCampaigns();
      const matchingCampaign = activeList.find((c) => c.profileId === state.profileId) || activeList[0];
      if (matchingCampaign) {
        state.selectedCampaignId = matchingCampaign.id;
        state.prompt = matchingCampaign.seedPrompt;
        state.detectedPills = detectPillsClientSide(state.prompt);
      }
      render();
    });
  }

  // Campaign selection
  document.querySelectorAll("[data-campaign-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cid = btn.getAttribute("data-campaign-id");
      const activeList = getActiveCampaigns();
      const camp = activeList.find((c) => c.id === cid) || state.campaigns.find((c) => c.id === cid);
      if (camp) {
        state.selectedCampaignId = camp.id;
        if (camp.profileId) {
          state.profileId = camp.profileId;
        }
        state.prompt = camp.seedPrompt;
        state.detectedPills = detectPillsClientSide(state.prompt);
        render();
        document.getElementById("planner")?.scrollIntoView({ behavior: "smooth" });
      }
    });
  });

  const heroBtn = document.getElementById("hero-personalise-btn");
  if (heroBtn) {
    heroBtn.addEventListener("click", () => {
      document.getElementById("planner")?.scrollIntoView({ behavior: "smooth" });
      document.getElementById("planner-request")?.focus();
    });
  }

  // Prompt textarea live pill detection & pre-Gemini domain guardrail
  const promptArea = document.getElementById("planner-request");
  if (promptArea) {
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
  }

  // Planner form submit
  const plannerForm = document.getElementById("planner-form");
  if (plannerForm) {
    plannerForm.addEventListener("submit", (e) => {
      e.preventDefault();
      generatePlan(state.prompt);
    });
  }

  const kidToggleBtn = document.getElementById("toggle-kid-friendly-prompt-btn");
  if (kidToggleBtn) {
    kidToggleBtn.addEventListener("click", () => {
      const rx = /\s*Prioriza recetas suaves aptas para niños pequeños\.?/i;
      if (rx.test(state.prompt)) {
        state.prompt = state.prompt.replace(rx, "").trim();
      } else {
        const base = (state.prompt || "").trim().replace(/\.*$/, "");
        state.prompt = `${base}. Prioriza recetas suaves aptas para niños pequeños.`;
      }
      state.detectedPills = detectPillsClientSide(state.prompt);
      render();
    });
  }

  const resetBtn = document.getElementById("reset-plan-btn");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      state.plan = null;
      state.error = null;
      state.cartAddedResult = null;
      saveLocalActivePlan();
      render();
    });
  }

  const retryBtn = document.getElementById("retry-plan-btn");
  if (retryBtn) {
    retryBtn.addEventListener("click", () => generatePlan(state.prompt));
  }

  // Swap recipe buttons
  document.querySelectorAll("[data-swap-recipe]").forEach((btn) => {
    btn.addEventListener("click", () => {
      swapRecipe(btn.getAttribute("data-swap-recipe"));
    });
  });

  // Vote recipe buttons (thumbs up / down overlay)
  document.querySelectorAll("[data-vote-recipe]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      voteRecipe(
        btn.getAttribute("data-vote-recipe"),
        btn.getAttribute("data-vote-type"),
        btn.getAttribute("data-vote-name")
      );
    });
  });

  // Clear recipe preferences button
  const clearPrefsBtn = document.getElementById("clear-recipe-prefs-btn");
  if (clearPrefsBtn) {
    clearPrefsBtn.addEventListener("click", clearRecipePreferences);
  }

  // Send to Thermomix buttons (per-day scheduling)
  document.querySelectorAll("[data-thermomix-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      sendToThermomix(
        btn.getAttribute("data-thermomix-id"),
        btn.getAttribute("data-thermomix-url"),
        btn.getAttribute("data-thermomix-name"),
        btn.getAttribute("data-thermomix-day") || "Lunes"
      );
    });
  });

  // Cookidoo week mode selector (current week vs next week)
  document.querySelectorAll("[data-cookidoo-week]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.getAttribute("data-cookidoo-week") || "current";
      if (state.cookidooWeekMode !== mode) {
        state.cookidooWeekMode = mode;
        render();
      }
    });
  });

  // Batch schedule entire 5-day menu into Cookidoo "Mi Semana"
  const scheduleCookidooWeekBtn = document.getElementById("schedule-cookidoo-week-btn");
  if (scheduleCookidooWeekBtn) {
    scheduleCookidooWeekBtn.addEventListener("click", () => {
      scheduleWeekInCookidoo();
    });
  }

  // Cookidoo credentials toggle & account linking buttons
  const toggleCookidooBtn = document.getElementById("toggle-cookidoo-creds-btn");
  if (toggleCookidooBtn) {
    toggleCookidooBtn.addEventListener("click", () => {
      state.cookidooModalOpen = !state.cookidooModalOpen;
      render();
    });
  }
  const connectCookidooBtn = document.getElementById("connect-cookidoo-btn");
  if (connectCookidooBtn) {
    connectCookidooBtn.addEventListener("click", () => {
      connectCookidooSession({ demoMode: false });
    });
  }
  const connectCookidooDemoBtn = document.getElementById("connect-cookidoo-demo-btn");
  if (connectCookidooDemoBtn) {
    connectCookidooDemoBtn.addEventListener("click", () => {
      connectCookidooSession({ demoMode: true });
    });
  }
  const disconnectCookidooBtn = document.getElementById("disconnect-cookidoo-btn");
  if (disconnectCookidooBtn) {
    disconnectCookidooBtn.addEventListener("click", () => {
      disconnectCookidooSession();
    });
  }
  const cEmail = document.getElementById("cookidoo-email-input");
  if (cEmail) {
    cEmail.addEventListener("input", (e) => {
      state.cookidooEmail = e.target.value;
    });
    cEmail.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        connectCookidooSession({ demoMode: false });
      }
    });
  }
  const cPass = document.getElementById("cookidoo-pass-input");
  if (cPass) {
    cPass.addEventListener("input", (e) => {
      state.cookidooPassword = e.target.value;
    });
    cPass.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        connectCookidooSession({ demoMode: false });
      }
    });
  }

  // Mercadona session toggle & inputs
  const headerDiaBtn = document.getElementById("header-dia-connect-btn");
  if (headerDiaBtn) {
    headerDiaBtn.addEventListener("click", () => {
      state.activeTab = "planner";
      state.diaModalOpen = !state.diaModalOpen;
      state.diaVerifyError = "";
      render();
      if (state.diaModalOpen) {
        setTimeout(() => {
          document.getElementById("dia-connect-box")?.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 80);
      }
    });
  }
  const toggleDíaBtn = document.getElementById("toggle-dia-session-btn");
  if (toggleDíaBtn) {
    toggleDíaBtn.addEventListener("click", () => {
      state.diaModalOpen = !state.diaModalOpen;
      state.diaVerifyError = "";
      render();
    });
  }
  const closeDiaModalBtn = document.getElementById("close-dia-modal-btn");
  if (closeDiaModalBtn) {
    closeDiaModalBtn.addEventListener("click", () => {
      state.diaModalOpen = false;
      state.diaVerifyError = "";
      render();
    });
  }
  const bookmarkletLink = document.getElementById("dia-bookmarklet-link");
  if (bookmarkletLink) {
    bookmarkletLink.addEventListener("click", (e) => {
      e.preventDefault();
      showToast(
        "Arrástralo a tu barra de marcadores",
        "Haz clic sin soltar sobre el botón '🔗 Vincular con Mercadona', arrástralo a tu barra de marcadores arriba y púlsalo cuando estés en tienda.mercadona.es."
      );
    });
  }
  const copyConnectorBtn = document.getElementById("copy-dia-connector-btn");
  if (copyConnectorBtn) {
    copyConnectorBtn.addEventListener("click", async () => {
      const snippet = buildDiaConsoleSnippet();
      try {
        await navigator.clipboard.writeText(snippet);
        showToast(
          "Conector 1-Click copiado al portapapeles",
          "Abre tienda.mercadona.es, pulsa F12 → pestaña Console, pega el comando (Ctrl+V) y pulsa Enter."
        );
      } catch (e) {
        showToast("No se pudo copiar automáticamente", "Arrastra el botón a tu barra de marcadores.");
      }
    });
  }
  const mAuthInput = document.getElementById("dia-auth-input");
  if (mAuthInput) {
    mAuthInput.addEventListener("input", (e) => {
      state.diaAuthInput = e.target.value;
    });
  }
  const verifyDíaBtn = document.getElementById("verify-dia-session-btn");
  if (verifyDíaBtn) {
    verifyDíaBtn.addEventListener("click", () => connectDiaSession());
  }
  const disconnectDíaBtn = document.getElementById("disconnect-dia-session-btn");
  if (disconnectDíaBtn) {
    disconnectDíaBtn.addEventListener("click", disconnectDiaSession);
  }
  const syncModeSelect = document.getElementById("dia-sync-mode-select");
  if (syncModeSelect) {
    syncModeSelect.addEventListener("change", (e) => {
      state.diaSyncMode = e.target.value;
    });
  }

  // Live stock verification button
  const verifyStockBtn = document.getElementById("verify-live-stock-btn");
  if (verifyStockBtn) {
    verifyStockBtn.addEventListener("click", verifyLiveBasketStock);
  }

  // 1-Click ECI cart button
  const oneClickBtn = document.getElementById("oneclick-dia-cart-btn");
  if (oneClickBtn) {
    oneClickBtn.addEventListener("click", addBasketToDiaOneClick);
  }
  const precreatedBm = document.getElementById("precreated-cart-bookmarklet");
  if (precreatedBm) {
    precreatedBm.addEventListener("click", (e) => {
      e.preventDefault();
      showToast(
        "Arrástralo a tu barra de marcadores",
        "Arrastra este botón verde a tu barra de marcadores, abre tienda.mercadona.es y púlsalo para cargar tu cesta al instante."
      );
    });
  }
  const copyDiaScriptBtn = document.getElementById("copy-dia-script-btn");
  if (copyDiaScriptBtn && state.cartAddedResult && (state.cartAddedResult.eci_browser_sync_script || state.cartAddedResult.dia_browser_sync_script)) {
    copyDiaScriptBtn.addEventListener("click", async () => {
      const scriptToCopy = state.cartAddedResult.eci_browser_sync_script || state.cartAddedResult.dia_browser_sync_script;
      try {
        await navigator.clipboard.writeText(scriptToCopy);
        window.open("https://tienda.mercadona.es/", "_blank", "noopener,noreferrer");
        showToast(
          "Comando 1-Click copiado · Abriendo Mercadona",
          "En la pestaña de Mercadona, pulsa F12 → Console, pega (Ctrl+V) y pulsa Enter para cargar tu cesta."
        );
      } catch (e) {
        window.open("https://tienda.mercadona.es/", "_blank", "noopener,noreferrer");
        showToast("Script 1-Click preparado", "Abre tienda.mercadona.es para completar tu compra.");
      }
    });
  }

  // Follow-up prompt buttons
  document.querySelectorAll("[data-followup]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const fp = btn.getAttribute("data-followup");
      state.prompt = `${state.prompt.replace(/\.\s*$/, "")}. ${fp}.`;
      state.detectedPills = detectPillsClientSide(state.prompt);
      generatePlan(state.prompt);
    });
  });

  // Catalog search input & pagination
  const catInput = document.getElementById("catalog-filter-input");
  if (catInput) {
    catInput.addEventListener("input", (e) => {
      state.catalogSearch = e.target.value;
      state.catalogPage = 1;
      render();
      const refocused = document.getElementById("catalog-filter-input");
      if (refocused) {
        refocused.focus();
        refocused.setSelectionRange(refocused.value.length, refocused.value.length);
      }
    });
  }

  const catPrev = document.getElementById("cat-prev-btn");
  if (catPrev) {
    catPrev.addEventListener("click", () => {
      state.catalogPage = Math.max(1, state.catalogPage - 1);
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }
  const catNext = document.getElementById("cat-next-btn");
  if (catNext) {
    catNext.addEventListener("click", () => {
      state.catalogPage += 1;
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  // Cookidoo recipes search input & pagination
  const recInput = document.getElementById("recipes-filter-input");
  if (recInput) {
    recInput.addEventListener("input", (e) => {
      state.recipesSearch = e.target.value;
      state.recipesPage = 1;
      render();
      const refocused = document.getElementById("recipes-filter-input");
      if (refocused) {
        refocused.focus();
        refocused.setSelectionRange(refocused.value.length, refocused.value.length);
      }
    });
  }

  const recPrev = document.getElementById("rec-prev-btn");
  if (recPrev) {
    recPrev.addEventListener("click", () => {
      state.recipesPage = Math.max(1, state.recipesPage - 1);
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }
  const recNext = document.getElementById("rec-next-btn");
  if (recNext) {
    recNext.addEventListener("click", () => {
      state.recipesPage += 1;
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  // --- NEW FEATURES EVENT BINDINGS ---

  // 1. WhatsApp Copilot Drawer & Webhook Controls
  const openWaDrawer = async () => {
    state.whatsappOpen = true;
    render();
    await fetchWhatsAppState({ silent: true });
    const chatBox = document.getElementById("wa-chat-messages");
    if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;
  };
  const headerWaBtn = document.getElementById("header-whatsapp-btn");
  if (headerWaBtn) {
    headerWaBtn.addEventListener("click", () => {
      if (state.whatsappOpen) {
        state.whatsappOpen = false;
        render();
      } else {
        openWaDrawer();
      }
    });
  }
  const floatingWaBtn = document.getElementById("floating-whatsapp-btn");
  if (floatingWaBtn) {
    floatingWaBtn.addEventListener("click", openWaDrawer);
  }
  const basketWaBtn = document.getElementById("open-whatsapp-from-basket-btn");
  if (basketWaBtn) {
    basketWaBtn.addEventListener("click", openWaDrawer);
  }
  const closeWaBtn = document.getElementById("wa-close-drawer-btn");
  if (closeWaBtn) {
    closeWaBtn.addEventListener("click", () => {
      state.whatsappOpen = false;
      render();
    });
  }
  const waBackdrop = document.getElementById("wa-drawer-backdrop");
  if (waBackdrop) {
    waBackdrop.addEventListener("click", (e) => {
      if (e.target === waBackdrop) {
        state.whatsappOpen = false;
        render();
      }
    });
  }
  const waToggleConfigBtn = document.getElementById("wa-toggle-config-btn");
  if (waToggleConfigBtn) {
    waToggleConfigBtn.addEventListener("click", () => {
      state.whatsappConfigOpen = !state.whatsappConfigOpen;
      render();
    });
  }
  const waClearChatBtn = document.getElementById("wa-clear-chat-btn");
  if (waClearChatBtn) {
    waClearChatBtn.addEventListener("click", () => {
      saveWhatsAppConfig({ reset_chat: true });
    });
  }
  const copyWebhookUrlBtn = document.getElementById("wa-copy-webhook-url-btn");
  if (copyWebhookUrlBtn) {
    copyWebhookUrlBtn.addEventListener("click", async () => {
      const val = document.getElementById("wa-webhook-url-input")?.value || "";
      try {
        await navigator.clipboard.writeText(val);
        showToast("URL de Webhook copiada", val);
      } catch (e) {}
    });
  }
  const copyVerifyTokenBtn = document.getElementById("wa-copy-verify-token-btn");
  if (copyVerifyTokenBtn) {
    copyVerifyTokenBtn.addEventListener("click", async () => {
      const val = document.getElementById("wa-verify-token-input")?.value || "";
      try {
        await navigator.clipboard.writeText(val);
        showToast("Verify Token copiado", val);
      } catch (e) {}
    });
  }
  const simTwilioBtn = document.getElementById("wa-sim-twilio-btn");
  if (simTwilioBtn) {
    simTwilioBtn.addEventListener("click", () => simulateExternalWebhookPost("twilio"));
  }
  const simMetaBtn = document.getElementById("wa-sim-meta-btn");
  if (simMetaBtn) {
    simMetaBtn.addEventListener("click", () => simulateExternalWebhookPost("meta"));
  }
  document.querySelectorAll("[data-wa-quick]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const q = btn.getAttribute("data-wa-quick");
      if (q) sendWhatsAppMessage(q);
    });
  });
  const waChatInput = document.getElementById("wa-chat-input");
  if (waChatInput) {
    waChatInput.addEventListener("input", (e) => {
      state.whatsappInput = e.target.value;
    });
  }
  const waChatForm = document.getElementById("wa-chat-form");
  if (waChatForm) {
    waChatForm.addEventListener("submit", (e) => {
      e.preventDefault();
      sendWhatsAppMessage(state.whatsappInput);
    });
  }
  const waVoiceBtn = document.getElementById("wa-voice-note-btn");
  if (waVoiceBtn) {
    waVoiceBtn.addEventListener("click", startWhatsAppVoiceNote);
  }

  // 2. Fridge Vision (Multimodal Photo Upload & 1-Click Presets)
  const uploadFridgeBtn = document.getElementById("upload-fridge-photo-btn");
  const fridgeFileInput = document.getElementById("fridge-photo-input");
  if (uploadFridgeBtn && fridgeFileInput) {
    uploadFridgeBtn.addEventListener("click", () => fridgeFileInput.click());
    fridgeFileInput.addEventListener("change", (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const b64 = String(reader.result || "");
        runFridgeVision({ imageBase64: b64, mimeType: file.type || "image/jpeg" });
      };
      reader.readAsDataURL(file);
    });
  }
  document.querySelectorAll("[data-fridge-preset]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = btn.getAttribute("data-fridge-preset");
      if (pid) runFridgeVision({ presetId: pid });
    });
  });

  // 3. Per-Day Diners Scaling ("Hoy vienen invitados")
  document.querySelectorAll("[data-scale-day]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const dayName = btn.getAttribute("data-scale-day");
      const diners = Number(btn.getAttribute("data-scale-diners") || 3);
      if (!dayName || !state.plan) return;
      const nextServings = { ...(state.plan.day_servings || {}), [dayName]: diners };
      recalculateBasket({
        dayServings: nextServings,
        toastTitle: `👥 Comensales del ${dayName}: ${diners} personas`,
        toastBody: `Se han escalado las cantidades de tu cesta en Mercadona y las notas de mostrador para ${diners} comensales el ${dayName}.`,
      });
    });
  });

  // 4. 3-Way Basket Tier Switcher (Ahorro / Bio / Club del Gourmet)
  document.querySelectorAll("[data-basket-tier]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tier = btn.getAttribute("data-basket-tier");
      if (!tier || !state.plan) return;
      const labels = {
        ahorro: "🏷️ Nivel Ahorro Marca Mercadona activado",
        bio: "🌱 Gama Bio & Ecológicos Mercadona activada",
        gourmet: "🥂 Selección & Bodega & Mercadona Selection activado",
      };
      recalculateBasket({
        basketTier: tier,
        includeSommelierItem: tier === "gourmet" ? true : Boolean(state.plan.sommelier_pairing?.included),
        toastTitle: labels[tier] || "Nivel de cesta actualizado",
        toastBody:
          tier === "bio"
            ? "Se han sustituido los ingredientes compatibles por productos reales de Mercadona Bio y Huerta Mercadona."
            : tier === "gourmet"
            ? "Se han seleccionado referencias de Club del Gourmet, Mercadona Selection y el maridaje del Sumiller IA."
            : "Se han priorizado las referencias de mejor precio de Hacendado y Proveedores Totaler.",
      });
    });
  });

  // 5. Sommelier IA Pairing Toggle
  const toggleSommelierBtn = document.getElementById("toggle-sommelier-btn");
  if (toggleSommelierBtn && state.plan) {
    toggleSommelierBtn.addEventListener("click", () => {
      const nextVal = !Boolean(state.plan.sommelier_pairing?.included);
      recalculateBasket({
        includeSommelierItem: nextVal,
        toastTitle: nextVal ? "🍷 Maridaje Sumiller IA añadido" : "Maridaje retirado de la cesta",
        toastBody: nextVal
          ? `Se ha añadido '${state.plan.sommelier_pairing?.product_name || "Selección Club del Gourmet"}' a tu cesta.`
          : "Se ha retirado la recomendación de Bodega / Club del Gourmet de tu cesta.",
      });
    });
  }

  // 6. Custom Traditional Counter Preparation Cut Selector
  document.querySelectorAll("[data-counter-pid]").forEach((sel) => {
    sel.addEventListener("change", (e) => {
      const pid = sel.getAttribute("data-counter-pid");
      const chosenCut = e.target.value;
      if (!pid || !chosenCut || !state.plan) return;
      const nextCuts = { ...(state.plan.custom_counter_cuts || {}), [pid]: chosenCut };
      recalculateBasket({
        customCounterCuts: nextCuts,
        toastTitle: "🔪 Nota de mostrador actualizada",
        toastBody: `El maestro de mostrador recibirá la instrucción: «${chosenCut}».`,
      });
    });
  });

  // 7. Mercadona Delivery vs. Click & Car Selector
  document.querySelectorAll("[data-delivery-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.getAttribute("data-delivery-mode");
      if (mode) {
        state.deliveryMode = mode;
        showToast(
          mode === "click_and_car"
            ? `🚗 Recogida Click & Car seleccionada (${state.centerName || state.warehouse})`
            : `🏠 Envío a Domicilio seleccionado (CP ${state.postalCode})`,
          mode === "click_and_car"
            ? `Recoge tu pedido sin bajar del coche en el parking de ${state.centerName || state.warehouse}.`
            : "Entrega refrigerada en franja de 2 horas desde tu centro Mercadona."
        );
        render();
      }
    });
  });
  document.querySelectorAll("[data-clickcar-slot]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const slot = btn.getAttribute("data-clickcar-slot");
      if (slot) {
        state.selectedClickCarSlot = slot;
        showToast("🚗 Franja Click & Car reservada", slot);
        render();
      }
    });
  });
}

function ensureDiaFavicon() {
  document.querySelectorAll('link[rel*="icon"]').forEach((el) => el.remove());
  const pngLink = document.createElement("link");
  pngLink.rel = "icon";
  pngLink.type = "image/png";
  pngLink.sizes = "48x48";
  pngLink.href = "/favicon.png?v=mercadona-basket-2026";
  document.head.appendChild(pngLink);

  const icoLink = document.createElement("link");
  icoLink.rel = "shortcut icon";
  icoLink.type = "image/x-icon";
  icoLink.href = "/favicon.ico?v=mercadona-basket-2026";
  document.head.appendChild(icoLink);
}

// Initialize app and auto-refresh campaigns/session when returning to the tab
ensureDiaFavicon();
checkSession();
window.addEventListener("hashchange", () => {
  consumeDiaConnectHash();
});
window.addEventListener("storage", (e) => {
  if (e.key === "dia_session_sync_v1") {
    checkSession();
  }
});
window.addEventListener("focus", () => {
  fetchCampaignsFromLibrary();
  fetchWhatsAppState({ silent: true });
});
setInterval(() => {
  if (state.whatsappOpen && !state.whatsappSending) {
    fetchWhatsAppState({ silent: false });
  }
}, 5000);
