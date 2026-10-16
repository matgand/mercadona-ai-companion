# Auditoría de Calidad del Catálogo de Recetas Cookidoo y Servicio de Integración

**Fecha de ejecución:** 27 de Septiembre de 2026  
**Auditor Responsable:** Child 1: Cookidoo Recipe Quality Auditor  
**Subagentes Paralelos:** Slice A (0–1666), Slice B (1667–3333), Slice C (3334–4999)  
**Archivos Auditados:**
- Catálogo de datos: `/usr/local/google/home/mgandolfi/mercadona-ai-companion/data/cookidoo_recipes.json` (5.000 recetas)
- Catálogo de productos: `/usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json` (1.595 productos)
- Servicio de integración: `/usr/local/google/home/mgandolfi/mercadona-ai-companion/cookidoo_service.py`

---

## 1. Resumen Ejecutivo y Puntuación de Calidad

| Dimensión | Puntuación | Estado | Observación Principal |
|---|:---:|:---:|---|
| **Integridad de Esquema** | **98.6%** | ⚠️ Requiere ajuste | 68 recetas (índices 0–67) carecen de `category` e `is_dinner`. |
| **Unicidad de Identificadores** | **100.0%** | ✅ Excelente | 5.000 IDs y URLs de Cookidoo estrictamente únicos. |
| **Calidad de Imágenes** | **99.9%** | ✅ Excelente | 100% alojadas en CDN oficial (`assets.tmecosys.com`). Solo 1 colisión errónea detectada. |
| **Integridad de Ingredientes** | **99.9%** | ✅ Excelente | 47.439 ingredientes sin etiquetas HTML ni entidades residuales. 79.7% truncados a 10 items. |
| **Valores Numéricos (Outliers)** | **98.4%** | ⚠️ Requiere ajuste | 1 anomalía extrema (900 min en `r712249`); 76 recetas con tiempos subestimados (<=10m en guisos). |
| **Mapeo Mercadona & Alérgenos** | **95.7%** | ⚠️ Riesgo Alérgenos | 100% de product_ids existen en catálogo, pero colisiones de subcadenas asignaron carne a 217 vegetarianos. |
| **Higiene de Marca / Boilerplate** | **99.1%** | ⚠️ Requiere ajuste | 2 menciones en títulos, 4 "Varoma", 34 "(Cocción de arroz)", 6 menciones en descripciones. |
| **Servicio `cookidoo_service.py`** | **90.0%** | ℹ️ Mejorable | Sanitizador regex es demasiado estricto; faltan filtros de limpieza en carga de catálogo. |

---

## 2. Auditoría de Esquema y Estructura de Datos

El catálogo cuenta con **5.000 registros**. Cada registro debe cumplir con 19 atributos normalizados.

### 2.1 Cobertura de Campos

```
Total de registros: 5.000
Campos requeridos evaluados: 19
```

| Campo | Tipo Esperado | Cobertura | Registros Faltantes / Vacíos |
|---|---|:---:|:---:|
| `recipe_id` | `str` | 100% (5.000/5.000) | 0 |
| `cookidoo_id` | `str` | 100% (5.000/5.000) | 0 |
| `name` | `str` | 100% (5.000/5.000) | 0 |
| `original_name` | `str` | 100% (5.000/5.000) | 0 |
| `description` | `str` | 100% (5.000/5.000) | 0 |
| `image_url` | `str` | 100% (5.000/5.000) | 0 |
| `image_alt` | `str` | 100% (5.000/5.000) | 0 |
| `cookidoo_url` | `str` | 100% (5.000/5.000) | 0 |
| `minutes` | `int` | 100% (5.000/5.000) | 0 |
| `calories_per_serving` | `int` | 100% (5.000/5.000) | 0 |
| `cookidoo_servings` | `int` | 100% (5.000/5.000) | 0 |
| `estimated_cost` | `float` | 100% (5.000/5.000) | 0 |
| `is_fish` | `bool` | 100% (5.000/5.000) | 0 |
| `is_vegetarian` | `bool` | 100% (5.000/5.000) | 0 |
| `allergens` | `list[str]` | 100% (5.000/5.000) | 0 (768 listas vacías válidas) |
| `product_ids` | `list[str]` | 100% (5.000/5.000) | 0 |
| `ingredients` | `list[str]` | 100% (5.000/5.000) | 0 |
| **`category`** | `str` | **98.64% (4.932/5.000)** | **68 faltantes** (índices 0 a 67) |
| **`is_dinner`** | `bool` | **98.64% (4.932/5.000)** | **68 faltantes** (índices 0 a 67) |

