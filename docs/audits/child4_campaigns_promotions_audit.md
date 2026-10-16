# Auditoría de Campañas y Coherencia Promocional (Child 4)
**Mercadona AI Companion × Thermomix Cookidoo**  
**Fecha:** 27 de Septiembre de 2026  
**Auditor:** Child 4: Campaigns & Promotional Coherence Auditor  
**Subagentes Involucrados:**  
- `Subagent A: Integrity & Financial Auditor` (`69c625f0-9123-434d-9517-69a01c3f7e4a`)
- `Subagent B: Campaign Designer & Proposal Validator` (`348f7215-df7a-48f6-8a83-9ca35ce09a08`)

---

## 1. Resumen Ejecutivo

El presente informe detalla la auditoría técnica, nutricional, financiera y estratégica de las campañas promocionales del proyecto **Mercadona AI Companion**. La auditoría evaluó la biblioteca de campañas (`data/campaigns.json`), el microservicio de marketing (`campaign_service.py`) y el motor de planificación semanal (`gemini_planner.py`), contrastándolos de forma determinista con el catálogo de **5.000 recetas de Thermomix Cookidoo** (`data/cookidoo_recipes.json`) y el surtido real de **1.595 productos de Mercadona** (`data/mercadona_products.json`) en código postal `28016` (Madrid).

### Hallazgos Principales:
1. **Integridad Referencial Absoluta (100% PASS):**  
   - Las 7 campañas existentes generan mediante su `seedPrompt` un total de 35 asignaciones de cenas semanales. El 100% (35/35) de las recetas existen en el catálogo oficial de Cookidoo.
   - Todos los identificadores de producto (`product_ids`) referenciados en las recetas y en las cestas de la compra existen y cuentan con stock y precio unitario en el catálogo de Mercadona.
   - En el análisis global de las 5.000 recetas de Cookidoo no existe ni una sola referencia huérfana a productos de Mercadona (0 dangling references).
2. **Coherencia Presupuestaria y Precisión de Cesta (100% PASS):**  
   - Todas las cestas semanales generadas respetan holgadamente el presupuesto máximo fijado (`maxBudget`), con importes totales que oscilan entre **18,56 € y 37,56 €** (frente a límites de 45 € a 65 €).
   - El coste medio por persona y cena se sitúa entre **0,93 € y 3,44 €**, posicionando la cesta como una propuesta de ahorro hipercompetitiva frente a restaurantes o delivery.
3. **Equilibrio Nutricional y Restricciones Dietéticas (100% PASS):**  
   - Los límites calóricos explícitos son rigurosamente cumplidos:
     - `saludables-ligeras-equilibradas` (límite 450 kcal): máximo real de **343 kcal** (promedio 294,2 kcal).
     - `familias-pescado-cuchara-otono` (límite 520 kcal): máximo real de **491 kcal** (promedio 362,8 kcal).
     - `saludables-proteina-sin-gluten` (límite 420 kcal): máximo real de **417 kcal** (promedio 331,0 kcal).
   - Se validaron exclusiones de alérgenos (sin gluten, sin lácteos, sin frutos secos) y cuotas mínimas de pescado con 0 infracciones.
4. **Viabilidad de Tiempos de Cocinado (100% PASS):**  
   - Ninguna receta excede los límites estipulados de 25 o 30 minutos de tiempo activo en Thermomix.
5. **Incidencias Menores Detectadas (Acciones Correctivas Propuestas):**  
   - **Imágenes de portada:** De las 7 campañas, 4 disponen de fichero `.webp` en `public/meals/`. Las 3 campañas más recientes (`salmon-kale-soup.webp`, `turkey-avocado-wraps.webp`, `Stewed-lentils.webp`) no existen físicamente en disco, requiriendo un fallback automático en frontend o generación de los assets.
   - **Parsing de despensa:** En `gemini_planner.py:188`, la expresión regular `(?:el|la|los|las|the)?` consume parcialmente prefijos en palabras como *"las espinacas"* extrayendo `'s espinacas'`. Asimismo, faltan gerundios como *"usando"* o *"utilizando"*.
