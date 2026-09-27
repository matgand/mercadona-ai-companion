/**
 * Mercadona Campaign Library — Microservicio para el equipo de Marketing
 * Conectado en tiempo real con Mercadona AI Shopping Companion
 */

const CATEGORIES = ["Familias", "Saludables", "Rutina rápida", "Ahorro"];
const STATUSES = ["Activa", "Planificada", "Borrador", "Terminada"];

const STATUS_CLASS_MAP = {
  Activa: "live",
  Planificada: "scheduled",
  Borrador: "draft",
  Terminada: "archived",
};

const EXAMPLE_BRIEFS = [
  {
    label: "Familias · Pescado y verduras ocultas",
    category: "Familias",
    text: "Crea una campaña para Familias (2 adultos y 2 niños) con 5 cenas variadas en menos de 25 minutos, presupuesto máximo de 60€, incluyendo dos cenas de pescado suave y usando las patatas que ya tengo en casa.",
  },
  {
    label: "Saludables · Cena mediterránea < 420 kcal",
    category: "Saludables",
    text: "Lanza una campaña Saludables para 2 adultos con 5 cenas mediterráneas bajas en calorías (máximo 420 kcal por ración), en 25 minutos o menos y bajo 58€.",
  },
  {
    label: "Rutina rápida · Cenas en 20 min",
    category: "Rutina rápida",
    text: "Diseña una campaña de Rutina rápida para días de teletrabajo con 5 cenas exprés en 20 minutos o menos, presupuesto bajo 50€ y usando el arroz que ya tengo en casa.",
  },
  {
    label: "Ahorro · Cesta inteligente < 45€",
    category: "Ahorro",
    text: "Crea una campaña de Ahorro máximo para 2 adultos y 1 niño con 5 cenas económicas por debajo de 45€ en total, en 30 minutos o menos, aprovechando huevos y pasta de la despensa.",
  },
];

const mState = {
  auth: {
    checked: false,
    authenticated: false,
    user: null,
    allowedUsers: ["matgand@gmail.com", "mgandolfi@google.com", "andrea.anaut@gmail.com"],
    error: "",
  },
  companionAppUrl: "https://mercadona-ai-companion-905208270932.europe-west1.run.app",
  campaigns: [],
  selectedId: null,
  filterCategory: "Todas",
  filterStatus: "Todos",
  briefText: "",
  briefCategory: "Auto",
  briefInitialStatus: "Activa",
  generating: false,
  saving: false,
  notice: null,
  isErrorNotice: false,
};

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatEUR(val) {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(Number(val || 0));
}

function showNotice(msg, isError = false) {
  mState.notice = msg;
  mState.isErrorNotice = isError;
  render();
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
  if (!mState.auth.checked || mState.auth.authenticated) return "";
  return `
    <div class="auth-gate-overlay" role="dialog" aria-modal="true" aria-labelledby="auth-gate-title">
      <div class="auth-gate-card">
        <div class="brand-lockup" style="margin-bottom: 18px;">
          ${renderGoogleCloudLockup()}
          <span class="brand-divider"></span>
          <img class="mercadona-logo" src="/brand/mercadona.svg" alt="Mercadona" style="width: 125px;" />
        </div>
        <p class="eyebrow" style="margin-bottom: 6px;">Campaign Library · Google Identity</p>
        <h2 id="auth-gate-title">Acceso Marketing Mercadona</h2>
        <p>
          Inicia sesión con tu cuenta de Google autorizada para gestionar las campañas semanales conectadas con Mercadona AI Companion.
        </p>
        <div class="allowed-users-box">
          <span>Usuarios Google autorizados (Click para entrar)</span>
          ${mState.auth.allowedUsers
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
          mState.auth.error
            ? `<div class="auth-error-msg" role="alert">${escapeHtml(mState.auth.error)}</div>`
            : ""
        }
      </div>
    </div>
  `;
}

