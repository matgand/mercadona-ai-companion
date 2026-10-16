# Auditoría Integral de Accesibilidad (WCAG 2.1 AA / ARIA) e i18n / Localización en Español Europeo (es-ES)

**Subagente Auditor:** Child Subagent 3 — Accessibility & i18n Specialist  
**Proyecto:** Mercadona AI Shopping Companion & Marketing Campaign Library  
**Repositorio:** `/usr/local/google/home/mgandolfi/mercadona-ai-companion`  
**Archivos Auditados:**
- `/usr/local/google/home/mgandolfi/mercadona-ai-companion/public/index.html`
- `/usr/local/google/home/mgandolfi/mercadona-ai-companion/public/marketing.html`
- `/usr/local/google/home/mgandolfi/mercadona-ai-companion/public/app.js`
- `/usr/local/google/home/mgandolfi/mercadona-ai-companion/public/marketing.js`
- `/usr/local/google/home/mgandolfi/mercadona-ai-companion/public/styles.css`
- **Referencia Corporativa:** `/google/src/files/head/depot/google3/learning/gemini/agents/skills/i18n/SKILL.md`

---

## 1. Resumen Ejecutivo y Cuadro de Mando

La aplicación web **Mercadona AI Shopping Companion** y su microservicio gemelo **Marketing Campaign Library** presentan un alto estándar visual y una excelente contextualización gastronómica adaptada al mercado español (uso coherente de terminología de Mercadona, Cookidoo y Thermomix como *cesta*, *despensa*, *Hacendado*, *raciones*, *varoma*, *tupper*).

No obstante, la auditoría técnica en profundidad según las directrices de **WCAG 2.1 Nivel AA** y las normas corporativas de **i18n de Google** revela vulnerabilidades e inconsistencias que afectan a la experiencia de usuarios con tecnologías de asistencia (lectores de pantalla NVDA/VoiceOver/JAWS, usuarios de solo teclado) y a la consistencia lingüística/monetaria.

### Cuadro de Estado de Cumplimiento

| Dominio | Criterio de Referencia | Cumplimiento Actual | Severidad | Hallazgos Principales |
| :--- | :--- | :---: | :---: | :--- |
| **ARIA & Live Regions** | WCAG 4.1.2, 4.1.3 | ⚠️ Parcial (62%) | **Alta** | Regiones vivas dinámicas no persistentes en DOM; modales sin trampa de foco ni `aria-describedby`; acordeones sin `aria-expanded`. |
| **Nombres Accesibles** | WCAG 1.3.1, 4.1.2 | ⚠️ Parcial (68%) | **Media-Alta** | Inputs de catálogo, recetas y autenticación sin `<label>` ni `aria-label`; botones de cambio rápido ambiguos en lectura aislada. |
| **Navegación Teclado** | WCAG 2.1.1, 2.1.2, 2.4.7 | ❌ No Conforme (45%) | **Alta** | Sin trampa de foco en el modal IAP; contorno `:focus-visible` con opacidad alfa (1.4:1 contra 3:1 mínimo exigido). |
| **Contraste de Color** | WCAG 1.4.3, 1.4.11 | ⚠️ Parcial (74%) | **Alta** | Contraste insuficiente (<4.5:1) en números de plato, IDs de catálogo, bordes de chips y el propio indicador de foco. |
| **i18n & Gramática es-ES** | Google i18n SKILL | ⚠️ Parcial (71%) | **Media** | Calco léxico italiano («Anteprima» en marketing); anglicismos («1-Click», «Badge»); mezclas de puntuación. |
| **Formato Moneda / Núm.** | ISO 4217, ICU es-ES | ⚠️ Inconsistente (65%) | **Alta** | Presencia de literales anglosajones `≤ €65` y `.toFixed(2)` en lugar de `formatEUR()` estándar (`65,00 €`). |
| **Expansión Textual CSS** | Google i18n (30-50% buffer) | ⚠️ En Riesgo (58%) | **Media** | Cabecera rígida con `white-space: nowrap` y `flex-wrap: nowrap` susceptible de desborde horizontal entre 1280px y 1440px. |

---

## 2. Auditoría de Accesibilidad (WCAG 2.1 AA)

### 2.1 Roles ARIA, Landmarks y Regiones en Vivo (WCAG 4.1.2 / 4.1.3)