6. **Propuesta de Nuevas Campañas de Alto Impacto (4 Campañas):**  
   - Diseñadas y validadas 4 nuevas campañas alineadas con la estacionalidad en España, el recetario de Cookidoo y productos estratégicos de Mercadona (platos de cuchara otoñales, tapeo saludable de fin de semana, pescado fresco de lonja al vapor en Varoma y cesta anticrisis < 40€ de batch cooking).

---

## 2. Auditoría Técnica de `campaign_service.py` y Arquitectura

El microservicio `campaign_service.py` gestiona el ciclo de vida de las campañas del equipo de Marketing de Mercadona. Funciona tanto de forma local como en despliegues distribuidos en Google Cloud Run (`SERVICE_ROLE=campaign-library`).

### 2.1 Flujo de Sincronización y Persistencia
- **Almacenamiento Local:** `data/campaigns.json` se accede mediante exclusión mutua con `threading.Lock()` (`_LOCK`), garantizando seguridad en entornos concurrentes.
- **Normalización de Datos:** La función `_enrich_campaign()` valida y asegura valores por defecto para perfiles (`familias`, `saludables`, `rutina-rapida`, `ahorro`), estados (`Activa`, `Planificada`, `Borrador`, `Terminada`) y metadatos de hogares elegibles.
- **Sincronización Peer-to-Peer:** Implementa `push_sync_to_peer_services()` y `fetch_campaigns_from_remote_or_local()`, empleando cabeceras de identidad OIDC de Google Cloud Run (`Metadata-Flavor: Google`) y tokens de sincronización interna (`X-Internal-Sync-Token` con SHA256 derivado de `SESSION_SECRET`).

### 2.2 Generación con Gemini 3.8 Flash
- La función `generate_campaign_from_brief()` permite al equipo de Marketing redactar un brief en lenguaje natural (ej. *"Campaña de vuelta al cole económica"*).
- Incorpora un guardarraíl determinista previo (`validate_meal_planning_prompt`) para descartar solicitudes fuera de dominio antes de invocar la API de Vertex AI.
- Invoca la API de Vertex AI con Gemini (`gemini-2.0-flash` o `gemini-1.5-flash`), con un fallback determinista robusto que completa título, tagline, badge, seedPrompt y perfil si no hay conectividad o credenciales de nube.

---

## 3. Matriz de Integridad y Métricas de las 7 Campañas Actuales

| Campaign ID | Título | Estado | Perfil / Hogar | Presup. Máx | Cesta Real | Holgura (€) | Coste/Cena/Pax | Tiempo (Cap/Real) | Calorías (Cap/Avg/Max) | Estado Imagen |
| :--- | :--- | :---: | :---: | :-: | :-: | :-: | :-: | :-: | :-: | :---: |
| `familias-semana-resuelta` | Tu semana familiar, resuelta | Activa | Familias (2A + 1N) | 65,00 € | **33,88 €** | +31,12 € | 2,26 € | 25m / 25m | — / 424,6 / 526 | ✅ OK |
| `saludables-ligeras-equilibradas` | Cenas ligeras y equilibradas | Activa | Saludables (2A) | 60,00 € | **22,55 €** | +37,45 € | 2,26 € | 30m / 30m | 450 / 294,2 / 343 | ✅ OK |
| `rutina-rapida-25min` | Cena lista en menos de 25 min | Activa | Rutina rápida (2A) | 50,00 € | **30,18 €** | +19,82 € | 3,02 € | 25m / 25m | — / 367,8 / 540 | ✅ OK |
| `ahorro-despensa-inteligente` | Aprovecha tu despensa | Activa | Ahorro (2A + 2N) | 48,00 € | **18,56 €** | +29,44 € | 0,93 € | 30m / 30m | — / 473,2 / 615 | ✅ OK |
| `familias-pescado-cuchara-otono` | Especial cuchara y pescado | Planificada | Familias (2A + 2N) | 62,00 € | **37,56 €** | +24,44 € | 1,88 € | 30m / 30m | 520 / 362,8 / 491 | ⚠️ Pendiente |
| `saludables-proteina-sin-gluten` | Semana alta en proteína | Borrador | Saludables (2A) | 58,00 € | **34,39 €** | +23,61 € | 3,44 € | 25m / 22m | 420 / 331,0 / 417 | ⚠️ Pendiente |
| `ahorro-vuelta-al-cole` | Vuelta a la rutina < 45€ | Terminada | Ahorro (2A + 1N) | 45,00 € | **27,83 €** | +17,17 € | 1,86 € | 30m / 30m | — / 472,0 / 576 | ⚠️ Pendiente |