async function initMarketingApp() {
  try {
    const authRes = await fetch("/api/auth/session");
    if (authRes.ok) {
      const authData = await authRes.json();
      mState.auth.checked = true;
      mState.auth.authenticated = Boolean(authData.authenticated);
      mState.auth.user = authData.user || null;
      mState.auth.allowedUsers = authData.allowed_users || mState.auth.allowedUsers;
    } else {
      mState.auth.checked = true;
    }
  } catch (e) {
    mState.auth.checked = true;
  }

  await loadCampaigns();
}

async function loadCampaigns() {
  try {
    const res = await fetch("/api/campaigns");
    if (res.ok) {
      const data = await res.json();
      mState.campaigns = data.campaigns || [];
      if (data.companion_app_url) {
        mState.companionAppUrl = data.companion_app_url;
      }
      if (!mState.selectedId && mState.campaigns.length > 0) {
        mState.selectedId = mState.campaigns[0].id;
      }
    }
  } catch (e) {
    console.error("Error loading campaigns:", e);
  }
  render();
}

async function loginWithEmail(email) {
  mState.auth.error = "";
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const data = await res.json();
    if (!res.ok) {
      mState.auth.error = data.error || "Acceso denegado.";
      render();
      return;
    }
    mState.auth.authenticated = true;
    mState.auth.user = data.user;
    render();
  } catch (e) {
    mState.auth.error = "Error de red al verificar identidad.";
    render();
  }
}

async function logoutUser() {
  await fetch("/api/auth/logout", { method: "POST" });
  mState.auth.authenticated = false;
  mState.auth.user = null;
  render();
}

async function handleGenerateCampaign(e) {
  e.preventDefault();
  const brief = (mState.briefText || "").trim();
  if (!brief || mState.generating) return;

  mState.generating = true;
  mState.notice = null;
  render();

  try {
    const res = await fetch("/api/campaigns/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        brief,
        category: mState.briefCategory === "Auto" ? null : mState.briefCategory,
        status: mState.briefInitialStatus,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      showNotice(data.error || "No se pudo generar la campaña.", true);
      mState.generating = false;
      render();
      return;
    }
    const created = data.campaign;
    mState.campaigns = data.campaigns || [created, ...mState.campaigns];
    mState.selectedId = created.id;
    mState.filterCategory = "Todas";
    mState.filterStatus = "Todos";
    mState.briefText = "";
    showNotice(
      `✓ Campaña «${created.title}» (${created.category}) creada con estado '${created.status}' y sincronizada con la aplicación principal.`
    );
  } catch (err) {
    showNotice("Error al conectar con el generador de campañas IA.", true);
  } finally {
    mState.generating = false;
    render();
  }
}

async function handleChangeStatus(campaignId, newStatus) {
  if (mState.saving) return;
  mState.saving = true;
  render();

  try {
    const res = await fetch("/api/campaigns/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: campaignId,
        status: newStatus,
      }),
    });
    const data = await res.json();
    if (res.ok && data.campaign) {
      mState.campaigns = data.campaigns || mState.campaigns.map((c) => (c.id === campaignId ? data.campaign : c));
      const syncText =
        newStatus === "Activa"
          ? "Ya está visible en «Más ideas para tu semana» de la aplicación principal."
          : "Se ha actualizado su visibilidad en la aplicación principal.";
      showNotice(`✓ Estado de «${data.campaign.title}» cambiado a '${newStatus}'. ${syncText}`);
    } else {
      showNotice(data.error || "Error al cambiar el estado.", true);
    }
  } catch (e) {
    showNotice("Error de red al cambiar el estado de la campaña.", true);
  } finally {
    mState.saving = false;
    render();
  }
}