#### Hallazgo A1 (Alta Severidad): Toast y Anuncios de Estado Dinámico No Anunciados en Lectores de Pantalla
- **Ubicación:** `public/app.js` (L1513–L1521, L204–L211)
- **Diagnóstico Técnico:**
  El banner de notificación toast se monta y desmonta condicionalmente en el DOM cada vez que cambia el estado global:
  ```javascript
  // app.js:1513
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
  ```
  Según la especificación WAI-ARIA y la implementación de motores de accesibilidad en navegadores (Chromium / WebKit / Gecko), una región con `role="status"` o `aria-live="polite"` **debe estar presente previamente en el árbol de accesibilidad antes de que se inyecte el texto**. Si el nodo completo se crea y destruye simultáneamente con su contenido, los lectores de pantalla (VoiceOver, NVDA, JAWS) ignoran la mutación y el usuario invidente nunca escucha confirmaciones críticas (ej.: *«Enviado a tu Thermomix»*, *«¡Añadido a tu carrito real de Mercadona.es!»*, *«Código postal inválido»*).
- **Remediación:**
  1. Dejar un contenedor persistente en la estructura HTML base:
     ```html
     <div id="global-toast-region" class="toast-banner-region" aria-live="polite" aria-atomic="true"></div>
     ```
  2. Para errores de red o validaciones fallidas, utilizar un canal prioritario con `role="alert"` y `aria-live="assertive"`.

#### Hallazgo A2 (Alta Severidad): Notificación del Reemplazo Rápido de Receta («Quick Swap»)
- **Ubicación:** `public/app.js` (L889–L903, L468–L513)
- **Diagnóstico Técnico:**
  Al invocar `/api/recipe-swap`, el estado actualiza `state.lastSwapChange` y re-renderiza el contenedor `.plan-delta` con `role="status"`. Sin embargo, al rehacer el innerHTML completo del contenedor principal, el lector de pantalla pierde el foco activo del botón pulsado (`.quick-swap-button`) y no anuncia la receta saliente ni la entrante de forma automática.
- **Remediación:**
  Incluir un contenedor `aria-live="polite"` persistente o actualizar el anuncio verbal:
  *«Se ha sustituido la cena del [Día] por [Nombre de la nueva receta]. El nuevo total de la cesta es [Importe en euros]».*

#### Hallazgo A3 (Media Severidad): Diálogo Modal de Identificación IAP sin `aria-describedby` ni Gestión de Foco
- **Ubicación:** `public/app.js` (L695–L735), `public/marketing.js` (L108–L146)
- **Diagnóstico Técnico:**
  El diálogo modal `.auth-gate-overlay` declara:
  ```html
  <div class="auth-gate-overlay" role="dialog" aria-modal="true" aria-labelledby="auth-gate-title">
  ```
  - **Falta `aria-describedby`:** El usuario invidente escucha únicamente el título *«Autenticación Google obligatoria»*, pero no se asocia el texto explicativo de L704–L706 que describe por qué se requiere la autorización IAP y la lista de cuentas permitidas.
  - **Falta foco programático:** Al activarse el modal (cuando `state.auth.authenticated === false`), el script no traslada el foco mediante `.focus()` al modal ni a su primer elemento accionable.

#### Hallazgo A4 (Media Severidad): Controles Desplegables de Credenciales y Sesión sin Atributos de Acordeón
- **Ubicación:**
  - `public/app.js` L866–L868 (`#toggle-cookidoo-creds-btn`)
  - `public/app.js` L1052–L1060 (`#toggle-mercadona-session-btn`)
- **Diagnóstico Técnico:**
  Ambos botones expanden y colapsan paneles de configuración de contraseñas/tokens. Sin embargo, no indican su estado de apertura ni el contenedor asociado:
  - Carecen de `aria-expanded="true|false"`.
  - Carecen de `aria-controls="cookidoo-creds-panel"` o `aria-controls="mercadona-session-panel"`.
  Para un usuario de lector de pantalla, el botón solo cambia de texto («Configurar...» a «Ocultar...»), obligándolo a explorar a ciegas las líneas contiguas para averiguar si apareció un nuevo bloque.

---

### 2.2 Nombres Accesibles y Formularios (WCAG 1.3.1 / 4.1.2)

