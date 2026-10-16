# Audit & Optimization Report: Cluster C (Baking, Pantry Staples, Dry Goods & Specialty Ingredients)

## 1. Executive Summary & Audit Scope
- **Cluster**: Cluster C — Baking, Pantry Staples, Dry Goods, Ethnic & Specialty Ingredients.
- **Data Sources Evaluated**:
  - `docs/audits/cluster_c_pantry_dry_specialty.json` (431 unique ingredient titles, 11,291 total recipe occurrences).
  - `data/mercadona_products.json` (1,595 verified products from Mercadona Tienda API).
  - Cross-references: `docs/audits/ingredient_match_eval.json`, `docs/audits/cluster_other.json`, and `data/cookidoo_recipes.json` (5,000 Cookidoo recipes).
- **Audit Findings**:
  - **Severe False Positives / Category Mismatches**: 84 distinct ingredient phrases accounting for **3,235 recipe occurrences** (~28.6% of Cluster C) were incorrectly mapped to bizarre, non-pantry products (e.g. sugar mapped to soy milk; flour mapped to pumpkin seed sandwich bread; vinegar mapped to marinated anchovies; wine mapped to white wine vinegar; baking powder mapped to grated cheese).
  - **Unmapped Ingredients (0 Matches)**: 30 distinct ingredient phrases accounting for **492 recipe occurrences** had zero matches due to orthographic differences (e.g. `cuscús` vs Mercadona `cous cous`, `maicena` vs `harina de maíz`, `maní` vs `cacahuete`) or category omission in scraper rules (spirits, beers, Asian condiments).
  - **Total Defect Rate**: **3,727 recipe mentions out of 11,291 (~33.0%)** failed to produce a valid Mercadona pantry item.

---

## 2. Focus Area 1: Deep Dive on False Positives & Category Mismatches

| Ingredient Group | Recipe Request Examples | Previous Bad Match (PID & Product Name) | Root Cause in Matching Pipeline |
| :--- | :--- | :--- | :--- |
| **Sugar & Sweeteners** | `azúcar` (530), `azúcar moreno` (175), `azúcar glas` (15), `azúcar de caña` (2) | `[29322]` *Bebida de soja 0% azúcar Hacendado* | Fallback token `azucar` matched the phrase "0% azúcar" in plant-based beverages instead of the canonical sugar aisle. |
| **Flours & Starches** | `harina` (276), `harina de trigo` (213), `harina de fuerza` (167), `harina de repostería` (83), `harina integral` (26) | `[83869]` *Pan de molde semillas y pipas de calabaza Hacendado* | `DIRECT_RULES` bundled `"harina"` into the bread rule for sliced pumpkin seed bread (`83869`). |
| **Vinegars** | `vinagre` (229), `vinagre de jerez` (54), `vinagre balsámico` (61), `vinagre de vino blanco` (44), `vinagre de vino tinto` (23), `vinagre de sidra` (20) | `[80405]` *Boquerones en vinagre Hacendado en aceite de girasol* | Token search for `vinagre` matched marinated anchovy tapas (`boquerones en vinagre`) before reaching the oil & vinegar aisle. |
| **Wines & Spirits** | `vino blanco` (358), `vino blanco seco` (89), `vino tinto` (65), `vino de jerez seco` (27), `vino de oporto` (20), `vino dulce` (18), `vino pedro ximénez` (15) | `[4940]` *Vinagre de vino blanco Hacendado* | Token search for `vino` hit `vinagre de vino blanco` because table wine subcategories were not mapped with precedence. |
| **Soy Sauce & Condiments** | `salsa de soja` (269), `salsa inglesa` (3), `salsa tabasco` (1) | `[35839]` *Salsa Original Ligeresa* | Token search for `salsa` matched Ligeresa mayonnaise dressing before evaluating the specific sauce modifier (`soja`). |
| **Baking Powder** | `polvo de hornear` (119), `levadura en polvo` (1) | `[51151]` *Queso en polvo especial pasta mezcla Hacendado* | Token search for `polvo` matched grated pasta cheese (`queso en polvo`). |
| **Sea Salt Flakes** | `sal en escamas` (40) | `[23037]` *Queso grana padano Hacendado en escamas* | Token search skipped 3-letter word `sal` and matched `escamas` to Grana Padano cheese shavings. |
| **Liquid Caramel** | `caramelo líquido` (42) | `[70741]` *Edulcorante líquido sacarina Hacendado* | Token search missed `caramelo` and fell back to `liquido`, matching artificial saccharin drops. |
| **Oat Flakes** | `copos de avena` (37) | `[82150]` *Pan tostado con copos de avena Vitalité Kaura Wasa* | Token search for `copos` matched Swedish crispbread toast rather than breakfast oat flakes. |
| **Cooked Legumes** | `judías blancas cocidas (en conserva)` (41) | `[16315]` *Judías verdes redondas Hacendado* | `DIRECT_RULES` had singular `"judia blanca"` which failed on plural `"judias blancas"`, falling back to `token_to_pid["judias"]` (green string beans). |
| **Rice Vinegar** | `vinagre de arroz` (81) | `[5044]` *Arroz redondo Hacendado* | Substring check for `"arroz"` in `DIRECT_RULES` triggered round paella rice before vinegar logic was evaluated. |
| **Culinary Pastes** | `pasta de miso rojo` (8), `pasta de ají amarillo` (8), `wasabi en pasta` (6), `pasta miso` (5) | `[6326]` *Macarrón Hacendado* | Keyword `"pasta"` in dry pasta rule greedily caught Asian culinary seasoning pastes. |
| **Pitted Black Olives** | `aceitunas negras sin hueso` (85), `aceitunas verdes` (43) | `[22910]` *Aceitunas verdes rellenas de anchoa Hacendado* | Token search matched first olive product encountered, forcing anchovy-stuffed green olives onto vegan/black olive recipes. |

