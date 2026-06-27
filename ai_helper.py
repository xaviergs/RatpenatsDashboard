import os
import json
import pandas as pd
import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import List, Optional
import altair as alt

def _get_secret(key: str) -> str | None:
    """
    Reads a secret from st.secrets (Streamlit Cloud) if available,
    otherwise falls back to os.environ (local .env via load_dotenv).
    """
    try:
        import streamlit as st
        return st.secrets.get(key)
    except Exception:
        return os.environ.get(key)

# Define the Pydantic schema for Gemini Structured Output
class QueryAnalysisSchema(BaseModel):
    explanation: str = Field(
        description="Explicació molt curta en català de quins filtres i mètrica s'apliquen al gràfic segons la petició de l'usuari."
    )
    # FIX: Tots els camps Optional ara tenen default=None explícit dins de Field()
    # per evitar l'error "Unknown field for Schema: default" de la llibreria google-generativeai
    filter_species: Optional[List[str]] = Field(
        default=None,
        description="Llista d'espècies exactes a filtrar. Buidor o nul si es refereix a totes o no s'especifica cap."
    )
    filter_locations: Optional[List[str]] = Field(
        default=None,
        description="Llista de localitzacions exactes a filtrar. Buidor o nul si es refereix a totes o no s'especifica cap."
    )
    filter_start_date: Optional[str] = Field(
        default=None,
        description="Data d'inici en format YYYY-MM-DD. Nul si no s'especifica."
    )
    filter_end_date: Optional[str] = Field(
        default=None,
        description="Data final en format YYYY-MM-DD. Nul si no s'especifica."
    )
    metric: str = Field(
        description="Mètrica demanada pel gràfic: 'total_count' (Comptatge), 'total_buzz' (Buzz), 'OA' (Ocupació Acústica), 'OT' (Ocupació Tròfica), 'IA' (Intensitat Depredadora), 'temp' (Temperatura), 'rel_humidity' (Humitat), 'wind_speed' (Vent), 'percip_mm' (Precipitació)."
    )
    x_axis: str = Field(
        description="Eix X desitjat pel gràfic: 'species' (Espècie), 'location_name' (Localització), 'observation_date' (Data), 'month_year' (Mes i any), 'observation_hour' (Franja horària)."
    )
    chart_type: str = Field(
        description="Tipus de gràfic a dibuixar: 'barres' (gràfic de barres), 'línies' (gràfic de línies), 'dispersió' (gràfic de dispersió), o 'cap' (si l'usuari només fa una pregunta sense demanar gràfic)."
    )
    chart_recommendation_reason: str = Field(
        description="Justificació breu en català de per què s'ha escollit aquest tipus de gràfic. Explica la lògica de la visualització en funció de la intenció de l'usuari i la naturalesa de les dades (ex: 'Gràfic de barres perquè comparem múltiples espècies en una data específica', 'Gràfic de línies per mostrar l'evolució temporal de l'activitat', etc.)."
    )
    conversational_answer: Optional[str] = Field(
        default=None,
        description="Si l'usuari fa una pregunta concreta (ex: 'quina espècie caça més?'), redacta una resposta explicativa en català usant les dades analitzades. Si és només una petició de gràfic, aquest camp pot ser breu."
    )
    # FIX: secondary_metric i use_dual_axis ara usen Field() amb default explícit
    secondary_metric: Optional[str] = Field(
        default=None,
        description="Segona mètrica per al eix Y secundari (dret) en gràfics de doble eix. Nul si no s'aplica dual axis."
    )
    use_dual_axis: bool = Field(
        default=False,
        description="Si és True, el gràfic tindrà dos eixos Y independents per comparar dues mètriques amb escales diferents."
    )
    color_by: Optional[str] = Field(
        default=None,
        description="Dimensió per la qual desglossar el color/llegenda del gràfic: 'species', 'location_name', o None (sense desglossament per color). Posa None si use_dual_axis és True o si l'usuari vol un únic agregat net."
    )
    aggregation: str = Field(
        default="auto",
        description="Mètode d'agregació de la mètrica: 'sum' (recomanat per total_count i total_buzz), 'mean' (recomanat per temp, rel_humidity, wind_speed, percip_mm), 'max', 'min', o 'auto' (dedueix automàticament segons la mètrica)."
    )
    filter_hours: Optional[List[int]] = Field(
        default=None,
        description="Llista d'hores (0-23) a incloure al filtre. Nul si l'usuari no especifica cap franja horària. Exemple: de 21h a 23h seria [21, 22, 23]."
    )
    top_n: Optional[int] = Field(
        default=None,
        description="Si l'usuari demana un rànquing o les 'top N' categories (ex: 'les 5 espècies amb més activitat'), indica el nombre N. Nul si no es demana cap rànquing limitat."
    )