### 2.2 Detalle de la Brecha de Esquema (Índices 0 a 67)
Las primeras 68 recetas (desde `r106128` *Pastelitos de pescado con patata* hasta `r129078` *Goulash húngaro*) provienen de una tanda inicial de scraping o generación:
- Carencia de `category`: provoca que en los filtros de la interfaz o el recomendador no aparezcan en ninguna categoría.
- Carencia de `is_dinner`: no se indexan al solicitar planes de cena.
- Formato divergente de `image_alt`: tienen el prefijo `"Foto de portada de Cookidoo: <nombre>"`, a diferencia del resto (4.932) que contiene directamente el `<nombre>`.
- Diferenciación `name` vs `original_name`: son las únicas 68 recetas donde `name` está traducido al español y `original_name` contiene el título en inglés (`Thai Fishcakes`, `Creamy capsicum and zucchini soup`, etc.). En las restantes 4.932 recetas, `original_name == name`.

### 2.3 Distribución de Categorías en el Catálogo
Total clasificadas: **4.932 recetas**
- `Entradas y ensaladas`: 997 (20.2%)
- `Platos principales: carne`: 928 (18.8%)
- `Platos principales: pescado`: 650 (13.2%)
- `Platos de pasta y arroz`: 562 (11.4%)
- `Platos principales: otros`: 341 (6.9%)
- `Repostería salada (quiches, pizzas, empanadas)`: 336 (6.8%)
- `Sopas y cremas`: 335 (6.8%)
- `Platos principales: vegetarianos`: 329 (6.7%)
- `Aperitivos y tapas`: 202 (4.1%)
- `Acompañamientos y verduras`: 127 (2.6%)
- `Menús completos`: 86 (1.7%)
- `Salsas y cremas saladas`: 39 (0.8%)
- `[Sin categoría]`: 68 (1.4%)

---

## 3. Auditoría de Imágenes y Multimedia

- **Dominio CDN:** El 100% de las URLs (5.000) apuntan al CDN oficial de Thermomix/Vorwerk: `https://assets.tmecosys.com/...`.
- **Estado de Enlaces:** 0 URLs rotas, 0 strings vacíos, 0 imágenes placeholder (`default.jpg`, `placeholder.png`).
- **Unicidad de URLs de Imagen:** 4.994 imágenes únicas. Existen **6 URLs compartidas** entre 12 recetas:
  1. `r396142` (*Guiso marinero de patatas con bacalao*) y `r802268` (*Tortilla jugosa de queso y espinacas*): ❌ **Error de asignación**. Platos completamente diferentes con la misma imagen.
  2. `r699195` (*Ternera estofada con ñoquis*) y `r1066787` (*Guiso de aguja de ternera y ñoquis de patata al vapor*): ✅ Variante de la misma receta.
  3. `r432316` (*Sopa versátil con tropezones*) y `r429952` (*Versatile chunky soup*): ✅ Misma receta en español e inglés.
  4. `r113575` (*Empanada de acelgas, chorizo y panceta*) y `r759568` (*Empanada de caballa y espinacas*): ⚠️ Imagen genérica de masa de empanada reutilizada por Cookidoo.
  5. `r86300` (*Menú: Sopa de picadillo. Rape con gambón...*) y `r117758` (*Menú para dos: Sopa de picadillo. Rape con gambón...*): ✅ Variante ración simple vs doble.
  6. `r85649` (*Ensalada templada de berros con pulpo y langostinos para dos*) y `r123473` (*Ensalada templada de berros con pulpo y langostinos*): ✅ Variante de raciones.

---

## 4. Unicidad de Títulos y Recetas Duplicadas