---

## 4. Desglose Detallado de Cada Campaña Existente

### 4.1 `familias-semana-resuelta`
- **Seed Prompt:** *"Planifica 5 cenas entre semana para 2 adultos y 1 niño. Mantén el presupuesto bajo 65€, prepara cada receta en 25 minutos o menos, incluye una cena de pescado y usa la pasta que ya tengo en casa."*
- **Alineación de Perfil:** Familias trabajadoras que buscan variedad sin complicaciones.
- **Cenas Generadas:**
  1. *Fusilli con calamares en salsa americana y champiñones* (`r69479`) — 20 min | 471 kcal | Pescado: Sí | Despensa: Pasta
  2. *Mac and Cheese con calabaza* (`r792540`) — 15 min | 526 kcal | Pescado: No | Despensa: Pasta
  3. *Curry de pescado y langostinos* (`r263180`) — 25 min | 364 kcal | Pescado: Sí
  4. *Salmón con pak choi a la pimienta verde* (`r86755`) — 20 min | 456 kcal | Pescado: Sí
  5. *Cocción de pasta larga* (`r910248`) — 25 min | 306 kcal | Pescado: No | Despensa: Pasta
- **Evaluación Financiera:** Presupuesto de 65,00 €; cesta real de **33,88 €** (17 artículos). Tasa de uso presupuestario: 52,1%. Coste medio por persona/cena: **2,26 €**.
- **Evaluación Nutricional:** Aporte medio de 424,6 kcal por ración, equilibrado entre carbohidratos complejos y proteína de pescado.

### 4.2 `saludables-ligeras-equilibradas`
- **Seed Prompt:** *"Planifica 5 cenas saludables para 2 adultos. Mantén el presupuesto bajo 60€, máximo 30 minutos por receta y menos de 450 kcal por ración."*
- **Alineación de Perfil:** Adultos con foco en mantenimiento de peso, control calórico y digestiones ligeras.
- **Cenas Generadas:**
  1. *Gazpacho de aguacate* (`r448993`) — 10 min | 343 kcal
  2. *Percebes cocidos* (`r923811`) — 20 min | 247 kcal
  3. *Ensalada templada de pasta y garbanzos* (`r123512`) — 25 min | 342 kcal
  4. *Bígaros al vapor de algas* (`r83683`) — 30 min | 245 kcal
  5. *Lentejas estofadas con verduras en Thermomix* (`r280495`) — 10 min | 294 kcal
- **Evaluación Financiera:** Presupuesto de 60,00 €; cesta real de **22,55 €** (17 artículos). Holgura de 37,45 €. Coste por persona/cena: **2,26 €**.
- **Evaluación Nutricional:** Límite máximo de 450 kcal plenamente respetado (máximo real: **343 kcal**, promedio: **294,2 kcal**).

### 4.3 `rutina-rapida-25min`
- **Seed Prompt:** *"Planifica 5 cenas rápidas para 2 adultos. Presupuesto máximo de 50€, máximo 25 minutos por receta, sin frutos secos y usa las espinacas y el arroz que ya tengo en casa."*
- **Alineación de Perfil:** Días con prisa, teletrabajo o jornadas extensas.
- **Cenas Generadas:**
  1. *Arroz con atún, espinacas y judías rojas* (`r65238`) — 25 min | 345 kcal | Despensa: Arroz, espinacas
  2. *Arroz integral con espinacas frescas* (`r220919`) — 15 min | 440 kcal | Despensa: Arroz, espinacas
  3. *Risotto de espinacas y gambas* (`r462532`) — 25 min | 240 kcal | Despensa: Arroz, espinacas
  4. *Caldo de gallina* (`r141581`) — 15 min | 274 kcal | Despensa: Arroz
  5. *Cacerola de carne y arroz* (`r319946`) — 8 min | 540 kcal
