# Mercadona AI Companion — Slice C Deep Product Audit
**Focus:** Frozen Goods, Beverages, Snacks & Sweets, Breakfast, Prepared Foods, Special Diets, and Unassigned Residuals  
**Dataset:** `/usr/local/google/home/mgandolfi/mercadona-ai-companion/scratch/slice_c.json`  
**Total Products:** 404  
**Date:** September 2026  
**Auditor:** Subagent C  

---

## Executive Summary

Slice C represents a diverse, high-utility segment of the Mercadona catalog (404 products out of the 1,595 catalog snapshot, or 25.3%). It comprises critical staples for convenience cooking, freezer management, baking, aperitifs, and quick weeknight meals. 

This audit uncovered major insights and critical data-engineering defects:
1. **Severe Field Omission:** 94.1% of products (380/404) lack explicit `categories`, `ingredients`, `packaging`, and `size_format` fields. 66.6% (269/404) fall back to the default string `"Sin alérgenos declarados en la API"`.
2. **Taxonomy Spillover:** 121 products (30.0%) in Slice C are residual items from Slice A (fresh meats, charcuterie, produce, seafood) and Slice B (pantry, pasta, pickles, spices) that fell through the slicing regexes due to stem mismatches (e.g. `panes` vs `pan\b`, `burger` vs `hamburguesa`, `bacón` with accent vs `bacon`, `allioli` with double-l vs `alioli`, and missing categories like aceitunas/encurtidos).
3. **Missing Product Families in Catalog Snapshot:** Beers (`cerveza`), mineral waters (`agua mineral`), and carbonated soft drinks (`refresco`, `cola`) have **0 products** in the underlying 1,595 Mercadona catalog snapshot. The token `cola` in initial filters matched seafood tails (`colas de gambón`, `cola de rape`), chocolates, and `ColaCao`.
4. **Unit String Malformations:** 29 frozen seafood products have corrupted unit strings (`"Paquete  kg"`, `"Pieza  kg"`, `"Bandeja  kg"`) with blank weights, caused by catch-weight API fields stripped during scraping.
5. **Critical Allergen False Negatives:** Breaded frozen fish items (`Varitas de merluza empanadas`, `Figuritas de merluza empanadas`, `Rabas empanadas`) omit gluten/cereals from their API allergen strings despite containing wheat breadcrumbs. Conversely, 100% (23/23) of true white and fortified wines declare sulphites correctly.
6. **High Cookidoo Impact:** While only 17.6% (71/404) of Slice C products are referenced in Cookidoo, those 71 products power **2,139 out of 5,000 Cookidoo recipes (42.8%)**, driven by staple items like walnuts (`Nuez natural pelada`, 565 recipes), frozen prawns (`Langostino crudo`, 183 recipes), and frozen peas (`Guisante muy tierno`, 163 recipes).

---

## 1. Category Coverage & Taxonomy Balance

### 1.1 Granular Subcategory Distribution