async function handleSaveSelectedEdits(e) {
  e.preventDefault();
  const selected = getSelectedCampaign();
  if (!selected || mState.saving) return;

  const title = document.getElementById("edit-title")?.value.trim() || selected.title;
  const tagline = document.getElementById("edit-tagline")?.value.trim() || selected.tagline;
  const category = document.getElementById("edit-category")?.value || selected.category;
  const status = document.getElementById("edit-status")?.value || selected.status;
  const badge = document.getElementById("edit-badge")?.value.trim() || selected.badge;
  const seedPrompt = document.getElementById("edit-seed-prompt")?.value.trim() || selected.seedPrompt;
  const maxBudget = Number(document.getElementById("edit-budget")?.value || selected.maxBudget);
  const maxMinutes = Number(document.getElementById("edit-minutes")?.value || selected.maxMinutes);

  mState.saving = true;
  render();

  try {
    const res = await fetch("/api/campaigns/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: selected.id,
        updates: {
          title,
          tagline,
          category,
          status,
          badge,
          seedPrompt,
          maxBudget,
          maxMinutes,
        },
      }),
    });
    const data = await res.json();
    if (res.ok && data.campaign) {
      mState.campaigns = data.campaigns || mState.campaigns.map((c) => (c.id === selected.id ? data.campaign : c));
      showNotice(`✓ Campaña «${data.campaign.title}» actualizada y sincronizada con la aplicación principal.`);
    } else {
      showNotice(data.error || "No se pudieron guardar los cambios.", true);
    }
  } catch (err) {
    showNotice("Error al guardar la campaña.", true);
  } finally {
    mState.saving = false;
    render();
  }
}

function getFilteredCampaigns() {
  return mState.campaigns.filter((c) => {
    const matchCat = mState.filterCategory === "Todas" || c.category === mState.filterCategory;
    const matchStatus = mState.filterStatus === "Todos" || c.status === mState.filterStatus;
    return matchCat && matchStatus;
  });
}

function getSelectedCampaign() {
  const filtered = getFilteredCampaigns();
  const exact = mState.campaigns.find((c) => c.id === mState.selectedId);
  if (exact) return exact;
  if (filtered.length > 0) return filtered[0];
  return mState.campaigns[0] || null;
}