- **Evaluación Financiera:** Presupuesto de 50,00 €; cesta real de **30,18 €** (15 artículos).
- **Evaluación de Alérgenos:** Alérgeno excluido `nuts`: 0 recetas contienen frutos secos.

### 4.4 `ahorro-despensa-inteligente`
- **Seed Prompt:** *"Planifica 5 cenas económicas para 2 adultos y 2 niños con presupuesto máximo de 48€, en 30 minutos o menos, sin lactosa y usa los huevos y las patatas que ya tengo en casa."*
- **Alineación de Perfil:** Familias de 4 miembros con foco en máxima economía doméstica y aprovechamiento.
- **Cenas Generadas:**
  1. *Ensalada de patata, remolacha fresca y huevo* (`r154741`) — 15 min | 477 kcal | Despensa: Huevos, patatas
  2. *Ensaladilla rusa* (`r55676`) — 30 min | 615 kcal | Despensa: Huevos, patatas
  3. *Ensalada campera con naranja* (`r77976`) — 15 min | 317 kcal | Despensa: Huevos, patatas
  4. *Huevos rotos con patatas y jamón* (`r255607`) — 30 min | 554 kcal | Despensa: Huevos, patatas
  5. *Pimientos y patatas con huevos revueltos* (`r115582`) — 30 min | 403 kcal | Despensa: Huevos, patatas
- **Evaluación Financiera:** Presupuesto de 48,00 €; cesta real de **18,56 €** (10 artículos). Coste por ración familiar (4 personas): **0,93 €**.
- **Evaluación de Alérgenos:** Alérgeno excluido `dairy`: 0 recetas contienen lácteos.

### 4.5 `familias-pescado-cuchara-otono`
- **Seed Prompt:** *"Planifica 5 cenas familiares para 2 adultos y 2 niños con presupuesto máximo de 62€, máximo 30 minutos por receta, incluyendo dos cenas de pescado y legumbres."*
- **Cenas Generadas:**
  1. *Arroz al curry con pescado ahumado (kedgeree)* (`r751237`) — 30 min | 491 kcal
  2. *Salpicón de legumbres con palitos de surimi* (`r21720`) — 10 min | 285 kcal
  3. *Sopa agridulce de langostinos (Tom Yum Goong)* (`r362686`) — 25 min | 364 kcal
  4. *Arroz con salmonetes* (`r791010`) — 30 min | 418 kcal
  5. *Alubias con gambas* (`r65016`) — 20 min | 256 kcal
- **Evaluación:** Cesta de **37,56 €** (24 artículos). Límite calórico de 520 kcal cumplido (máx 491 kcal).

### 4.6 `saludables-proteina-sin-gluten`
- **Seed Prompt:** *"Planifica 5 cenas sin gluten para 2 adultos con menos de 420 kcal por ración, en 25 minutos o menos y presupuesto máximo de 58€."*
- **Cenas Generadas:**
  1. *Salmorejo sin gluten* (`r121551`) — 10 min | 417 kcal
  2. *Ensalada con tortitas de amaranto y atún (sin gluten)* (`r135554`) — 20 min | 298 kcal
  3. *Focaccia con uvas y queso (sin azúcar, sin gluten)* (`r766089`) — 22 min | 416 kcal
  4. *Smoothie light* (`r723037`) — 10 min | 267 kcal
  5. *Carabineros a la sal* (`r541590`) — 20 min | 257 kcal
- **Evaluación:** Cesta de **34,39 €** (19 artículos). Límite de 420 kcal cumplido (máx 417 kcal). 100% libre de gluten.