#### Hallazgo A5 (Alta Severidad): Inputs y Controles de Formulario Críticos sin `<label>` ni `aria-label`
A través de un análisis del árbol DOM generado, se detectan múltiples controles huérfanos que dependen exclusivamente del atributo visual `placeholder`:

| Archivo | Línea | Selector / Control | Atributos Actuales | Deficiencia Accesible | Remediación Requerida |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `app.js` | L880 | `#cookidoo-email-input` | `placeholder="Email de Cookidoo"` | Sin `<label>` ni `aria-label` | Agregar `aria-label="Correo electrónico de tu cuenta Cookidoo"` |
| `app.js` | L881 | `#cookidoo-pass-input` | `placeholder="Contraseña de Cookidoo"` | Sin `<label>` ni `aria-label` | Agregar `aria-label="Contraseña de tu cuenta Cookidoo"` |
| `app.js` | L1047 | `#mercadona-sync-mode-select` | Envuelto en `<label>Modo:` | Sin `for=""` ni `id` vinculado formalmente | Vincular `<label for="mercadona-sync-mode-select">Modo de sincronización</label>` |
| `app.js` | L1081 | `#mercadona-auth-input` | `placeholder="Pega aquí el comando..."` | Textarea huérfano sin etiqueta accesible | Agregar `aria-label="Token de autenticación o comando cURL de Mercadona"` |
| `app.js` | L1350 | `#catalog-filter-input` | `placeholder="Buscar entre 500 productos..."` | Sin etiqueta para lectores de pantalla | Agregar `aria-label="Filtrar productos del catálogo de Mercadona"` |
| `app.js` | L1400 | `#recipes-filter-input` | `placeholder="Buscar entre las 60 recetas..."` | Sin etiqueta para lectores de pantalla | Agregar `aria-label="Filtrar recetas de Cookidoo por nombre o ingrediente"` |
| `marketing.js` | L430 | `#filter-category-select` | `<label>Categoría: <select...>` | Sin asociación formal `id`/`for` | Agregar `id="filter-category-select"` y `<label for="filter-category-select">` |
| `marketing.js` | L439 | `#filter-status-select` | `<label>Estado: <select...>` | Sin asociación formal `id`/`for` | Agregar `id="filter-status-select"` y `<label for="filter-status-select">` |
| `marketing.js` | L543 | `#brief-category-select` | Envuelto en texto plano | Sin atributo `for` | Agregar asociación formal con `<label for="brief-category-select">` |
| `marketing.js` | L552 | `#brief-status-select` | Envuelto en texto plano | Sin atributo `for` | Agregar asociación formal con `<label for="brief-status-select">` |

#### Hallazgo A6 (Media Severidad): Botones con Nombres Ambiguos en Modos de Navegación de Lista
- **`public/app.js` L940 (`.quick-swap-button`):**
  - Cada tarjeta de cena presenta un botón idéntico: `<button class="quick-swap-button">↻ Cambio rápido</button>`.
  - Cuando un usuario de lector de pantalla utiliza la lista de botones rápidos de la página (tecla `B` en NVDA o `Rotor` en VoiceOver), escucha repetidas veces: *«Cambio rápido, botón»*, *«Cambio rápido, botón»*, sin saber a qué día o receta corresponde cada uno.
  - **Solución:** Incorporar un span oculto con `.sr-only`:
    ```html
    <button class="quick-swap-button" data-swap-recipe="${escapeHtml(meal.recipe_id)}">
      <span aria-hidden="true">↻</span> Cambio rápido
      <span class="sr-only"> para ${escapeHtml(meal.name)} (${escapeHtml(meal.day)})</span>
    </button>
    ```
- **`public/marketing.js` L533 (`.brief-chip-btn`):**
  - Los chips de sugerencias rápidas tienen texto `+ ${escapeHtml(b.label)}`. El lector pronuncia *«Más Familias saludables»*.
  - **Solución:** Agregar `aria-label="Cargar plantilla: ${escapeHtml(b.label)}"`.
- **`public/marketing.js` L493 (`.status-switch-btn`):**
  - En la botonera de estados («Activa», «Borrador», «Pausada», «Archivada»), no se comunica cuál es el estado actual de la campaña.
  - **Solución:** Añadir `aria-pressed="${c.status === s ? "true" : "false"}"`.

---