| Subcategory | Product Count | Share (%) | Primary Typical Products |
| :--- | :---: | :---: | :--- |
| **Frozen: Fish & Shellfish** | 94 | 23.3% | Merluza del Cabo, Gambón, Langostino, Calamar, Sepia, Salmón salvaje |
| **Frozen: Vegetables, Rice & Sides** | 34 | 8.4% | Guisantes tiernos, Habas baby, Arroz 3 delicias, Salteado setas |
| **Frozen: Meat & Poultry** | 8 | 2.0% | Alitas de pollo, Jamoncitos, Brochetas Yakitori congeladas |
| **Frozen: Prepared Bases & Meals** | 3 | 0.7% | Preparado de paella y sopa, Lasaña boloñesa ultracongelada |
| **Beverages: Wine & Fortified** | 27 | 6.7% | Vino blanco (Rueda, Rioja, Albariño), Vino fino, Pedro Ximénez |
| **Beverages: Coffee, Tea & Infusions** | 17 | 4.2% | Café molido/cápsulas, Té verde, Manzanilla, Menta poleo |
| **Beverages: Dairy/Juice/Plant Drinks** | 6 | 1.5% | Bebida láctea Puleva Max, Bebida de almendras, Horchata |
| **Beverages: Beer & Soft Drinks** | 0 | 0.0% | *Missing from scraped snapshot* |
| **Snacks: Nuts & Dried Fruits** | 23 | 5.7% | Nuez pelada, Almendras fritas, Anacardos, Pistachos, Frutos secos |
| **Snacks: Crackers & Chips** | 4 | 1.0% | Mini biscotes, Crackers integrales, Torrezno precocinado |
| **Sweets & Desserts** | 4 | 1.0% | Postre lácteo azucarado sin lactosa, Bombones/Gelatinas |
| **Breakfast & Spreads** | 9 | 2.2% | Miel de flores, Muesli, Dulce de membrillo, Papilla de fruta |
| **Prepared Meals & Dips (Chilled)** | 35 | 8.7% | Tortillas de trigo, Wraps Texas, Piadina, Hummus, Guacamole, Pisto |
| **Plant-Based & Special Diets** | 3 | 0.7% | Tofu firme, Edamame soja verde, Margarina 100% vegetal |
| **Misc Spillover: Fresh Meat & Charcuterie** | 28 | 6.9% | Burger americana, Magret pato, Guanciale, Bacón lonchas, Maxi york |
| **Misc Spillover: Pickles, Olives & Pantry** | 93 | 23.0% | Aceitunas Chupadedos/Gazpacha, Pepinillos, Banderillas, Especias, Panes |
| **Misc Spillover: Fresh Produce & Seafood** | 16 | 4.0% | Lima, Batata, Endibias, Ostra viva, Navaja viva, Bacaladilla |
| **Total** | **404** | **100.0%** | |

### 1.2 Taxonomy Spillover Root Causes
A significant portion of Slice C (137 items, 33.9%) consists of unassigned items from Slices A and B:
1. **Charcuterie & Meats (Slice A spillover):** Products using English loanwords (`Burger americana gruesas`, `Burger Crunchy Chicken`), accented forms (`Bacón Hacendado cintas`, `Bacón Oscar Mayer`), cured meats (`Maxi york`, `Lacón al horno`, `Guanciale`, `Torrezno`), game poultry (`Codornices`, `Magret de pato`, `Gallina`), and soup bones (`Hueso garrón`, `Arreglo para cocido`).
2. **Fresh Produce & Shellfish (Slice A spillover):** Root tubers and salad items (`Batata`, `Yuca`, `Rabanitos`, `Endibias`, `Escarola rizada`, `Lima`, `Maíz dulce en mazorca`); live shellfish (`Navaja viva`, `Ostra viva`).
3. **Pickles, Olives & Condiments (Slice B spillover):** 20+ varieties of Spanish aperitivo encurtidos (`Aceitunas verdes Chupadedos`, `Aceitunas Gazpacha`, `Pepinillos agridulces`, `Banderillas`, `Piparras`, `Altramuces`, `Alcaparras`).
4. **Bakery & Bread (Slice A spillover):** Plural forms missed by regex word boundaries: `Panes chapata de cristal`, `Panes pulguitas`, `Panes molletes`, `Bocadillos`.
5. **Baking & Pastry Doughs (Slice B spillover):** `Masa fresca hojaldre`, `Masa fresca quebrada`, `Masa filo`, `Gelatina neutra`, `Azúcar moreno`, `Panela`, `Azúcar glas`.
6. **Sauces & Emulsions (Slice B spillover):** Catalan/Valencian spelling `Allioli` (double 'l') was not matched by `alioli` (single 'l') in `pat_b`.

---

## 2. Price Distribution & Unit Price Economics

### 2.1 Overall Pack Price Statistics (n=404)
* **Minimum Price:** 0.31 € (`Lima`, Pieza 0.07 kg)
* **Maximum Price:** 23.34 € (`Pulpo crudo congelado Hacendado`, Paquete 1.3 kg)
* **Mean Price:** 3.08 €
* **Median Price:** 2.20 €
* **Standard Deviation:** 2.61 €
* **Price Quartiles:** Q1 = 1.45 €, Q2 (Median) = 2.20 €, Q3 = 3.80 €