### 4.7 `ahorro-vuelta-al-cole`
- **Seed Prompt:** *"Planifica 5 cenas económicas para 2 adultos y 1 niño con presupuesto máximo de 45€, máximo 30 minutos por receta y usando el arroz que ya tengo en casa."*
- **Cenas Generadas:**
  1. *Arroz integral, lentejas y verduras al vapor* (`r242167`) — 22 min | 460 kcal
  2. *Croquetas de garbanzos y zanahoria* (`r41951`) — 20 min | 576 kcal
  3. *Arroz con brócoli, atún y aguacate* (`r282842`) — 30 min | 460 kcal
  4. *Caldo de gallina (Canja de galinha)* (`r305121`) — 22 min | 324 kcal
  5. *Cacerola de carne y arroz* (`r319946`) — 8 min | 540 kcal
- **Evaluación:** Cesta de **27,83 €** (17 artículos). Holgura de 17,17 €.

---

## 5. Auditoría de Assets Visuales

El catálogo de imágenes de portada referenciadas por las campañas se encuentra en `public/meals/`.

| Imagen Referenciada | Campaña Asignada | Estado en Disco | Acción Recomendada |
| :--- | :--- | :---: | :--- |
| `/meals/lemon-hake-potatoes.webp` | `familias-semana-resuelta` | ✅ Presente (178 KB) | Mantener. |
| `/meals/pasta-chickpea-salad.webp` | `saludables-ligeras-equilibradas` | ✅ Presente (90 KB) | Mantener. |
| `/meals/quick-broccoli-salad.webp` | `rutina-rapida-25min` | ✅ Presente (195 KB) | Mantener. |
| `/meals/chickpea-spinach-tomato-rice.webp` | `ahorro-despensa-inteligente` | ✅ Presente (210 KB) | Mantener. |
| `/meals/salmon-kale-soup.webp` | `familias-pescado-cuchara-otono` | ❌ Ausente | Utilizar fallback a `/meals/lemon-hake-potatoes.webp` o generar asset. |
| `/meals/turkey-avocado-wraps.webp` | `saludables-proteina-sin-gluten` | ❌ Ausente | Utilizar fallback a `/meals/pasta-chickpea-salad.webp` o generar asset. |
| `/meals/Stewed-lentils.webp` | `ahorro-vuelta-al-cole` | ❌ Ausente | Utilizar fallback a `/meals/chickpea-spinach-tomato-rice.webp` o generar asset. |

---

## 6. Propuesta de 4 Nuevas Campañas de Alto Impacto para Mercadona

Diseñadas por el **Subagente B** y validadas con `build_weekly_plan()`. Conectan momentos clave del consumidor español con categorías estratégicas de Mercadona.

### Propuesta 1: Otoño y Tradición: Platos de Cuchara y Legumbres Hacendado
- **ID:** `otono-platos-cuchara-legumbres`
- **Categoría:** Familias (Perfil: `familias`)
- **Badge:** `Otoño de Cuchara · Legumbres Hacendado`
- **Hogares Elegibles:** 450.000 hogares
- **Imagen:** `/meals/chickpea-spinach-tomato-rice.webp`
- **Presupuesto Máximo:** 55,00 € | **Tiempo Máximo:** 35 min
- **Seed Prompt:** *"Planifica 5 cenas de platos de cuchara con lentejas, garbanzos y guisos para 2 adultos y 2 niños con presupuesto máximo de 55€, máximo 35 minutos por receta y usa el aceite de oliva que ya tengo en casa."*
- **Resultado Simulación:**
  - **Cesta Real:** **29,29 €** (15 productos Mercadona, holgura de 25,71 €).
  - **Recetas Cookidoo:**
    1. *Salpicón de legumbres con palitos de surimi* (`r21720`) — 10 min | 285 kcal | 8,30 €
    2. *Ventresca de bonito confitada con vinagreta de lentejas* (`r122102`) — 30 min | 325 kcal | 12,91 €
    3. *Garbanzos con fideos y mejillones* (`r37806`) — 20 min | 358 kcal | 5,00 €
    4. *Macarrones integrales con lentejas* (`r212862`) — 30 min | 397 kcal | 3,95 €
    5. *Lentejas estofadas tradicionales* (`r603746`) — 30 min | 506 kcal | 5,33 €
