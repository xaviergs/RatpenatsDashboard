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
        description="Columna per desglossar per color ('species' o 'location_name'). Nul si s'ha d'escollir automàticament."
    )
    aggregation: Optional[str] = Field(
        default="auto",
        description="Funció d'agregació per a la mètrica: 'auto', 'sum' o 'mean'. 'auto' aplica la lògica per defecte segons la mètrica."
    )
    filter_hours: Optional[List[int]] = Field(
        default=None,
        description="Llista d'hores (0-23) a filtrar. Nul si no s'especifica cap franja horària concreta."
    )
    top_n: Optional[int] = Field(
        default=None,
        description="Si l'usuari demana un rànquing (ex: 'top 5 espècies'), nombre màxim de categories a mostrar ordenades per la mètrica. Nul si no s'especifica."
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

CAMPS OPCIONALS ADDICIONALS:
- 'color_by': indica 'species' o 'location_name' si l'usuari vol forçar explícitament el desglossament per color. Deixa'l nul si no ho especifica.
- 'aggregation': 'sum' o 'mean' si l'usuari ho demana explícitament (ex: 'mitjana de temperatura'). Per defecte 'auto'.
- 'filter_hours': llista d'hores (0-23) si l'usuari restringeix a una franja horària concreta (ex: 'entre les 22h i les 24h').
- 'top_n': nombre enter si l'usuari demana un rànquing (ex: 'top 5 espècies amb més comptatge').
"""

    # Use model from environment variable or default to gemini-3.5-flash
    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    
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
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": QueryAnalysisSchema
            }
        )
        response = model.generate_content(contents)
    except Exception as primary_error:
        # Check if it is a rate limit, quota, or model access error
        error_msg = str(primary_error).lower()
        is_quota_or_model_error = any(kw in error_msg for kw in ["429", "quota", "limit", "blocked", "not found", "not enabled"])
        
        if is_quota_or_model_error:
            # FIX: Seqüència de fallback més clara i explícita
            fallback_models = ["gemini-2.5-flash", "gemini-2.5-pro"]
            last_error = primary_error
            for fallback_model in fallback_models:
                if fallback_model == model_name:
                    continue
                try:
                    model = genai.GenerativeModel(
                        model_name=fallback_model,
                        system_instruction=system_instruction,
                        generation_config={
                            "response_mime_type": "application/json",
                            "response_schema": QueryAnalysisSchema
                        }
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
        data = json.loads(response.text)
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

    # Ensure optional fields exist and use safe defaults.
    normalized.setdefault("secondary_metric", None)
    normalized["use_dual_axis"] = _normalize_bool(normalized.get("use_dual_axis", False))

    # If use_dual_axis is true but secondary_metric is missing or identical, disable dual axis.
    if normalized["use_dual_axis"] and not normalized.get("secondary_metric"):
        normalized["use_dual_axis"] = False
    if normalized["use_dual_axis"] and normalized.get("secondary_metric") == normalized.get("metric"):
        normalized["use_dual_axis"] = False
        normalized["secondary_metric"] = None

    # Normalize newer optional fields so older/partial LLM responses don't fail validation.
    normalized.setdefault("color_by", None)
    if normalized.get("color_by") not in ("species", "location_name", None):
        normalized["color_by"] = None

    normalized["aggregation"] = normalized.get("aggregation") or "auto"
    if normalized["aggregation"] not in ("auto", "sum", "mean"):
        normalized["aggregation"] = "auto"

    hours = normalized.get("filter_hours")
    if isinstance(hours, list):
        try:
            normalized["filter_hours"] = [int(h) for h in hours if 0 <= int(h) <= 23]
        except (TypeError, ValueError):
            normalized["filter_hours"] = None
    else:
        normalized["filter_hours"] = None

    top_n = normalized.get("top_n")
    try:
        normalized["top_n"] = int(top_n) if top_n else None
    except (TypeError, ValueError):
        normalized["top_n"] = None

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


def calculate_indices_for_df(df_target, df_unfiltered, group_cols):
    """
    Calculates sampling effort and ecological indices for a grouped dataframe.
    Exactly identical to calculations in the main app to maintain dashboard consistency.
    """
    if df_target.empty:
        return pd.DataFrame()
        
    # Aggregate counts and meteorological metrics per grouping
    agg_dict = {
        "total_count": "sum",
        "total_buzz": "sum",
        "temp": "mean",
        "rel_humidity": "mean",
        "percip_mm": "mean",
        "wind_speed": "mean"
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

def apply_filters_and_generate_chart(df: pd.DataFrame, analysis: QueryAnalysisSchema, chart_style: dict | None = None):
    """
    Applies filters specified by the QueryAnalysisSchema and creates an Altair chart
    suitable for the active dashboard panel. `chart_style` holds optional cosmetic
    overrides coming from the manual style controls in the UI.
    """
    chart_style = chart_style or {}
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

    # 3b. Apply Hours Filter
    if analysis.filter_hours:
        df_filtered = df_filtered[df_filtered['observation_hour'].isin(analysis.filter_hours)]
        hours_txt = ', '.join(str(h) for h in analysis.filter_hours)
        active_filters_txt.append(f"Hores: {hours_txt}")

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
    # If grouping by location but species are multiple, we might want color by species (and vice-versa)
    color_col = None
    if not (analysis.use_dual_axis and analysis.secondary_metric):
        if analysis.color_by in ('species', 'location_name') and analysis.color_by != x_col:
            grouping_cols.append(analysis.color_by)
            color_col = analysis.color_by
        elif x_col != 'species' and (not analysis.filter_species or len(analysis.filter_species) > 1):
            grouping_cols.append('species')
            color_col = 'species'
        elif x_col != 'location_name' and (not analysis.filter_locations or len(analysis.filter_locations) > 1):
            grouping_cols.append('location_name')
            color_col = 'location_name'
        
    df_grouped = calculate_indices_for_df(df_filtered, df, grouping_cols)
    
    if df_grouped.empty:
        return df_filtered, None, "Error calculant els índexs per a la visualització."

    # FIX: Validació que les columnes de mètrica existeixen al df_grouped abans de dibuixar
    missing_cols = [c for c in [metric_col] if c not in df_grouped.columns]
    if analysis.use_dual_axis and analysis.secondary_metric:
        missing_cols += [c for c in [analysis.secondary_metric] if c not in df_grouped.columns]
    if missing_cols:
        return df_grouped, None, f"Les columnes {missing_cols} no s'han pogut calcular per a la visualització."

    # 6b. Apply Top N ranking (categories with the highest primary metric value)
    if analysis.top_n and analysis.top_n > 0 and len(df_grouped) > analysis.top_n:
        df_grouped = df_grouped.sort_values(by=metric_col, ascending=False).head(analysis.top_n).copy()
        active_filters_txt.append(f"Top {analysis.top_n}")

    # 7. Generate Altair Chart
    chart = None
    if analysis.chart_type != "cap":
        # Resolve cosmetic overrides coming from the manual style panel, with sane defaults.
        primary_color = chart_style.get("primary_color") or "#1f77b4"
        secondary_color = chart_style.get("secondary_color") or "#ff7f0e"
        height = chart_style.get("height") or 400
        opacity = chart_style.get("opacity", 0.85)
        point_size = chart_style.get("point_size", 80)
        label_angle = chart_style.get("label_angle", -45)
        log_scale = chart_style.get("log_scale", False)
        show_grid = chart_style.get("show_grid", True)
        show_points = chart_style.get("show_points", True)
        interactive = chart_style.get("interactive", True)

        y_scale = alt.Scale(type="log") if log_scale else alt.Undefined

        # Order hours nocturnally if that is the X axis
        sort_order = None
        if x_col == 'hora':
            sort_order = [str(i).zfill(2) for i in range(16, 24)] + [str(i).zfill(2) for i in range(0, 16)]

        # FIX: Determinem el tipus Altair de l'eix X una sola vegada per reutilitzar-lo de forma consistent
        x_is_ordinal = x_col in ['hora', 'species', 'location_name']
        x_altair_type = 'O' if x_is_ordinal else 'T'
        x_shorthand = f'{x_col}:{x_altair_type}'

        x_axis_kwargs = {"labelAngle": label_angle}
        x_encoding = alt.X(x_shorthand, title=x_label, axis=alt.Axis(**x_axis_kwargs))
        if sort_order:
            x_encoding = alt.X(x_shorthand, title=x_label, sort=sort_order, axis=alt.Axis(**x_axis_kwargs))
            
        y_encoding = alt.Y(
            f'{metric_col}:Q', title=metric_label, scale=y_scale,
            axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])
        )
        
        # Color encoding
        color_encoding = alt.Color(f'{color_col}:N', title="Llegenda") if color_col else alt.value(primary_color)
        
        # FIX: Tooltip usa x_shorthand per garantir que el tipus coincideix sempre amb l'encoding X
        tooltip_list = [
            alt.Tooltip(x_shorthand, title=x_label),
            alt.Tooltip(f'{metric_col}:Q', title=metric_label, format=".4f")
        ]
        if color_col:
            tooltip_list.append(alt.Tooltip(f'{color_col}:N', title=color_col))
            
        # Draw chart
        if analysis.chart_type == "línies":
            if analysis.use_dual_axis and analysis.secondary_metric:
                secondary_metric_col = analysis.secondary_metric
                secondary_metric_label = {
                    "total_count": "Comptatge Total",
                    "total_buzz": "Total Feeding Buzz",
                    "OA": "Ocupació Acústica (OA)",
                    "OT": "Ocupació Tròfica (OT)",
                    "IA": "Intensitat Depredadora (IA)",
                    "temp": "Temperatura (°C)",
                    "rel_humidity": "Humitat Relativa (%)",
                    "percip_mm": "Precipitació (mm)",
                    "wind_speed": "Velocitat del Vent (m/s)"
                }.get(secondary_metric_col, secondary_metric_col)
                
                base = alt.Chart(df_grouped).encode(x=x_encoding)
                
                # FIX: Tooltip del dual axis usa x_shorthand consistent
                dual_tooltip_primary = [
                    alt.Tooltip(x_shorthand, title=x_label),
                    alt.Tooltip(f'{metric_col}:Q', title=metric_label, format=".4f")
                ]
                dual_tooltip_secondary = [
                    alt.Tooltip(x_shorthand, title=x_label),
                    alt.Tooltip(f'{secondary_metric_col}:Q', title=secondary_metric_label, format=".4f")
                ]

                line_primary = base.mark_line(color=primary_color, size=2, point=show_points, opacity=opacity).encode(
                    y=alt.Y(f'{metric_col}:Q', title=metric_label, axis=alt.Axis(titleColor=primary_color, grid=True, gridColor="gray", gridOpacity=0.3, gridDash=[4, 4])),
                    tooltip=dual_tooltip_primary
                )
                
                line_secondary = base.mark_line(color=secondary_color, size=2, point=show_points, opacity=opacity).encode(
                    y=alt.Y(f'{secondary_metric_col}:Q', title=secondary_metric_label, axis=alt.Axis(titleColor=secondary_color, orient="right", grid=False)),
                    tooltip=dual_tooltip_secondary
                )
                
                chart = alt.layer(line_primary, line_secondary).resolve_scale(y="independent").properties(
                    height=height,
                    title=f"{metric_label} vs {secondary_metric_label} per {x_label}"
                )
            else:
                base_chart = alt.Chart(df_grouped).mark_line(point=show_points, opacity=opacity).encode(
                    x=x_encoding,
                    y=y_encoding,
                    color=color_encoding,
                    tooltip=tooltip_list
                )
                chart = base_chart.properties(height=height, title=f"{metric_label} per {x_label}")
        elif analysis.chart_type == "dispersió":
            base_chart = alt.Chart(df_grouped).mark_circle(size=point_size, opacity=opacity).encode(
                x=x_encoding,
                y=y_encoding,
                color=color_encoding,
                tooltip=tooltip_list
            )
            chart = base_chart.properties(height=height, title=f"{metric_label} per {x_label}")
        else: # Default is barres
            base_chart = alt.Chart(df_grouped).mark_bar(opacity=opacity).encode(
                x=x_encoding,
                y=y_encoding,
                color=color_encoding,
                tooltip=tooltip_list
            )
            chart = base_chart.properties(height=height, title=f"{metric_label} per {x_label}")
            
        chart = chart.configure_axis(grid=show_grid).configure_title(fontSize=16, anchor='start')
        if interactive:
            chart = chart.interactive()
        
    filters_summary = " | ".join(active_filters_txt) + f" | Mètrica: {metric_label}"
    return df_grouped, chart, filters_summary