#### Top 5 Most Economical Items
1. `Lima`: 0.31 € (Pieza 0.07 kg)
2. `Bocadillo`: 0.45 € (Pieza 0.13 kg)
3. `Impulsor gasificante repostería Hacendado`: 0.70 € (Caja 0.09 kg)
4. `Mini biscotes de trigo Hacendado`: 0.76 € (Caja 0.12 kg)
5. `Hélices Hacendado`: 0.80 € (Paquete 0.5 kg)

#### Top 5 Premium / High-Ticket Items
1. `Pulpo crudo Hacendado congelado`: 23.34 € (1.3 kg pack)
2. `Gambón grande congelado`: 22.00 € (2.0 kg box)
3. `Bogavante americano crudo Hacendado ultracongelado`: 17.13 € (Pieza / unit)
4. `Filetes de merluza grandes del Cabo sin piel`: 13.25 € (Bulk frozen pack)
5. `Preparado lácteo con cereales Peques 3 Puleva`: 12.00 € (Pack 6x1.0 L)

---

### 2.2 Standardized Unit Price Analysis (per kg / per Liter)

| Metric | Overall (per kg) | Overall (per Liter) | Frozen Fish & Shellfish | Wines & Fortified | Nuts & Frutos Secos | Ready Meals & Dips |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Sample Size (n)** | 311 parsed | 58 parsed | 39 parsed kg | 25 parsed L | 22 parsed kg | 33 parsed kg |
| **Mean** | 10.77 €/kg | 3.50 €/L | 13.17 €/kg | 4.05 €/L | 11.47 €/kg | 10.06 €/kg |
| **Median** | 6.37 €/kg | 2.66 €/L | 11.35 €/kg | 3.33 €/L | 12.25 €/kg | 6.86 €/kg |
| **Min** | 0.90 €/kg | 0.95 €/L | 3.80 €/kg | 0.95 €/L | 5.20 €/kg | 1.00 €/kg |
| **Max** | 205.56 €/kg | 13.67 €/L | 27.59 €/kg | 9.07 €/L | 29.50 €/kg | 68.97 €/kg |
| **Std Dev** | 16.77 €/kg | 2.58 €/L | 6.70 €/kg | 2.21 €/L | 5.95 €/kg | 13.64 €/kg |

#### Unit Price Outlier Analysis
* **205.56 €/kg:** `Edulcorante en pastillas stevia Hacendado` (1.85 € for 9 grams). Highly concentrated tabletop sweetener.
* **102.78 €/kg:** `Eneldo Hacendado` (1.85 € for 18 grams). Dried herb shaker jar.
* **85.94 €/kg:** `Tinta de sepia Nortindal congelada` (2.75 € for 32 grams). Concentrated culinary squid ink.
* **85.00 €/kg:** `Foie gras de pato fresco` (6.80 € for 80 grams). Luxury fresh poultry liver.
* **68.97 €/kg:** `Preparado en polvo gelatina frutos rojos 0%` (2.00 € for 29 grams). Dehydrated gelatin dessert mix.
* **Wine per Liter Range:** From 0.95 €/L (`Vino blanco Don Simón` brik 1L) to 9.07 €/L (`Vino dulce Pedro Ximénez Panda Verdia DO Málaga` 0.75L bottle at 6.80 €).

---

## 3. Metadata Consistency & Packaging Quality

### 3.1 Field Omission Audit

| Field | Populated Records | Missing / Default Records | Omission Rate (%) | Severity |
| :--- | :---: | :---: | :---: | :--- |
| `id` | 404 | 0 | 0.0% | Optimal |
| `name` | 404 | 0 | 0.0% | Optimal |
| `unit_price` | 404 | 0 | 0.0% | Optimal |
| `unit` (string) | 404 | 0 | 0.0% | Optimal |
| `thumbnail` | 404 | 0 | 0.0% | Optimal |
| `share_url` | 404 | 0 | 0.0% | Optimal |
| `available` | 380 | 24 | 5.9% | Low |
| `warehouse` | 380 | 24 | 5.9% | Low |
| `allergens` (real) | 135 | 269 | **66.6%** | **High** |
| `categories` | 24 | 380 | **94.1%** | **Critical** |
| `ingredients` | 24 | 380 | **94.1%** | **Critical** |
| `packaging` (field) | 24 | 380 | **94.1%** | **Critical** |
| `size_format` | 24 | 380 | **94.1%** | **Critical** |
| `unit_size` | 20 | 384 | **95.0%** | **Critical** |