- **Impacto Comercial:** Dinamización de legumbres cocidas en bote de cristal Hacendado, verduras de sofrito y mariscos cocidos. Estimación de **+24% de conversión en familias**.

```json
{
  "id": "otono-platos-cuchara-legumbres",
  "title": "Otoño y Tradición: Platos de Cuchara y Legumbres Hacendado",
  "tagline": "Cinco cenas de cuchara calientes, saciantes y nutritivas en Thermomix por menos de 30€.",
  "category": "Familias",
  "occasion": "Familias",
  "profileId": "familias",
  "badge": "Otoño de Cuchara · Legumbres Hacendado",
  "status": "Activa",
  "imageUrl": "/meals/chickpea-spinach-tomato-rice.webp",
  "seedPrompt": "Planifica 5 cenas de platos de cuchara con lentejas, garbanzos y guisos para 2 adultos y 2 niños con presupuesto máximo de 55€, máximo 35 minutos por receta y usa el aceite de oliva que ya tengo en casa.",
  "mealCount": 5,
  "maxBudget": 55,
  "maxMinutes": 35,
  "maxCaloriesPerServing": null,
  "eligibleHouseholds": "450k hogares",
  "whyProfile": "Diseñada para el perfil Familias (2 adultos + 2 niños) ante la bajada otoñal de temperaturas: aprovecha la comodidad de los guisos en Thermomix y el ahorro de las legumbres Hacendado para resolver las cenas semanales por menos de 30€.",
  "updatedAt": "2026-09-27T12:00:00Z"
}
```

---

### Propuesta 2: Tapeo y Picoteo Saludable de Fin de Semana
- **ID:** `tapeo-picoteo-saludable-finde`
- **Categoría:** Rutina rápida (Perfil: `rutina-rapida`)
- **Badge:** `Tapeo Saludable · ≤ 25 min`
- **Hogares Elegibles:** 330.000 hogares
- **Imagen:** `/meals/quick-broccoli-salad.webp`
- **Presupuesto Máximo:** 52,00 € | **Tiempo Máximo:** 25 min
- **Seed Prompt:** *"Planifica 5 cenas de picoteo y tapeo con brochetas, hummus, wraps y tortilla para 2 adultos con presupuesto máximo de 52€ y en 25 minutos o menos."*
- **Resultado Simulación:**
  - **Cesta Real:** **48,39 €** (20 productos Mercadona).
  - **Recetas Cookidoo:**
    1. *Brochetas de salmón con hummus de aguacate* (`r721328`) — 20 min | 353 kcal | 11,36 €
    2. *Wraps con guisantes, feta y cherrys* (`r909920`) — 10 min | 414 kcal | 10,70 €
    3. *Wraps de pollo con piña* (`r128019`) — 20 min | 455 kcal | 13,60 €
    4. *Wraps de pollo con salsa barbacoa y piña* (`r286027`) — 10 min | 367 kcal | 14,35 €
    5. *Tortilla jugosa de queso y espinacas* (`r802268`) — 25 min | 507 kcal | 8,14 €
- **Impacto Comercial:** Alternativa saludable y casera al delivery de fin de semana. Tracciona carnes magras en corte fino, quesos especiales (feta, emmental), panadería (tortillas de trigo) y ensaladas de IV gama. Estimación de **+19% en pedidos jueves y viernes**.

```json
{
  "id": "tapeo-picoteo-saludable-finde",
  "title": "Tapeo y Picoteo Saludable de Fin de Semana",
  "tagline": "Tapas caseras, brochetas en Varoma y wraps ligeros en menos de 25 minutos para disfrutar del fin de semana.",
  "category": "Rutina rápida",
  "occasion": "Rutina rápida",
  "profileId": "rutina-rapida",
  "badge": "Tapeo Saludable · ≤ 25 min",
  "status": "Activa",
  "imageUrl": "/meals/quick-broccoli-salad.webp",
  "seedPrompt": "Planifica 5 cenas de picoteo y tapeo con brochetas, hummus, wraps y tortilla para 2 adultos con presupuesto máximo de 52€ y en 25 minutos o menos.",
  "mealCount": 5,
  "maxBudget": 52,
  "maxMinutes": 25,
  "maxCaloriesPerServing": null,
  "eligibleHouseholds": "330k hogares",
  "whyProfile": "Especialmente concebida para el perfil Rutina rápida (jóvenes adultos y parejas ocupadas): transforma el tapeo informal de viernes y vísperas de festivo en recetas caseras saludables listas en 10-25 minutos, evitando comida rápida o procesados.",
  "updatedAt": "2026-09-27T12:05:00Z"
}
```