- **Colisiones de ID:** **0**. No existe ninguna colisión en `recipe_id` ni en `cookidoo_id`.
- **Títulos Duplicados:** Existen **30 títulos compartidos** (60 recetas en total).
  - Todas poseen IDs distintos y URLs distintas en Cookidoo.
  - La mayoría corresponden a variaciones de porciones (para 2 vs para 4), técnicas Thermomix (TM5 vs TM6 Cocción Lenta) o adaptaciones regionales.
  - *Muestras destacadas:*
    - `Magret de pato con salsa de soja y mirin`: `r460860` y `r138478`
    - `Lasaña boloñesa`: `r570442` (carne) y `r55079` (pasta y arroz)
    - `Cocido madrileño`: `r55700` y `r689411`
    - `Salmón con salsa de naranja`: `r41523` y `r454806`
    - `Risotto con pera y gorgonzola`: `r19887` (6 raciones) y `r595980` (10 raciones)
    - `Arroz a la cubana`: `r55736` (60 min) y `r671627` (40 min)
    - `Espaguetis integrales con salsa de aguacate`: `r174241` y `r142172`
    - `Curry indio de verduras`: `r6255` y `r576589`

---

## 5. Análisis de Valores Numéricos y Detección de Anomalías

### 5.1 Calorías por Ración (`calories_per_serving`)
- **Rango:** 55 kcal a 889 kcal.
- **Media:** 407.7 kcal | **Mediana:** 407.0 kcal | **Desviación Estándar:** 89.2 kcal.
- **Valores <= 0:** 0 recetas.
- **Valores > 1000 kcal:** 0 recetas.
- **Valores < 100 kcal (2 recetas):**
  - `r106128` (*Pastelitos de pescado con patata*): 55 kcal (aperitivo dividido en 9 raciones).
  - `r67066` (*Crema ligera de verduras en 25 minutos*): 79 kcal.
- **Conclusión:** La distribución calórica es nutricionalmente sólida, plausible y no presenta valores disparatados.

### 5.2 Tiempo de Preparación / Cocinado (`minutes`)
- **Rango:** 5 min a 900 min.
- **Media:** 38.2 min | **Mediana:** 35.0 min.
- **Anomalía Extrema (> 180 min):** **1 receta**
  - `r712249` (*Crema de verduras con huevo poché*): **900 minutos (15 horas)**.
    - *Causa raíz:* El scraped original contenía ingredientes de masa madre / prefermento de centeno con fermentación en frío (15 h) mezclados erróneamente con una crema de verduras. El tiempo real de cocinado de la crema con huevo es de **30 minutos**.
- **Tiempos Subestimados (<= 10 min):** **187 recetas**
  - Preparaciones frías, aperitivos, batidos o tartares legítimos: ~110 recetas (ej. `Carpaccio`, `Ceviche`, `Gazpacho`, `Pesto`).
  - **Artifacts de scraping (tiempo activo en vez de total):** ~77 recetas de cocción lenta o legumbres:
    - `r280495` (*Lentejas estofadas con verduras en Thermomix*): **10 min** (imposible estofar lentejas en 10m).
    - `r566743` (*Garbanzos con compango en cocción lenta*): **8 min** (un cocido a baja temperatura requiere 4 a 6 horas).
    - `r44868` (*Alitas de pollo con salsa de soja, miel y limón*): **8 min**.
    - `r62927` (*Carrilleras de cerdo ibérico al vino oloroso*): **8 min**.
    - `r699197` (*Costillas de cerdo con salsa barbacoa en cocción lenta*): **8 min**.
    - `r806383` (*Caldo de pollo rico en colágeno*): **8 min**.