### 3.2 Packaging Formats (Extracted from `unit` string vs explicit field)
While the structured `packaging` field is only populated for 24 items (Paquete: 13, Caja: 7, Bandeja: 2, Bote: 1, Pieza: 1), parsing the `unit` string yields rich packaging typology across all 404 products:
* **Paquete (Pouch/Pillow pack):** 172 products (42.6%) — predominantly frozen fish, frozen veggies, dried fruits, flour, pastas.
* **Tarro (Glass Jar):** 31 products (7.7%) — pickles, olives, capers, canned vegetables.
* **Botella (Glass/PET Bottle):** 28 products (6.9%) — wines, syrups, spirits, liquid sweeteners.
* **Bandeja (Tray/Punit):** 26 products (6.4%) — chilled meats, prepared vegetables, chilled surimi.
* **Bote (Tub/Shaker):** 24 products (5.9%) — spices, sugar glas, table olives, nuts.
* **Caja (Cardboard Box):** 18 products (4.5%) — crackers, frozen prawns, sugar cubes, baking aids.
* **Pieza (Individual Piece/Weight item):** 15 products (3.7%) — whole frozen fish, lime, fresh melon, baguettes.
* **Brik (Tetra Brik carton):** 13 products (3.2%) — cooking wines, pisto, broths, almond milks.
* **Tarrina (Plastic Tub):** 11 products (2.7%) — margarines, allioli dips, dulce de membrillo.
* **Pack-3 / Pack-2 (Multipacks):** 10 products (2.5%) — bechamel, canned tuna/squid, canned peas.
* **Bolsa (Bag):** 8 products (2.0%) — artisan breads, crystal buns.
* **Bare Decimal / Format without packaging word:** 38 products (9.4%) — e.g. `"0.13 kg"`, `"1.0 kg"`.

### 3.3 Corrupted Unit String Defect (29 Frozen Seafood Products)
Twenty-nine products in Slice C have a missing numeric quantity between the packaging type and the weight symbol:
* `62048`: `"Preparado de paella y sopa Hacendado ultracongelado"` -> `"Paquete  kg"`
* `24181`: `"Gamba pelada cruda tamaño mediano Hacendado ultracongelada"` -> `"Paquete  kg"`
* `24477`: `"Langostino cocido y pelado Hacendado ultracongelado"` -> `"Bandeja  kg"`
* `62380`: `"Bogavante americano crudo Hacendado ultracongelado"` -> `"Pieza  kg"`
* `62228`: `"Filetes de merluza del Cabo sin piel Hacendado ultracongelados"` -> `"Paquete  kg"`
* `24340`: `"Cola de rape del Cabo sin piel Hacendado ultracongelada"` -> `"Pieza  kg"`
* `24249`: `"Anillas de pota Argentina Hacendado congeladas"` -> `"Paquete  kg"`
* `26760`: `"Filetes de merluza grandes del Cabo sin piel Hacendado ultracongelados"` -> `"Paquete  kg"`

**Root Cause:** In the Mercadona e-commerce backend, catch-weight or variable-weight frozen items often store weight in an `approx_size` or `variable_weight_unit` attribute. The initial scraping script read a template string formatted as `{packaging} {weight_value} {weight_unit}`, but when `weight_value` was null/empty, it collapsed to `"Paquete  kg"`.

---

## 4. Allergen Tagging & Food Safety Audit

Under Regulation (EU) No 1169/2011 (FIC), 14 allergens must be declared clearly on prepacked food. The audit revealed distinct compliance profiles across subcategories:

### 4.1 Sulphites in Wines & Cavas
* **Total True Wines:** 23 products.
* **Declaring Sulphites:** 23 out of 23 (**100.0%**).
* **Tagging string:** `"Contiene dióxido de azufre y sulfitos."`
* **Finding:** Wine allergen compliance is flawless across all white wines, sweet wines, and fortified wines (`DO Rueda`, `DO Rioja`, `DO Rías Baixas`, `DO Somontano`, `DO Montilla-Moriles`).
* Non-alcoholic wine alternatives (e.g. `Bebida refrescante aromatizada tinto sin alcohol light Castillo de Salobreña`) and grape juice (`Mosto tinto Casón Histórico`) have `"Sin alérgenos declarados en la API"`.