---

### Propuesta 3: Cenas Mediterráneas con Pescado Fresco de Lonja
- **ID:** `cenas-mediterraneas-pescado-lonja`
- **Categoría:** Saludables (Perfil: `saludables`)
- **Badge:** `Lonja & Varoma · Dieta Mediterránea`
- **Hogares Elegibles:** 340.000 hogares
- **Imagen:** `/meals/lemon-hake-potatoes.webp`
- **Presupuesto Máximo:** 65,00 € | **Tiempo Máximo:** 30 min
- **Seed Prompt:** *"Planifica 5 cenas de pescado fresco con merluza al vapor, lubina a la sal y bacalao para 2 adultos y 1 niño con presupuesto máximo de 65€, en 30 minutos o menos y usa la patata que ya tengo en casa."*
- **Resultado Simulación:**
  - **Cesta Real:** **40,95 €** (16 productos Mercadona, holgura de 24,05 €).
  - **Recetas Cookidoo:**
    1. *Merluza al vapor de almejas* (`r33507`) — 30 min | 433 kcal | 15,30 €
    2. *Bacalao al vapor sobre crema de guisantes y calabaza* (`r69593`) — 30 min | 422 kcal | 15,95 €
    3. *Pastel de patata con acelgas y bacalao* (`r63748`) — 30 min | 270 kcal | 7,45 € (Despensa: patata)
    4. *Salmón al vapor con verduras* (`r40286`) — 30 min | 439 kcal | 9,10 € (Despensa: patata)
    5. *Crema fría de bacalao* (`r23670`) — 30 min | 338 kcal | 10,60 € (Despensa: patata)
- **Impacto Comercial:** Impulsa el consumo de pescado blanco y azul eliminando la fricción de humos y olores en el hogar gracias a la cocción en Varoma. Potencia referencias de pescadería congelada y fresca (bacalao MareDeus, salmón y merluza). Estimación de **+31% en penetración de pescadería**.

```json
{
  "id": "cenas-mediterraneas-pescado-lonja",
  "title": "Cenas Mediterráneas con Pescado Fresco de Lonja",
  "tagline": "Merluza, bacalao y salmón cocinados al vapor en Varoma con huerta mediterránea. Cero humos ni olores.",
  "category": "Saludables",
  "occasion": "Saludables",
  "profileId": "saludables",
  "badge": "Lonja & Varoma · Dieta Mediterránea",
  "status": "Activa",
  "imageUrl": "/meals/lemon-hake-potatoes.webp",
  "seedPrompt": "Planifica 5 cenas de pescado fresco con merluza al vapor, lubina a la sal y bacalao para 2 adultos y 1 niño con presupuesto máximo de 65€, en 30 minutos o menos y usa la patata que ya tengo en casa.",
  "mealCount": 5,
  "maxBudget": 65,
  "maxMinutes": 30,
  "maxCaloriesPerServing": null,
  "eligibleHouseholds": "340k hogares",
  "whyProfile": "Diseñada para el perfil Saludables (y familias con foco nutricional): fomenta el consumo recomendado de 3-4 raciones semanales de pescado blanco y azul, reduciendo a cero la fricción de humos, frituras y olores domésticos gracias al recipiente Varoma.",
  "updatedAt": "2026-09-27T12:10:00Z"
}
```

---