function render() {
  const root = document.getElementById("marketing-root");
  if (!root) return;

  const filtered = getFilteredCampaigns();
  const selected = getSelectedCampaign();

  const activeCount = mState.campaigns.filter((c) => c.status === "Activa").length;
  const plannedOrDraftCount = mState.campaigns.filter((c) => c.status === "Planificada" || c.status === "Borrador").length;
  const userInitial = mState.auth.user ? mState.auth.user.charAt(0).toUpperCase() : "M";

  root.innerHTML = `
    ${renderAuthModal()}
    <main class="marketing-shell">
      <header class="brand-bar marketing-brand-bar">
        <a class="brand-lockup" href="${escapeHtml(mState.companionAppUrl)}" aria-label="Google Cloud y Mercadona">
          ${renderGoogleCloudLockup()}
          <span class="brand-divider" aria-hidden="true"></span>
          <img class="mercadona-logo" src="/brand/mercadona.svg" alt="Mercadona" />
        </a>
        <nav class="top-navigation" aria-label="Navegación entre microservicios">
          <a href="${escapeHtml(mState.companionAppUrl)}">Experiencia Cliente (Planificador)</a>
          <a href="/marketing" aria-current="page">Campaign Library</a>
          <a href="${escapeHtml(mState.companionAppUrl)}/#for-you">Ver «Más ideas para tu semana» ↗</a>
        </nav>
        <div class="header-controls">
          <span class="internal-pill">Microservicio · Campaign Library</span>
          ${
            mState.auth.authenticated
              ? `
            <div class="user-auth-pill">
              <span class="user-avatar">${escapeHtml(userInitial)}</span>
              <span>${escapeHtml(mState.auth.user)}</span>
              <button type="button" id="logout-btn">Salir</button>
            </div>
          `
              : ""
          }
        </div>
      </header>

      <section class="marketing-hero">
        <div>
          <p class="eyebrow">Mercadona Marketing · Campaign Library</p>
          <h1>De campañas estáticas a menús semanales vivos.</h1>
          <p>
            Define en lenguaje natural propuestas semanales adaptadas a cada perfil de usuario
            (<strong>Familias</strong>, <strong>Saludables</strong>, <strong>Rutina rápida</strong>, <strong>Ahorro</strong>).
            Las campañas en estado <strong>Activa</strong> se publican automáticamente en la sección
            <em>«Más ideas para tu semana. Olvida el buscador. Compra según tu estilo de vida.»</em> de la aplicación principal.
          </p>
        </div>
        <div class="marketing-kpis" aria-label="Resumen del portfolio de campañas">
          <div>
            <strong>${activeCount}</strong>
            <span>Campañas Activas</span>
          </div>
          <div>
            <strong>${plannedOrDraftCount}</strong>
            <span>Planificadas / Borrador</span>
          </div>
          <div>
            <strong>1.28M</strong>
            <span>Hogares elegibles</span>
          </div>
          <small>Conectado en tiempo real con Mercadona AI Companion · 5.000 recetas Cookidoo · 1.595 productos Mercadona</small>
        </div>
      </section>

      ${
        mState.notice
          ? `<div class="library-notice ${mState.isErrorNotice ? "error" : ""}" role="status">${escapeHtml(mState.notice)}</div>`
          : ""
      }

      <section class="marketing-workspace" aria-label="Espacio de trabajo de campañas de marketing">
        <!-- COLUMNA 1: Portfolio y Control de Estados -->
        <aside class="campaign-library-panel">
          <div class="panel-title-row">
            <div>
              <p class="eyebrow">Portfolio</p>
              <h2>Campaign Library</h2>
            </div>
            <span class="prototype-label">${filtered.length} de ${mState.campaigns.length} campañas</span>
          </div>

          <div class="library-filters">
            <label>
              Categoría / Perfil
              <select id="filter-category-select">
                <option value="Todas" ${mState.filterCategory === "Todas" ? "selected" : ""}>Todas las categorías</option>
                ${CATEGORIES.map(
                  (cat) => `<option value="${escapeHtml(cat)}" ${mState.filterCategory === cat ? "selected" : ""}>${escapeHtml(cat)}</option>`
                ).join("")}
              </select>
            </label>
            <label>
              Estado
              <select id="filter-status-select">
                <option value="Todos" ${mState.filterStatus === "Todos" ? "selected" : ""}>Todos los estados</option>
                ${STATUSES.map(
                  (st) => `<option value="${escapeHtml(st)}" ${mState.filterStatus === st ? "selected" : ""}>${escapeHtml(st)}</option>`
                ).join("")}
              </select>
            </label>
          </div>

          <div class="campaign-admin-list" role="list">
            ${
              filtered.length === 0
                ? `<p style="font-size:12px; color:var(--muted); padding: 14px 0;">No hay campañas con esos filtros.</p>`
                : filtered
                    .map((c) => {
                      const isSel = selected && c.id === selected.id;
                      const stClass = STATUS_CLASS_MAP[c.status] || "live";
                      return `
                  <button
                    type="button"
                    class="campaign-admin-card ${isSel ? "selected" : ""}"
                    data-select-campaign="${escapeHtml(c.id)}"
                  >
                    <span class="status-dot ${stClass}" aria-hidden="true"></span>
                    <span class="campaign-admin-copy">
                      <strong>${escapeHtml(c.title)}</strong>
                      <small>${escapeHtml(c.category)} · ${c.mealCount} cenas · ≤ €${Number(c.maxBudget).toFixed(0)}</small>
                    </span>
                    <span class="status-label ${stClass}">${escapeHtml(c.status)}</span>
                  </button>
                `;
                    })
                    .join("")
            }
          </div>

          ${
            selected
              ? `
            <div class="campaign-actions-card">
              <div>
                <strong>Cambiar estado · «${escapeHtml(selected.title)}»</strong>
                <p>
                  Selecciona el estado de la campaña. Al marcarla como <strong>Activa</strong>, aparece al instante en
                  <em>«Más ideas para tu semana»</em> de la aplicación principal.
                </p>
              </div>
              <div class="status-switcher-grid" role="group" aria-label="Cambiar estado de la campaña">
                ${STATUSES.map((st) => {
                  const stClass = STATUS_CLASS_MAP[st] || "live";
                  const isCurrent = selected.status === st;
                  return `
                    <button
                      type="button"
                      class="status-switch-btn ${isCurrent ? "active-state" : ""}"
                      data-set-status="${escapeHtml(st)}"
                      data-target-id="${escapeHtml(selected.id)}"
                      ${mState.saving ? "disabled" : ""}
                    >
                      <span class="status-dot ${stClass}" aria-hidden="true"></span>
                      <span>${escapeHtml(st)}</span>
                    </button>
                  `;
                }).join("")}
              </div>
            </div>
          `
              : ""
          }
        </aside>

        <!-- COLUMNA 2: Generador en lenguaje natural + Editor de campaña -->
        <section class="campaign-builder-panel">
          <div class="panel-title-row">
            <div>
              <p class="eyebrow">Copiloto de Campañas IA</p>
              <h2>Definir nueva campaña</h2>
            </div>
            <span class="prototype-label">Gemini 3.8 Flash</span>
          </div>

          <form class="campaign-brief-form" id="create-campaign-form">
            <label for="campaign-brief-textarea">
              Brief de campaña en lenguaje natural
              <textarea
                id="campaign-brief-textarea"
                rows="4"
                placeholder="Describe en lenguaje natural la campaña que quieres lanzar (ej.: 'Crea una campaña para Familias con 5 cenas de pescado y legumbres en menos de 25 minutos y presupuesto bajo 60€' o 'Campaña de Ahorro por menos de 45€ aprovechando huevos y arroz')..."
              >${escapeHtml(mState.briefText)}</textarea>
            </label>

            <div class="brief-chips-row" aria-label="Ejemplos rápidos de briefs">
              ${EXAMPLE_BRIEFS.map(
                (b, idx) => `
                <button type="button" class="brief-chip-btn" data-brief-idx="${idx}">
                  + ${escapeHtml(b.label)}
                </button>
              `
              ).join("")}
            </div>

            <div class="library-filters" style="margin-bottom: 4px; margin-top: 4px;">
              <label>
                Categoría de Perfil
                <select id="brief-category-select">
                  <option value="Auto" ${mState.briefCategory === "Auto" ? "selected" : ""}>Auto-detectar según el prompt</option>
                  ${CATEGORIES.map(
                    (cat) => `<option value="${escapeHtml(cat)}" ${mState.briefCategory === cat ? "selected" : ""}>${escapeHtml(cat)}</option>`
                  ).join("")}
                </select>
              </label>
              <label>
                Estado inicial
                <select id="brief-status-select">
                  <option value="Activa" ${mState.briefInitialStatus === "Activa" ? "selected" : ""}>Activa (Publicar en la App)</option>
                  <option value="Planificada" ${mState.briefInitialStatus === "Planificada" ? "selected" : ""}>Planificada</option>
                  <option value="Borrador" ${mState.briefInitialStatus === "Borrador" ? "selected" : ""}>Borrador</option>
                  <option value="Terminada" ${mState.briefInitialStatus === "Terminada" ? "selected" : ""}>Terminada</option>
                </select>
              </label>
            </div>

            <button class="primary-button compact" type="submit" ${mState.generating ? "disabled" : ""}>
              ${mState.generating ? "Generando campaña con Gemini 3.8 Flash..." : "Crear campaña desde lenguaje natural"}
              <span aria-hidden="true">↗</span>
            </button>
          </form>

          ${
            selected
              ? `
            <form class="campaign-draft-editor" id="edit-campaign-form">
              <div class="draft-heading">
                <div>
                  <span class="status-dot ${STATUS_CLASS_MAP[selected.status] || "live"}"></span>
                  <strong>CAMPAÑA SELECCIONADA: ${escapeHtml(selected.status.toUpperCase())}</strong>
                </div>
                <small>ID: ${escapeHtml(selected.id)} · ${escapeHtml(selected.eligibleHouseholds)}</small>
              </div>

              <div class="draft-fields">
                <label>
                  Título de la campaña
                  <input type="text" id="edit-title" value="${escapeHtml(selected.title)}" />
                </label>
                <label>
                  Subtítulo / Propuesta de valor
                  <input type="text" id="edit-tagline" value="${escapeHtml(selected.tagline)}" />
                </label>
                <label>
                  Categoría / Perfil de usuario
                  <select id="edit-category">
                    ${CATEGORIES.map(
                      (cat) => `<option value="${escapeHtml(cat)}" ${selected.category === cat ? "selected" : ""}>${escapeHtml(cat)}</option>`
                    ).join("")}
                  </select>
                </label>
                <label style="grid-column: auto;">
                  Estado de la campaña
                  <select id="edit-status">
                    ${STATUSES.map(
                      (st) => `<option value="${escapeHtml(st)}" ${selected.status === st ? "selected" : ""}>${escapeHtml(st)}</option>`
                    ).join("")}
                  </select>
                </label>
                <label style="grid-column: 1 / -1;">
                  Prompt de menú inicial (conectado al Planificador de la App Principal)
                  <input type="text" id="edit-seed-prompt" value="${escapeHtml(selected.seedPrompt)}" />
                </label>
                <label>
                  Etiqueta destacada (Badge)
                  <input type="text" id="edit-badge" value="${escapeHtml(selected.badge)}" />
                </label>
                <label>
                  Presupuesto máx (€) / Tiempo máx (min)
                  <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                    <input type="number" id="edit-budget" min="20" max="200" step="1" value="${Number(selected.maxBudget)}" title="Presupuesto máximo (€)" />
                    <input type="number" id="edit-minutes" min="10" max="90" step="5" value="${Number(selected.maxMinutes)}" title="Tiempo máximo (min)" />
                  </div>
                </label>
              </div>

              <div class="validation-ribbon guardrail-grid">
                <span>✓ Perfil: ${escapeHtml(selected.category)}</span>
                <span>✓ ${selected.mealCount} cenas Cookidoo</span>
                <span>✓ ≤ ${selected.maxMinutes} min</span>
                <span>✓ ≤ €${Number(selected.maxBudget).toFixed(2)} Mercadona</span>
              </div>

              <button type="submit" class="secondary-button compact" style="width:100%;" ${mState.saving ? "disabled" : ""}>
                ${mState.saving ? "Sincronizando..." : "Guardar cambios y sincronizar con la App Principal"}
                <span aria-hidden="true">✓</span>
              </button>
            </form>
          `
              : ""
          }
        </section>

        <!-- COLUMNA 3: Anteprima en vivo de la campaña seleccionada -->
        <aside class="customer-preview-panel" aria-label="Anteprima de la campaña seleccionada">
          <p class="eyebrow">Anteprima de la campaña seleccionada</p>
          ${
            selected
              ? `
            <article class="campaign-preview-card">
              <figure>
                <img src="${escapeHtml(selected.imageUrl)}" alt="${escapeHtml(selected.title)}" />
              </figure>
              <div class="campaign-preview-body">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:14px; flex-wrap:wrap;">
                  <span class="campaign-badge" style="margin-bottom:0;">${escapeHtml(selected.badge)}</span>
                  <span class="status-label ${STATUS_CLASS_MAP[selected.status] || "live"}">${escapeHtml(selected.status)} · ${escapeHtml(selected.category)}</span>
                </div>
                <h2>${escapeHtml(selected.title)}</h2>
                <p>${escapeHtml(selected.tagline)}</p>
                <div class="campaign-facts">
                  <span>${selected.mealCount} cenas</span>
                  <span>≤ ${selected.maxMinutes} min</span>
                  <span>≤ ${formatEUR(selected.maxBudget)}</span>
                  ${selected.maxCaloriesPerServing ? `<span>≤ ${selected.maxCaloriesPerServing} kcal</span>` : ""}
                </div>
                <div class="why-profile">
                  <strong>Por qué encaja con el perfil «${escapeHtml(selected.category)}»</strong>
                  <p>${escapeHtml(selected.whyProfile)}</p>
                </div>
                <div class="why-profile">
                  <strong>Menú inicial que cargará en el Planificador</strong>
                  <p style="font-family:var(--font-geist-mono),monospace; font-size:10px; background:#f6f6f2; padding:8px 10px; border-radius:2px; margin-top:6px; color:var(--ink);">
                    “${escapeHtml(selected.seedPrompt)}”
                  </p>
                </div>
                <a
                  class="campaign-hero-button preview-cta"
                  href="${escapeHtml(mState.companionAppUrl)}/?campaign=${encodeURIComponent(selected.id)}#for-you"
                >
                  Probar esta campaña en la App Principal <span aria-hidden="true">→</span>
                </a>
              </div>
            </article>
            <p class="preview-disclaimer">
              ${
                selected.status === "Activa"
                  ? `✓ Esta campaña está <strong>Activa</strong> y aparece ahora mismo en la sección <em>«Más ideas para tu semana. Olvida el buscador. Compra según tu estilo de vida.»</em> de la aplicación principal.`
                  : `ℹ️ Esta campaña está en estado <strong>${escapeHtml(selected.status)}</strong>. Cámbiala a <strong>Activa</strong> para publicarla en <em>«Más ideas para tu semana»</em>.`
              }
            </p>
          `
              : `<p style="font-size:13px; color:var(--muted);">Selecciona una campaña para visualizar su anteprima.</p>`
          }
        </aside>
      </section>
    </main>
  `;

  bindMarketingEvents();
}