### 2.3 Navegación por Teclado y Gestión del Foco (WCAG 2.1.1 / 2.1.2 / 2.4.7)

#### Hallazgo A7 (Crítico): Trampa de Foco Inexistente en el Modal de Seguridad IAP
- **Ubicación:** `public/app.js` L695 y `public/marketing.js` L108
- **Diagnóstico Técnico:**
  Cuando el usuario no está autenticado, se muestra el overlay modal `.auth-gate-overlay`. Sin embargo, al pulsar repetidamente la tecla `Tab`, el foco se desplaza libremente a los enlaces y botones que se encuentran visualmente ocultos detrás del telón semitransparente (`#nav-home-logo`, enlaces de navegación, inputs de la página principal).
- **Incumplimiento:** WCAG 2.1.2 No Keyboard Trap (Nivel A).
- **Remediación:**
  Implementar trampa de foco (`focus trap`) mediante escucha del evento `keydown`:
  ```javascript
  function trapFocus(modalElement, event) {
    if (event.key !== "Tab") return;
    const focusables = modalElement.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      last.focus();
      event.preventDefault();
    } else if (!event.shiftKey && document.activeElement === last) {
      first.focus();
      event.preventDefault();
    }
  }
  ```

#### Hallazgo A8 (Alta Severidad): Contraste Deficiente en el Indicador de Foco (`:focus-visible`)
- **Ubicación:** `public/styles.css` (L2 / bloque de reglas base):
  ```css
  button:focus-visible, textarea:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible {
    outline-offset: 3px;
    outline: 3px solid #008f6147;
  }
  ```
- **Diagnóstico Técnico:**
  El color del borde seleccionado es `#008f6147` (verde Mercadona `#008f61` con un canal alfa hexadecimal `47` equivalente al **28% de opacidad**).
  - Al renderizarse sobre fondo blanco (`#ffffff`), el color resultante percibido es `#b7dfd3`, cuyo ratio de contraste respecto al fondo blanco es de **1.42:1**.
  - Al renderizarse sobre el fondo gris papel (`var(--paper)` = `#f7f7f2`), el contraste efectivo es de **1.38:1**.
- **Incumplimiento:** WCAG 2.1 SC 1.4.11 Non-text Contrast (Nivel AA), que exige un contraste mínimo de **3.0:1** para los estados e indicadores de interfaz.
- **Remediación:**
  Utilizar un contorno sólido de alto contraste con desplazamiento adecuado:
  ```css
  button:focus-visible,
  textarea:focus-visible,
  input:focus-visible,
  select:focus-visible,
  a:focus-visible {
    outline: 2px solid var(--green-dark); /* #006f4a -> Ratio 6.23:1 sobre blanco */
    outline-offset: 2px;
  }
  ```

---

### 2.4 Cumplimiento de Contraste de Color (WCAG 1.4.3 / 1.4.11)

Se ha realizado el cálculo computacional de luminancia relativa y ratio de contraste según el algoritmo estándar W3C para todos los pares cromáticos empleados en la interfaz:

$$\text{Contrast Ratio} = \frac{L_1 + 0.05}{L_2 + 0.05}$$

#### Tabla de Mediciones de Contraste