### 5.3 Raciones (`cookidoo_servings`)
- **Rango:** 1 a 24 raciones.
- **Media:** 6.3 raciones | **Mediana:** 6.0 raciones.
- **Valores <= 0:** 0 recetas.
- **Raciones de 1 persona (28 recetas):**
  - Recetas diseñadas explícitamente para individuales: `r396146` (*Macarrones all'arrabiata para uno*), `r396144` (*Risotto para uno*), `r412870` (*Menú para 1*).
- **Raciones altas (>= 12 raciones, 620 recetas):**
  - 12 raciones representa el 12.4% del catálogo. Se aplica típicamente a tapas, bocaditos, canapés, nuggets y pizzas para compartir.
  - **Inconsistencia menor:** Salsas o masas como `r807640` (*Pesto de perejil*) o `r55171` (*Masa básica de pizza*) marcan 12 raciones.
- **Máximo absoluto:** `r938184` (*Rollitos vegetales al horno*): 24 unidades/raciones.

### 5.4 Coste Estimado y Catálogo Mercadona
- **Rango:** 3.06 € a 32.16 €. Media: 12.60 €.
- **Consistencia Matemática:** El `estimated_cost` equivale al 100% de la suma exacta de los `unit_price` de los productos vinculados en `product_ids`.
- **Integridad Referencial con Mercadona:**
  - Total de referencias de producto analizadas: **29.192**.
  - Total de productos únicos de Mercadona referenciados: **212** (de 1.595 disponibles en `mercadona_products.json`).
  - **Productos inexistentes en el catálogo:** **0 (0.0%)**. Todas las claves de producto resuelven perfectamente.

---

## 6. Integridad de Ingredientes y Mapeos de Alérgenos

### 6.1 Truncamiento de Ingredientes (Cap de 10 elementos)
- Se detectó que **3.985 recetas (79.7%) tienen exactamente 10 ingredientes**.
- Las recetas cuyo despiece en Cookidoo superaba 10 ingredientes fueron truncadas rígidamente en el elemento 10 durante la exportación.
- *Efecto colateral:* En recetas compuestas (menú completo plato + postre), se pierden los ingredientes finales o se prioriza la subreceta que estaba al inicio.

### 6.2 Alérgenos y Falsos Positivos de Pescado / Carne
Se descubrieron dos problemas derivados de mapeos léxicos ingenuos (búsqueda de subcadenas):
1. **Falsos positivos de `is_fish: true` y alérgeno `fish` en carnes (5 recetas en Slice A):**
   - `r556151` (*Tiras de pechuga de pollo doradas*)
   - `r556152` (*Tiras de pechuga de pollo con beicon*)
   - `r112336` (*Pimientos rellenos de carne picada*)
   - `r798923` (*Hummus con carne dorada*)
   - *Causa:* Se les asignó alérgeno de pescado sin contener ningún producto de mar.
2. **Contaminación de recetas vegetarianas con productos cárnicos (217 recetas en Slice B):**
   - Substring "chile" -> `62401` *Mejillón de Chile entero* (añade moluscos a un curry vegano `r750379`).
   - Substring "corazones de alcachofa" -> `2857` *Hígados y corazones de pollo* (en pasta con alcachofas `r645132`).
   - Substring "alas" (de alcachofas) -> `25184` *Alas de pollo congeladas* (`r108872`).
   - Substring "caldo de verduras" -> `7313` *Caldo de pollo Hacendado* (`r19887`).
   - Substring "aceitunas" -> `22910` *Aceitunas verdes rellenas de anchoa* (`r212861`).

### 6.3 Plantillas de Descripción Contradictorias (59 recetas)
59 recetas con carne o pescado tienen una descripción generada que afirma:
> *"Plato vegetal nutritivo y equilibrado con..."*
- Ejemplo `r566743` (*Garbanzos con compango*): *"Plato vegetal nutritivo y equilibrado con garbanzos secos, chorizo, morcilla y lacón."*
- Ejemplo `r424595` (*Potaje con gambones*): *"Plato vegetal nutritivo y equilibrado con gambones crudos enteros..."*

---

## 7. Boilerplate, Marcas Registradas y Textos Residuales

### 7.1 Menciones de Marcas en Nombres y Descripciones
La política de la aplicación exige que la experiencia sea neutra para el usuario de Mercadona y no dependa de menciones a Thermomix:

- **Títulos con Thermomix / Modelos (2 recetas):**
  - `r280495`: *"Lentejas estofadas con verduras en Thermomix"* -> Sugerido: *"Lentejas estofadas con verduras"*
  - `r1085632`: *"Espaguetis diavolo integrales (TM5, TM6)"* -> Sugerido: *"Espaguetis diavolo integrales"*
- **Títulos con accesorio "Varoma" (4 recetas):**
  - `r789368`: *"Filetes de merluza al vapor en Varoma"* -> Sugerido: *"Filetes de merluza al vapor"*
  - `r748459`: *"Tarros de verdura y pavo en Varoma con arroz largo"* -> Sugerido: *"Tarros de verdura y pavo al vapor con arroz"*
  - `r909922`: *"Tortilla caprese en Varoma"* -> Sugerido: *"Tortilla caprese al vapor"*
  - `r821785`: *"Castañas en Varoma"* -> Sugerido: *"Castañas al vapor"*
- **Títulos con sufijo de modo asistido "(Cocción de arroz)" (34 recetas):**
  - Ejemplo `r756906`: *"Arroz con bogavante (Cocción de arroz)"* -> Sugerido: *"Arroz con bogavante"*
- **Descripciones con "Thermomix" (6 recetas):**
  - `r161846`, `r396142`, `r802268`, `r819645`, `r85427`, `r929941`.
  - Actualmente `cookidoo_service.py:sanitize_recipe_description()` solo busca `^Receta oficial de Thermomix Cookidoo...` al principio de la cadena, dejando intactas frases intermedias como *"guisadas en Thermomix"*.

### 7.2 Calidad HTML / Caracteres Especiales
- **Etiquetas HTML (`<p>`, `<div>`, etc.):** 0 encontradas.
- **Entidades HTML (`&amp;`, `&#39;`, etc.):** 0 encontradas.
- **Mojibake / Codificación rota:** 0 caracteres corrompidos. El texto en español (tildes, eñes) está correctamente serializado en UTF-8.

---

## 8. Auditoría del Servicio de Integración (`cookidoo_service.py`)

Se inspeccionó detalladamente la implementación técnica de `cookidoo_service.py`:

1. **Función `sanitize_recipe_description()`:**
   - La expresión regular `^Receta\s+oficial\s+de\s+Thermomix\s+Cookidoo...` solo coincide si la descripción comienza exactamente con ese patrón. Si una descripción termina con *"cocinado lentamente en Thermomix."*, no la limpia.
   - **Mejora recomendada:** Reemplazar menciones intermedias de `en Thermomix` o `en el vaso de la Thermomix` por `al robot de cocina` o `a fuego lento`.
2. **Función `load_cookidoo_catalog()`:**
   - Carga y cachea en memoria los 5.000 registros.
   - Aplica `sanitize_recipe_description()` dinámicamente sobre la marcha.
   - **Mejora recomendada:** Si `category` o `is_dinner` faltan en el JSON, aplicar valores por defecto o inferirlos durante la carga para evitar `KeyError` o fallos en capas superiores.
3. **Función `fetch_live_cookidoo_recipe()`:**
   - Scrapea en tiempo real desde `cookidoo.es` o `cookidoo.thermomix.com` mediante JSON-LD estructurado.
   - Excelente manejo de User-Agent, timeouts (6s) y parsing ISO 8601 de duraciones (`PT25M`).
4. **Función `send_recipe_to_thermomix()`:**
   - Si no hay credenciales, devuelve elegantemente `handoff_ready` abriendo el enlace directo en Cookidoo.
   - Soporte asíncrono robusto para `cookidoo-api` (`_send_to_cookidoo_async`) programando fecha en el calendario `Mi Semana`.

---

## 9. Plan de Acción y Recomendaciones Prioritarias

### Prioridad 1: Seguridad Alimentaria y Lógica de Negocio (Crítico)
1. **Corregir los 217 mapeos vegetarianos contaminados:**
   - Aplicar una validación estricta en el recomendador o generador: si `is_vegetarian == True`, vetar productos con categoría cárnica o pescado.
   - Desacoplar las coincidencias por subcadena parcial (`chile` -> mejillones, `corazones` -> corazones de pollo).
2. **Corregir los 5 falsos positivos de pescado (`is_fish: true`) en pollo y carnes.**
3. **Corregir la colisión de imagen en `r802268`:**
   - La *Tortilla jugosa de queso y espinacas* no debe mostrar la foto del *Guiso marinero de patatas con bacalao*.

### Prioridad 2: Integridad del Esquema (Alto)
1. **Completar las 68 recetas iniciales (índices 0–67):**
   - Asignar `category` correspondiente (`Platos principales: carne`, `Platos principales: pescado`, etc.).
   - Asignar `is_dinner: True`.
   - Limpiar `image_alt` eliminando `"Foto de portada de Cookidoo: "`.
2. **Normalizar `is_dinner`:**
   - Establecer `is_dinner = False` en batidos/smoothies (`r723033`-`r723037`), barras de pan crudas (`r818966`) y repostería dulce (`r817553`).

### Prioridad 3: Limpieza de Tiempos y Redacción (Medio)
1. **Corregir `r712249`:** Modificar `minutes: 900` por `minutes: 30`.
2. **Re-estimar tiempos de cocción lenta:** En recetas con `cocción lenta` o `estofadas` que marcan <= 10 min, ajustar el tiempo total a valores realistas (30 a 60 min).
3. **Refinar `sanitize_recipe_description()` en `cookidoo_service.py`:**
   - Ampliar la sanitización para reemplazar *"en Thermomix"* y *"en Varoma"*.
   - Limpiar los 34 títulos con `(Cocción de arroz)` y los 4 con `en Varoma`.