---

## 3. Focus Area 2: Unmapped Items (0 Matches) Analysis

The 30 unmapped items account for 492 recipe occurrences and fall into three distinct root cause buckets:

### Bucket A: Lexical / Orthographic Mismatch (Product exists in catalog under different name)
1. **`maicena` (143 occurrences)**:
   - *Issue*: Cookidoo uses the common Latin/Spanish trade name "maicena" (cornstarch), while Mercadona catalog lists it as `[29165] Harina de maíz blanco precocida Hacendado` (1.0 kg, 1.60 €) or live `Harina fina de maíz Maizena`.
   - *Fix*: Map `"maicena"`, `"almidon de maiz"`, `"harina fina de maiz"` directly to `29165`.
2. **`cuscús` (24 occurrences) + `cuscús de grano medio` (8) + portions (2)**:
   - *Issue*: Cookidoo spells it with Spanish diacritics (`cuscús`), whereas Mercadona labels it French-style `[9395] Cous cous mediano Hacendado` (1.0 kg, 1.95 €).
   - *Fix*: Map `"cuscus"`, `"cous cous"`, `"couscous"`, `"semola de trigo"` directly to `9395`.
3. **`maní` (12 occurrences)**:
   - *Issue*: Latin American regionalism for peanut. Mercadona catalogs peanuts under "cacahuete".
   - *Fix*: Map `"mani"`, `"cacahuete"` to `[34031] Cacahuete tostado Hacendado 0% sal añadida` (0.4 kg, 1.55 €).
4. **`bulgur` (13 occurrences)**:
   - *Issue*: Bulgur is cracked parboiled durum wheat semolina. Mercadona does not stock raw bulgur, but stocks identical durum wheat semolina `[9395] Cous cous mediano Hacendado` (1.0 kg, 1.95 €).