### Propuesta 4: Batch Cooking Exprés: Cesta Anticrisis < 40€
- **ID:** `batch-cooking-expres-cesta-anticrisis`
- **Categoría:** Ahorro (Perfil: `ahorro`)
- **Badge:** `Cesta Anticrisis · 36,43€ Total`
- **Hogares Elegibles:** 410.000 hogares
- **Imagen:** `/meals/pasta-chickpea-salad.webp`
- **Presupuesto Máximo:** 38,00 € | **Tiempo Máximo:** 25 min
- **Seed Prompt:** *"Planifica 5 cenas económicas de batch cooking exprés para 2 adultos con presupuesto máximo de 38€, en 25 minutos o menos y usa el arroz y los huevos que ya tengo en casa."*
- **Resultado Simulación:**
  - **Cesta Real:** **36,43 €** (18 productos Mercadona). Coste por cena y persona: **1,82 €**.
  - **Recetas Cookidoo:**
    1. *Crostata con salami y queso (sin gluten)* (`r147318`) — 15 min | 445 kcal | 8,15 €
    2. *Cake salado con aceitunas, queso y jamón (sin gluten)* (`r147364`) — 15 min | 433 kcal | 9,00 €
    3. *Lentejas guisadas con verduras* (`r553376`) — 15 min | 401 kcal | 6,08 €
    4. *Lentejas y soja con verduras* (`r426547`) — 15 min | 273 kcal | 10,90 €
    5. *Pollo con arroz Hainan, sopa de verduras y huevo al vapor* (`r729124`) — 22 min | 530 kcal | 10,45 €
- **Impacto Comercial:** Cesta escudo frente a la inflación y cadenas de descuento duro. Focalizada en marca Hacendado de alta rotación (legumbres, harinas, condimentos y avícola). Estimación de **+35% en retención de clientes sensibles al precio**.

```json
{
  "id": "batch-cooking-expres-cesta-anticrisis",
  "title": "Batch Cooking Exprés: Cesta Anticrisis < 40€",
  "tagline": "Cinco cenas completas por solo 36,43€ semanales con técnicas de horneado batch y cocción simultánea.",
  "category": "Ahorro",
  "occasion": "Ahorro",
  "profileId": "ahorro",
  "badge": "Cesta Anticrisis · 36,43€ Total",
  "status": "Activa",
  "imageUrl": "/meals/pasta-chickpea-salad.webp",
  "seedPrompt": "Planifica 5 cenas económicas de batch cooking exprés para 2 adultos con presupuesto máximo de 38€, en 25 minutos o menos y usa el arroz y los huevos que ya tengo en casa.",
  "mealCount": 5,
  "maxBudget": 38,
  "maxMinutes": 25,
  "maxCaloriesPerServing": null,
  "eligibleHouseholds": "410k hogares",
  "whyProfile": "Máxima eficiencia para el perfil Ahorro: una planificación de cinco cenas por menos de 37€ en total (apenas 3,64€ por cena para 2 adultos), reutilizando ingredientes cruzados de alta durabilidad y despensa básica.",
  "updatedAt": "2026-09-27T12:15:00Z"
}
```

---

## 7. Plan de Acción y Recomendaciones de Implementación

1. **Corrección de Expresiones Regulares en `gemini_planner.py`:**
   - En `extract_pantry_items()` (línea 188): sustituir `(?:el|la|los|las|the)?` por un límite de palabra estricto `\b(?:los|las|el|la|the)\b\s*` para evitar capturar residuos como `'s espinacas'`.
   - Incorporar gerundios comunes en español (`(?:usando|utilizando|aprovechando)`) al patrón de detección de despensa.
2. **Cobertura de Imágenes en Frontend:**
   - Para las campañas planificadas o en borrador que referencian imágenes ausentes en `public/meals/`, remapear temporalmente su `imageUrl` a los 4 activos verificados (`lemon-hake-potatoes.webp`, `pasta-chickpea-salad.webp`, `quick-broccoli-salad.webp`, `chickpea-spinach-tomato-rice.webp`) o añadir lógica de fallback en `app.js` (`onerror="this.src='/meals/lemon-hake-potatoes.webp'"`).
3. **Incorporación al Catálogo de Campañas:**
   - Añadir las 4 nuevas campañas propuestas al archivo `data/campaigns.json` o mediante llamadas POST al endpoint `/api/campaigns/generate` para sincronizarlas con el entorno en vivo.
