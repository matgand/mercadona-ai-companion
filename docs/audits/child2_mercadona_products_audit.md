# AUDITORÍA INTEGRAL DEL CATÁLOGO DE PRODUCTOS DE MERCADONA & MERCADONA_SERVICE
**Ruta del Catálogo:** [`data/mercadona_products.json`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json) (1.595 productos)  
**Servicio de Integración:** [`mercadona_service.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/mercadona_service.py) (776 líneas)  
**Catálogo de Recetas Cruzadas:** [`data/cookidoo_recipes.json`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/cookidoo_recipes.json) (5.000 recetas Thermomix Cookidoo)  
**Auditor:** Child 2 — Mercadona Products Catalog & Service Auditor  
**Fecha de Ejecución:** 27 de Septiembre de 2026  
**Estatus:** Auditoría Exhaustiva Completada — 3 Subagentes de Especialidad Ejecutados

---

## 1. RESUMEN EJECUTIVO & HALLAZGOS CRÍTICOS

El catálogo local [`data/mercadona_products.json`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json) contiene **1.595 referencias de productos** verificadas contra los almacenes de Mercadona Online (`tienda.mercadona.es`), sirviendo de base determinista para el planificador semanal con Gemini 3.8 Flash ([`gemini_planner.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/gemini_planner.py)) y la sincronización 1-Click Cart ([`mercadona_service.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/mercadona_service.py)).

A través de una partición tridimensional del catálogo en 3 rodajas temáticas auditadas por subagentes especializados, se han verificado métricas matemáticas exactas, discrepancias en el modelado de datos y fallos de seguridad alimentaria que deben resolverse en la capa de datos y servicio:

| Métrica Global | Valor Auditado | Impacto Operativo & Diagnóstico |
| :--- | :---: | :--- |
| **Volumen Total de SKUs** | **1.595 productos** | Cobertura suficiente para 5.000 recetas, pero con lagunas severas de bebidas y aguas. |
| **SKUs con `categories` explícitas** | **101 / 1.595 (6,3%)** | **93,7% de omisión de taxonomía** (1.494 productos con `categories: null`). |
| **SKUs con `ingredients` estructurados** | **97 / 1.595 (6,1%)** | **93,9% de omisión** de lista de ingredientes en el JSON. |
| **SKUs con `unit_size` numérico** | **97 / 1.595 (6,1%)** | El 93,9% almacena el peso/volumen mezclado en la cadena de texto `unit`. |
| **Precio Medio (`unit_price`)** | **3,56 €** | Mediana: **2,05 €** \| Desviación Estándar: **15,82 €** (distribución altamente asimétrica). |
| **Rango de Precios** | **0,20 € — 476,00 €** | Mín: *Pimiento verde* (0,20 €) \| Máx: *Jamón bellota 100% 8.5 kg* (476,00 €). |
| **SKUs con Alérgenos Positivos** | **643 / 1.595 (40,3%)** | 952 productos (59,7%) tienen el valor por defecto `"Sin alérgenos declarados en la API"`. |
| **Falsos Positivos de Alérgenos Críticos** | **8 productos** | **Calabaza cacahuete** etiquetada con *cacahuetes*; **champiñones frescos** con *frutos de cáscara*. |
| **Falsos Negativos de Alérgenos Críticos** | **4 productos** | Pescados y rabas empanadas que declaran pescado pero omiten **gluten/trigo**. |
| **Unidades de Peso Corruptas** | **29 productos** | Productos de pescado congelado con unidades incompletas `"Paquete  kg"`. |
| **SKUs utilizados en Recetas Cookidoo** | **261 / 1.595 (16,4%)** | 261 productos ancla sustentan el 100% de las 5.000 recetas Cookidoo mapeadas. |
| **Alcance en Recetas Cookidoo** | **5.000 / 5.000 (100%)** | Cero productos huérfanos entre recetas y catálogo; 100% de recetas tienen ingredientes válidos. |

```
                                  MAPA DE INTEGRACIÓN DEL CATÁLOGO
   +-----------------------------------------------------------------------------------------------+
   |                                 MERCADONA CATALOG (1.595 SKUs)                                |
   +-----------------------------------------------------------------------------------------------+
                 |                                  |                                  |
                 v                                  v                                  v
   +---------------------------+      +---------------------------+      +---------------------------+
   |   SLICE A: FRESCOS        |      |   SLICE B: DESPENSA       |      |   SLICE C: CONGELADOS     |
   |   846 SKUs (53,0%)        |      |   345 SKUs (21,6%)        |      |   404 SKUs (25,3%)        |
   |   Produce, Carne, Pescado |      |   Pasta, Arroz, Especias  |      |   Congelados, Vinos,      |
   |   Huevos, Lácteos, Pan    |      |   Aceites, Legumbres      |      |   Snacks, Preparados      |
   +---------------------------+      +---------------------------+      +---------------------------+
                 |                                  |                                  |
                 v                                  v                                  v
   +-----------------------------------------------------------------------------------------------+
   |                      COOKIDOO 5.000 RECETAS (Thermomix Integration Engine)                    |
   |  - 4.940 recetas (98,8%) usan Frescos (Slice A)     -> Cebollas, ajos, huevos, pimientos      |
   |  - 4.728 recetas (94,6%) usan Despensa (Slice B)    -> AOVE Hacendado (3.468 r), Curry (2.053) |
   |  - 2.150 recetas (43,0%) usan Congelados (Slice C)   -> Nueces (565 r), Langostinos, Salmón   |
   +-----------------------------------------------------------------------------------------------+
```

---

## 2. AUDITORÍA DEL SERVICIO MERCADONA (`mercadona_service.py`)

Se realizó una inspección línea por línea de [`mercadona_service.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/mercadona_service.py) (776 líneas), que implementa el cliente HTTP y de sesión contra la API oficial de `tienda.mercadona.es`:

### 2.1 Puntos Fuertes Implementados
1. **Resolución de Código Postal Dinámica (`resolve_postal_code`, L55-86):**
   - Ejecuta `PUT https://tienda.mercadona.es/api/postal-codes/actions/change-pc/` con cabeceras de cliente reales.
   - Extrae el almacén logístico de entrega desde las cabeceras `x-customer-wh` y `x-customer-pc`.
   - Incluye fallback determinista (`_guess_warehouse`, L88-100) para Madrid (`mad3`), Valencia (`vlc1`), Barcelona (`bcn1`), Alicante (`alc1`) y Sevilla (`svq1`).
2. **Carga en Memoria con Caché (`load_snapshot_products`, L43-53):**
   - Carga diferida e indexación por ID en un diccionario `dict[str, dict[str, Any]]`, asegurando accesos $O(1)$ sin sobrecargar I/O.
3. **Validación Concurrente en Tiempo Real (`get_catalog_for_postal_code`, L153-186):**
   - Utiliza `concurrent.futures.ThreadPoolExecutor(max_workers=8)` para consultar `GET /api/products/<id>/?lang=es&wh=<wh>` en paralelo para verificar stock y precio en vivo.
4. **Manejo Seguro de Autenticación (`parse_mercadona_auth_input`, L217-300):**
   - Soporta comandos cURL de DevTools, volcados HAR, tokens JWT crudos y payloads de sesión, decodificando claims de SimpleJWT sin exponer credenciales en logs.
5. **Inyección de Carrito 1-Click (`prepare_mercadona_oneclick_cart`, L608-775):**
   - Soporta modos `add` (fusión acumulativa) y `replace` sobre el endpoint `PUT /api/customers/<id>/cart/`, validando la estructura requerida `{"lines": [{"product_id", "quantity", "sources"}]}`.

### 2.2 Limitaciones y Deficiencias Técnicas Detectadas
1. **Falta de Búsqueda y Normalización en `mercadona_service.py`:**
   - El servicio **no contiene funciones internas de búsqueda de catálogo ni de tokenización**. La búsqueda se delega a JavaScript en el navegador ([`public/app.js`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/public/app.js) L1350) o a expresiones regulares en [`gemini_planner.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/gemini_planner.py).
   - No existe un método para filtrar por categoría jerárquica, alérgenos o precio por kilo.
2. **Dependencia de la Estructura Dispersa:**
   - `fetch_live_product` (L102-150) calcula `unit = f"{unit_size} {size_format}"`, pero cuando el snapshot local tiene solo la cadena `unit`, los campos `unit_size` y `size_format` quedan vacíos al serializarse.

---

## 3. AUDITORÍA DE CATEGORÍAS, TAXONOMÍA Y DISTRIBUCIÓN DE PRECIOS

### 3.1 Desequilibrio de la Taxonomía Cruda vs Clasificación Real
En el archivo original [`data/mercadona_products.json`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json), **solo 101 productos (6,3%)** tienen el campo `categories` poblado (correspondientes al scrape inicial). Los restantes 1.494 productos tienen `categories: null`.

Al aplicar un clasificador determinista basado en reglas sobre el total de 1.595 productos, se obtiene la taxonomía balanceada real:

| Categoría Normalizada | SKUs Totales | % Catálogo | Subcategorías Principales Representadas |
| :--- | :---: | :---: | :--- |
| **Fruta y verdura fresca** | 241 | 15,1% | Frutas (plátano, manzana, cítricos), verduras (tomate, cebolla, patata, pimiento, calabacín), hierbas frescas. |
| **Carne y aves** | 202 | 12,7% | Pollo (pechuga, muslos, alitas), cerdo (lomo, costilla), ternera/vacuno, conejo, picadas. |
| **Pescado y marisco (Fresco y congelado)** | 163 | 10,2% | Merluza, salmón, bacalao, calamar, sepia, gambas, langostinos, mejillones. |
| **Charcutería y quesos** | 180 | 11,3% | Jamones ibéricos y serranos, quesos curados/tiernos/rallados, bacón, fiambres. |
| **Lácteos y huevos** | 117 | 7,3% | Leche entera/desnatada/sin lactosa, mantequilla, natas, yogures, huevos camperos. |
| **Panadería, masas y cereales** | 100 | 6,3% | Pan de molde, barras frescas, baguettes, tostadas, crackers, masas de hojaldre. |
| **Arroz, legumbres y pasta** | 92 | 5,8% | Macarrones, espaguetis, arroz redondo/vaporizado, garbanzos, lentejas, alubias. |
| **Aceites, especias y condimentos** | 128 | 8,0% | AOVE (1L, 3L, 5L, spray), aceite de girasol, vinagres, azafrán, curry, pimienta, sal. |
| **Conservas, caldos y cremas** | 80 | 5,0% | Atún en lata, tomate triturado, caldos de pollo/carne en brik, cremas de verduras. |
| **Congelados (Verduras y platos)** | 71 | 4,5% | Guisantes, habas baby, salteados, lasañas y pizzas ultracongeladas. |
| **Aperitivos, frutos secos y encurtidos** | 78 | 4,9% | Nueces, almendras, pistachos, aceitunas Chupadedos, pepinillos, banderillas. |
| **Bebidas (Vinos, café, infusiones)** | 50 | 3,1% | Vinos blancos (Rueda, Rioja), fino, Pedro Ximénez, café en grano/cápsulas, infusiones. |
| **Platos preparados y refrigerados** | 45 | 2,8% | Tortillas de patata, wraps, guacamole, hummus, ensaladillas. |
| **Dulces, miel, desayunos y otros** | 48 | 3,0% | Miel de flores, mermeladas, chocolates para fundir, postres lácteos. |
| **TOTAL** | **1.595** | **100,0%** | **100% clasificado de forma determinista** |

### 3.2 Gran Laguna de Catálogo Detectada: Cervezas, Refrescos y Aguas
Un hallazgo crítico de la auditoría es que el catálogo de 1.595 productos **carece por completo de cervezas (0 SKUs), aguas minerales (0 SKUs) y refrescos de cola/naranja (0 SKUs)**. 
- Las coincidencias previas con la palabra `cola` correspondían a pescado (`colas de gambón`, `cola de rape`), chocolates de repostería y batidos `ColaCao`.
- Los vinos presentes son exclusivamente **vinos blancos, dulces o de cocina (23 SKUs)**. No existe **ningún vino tinto con alcohol** en el snapshot (solo 2 productos sin alcohol/mosto).

### 3.3 Distribución de Precios y Percentiles Globales
- **Número de Productos:** 1.595
- **Media de Precio:** 3,56 €
- **Mediana de Precio:** 2,05 €
- **Desviación Estándar:** 15,82 €
- **Mínimo:** 0,20 € (`69320` *Pimiento verde freír*, Pieza 0.08 kg)
- **Máximo:** 476,00 € (`58323` *Jamón de bellota ibérico 100% Campo Extremadura*, 8.5 kg)
- **Percentiles:**
  - $P_{10}$: 1,00 €
  - $P_{25}$: 1,45 €
  - $P_{50}$ (Mediana): 2,05 €
  - $P_{75}$: 3,34 €
  - $P_{90}$: 5,50 €
  - $P_{99}$: 17,25 €

El 90% de los productos del catálogo cuesta 5,50 € o menos, reflejando el modelo de precios bajos y marcas propias (Hacendado) de Mercadona. La cola derecha está dominada por piezas enteras de jamón ibérico y ruedas completas de queso curado.

---

## 4. AUDITORÍA DETALLADA DE LAS 3 RODAJAS DE PRODUCTOS

### 4.1 Rodaja A: Frescos (Fruta, Verdura, Carne, Pescado, Huevos, Lácteos, Panadería)
- **Archivo de Trabajo:** `scratch/slice_a.json`
- **Total de Productos:** **846 referencias (53,0% del catálogo)**
- **Distribución de Precios:** Mín: 0,20 € \| Máx: 476,00 € \| Media: 4,37 € \| Mediana: 2,25 € \| StdDev: 21,57 €
- **Precio Unitario Normalizado por Kilo (€/kg, n=756):**
  - Media: **10,69 €/kg** \| Mediana: **7,33 €/kg** \| Mín: **0,90 €/kg** (*Melón piel de sapo*) \| Máx: **168,00 €/kg** (*Jamón bellota 100% lonchas 90g* a 15,12 €).
- **Precio Unitario Normalizado por Litro (€/l, n=74):**
  - Media: **1,64 €/l** \| Mediana: **1,29 €/l** \| Mín: **0,82 €/l** (*Leche desnatada Hacendado*) \| Máx: **5,67 €/l** (*Claras pasteurizadas*).
- **Packaging Parsed:** Bandeja (182), Paquete (192), Pieza (87), Pack multipack (68), Bote/Tarro (68), Tarrina (31).
- **Alérgenos Declarados:** 363 productos con alérgenos positivos (leche: 212, gluten: 78, pescado: 42, huevo: 17, frutos de cáscara: 13).
- **Intersección con Cookidoo:** **130 de 846 SKUs (15,4%)** aparecen en recetas, pero constituyen la base del **98,8% de las 5.000 recetas** (cebollas en 2.247 recetas, ajos en 2.232 recetas, pan de molde en 1.032 recetas, huevos M en 808 recetas).

### 4.2 Rodaja B: Despensa, Granos, Pastas, Especias, Aceites, Legumbres, Conservas
- **Archivo de Trabajo:** `scratch/slice_b.json`
- **Total de Productos:** **345 referencias (21,6% del catálogo)**
- **Distribución de Precios:** Mín: 0,33 € \| Máx: 19,00 € (*AOVE Hacendado 5L*) \| Media: 2,15 € \| Mediana: 1,55 € \| StdDev: 2,18 €
- **Precio Unitario Normalizado por Kilo (€/kg, n=268):**
  - Media: **46,07 €/kg** \| Mediana: **6,55 €/kg** \| Mín: **0,40 €/kg** (*Sal fina 1kg*) \| Máx: **4.875,00 €/kg** (*Azafrán hebra Hacendado 0.4g* a 1,95 €).
  - Outliers superiores: Azafrán molido (4.750 €/kg), canela en rama (78,95 €/kg), sazonador paella (77,50 €/kg), hojas de laurel (70,83 €/kg).
  - Outliers inferiores: Sal común (0,40 €/kg), harina de trigo 5kg (0,59 €/kg), arroz redondo (1,15 €/kg), macarrones (1,15 €/kg).
- **Precio Unitario Normalizado por Litro (€/l, n=76):**
  - Media: **3,68 €/l** \| Mediana: **3,23 €/l** \| Mín: **0,65 €/l** (*Vinagre de vino blanco*) \| Máx: **13,33 €/l** (*Aroma de vainilla*).
  - AOVE 5L: 3,80 €/l \| AOVE 1L: 4,45 €/l \| AOVE spray 200ml: 13,00 €/l \| Girasol: 1,72 - 1,85 €/l.
- **Packaging Parsed:** Paquete (102), Bote (46), Tarro de vidrio (22), Brik (18), Botella (18), Lata (10), Garrafa (6).
- **Alérgenos Declarados:** 145 con alérgenos positivos (gluten: 57, pescado: 26, soja: 21, leche: 19, frutos de cáscara: 16). 200 productos están en estado de API default.
- **Intersección con Cookidoo:** **60 de 345 SKUs (17,4%)** participan en **10.144 menciones en recetas**, liderados por *Aceite de oliva virgen extra Hacendado 1L* (3.468 recetas, 69,4% del total) y *Curry Hacendado* (2.053 recetas, 41,1%).

### 4.3 Rodaja C: Congelados, Vinos, Snacks, Dulces, Desayunos, Platos Preparados
- **Archivo de Trabajo:** `scratch/slice_c.json`
- **Total de Productos:** **404 referencias (25,3% del catálogo)**
- **Distribución de Precios:** Mín: 0,31 € (`Lima`) \| Máx: 23,34 € (`Pulpo crudo congelado 1.3kg`) \| Media: 3,08 € \| Mediana: 2,20 € \| StdDev: 2,61 €
- **Precio Unitario Normalizado por Kilo (€/kg, n=311):**
  - Media: **10,77 €/kg** \| Mediana: **6,37 €/kg** \| Mín: **0,90 €/kg** \| Máx: **205,56 €/kg** (*Edulcorante stevia pastillas 9g* a 1,85 €).
  - Outliers: Eneldo seco (102,78 €/kg), tinta de sepia congelada (85,94 €/kg), foie gras fresco (85,00 €/kg).
- **Precio Unitario Normalizado por Litro (€/l, n=58):**
  - Media: **3,50 €/l** \| Mediana: **2,66 €/l** \| Mín: **0,95 €/l** \| Máx: **13,67 €/l**.
- **Packaging Parsed:** Paquete (172), Tarro (31), Botella (28), Bandeja (26), Bote (24), Caja (18), Brik (13), Tarrina (11).
- **Defecto de Corrupción Detectado:** 29 productos de marisco y pescado congelado presentan la cadena de unidad truncada `"Paquete  kg"`.
- **Alérgenos Declarados:** 135 con alérgenos positivos. Vinos: 23 de 23 (**100%**) declaran sulfitos. Frutos secos: 23 de 26 (**88,5%**) declaran nueces/cacahuetes.
- **Intersección con Cookidoo:** **71 de 404 SKUs (17,6%)** aparecen en **2.150 recetas (43,0%)**, encabezados por *Nuez natural pelada* (565 recetas), *Langostino crudo congelado* (183 recetas) y *Guisante muy tierno ultracongelado* (163 recetas).

---

## 5. AUDITORÍA DE SEGURIDAD ALIMENTARIA & ALÉRGENOS (REGLAMENTO UE 1169/2011)

### 5.1 Falsos Positivos Críticos de Alérgenos (Severidad Alta)
Se detectaron 8 productos con asignaciones de alérgenos erróneas debidas a coincidencia ingenua de subcadenas o metadatos de proveedor corruptos:

1. **Calabaza Cacahuete etiquetada como Cacahuete (Peligro de Alergia Letal):**
   - Productos [`3527`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L3527) (*Calabaza cacahuete cortada a trozos*) y [`69853`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L69853) (*Media calabaza cacahuete*):
   - Etiquetado erróneo: `"Contiene cacahuetes y productos a base de cacahuetes."`
   - *Causa raíz:* La variedad botánica española *Cucurbita moschata* se denomina popularmente *"calabaza cacahuete"* por su forma. Un scraper o pipeline de reglas ingenuo asignó el alérgeno cacahuete a una hortaliza que no contiene ningún fruto seco.
2. **Champiñones Frescos Cultivados etiquetados como Frutos de Cáscara:**
   - Productos [`69664`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L69664) (*Champiñones Portobello*), [`26951`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L26951) (*Champiñones blancos*), [`16618`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L16618) (*Champiñones laminados*) y [`16625`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L16625) (*Champiñón entero*):
   - Etiquetado erróneo: `"Contiene frutos de cáscara."`
   - *Causa raíz:* Hongos frescos sin procesar contaminados en los metadatos con la categoría de frutos de cáscara.
3. **Contradicciones Lógicas Internas:**
   - Producto [`51050`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L51050) (*Mozzarella fresca de vaca Hacendado*): Contiene simultáneamente en la misma cadena: `"Libre de leche y sus derivados (incluida la lactosa)"` y `"Contiene leche y sus derivados (incluida la lactosa)"`.

### 5.2 Falsos Negativos Críticos (Ocultación Involuntaria de Gluten)
En productos ultracongelados empanados, la API oficial omite el alérgeno cereal/trigo:
- [`63170`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L63170) (*Varitas de merluza empanadas Hacendado*): Declara únicamente pescado; **omite gluten y trigo del rebozado**.
- [`63159`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L63159) (*Figuritas de merluza empanadas Hacendado*): Declara únicamente pescado; **omite gluten y trigo**.
- [`63161`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L63161) (*Rabas empanadas Hacendado*): Declara `"Sin alérgenos declarados en la API"`; **omite moluscos y gluten**.
- Harinas de trigo y espelta ([`29019`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L29019), [`29134`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L29134), [`29174`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/data/mercadona_products.json#L29174)): Presentan `"Sin alérgenos declarados en la API"`.

---

## 6. AUDITORÍA DE ÍNDICE DE BÚSQUEDA Y VOCABULARIO DE TOKENS

### 6.1 Frecuencia de Términos (Top Unigramas y Bigramas)
De las 1.595 descripciones de producto se extrajeron los tokens más repetidos:
1. `hacendado`: **968 productos (60,7%)** — Dominancia masiva de la marca propia.
2. `queso`: 121 (7,6%)
3. `pollo`: 87 (5,5%)
4. `pan`: 71 (4,5%)
5. `cerdo`: 65 (4,1%)
6. `leche`: 64 (4,0%)
7. `lonchas`: 64 (4,0%)
8. `aceite`: 47 (2,9%)
9. `sal`: 46 (2,9%)
10. `mezcla`: 45 (2,8%)
11. `ultracongelado`: 37 (2,3%) \| `ultracongelada`: 26 \| `ultracongeladas`: 25 \| `ultracongelados`: 17.

### 6.2 Modos de Fallo en el Motor de Búsqueda
1. **Fragmentación por Flexión Gramatical (Concordancia de Género y Número):**
   - Una búsqueda literal en el front-end por `"ultracongelado"` encuentra solo 54 productos, ignorando los 51 productos rotulados como `"ultracongelada"`, `"ultracongeladas"` o `"ultracongelados"`.
   - *Solución:* Lematizador o stemmer en español (Snowball).
2. **Insensibilidad a Tildes y Caracteres Especiales:**
   - En el catálogo existen **153 palabras distintas con tilde o eñe** (`café`, `salmón`, `bacón`, `champiñón`, `arándanos`, `atún`, `azafrán`).
   - La búsqueda en [`public/app.js`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/public/app.js) utiliza `p.name.toLowerCase().includes(q)`. Si el usuario escribe `"cafe"` o `"salmon"` sin tilde, obtiene 0 resultados.
3. **Lagunas en `PANTRY_KEYWORDS_TO_PRODUCTS` ([`gemini_planner.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/gemini_planner.py)):**
   - La tabla de despensa incluye pasta, arroz, legumbres y huevos, pero **carece de entradas para ingredientes fundamentales de cocina**:
     - *Harina* (0 mapeados; existen `29100`, `29106`, `29019`).
     - *Sal* (0 mapeados; existen `19731`, `16864`).
     - *Pimienta y especias* (0 mapeados; existen `34171`, `5598`, `34102`).
     - *Vinagre* (0 mapeados; existe `4940`).
     - *Caldo de pollo/carne* (0 mapeados; existe `7313`).
     - *Atún en conserva* (0 mapeados; existen `18002`, `18071`).
     - *Levadura* (0 mapeados; existe `87811`).