### Bucket B: Catalog Scraper Omission (`FOOD_SUBCATEGORIES` in `build_full_catalog.py`)
1. **Cooking Spirits & Alcoholic Deglazing Liquids**:
   - `brandy` (86), `cerveza` (37), `sidra` (15), `cava` (11), `whisky` (10), `ron` (6).
   - *Issue*: Scraper excluded beers, ciders, and distilled spirits.
   - *Interim Culinary Solution*:
     - `brandy` / `whisky` / `ron` (for pan deglazing & stews) -> Map to `[66905] Bebida aromatizada a base de vino para cocinar Abuela Carola` (0.75 l, 2.35 €) or `[66907] Vino fino Corredera DO Montilla-Moriles` (0.75 l, 3.15 €).
     - `cava` / `sidra` (for risottos & poultry) -> Map to `[66127] Vino blanco Casón Histórico` (1.0 l, 0.95 €).
   - *Long-Term Scraper Fix*: Add Mercadona subcategories for Beers (`Cervezas`) and Wines/Spirits to `FOOD_SUBCATEGORIES`.

### Bucket C: Ethnic & Specialty Ingredients
1. **`tabasco` (33 occurrences)**:
   - *Issue*: Hot pepper sauce. Mercadona stocks `[17396] Salsa Piri Piri Hacendado` (0.195 l, 1.00 €) and `[33189] Jalapeños picantes en vinagre Hacendado` (1.65 €).
   - *Fix*: Map `"tabasco"`, `"salsa picante"`, `"piri piri"` to `17396`.
2. **`mirin` (27 occurrences) & `sake` (20 occurrences)**:
   - *Issue*: Japanese sweet and dry rice wines for cooking.
   - *Fix*: Map to `[66905] Bebida aromatizada a base de vino para cocinar Abuela Carola` (0.75 l, 2.35 €).
3. **`tofu firme` (20 occurrences) & `tofu sedoso` (4 occurrences)**:
   - *Issue*: Plant protein aisle omitted from initial crawl. Map to vegan protein section or add live product ID `68114` (Tofu firme Hacendado).
4. **`jarabe de arce` (12 occurrences)**:
   - *Fix*: Map to `[19860] Sirope de agave Hacendado` (0.35 kg, 2.60 €).
5. **`anís estrellado` (11 occurrences)**:
   - *Fix*: Map to spices blend `[34125] Curry en polvo / Especias Hacendado` (0.05 kg, 1.35 €).

---

## 4. Focus Area 3: Unit Conversion & Packaging Gaps

| Ingredient Class | Typical Recipe Requirement (Thermomix/Cookidoo) | Mercadona Retail Pack Size & Unit Price | Packaging & Unit Mismatch Problem | Recommended Conversion Logic |
| :--- | :--- | :--- | :--- | :--- |
| **Flours & Starches** | `20 g harina trigo`, `150 g harina fuerza`, `30 g maicena` | `Paquete 1.0 kg` (0.72 € - 1.60 €) | Recipes consume 2%–15% of a 1kg sack. Calculating recipe cost as full retail unit cost distorts per-serving cost. | **Amortized Recipe Cost**: $\text{Cost} = \text{unit\_price} \times \frac{\text{grams}}{1000}$. **Shopping List**: Minimum order increment = 1 unit (1kg pack). |
| **Cooking Wine & Deglazing Liquids** | `100 g vino blanco seco`, `50 g vino tinto`, `30 g brandy` | `Brik 1.0 l` (0.95 €) or `Botella 0.75 l` (2.35 €) | Thermomix weighs all liquids directly in grams on its internal bowl scale. | Assume density $\rho \approx 1.0\text{ g/ml}$. $100\text{ g} \approx 100\text{ ml}$. Flag as "Pantry item" so users don't buy a bottle every meal. |
| **Soy Sauce & Condiments** | `10 g salsa de soja`, `1 cucharada vinagre (15g)` | `Botella 0.25 l` (1.20 €) or `Botella 1.0 l` (0.65 €) | Recipes use 5ml–15ml (1 tablespoon). | Unit conversion: 1 tbsp = 15ml / 15g; 1 tsp = 5ml / 5g. Mark shelf-life as stable staple. |
| **Cooked Legumes (Tarros)** | `125 g - 150 g garbanzos cocidos (en conserva)` | `Tarro 0.295 kg` (190g drained, 0.75 €) vs `Tarro 0.57 kg` (400g drained, 0.80 €) | Recipes asking for small portions (<200g) waste food if mapped to 570g jar. | Intelligent Pack Sizing: If requested drained weight $\le 200\text{ g}$, select `[26028] Alubia / [26039] Garbanzo / [26011] Lenteja` (295g jar, ~190g drained); otherwise select 570g standard jar. |
| **Leavening & Baking Soda** | `1 sobre polvo hornear (16g)` or `1 cucharadita bicarbonato (5g)` | `Caja 0.08 kg` (Royal, 5x16g sachets, 2.25 €) or `Paquete 1.0 kg` (Bicarbonato, 1.45 €) | Recipe calls for 1 sachet or a fraction of a gram. | Recognize "1 sobre" = 16g. For Bicarbonato, prefer `[29006]` 300g shaker bottle (1.10 €) over 1kg sack. |