def init_gemini_client():
    """
    Initializes the Gemini API client.
    Reads GEMINI_API_KEY from st.secrets (Streamlit Cloud) or os.environ (local .env).
    """
    api_key = _get_secret("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("No s'ha trobat la clau GEMINI_API_KEY. Afegeix-la a Streamlit Secrets o al fitxer .env local.")
    genai.configure(api_key=api_key)


def _extract_response_text(response) -> str:
    """
    Safely extract the text payload from a Gemini response.
    Raises a descriptive error if the model returned no usable candidate
    (e.g. blocked by safety filters or empty output), instead of letting
    the bare `response.text` accessor raise an opaque exception.
    """
    # Detect prompt-level blocking first.
    feedback = getattr(response, "prompt_feedback", None)
    block_reason = getattr(feedback, "block_reason", None) if feedback else None
    if block_reason:
        raise ValueError(f"La petició ha estat bloquejada per Gemini (motiu: {block_reason}).")

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise ValueError("Gemini no ha retornat cap resposta. Torna-ho a provar o reformula la consulta.")

    # Reconstruct text from candidate parts when available.
    try:
        return response.text
    except Exception:
        parts_text = []
        for cand in candidates:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", []) or []:
                txt = getattr(part, "text", None)
                if txt:
                    parts_text.append(txt)
        if not parts_text:
            raise ValueError("Gemini ha retornat una resposta buida o sense text utilitzable.")
        return "".join(parts_text)


def analyze_query_with_llm(user_query: str, chat_history: list, df_full: pd.DataFrame) -> QueryAnalysisSchema:
    """
    Calls Gemini using structured outputs to parse the user's natural language query
    into filters and chart parameters.
    """
    init_gemini_client()
    
    # Get metadata from the DataFrame to insert into the system instructions
    if df_full.empty:
        raise ValueError("El DataFrame de dades està buit. No es pot realitzar l'anàlisi.")
        
    unique_species = sorted(df_full['species'].dropna().unique().tolist())
    unique_locations = sorted(df_full['location_name'].dropna().unique().tolist())
    min_date = df_full['observation_date'].min()
    max_date = df_full['observation_date'].max()
    
    # Load semantic model config dynamically
    semantic_config_str = ""
    try:
        config_path = os.path.join(os.path.dirname(__file__), "semantic_model.json")
        with open(config_path, "r", encoding="utf-8") as f:
            semantic_config = json.load(f)
            semantic_config_str = json.dumps(semantic_config, indent=2, ensure_ascii=False)
    except Exception as e:
        semantic_config_str = f"No s'ha pogut carregar el fitxer semantic_model.json: {str(e)}"
    
    # Structure system instructions to guide Gemini precisely
    system_instruction = f"""
Ets un assistent analista de dades expert en ratpenats al Cap de Creus.
El teu objectiu és analitzar la petició de l'usuari en llenguatge natural i mapejar-la a filtres i paràmetres de gràfic exactes contra el nostre DataFrame de dades.
A més, has de raonar sobre quina és la visualització més adequada per a cada consulta i justificar la teva elecció.

MODEL SEMÀNTIC DE REFERÈNCIA, REGLES DE TRADUCCIÓ I DICCIONARI DE SINÒNIMS:
{semantic_config_str}

El DataFrame de dades ('bat_observations_full') té les següents columnes rellevants:
- 'species': Espècie de ratpenat.
- 'location_name': Nom de la localització del detector acústic.
- 'observation_date': Data de l'observació (YYYY-MM-DD).
- 'observation_hour': Hora de la sessió de gravació (valor de 0 a 23).
- 'total_count': Comptatge o nombre de contactes acústics registrats.
- 'total_buzz': Nombre de 'feeding buzzes' (indicador estricte d'activitat de caça/alimentació).
- 'temp': Temperatura.
- 'rel_humidity': Humitat relativa.
- 'wind_speed': Velocitat del vent.

METADADES REALS DEL DATASET (IMPORTANT: Mapeja els sinònims del model semàntic a aquests valors exactes per als filtres):
- Espècies disponibles: {unique_species}
- Localitzacions disponibles: {unique_locations}
- Rang de dates reals: des de {min_date} fins a {max_date}

GUIA PER A LA SELECCIÓ DEL TIPUS DE GRÀFIC:
- Utilitza 'barres' quan vulguis comparar valors discrets o categories (ex: espècies, localitzacions, hores específiques). Ideals per a comparacions directes entre grups.
- Utilitza 'línies' quan vulguis mostrar l'evolució o tendència al llarg del temps (ex: activitat diària, evolució mensual, patrons horaris en seqüència).
- Utilitza 'dispersió' quan vulguis explorar relacions entre dues variables contínues o detectar patrons/correlacions (ex: temperatura vs. comptatge).
- Utilitza 'cap' quan l'usuari només fa una pregunta sense demanar explícitament un gràfic. En aquest cas, proporciona la resposta conversacional.

INSTRUCCIONS PER A DUAL AXIS (DOS EIXOS Y):
- Si l'usuari demana comparar dues mètriques diferents en el MATEIX gràfic (ex: 'mostra temperatura i comptatge junts', 'compara ocupació acústica amb humitat'), utilitza:
  * use_dual_axis = true
  * metric = la PRIMERA mètrica (eix Y primari, esquerra)
  * secondary_metric = la SEGONA mètrica (eix Y secundari, dreta)
  * chart_type = 'línies' (és l'opció més adequada per a dual axis)
- Si el gràfic és dual axis, els dos eixos seran independents (escales diferents), ideal per comparar variables amb unitats o magnituds molt distintes.
- Exemple: Si l'usuari diu 'fes un gràfic de temperatura i comptatge al llarg del temps', retorna:
  * metric = 'temp'
  * secondary_metric = 'total_count'
  * use_dual_axis = true
  * chart_type = 'línies'

PER AL CAMP 'chart_recommendation_reason':
- Explica breument (en català) per què aquest tipus de gràfic és el millor per a la petició de l'usuari.
- Exemple 1: "Gràfic de barres perquè comparem l'activitat de 3 espècies en la mateixa data."
- Exemple 2: "Gràfic de línies per visualitzar l'evolució temporal de l'ocupació acústica al llarg de 6 mesos."
- Exemple 3: "Cap visualització, ja que la pregunta és analítica (demana el recompte total) en lloc de descriptiva."

INSTRUCCIONS DE SEGURETAT I FORMAT:
1. Has de retornar un JSON que s'ajusti estrictament a l'esquema sol·licitat.
2. Si l'usuari demana filtrar per una espècie o lloc en català (noms comuns), utilitza el diccionari de sinònims per traduir-ho als noms de les metadades reals. Si no coincideix amb cap espècie coneguda, deixa la llista buida.
3. Redacta la 'conversational_answer', l'explanation i la 'chart_recommendation_reason' en català de forma clara, professional i concisa.
4. Si l'usuari et fa una pregunta sobre el context de la conversa, utilitza l'historial del xat que et passem.
5. El camp 'chart_recommendation_reason' ha de ser sempre una justificació vàlida i meaningful de la visualització triada, inclús quan chart_type='cap'.

RAONAMENT PAS A PAS (segueix aquest ordre mental abans de generar el JSON):
1. Quantes mètriques vol veure l'usuari? Si en vol DUES de naturalesa diferent (ex: una biològica i una meteorològica) → use_dual_axis=true, metric=primera, secondary_metric=segona. Si en vol UNA → use_dual_axis=false, secondary_metric=null.
2. Vol comparar entre categories o veure una evolució? Decideix x_axis i chart_type segons x_axis_rules (barres per comparar categories, línies per evolució temporal, dispersió per correlacions).
3. Vol desglossar per una categoria addicional (espècie o lloc) amb colors? Aplica color_rules per decidir color_by. RECORDA: color_by és per categories, dual axis és per mètriques. MAI els dos alhora.
4. Com s'ha d'agregar la mètrica? Aplica aggregation_rules (sum per comptatges, mean per meteorologia/índexs, 'auto' si dubtes).
5. Demana un rànquing limitat ('top N')? Aplica top_n_rules. Acota una franja horària? Aplica hour_filter_rules (filter_hours).
6. Hi ha filtres explícits d'espècie, lloc o dates? Omple'ls; si no, deixa'ls null (= tots).
Consulta sempre les seccions dual_axis_rules, color_rules, aggregation_rules, top_n_rules, hour_filter_rules i few_shot_examples del MODEL SEMÀNTIC abans de respondre.
"""

    # Use model from environment variable or default to gemini-2.5-pro
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")

    # Shared generation config: enforce JSON output against the Pydantic schema
    # and use a low temperature for stable, deterministic structured parsing.
    generation_config = {
        "response_mime_type": "application/json",
        "response_schema": QueryAnalysisSchema,
        "temperature": 0.1,
    }
    
    # Prepare chat conversation structure for the model
    # Convert past history into Content objects for Google Generative AI
    contents = []
    for msg in chat_history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [msg["content"]]})
        
    # Append the current query
    contents.append({"role": "user", "parts": [user_query]})
    
    # Initialize the model with system instructions and JSON output constraint
    try:
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction,
            generation_config=generation_config
        )
        response = model.generate_content(contents)
    except Exception as primary_error:
        # Check if it is a rate limit, quota, or model access error
        error_msg = str(primary_error).lower()
        is_quota_or_model_error = any(kw in error_msg for kw in ["429", "quota", "limit", "blocked", "not found", "not enabled"])

        if is_quota_or_model_error:
            # FIX: Seqüència de fallback amb noms de model vàlids i actuals.
            fallback_models = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"]
            last_error = primary_error
            for fallback_model in fallback_models:
                if fallback_model == model_name:
                    continue
                try:
                    model = genai.GenerativeModel(
                        model_name=fallback_model,
                        system_instruction=system_instruction,
                        generation_config=generation_config
                    )
                    response = model.generate_content(contents)
                    break  # Si ha funcionat, sortim del bucle
                except Exception as fallback_error:
                    last_error = fallback_error
                    continue
            else:
                raise last_error
        else:
            raise primary_error

    # Parse the response back into the Pydantic schema
    try:
        data = json.loads(_extract_response_text(response))
        normalized_data = _normalize_analysis(data)
        return QueryAnalysisSchema(**normalized_data)
    except Exception as e:
        # Fallback in case of parse error
        return _fallback_analysis(e)