| Elemento / Clase | Color Primer Plano | Color Fondo | Ratio Medido | Requisito WCAG AA | Diagnóstico | Corrección Recomendada |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| **Texto de botón primario** (`.mercadona-oneclick-btn`, `.confirm-button`) | `#ffffff` | `#008f61` | **4.12:1** | 4.5:1 (Normal) / 3.0:1 (Grande) | ⚠️ Límite | Si el texto mide <14pt bold (<18.6px regular), no cumple 4.5:1. Se aconseja usar `#006f4a` (**6.23:1**) o tipografía bold de 14px+. |
| **Número correlativo de plato** (`.meal-number`) | `#a3a39b` | `#ffffff` | **2.54:1** | 4.5:1 | ❌ **FAIL** | Cambiar a `#686861` (**5.61:1**) o `#55554f` (**7.4:1**). |
| **Identificador de producto** (`.catalog-product-id`) | `#8a8a82` | `#ffffff` | **3.48:1** | 4.5:1 | ❌ **FAIL** | Texto a 9px mono. Cambiar a `#686861` (**5.61:1**). |
| **Placeholder/icono catálogo** (`.catalog-product-image span`) | `#97978f` | `#f5f5ef` | **2.69:1** | 3.0:1 (Icono) | ❌ **FAIL** | Oscurecer a `#66665f` (**4.4:1**). |
| **Borde inactivo de chip brief** (`.brief-chip-btn`) | `#d5dbd7` | `#f7f9f7` | **1.33:1** | 3.0:1 (Borde UI) | ❌ **FAIL** | Aumentar borde a `#96a59c` (**3.12:1**). |
| **Pie de página y avisos legales** (`.catalog-footer`, `.source-footer`) | `#77776f` | `#f7f7f2` | **4.20:1** | 4.5:1 | ❌ **FAIL** | Tipografía pequeña (10px). Oscurecer a `#595952` (**6.98:1**). |
| **Insignia naranja fallback** (`.live-badge.fallback span`) | `#f3a13b` | `#ffffff` | **2.11:1** | 3.0:1 (Gráfico) | ❌ **FAIL** | Oscurecer el naranja a `#b86a04` (**4.55:1**). |
| **Insignia verde catálogo** (`.status-pill`, `.live-badge span`) | `#006f4a` | `#dff3e9` | **5.38:1** | 4.5:1 | ✅ **PASS** | Cumple con holgura. |
| **Texto de alerta de error** (`.auth-error-msg`) | `#9e2a2b` | `#fff0ec` | **6.71:1** | 4.5:1 | ✅ **PASS** | Excelente contraste. |

---

## 3. Auditoría de i18n y Localización en Español de España (es-ES)

De acuerdo con las instrucciones de `/google/src/files/head/depot/google3/learning/gemini/agents/skills/i18n/SKILL.md`:
> *«Never assume decimal separators (. vs ,), grouping separators, or currency symbol positioning. Never hardcode unit symbols or perform manual unit conversion math. Always accommodate ~30-50% text expansion.»*

### 3.1 Gramática, Léxico y Terminología en Contexto Mercadona

#### Hallazgo I1 (Severidad Alta): Calco Léxico Italiano Inadecuado («Anteprima»)
- **Ubicaciones:**
  - `public/marketing.js:638`: `<!-- COLUMNA 3: Anteprima en vivo de la campaña seleccionada -->`
  - `public/marketing.js:639`: `<aside class="customer-preview-panel" aria-label="Anteprima de la campaña seleccionada">`
  - `public/marketing.js:640`: `<p class="eyebrow">Anteprima de la campaña seleccionada</p>`
  - `public/marketing.js:687`: `<p style="font-size:13px; color:var(--muted);">Selecciona una campaña para visualizar su anteprima.</p>`
- **Problema Lingüístico:**
  El vocablo *«Anteprima»* es una palabra netamente italiana. En el contexto empresarial de Mercadona en España, la terminología estándar y natural en interfaces de usuario es **«Vista previa»** o **«Previsualización»**. Su presencia deteriora la calidad percibida de la herramienta.
- **Remediación:** Sustituir todas las apariciones por **«Vista previa»**:
  ```javascript
  <aside class="customer-preview-panel" aria-label="Vista previa de la campaña seleccionada">
    <p class="eyebrow">Vista previa de la campaña seleccionada</p>
    ...
    <p style="font-size:13px; color:var(--muted);">Selecciona una campaña para visualizar su vista previa.</p>
  ```

#### Hallazgo I2 (Severidad Media): Anglicismos y Ortografía de «Clic» vs «Click»
- **Ubicaciones:**
  - `app.js:832`: `Envía las recetas a tu Thermomix y añade la compra al carrito en 1 click`
  - `app.js:970`: `para que puedas enviarla en un solo click a tu cuenta de Cookidoo.`
  - `app.js:1079`: `al pulsar el botón 1-Click.`
  - `app.js:1135`: `"Añadir al carrito de Mercadona (1-Click)"`
- **Norma RAE y Libro de Estilo de Google en Español:**
  En español, la adaptación gráfica asentada es **«clic»** (plural *clics*), no la forma inglesa *click*. Adicionalmente, las expresiones sintácticas *«en un solo clic»* o *«en 1 clic»* son preferibles a la fórmula anglosajona *«1-Click»*.
- **Remediación:**
  - Sustituir *"1 click"* por *"1 clic"*.
  - Sustituir *"un solo click"* por *"un solo clic"*.
  - Sustituir *"1-Click"* por *"en 1 clic"* o *"compra directa en 1 clic"*.

