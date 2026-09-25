# Mercadona AI Shopping Companion (Gemini 3.8 Flash × Cookidoo × Mercadona)

Planificador inteligente de menú semanal familiar con look & feel corporativo de **Mercadona**, impulsado por **Google Gemini 3.8 Flash**, integrado con el catálogo oficial de recetas de **Cookidoo (Thermomix)** y con la API en tiempo real de **Mercadona Tienda**.

## Características principales

1. **Planificación semanal por lenguaje natural (Gemini 3.8 Flash)**:
   - Soporta número de días/cenas de la semana, número de componentes de la familia (adultos y niños), límite de presupuesto (€), máximo de calorías por ración (kcal), máximo tiempo de preparación (min), alergias/intolerancias (14 alérgenos UE) e ingredientes que ya tienes en casa (descontados automáticamente de la lista de la compra).
2. **Integración con Cookidoo (`miaucl/cookidoo-api` + JSON-LD oficial)**:
   - Muestra la foto de portada oficial de Cookidoo (`assets.tmecosys.com`), tiempo, calorías y raciones.
   - Botón **"Envía a tu Thermomix"** en cada receta para abrir su ficha oficial en `cookidoo.es` y/o añadirla en un click a la cuenta de Cookidoo del usuario mediante `cookidoo-api`.
3. **Mapping al catálogo en tiempo real de Mercadona (`tienda.mercadona.es/api/`)**:
   - Selección exclusiva de recetas cuyos ingredientes están disponibles en Mercadona.
   - Código postal por defecto **`28016` (Madrid, almacén `mad3`)**, configurable en tiempo real por el usuario desde la cabecera (`PUT /api/postal-codes/actions/change-pc/`).
   - Botón **"Añadir al carrito de Mercadona (1-Click)"**.
4. **Login restringido con Google Identity**:
   - Acceso restringido mediante lista blanca (`ALLOWED_USERS`) a:
     - `matgand@gmail.com`
     - `mgandolfi@google.com`
     - `andrea.anaut@gmail.com`

## Ejecución local

```bash
python3 server.py
# Abre http://localhost:8080
```

## Despliegue automático en Google Cloud Run

```bash
chmod +x deploy.sh
PROJECT_ID="tu-proyecto-gcp" GEMINI_API_KEY="tu-api-key" ./deploy.sh
```