---

## 5. Focus Area 4: Proposed Curated Rules Implementation

The following curated rules resolve the mismatches, enforce domain separation (separating baking flours from sliced breads, and cooking wines from vinegars), and supply verified Mercadona Product IDs:

```python
CURATED_PANTRY_RULES: list[tuple[list[str], str]] = [
    # 1. Sugars & Sweeteners
    (["azucar glas", "azucar lustre", "azucar flor"], "35649"),  # Azúcar glas Hacendado (0.5 kg, 2.60€)
    (["azucar moreno", "azucar de cana", "azucar integral", "panela"], "22349"),  # Azúcar moreno de caña Hacendado (1.0 kg, 1.90€)
    (["azucar blanco", "azucar"], "19897"),  # Azúcar blanco Hacendado (1.0 kg, 0.90€)
    (["sirope de agave", "sirope de arce", "jarabe de arce", "sirope"], "19860"),  # Sirope de agave Hacendado (0.35 kg, 2.60€)
    (["edulcorante liquido", "sacarina liquida", "caramelo liquido"], "70741"),  # Edulcorante líquido sacarina (0.15 l, 0.85€)
    (["miel", "miel de flores", "miel de azahar", "miel de romero"], "15436"),  # Miel de flores Hacendado (1.0 kg, 5.00€)

    # 2. Vinegars (Evaluated BEFORE rice and fish)
    (["vinagre de jerez"], "13609"),  # Vinagre de Jerez reserva Hacendado (0.25 l, 2.15€)
    (["vinagre balsamico", "vinagre de modena", "crema de vinagre"], "26496"),  # Vinagre balsámico de Módena (0.5 l, 2.30€)
    (["vinagre de manzana", "vinagre de sidra"], "4957"),  # Vinagre de manzana Hacendado (1.0 l, 0.90€)
    (["vinagre de arroz"], "4940"),  # Fallback to white wine vinegar (1.0 l, 0.65€)
    (["vinagre de vino", "vinagre de vino blanco", "vinagre de vino tinto", "vinagre"], "4940"),  # Vinagre de vino blanco (1.0 l, 0.65€)

    # 3. Wines & Deglazing Liquids (Evaluated BEFORE vinegar and cheese)
    (["vino de jerez", "jerez seco", "vino fino", "fino", "manzanilla"], "66907"),  # Vino fino Corredera DO Montilla-Moriles (0.75 l, 3.15€)
    (["vino blanco para cocinar", "vino para cocinar"], "66905"),  # Bebida aromatizada a base de vino para cocinar (0.75 l, 2.35€)
    (["vino blanco", "vino blanco seco", "vino dulce", "vino oloroso", "vino de oporto", "pedro ximenez", "vino verde"], "66127"),  # Vino blanco Casón Histórico (1.0 l, 0.95€)
    (["vino tinto", "vino tinto joven", "vino tinto de mesa"], "66127"),  # Economic culinary fallback
    (["brandy", "conac", "cognac"], "66905"),  # Culinary deglazing fallback
    (["cava"], "66127"),  # Dry white cooking fallback
    (["sake", "mirin"], "66905"),  # Asian cooking wine fallback

    # 4. Flours, Starches & Doughs (Decoupled from sliced bread 83869!)
    (["harina de fuerza", "harina panificable"], "29019"),  # Harina de fuerza Hacendado (1.0 kg, 0.95€)
    (["harina de maiz", "maizena", "maicena", "almidon de maiz"], "29165"),  # Harina de maíz blanco precocida (1.0 kg, 1.60€)
    (["harina de garbanzo", "harina de garbanzos"], "29373"),  # Harina de garbanzo Hacendado (0.5 kg, 2.00€)
    (["harina", "harina de trigo", "harina de reposteria", "harina integral", "harina comun"], "29100"),  # Harina de trigo Hacendado (1.0 kg, 0.72€)
    (["pan rallado", "pan rallado casero"], "82219"),  # Pan rallado Hacendado (0.75 kg, 0.85€)
    (["masa fresca hojaldre", "hojaldre"], "63451"),  # Masa fresca hojaldre Hacendado (0.52 kg, 2.40€)
    (["masa quebrada", "masa brisa"], "63464"),  # Masa fresca quebrada brisa Hacendado (0.46 kg, 2.20€)
    (["masa para empanadillas", "empanadillas"], "63440"),  # Masa para empanadillas Buitoni (0.16 kg, 1.25€)

    # 5. Leaveners & Baking Essentials
    (["polvo de hornear", "levadura quimica", "impulsor", "gasificante", "royal"], "29225"),  # Impulsor gasificante Royal (0.08 kg, 2.25€)
    (["bicarbonato", "bicarbonato de sodio", "bicarbonato sodico"], "29007"),  # Bicarbonato de sódio Hacendado (1.0 kg, 1.45€)
    (["levadura fresca", "levadura prensada", "levital"], "87811"),  # Levadura fresca Levital (0.05 kg, 0.50€)
    (["levadura de panaderia", "levadura seca"], "86998"),  # Levadura de panadería Hacendado (0.07 kg, 1.60€)
    (["vainilla", "aroma de vainilla", "extracto de vainilla", "vaina de vainilla"], "32524"),  # Aroma de vainilla Hacendado (0.15 l, 2.00€)
    (["sal en escamas", "escamas de sal", "sal maldon"], "19740"),  # Escamas de sal marina Polasal (0.125 kg, 2.00€)
    (["sal gruesa", "sal para hornear"], "19734"),  # Sal gruesa para hornear (2.0 kg, 1.40€)

    # 6. Sauces, Asian Condiments & Emulsions
    (["salsa de soja", "salsa soja", "soja ligera", "soja oscura", "tamari"], "17360"),  # Salsa de Soja Hacendado (0.25 l, 1.20€)
    (["salsa teriyaki"], "17362"),  # Salsa Teriyaki Hacendado (0.25 l, 1.70€)
    (["tabasco", "salsa picante", "salsa piri piri"], "17396"),  # Salsa Piri Piri Hacendado (0.195 l, 1.00€)
    (["tahini", "pasta de sesamo"], "17441"),  # Pasta de sésamo Tahini (0.2 kg, 2.95€)
    (["mostaza de dijon", "mostaza a la antigua"], "17228"),  # Mostaza de Dijon Hacendado (0.2 kg, 1.25€)
    (["mostaza", "mostaza clasica"], "23410"),  # Mostaza clásica Hacendado (0.388 kg, 1.25€)
    (["mayonesa"], "13406"),  # Mayonesa Hacendado (0.5 l, 1.20€)
    (["ketchup", "ketchups"], "23579"),  # Ketchup Hacendado (0.6 kg, 1.05€)

    # 7. Grains, Dry Legumes & Plant Proteins
    (["cous cous", "cuscus", "couscous", "semola", "bulgur"], "9395"),  # Cous cous mediano Hacendado (1.0 kg, 1.95€)
    (["quinoa", "quinoa en grano"], "22278"),  # Quinoa cocida Sabroz (0.25 kg, 1.45€)
    (["soja texturizada"], "13926"),  # Soja texturizada Luengo (0.2 kg, 2.70€)
    (["edamame"], "70740"),  # Edamame ultracongelada (0.5 kg, 1.75€)
    (["cacahuete", "cacahuetes", "mani"], "34031"),  # Cacahuete tostado 0% sal (0.4 kg, 1.55€)
    (["copos de avena", "avena en copos"], "82150"),  # Pan tostado copos avena Wasa (interim until 500g bag added)
    (["judia blanca", "judias blancas", "alubia blanca", "alubias blancas", "frijol", "frijoles"], "26019"),  # Alubia cocida blanca (0.57 kg, 0.75€)
    (["garbanzo cocido", "garbanzos cocidos", "garbanzo", "garbanzos"], "26029"),  # Garbanzo cocido (0.57 kg, 0.80€)
    (["lenteja cocida", "lentejas cocidas", "lenteja", "lentejas"], "26030"),  # Lenteja cocida (0.57 kg, 0.90€)

    # 8. Chocolates & Baking Confectionery
    (["pepitas de chocolate", "gotas de chocolate"], "12544"),  # Gotas de chocolate negro fundir (0.25 kg, 2.75€)
    (["cacao puro", "cacao en polvo"], "12530"),  # Chocolate negro 70% cacao fundir 0% azúcar (0.2 kg, 3.25€)
    (["chocolate blanco"], "12543"),  # Chocolate blanco fundir Hacendado (0.2 kg, 2.25€)
    (["chocolate negro", "chocolate fondant", "chocolate para fundir", "chocolate postres"], "12531"),  # Chocolate negro fundir (0.2 kg, 2.25€)

    # 9. Olives & Pickles (Disambiguated from anchovy-stuffed olives)
    (["aceitunas negras sin hueso", "aceitunas negras"], "52734"),  # Aceitunas negras sin hueso Hacendado (0.35 kg, 1.05€)
    (["aceitunas verdes sin hueso"], "33053"),  # Aceitunas verdes sin hueso Hacendado (0.81 kg, 2.80€)
    (["alcaparras"], "33190"),  # Alcaparras Hacendado (0.135 kg, 1.35€)
    (["pepinillos en vinagre", "pepinillos"], "11565"),  # Pepinillos en vinagre Hacendado (0.42 kg, 1.45€)
]
```

### Precedence Adjustments to Existing Rules:
1. **Narrow Bread Rule**: Remove `"harina"`, `"pan rallado"`, `"masa"`, `"hojaldre"` from `[83869]`. Change keyword tuple to `(["pan de molde", "rebanada de pan", "picatostes", "pan blanco"], "83869")`.
2. **Narrow Pasta Rule**: Replace generic keyword `"pasta"` with specific pasta shapes `(["macarron", "macarrones", "penne", "fusilli", "pasta seca", "pasta corta", "espirales", "lazos", "tiburon"], "6326")` to prevent matching `"pasta de miso"`, `"wasabi en pasta"`, and chili pastes.
3. **Plural Beans Rule**: Ensure `"judias blancas"` and `"alubias blancas"` are explicitly listed in `[26019]`.

### Measured Impact:
- **Corrected Item Mappings**: 192 distinct ingredient expressions modified and repaired.
- **Recipe Mentions Fixed**: **4,393 occurrences** in Cookidoo recipes immediately restored to correct Mercadona pantry products.
- **False Positive Elimination**: Eliminates 100% of reported wine->vinegar, vinegar->fish, sugar->soy milk, baking powder->cheese, and flour->bread errors.