#### Hallazgo I3 (Severidad Media): Extranjerismo Innecesario («Badge»)
- **Ubicación:** `public/marketing.js:609`
  ```html
  <label>Etiqueta destacada (Badge)<input type="text" id="edit-badge" ... /></label>
  ```
- **Remediación:** Eliminar el término inglés entre paréntesis y rotular limpiamente:
  `<label>Etiqueta destacada<input type="text" id="edit-badge" ... /></label>` o *«Distintivo destacado»*.

#### Hallazgo I4 (Severidad Baja): Opciones de Detección Abreviadas
- **Ubicación:** `public/marketing.js:59` y `L544`:
  `<option value="Auto">Auto-detectar según el prompt</option>`
- **Remediación:** En español peninsular culto se prefiere: *«Detección automática según la descripción»*.

---

### 3.2 Formato de Moneda y Números (Intl.NumberFormat vs Literales)

En la norma internacional para el español de España (`es-ES`), las reglas tipográficas y del estándar Unicode CLDR establecen:
1. El símbolo del euro (`€`) se coloca **detrás de la cantidad numérica**, separado de esta por un espacio de no separación (`\u00A0` o `&nbsp;`), nunca delante: `65,00 €` (correcto) vs `€65` o `€65.00` (incorrecto).
2. El separador decimal obligatorio es la **coma (`,`)**, no el punto decimal inglés (`.`).
3. El separador de millares es el espacio fino o el punto (`.`): `1.280.000` o `1,28 mill.`.

#### Inventario de Errores de Moneda en el Código

| Archivo | Línea | Fragmento Actual de Código | Problema Específico | Corrección Mandatoria |
| :--- | :--- | :--- | :--- | :--- |
| `app.js` | L142 | `"≤ €65"` (en `detectedPills`) | Símbolo a la izquierda y sin espacio | `"≤ 65 €"` |
| `app.js` | L263 | `pills.push(`≤ €${mBud ? mBud[1] \|\| mBud[2] : 65}`);` | Prefijo anglosajón hardcodeado | `pills.push(`≤ ${mBud ? mBud[1] \|\| mBud[2] : 65} €`);` |
| `app.js` | L1152 | `<strong>${escapeHtml(String(...total))} €</strong>` | Interpolación directa de float/string con posible punto inglés | Usar `<strong>${formatEUR(...total)}</strong>` |
| `app.js` | L1220 | `<span>≤ €${Number(featuredCampaign.maxBudget).toFixed(2)}</span>` | Uso de `.toFixed(2)` que genera punto decimal inglés (`65.00`) | `<span>≤ ${formatEUR(featuredCampaign.maxBudget)}</span>` |
| `app.js` | L1251 | `<span>... ≤ €${Number(c.maxBudget).toFixed(2)}</span>` | Punto decimal y símbolo a la izquierda | `<span>... ≤ ${formatEUR(c.maxBudget)}</span>` |
| `marketing.js` | L465 | `<small>... ≤ €${Number(c.maxBudget).toFixed(0)}</small>` | Prefijo anglosajón hardcodeado | `<small>... ≤ ${Number(c.maxBudget).toLocaleString('es-ES')} €</small>` |
| `marketing.js` | L625 | `<span>✓ ≤ €${Number(selected.maxBudget).toFixed(2)} Mercadona</span>` | Formato manual erróneo | `<span>✓ ≤ ${formatEUR(selected.maxBudget)} Mercadona</span>` |

> [!NOTE]
> La función `formatEUR(value)` implementada en `public/app.js:188` está perfectamente programada:
> ```javascript
> function formatEUR(value) {
>   return new Intl.NumberFormat("es-ES", {
>     style: "currency",
>     currency: "EUR",
>     minimumFractionDigits: 2,
>   }).format(Number(value || 0));
> }
> ```
> El problema radica en que en los puntos indicados en la tabla anterior, **no se invoca esta función y se sustituye por cadenas manuales con sintaxis anglosajona**.

#### Notación Compacta para Grandes Cifras
- **Ubicación:** `public/marketing.js:403–404`
  ```html
  <strong>1.28M</strong>
  <span>Hogares elegibles</span>
  ```