### 4.2 Tree Nuts & Peanuts in Snacks
* **Total Nut Products:** 26 products.
* **Declaring Nut Allergens:** 23 out of 26 (**88.5%**).
* **Compliance breakdown:**
  * Whole nuts (`Almendra natural`, `Nuez natural`, `Anacardo frito`, `Pistacho`, `Nuez de Brasil`, `Nuez Pecana`): Declare `"Contiene frutos de cáscara."`
  * Peanuts (`Cacahuete frito con piel`, `Cacahuete con miel`, `Cacahuete en polvo desgrasado`): Declare `"Contiene cacahuetes y productos a base de cacahuetes."`
  * Sunflower seeds (`Pipas de girasol peladas`, `Pipas barbacoa`): Declare `"Sin alérgenos declarados en la API"`. (Botanically seeds, not tree nuts; compliant unless cross-contamination is declared).
* **API Data Corruption Notice:** Product `34024` (`Nuez natural Hacendado pelada`) contains a truncated string typo from upstream:  
  `"Contiene sw. Puede contener cacahuetes y productos a base de cacahuetes. Puede contener frutos de cáscara."` (Where `"sw"` appears to be a corrupted token).

### 4.3 Gluten & Dairy in Ready Meals, Pizzas & Breaded Items (Critical Safety Gaps)
* **Gluten in Prepared Foods:** 10 of 18 ready-meal items explicitly declare gluten.
* **Dairy in Prepared Foods:** Only 2 items declare milk/lactose (`Lasaña boloñesa familiar` and `Lasaña a la boloñesa`).
* **CRITICAL SAFETY FALSE NEGATIVES IN BREADED PRODUCTS:**
  1. `63170`: `"Varitas de merluza empanadas Hacendado ultracongeladas"`:
     * Current API string: `"Contiene pescado y productos a base de pescado."`
     * **Missing:** **Gluten / Cereales con gluten (Trigo)**. This is a breaded fish stick formulated with wheat flour and breadcrumbs.
  2. `63159`: `"Figuritas de merluza empanadas Hacendado ultracongeladas"`:
     * Current API string: `"Contiene pescado y productos a base de pescado."`
     * **Missing:** **Gluten / Trigo**.
  3. `63161`: `"Rabas empanadas Hacendado ultracongeladas"`:
     * Current API string: `"Sin alérgenos declarados en la API"`!
     * **Missing:** **Moluscos** (calamar/pota) AND **Gluten** (empanado).
  4. `86820`: `"Relleno fajitas pollo, pimientos y cebolla Hacendado ultracongelado"`:
     * Current API string: `"Sin alérgenos declarados en la API"`.

### 4.4 Vegan / Vegetarian & Plant-Based Labeling Clarity
* Only 3 products represent dedicated vegan proteins/substitutes:
  * `70740`: `Edamame soja verde Hacendado ultracongelada` (Declares `"Contiene soja"`).
  * `20196`: `Margarina 100% vegetal Hacendado` (Declares `"Sin alérgenos declarados en la API"`).
  * `23925` / `23926` / `15647`: `Bebida de almendras 0% azúcar Hacendado` (Declares `"Contiene frutos de cáscara"`).
* **Gap:** None of these products feature structured dietary flags (`is_vegan: true`, `is_vegetarian: true`, `is_celiac_safe: true`). Users on specialized plant-based or celiac diets currently have to inspect ingredient strings manually or rely on heuristic keyword matching.

---

## 5. Search Tokens & Discoverability Audit

### 5.1 Token Frequency Analysis (n=404 products)

