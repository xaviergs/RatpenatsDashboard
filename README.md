# Ratpenats al Cap de Creus — Dashboard d'Anàlisi Acústica de Ratpenats

Aplicació de visualització i anàlisi de dades acústiques de ratpenats recollides en múltiples localitzacions del Cap de Creus i l'Empordà. Permet explorar l'activitat de les espècies de ratpenats de manera interactiva, tant mitjançant filtres manuals com a través d'un assistent semàntic basat en intel·ligència artificial (Gemini).

---

## 🗂️ Estructura del Projecte

```
Ratpenats/
├── app.py                  # Aplicació principal de Streamlit (UI i lògica de pestanyes)
├── ai_helper.py            # Mòdul d'integració amb Gemini (anàlisi semàntica + gràfics)
├── semantic_model.json     # Model semàntic: sinònims, localitzacions, regles de la IA
├── requirements.txt        # Dependències Python del projecte
├── Dockerfile              # Definició del contenidor per a Google Cloud Run
├── .env                    # Variables d'entorn locals (NO pujeu al repositori)
├── .env.example            # Plantilla de variables d'entorn per a nous entorns
└── .devcontainer/          # Configuració de Dev Container per a VS Code
```

---

## ⚙️ Variables d'Entorn (`.env`)

| Variable        | Descripció                                                            |
|-----------------|-----------------------------------------------------------------------|
| `SUPABASE_URL`  | URL del projecte Supabase                                             |
| `SUPABASE_KEY`  | Clau `anon` del projecte Supabase                                     |
| `GEMINI_API_KEY`| Clau d'API de Google AI Studio per al model de IA Gemini              |
| `GEMINI_MODEL`  | (opcional) Model de Gemini a usar. Per defecte: `gemini-2.5-pro`    |

> ⚠️ **Mai pujeu el fitxer `.env` al repositori.** Feu servir `.env.example` com a plantilla.

---

## 🗃️ Base de Dades (Supabase / PostgreSQL)

L'aplicació es connecta a un projecte **Supabase** i consulta principalment la vista:

### Vista principal: `bat_observations_full`

Cada fila representa un interval d'observació acústica. Columnes principals:

| Columna            | Tipus    | Descripció                                                               |
|--------------------|----------|--------------------------------------------------------------------------|
| `species`          | text     | Espècie identificada automàticament (nom científic)                      |
| `location_name`    | text     | Nom del lloc de mostreig (`display_name` de la taula `locations`)        |
| `observation_date` | date     | Data de l'observació                                                     |
| `observation_hour` | integer  | Franja horària (0–23)                                                    |
| `total_count`      | numeric  | Comptatge de contactes acústics totals                                   |
| `total_buzz`       | numeric  | Comptatge de "feeding buzzes" (acció de caça)                            |
| `temp`             | numeric  | Temperatura ambiental associada                                          |
| `rel_humidity`     | numeric  | Humitat relativa associada                                               |
| `wind_speed`       | numeric  | Velocitat del vent associada                                             |

### Altres taules consultades

- `file_registry`, `locations`, `weather_metrics`, `weather_observations_history`, `weather_stations`, `days_by_location` (per als indicadors de la pestanya Estatus).

---

## 🐍 Mòduls Python

### `app.py`
Aplicació principal de Streamlit. Estructura en 4 pestanyes:

| Pestanya             | Descripció                                                               |
|----------------------|--------------------------------------------------------------------------|
| 🚀 **Accions**       | Gràfics interactius estàtics amb filtres manuals (espècie, localització, dates, mètriques, tipus de gràfic). Inclou anàlisi de regressió lineal. |
| 📊 **Estatus**       | Mètriques de salut de la base de dades, comptadors de registres, xarxa d'estacions meteorològiques. |
| 📖 **Syllabus**      | Documentació tècnica interna: diccionari de dades, fórmules dels índexs ecològics, metodologia de l'esforç de mostreig. |
| 💬 **Anàlisi Semàntica** | Xat-bot impulssat per Gemini + panell de visualització híbrid (filtres auto-emplenats per la IA, retocables manualment). |

### `ai_helper.py`
Mòdul de suport per a la integració de Gemini. Conté:

- **`init_gemini_client()`**: Inicialitza el client de l'API de Gemini des de la variable d'entorn `GEMINI_API_KEY`.
- **`analyze_query_with_llm(user_query, chat_history, df_full)`**: Envia la consulta de l'usuari a Gemini amb un *system prompt* ric que inclou:
  - El contingut complet de `semantic_model.json` (sinònims, regles, mètriques).
  - Les metadades reals del DataFrame (llista d'espècies, localitzacions i rang de dates).
  - Força la resposta en format JSON estructurat (`response_schema`) mitjançant **Pydantic**.
  - Té un mecanisme de *fallback* automàtic a models alternatius (`gemini-2.5-flash`, `gemini-2.5-pro`) en cas d'error de quota o model no disponible.
- **`apply_filters_and_generate_chart(df, analysis)`**: Filtra el DataFrame de forma segura (sense `eval` ni `exec`) i genera un gràfic interactiu amb **Altair** ajustat a la mètrica i l'eix X demanats.

### `semantic_model.json`
Fitxer de configuració JSON que actua com a **model semàntic** per a la IA. Conté:

- **`locations_catalogue`**: Totes les localitzacions del projecte agrupades per zona geogràfica (Cap de Creus-Roses, Espolla, Aiguamolls, Muga), amb els noms de la BD i els sinònims en català.
- **`locations_synonyms_flat`**: Mapejat pla de sinònim → nom exacte a la BD per facilitar la traducció de consultes col·loquials.
- **`species_synonyms`**: Noms comuns i genèrics de ratpenats → nom científic de la BD.
- **`metrics_explanation`**: Definició tècnica de cada mètrica (total_count, total_buzz, OA, OT, IA) amb les paraules clau associades.
- **`x_axis_rules`**: Indicació de quan usar cada agrupació de l'eix X.
- **`semantic_rules`**: Regles de comportament que guien la IA: com tractar termes ambigus, el format de dates, la priorització dels noms exactes de la BD, etc.

> 💡 **Per afegir noves localitzacions o espècies**: Editeu `semantic_model.json` directament, sense tocar el codi Python. La IA el llegirà en cada petició.

---

## 📦 Dependències (`requirements.txt`)

| Llibreria            | Versió  | Ús                                          |
|----------------------|---------|---------------------------------------------|
| `streamlit`          | latest  | Framework de la interfície d'usuari web      |
| `supabase`           | latest  | Client de la base de dades Supabase          |
| `pandas`             | latest  | Processament i filtratge de dades tabulars   |
| `python-dotenv`      | latest  | Càrrega de variables d'entorn des de `.env`  |
| `google-generativeai`| latest  | SDK de Google Gemini per a la IA             |
| `pydantic`           | latest  | Validació d'esquemes JSON estructurats       |

> Altair s'instal·la automàticament com a dependència de Streamlit.

---

## 🚀 Posada en Marxa Local

```bash
# 1. Clonar el repositori i accedir al directori
cd "c:/Test and experiments/Antigravity/Ratpenats"

# 2. Crear i activar l'entorn virtual
python -m venv venv
venv\Scripts\activate   # Windows

# 3. Instal·lar dependències
pip install -r requirements.txt

# 4. Configurar variables d'entorn
copy .env.example .env
# Editar .env i afegir SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY

# 5. Executar l'aplicació
venv\Scripts\python -m streamlit run app.py
```

L'aplicació estarà disponible a `http://localhost:8501`.

---

## ☁️ Desplegament a Google Cloud Run

L'aplicació és compatible amb Google Cloud Run. El `Dockerfile` inclòs configura el servidor de Streamlit per escoltar al port `$PORT` que defineix Cloud Run.

Variables d'entorn necessàries en producció: `SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY` (i opcionalment `GEMINI_MODEL`).

---

## 📊 Índexs Ecològics

| Índex | Fórmula                        | Interpretació                                         |
|-------|--------------------------------|-------------------------------------------------------|
| **OA** | `total_count / N`             | Grau d'ús acústic general de l'hàbitat per unitat d'esforç |
| **OT** | `total_buzz / N`              | Grau d'activitat de caceria per unitat d'esforç        |
| **IA** | `total_buzz / total_count`    | Proporció d'activitat de caça sobre l'activitat total  |

On `N = hores úniques de sessió × 60` (esforç de mostreig normalitzat per minuts).