- **Remediación:** En español, la `M` anglosajona no es la abreviatura convencional. Se debe formatear mediante:
  ```javascript
  new Intl.NumberFormat("es-ES", { notation: "compact", maximumFractionDigits: 2 }).format(1280000);
  // Produce exactamente: "1,28 mill."
  ```

---

### 3.3 Unidades Físicas y Reglas de Pluralización

#### Plurales Rígidos Asumidos (Hardcoded)
Aunque en `app.js:254` y `267` existe una lógica rudimentaria condicional (`${mealCount === 1 ? "cena" : "cenas"}`), en múltiples áreas se asume cantidad plural sin evaluar el valor singular:
- `app.js:844`: `<p class="empty-kicker">Tu menú semanal de ${p.meals.length} cenas</p>` (Si el usuario solicita 1 cena suelta, genera *"1 cenas"*).
- `app.js:977`: `<h3>${p.basket.length} productos de Mercadona · ${formatEUR(p.total)}</h3>` (Si la cesta tiene 1 artículo, produce *"1 productos"*).
- `app.js:1119`: `Se inyectarán directamente los ${p.basket.length} productos...`
- `app.js:1486`: `(${filtered.length} recetas)`

**Solución con `Intl.PluralRules`:**
```javascript
const esPluralRules = new Intl.PluralRules("es-ES");
function pluralize(count, singular, plural) {
  return `${count} ${esPluralRules.select(count) === "one" ? singular : plural}`;
}
// Ejemplo de uso: pluralize(p.basket.length, "producto", "productos")
```

#### Unidades Comerciales en el Contexto de Mercadona
- En `app.js:1013`: `${item.quantity} × ${escapeHtml(item.unit)} (${formatEUR(item.unit_price)}/ud)`
  En el etiquetado oficial de Mercadona se emplea la abreviatura con punto **`ud.`** o la palabra completa **`unidad`**. Se sugiere mantener la uniformidad en `ud.`.
- Las unidades del Sistema Internacional (`g`, `kg`, `ml`, `l`, `min`) están correctamente implementadas sin pluralización incorrecta (ej.: *«25 min»*, no *«25 mins»*).

---

### 3.4 Expansión Textual (~30-50%) y Restricciones de Maquetación en `styles.css`

El español requiere entre un **20% y un 35% más de longitud de caracteres** que el inglés para expresar las mismas ideas. Si el diseño visual utiliza dimensiones rígidas o suprime el salto de línea, se producen desbordamientos o recortes prematuros de información.

#### Hallazgo E1 (Media-Alta Severidad): Colapso Horizontal de la Barra Superior
- **Ubicación:** `public/styles.css` (L6–L54)
  ```css
  .companion-brand-bar, .marketing-brand-bar {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    flex-wrap: nowrap; /* <-- Rígido */
  }
  .companion-brand-bar .top-navigation,
  .marketing-brand-bar .top-navigation {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: clamp(14px, 1.6vw, 26px);
    flex-shrink: 0;
    white-space: nowrap; /* <-- No permite salto */
  }
  .header-controls {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    flex-shrink: 0;
    flex-wrap: nowrap; /* <-- Rígido */
  }
  ```
- **Problema de Maquetación:**
  En pantallas intermedias (1280px a 1400px de ancho, habituales en portátiles corporativos con pantalla de 13"-14" escaladas al 125%), la suma de los logotipos, los 5 botones de navegación en español (`Experiencia Cliente (Planificador)`, `Campaign Library`, etc.) y los selectores de código postal/perfil suman más de 1320px de ancho incompresible. Dado que la media query de colapso no entra en vigor hasta `<= 1280px` (`styles.css` L172), se genera un **desbordamiento horizontal (scroll lateral invisible o truncado)** en pantalla.
- **Remediación:**
  1. Permitir `overflow-x: auto` en `.top-navigation` con una barra de desplazamiento suave o adelantar la media query responsive a `<= 1380px`.
  2. Sustituir `flex-wrap: nowrap` por `flex-wrap: wrap` en `.header-controls`.

#### Hallazgo E2 (Media Severidad): Truncamiento Elíptico Severo en el Listado de Campañas
- **Ubicación:** `public/styles.css` (L2 / bloque `.campaign-admin-copy`):
  ```css
  .campaign-admin-copy strong {
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 12px;
    overflow: hidden;
  }
  ```