```
Top 20 Unigram Tokens in Product Names:
 1. hacendado           : 291 products (72.0%)  <-- Extreme private label dominance
 2. ultracongelado      :  37 products ( 9.2%)  <-- Grammatical masculine singular
 3. ultracongelada      :  26 products ( 6.4%)  <-- Grammatical feminine singular
 4. ultracongeladas     :  25 products ( 6.2%)  <-- Grammatical feminine plural
 5. vino                :  23 products ( 5.7%)
 6. preparado           :  21 products ( 5.2%)
 7. blanco              :  21 products ( 5.2%)
 8. ultracongelados     :  17 products ( 4.2%)  <-- Grammatical masculine plural
 9. do                  :  16 products ( 4.0%)  <-- Denominación de Origen
10. aceitunas           :  15 products ( 3.7%)
11. merluza             :  14 products ( 3.5%)
12. verduras            :  14 products ( 3.5%)
13. natural             :  12 products ( 3.0%)
14. congelado           :  12 products ( 3.0%)
15. verdes              :  12 products ( 3.0%)
16. hueso               :  11 products ( 2.7%)
17. piel                :  10 products ( 2.5%)
18. maíz                :  10 products ( 2.5%)
19. bebida              :  10 products ( 2.5%)
20. cocido              :   9 products ( 2.2%)
```

### 5.2 Top Bigrams
1. `hacendado ultracongelado` (34)
2. `hacendado ultracongelada` (26)
3. `hacendado ultracongeladas` (23)
4. `vino blanco` (19)
5. `hacendado ultracongelados` (17)
6. `aceitunas verdes` (11)
7. `hacendado congelado` (10)
8. `verduras hacendado` (10)
9. `merluza cabo` (6)
10. `frutos secos` (6)

### 5.3 Search Discoverability Failure Modes
1. **Inflection Fragmentation (`ultracongelad*`):**
   * There are 105 total products with a variation of `ultracongelad*`.
   * A literal search for `"ultracongelado"` matches only 54 items (37 masculine singular + some bigrams), completely hiding 26 feminine singular (`ultracongelada`), 25 feminine plural (`ultracongeladas`), and 17 masculine plural (`ultracongelados`) items!
   * *Required fix:* Spanish Snowball stemmer or dictionary lemmatizer normalizing to `ultracongelad`.
2. **Diacritic & Accent Inflexibility:**
   * A query for unaccented `"cafe"` yields **0 matches**, whereas `"café"` yields 7 matches.
   * A query for `"bacon"` misses the accented items (`Bacón Hacendado cintas`).
   * *Required fix:* Full Unicode NFD decomposition and ASCII folding (`cafe` matches `café`, `salmon` matches `salmón`).
3. **Substring Token Collisions:**
   * Searching for `cola` matched `colas de rape` (monkfish tails), `colas de gambón` (prawn tails), and `chocolate`.
   * *Required fix:* Strict word-boundary tokenization with part-of-speech context.
4. **Brand Bias:**
   * With 72.0% of products carrying `Hacendado`, querying `hacendado` adds zero discriminative value and pollutes TF-IDF scores unless downweighted via a domain-specific stopword list or dedicated brand facet.

---

## 6. Integration with Cookidoo & Meal Planner

### 6.1 Cross-Reference Metrics
* **Total Products in Slice C:** 404
* **Products referenced in Cookidoo (`product_ids`):** **71 products (17.6%)**
* **Total Cookidoo Recipes:** 5,000
* **Cookidoo Recipes utilizing Slice C products:** **2,139 recipes (42.8%)**

This proves that while only a sixth of Slice C items are mapped to Cookidoo IDs, those items represent high-frequency culinary building blocks that appear in nearly half of all Thermomix / Cookidoo recipes!

### 6.2 Top 15 High-Frequency Cookidoo Anchor Products