def _normalize_bool(value) -> bool:
    """Normalize common boolean-like values from LLM JSON responses."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "sí", "si"}
    return bool(value)


def _normalize_analysis(data: dict) -> dict:
    """Normalize LLM response fields before building Pydantic model."""
    normalized = dict(data)

    # Valid columns/values to guard against LLM hallucinations.
    valid_metrics = {
        "total_count", "total_buzz", "OA", "OT", "IA",
        "temp", "rel_humidity", "wind_speed", "percip_mm"
    }
    valid_dimensions = {"species", "location_name"}
    valid_aggregations = {"sum", "mean", "max", "min", "auto"}

    # Ensure optional fields exist and use safe defaults.
    normalized.setdefault("secondary_metric", None)
    normalized["use_dual_axis"] = _normalize_bool(normalized.get("use_dual_axis", False))

    # If use_dual_axis is true but secondary_metric is missing or identical, disable dual axis.
    if normalized["use_dual_axis"] and not normalized.get("secondary_metric"):
        normalized["use_dual_axis"] = False
    if normalized["use_dual_axis"] and normalized.get("secondary_metric") == normalized.get("metric"):
        normalized["use_dual_axis"] = False
        normalized["secondary_metric"] = None

    # Validate secondary_metric is a known metric, else drop it.
    if normalized.get("secondary_metric") not in valid_metrics:
        normalized["secondary_metric"] = None
        if normalized["use_dual_axis"]:
            normalized["use_dual_axis"] = False

    # Normalize color_by: only valid dimensions, and never when dual axis is active.
    color_by = normalized.get("color_by")
    if color_by not in valid_dimensions:
        color_by = None
    if normalized["use_dual_axis"]:
        color_by = None
    # Avoid redundant color when it duplicates the X axis dimension.
    if color_by is not None and color_by == normalized.get("x_axis"):
        color_by = None
    normalized["color_by"] = color_by

    # Normalize aggregation method.
    aggregation = normalized.get("aggregation", "auto")
    if not isinstance(aggregation, str) or aggregation.strip().lower() not in valid_aggregations:
        aggregation = "auto"
    normalized["aggregation"] = aggregation.strip().lower()

    # Normalize filter_hours: keep only valid integers in 0-23.
    raw_hours = normalized.get("filter_hours")
    if isinstance(raw_hours, list) and raw_hours:
        clean_hours = []
        for h in raw_hours:
            try:
                hv = int(h)
            except (TypeError, ValueError):
                continue
            if 0 <= hv <= 23:
                clean_hours.append(hv)
        normalized["filter_hours"] = sorted(set(clean_hours)) or None
    else:
        normalized["filter_hours"] = None

    # Normalize top_n: positive integer or None.
    raw_top_n = normalized.get("top_n")
    try:
        top_n = int(raw_top_n) if raw_top_n is not None else None
    except (TypeError, ValueError):
        top_n = None
    if top_n is not None and top_n <= 0:
        top_n = None
    normalized["top_n"] = top_n

    return normalized


def _fallback_analysis(error: Exception) -> QueryAnalysisSchema:
    return QueryAnalysisSchema(
        explanation="Error al processar la petició de la intel·ligència artificial.",
        metric="total_count",
        x_axis="species",
        chart_type="cap",
        chart_recommendation_reason="No s'ha pogut generar una recomanació de visualització degut a un error al processar la consulta.",
        conversational_answer=f"Ho sento, hi ha hagut un problema interpretant la resposta: {str(error)}. Si us plau, torna-ho a provar."
    )


def calculate_indices_for_df(df_target, df_unfiltered, group_cols, weather_agg: str = "mean"):
    """
    Calculates sampling effort and ecological indices for a grouped dataframe.
    Exactly identical to calculations in the main app to maintain dashboard consistency.

    weather_agg controls how meteorological metrics (temp, rel_humidity, wind_speed,
    percip_mm) are aggregated ('mean', 'max', 'min'). Counts are always summed because
    the ecological indices (OA, OT, IA) depend on summed totals.
    """
    if df_target.empty:
        return pd.DataFrame()

    if weather_agg not in ("mean", "max", "min"):
        weather_agg = "mean"

    # Aggregate counts and meteorological metrics per grouping
    agg_dict = {
        "total_count": "sum",
        "total_buzz": "sum",
        "temp": weather_agg,
        "rel_humidity": weather_agg,
        "percip_mm": weather_agg,
        "wind_speed": weather_agg
    }
    # Use only columns present in the DataFrame to avoid KeyError
    available_agg = {k: v for k, v in agg_dict.items() if k in df_target.columns}
    df_grouped = df_target.groupby(group_cols, as_index=False).agg(available_agg).reset_index(drop=True)

    
    # Sampling effort N: unique hours (observation_date + observation_hour + location_name) * 60
    df_unfiltered_copy = df_unfiltered.copy()
    df_unfiltered_copy['session_hour_key'] = (
        df_unfiltered_copy['observation_date'].astype(str) + "_" + 
        df_unfiltered_copy['observation_hour'].astype(str) + "_" + 
        df_unfiltered_copy['location_name']
    )
    
    # Effort grouping: exclude species from group columns
    # Exclude 'species', temporal grouping column 'month_year', and temporary hour column 'hora' from effort calculation to avoid KeyError
    eff_group_cols = [c for c in group_cols if c not in ('species', 'month_year', 'hora')]
    
    if eff_group_cols:
        effort_per_group = df_unfiltered_copy.groupby(eff_group_cols)['session_hour_key'].nunique().reset_index(name='total_hours')
    else:
        total_h = df_unfiltered_copy['session_hour_key'].nunique()
        effort_per_group = pd.DataFrame({'total_hours': [total_h]})
        
    effort_per_group['N'] = effort_per_group['total_hours'] * 60
    effort_per_group.loc[effort_per_group['N'] == 0, 'N'] = 1
    
    if eff_group_cols:
        df_grouped = pd.merge(df_grouped, effort_per_group, on=eff_group_cols, how='left')
    else:
        df_grouped['N'] = effort_per_group['N'].iloc[0]
        
    df_grouped['N'] = df_grouped['N'].fillna(1)
    
    df_grouped['OA'] = df_grouped['total_count'] / df_grouped['N']
    df_grouped['OT'] = df_grouped['total_buzz'] / df_grouped['N']
    df_grouped['IA'] = df_grouped.apply(
        lambda row: row['total_buzz'] / row['total_count'] if row['total_count'] > 0 else 0.0, axis=1
    )
    
    return df_grouped

# Default visual style for generated charts. Any subset can be overridden via the
# `chart_style` argument of apply_filters_and_generate_chart so the user can fully
# customise the look & feel from the UI without touching the analysis logic.
DEFAULT_CHART_STYLE = {
    "height": 420,
    "color_scheme": "tableau10",   # Altair categorical color scheme for the legend
    "primary_color": "#1f77b4",    # Single-series color when there is no color breakdown
    "secondary_color": "#ff7f0e",  # Secondary metric color on dual-axis charts
    "opacity": 0.85,               # Mark opacity (0.1 - 1.0)
    "show_points": True,           # Show markers on line/scatter charts
    "show_grid": True,             # Show Y axis gridlines
    "log_scale": False,            # Use a logarithmic scale on the Y axis
    "interactive": True,           # Enable pan & zoom interactions
    "label_angle": -45,            # X axis label rotation for categorical axes
    "point_size": 80,              # Marker size for scatter charts
}


def _resolve_chart_style(chart_style: dict | None) -> dict:
    """Merge a user-provided style dict over the defaults, ignoring None values."""
    style = dict(DEFAULT_CHART_STYLE)
    if chart_style:
        for key, value in chart_style.items():
            if key in style and value is not None:
                style[key] = value
    return style


def apply_filters_and_generate_chart(df: pd.DataFrame, analysis: QueryAnalysisSchema, chart_style: dict | None = None):
    """
    Applies filters specified by the QueryAnalysisSchema and creates an Altair chart
    suitable for the active dashboard panel.

    chart_style is an optional dict of visual overrides (see DEFAULT_CHART_STYLE)
    that lets the user customise colors, height, scale, opacity and interactivity.
    """
    style = _resolve_chart_style(chart_style)

    if df.empty:
        return pd.DataFrame(), None, "Sense dades disponibles."
        
    df_filtered = df.copy()
    
    # Keep track of active filters applied in text
    active_filters_txt = []
    
    # 1. Apply Species Filter
    if analysis.filter_species:
        df_filtered = df_filtered[df_filtered['species'].isin(analysis.filter_species)]
        active_filters_txt.append(f"Espècies: {', '.join(analysis.filter_species)}")
    else:
        active_filters_txt.append("Espècies: Totes")
        
    # 2. Apply Location Filter
    if analysis.filter_locations:
        df_filtered = df_filtered[df_filtered['location_name'].isin(analysis.filter_locations)]
        active_filters_txt.append(f"Localitzacions: {', '.join(analysis.filter_locations)}")
    else:
        active_filters_txt.append("Localitzacions: Totes")
        
    # 3. Apply Dates Filter
    if analysis.filter_start_date:
        try:
            start_date = pd.to_datetime(analysis.filter_start_date).date()
            df_filtered = df_filtered[df_filtered['observation_date'] >= start_date]
            active_filters_txt.append(f"Des de: {analysis.filter_start_date}")
        except Exception:
            pass
            
    if analysis.filter_end_date:
        try:
            end_date = pd.to_datetime(analysis.filter_end_date).date()
            df_filtered = df_filtered[df_filtered['observation_date'] <= end_date]
            active_filters_txt.append(f"Fins a: {analysis.filter_end_date}")
        except Exception:
            pass

    # 3b. Apply Hour Filter
    if getattr(analysis, "filter_hours", None):
        valid_hours = [h for h in analysis.filter_hours if isinstance(h, int) and 0 <= h <= 23]
        if valid_hours and 'observation_hour' in df_filtered.columns:
            df_filtered = df_filtered[df_filtered['observation_hour'].isin(valid_hours)]
            active_filters_txt.append(f"Hores: {', '.join(str(h) + 'h' for h in valid_hours)}")

    # 4. If resulting df is empty, return early
    if df_filtered.empty:
        return pd.DataFrame(), None, "Cap registre no coincideix amb els filtres indicats pel xat-bot."
        
    # Prepare dimensions
    metric_col = analysis.metric
    metric_label = {
        "total_count": "Comptatge Total",
        "total_buzz": "Total Feeding Buzz",
        "OA": "Ocupació Acústica (OA)",
        "OT": "Ocupació Tròfica (OT)",
        "IA": "Intensitat Depredadora (IA)",
        "temp": "Temperatura (°C)",
        "rel_humidity": "Humitat Relativa (%)",
        "percip_mm": "Precipitació (mm)",
        "wind_speed": "Velocitat del Vent (m/s)"
    }.get(metric_col, metric_col)
    
    x_col = analysis.x_axis
    x_label = {
        "species": "Espècie",
        "location_name": "Localització",
        "observation_date": "Data",
        "month_year": "Mes - Any",
        "observation_hour": "Franja Horària (h)"
    }.get(x_col, x_col)
    
    # 5. Temporal groupings preprocessing if needed
    if x_col == 'month_year':
        df_filtered['obs_dt'] = pd.to_datetime(df_filtered['observation_date'])
        df_filtered['month_year'] = df_filtered['obs_dt'].dt.to_period('M').dt.to_timestamp()
    elif x_col == 'observation_hour':
        df_filtered['hora'] = df_filtered['observation_hour'].astype(str).str.zfill(2)
        x_col = 'hora'
        
    # 6. Group and calculate indices
    grouping_cols = [x_col]
    # Determine color/legend dimension. Prefer the explicit color_by from the LLM;
    # otherwise fall back to a heuristic that splits by the non-X categorical dimension.
    color_col = None
    if not (analysis.use_dual_axis and analysis.secondary_metric):
        explicit_color = getattr(analysis, "color_by", None)
        if explicit_color in ('species', 'location_name') and explicit_color != x_col:
            color_col = explicit_color
        elif explicit_color is None:
            # Heuristic fallback when the LLM did not specify a color dimension.
            if x_col != 'species' and (not analysis.filter_species or len(analysis.filter_species) > 1):
                color_col = 'species'
            elif x_col != 'location_name' and (not analysis.filter_locations or len(analysis.filter_locations) > 1):
                color_col = 'location_name'
        if color_col and color_col not in grouping_cols:
            grouping_cols.append(color_col)

    # Resolve aggregation method for weather metrics (counts are always summed).
    weather_agg = "mean"
    requested_agg = getattr(analysis, "aggregation", "auto") or "auto"
    if requested_agg in ("max", "min"):
        weather_agg = requested_agg

    df_grouped = calculate_indices_for_df(df_filtered, df, grouping_cols, weather_agg=weather_agg)

    if df_grouped.empty:
        return df_filtered, None, "Error calculant els índexs per a la visualització."

    # FIX: Validació que les columnes de mètrica existeixen al df_grouped abans de dibuixar
    missing_cols = [c for c in [metric_col] if c not in df_grouped.columns]
    if analysis.use_dual_axis and analysis.secondary_metric:
        missing_cols += [c for c in [analysis.secondary_metric] if c not in df_grouped.columns]
    if missing_cols:
        return df_grouped, None, f"Les columnes {missing_cols} no s'han pogut calcular per a la visualització."

    # 6b. Apply top_n ranking on categorical X axis if requested.
    top_n = getattr(analysis, "top_n", None)
    if top_n and x_col in ('species', 'location_name') and metric_col in df_grouped.columns:
        if color_col:
            # Rank the top categories by aggregated metric, then keep their rows.
            top_categories = (
                df_grouped.groupby(x_col)[metric_col].sum()
                .nlargest(top_n).index.tolist()
            )
            df_grouped = df_grouped[df_grouped[x_col].isin(top_categories)]
        else:
            df_grouped = df_grouped.nlargest(top_n, metric_col)
        active_filters_txt.append(f"Top {top_n} per {x_label}")
        
    # 7. Generate Altair Chart
    chart = None
    if analysis.chart_type != "cap":
        # Order hours nocturnally if that is the X axis
        sort_order = None
        if x_col == 'hora':
            sort_order = [str(i).zfill(2) for i in range(16, 24)] + [str(i).zfill(2) for i in range(0, 16)]

        # FIX: Determinem el tipus Altair de l'eix X una sola vegada per reutilitzar-lo de forma consistent
        x_is_ordinal = x_col in ['hora', 'species', 'location_name']
        x_altair_type = 'O' if x_is_ordinal else 'T'
        x_shorthand = f'{x_col}:{x_altair_type}'

        # X axis styling (categorical axes get a configurable label angle).
        x_axis_opts = alt.Axis(grid=False, labelAngle=style['label_angle']) if x_is_ordinal else alt.Axis(grid=False)
        x_encoding = alt.X(x_shorthand, title=x_label, axis=x_axis_opts)
        if sort_order:
            x_encoding = alt.X(x_shorthand, title=x_label, sort=sort_order, axis=x_axis_opts)

        # Y axis styling: optional logarithmic scale and configurable gridlines.
        y_scale = alt.Scale(type='log') if style['log_scale'] else alt.Undefined
        y_axis_opts = alt.Axis(grid=style['show_grid'], gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])
        y_encoding = alt.Y(f'{metric_col}:Q', title=metric_label, scale=y_scale, axis=y_axis_opts)

        # Color encoding: apply the chosen categorical scheme, or a single primary color.
        if color_col:
            color_encoding = alt.Color(f'{color_col}:N', title="Llegenda", scale=alt.Scale(scheme=style['color_scheme']))
        else:
            color_encoding = alt.value(style['primary_color'])
        
        # FIX: Tooltip usa x_shorthand per garantir que el tipus coincideix sempre amb l'encoding X
        tooltip_list = [
            alt.Tooltip(x_shorthand, title=x_label),
            alt.Tooltip(f'{metric_col}:Q', title=metric_label, format=".4f")
        ]
        if color_col:
            tooltip_list.append(alt.Tooltip(f'{color_col}:N', title=color_col))

        # Shared label map reused for primary and secondary metrics.
        metric_labels_map = {
            "total_count": "Comptatge Total",
            "total_buzz": "Total Feeding Buzz",
            "OA": "Ocupació Acústica (OA)",
            "OT": "Ocupació Tròfica (OT)",
            "IA": "Intensitat Depredadora (IA)",
            "temp": "Temperatura (°C)",
            "rel_humidity": "Humitat Relativa (%)",
            "percip_mm": "Precipitació (mm)",
            "wind_speed": "Velocitat del Vent (m/s)"
        }

        # Resolve dual-axis state once for all chart types.
        dual_active = bool(analysis.use_dual_axis and analysis.secondary_metric)
        secondary_metric_col = analysis.secondary_metric if dual_active else None
        secondary_metric_label = metric_labels_map.get(secondary_metric_col, secondary_metric_col) if dual_active else None

        primary_color = style['primary_color']
        secondary_color = style['secondary_color']
        chart_height = style['height']
        mark_opacity = style['opacity']

        def _build_dual_axis_chart(primary_mark: str):
            """Build a layered dual-Y-axis chart. primary_mark is 'line' or 'bar'."""
            base = alt.Chart(df_grouped).encode(x=x_encoding)
            dual_tooltip_primary = [
                alt.Tooltip(x_shorthand, title=x_label),
                alt.Tooltip(f'{metric_col}:Q', title=metric_label, format=".4f")
            ]
            dual_tooltip_secondary = [
                alt.Tooltip(x_shorthand, title=x_label),
                alt.Tooltip(f'{secondary_metric_col}:Q', title=secondary_metric_label, format=".4f")
            ]
            if primary_mark == "bar":
                layer_primary = base.mark_bar(color=primary_color, opacity=min(mark_opacity, 0.75)).encode(
                    y=alt.Y(f'{metric_col}:Q', title=metric_label, scale=y_scale, axis=alt.Axis(titleColor=primary_color, grid=style['show_grid'], gridColor="gray", gridOpacity=0.3, gridDash=[4, 4])),
                    tooltip=dual_tooltip_primary
                )
            else:
                layer_primary = base.mark_line(color=primary_color, size=2, point=style['show_points'], opacity=mark_opacity).encode(
                    y=alt.Y(f'{metric_col}:Q', title=metric_label, scale=y_scale, axis=alt.Axis(titleColor=primary_color, grid=style['show_grid'], gridColor="gray", gridOpacity=0.3, gridDash=[4, 4])),
                    tooltip=dual_tooltip_primary
                )
            layer_secondary = base.mark_line(color=secondary_color, size=2, point=style['show_points'], opacity=mark_opacity).encode(
                y=alt.Y(f'{secondary_metric_col}:Q', title=secondary_metric_label, axis=alt.Axis(titleColor=secondary_color, orient="right", grid=False)),
                tooltip=dual_tooltip_secondary
            )
            return alt.layer(layer_primary, layer_secondary).resolve_scale(y="independent").properties(
                height=chart_height,
                title=f"{metric_label} vs {secondary_metric_label} per {x_label}"
            )

        # Draw chart
        if analysis.chart_type == "línies":
            if dual_active:
                chart = _build_dual_axis_chart("line")
            else:
                base_chart = alt.Chart(df_grouped).mark_line(point=style['show_points'], opacity=mark_opacity).encode(
                    x=x_encoding,
                    y=y_encoding,
                    color=color_encoding,
                    tooltip=tooltip_list
                )
                chart = base_chart.properties(height=chart_height, title=f"{metric_label} per {x_label}")
        elif analysis.chart_type == "dispersió":
            base_chart = alt.Chart(df_grouped).mark_circle(size=style['point_size'], opacity=mark_opacity).encode(
                x=x_encoding,
                y=y_encoding,
                color=color_encoding,
                tooltip=tooltip_list
            )
            chart = base_chart.properties(height=chart_height, title=f"{metric_label} per {x_label}")
        else: # Default is barres
            if dual_active:
                chart = _build_dual_axis_chart("bar")
            else:
                base_chart = alt.Chart(df_grouped).mark_bar(opacity=mark_opacity).encode(
                    x=x_encoding,
                    y=y_encoding,
                    color=color_encoding,
                    tooltip=tooltip_list
                )
                chart = base_chart.properties(height=chart_height, title=f"{metric_label} per {x_label}")

        # Enable pan & zoom interactions when requested, then apply title styling.
        if style['interactive']:
            chart = chart.interactive()
        chart = chart.configure_title(fontSize=16, anchor='start')
        
    filters_summary = " | ".join(active_filters_txt) + f" | Mètrica: {metric_label}"
    return df_grouped, chart, filters_summary