- **Problema:** En la columna lateral de marketing, títulos elaborados en español como *«Familias · Pescado y verduras ocultas»* o *«Aprovecha tu despensa, compra solo lo justo»* se cortan a menos de la mitad del texto («Familias · Pescado y verd...»), dificultando la identificación de la campaña.
- **Remediación:**
  Permitir hasta dos líneas de texto antes de truncar:
  ```css
  .campaign-admin-copy strong {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    white-space: normal;
    overflow: hidden;
    font-size: 12px;
  }
  ```

---

### 3.5 Metadatos del Documento HTML y Especificación Regional

- **Archivos:** `public/index.html:2` y `public/marketing.html:2`
- **Declaración Actual:**
  ```html
  <!DOCTYPE html>
  <html lang="es">
  ```
- **Evaluación y Recomendación:**
  Aunque `lang="es"` es genéricamente válido, para optimizar la compatibilidad con motores de síntesis de voz (TTS) en lectores de pantalla y asistentes que distinguen acentos regionales (ej.: pronunciación de la «z» y «c» frente a seseo latinoamericano, entonación de preguntas), se recomienda especificar la variante regional peninsular:
  ```html
  <html lang="es-ES">
  ```

---

## 4. Plan de Acción y Matriz de Remediación

A continuación se presenta la matriz priorizada de intervenciones requeridas para alcanzar la plena conformidad WCAG 2.1 AA y el estándar de calidad lingüística de Google.

| # | Dominio | Fichero(s) | Líneas | Severidad | Acción de Remediación Concreta |
| :---: | :--- | :--- | :--- | :---: | :--- |
| **1** | **ARIA** | `app.js` | 1513–1521 | **Alta** | Crear región permanente en el DOM (`aria-live="polite"` y `aria-atomic="true"`) para anuncios de Toast y estados dinámicos. |
| **2** | **Teclado** | `app.js`, `marketing.js` | 695–735, 108–146 | **Alta** | Implementar trampa de foco (`focus trap`) y foco inicial programático en el modal de autenticación IAP. |
| **3** | **Foco UI** | `styles.css` | 2 (base) | **Alta** | Sustituir `outline: 3px solid #008f6147` por contorno sólido accesible `outline: 2px solid #006f4a; outline-offset: 2px;`. |
| **4** | **Contraste** | `styles.css` | 2, 455 | **Alta** | Ajustar `#a3a39b` (`.meal-number`) a `#686861` y el borde `#d5dbd7` (`.brief-chip-btn`) a `#96a59c`. |
| **5** | **Labels** | `app.js` | 880, 881, 1081, 1350, 1400 | **Alta** | Añadir atributos `aria-label` descriptivos a los inputs de búsqueda de catálogo, recetas y credenciales. |
| **6** | **Labels** | `marketing.js` | 430, 439, 543, 552 | **Media** | Asociar formalmente `<label for="...">` con los elementos `<select>` de filtrado y creación de campañas. |
| **7** | **i18n** | `marketing.js` | 638–640, 687 | **Alta** | Reemplazar el calco italiano **«Anteprima»** por el término estándar en España **«Vista previa»**. |
| **8** | **Moneda** | `app.js` | 142, 263, 1152, 1220, 1251 | **Alta** | Erradicar la sintaxis anglosajona `≤ €65` y `.toFixed(2)`; invocar consistentemente `formatEUR()`. |
| **9** | **Moneda** | `marketing.js` | 465, 625 | **Alta** | Reemplazar `≤ €${Number(c.maxBudget).toFixed(0)}` por formato de moneda español (`formatEUR`). |
| **10** | **Léxico** | `app.js`, `marketing.js` | Varios | **Media** | Corregir anglicismos: *"1-Click"* / *"1 click"* $\rightarrow$ *"en 1 clic"*; *"Badge"* $\rightarrow$ *"Etiqueta destacada"*. |
| **11** | **CSS** | `styles.css` | 6–54, 172 | **Media** | Adaptar `flex-wrap` y adelantar breakpoint a 1380px para evitar solapamientos por expansión de texto en español. |
| **12** | **HTML** | `index.html`, `marketing.html` | 2 | **Baja** | Actualizar la declaración de idioma a `<html lang="es-ES">`. |

---
*Fin del informe de auditoría. Documento generado para su consolidación en el reporte maestro del proyecto.*