| Product ID | Product Name | Cookidoo Recipe Count | Primary Culinary Role |
| :---: | :--- | :---: | :--- |
| `34024` | `Nuez natural Hacendado pelada` | **565** | Baking, pesto, salad topping, desserts |
| `24712` | `Langostino crudo Hacendado ultracongelado` | **183** | Paellas, rice dishes, seafood stews, bisque |
| `61200` | `Guisante muy tierno Hacendado ultracongelado` | **163** | Side dishes, menestras, tortillas, sautés |
| `35240` | `Miel de flores Hacendado` | **152** | Glazes, marinades, salad dressings, baking |
| `62396` | `Carne de mejillón cocido Hacendado ultracongelado` | **149** | Seafood pasta, empanada fillings, fideuás |
| `24350` | `Filete de salmón rosado salvaje con piel ultracongelado` | **133** | Varoma steamed fish, baked salmon, purées |
| `62401` | `Mejillón de Chile entero cocido Hacendado ultracongelado` | **121** | Steamed mussels, fisherman rices, broths |
| `62113` | `Lomos y centros de merluza del Cabo Hacendado` | **119** | Salsa verde, steamed fillets, children's meals |
| `26775` | `Chipirones enharinados Hacendado ultracongelado` | **112** | Tapas, quick fried seafood, paella toppings |
| `24016` | `Filetes de bacalao MareDeus ultracongelado` | **99** | Bacalao al pil-pil, brandada, fish soups |
| `52739` | `Eneldo Hacendado` | **67** | Herb butter, salmon seasoning, creamy sauces |
| `33190` | `Alcaparras Hacendado` | **55** | Tartar sauce, vitello tonnato, pasta puttanesca |
| `69463` | `Preparado de verduras para sofreír cortado y lavado` | **48** | Sofrito base, vegetable soups, batch cooking |
| `80859` | `Tortillas de trigo Hacendado` | **41** | Fajitas, wraps, quick weeknight dinners |
| `35650` | `Edulcorante líquido sacarina Hacendado` | **41** | Low-calorie desserts, beverage sweetening |

### 6.3 Meal Planner Categorization & Utility
1. **Quick Weeknight Dinners (< 20 mins):**
   * `Tortillas de trigo` (id 80859) + `Relleno fajitas pollo` (id 86820) + `Guacamole/Hummus`.
   * `Chipirones enharinados` (id 26775) + `Allioli Chovi` (id 17150).
   * `Lasaña a la boloñesa` (id 86597) / `Canelones de carne` (id 86600) (oven or microwave ready).
2. **Healthy Side Dishes & Vegetable Bases:**
   * `Guisante muy tierno ultracongelado` (id 61200) sautéed with jamón or poached eggs.
   * `Salteado de verduras para microondas` (id 69463) steamed in 5 minutes.
   * `Risotto de setas para microondas` (id 22720) as an instant carb/mushroom side.
3. **Batch Cooking & Freezer Meal Prep:**
   * 1 kg packs of `Langostinos`, `Porciones de merluza`, and `Filetes de bacalao` allow multi-portion meal prepping without spoilage.
   * `Preparado de paella y sopa` (id 62048) serves as a concentrated broth base for weekend batch rice dishes.

### 6.4 Unmapped Opportunities (333 unreferenced items)
* **Wines for Deglazing:** None of the 23 white wines in Slice C are mapped to Cookidoo ingredient IDs, despite hundreds of recipes specifying `vino blanco seco` or `vino de Jerez`.
* **56 Unmapped Frozen Seafood Items:** Specialty items like `Bogavante americano` (id 62380), `Calamar patagónico` (id 63432), and `Sepia limpia` (id 24200) are missing direct recipe links.
* **Ready Dips & Tapas:** `Aceitunas Chupadedos` and `Mix de encurtidos` can be integrated as suggested automated aperitivo pairings for weekend menus.

---

## 7. Architectural Recommendations

```
+-----------------------------------------------------------------------------------+
|                        MERCADONA CATALOG ENRICHMENT ENGINE                        |
+-----------------------------------------------------------------------------------+
                                          |
            +-----------------------------+-----------------------------+
            |                                                           |
            v                                                           v
+-----------------------+                                   +-----------------------+
|  Deterministic Regex  |                                   |  Gemini Flash / LLM   |
|   & Catalog Rules     |                                   |  Structured Extractor |
+-----------------------+                                   +-----------------------+
            | (Fast match 85%)                                          | (Edge cases 15%)
            +-----------------------------+-----------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                           CANONICAL PRODUCT MODEL                                 |
| - category_l1: Sector (Congelados, Bebidas, Despensa, Platos Preparados)          |
| - category_l2: Subcategoría (Pescado, Verduras, Vino Blanco, Encurtidos)         |
| - package_format: Normalized (Bolsa, Botella, Tarrina, Caja, Brik)                |
| - weight_net_g / volume_net_ml: Parsed numeric floats                             |
| - unit_price_standardized: €/kg or €/L calculated deterministically               |
+-----------------------------------------------------------------------------------+
            |                                                           |
            v                                                           v
+---------------------------------------+   +---------------------------------------+
|    EU FIC 1169/2011 ALLERGEN RULES    |   |     HYBRID SEARCH / VECTOR INDEX      |
| - Empanado -> assert(gluten, trigo)   |   | - Accent folding (NFD + ASCII)        |
| - Vino/Cava -> assert(sulfitos)       |   | - Spanish Snowball stemmer            |
| - Fruto seco -> assert(cáscara)       |   | - Brand demotion (Hacendado 72%)      |
| - Pescado/Molusco -> assert(marino)   |   | - Gemini text-embedding-004 vectors   |
+---------------------------------------+   +---------------------------------------+
```