function bindMarketingEvents() {
  // Auth
  document.querySelectorAll("[data-login-email]").forEach((btn) => {
    btn.addEventListener("click", () => loginWithEmail(btn.getAttribute("data-login-email")));
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

  // Filters
  const catFilter = document.getElementById("filter-category-select");
  if (catFilter) {
    catFilter.addEventListener("change", (e) => {
      mState.filterCategory = e.target.value;
      const f = getFilteredCampaigns();
      if (f.length > 0 && !f.some((c) => c.id === mState.selectedId)) {
        mState.selectedId = f[0].id;
      }
      render();
    });
  }

  const stFilter = document.getElementById("filter-status-select");
  if (stFilter) {
    stFilter.addEventListener("change", (e) => {
      mState.filterStatus = e.target.value;
      const f = getFilteredCampaigns();
      if (f.length > 0 && !f.some((c) => c.id === mState.selectedId)) {
        mState.selectedId = f[0].id;
      }
      render();
    });
  }

  // Select campaign from list
  document.querySelectorAll("[data-select-campaign]").forEach((btn) => {
    btn.addEventListener("click", () => {
      mState.selectedId = btn.getAttribute("data-select-campaign");
      render();
    });
  });

  // Status quick-switch buttons
  document.querySelectorAll("[data-set-status]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const newSt = btn.getAttribute("data-set-status");
      const targetId = btn.getAttribute("data-target-id");
      if (targetId && newSt) {
        handleChangeStatus(targetId, newSt);
      }
    });
  });

  // Brief textarea & example chips
  const briefArea = document.getElementById("campaign-brief-textarea");
  if (briefArea) {
    briefArea.addEventListener("input", (e) => {
      mState.briefText = e.target.value;
    });
  }

  document.querySelectorAll("[data-brief-idx]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.getAttribute("data-brief-idx"));
      const item = EXAMPLE_BRIEFS[idx];
      if (item) {
        mState.briefText = item.text;
        mState.briefCategory = item.category;
        render();
      }
    });
  });

  const briefCatSelect = document.getElementById("brief-category-select");
  if (briefCatSelect) {
    briefCatSelect.addEventListener("change", (e) => {
      mState.briefCategory = e.target.value;
    });
  }

  const briefStSelect = document.getElementById("brief-status-select");
  if (briefStSelect) {
    briefStSelect.addEventListener("change", (e) => {
      mState.briefInitialStatus = e.target.value;
    });
  }

  // Create campaign form
  const createForm = document.getElementById("create-campaign-form");
  if (createForm) {
    createForm.addEventListener("submit", handleGenerateCampaign);
  }

  // Edit campaign form
  const editForm = document.getElementById("edit-campaign-form");
  if (editForm) {
    editForm.addEventListener("submit", handleSaveSelectedEdits);
  }
}

function ensureMercadonaFavicon() {
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

ensureMercadonaFavicon();
initMarketingApp();