---

## 7. PLAN DE ACCIÓN Y RECOMENDACIONES ARQUITECTURALES

```
                          PIPELINE DE NORMALIZACIÓN PROPUESTO
+---------------------------------------------------------------------------------------+
| 1. RAW API INGESTION: tienda.mercadona.es/api/products/<id>                           |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| 2. DETERMINISTIC PARSER & REPAIR ENGINE (Regex + Unicode Fold)                        |
|    - Parseo de `unit`: "Paquete 1.0 kg" -> packaging="Paquete", unit_size=1.0, fmt="kg"|
|    - Reparación de los 29 "Paquete  kg" -> extracción de peso neto del packaging      |
|    - Cálculo automático de `unit_price_per_kg` y `unit_price_per_l`                   |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| 3. EU FIC ALLERGEN ASSERTION & SCRUBBING ENGINE                                       |
|    - Limpieza de falsos positivos: Eliminar "cacahuete" de "Calabaza cacahuete"       |
|    - Limpieza de falsos positivos: Eliminar "frutos de cáscara" de setas frescas      |
|    - Inserción de alérgenos obligatorios: Varitas/Rabas empanadas -> assert(gluten)   |
|    - Generación de flags booleanos: `is_gluten_free`, `is_dairy_free`, `is_vegan`     |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| 4. EXPANDED PANTRY & HYBRID SEARCH INDEX                                              |
|    - Actualizar PANTRY_KEYWORDS_TO_PRODUCTS en gemini_planner.py (harina, sal, caldo) |
|    - Índice de búsqueda con Stemming en español y ASCII Folding en app.js y backend   |
|    - Brand downweighting: Tratar "Hacendado" como faceta y no como keyword principal |
+---------------------------------------------------------------------------------------+
```

### 7.1 Implementación Inmediata de Prototipo de Normalización
Se desarrolló y validó en [`scratch/prototype_normalizer.py`](file:///usr/local/google/home/mgandolfi/mercadona-ai-companion/scratch/prototype_normalizer.py) un algoritmo de desestructuración que logró resolver automáticamente el tamaño unitario y el formato para **1.562 de 1.595 productos (97,9% de éxito)** a partir de la cadena compuesta `unit`.

### 7.2 Corrección en `gemini_planner.py`
Se recomienda integrar en el siguiente sprint las palabras clave de despensa identificadas para evitar que el usuario compre innecesariamente sal, harina, vinagre, pimienta o caldo cuando ya indicó que los tiene en casa.

### 7.3 Conclusión de Auditoría
El catálogo de Mercadona y su servicio de integración cuentan con una arquitectura funcional sólida y un rendimiento determinista notable, sustentando el 100% de las 5.000 recetas Cookidoo. La aplicación de este plan de normalización elevará la fidelidad del catálogo al estándar de producción enterprise de Google Cloud.