### 7.1 Automated Category Classification Pipeline
1. **Three-Tier Hierarchical Taxonomy:**
   * `Level 1 (Sector)`: Congelados | Bebidas | Aperitivos y Snacks | Platos Preparados | Despensa | Frescos.
   * `Level 2 (Family)`: Pescado y Marisco | Verduras y Salteados | Vinos | Aceitunas y Encurtidos | Frutos Secos | Panadería.
   * `Level 3 (Segment)`: Filetes sin piel | Langostinos enteros | Vino Blanco Rueda | Nueces peladas.
2. **Fixing Spillover Ingestion:**
   * Expand slicing dictionary to include missing categories: `aceituna*`, `encurtido*`, `pepinillo*`, `banderilla*`, `piparra*` -> map to Despensa/Aperitivos.
   * Add plural token handling: `panes` -> Panadería; `burgers` -> Carne fresca; `bacón` -> Charcutería.
   * Add dialectal spellings: `allioli` and `alioli` -> Salsas.
3. **Catch-Weight Unit String Repair:**
   * For the 29 corrupted items (`"Paquete  kg"`), query the Mercadona catalog API field `approx_size` or default to the standard retail net weight (e.g. 400g for merluza medallions, 800g for langostinos) to restore accurate €/kg price analytics.

### 7.2 Food Safety & Allergen Validation Engine
1. **Deterministic EU FIC Allergen Assertion Layer:**
   * Build a ruleset that cross-checks title tokens against declared allergens:
     * If `name` matches `empanad*|varitas|figuritas|rabas|rebozad*` -> enforce `gluten` and `trigo`.
     * If `name` matches `vino|cava|mosto fermentado` -> enforce `dióxido de azufre y sulfitos`.
     * If `name` matches `almendra|nuez|pistacho|avellana|anacardo` -> enforce `frutos de cáscara`.
     * If `name` matches `cacahuete` -> enforce `cacahuetes`.
2. **Data Sanitization & Typo Scrubbing:**
   * Replace corrupted upstream strings like `"Contiene sw."` with standardized EU allergen codes (`FIC_NUTS`, `FIC_PEANUTS`).
3. **Dietary Attribute Flags:**
   * Generate explicit boolean flags (`is_gluten_free`, `is_vegan`, `is_vegetarian`, `is_dairy_free`, `is_alcohol_free`) to empower meal planning filters for dietary restrictions.

### 7.3 Search Index Optimization
1. **Stemming & Lemmatization:**
   * Implement Spanish Snowball stemming in the search indexing pipeline so that `ultracongelado`, `ultracongelada`, `ultracongelados`, and `ultracongeladas` index to the root stem `ultracongelad`.
2. **Diacritic & Accent Invariance:**
   * Standardize all tokens to lowercase ASCII unfolded text: `café` -> `cafe`, `salmón` -> `salmon`, `bacón` -> `bacon`, `cacao` -> `cacao`.
3. **Private Label Normalization:**
   * Treat `Hacendado` as an optional brand attribute rather than a heavy TF-IDF keyword. Strip `Hacendado` during natural-language recipe matching so queries like "comprar merluza congelada" match `Lomos de merluza Hacendado ultracongelados` with full relevance.
4. **Recipe-to-Product Semantic Embedding:**
   * Map Cookidoo ingredient strings (e.g. `"150 g de nueces peladas"`, `"1 chorrito de vino blanco seco"`) directly to Mercadona product embeddings using `text-embedding-004` cosine similarity, achieving automated, frictionless 1-click cart fulfillment.
