/**
 * Mercadona AI Shopping Companion — Frontend Application
 * Powered by Gemini 3.8 Flash · Cookidoo API (Thermomix) · Mercadona Tienda API
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
    allowedUsers: ["matgand@gmail.com", "mgandolfi@google.com", "andrea.anaut@gmail.com"],
    googleClientId: "",
    error: "",
  },
  campaignLibraryUrl: "https://campaign-library-905208270932.europe-west1.run.app",
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
  postalCode: "28016",
  warehouse: "mad3",
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
  cartAddedResult: null,
  addingToCart: false,
  catalogData: null,
  catalogSearch: "",
  catalogPage: 1,
  recipesSearch: "",
  recipesPage: 1,
  toast: null,
};

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
    .replace(/"/g, "&quot;");
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

function detectPillsClientSide(text) {
  const pills = [];
  const mMeals = text.match(
    /\b(one|two|three|four|five|six|seven|un|una|uno|dos|tres|cuatro|cinco|seis|siete|[1-7])\s+(?:(?:weekday|weeknight|vegetarian|quick|healthy|family|rápidas|rapidas|saludables|familiares|entre\s+semana)\s+){0,3}(?:dinners?|meals?|cenas?|comidas?|días?|dias?)\b/i
  );
  const wordMap = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, un: 1, una: 1, uno: 1, dos: 2, tres: 3, cuatro: 4, cinco: 5, seis: 6, siete: 7 };
  const mealCount = mMeals ? wordMap[mMeals[1].toLowerCase()] || Number(mMeals[1]) || 5 : 5;
  pills.push(`${mealCount} ${mealCount === 1 ? "cena" : "cenas"}`);

  const mMin = text.match(/\b(\d{1,3})\s*(?:minutes?|mins?|minutos?|min)\b/i);
  pills.push(`≤ ${mMin ? mMin[1] : 25} min`);

  const mCal = text.match(/\b(\d{2,4})\s*(?:kcal|calorías|calorias|calories|cal)\b/i);
  if (mCal) pills.push(`≤ ${mCal[1]} kcal/ración`);

  const mBud = text.match(/(?:€\s*(\d+(?:[.,]\d{1,2})?)|(\d+(?:[.,]\d{1,2})?)\s*(?:€|euros?|eur))/i);
  pills.push(`≤ €${mBud ? mBud[1] || mBud[2] : 65}`);

  const mAdults = text.match(/\b(one|two|three|four|five|six|un|una|uno|dos|tres|cuatro|cinco|seis|[1-6])\s+(?:adults?|adultos?)\b/i);
  const mKids = text.match(/\b(one|two|three|four|five|six|un|una|uno|dos|tres|cuatro|cinco|seis|[1-6])\s+(?:children|child|kids?|niños?|ninos?|hijos?)\b/i);
  const adults = mAdults ? wordMap[mAdults[1].toLowerCase()] || Number(mAdults[1]) || 2 : 2;
  const kids = mKids ? wordMap[mKids[1].toLowerCase()] || Number(mKids[1]) || 0 : mAdults ? 0 : 1;
  pills.push(`${adults} ${adults === 1 ? "adulto" : "adultos"}${kids > 0 ? ` + ${kids} ${kids === 1 ? "niño" : "niños"}` : ""}`);

  if (/\b(?:pescado|merluza|salmón|salmon|fish)\b/i.test(text) && !/\bsin\s+pescado\b/i.test(text)) {
    pills.push("Incluye pescado");
  }
  if (/\b(?:vegetariano|vegetariana|vegetarian|sin\s+carne)\b/i.test(text)) {
    pills.push("Vegetariano");
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
  // 1. Try querying the campaign-library microservice directly via CORS if configured
  if (state.campaignLibraryUrl) {
    try {
      const remoteRes = await fetch(`${state.campaignLibraryUrl}/api/campaigns`);
      if (remoteRes.ok) {
        const remoteData = await remoteRes.json();
        if (Array.isArray(remoteData.campaigns) && remoteData.campaigns.length > 0) {
          loaded = remoteData.campaigns;
        }
      }
    } catch (e) {
      // Fallback to local /api/campaigns
    }
  }
  // 2. Fallback or sync via local /api/campaigns
  if (!loaded) {
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

async function checkSession() {
  try {
    const res = await fetch("/api/auth/session");
    const data = await res.json();
    state.auth.checked = true;
    state.auth.authenticated = Boolean(data.authenticated);
    state.auth.user = data.user || null;
    state.auth.allowedUsers = data.allowed_users || state.auth.allowedUsers;
    state.auth.googleClientId = data.google_client_id || "";
    if (data.campaign_library_url) {
      state.campaignLibraryUrl = data.campaign_library_url;
    }
    render();
  } catch (err) {
    state.auth.checked = true;
    render();
  }
  await fetchCampaignsFromLibrary();
}

async function loginWithEmail(email) {
  state.auth.error = "";
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const data = await res.json();
    if (!res.ok) {
      state.auth.error = data.error || "Acceso denegado.";
      render();
      return;
    }
    state.auth.authenticated = true;
    state.auth.user = data.user;
    state.auth.error = "";
    showToast("Sesión iniciada con Google Identity", `Bienvenido/a, ${data.user}`);
    render();
  } catch (err) {
    state.auth.error = "Error de red al verificar la identidad.";
    render();
  }
}

async function logoutUser() {
  await fetch("/api/auth/logout", { method: "POST" });
  state.auth.authenticated = false;
  state.auth.user = null;
  render();
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
      showToast(
        `Código Postal ${data.postal_code} activo`,
        `Conectado en tiempo real al almacén '${data.warehouse}' de Mercadona Tienda.`
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

  state.loading = true;
  state.error = null;
  state.cartAddedResult = null;
  state.lastSwapChange = null;
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
        varietySeed: `${state.profileId}:${state.selectedCampaignId}:${state.varietyCounter}`,
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
  } catch (err) {
    state.error = err.message || "Error al conectar con el planificador Gemini 3.8 Flash.";
  } finally {
    state.loading = false;
    render();
  }
}

async function swapRecipe(recipeId) {
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
      }),
    });
    const data = await res.json();
    if (res.ok && data.replacement) {
      state.previousPlan = state.plan;
      state.lastSwapChange = data.change;
      state.plan = {
        ...state.plan,
        meals: state.plan.meals.map((m) => (m.recipe_id === recipeId ? data.replacement : m)),
        basket: data.basket,
        total: data.total,
        budget_remaining: data.budget_remaining,
      };
      showToast(
        `Cambio rápido (${data.change.day})`,
        `Se sustituyó solo esta receta por '${data.change.to_recipe_name}' y se actualizó la cesta (${formatEUR(data.total)}).`
      );
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

async function sendToThermomix(recipeId, cookidooUrl, recipeName) {
  // Open the official Cookidoo recipe page in a new tab immediately on user click
  window.open(cookidooUrl, "_blank", "noopener,noreferrer");
  try {
    const res = await fetch("/api/cookidoo/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recipe_id: recipeId,
        cookidoo_email: state.cookidooEmail,
        cookidoo_password: state.cookidooPassword,
      }),
    });
    const data = await res.json();
    state.sentThermomixIds[recipeId] = true;
    showToast(`Enviado a tu Thermomix (${recipeId})`, data.message || `Receta '${recipeName}' abierta en Cookidoo.`);
    render();
  } catch (err) {
    state.sentThermomixIds[recipeId] = true;
    render();
  }
}

async function addBasketToMercadonaOneClick() {
  if (!state.plan || state.addingToCart) return;
  state.addingToCart = true;
  render();
  try {
    const res = await fetch("/api/mercadona/cart", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        basket: state.plan.basket,
        postal_code: state.postalCode,
      }),
    });
    const data = await res.json();
    if (res.ok) {
      state.cartAddedResult = data;
      showToast("¡Cesta añadida a Mercadona!", data.message);
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

function renderGoogleCloudLockup() {
  return `
    <span class="gcloud-lockup-badge" aria-label="Google Cloud">
      <svg class="gcloud-logo-icon" viewBox="0 0 64 52" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <path d="M40.6 14.2L47.8 7C43.5 3.1 37.9 0.8 31.8 0.8C20.5 0.8 10.9 7.8 7.3 17.8L16.8 25.1C18.7 18.8 24.7 14.2 31.8 14.2C35.1 14.2 38.2 15.2 40.6 14.2Z" fill="#EA4335"/>
        <path d="M55.7 17.8C53.6 12.1 49.7 7.2 44.6 4.1L36.8 11.9C40.6 14.1 43.4 17.9 44.2 22.4V23.8C49.2 23.8 53.2 27.8 53.2 32.8C53.2 37.8 49.2 41.8 44.2 41.8H31.8L29.1 47.2L31.8 51.8H44.2C54.7 51.8 63.2 43.3 63.2 32.8C63.2 26.3 59.9 20.6 55.7 17.8Z" fill="#4285F4"/>
        <path d="M19.4 51.8H44.2V41.8H19.4C17.8 41.8 16.3 41.4 15 40.6L7.8 47.8C11.1 50.3 15.1 51.8 19.4 51.8Z" fill="#34A853"/>
        <path d="M19.4 13.8C8.9 13.8 0.4 22.3 0.4 32.8C0.4 38.9 3.3 44.3 7.8 47.8L15 40.6C12.2 38.8 10.4 36 10.4 32.8C10.4 27.8 14.4 23.8 19.4 23.8C22.6 23.8 25.4 25.6 27.2 28.4L34.4 21.2C30.9 16.7 25.5 13.8 19.4 13.8Z" fill="#FBBC05"/>
      </svg>
      <span class="gcloud-wordmark">
        <span class="gc-g1">G</span><span class="gc-o1">o</span><span class="gc-o2">o</span><span class="gc-g2">g</span><span class="gc-l">l</span><span class="gc-e">e</span>
        <span class="gc-cloud">Cloud</span>
      </span>
    </span>
  `;
}

function renderAuthModal() {
  if (!state.auth.checked || state.auth.authenticated) return "";
  return `
    <div class="auth-gate-overlay" role="dialog" aria-modal="true" aria-labelledby="auth-gate-title">
      <div class="auth-gate-card">
        <div class="brand-lockup" style="margin-bottom: 18px;">
          ${renderGoogleCloudLockup()}
          <span class="brand-divider"></span>
          <img class="mercadona-logo" src="/brand/mercadona.svg" alt="Mercadona" style="width: 125px;" />
        </div>
        <p class="eyebrow" style="margin-bottom: 6px;">Acceso Restringido · Google Identity</p>
        <h2 id="auth-gate-title">Inicia sesión con tu cuenta de Google</h2>
        <p>
          El acceso a este planificador está restringido exclusivamente a las cuentas de Google autorizadas en la lista blanca del proyecto.
        </p>
        <div class="allowed-users-box">
          <span>Usuarios Google autorizados (Click para entrar)</span>
          ${state.auth.allowedUsers
            .map(
              (email) => `
            <button type="button" class="allowed-user-btn" data-login-email="${escapeHtml(email)}">
              <strong>${escapeHtml(email)}</strong>
              <small>Entrar con Google →</small>
            </button>
          `
            )
            .join("")}
        </div>
        <form id="custom-login-form" class="custom-email-form">
          <input type="email" id="custom-login-email" placeholder="Probar otro email de Google..." required />
          <button type="submit">Verificar acceso</button>
        </form>
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
        ${renderGoogleCloudLockup()}
        <span class="brand-divider" aria-hidden="true"></span>
        <img class="mercadona-logo" src="/brand/mercadona.svg" alt="Mercadona" />
      </a>
      <nav class="top-navigation" aria-label="Navegación principal">
        <a href="#for-you" data-tab="planner" ${state.activeTab === "planner" ? 'aria-current="page"' : ""}>Para ti</a>
        <a href="#planner" data-tab="planner">Mi semana</a>
        <a href="#catalog" data-tab="catalog" ${state.activeTab === "catalog" ? 'aria-current="page"' : ""}>Catálogo Mercadona</a>
        <a href="#sources" data-tab="sources" ${state.activeTab === "sources" ? 'aria-current="page"' : ""}>Cookidoo &amp; APIs</a>
        <a href="${escapeHtml(state.campaignLibraryUrl || "/marketing")}" target="_blank" rel="noopener">Campaign Library ↗</a>
      </nav>
      <div class="header-controls">
        <form id="postal-code-form" class="postal-selector" title="Configura tu código postal para consultar disponibilidad en tiempo real en Mercadona">
          <label for="header-pc-input">CP</label>
          <input id="header-pc-input" type="text" maxlength="5" value="${escapeHtml(state.postalCode)}" aria-label="Código postal" />
          <span class="wh-pill">(${escapeHtml(state.warehouse)})</span>
          <button type="submit">Actualizar</button>
        </form>
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

function renderExperiencePanel() {
  if (state.loading) {
    return `
      <div class="loading-state" aria-live="polite">
        <div class="loading-orbit"><span></span></div>
        <p class="empty-kicker">Gemini 3.8 Flash trabajando</p>
        <h2>Elaborando tu menú semanal en Cookidoo y Mercadona</h2>
        <p>Verificando restricciones nutricionales, alérgenos, recetas de Thermomix y stock real en Mercadona para el CP ${escapeHtml(state.postalCode)} (${escapeHtml(state.warehouse)}).</p>
        <div class="loading-steps">
          <span>Analizando condiciones del prompt con Gemini 3.8 Flash</span>
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
          El asistente interpreta tus condiciones con <strong>Gemini 3.8 Flash</strong>, selecciona recetas reales de <strong>Cookidoo</strong> con su foto de portada, descuenta lo que ya tienes en casa y mapea todos los ingredientes al catálogo de <strong>Mercadona</strong> para el CP <strong>${escapeHtml(state.postalCode)}</strong>.
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
  return `
    <div class="plan-state">
      <div class="plan-heading">
        <div>
          <p class="empty-kicker">Tu menú semanal de ${p.meals.length} cenas</p>
          <h2>${escapeHtml(p.headline)}</h2>
          <p>${escapeHtml(p.summary)}</p>
        </div>
        <div class="live-badge">
          <span></span>
          ${escapeHtml(p.model || "Gemini 3.8 Flash")}
        </div>
      </div>

      <div class="validation-ribbon" aria-label="Validaciones deterministas completadas">
        <span>✓ Recetas Cookidoo verificadas</span>
        <span>✓ Stock Mercadona CP ${escapeHtml(p.postal_code)} (${escapeHtml(p.warehouse)})</span>
        <span>✓ Alérgenos declarados comprobados</span>
        <span>✓ Presupuesto recalculado (${formatEUR(p.total)})</span>
        ${p.constraints.maxCaloriesPerServing ? `<span>✓ ≤ ${p.constraints.maxCaloriesPerServing} kcal / ración</span>` : ""}
      </div>

      <div style="display:flex; justify-content:space-between; align-items:center; padding: 14px 0; border-bottom: 1px solid var(--line); flex-wrap: wrap; gap: 10px;">
        <span style="font-size:12px; color:var(--muted);">
          ¿Quieres sincronizar directamente con tu cuenta de Cookidoo mediante <code>cookidoo-api</code>?
        </span>
        <button type="button" class="text-button" id="toggle-cookidoo-creds-btn">
          ${state.cookidooModalOpen ? "Ocultar credenciales Cookidoo" : "Configurar cuenta Cookidoo (Opcional)"}
        </button>
      </div>

      ${
        state.cookidooModalOpen
          ? `
        <div style="background:#f4faf7; border:1px solid #cfded6; padding:16px; margin-bottom:16px; border-radius:3px;">
          <strong style="display:block; font-size:13px; margin-bottom:6px;">Conexión directa con <code>miaucl/cookidoo-api</code></strong>
          <p style="font-size:12px; color:var(--muted); margin-bottom:12px;">
            Introduce tus credenciales de Cookidoo si deseas que el botón "Envía a tu Thermomix" añada además la receta automáticamente a tu calendario "Mi Semana" y lista de la compra mediante la API de Cookidoo.
          </p>
          <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <input type="email" id="cookidoo-email-input" placeholder="Email de Cookidoo" value="${escapeHtml(state.cookidooEmail)}" style="border:1px solid var(--line); background:#fff; padding:8px 10px; font-size:12px; border-radius:2px; flex:1;" />
            <input type="password" id="cookidoo-pass-input" placeholder="Contraseña de Cookidoo" value="${escapeHtml(state.cookidooPassword)}" style="border:1px solid var(--line); background:#fff; padding:8px 10px; font-size:12px; border-radius:2px; flex:1;" />
          </div>
        </div>
      `
          : ""
      }

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
            const isSent = Boolean(state.sentThermomixIds[meal.recipe_id]);
            return `
            <article class="meal-card" aria-busy="${isSwapping}">
              <figure class="meal-image">
                <img src="${escapeHtml(meal.image_url)}" alt="${escapeHtml(meal.image_alt)}" loading="lazy" />
              </figure>
              <div class="meal-card-body">
                <div class="meal-card-topline">
                  <div class="meal-number">0${idx + 1}</div>
                  <div class="meal-day">${escapeHtml(meal.day)}</div>
                </div>
                <h3>${escapeHtml(meal.name)}</h3>
                <p>${escapeHtml(meal.description)}</p>
                <div class="meal-meta">
                  <span>${meal.minutes} min</span>
                  <span>${formatEUR(meal.estimated_cost)}</span>
                  <span class="meal-calories">${Math.round(meal.calories_per_serving)} kcal/ración</span>
                </div>
                <div class="cookidoo-meta">
                  <span>Cookidoo ${escapeHtml(meal.cookidoo_id)}</span>
                  <span>${meal.cookidoo_servings} ${meal.cookidoo_servings === 1 ? "ración" : "raciones"}</span>
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
                    data-thermomix-url="${escapeHtml(meal.cookidoo_url)}"
                    data-thermomix-name="${escapeHtml(meal.name)}"
                  >
                    ${isSent ? "Enviada a Thermomix" : "Envía a tu Thermomix"}
                    <span aria-hidden="true">${isSent ? "✓" : "↗"}</span>
                  </button>
                </div>
                <p class="quick-swap-helper">
                  <strong>Cambio rápido</strong> sustituye solo esta cena manteniendo el resto del menú. <strong>Envía a tu Thermomix</strong> abre la receta (${escapeHtml(meal.cookidoo_id)}) en Cookidoo.
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

      <div class="basket-section">
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
            .map(
              (item) => `
            <div class="basket-row">
              <div class="basket-product-mark" aria-hidden="true">
                ${
                  item.thumbnail
                    ? `<img src="${escapeHtml(item.thumbnail)}" alt="" loading="lazy" />`
                    : escapeHtml(item.name.charAt(0))
                }
              </div>
              <div class="basket-product-copy">
                <a href="${escapeHtml(item.share_url)}" target="_blank" rel="noreferrer">
                  ${escapeHtml(item.name)} <span aria-hidden="true">↗</span>
                </a>
                <span>
                  ${item.quantity} × ${escapeHtml(item.unit)} (${formatEUR(item.unit_price)}/ud)
                  ${
                    item.used_in_days && item.used_in_days.length
                      ? ` · Para: ${escapeHtml(item.used_in_days.join(", "))}`
                      : ""
                  }
                </span>
              </div>
              <strong>${formatEUR(item.line_total)}</strong>
            </div>
          `
            )
            .join("")}
        </div>

        <div class="allergen-note">
          <span>i</span>
          <p>${escapeHtml(p.allergen_notice)}</p>
        </div>

        <div class="mercadona-oneclick-bar">
          <div>
            <strong style="display:block; font-size:15px; margin-bottom:4px;">
              Añadir todos los productos al carrito de Mercadona
            </strong>
            <span style="font-size:12px; color:var(--muted);">
              Sincroniza los ${p.basket.length} productos disponibles en el CP ${escapeHtml(p.postal_code)} (${escapeHtml(p.warehouse)}) por ${formatEUR(p.total)}.
            </span>
          </div>
          <button
            type="button"
            class="mercadona-oneclick-btn"
            id="oneclick-mercadona-cart-btn"
            ${state.addingToCart ? "disabled" : ""}
          >
            ${
              state.addingToCart
                ? "Sincronizando con Mercadona..."
                : state.cartAddedResult
                ? "✓ Productos añadidos al carrito de Mercadona"
                : "Añadir al carrito de Mercadona (1-Click)"
            }
            <span aria-hidden="true">→</span>
          </button>
        </div>

        ${
          state.cartAddedResult
            ? `
          <div class="confirmation-state" role="status" style="margin-top:14px;">
            <span>✓</span>
            <div>
              <strong>${escapeHtml(state.cartAddedResult.message)}</strong>
              <p>
                Puedes revisar cada producto directamente en
                <a href="https://tienda.mercadona.es/" target="_blank" rel="noreferrer" style="text-decoration:underline; font-weight:700;">
                  tienda.mercadona.es (CP ${escapeHtml(state.cartAddedResult.postal_code)}) ↗
                </a>
              </p>
            </div>
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
          <img src="${escapeHtml(featuredCampaign.imageUrl)}" alt="${escapeHtml(featuredCampaign.title)}" />
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
          <h2 id="campaign-discovery-title">Olvida el buscador. Compra según tu estilo de vida.</h2>
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
            <img src="${escapeHtml(c.imageUrl)}" alt="" />
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

          <div class="constraint-row" id="constraint-pills-row" aria-label="Condiciones detectadas">
            ${state.detectedPills.map((pill) => `<span>${escapeHtml(pill)}</span>`).join("")}
          </div>

          <div class="form-actions">
            <button class="primary-button" type="submit" ${state.loading ? "disabled" : ""}>
              ${state.loading ? "Elaborando menú con Gemini 3.8 Flash..." : "Generar mi menú semanal"}
              <span aria-hidden="true">↗</span>
            </button>
            ${
              state.plan
                ? `<button class="text-button" type="button" id="reset-plan-btn">Reiniciar</button>`
                : ""
            }
          </div>
        </form>

        <div class="trust-note">
          <span class="trust-icon">✓</span>
          <p>
            Las recetas, fotos de portada y valores nutricionales provienen de <strong>Cookidoo</strong>. Los nombres de producto, formatos, precios y disponibilidad en tiempo real provienen de la API de <strong>Mercadona Tienda</strong> para el código postal <strong>${escapeHtml(state.postalCode)}</strong>.
          </p>
        </div>
      </div>

      <div class="experience-panel ${state.plan ? "has-plan" : ""}">
        ${renderExperiencePanel()}
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
      <p class="eyebrow">API de Mercadona Tienda · CP ${escapeHtml(state.postalCode)} (${escapeHtml(state.warehouse)})</p>
      <h1 style="font-size: clamp(42px, 5vw, 72px); margin-bottom: 18px;">Catálogo de Productos de Mercadona (${allProducts.length})</h1>
      <p class="hero-subtitle">
        Productos verificados en la API de Mercadona (<code>tienda.mercadona.es/api/categories/</code> y <code>/api/products/&lt;id&gt;/?lang=es&amp;wh=${escapeHtml(state.warehouse)}</code>) utilizados para el mapping de las 5.000 recetas.
      </p>
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px; margin-bottom: 24px;">
        <div style="flex:1; min-width: 280px; max-width: 480px;">
          <input
            type="search"
            id="catalog-filter-input"
            placeholder="Buscar entre ${allProducts.length} productos de Mercadona (ej. Hacendado, salmón, 3400)..."
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
                  ${p.thumbnail ? `<img src="${escapeHtml(p.thumbnail)}" alt="" loading="lazy" />` : escapeHtml(p.name.charAt(0))}
                </div>
                <div class="basket-product-copy">
                  <a href="${escapeHtml(p.share_url)}" target="_blank" rel="noreferrer">
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
              <img src="${escapeHtml(r.image_url)}" alt="${escapeHtml(r.name)}" loading="lazy" />
            </figure>
            <div class="meal-card-body">
              <div class="meal-card-topline">
                <div class="meal-number">#${String(startIdx + idx + 1).padStart(2, "0")}</div>
                <div class="meal-day">${escapeHtml(r.cookidoo_id)}</div>
              </div>
              <h3>${escapeHtml(r.name)}</h3>
              <p>${escapeHtml(r.description)}</p>
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
                  data-thermomix-url="${escapeHtml(r.cookidoo_url)}"
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

function render() {
  const root = document.getElementById("app-root");
  if (!root) return;

  root.innerHTML = `
    ${renderAuthModal()}
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
  // Auth buttons
  document.querySelectorAll("[data-login-email]").forEach((btn) => {
    btn.addEventListener("click", () => {
      loginWithEmail(btn.getAttribute("data-login-email"));
    });
  });

  const customLoginForm = document.getElementById("custom-login-form");
  if (customLoginForm) {
    customLoginForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = document.getElementById("custom-login-email");
      if (input) loginWithEmail(input.value);
    });
  }

  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", logoutUser);
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

  // Prompt textarea live pill detection
  const promptArea = document.getElementById("planner-request");
  if (promptArea) {
    promptArea.addEventListener("input", (e) => {
      state.prompt = e.target.value;
      state.detectedPills = detectPillsClientSide(state.prompt);
      const pillRow = document.getElementById("constraint-pills-row");
      if (pillRow) {
        pillRow.innerHTML = state.detectedPills.map((p) => `<span>${escapeHtml(p)}</span>`).join("");
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

  const resetBtn = document.getElementById("reset-plan-btn");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      state.plan = null;
      state.error = null;
      state.cartAddedResult = null;
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

  // Send to Thermomix buttons
  document.querySelectorAll("[data-thermomix-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      sendToThermomix(
        btn.getAttribute("data-thermomix-id"),
        btn.getAttribute("data-thermomix-url"),
        btn.getAttribute("data-thermomix-name")
      );
    });
  });

  // Cookidoo credentials toggle & inputs
  const toggleCookidooBtn = document.getElementById("toggle-cookidoo-creds-btn");
  if (toggleCookidooBtn) {
    toggleCookidooBtn.addEventListener("click", () => {
      state.cookidooModalOpen = !state.cookidooModalOpen;
      render();
    });
  }
  const cEmail = document.getElementById("cookidoo-email-input");
  if (cEmail) {
    cEmail.addEventListener("input", (e) => {
      state.cookidooEmail = e.target.value;
    });
  }
  const cPass = document.getElementById("cookidoo-pass-input");
  if (cPass) {
    cPass.addEventListener("input", (e) => {
      state.cookidooPassword = e.target.value;
    });
  }

  // 1-Click Mercadona cart button
  const oneClickBtn = document.getElementById("oneclick-mercadona-cart-btn");
  if (oneClickBtn) {
    oneClickBtn.addEventListener("click", addBasketToMercadonaOneClick);
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
}

// Initialize app and auto-refresh campaigns when returning to the tab
checkSession();
window.addEventListener("focus", () => {
  fetchCampaignsFromLibrary();
});
