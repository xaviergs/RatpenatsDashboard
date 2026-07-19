import os
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env file for local development.
# In a cloud or production environment (like Google Cloud Run), 
# variables are typically loaded directly from os.environ.
load_dotenv()

# Streamlit natively uses `--server.port` via CLI, but retrieving the PORT
# environment variable ensures we are ready for Google Cloud Run deployment.
port = os.environ.get("PORT", "8501")

st.set_page_config(page_title="Ratpenats al Cap de Creus", page_icon="🚀", layout="wide")

# Inject Custom CSS for premium look and feel
st.markdown("""
<style>
    /* Styling for metric cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, rgba(20, 20, 25, 0.05) 0%, rgba(30, 30, 40, 0.05) 100%);
        border: 1px solid rgba(100, 100, 100, 0.3);
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 15px rgba(0, 0, 0, 0.2);
        border: 1px solid rgba(100, 100, 100, 0.6);
    }
    /* Modern Typography adjustments */
    h1, h2, h3 {
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
    }
    /* Button enhancements */
    div.stButton > button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    div.stButton > button:hover {
        transform: scale(1.02);
    }
    /* Tab labels enhancements */
    button[data-baseweb="tab"] p {
        font-size: 1.25rem !important;
        font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_connection() -> Client:
    """
    Initialize and return a singleton connection to Supabase.
    Reads credentials from st.secrets (Streamlit Cloud) or os.environ (local .env).
    Uses @st.cache_resource to prevent re-initializing the client on every rerun.
    """
    def _get(key: str) -> str | None:
        value = None
        try:
            value = st.secrets.get(key)
        except Exception:
            pass

        if value is None:
            value = os.environ.get(key)

        if isinstance(value, str):
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1].strip()
        return value

    url = _get("SUPABASE_URL")
    key = _get("SUPABASE_KEY")

    if not url or not key:
        st.error("No s'han trobat les credencials de Supabase. Si us plau, configureu les variables d'entorn SUPABASE_URL i SUPABASE_KEY.")
        st.stop()

    if key and not key.startswith("sb_"):
        st.warning("La clau SUPABASE_KEY no comença per 'sb_'. Comprova que has configurat la clau pública correcta (sense cometes ni espais addicionals).")

    try:
        return create_client(url, key)
    except Exception as e:
        # Show limited debug info without leaking secrets
        if isinstance(key, str):
            key_len = len(key)
            key_sample = key[:5] + '...' + key[-5:]
        else:
            key_len = 'None'
            key_sample = 'None'

        st.error(
            "❌ Error connectant a Supabase. Verifica que SUPABASE_URL i SUPABASE_KEY siguin correctes."
        )
        st.error(f"URL capturada: {url}")
        st.error(f"SUPABASE_KEY longitud: {key_len}, prefix: {key[:3] if isinstance(key, str) else 'None'}")
        st.stop()

def load_bat_observations(_progress_callback=None):
    """
    Load the full bat_observations_full dataset using paginated range() queries.

    _progress_callback(loaded_rows: int) is invoked after each page so the UI can
    render a live progress indicator. It is prefixed with an underscore so Streamlit
    excludes it from the cache key (callbacks are not hashable / not relevant to data).
    An optional MAX_ROWS_LOAD env var caps the load only as a safety valve; by default
    the whole dataset is fetched.
    """
    client = init_connection()
    all_records = []
    offset = 0
    max_rows = 1000
    cap_env = os.getenv("MAX_ROWS_LOAD", "").strip()
    max_total_rows = int(cap_env) if cap_env.isdigit() and int(cap_env) > 0 else None
    # Keep payload minimal to reduce first-load latency from Supabase.
    selected_columns = (
        "species,location_name,observation_date,observation_hour,"
        "total_count,total_buzz,temp,rel_humidity,wind_speed,precip_mm"
    )

    while True:
        if max_total_rows is not None and len(all_records) >= max_total_rows:
            break
        try:
            page_size = max_rows
            if max_total_rows is not None:
                page_size = min(max_rows, max_total_rows - len(all_records))
            res = (
                client.table("bat_observations_full")
                .select(selected_columns)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            if res.data:
                all_records.extend(res.data)
                if _progress_callback:
                    _progress_callback(len(all_records))

            if not res.data or len(res.data) < page_size:
                break

            offset += page_size
        except Exception as e:
            st.error(f"Error carregant dades bat_observations_full: {e}")
            break

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)

    # Ensure proper data types
    if 'observation_date' in df.columns:
        df['observation_date'] = pd.to_datetime(df['observation_date']).dt.date
    if 'total_count' in df.columns:
        df['total_count'] = pd.to_numeric(df['total_count'], errors='coerce').fillna(0)
    if 'total_buzz' in df.columns:
        df['total_buzz'] = pd.to_numeric(df['total_buzz'], errors='coerce').fillna(0)

    if 'temp' in df.columns:
        df['temp'] = pd.to_numeric(df['temp'], errors='coerce')
    if 'rel_humidity' in df.columns:
        df['rel_humidity'] = pd.to_numeric(df['rel_humidity'], errors='coerce')
    if 'wind_speed' in df.columns:
        df['wind_speed'] = pd.to_numeric(df['wind_speed'], errors='coerce')
    # Backward compatibility: the app uses `percip_mm` in metrics/options.
    if 'precip_mm' in df.columns and 'percip_mm' not in df.columns:
        df['percip_mm'] = pd.to_numeric(df['precip_mm'], errors='coerce')
    elif 'percip_mm' in df.columns:
        df['percip_mm'] = pd.to_numeric(df['percip_mm'], errors='coerce')

    return df

def calculate_ecological_indices(df_target, df_unfiltered, group_cols):
    df_grouped = df_target.groupby(group_cols, as_index=False)[["total_count", "total_buzz"]].sum()
    
    df_unfiltered_copy = df_unfiltered.copy()
    df_unfiltered_copy['session_hour_key'] = df_unfiltered_copy['observation_date'].astype(str) + "_" + df_unfiltered_copy['observation_hour'].astype(str) + "_" + df_unfiltered_copy['location_name']
    
    eff_group_cols = [c for c in group_cols if c != 'species']
    
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
    df_grouped['IA'] = df_grouped.apply(lambda row: row['total_buzz'] / row['total_count'] if row['total_count'] > 0 else 0.0, axis=1)
    
    return df_grouped

METRIC_COLS = {
    "Comptatge": ("total_count", "Comptatge Total"),
    "Buzz": ("total_buzz", "Total Buzz"),
    "OA (Ocupació Acústica)": ("OA", "Índex OA"),
    "OT (Ocupació Tròfica)": ("OT", "Índex OT"),
    "IA (Intensitat Depredadora)": ("IA", "Índex IA"),
    "Temperatura (temp)": ("temp", "Temperatura (°C)"),
    "Humitat (rel_humidity)": ("rel_humidity", "Humitat Relativa (%)"),
    "Precipitació (percip_mm)": ("percip_mm", "Precipitació (mm)"),
    "Vent (wind_speed)": ("wind_speed", "Velocitat del Vent (m/s)")
}


# Two-color palette for dual-axis line charts: first metric → left axis, second → right axis.
CHART_DUAL_COLORS = ['#1f77b4', '#ff7f0e']


def render_y_range_slider(series, key, label, color=None):
    """
    Show an always-visible range slider for a Y axis.
    When color is provided, renders a colored label above the slider.
    Returns [min, max] or None if the series has no valid numeric data.
    """
    values = pd.to_numeric(series, errors='coerce').dropna()
    if values.empty:
        return None

    y_min = float(values.min())
    y_max = float(values.max())

    if y_min == y_max:
        y_max = y_min + 1.0 if y_min == 0 else y_max * 1.1
        y_min = 0.0 if y_min == 0 else y_min * 0.9

    if color:
        st.markdown(
            f'<p style="color:{color};font-weight:600;margin:4px 0 -14px 0">● Llindar — {label}</p>',
            unsafe_allow_html=True,
        )
    y_range = st.slider(
        label,
        min_value=float(y_min),
        max_value=float(y_max),
        value=(float(y_min), float(y_max)),
        key=key,
        label_visibility="collapsed" if color else "visible",
    )
    return [float(y_range[0]), float(y_range[1])]


def filter_by_range(df, col, y_domain=None, no_zero=False):
    """
    Filter df rows by optional numeric range and optionally remove zeros for a column.
    """
    if df.empty or col not in df.columns:
        return df

    out = df.copy()
    vals = pd.to_numeric(out[col], errors='coerce')
    out = out[vals.notna()]
    vals = pd.to_numeric(out[col], errors='coerce')

    if no_zero:
        out = out[vals != 0]
        vals = pd.to_numeric(out[col], errors='coerce')

    if y_domain is not None:
        out = out[(vals >= float(y_domain[0])) & (vals <= float(y_domain[1]))]

    return out


def enrich_grouped_with_env(df_source, group_cols, df_grouped):
    """
    Merge mean-aggregated environmental columns into an already-grouped dataframe.
    """
    env_cols = [c for c in ("temp", "rel_humidity", "wind_speed", "percip_mm") if c in df_source.columns]
    if not env_cols:
        return df_grouped
    valid_group_cols = [c for c in group_cols if c in df_source.columns]
    if not valid_group_cols:
        return df_grouped
    env_agg = df_source.groupby(valid_group_cols, as_index=False)[env_cols].mean()
    return pd.merge(df_grouped, env_agg, on=valid_group_cols, how='left')


@st.cache_data(ttl=900, show_spinner=False)
def load_location_coordinates():
    """
    Load coordinates from the locations_and_stations view and normalize to:
    location_name, latitude, longitude.
    """
    client = init_connection()
    try:
        resp = client.table("locations_and_stations").select("*").execute()
        records = resp.data or []
        if not records:
            return pd.DataFrame(columns=["location_name", "latitude", "longitude"])

        df_raw = pd.DataFrame(records)
        name_col = next((c for c in ["location_name", "display_name", "name", "nom"] if c in df_raw.columns), None)
        lat_col = next((c for c in ["latitude", "lat"] if c in df_raw.columns), None)
        lon_col = next((c for c in ["longitude", "lon", "lng", "long"] if c in df_raw.columns), None)

        if not name_col or not lat_col or not lon_col:
            return pd.DataFrame(columns=["location_name", "latitude", "longitude"])

        # Keep every column from the view and normalize core fields for joins/map.
        df_coords = df_raw.copy()
        rename_map = {}
        if name_col != "location_name":
            rename_map[name_col] = "location_name"
        if lat_col != "latitude":
            rename_map[lat_col] = "latitude"
        if lon_col != "longitude":
            rename_map[lon_col] = "longitude"
        if rename_map:
            df_coords = df_coords.rename(columns=rename_map)

        df_coords["location_name"] = df_coords["location_name"].astype(str).str.strip()
        df_coords["latitude"] = pd.to_numeric(df_coords["latitude"], errors="coerce")
        df_coords["longitude"] = pd.to_numeric(df_coords["longitude"], errors="coerce")

        df_coords = df_coords[
            (df_coords["location_name"] != "")
            & df_coords["latitude"].notna()
            & df_coords["longitude"].notna()
        ].drop_duplicates(subset=["location_name"], keep="first")

        return df_coords
    except Exception:
        return pd.DataFrame(columns=["location_name", "latitude", "longitude"])


def compute_metric_grouped(df_source: pd.DataFrame, metric_col: str, group_cols: list[str]) -> pd.DataFrame:
    """
    Compute map metric by groups using ecological indices when required.
    """
    derived_metrics = {"total_count", "total_buzz", "OA", "OT", "IA"}

    if metric_col in derived_metrics:
        df_metric = calculate_ecological_indices(df_source, df_source, group_cols)
        if metric_col not in df_metric.columns:
            return pd.DataFrame(columns=group_cols + [metric_col])
        cols = [c for c in group_cols if c in df_metric.columns] + [metric_col]
        return df_metric[cols].copy()

    if metric_col not in df_source.columns:
        return pd.DataFrame(columns=group_cols + [metric_col])

    return df_source.groupby(group_cols, as_index=False)[metric_col].mean()


def merge_metric_with_coordinates(df_metric: pd.DataFrame) -> pd.DataFrame:
    """
    Merge grouped metric dataframe with location coordinates view.
    Keeps all metadata columns from locations_and_stations.
    """
    if df_metric.empty or "location_name" not in df_metric.columns:
        return pd.DataFrame()

    df_coords = load_location_coordinates()
    if df_coords.empty:
        return pd.DataFrame()

    df_m = df_metric.copy()
    df_m["join_key"] = df_m["location_name"].astype(str).str.strip().str.lower()

    df_c = df_coords.copy()
    df_c["join_key"] = df_c["location_name"].astype(str).str.strip().str.lower()
    df_c = df_c.rename(columns={"location_name": "location_name_coords"})

    df_m = df_m.rename(columns={"location_name": "location_name_metric"})
    df_map = pd.merge(df_m, df_c, on="join_key", how="left")
    df_map["location_name"] = df_map["location_name_metric"].fillna(df_map["location_name_coords"])
    df_map = df_map[df_map["latitude"].notna() & df_map["longitude"].notna()].copy()
    return df_map


def build_map_detail_table(df_map: pd.DataFrame, metric_col: str) -> pd.DataFrame:
    """
    Prepare georeferenced detail table with full location view metadata.
    """
    if df_map.empty:
        return df_map

    display_df = df_map.copy()
    drop_if_present = [
        "join_key", "location_name_metric", "location_name_coords",
        "color", "radius", "latitude_plot", "longitude_plot", "weight",
        "species_rank", "species_count", "angle", "share_in_location",
    ]
    display_df = display_df.drop(columns=[c for c in drop_if_present if c in display_df.columns])

    cols_first = ["location_name", "latitude", "longitude", metric_col]
    cols_to_show = [c for c in cols_first if c in display_df.columns]
    cols_to_show += [c for c in display_df.columns if c not in cols_to_show]
    return display_df[cols_to_show]


def render_species_legend(species_color: dict, title: str = "Llegenda d'espècies"):
    """
    Render an inline color-chip legend for species categories.
    """
    if not species_color:
        return

    chips = []
    for species_name, rgba in species_color.items():
        r, g, b, _a = rgba
        safe_name = str(species_name).replace("<", "&lt;").replace(">", "&gt;")
        chips.append(
            f"<span style='display:inline-flex;align-items:center;margin:2px 8px 2px 0;'>"
            f"<span style='width:10px;height:10px;border-radius:999px;background:rgb({r},{g},{b});display:inline-block;margin-right:6px;'></span>"
            f"<span>{safe_name}</span></span>"
        )

    st.markdown(f"**{title}**", unsafe_allow_html=False)
    st.markdown("".join(chips), unsafe_allow_html=True)


def install_tab_persistence():
        """
        Persist and restore active Streamlit tab across reruns.
        """
        components.html(
                """
                <script>
                (function () {
                    const KEY = 'ratpenats_active_tab_idx';
                    const root = window.parent.document;

                    function bindAndRestore() {
                        const tabs = root.querySelectorAll('button[data-baseweb="tab"]');
                        if (!tabs || !tabs.length) return;

                        tabs.forEach((tab, idx) => {
                            if (!tab.dataset.ratpenatsBound) {
                                tab.addEventListener('click', () => {
                                    window.parent.sessionStorage.setItem(KEY, String(idx));
                                });
                                tab.dataset.ratpenatsBound = '1';
                            }
                        });

                        const saved = parseInt(window.parent.sessionStorage.getItem(KEY) || '0', 10);
                        if (Number.isFinite(saved) && saved >= 0 && saved < tabs.length) {
                            const isSelected = tabs[saved].getAttribute('aria-selected') === 'true';
                            if (!isSelected) tabs[saved].click();
                        }
                    }

                    bindAndRestore();
                    setTimeout(bindAndRestore, 60);
                    setTimeout(bindAndRestore, 180);
                    setTimeout(bindAndRestore, 360);
                })();
                </script>
                """,
                height=0,
        )


def main():
    st.title("Ratpenats al Cap de Creus")
    st.markdown(f"**Port de Desplegament**: `{port}` (Punt per a Cloud Run)")
    st.divider()
    
    # Initialize connection
    try:
        supabase_client = init_connection()
    except Exception as e:
        st.error(f"Error amb Supabase: {e}")
        return
    
    # Load all observations automatically on startup, with a live progress indicator
    # so the user can see how the download is going on large datasets.
    if "df_full" not in st.session_state:
        progress_box = st.status("Carregant dades de ratpenats...", expanded=True)
        progress_bar = st.progress(0, text="Connectant amb la base de dades...")

        def _update_progress(loaded_rows):
            # We don't know the total upfront; show a moving indicator capped at 95%.
            pct = min(95, 5 + (loaded_rows // 1000) * 5)
            progress_bar.progress(pct, text=f"Carregant observacions... {loaded_rows:,} registres")

        try:
            df_loaded = load_bat_observations(_progress_callback=_update_progress)
            progress_bar.progress(100, text=f"Completat: {len(df_loaded):,} registres carregats.")
            progress_box.update(
                label=f"Dades carregades correctament ({len(df_loaded):,} registres).",
                state="complete",
                expanded=False,
            )
            progress_bar.empty()
            st.session_state.df_full = df_loaded
        except Exception as e:
            progress_box.update(label="Error carregant les dades.", state="error")
            st.error(f"Error carregant dades: {e}")
            st.session_state.df_full = pd.DataFrame()
    
    df_full = st.session_state.df_full

    # Create Layout Tabs
    tab_accions, tab_mapa, tab_estatus, tab_syllabus, tab_chat = st.tabs(["🚀 Accions", "🗺️ Mapa", "📊 Estatus", "📖 Syllabus", "💬 Anàlisi Semàntica"])
    install_tab_persistence()

    # ---------------- TAB 1: ACCIONS ----------------
    with tab_accions:
        st.header("Anàlisi i Accions: Comptatge i Buzz")
        st.markdown("Explora els resultats gràfics del comptatge i l'activitat (buzz) segons diferents criteris.")
        
        import datetime
        all_species = sorted(df_full['species'].dropna().unique().tolist()) if not df_full.empty and 'species' in df_full.columns else []
        all_locations = sorted(df_full['location_name'].dropna().unique().tolist()) if not df_full.empty and 'location_name' in df_full.columns else []
        
        min_date_val = df_full['observation_date'].dropna().min() if not df_full.empty and 'observation_date' in df_full.columns else None
        max_date_val = df_full['observation_date'].dropna().max() if not df_full.empty and 'observation_date' in df_full.columns else None
        
        if pd.isna(min_date_val) or pd.isna(max_date_val):
            min_date_val = datetime.date(2020, 1, 1)
            max_date_val = datetime.date.today()
            
        if min_date_val == max_date_val:
            min_date_val = min_date_val - datetime.timedelta(days=1)
            max_date_val = max_date_val + datetime.timedelta(days=1)
        
        # --- Àrea 1: Comptatge i Buzz per espècies ---
        st.subheader("Comptatge i Buzz per espècies")
        with st.container(border=True):
            col1_filt, col1_graf = st.columns([1, 3])
            with col1_filt:
                st.markdown("##### Paràmetres")
                sp_esp_sel = st.multiselect("Selecciona Espècie(s):", ["Totes"] + all_species, default=["Totes"], key="sp_esp")
                sp_loc_sel = st.multiselect("Selecciona Localització:", ["Totes"] + all_locations, default=["Totes"], key="sp_loc")
                
                # Selector de dates
                sp_date_method = st.radio("Mètode de selecció de dates:", ["Desplaçador (Slider)", "Calendari Manual", "Només un dia"], horizontal=True, key="sp_date_method")
                if sp_date_method == "Desplaçador (Slider)":
                    sp_date_sel = st.slider("Rang de dates:", min_value=min_date_val, max_value=max_date_val, value=(min_date_val, max_date_val), key="sp_date_slider")
                elif sp_date_method == "Només un dia":
                    _d = st.date_input("Data:", value=min_date_val, min_value=min_date_val, max_value=max_date_val, key="sp_date")
                    sp_date_sel = (_d, _d)
                else:
                    c1, c2 = st.columns(2)
                    with c1:
                        _s = st.date_input("Data inicial:", value=min_date_val, min_value=min_date_val, max_value=max_date_val, key="sp_start")
                    with c2:
                        _e = st.date_input("Data final:", value=max_date_val, min_value=min_date_val, max_value=max_date_val, key="sp_end")
                    sp_date_sel = (_s, _e) if _s <= _e else (_e, _s)
                
                sp_vis_type = st.radio("Tipus de visualització:", ["Línies", "Barres"], horizontal=True, key="sp_vis")

                sp_metrics_sel = st.multiselect(
                    "Mètriques a visualitzar (màx. 2):",
                    list(METRIC_COLS.keys()),
                    default=["Comptatge"],
                    key="sp_metrics",
                )
                if len(sp_metrics_sel) > 2:
                    st.warning("Només pots seleccionar fins a 2 opcions. S'utilitzaran les dues primeres.")
                    sp_metrics_sel = sp_metrics_sel[:2]
                if not sp_metrics_sel:
                    sp_metrics_sel = ["Comptatge"]
                sp_no_zeros = st.checkbox("No mostrar zeros", value=False, key="sp_no_zeros")
            
            with col1_graf:
                st.markdown("##### Resultat Gràfic")
                if df_full.empty:
                    st.warning("No s'han trobat dades a la vista bat_observations_full.")
                else:
                    df_unfiltered = df_full.copy()
                    if "Totes" not in sp_loc_sel and sp_loc_sel:
                        df_unfiltered = df_unfiltered[df_unfiltered['location_name'].isin(sp_loc_sel)]
                    start_d, end_d = sp_date_sel
                    df_unfiltered = df_unfiltered[(df_unfiltered['observation_date'] >= start_d) & (df_unfiltered['observation_date'] <= end_d)]
                    
                    df_sp = df_unfiltered.copy()
                    if "Totes" not in sp_esp_sel and sp_esp_sel:
                        df_sp = df_sp[df_sp['species'].isin(sp_esp_sel)]
                        
                    if df_sp.empty:
                        st.info("Cap registre coincideix amb els filtres seleccionats.")
                    else:
                        import altair as alt
                        chart_sp = None
                        m1_label = sp_metrics_sel[0]
                        m1_col, m1_title = METRIC_COLS[m1_label]
                        is_dual = len(sp_metrics_sel) == 2 and sp_vis_type == "Línies"
                        c1_color, c2_color = CHART_DUAL_COLORS

                        if sp_vis_type == "Línies":
                            df_sp_grouped = calculate_ecological_indices(df_sp, df_unfiltered, ["species"])
                            df_sp_grouped = enrich_grouped_with_env(df_sp, ["species"], df_sp_grouped)
                            c1_ser = df_sp_grouped[m1_col] if m1_col in df_sp_grouped.columns else pd.Series(dtype=float)
                            if is_dual:
                                m2_label = sp_metrics_sel[1]
                                m2_col, m2_title = METRIC_COLS[m2_label]
                                c2_ser = df_sp_grouped[m2_col] if m2_col in df_sp_grouped.columns else pd.Series(dtype=float)
                                dom1 = render_y_range_slider(c1_ser, "sp_line_m1", m1_title, c1_color)
                                df_sp_grouped = filter_by_range(df_sp_grouped, m1_col, dom1, sp_no_zeros)
                                dom2 = render_y_range_slider(c2_ser, "sp_line_m2", m2_title, c2_color)
                                df_sp_grouped = filter_by_range(df_sp_grouped, m2_col, dom2, sp_no_zeros)
                            else:
                                dom1 = render_y_range_slider(c1_ser, "sp_line_m1", m1_title, c1_color)
                                dom2 = None
                                df_sp_grouped = filter_by_range(df_sp_grouped, m1_col, dom1, sp_no_zeros)

                            if df_sp_grouped.empty:
                                st.info("No hi ha punts dins del rang seleccionat o després d'aplicar 'No mostrar zeros'.")
                            else:
                                base = alt.Chart(df_sp_grouped).encode(
                                    x=alt.X('species:N', title='Espècie', axis=alt.Axis(labelAngle=-45, grid=False))
                                )
                                if is_dual:
                                    line1 = base.mark_line(color=c1_color, point=True).encode(
                                        y=alt.Y(f'{m1_col}:Q', title=m1_title,
                                            axis=alt.Axis(titleColor=c1_color, grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]),
                                            scale=alt.Scale(domain=dom1) if dom1 else alt.Undefined)
                                    )
                                    line2 = base.mark_line(color=c2_color, point=True).encode(
                                        y=alt.Y(f'{m2_col}:Q', title=m2_title,
                                            axis=alt.Axis(titleColor=c2_color, orient='right', grid=False),
                                            scale=alt.Scale(domain=dom2) if dom2 else alt.Undefined)
                                    )
                                    chart_sp = alt.layer(line1, line2).resolve_scale(y='independent').properties(height=400).configure_axis(grid=False)
                                else:
                                    chart_sp = base.mark_line(color=c1_color, point=True).encode(
                                        y=alt.Y(f'{m1_col}:Q', title=m1_title,
                                            axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]),
                                            scale=alt.Scale(domain=dom1) if dom1 else alt.Undefined),
                                        tooltip=['species:N', f'{m1_col}:Q']
                                    ).properties(height=400).configure_axis(grid=False)
                        else:
                            df_sp_grouped = calculate_ecological_indices(df_sp, df_unfiltered, ["species", "location_name"])
                            df_sp_grouped = enrich_grouped_with_env(df_sp, ["species", "location_name"], df_sp_grouped)
                            c1_ser = df_sp_grouped[m1_col] if m1_col in df_sp_grouped.columns else pd.Series(dtype=float)
                            dom1 = render_y_range_slider(c1_ser, "sp_bar_m1", m1_title, c1_color)
                            df_sp_grouped = filter_by_range(df_sp_grouped, m1_col, dom1, sp_no_zeros)

                            if df_sp_grouped.empty:
                                st.info("No hi ha punts dins del rang seleccionat o després d'aplicar 'No mostrar zeros'.")
                            else:
                                chart_sp = alt.Chart(df_sp_grouped).mark_bar().encode(
                                    x=alt.X('species:N', title='Espècie', axis=alt.Axis(labelAngle=-45, grid=False)),
                                    y=alt.Y(f'{m1_col}:Q', title=m1_title,
                                        axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]),
                                        scale=alt.Scale(domain=dom1) if dom1 else alt.Undefined),
                                    color=alt.Color('location_name:N', title='Localització', legend=alt.Legend(orient="bottom", columns=3)),
                                    tooltip=['species:N', 'location_name:N', f'{m1_col}:Q']
                                ).properties(height=400).configure_axis(grid=False)

                        if chart_sp is not None:
                            st.altair_chart(chart_sp, width="stretch")

        # --- Àrea 2: Comptatge i Buzz per localització ---
        st.subheader("Comptatge i Buzz per localització")
        with st.container(border=True):
            col2_filt, col2_graf = st.columns([1, 3])
            with col2_filt:
                st.markdown("##### Paràmetres")
                loc_esp_sel = st.multiselect("Selecciona Espècie(s):", ["Totes"] + all_species, default=["Totes"], key="loc_esp")
                loc_loc_sel = st.multiselect("Selecciona Localització:", ["Totes"] + all_locations, default=["Totes"], key="loc_loc")
                # Selector de dates
                loc_date_method = st.radio("Mètode de selecció de dates:", ["Desplaçador (Slider)", "Calendari Manual", "Només un dia"], horizontal=True, key="loc_date_method")
                if loc_date_method == "Desplaçador (Slider)":
                    loc_date_sel = st.slider("Rang de dates:", min_value=min_date_val, max_value=max_date_val, value=(min_date_val, max_date_val), key="loc_date_slider")
                elif loc_date_method == "Només un dia":
                    _d = st.date_input("Data:", value=min_date_val, min_value=min_date_val, max_value=max_date_val, key="loc_date")
                    loc_date_sel = (_d, _d)
                else:
                    c1, c2 = st.columns(2)
                    with c1:
                        _s = st.date_input("Data inicial:", value=min_date_val, min_value=min_date_val, max_value=max_date_val, key="loc_start")
                    with c2:
                        _e = st.date_input("Data final:", value=max_date_val, min_value=min_date_val, max_value=max_date_val, key="loc_end")
                    loc_date_sel = (_s, _e) if _s <= _e else (_e, _s)
                
                loc_vis_type = st.radio("Tipus de visualització:", ["Línies", "Barres"], horizontal=True, key="loc_vis")

                loc_metrics_sel = st.multiselect(
                    "Mètriques a visualitzar (màx. 2):",
                    list(METRIC_COLS.keys()),
                    default=["Comptatge"],
                    key="loc_metrics",
                )
                if len(loc_metrics_sel) > 2:
                    st.warning("Només pots seleccionar fins a 2 opcions. S'utilitzaran les dues primeres.")
                    loc_metrics_sel = loc_metrics_sel[:2]
                if not loc_metrics_sel:
                    loc_metrics_sel = ["Comptatge"]
                loc_no_zeros = st.checkbox("No mostrar zeros", value=False, key="loc_no_zeros")
                    
            with col2_graf:
                st.markdown("##### Resultat Gràfic")
                if df_full.empty:
                    st.warning("No s'han trobat dades a la vista bat_observations_full.")
                else:
                    df_unfiltered = df_full.copy()
                    if "Totes" not in loc_loc_sel and loc_loc_sel:
                        df_unfiltered = df_unfiltered[df_unfiltered['location_name'].isin(loc_loc_sel)]
                    start_d, end_d = loc_date_sel
                    df_unfiltered = df_unfiltered[(df_unfiltered['observation_date'] >= start_d) & (df_unfiltered['observation_date'] <= end_d)]
                    
                    df_loc = df_unfiltered.copy()
                    if "Totes" not in loc_esp_sel and loc_esp_sel:
                        df_loc = df_loc[df_loc['species'].isin(loc_esp_sel)]
                        
                    if df_loc.empty:
                        st.info("Cap registre coincideix amb els filtres seleccionats.")
                    else:
                        import altair as alt
                        chart_loc = None
                        m1_label = loc_metrics_sel[0]
                        m1_col, m1_title = METRIC_COLS[m1_label]
                        is_dual = len(loc_metrics_sel) == 2 and loc_vis_type == "Línies"
                        c1_color, c2_color = CHART_DUAL_COLORS

                        if loc_vis_type == "Línies":
                            df_loc_grouped = calculate_ecological_indices(df_loc, df_unfiltered, ["location_name"])
                            df_loc_grouped = enrich_grouped_with_env(df_loc, ["location_name"], df_loc_grouped)
                            c1_ser = df_loc_grouped[m1_col] if m1_col in df_loc_grouped.columns else pd.Series(dtype=float)
                            if is_dual:
                                m2_label = loc_metrics_sel[1]
                                m2_col, m2_title = METRIC_COLS[m2_label]
                                c2_ser = df_loc_grouped[m2_col] if m2_col in df_loc_grouped.columns else pd.Series(dtype=float)
                                dom1 = render_y_range_slider(c1_ser, "loc_line_m1", m1_title, c1_color)
                                df_loc_grouped = filter_by_range(df_loc_grouped, m1_col, dom1, loc_no_zeros)
                                dom2 = render_y_range_slider(c2_ser, "loc_line_m2", m2_title, c2_color)
                                df_loc_grouped = filter_by_range(df_loc_grouped, m2_col, dom2, loc_no_zeros)
                            else:
                                dom1 = render_y_range_slider(c1_ser, "loc_line_m1", m1_title, c1_color)
                                dom2 = None
                                df_loc_grouped = filter_by_range(df_loc_grouped, m1_col, dom1, loc_no_zeros)

                            if df_loc_grouped.empty:
                                st.info("No hi ha punts dins del rang seleccionat o després d'aplicar 'No mostrar zeros'.")
                            else:
                                base2 = alt.Chart(df_loc_grouped).encode(
                                    x=alt.X('location_name:N', title='Localització', axis=alt.Axis(labelAngle=-45, grid=False))
                                )
                                if is_dual:
                                    line1 = base2.mark_line(color=c1_color, point=True).encode(
                                        y=alt.Y(f'{m1_col}:Q', title=m1_title,
                                            axis=alt.Axis(titleColor=c1_color, grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]),
                                            scale=alt.Scale(domain=dom1) if dom1 else alt.Undefined)
                                    )
                                    line2 = base2.mark_line(color=c2_color, point=True).encode(
                                        y=alt.Y(f'{m2_col}:Q', title=m2_title,
                                            axis=alt.Axis(titleColor=c2_color, orient='right', grid=False),
                                            scale=alt.Scale(domain=dom2) if dom2 else alt.Undefined)
                                    )
                                    chart_loc = alt.layer(line1, line2).resolve_scale(y='independent').properties(height=400).configure_axis(grid=False)
                                else:
                                    chart_loc = base2.mark_line(color=c1_color, point=True).encode(
                                        y=alt.Y(f'{m1_col}:Q', title=m1_title,
                                            axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]),
                                            scale=alt.Scale(domain=dom1) if dom1 else alt.Undefined),
                                        tooltip=['location_name:N', f'{m1_col}:Q']
                                    ).properties(height=400).configure_axis(grid=False)
                        else:
                            df_loc_grouped = calculate_ecological_indices(df_loc, df_unfiltered, ["location_name", "species"])
                            df_loc_grouped = enrich_grouped_with_env(df_loc, ["location_name", "species"], df_loc_grouped)
                            c1_ser = df_loc_grouped[m1_col] if m1_col in df_loc_grouped.columns else pd.Series(dtype=float)
                            dom1 = render_y_range_slider(c1_ser, "loc_bar_m1", m1_title, c1_color)
                            df_loc_grouped = filter_by_range(df_loc_grouped, m1_col, dom1, loc_no_zeros)

                            if df_loc_grouped.empty:
                                st.info("No hi ha punts dins del rang seleccionat o després d'aplicar 'No mostrar zeros'.")
                            else:
                                chart_loc = alt.Chart(df_loc_grouped).mark_bar().encode(
                                    x=alt.X('location_name:N', title='Localització', axis=alt.Axis(labelAngle=-45, grid=False)),
                                    y=alt.Y(f'{m1_col}:Q', title=m1_title,
                                        axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]),
                                        scale=alt.Scale(domain=dom1) if dom1 else alt.Undefined),
                                    color=alt.Color('species:N', title='Espècie', legend=alt.Legend(orient="bottom", columns=3)),
                                    tooltip=['location_name:N', 'species:N', f'{m1_col}:Q']
                                ).properties(height=400).configure_axis(grid=False)

                        if chart_loc is not None:
                            st.altair_chart(chart_loc, width="stretch")

        # --- Àrea 3: Comptatge i Buzz per data ---
        st.subheader("Comptatge i Buzz per data")
        with st.container(border=True):
            col3_filt, col3_graf = st.columns([1, 3])
            with col3_filt:
                st.markdown("##### Paràmetres")
                date_esp_sel = st.multiselect("Selecciona Espècie(s):", ["Totes"] + all_species, default=["Totes"], key="date_esp")
                date_loc_sel = st.multiselect("Selecciona Localització:", ["Totes"] + all_locations, default=["Totes"], key="date_loc")
                # Selector de dates
                date_date_method = st.radio("Mètode de selecció de dates:", ["Desplaçador (Slider)", "Calendari Manual", "Només un dia"], horizontal=True, key="date_date_method")
                if date_date_method == "Desplaçador (Slider)":
                    date_date_sel = st.slider("Rang de dates:", min_value=min_date_val, max_value=max_date_val, value=(min_date_val, max_date_val), key="date_date_slider")
                elif date_date_method == "Només un dia":
                    _d = st.date_input("Data:", value=min_date_val, min_value=min_date_val, max_value=max_date_val, key="date_date")
                    date_date_sel = (_d, _d)
                else:
                    c1, c2 = st.columns(2)
                    with c1:
                        _s = st.date_input("Data inicial:", value=min_date_val, min_value=min_date_val, max_value=max_date_val, key="date_start")
                    with c2:
                        _e = st.date_input("Data final:", value=max_date_val, min_value=min_date_val, max_value=max_date_val, key="date_end")
                    date_date_sel = (_s, _e) if _s <= _e else (_e, _s)
                
                date_vis_type = st.radio("Tipus de visualització:", ["Línies", "Barres"], horizontal=True, key="date_vis")

                date_metrics_sel = st.multiselect(
                    "Mètriques a visualitzar (màx. 2):",
                    list(METRIC_COLS.keys()),
                    default=["Comptatge"],
                    key="date_metrics",
                )
                if len(date_metrics_sel) > 2:
                    st.warning("Només pots seleccionar fins a 2 opcions. S'utilitzaran les dues primeres.")
                    date_metrics_sel = date_metrics_sel[:2]
                if not date_metrics_sel:
                    date_metrics_sel = ["Comptatge"]
                date_no_zeros = st.checkbox("No mostrar zeros", value=False, key="date_no_zeros")
                    
            with col3_graf:
                st.markdown("##### Resultat Gràfic")
                if df_full.empty:
                    st.warning("No s'han trobat dades a la vista bat_observations_full.")
                else:
                    df_unfiltered = df_full.copy()
                    if "Totes" not in date_loc_sel and date_loc_sel:
                        df_unfiltered = df_unfiltered[df_unfiltered['location_name'].isin(date_loc_sel)]
                    start_d, end_d = date_date_sel
                    df_unfiltered = df_unfiltered[(df_unfiltered['observation_date'] >= start_d) & (df_unfiltered['observation_date'] <= end_d)]
                    
                    df_date = df_unfiltered.copy()
                    if "Totes" not in date_esp_sel and date_esp_sel:
                        df_date = df_date[df_date['species'].isin(date_esp_sel)]
                        
                    if df_date.empty:
                        st.info("Cap registre coincideix amb els filtres seleccionats.")
                    else:
                        df_unfiltered['obs_dt'] = pd.to_datetime(df_unfiltered['observation_date'])
                        df_unfiltered['month_year'] = df_unfiltered['obs_dt'].dt.to_period('M').dt.to_timestamp()
                        df_date['obs_dt'] = pd.to_datetime(df_date['observation_date'])
                        df_date['month_year'] = df_date['obs_dt'].dt.to_period('M').dt.to_timestamp()

                        import altair as alt
                        chart_date = None
                        m1_label = date_metrics_sel[0]
                        m1_col, m1_title = METRIC_COLS[m1_label]
                        is_dual = len(date_metrics_sel) == 2 and date_vis_type == "Línies"
                        c1_color, c2_color = CHART_DUAL_COLORS

                        if date_vis_type == "Línies":
                            df_date_grouped = calculate_ecological_indices(df_date, df_unfiltered, ["month_year"])
                            df_date_grouped = enrich_grouped_with_env(df_date, ["month_year"], df_date_grouped)
                            c1_ser = df_date_grouped[m1_col] if m1_col in df_date_grouped.columns else pd.Series(dtype=float)
                            if is_dual:
                                m2_label = date_metrics_sel[1]
                                m2_col, m2_title = METRIC_COLS[m2_label]
                                c2_ser = df_date_grouped[m2_col] if m2_col in df_date_grouped.columns else pd.Series(dtype=float)
                                dom1 = render_y_range_slider(c1_ser, "date_line_m1", m1_title, c1_color)
                                df_date_grouped = filter_by_range(df_date_grouped, m1_col, dom1, date_no_zeros)
                                dom2 = render_y_range_slider(c2_ser, "date_line_m2", m2_title, c2_color)
                                df_date_grouped = filter_by_range(df_date_grouped, m2_col, dom2, date_no_zeros)
                            else:
                                dom1 = render_y_range_slider(c1_ser, "date_line_m1", m1_title, c1_color)
                                dom2 = None
                                df_date_grouped = filter_by_range(df_date_grouped, m1_col, dom1, date_no_zeros)

                            if df_date_grouped.empty:
                                st.info("No hi ha punts dins del rang seleccionat o després d'aplicar 'No mostrar zeros'.")
                            else:
                                base3 = alt.Chart(df_date_grouped).encode(
                                    x=alt.X('month_year:T', title='Data (Mes - Any)', axis=alt.Axis(format='%m-%Y', labelAngle=-45, grid=False, tickCount='month'))
                                )
                                if is_dual:
                                    line1 = base3.mark_line(color=c1_color, point=True).encode(
                                        y=alt.Y(f'{m1_col}:Q', title=m1_title,
                                            axis=alt.Axis(titleColor=c1_color, grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]),
                                            scale=alt.Scale(domain=dom1) if dom1 else alt.Undefined)
                                    )
                                    line2 = base3.mark_line(color=c2_color, point=True).encode(
                                        y=alt.Y(f'{m2_col}:Q', title=m2_title,
                                            axis=alt.Axis(titleColor=c2_color, orient='right', grid=False),
                                            scale=alt.Scale(domain=dom2) if dom2 else alt.Undefined)
                                    )
                                    chart_date = alt.layer(line1, line2).resolve_scale(y='independent').properties(height=400).configure_axis(grid=False)
                                else:
                                    chart_date = base3.mark_line(color=c1_color, point=True).encode(
                                        y=alt.Y(f'{m1_col}:Q', title=m1_title,
                                            axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]),
                                            scale=alt.Scale(domain=dom1) if dom1 else alt.Undefined),
                                        tooltip=['month_year:T', f'{m1_col}:Q']
                                    ).properties(height=400).configure_axis(grid=False)
                        else:
                            df_date_grouped = calculate_ecological_indices(df_date, df_unfiltered, ["month_year", "species"])
                            df_date_grouped = enrich_grouped_with_env(df_date, ["month_year", "species"], df_date_grouped)
                            c1_ser = df_date_grouped[m1_col] if m1_col in df_date_grouped.columns else pd.Series(dtype=float)
                            dom1 = render_y_range_slider(c1_ser, "date_bar_m1", m1_title, c1_color)
                            df_date_grouped = filter_by_range(df_date_grouped, m1_col, dom1, date_no_zeros)

                            if df_date_grouped.empty:
                                st.info("No hi ha punts dins del rang seleccionat o després d'aplicar 'No mostrar zeros'.")
                            else:
                                chart_date = alt.Chart(df_date_grouped).mark_bar(size=35).encode(
                                    x=alt.X('month_year:T', title='Data (Mes - Any)', axis=alt.Axis(format='%m-%Y', labelAngle=-45, grid=False, tickCount='month')),
                                    y=alt.Y(f'{m1_col}:Q', title=m1_title,
                                        axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]),
                                        scale=alt.Scale(domain=dom1) if dom1 else alt.Undefined),
                                    color=alt.Color('species:N', title='Espècie', legend=alt.Legend(orient="bottom", columns=3)),
                                    tooltip=['month_year:T', 'species:N', f'{m1_col}:Q']
                                ).properties(height=400).configure_axis(grid=False)

                        if chart_date is not None:
                            st.altair_chart(chart_date, width="stretch")

        # --- Àrea 4: Comptatge i Buzz per franja horària ---
        st.subheader("Comptatge i Buzz per franja horària")
        with st.container(border=True):
            col4_filt, col4_graf = st.columns([1, 3])
            with col4_filt:
                st.markdown("##### Paràmetres")
                hour_esp_sel = st.multiselect("Selecciona Espècie(s):", ["Totes"] + all_species, default=["Totes"], key="hour_esp")
                hour_loc_sel = st.multiselect("Selecciona Localització:", ["Totes"] + all_locations, default=["Totes"], key="hour_loc")
                # Selector de dates
                hour_date_method = st.radio("Mètode de selecció de dates:", ["Desplaçador (Slider)", "Calendari Manual", "Només un dia"], horizontal=True, key="hour_date_method")
                if hour_date_method == "Desplaçador (Slider)":
                    hour_date_sel = st.slider("Rang de dates:", min_value=min_date_val, max_value=max_date_val, value=(min_date_val, max_date_val), key="hour_date_slider")
                elif hour_date_method == "Només un dia":
                    _d = st.date_input("Data:", value=min_date_val, min_value=min_date_val, max_value=max_date_val, key="hour_date")
                    hour_date_sel = (_d, _d)
                else:
                    c1, c2 = st.columns(2)
                    with c1:
                        _s = st.date_input("Data inicial:", value=min_date_val, min_value=min_date_val, max_value=max_date_val, key="hour_start")
                    with c2:
                        _e = st.date_input("Data final:", value=max_date_val, min_value=min_date_val, max_value=max_date_val, key="hour_end")
                    hour_date_sel = (_s, _e) if _s <= _e else (_e, _s)
                
                hour_vis_type = st.radio("Tipus de visualització:", ["Línies", "Barres"], horizontal=True, key="hour_vis")

                hour_metrics_sel = st.multiselect(
                    "Mètriques a visualitzar (màx. 2):",
                    list(METRIC_COLS.keys()),
                    default=["Comptatge"],
                    key="hour_metrics",
                )
                if len(hour_metrics_sel) > 2:
                    st.warning("Només pots seleccionar fins a 2 opcions. S'utilitzaran les dues primeres.")
                    hour_metrics_sel = hour_metrics_sel[:2]
                if not hour_metrics_sel:
                    hour_metrics_sel = ["Comptatge"]
                hour_no_zeros = st.checkbox("No mostrar zeros", value=False, key="hour_no_zeros")
                    
            with col4_graf:
                st.markdown("##### Resultat Gràfic")
                if df_full.empty:
                    st.warning("No s'han trobat dades a la vista bat_observations_full.")
                else:
                    df_unfiltered = df_full.copy()
                    if "Totes" not in hour_loc_sel and hour_loc_sel:
                        df_unfiltered = df_unfiltered[df_unfiltered['location_name'].isin(hour_loc_sel)]
                    start_d, end_d = hour_date_sel
                    df_unfiltered = df_unfiltered[(df_unfiltered['observation_date'] >= start_d) & (df_unfiltered['observation_date'] <= end_d)]
                    
                    df_hour = df_unfiltered.copy()
                    if "Totes" not in hour_esp_sel and hour_esp_sel:
                        df_hour = df_hour[df_hour['species'].isin(hour_esp_sel)]
                        
                    if df_hour.empty:
                        st.info("Cap registre coincideix amb els filtres seleccionats.")
                    else:
                        import altair as alt
                        chart_hour = None

                        if 'observation_hour' in df_unfiltered.columns:
                            df_unfiltered['hora'] = df_unfiltered['observation_hour'].astype(str).str.zfill(2)
                            df_hour['hora'] = df_hour['observation_hour'].astype(str).str.zfill(2)
                        else:
                            df_unfiltered['hora'] = 'Desconeguda'
                            df_hour['hora'] = 'Desconeguda'

                        ordre_nocturn = [str(i).zfill(2) for i in range(16, 24)] + [str(i).zfill(2) for i in range(0, 16)]
                        m1_label = hour_metrics_sel[0]
                        m1_col, m1_title = METRIC_COLS[m1_label]
                        is_dual = len(hour_metrics_sel) == 2 and hour_vis_type == "Línies"
                        c1_color, c2_color = CHART_DUAL_COLORS

                        if hour_vis_type == "Línies":
                            df_hour_grouped = calculate_ecological_indices(df_hour, df_unfiltered, ["hora"])
                            df_hour_grouped = enrich_grouped_with_env(df_hour, ["hora"], df_hour_grouped)
                            c1_ser = df_hour_grouped[m1_col] if m1_col in df_hour_grouped.columns else pd.Series(dtype=float)
                            if is_dual:
                                m2_label = hour_metrics_sel[1]
                                m2_col, m2_title = METRIC_COLS[m2_label]
                                c2_ser = df_hour_grouped[m2_col] if m2_col in df_hour_grouped.columns else pd.Series(dtype=float)
                                dom1 = render_y_range_slider(c1_ser, "hour_line_m1", m1_title, c1_color)
                                df_hour_grouped = filter_by_range(df_hour_grouped, m1_col, dom1, hour_no_zeros)
                                dom2 = render_y_range_slider(c2_ser, "hour_line_m2", m2_title, c2_color)
                                df_hour_grouped = filter_by_range(df_hour_grouped, m2_col, dom2, hour_no_zeros)
                            else:
                                dom1 = render_y_range_slider(c1_ser, "hour_line_m1", m1_title, c1_color)
                                dom2 = None
                                df_hour_grouped = filter_by_range(df_hour_grouped, m1_col, dom1, hour_no_zeros)

                            if df_hour_grouped.empty:
                                st.info("No hi ha punts dins del rang seleccionat o després d'aplicar 'No mostrar zeros'.")
                            else:
                                base4 = alt.Chart(df_hour_grouped).encode(
                                    x=alt.X('hora:O', title='Franja Horària (h)', sort=ordre_nocturn, axis=alt.Axis(labelAngle=0, grid=False))
                                )
                                if is_dual:
                                    line1 = base4.mark_line(color=c1_color, point=True).encode(
                                        y=alt.Y(f'{m1_col}:Q', title=m1_title,
                                            axis=alt.Axis(titleColor=c1_color, grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]),
                                            scale=alt.Scale(domain=dom1) if dom1 else alt.Undefined)
                                    )
                                    line2 = base4.mark_line(color=c2_color, point=True).encode(
                                        y=alt.Y(f'{m2_col}:Q', title=m2_title,
                                            axis=alt.Axis(titleColor=c2_color, orient='right', grid=False),
                                            scale=alt.Scale(domain=dom2) if dom2 else alt.Undefined)
                                    )
                                    chart_hour = alt.layer(line1, line2).resolve_scale(y='independent').properties(height=400).configure_axis(grid=False)
                                else:
                                    chart_hour = base4.mark_line(color=c1_color, point=True).encode(
                                        y=alt.Y(f'{m1_col}:Q', title=m1_title,
                                            axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]),
                                            scale=alt.Scale(domain=dom1) if dom1 else alt.Undefined),
                                        tooltip=['hora:O', f'{m1_col}:Q']
                                    ).properties(height=400).configure_axis(grid=False)
                        else:
                            df_hour_grouped = calculate_ecological_indices(df_hour, df_unfiltered, ["hora", "species"])
                            df_hour_grouped = enrich_grouped_with_env(df_hour, ["hora", "species"], df_hour_grouped)
                            c1_ser = df_hour_grouped[m1_col] if m1_col in df_hour_grouped.columns else pd.Series(dtype=float)
                            dom1 = render_y_range_slider(c1_ser, "hour_bar_m1", m1_title, c1_color)
                            df_hour_grouped = filter_by_range(df_hour_grouped, m1_col, dom1, hour_no_zeros)

                            if df_hour_grouped.empty:
                                st.info("No hi ha punts dins del rang seleccionat o després d'aplicar 'No mostrar zeros'.")
                            else:
                                chart_hour = alt.Chart(df_hour_grouped).mark_bar(size=22).encode(
                                    x=alt.X('hora:O', title='Franja Horària (h)', sort=ordre_nocturn, axis=alt.Axis(labelAngle=0, grid=False)),
                                    y=alt.Y(f'{m1_col}:Q', title=m1_title,
                                        axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]),
                                        scale=alt.Scale(domain=dom1) if dom1 else alt.Undefined),
                                    color=alt.Color('species:N', title='Espècie', legend=alt.Legend(orient="bottom", columns=3)),
                                    tooltip=['hora:O', 'species:N', f'{m1_col}:Q']
                                ).properties(height=400).configure_axis(grid=False)

                        if chart_hour is not None:
                            st.altair_chart(chart_hour, width="stretch")

        # --- Àrea 5: Regressió Linial ---
        st.subheader("Anàlisi de Regressió Linial")
        with st.container(border=True):
            col5_filt, col5_graf = st.columns([1, 3])
            with col5_filt:
                st.markdown("##### Paràmetres")
                reg_esp_sel = st.multiselect("Selecciona Espècie(s):", ["Totes"] + all_species, default=["Totes"], key="reg_esp")
                reg_loc_sel = st.multiselect("Selecciona Localització:", ["Totes"] + all_locations, default=["Totes"], key="reg_loc")
                # Selector de dates
                reg_date_method = st.radio("Mètode de selecció de dates:", ["Desplaçador (Slider)", "Calendari Manual", "Només un dia"], horizontal=True, key="reg_date_method")
                if reg_date_method == "Desplaçador (Slider)":
                    reg_date_sel = st.slider("Rang de dates:", min_value=min_date_val, max_value=max_date_val, value=(min_date_val, max_date_val), key="reg_date_slider")
                elif reg_date_method == "Només un dia":
                    _d = st.date_input("Data:", value=min_date_val, min_value=min_date_val, max_value=max_date_val, key="reg_date")
                    reg_date_sel = (_d, _d)
                else:
                    c1, c2 = st.columns(2)
                    with c1:
                        _s = st.date_input("Data inicial:", value=min_date_val, min_value=min_date_val, max_value=max_date_val, key="reg_start")
                    with c2:
                        _e = st.date_input("Data final:", value=max_date_val, min_value=min_date_val, max_value=max_date_val, key="reg_end")
                    reg_date_sel = (_s, _e) if _s <= _e else (_e, _s)
                
                st.markdown("##### Variables de Regressió")
                reg_y_var = st.selectbox("Variable Eix Y (Dependent):", list(METRIC_COLS.keys()), key="reg_y_var")

                reg_x_var = st.selectbox("Variable Eix X (Independent):", list(METRIC_COLS.keys()), key="reg_x_var")
                reg_x_col = METRIC_COLS.get(reg_x_var, ("total_count", ""))[0]
                
                st.markdown("##### Opcions d'Anàlisi")
                reg_outliers = st.checkbox("Mostra tots els punts (Inclou Outliers)", value=True, key="reg_outliers")
                reg_no_zeros = st.checkbox("No mostrar zeros", value=False, key="reg_no_zeros")
                
            with col5_graf:
                st.markdown("##### Resultat Gràfic i Estadístiques")
                if df_full.empty:
                    st.warning("No s'han trobat dades a la vista bat_observations_full.")
                else:
                    df_reg = df_full.copy()
                    
                    if "Totes" not in reg_esp_sel and reg_esp_sel:
                        df_reg = df_reg[df_reg['species'].isin(reg_esp_sel)]
                        
                    if "Totes" not in reg_loc_sel and reg_loc_sel:
                        df_reg = df_reg[df_reg['location_name'].isin(reg_loc_sel)]
                        
                    start_d, end_d = reg_date_sel
                    df_reg = df_reg[(df_reg['observation_date'] >= start_d) & (df_reg['observation_date'] <= end_d)]
                    
                    # Calcular OA, OT, IA de cada hora (N=60 per hora de granularitat de minuts)
                    df_reg['N'] = 60
                    df_reg['OA'] = df_reg['total_count'] / df_reg['N']
                    df_reg['OT'] = df_reg['total_buzz'] / df_reg['N']
                    df_reg['IA'] = df_reg.apply(lambda row: row['total_buzz'] / row['total_count'] if row['total_count'] > 0 else 0.0, axis=1)
                    
                    y_col = METRIC_COLS.get(reg_y_var, ("total_count", ""))[0]
                    x_col = reg_x_col
                    import numpy as np
                    
                    # Eliminar files on X o Y siguin NaN per no falsejar la regressió
                    df_reg_clean = df_reg.dropna(subset=[x_col, y_col]).copy()
                    df_reg_clean[x_col] = pd.to_numeric(df_reg_clean[x_col], errors='coerce')
                    df_reg_clean[y_col] = pd.to_numeric(df_reg_clean[y_col], errors='coerce')
                    df_reg_clean = df_reg_clean.dropna(subset=[x_col, y_col])
                    df_reg_clean = df_reg_clean[
                        np.isfinite(df_reg_clean[x_col]) & np.isfinite(df_reg_clean[y_col])
                    ]

                    if reg_no_zeros and not df_reg_clean.empty:
                        df_reg_clean = df_reg_clean[(df_reg_clean[x_col] != 0) & (df_reg_clean[y_col] != 0)]
                    
                    if not reg_outliers and not df_reg_clean.empty:
                        # Mètode IQR (Interquartile Range) per netejar outliers en ambdues variables
                        for col in [x_col, y_col]:
                            Q1 = df_reg_clean[col].quantile(0.25)
                            Q3 = df_reg_clean[col].quantile(0.75)
                            IQR = Q3 - Q1
                            if pd.isna(IQR):
                                continue
                            lower_bound = Q1 - 1.5 * IQR
                            upper_bound = Q3 + 1.5 * IQR
                            df_reg_clean = df_reg_clean[(df_reg_clean[col] >= lower_bound) & (df_reg_clean[col] <= upper_bound)]

                    
                    if df_reg_clean.empty or len(df_reg_clean) < 2:
                        st.info("No hi ha prou dades vàlides per aquesta combinació (mínim 2 punts amb valors no nuls).")
                    else:
                        import altair as alt
                        import numpy as np
                        
                        # Càlcul de la regressió lineal
                        x_vals = df_reg_clean[x_col].to_numpy(dtype=float)
                        y_vals = df_reg_clean[y_col].to_numpy(dtype=float)

                        finite_mask = np.isfinite(x_vals) & np.isfinite(y_vals)
                        if not finite_mask.all():
                            df_reg_clean = df_reg_clean.loc[finite_mask].copy()
                            x_vals = x_vals[finite_mask]
                            y_vals = y_vals[finite_mask]

                        if len(x_vals) < 2 or np.unique(x_vals).size < 2:
                            st.info("No hi ha prou variabilitat a l'eix X per calcular una regressió lineal fiable.")
                            chart_reg = alt.Chart(df_reg_clean).mark_circle(size=60, opacity=0.6, color='#1f77b4').encode(
                                x=alt.X(f'{x_col}:Q', title=reg_x_var, scale=alt.Scale(zero=False)),
                                y=alt.Y(f'{y_col}:Q', title=reg_y_var),
                                tooltip=[f'{x_col}:Q', f'{y_col}:Q', 'species:N', 'location_name:N']
                            ).properties(height=350)
                            st.altair_chart(chart_reg, width="stretch")
                        else:
                            try:
                                # polyfit grau 1 retorna [pendent, intercept]
                                m, b = np.polyfit(x_vals, y_vals, 1)
                            except (np.linalg.LinAlgError, ValueError, FloatingPointError):
                                st.warning("No s'ha pogut ajustar la regressió per inestabilitat numèrica. Es mostren només els punts.")
                                chart_reg = alt.Chart(df_reg_clean).mark_circle(size=60, opacity=0.6, color='#1f77b4').encode(
                                    x=alt.X(f'{x_col}:Q', title=reg_x_var, scale=alt.Scale(zero=False)),
                                    y=alt.Y(f'{y_col}:Q', title=reg_y_var),
                                    tooltip=[f'{x_col}:Q', f'{y_col}:Q', 'species:N', 'location_name:N']
                                ).properties(height=350)
                                st.altair_chart(chart_reg, width="stretch")
                            else:
                                # R2 robust: if one axis is constant, correlation is undefined.
                                if np.std(x_vals) == 0 or np.std(y_vals) == 0:
                                    r_squared = 0.0
                                else:
                                    corr_matrix = np.corrcoef(x_vals, y_vals)
                                    corr = corr_matrix[0, 1]
                                    r_squared = float(corr ** 2) if np.isfinite(corr) else 0.0
                        
                                # Afegim la columna de predicció per pintar la línia
                                df_reg_clean['prediction'] = m * df_reg_clean[x_col] + b

                                # Mostrem els coeficients en caixes de mètriques
                                c1, c2, c3 = st.columns(3)
                                c1.metric("Pendent (m)", f"{m:.4f}")
                                c2.metric("Intercepció (b)", f"{b:.4f}")
                                c3.metric("Coef. Determinació (R²)", f"{r_squared:.4f}")

                                st.markdown("<br>", unsafe_allow_html=True)

                                # Gràfic de dispersió (Scatter)
                                scatter = alt.Chart(df_reg_clean).mark_circle(size=60, opacity=0.6, color='#1f77b4').encode(
                                    x=alt.X(f'{x_col}:Q', title=reg_x_var, scale=alt.Scale(zero=False)),
                                    y=alt.Y(f'{y_col}:Q', title=reg_y_var),
                                    tooltip=[f'{x_col}:Q', f'{y_col}:Q', 'species:N', 'location_name:N']
                                )

                                # Línia de regressió
                                regression_line = alt.Chart(df_reg_clean).mark_line(color='red', size=3).encode(
                                    x=f'{x_col}:Q',
                                    y='prediction:Q'
                                )

                                chart_reg = (scatter + regression_line).properties(height=350)

                                st.altair_chart(chart_reg, width="stretch")

        # --- Àrea 6: Mapa de calor multidimensional ---
        st.subheader("Mapa de Calor Multidimensional")
        st.markdown("Creua dues dimensions (espècie, localització, hora o mes) per detectar patrons d'activitat amb una matriu de color.")
        with st.container(border=True):
            # Selectable dimensions and metrics for the heatmap matrix.
            HEAT_DIMS = {
                "species": "Espècie",
                "location_name": "Localització",
                "hora": "Franja Horària",
                "month_year": "Mes - Any",
            }
            HEAT_METRICS = {
                "Comptatge": ("total_count", "Comptatge Total"),
                "Buzz": ("total_buzz", "Total Buzz"),
                "OA (Ocupació Acústica)": ("OA", "Índex OA"),
                "OT (Ocupació Tròfica)": ("OT", "Índex OT"),
                "IA (Intensitat Depredadora)": ("IA", "Índex IA"),
            }
            col6_filt, col6_graf = st.columns([1, 3])
            with col6_filt:
                st.markdown("##### Paràmetres")
                heat_esp_sel = st.multiselect("Espècie(s):", ["Totes"] + all_species, default=["Totes"], key="heat_esp")
                heat_loc_sel = st.multiselect("Localització:", ["Totes"] + all_locations, default=["Totes"], key="heat_loc")
                heat_date_sel = st.slider("Rang de dates:", min_value=min_date_val, max_value=max_date_val, value=(min_date_val, max_date_val), key="heat_date_slider")
                heat_metric_lbl = st.selectbox("Mètrica (color):", list(HEAT_METRICS.keys()), key="heat_metric")
                heat_x_lbl = st.selectbox("Dimensió eix X:", list(HEAT_DIMS.values()), index=2, key="heat_x")
                heat_y_lbl = st.selectbox("Dimensió eix Y:", list(HEAT_DIMS.values()), index=0, key="heat_y")
                heat_scheme = st.selectbox("Paleta de color:", ["viridis", "plasma", "turbo", "magma", "inferno", "cividis"], index=2, key="heat_scheme")
                heat_show_text = st.checkbox("Mostra els valors a les cel·les", value=True, key="heat_show_text")
                if "heat_font_size" not in st.session_state:
                    st.session_state["heat_font_size"] = 12
                st.markdown("Mida de la font dels valors")
                font_col_minus, font_col_value, font_col_plus = st.columns([1, 2, 1])
                with font_col_minus:
                    if st.button("-", key="heat_font_minus"):
                        st.session_state["heat_font_size"] = max(6, st.session_state["heat_font_size"] - 1)
                with font_col_value:
                    st.caption(f"{st.session_state['heat_font_size']} pt")
                with font_col_plus:
                    if st.button("+", key="heat_font_plus"):
                        st.session_state["heat_font_size"] = min(36, st.session_state["heat_font_size"] + 1)

            with col6_graf:
                st.markdown("##### Resultat Gràfic")
                # Reverse-map the displayed Catalan labels back to column names.
                lbl_to_col = {v: k for k, v in HEAT_DIMS.items()}
                heat_x_col = lbl_to_col[heat_x_lbl]
                heat_y_col = lbl_to_col[heat_y_lbl]

                if df_full.empty:
                    st.warning("No s'han trobat dades a la vista bat_observations_full.")
                elif heat_x_col == heat_y_col:
                    st.info("Selecciona dues dimensions diferents per als eixos X i Y.")
                else:
                    import altair as alt

                    df_heat_unf = df_full.copy()
                    if "Totes" not in heat_loc_sel and heat_loc_sel:
                        df_heat_unf = df_heat_unf[df_heat_unf['location_name'].isin(heat_loc_sel)]
                    h_start, h_end = heat_date_sel
                    df_heat_unf = df_heat_unf[(df_heat_unf['observation_date'] >= h_start) & (df_heat_unf['observation_date'] <= h_end)]

                    df_heat = df_heat_unf.copy()
                    if "Totes" not in heat_esp_sel and heat_esp_sel:
                        df_heat = df_heat[df_heat['species'].isin(heat_esp_sel)]

                    # Derive the synthetic dimension columns used as axes.
                    for _df in (df_heat_unf, df_heat):
                        if 'observation_hour' in _df.columns:
                            _df['hora'] = _df['observation_hour'].astype('Int64').astype(str).str.zfill(2)
                        else:
                            _df['hora'] = 'Desconeguda'
                        _df['month_year'] = pd.to_datetime(_df['observation_date'], errors='coerce').dt.strftime('%Y-%m')

                    if df_heat.empty:
                        st.info("Cap registre coincideix amb els filtres seleccionats.")
                    else:
                        group_cols = [heat_x_col, heat_y_col]
                        df_heat_grouped = calculate_ecological_indices(df_heat, df_heat_unf, group_cols)
                        metric_col, metric_title = HEAT_METRICS[heat_metric_lbl]

                        # Keep hours in chronological nocturnal order on whichever axis uses them.
                        ordre_nocturn = [str(i).zfill(2) for i in range(16, 24)] + [str(i).zfill(2) for i in range(0, 16)]
                        x_sort = ordre_nocturn if heat_x_col == 'hora' else 'ascending'
                        y_sort = ordre_nocturn if heat_y_col == 'hora' else 'ascending'

                        base_heat = alt.Chart(df_heat_grouped).encode(
                            x=alt.X(f'{heat_x_col}:N', title=heat_x_lbl, sort=x_sort, axis=alt.Axis(labelAngle=-45)),
                            y=alt.Y(f'{heat_y_col}:N', title=heat_y_lbl, sort=y_sort),
                        )
                        heat_rects = base_heat.mark_rect().encode(
                            color=alt.Color(f'{metric_col}:Q', title=metric_title, scale=alt.Scale(scheme=heat_scheme)),
                            tooltip=[
                                alt.Tooltip(f'{heat_x_col}:N', title=heat_x_lbl),
                                alt.Tooltip(f'{heat_y_col}:N', title=heat_y_lbl),
                                alt.Tooltip(f'{metric_col}:Q', title=metric_title, format=".4f"),
                            ],
                        )
                        chart_heat = heat_rects
                        if heat_show_text:
                            text_fmt = ".0f" if metric_col in ("total_count", "total_buzz") else ".2f"
                            heat_text = base_heat.mark_text(baseline='middle', fontSize=st.session_state["heat_font_size"]).encode(
                                text=alt.Text(f'{metric_col}:Q', format=text_fmt),
                                color=alt.value('white'),
                            )
                            chart_heat = heat_rects + heat_text

                        n_rows = df_heat_grouped[heat_y_col].nunique()
                        chart_height = max(300, min(900, n_rows * 28))
                        chart_heat = chart_heat.properties(height=chart_height).configure_view(strokeWidth=0)
                        st.altair_chart(chart_heat, width="stretch")

    # ---------------- TAB 2: MAPA ----------------
    with tab_mapa:
        st.header("Visualització Geogràfica de Mètriques")
        st.markdown("Filtra com sempre i escull el mode de representació del mapa per comparar espècies, intensitat o composició.")

        if df_full.empty:
            st.warning("No s'han pogut carregar les dades de ratpenats per a la visualització geogràfica.")
        else:
            import datetime
            import numpy as np
            import pydeck as pdk

            all_species = sorted(df_full['species'].dropna().unique().tolist()) if 'species' in df_full.columns else []
            all_locations = sorted(df_full['location_name'].dropna().unique().tolist()) if 'location_name' in df_full.columns else []

            min_date_val = df_full['observation_date'].dropna().min() if 'observation_date' in df_full.columns else None
            max_date_val = df_full['observation_date'].dropna().max() if 'observation_date' in df_full.columns else None
            if pd.isna(min_date_val) or pd.isna(max_date_val):
                min_date_val = datetime.date(2020, 1, 1)
                max_date_val = datetime.date.today()
            if min_date_val == max_date_val:
                min_date_val = min_date_val - datetime.timedelta(days=1)
                max_date_val = max_date_val + datetime.timedelta(days=1)

            col_map_filters, col_map_view = st.columns([1, 3])

            with col_map_filters:
                st.markdown("##### Paràmetres")
                map_species_sel = st.multiselect("Espècie(s):", ["Totes"] + all_species, default=["Totes"], key="map_species")
                map_locations_sel = st.multiselect("Localització(ns):", ["Totes"] + all_locations, default=["Totes"], key="map_locations")
                map_dates_sel = st.slider(
                    "Rang de dates:",
                    min_value=min_date_val,
                    max_value=max_date_val,
                    value=(min_date_val, max_date_val),
                    key="map_dates",
                )

                map_metric_label = st.selectbox("Mètrica:", list(METRIC_COLS.keys()), index=0, key="map_metric")
                map_render_mode = st.selectbox(
                    "Visualització:",
                    ["Bombolles per espècie", "Mapa d'escalfor"],
                    index=0,
                    key="map_render_mode",
                )
                map_no_zeros = st.checkbox("No mostrar zeros", value=False, key="map_no_zeros")
                map_height = st.slider("Alçada del mapa (px)", min_value=520, max_value=1200, value=860, step=20, key="map_height")

                # Force a taller map container and keep map gestures isolated from page scroll.
                st.markdown(
                    f"""
                    <style>
                    div[data-testid="stDeckGlJsonChart"] {{
                        height: {int(map_height)}px !important;
                        overscroll-behavior: contain;
                    }}
                    div[data-testid="stDeckGlJsonChart"] iframe {{
                        height: {int(map_height)}px !important;
                    }}
                    div[data-testid="stDeckGlJsonChart"] canvas {{
                        touch-action: none;
                    }}
                    </style>
                    """,
                    unsafe_allow_html=True,
                )

                if map_render_mode == "Bombolles per espècie":
                    min_radius = st.slider("Radi mínim", min_value=100, max_value=1500, value=250, step=50, key="map_min_radius")
                    max_radius = st.slider("Radi màxim", min_value=300, max_value=4000, value=1800, step=100, key="map_max_radius")
                    if max_radius <= min_radius:
                        max_radius = min_radius + 100
                        st.caption("S'ha ajustat el radi màxim perquè sigui superior al mínim.")
                    radius_scale = st.selectbox("Escala del radi:", ["Arrel quadrada", "Lineal"], index=0, key="map_radius_scale")
                    bubble_offset = st.checkbox("Separar espècies en la mateixa localització", value=True, key="map_bubble_offset")
                    offset_m = st.slider("Separació (metres)", min_value=0, max_value=800, value=220, step=20, key="map_offset_m")
                else:
                    heat_radius = st.slider("Radi de calor (px)", min_value=20, max_value=220, value=95, step=5, key="map_heat_radius")
                    heat_intensity = st.slider("Intensitat", min_value=0.2, max_value=5.0, value=1.4, step=0.1, key="map_heat_intensity")
                    heat_threshold = st.slider("Llindar", min_value=0.0, max_value=1.0, value=0.03, step=0.01, key="map_heat_threshold")
                    show_heat_points = st.checkbox("Mostrar punts de suport", value=True, key="map_show_heat_points")
                    heat_palette = st.selectbox(
                        "Paleta de colors (calor):",
                        ["Inferno", "Viridis", "Turbo", "Blau -> Vermell", "Verd -> Groc -> Vermell"],
                        index=0,
                        key="map_heat_palette",
                    )

            with col_map_view:
                st.markdown("##### Mapa")
                df_map_source = df_full.copy()
                if "Totes" not in map_locations_sel and map_locations_sel:
                    df_map_source = df_map_source[df_map_source['location_name'].isin(map_locations_sel)]
                if "Totes" not in map_species_sel and map_species_sel:
                    df_map_source = df_map_source[df_map_source['species'].isin(map_species_sel)]

                start_d, end_d = map_dates_sel
                df_map_source = df_map_source[
                    (df_map_source['observation_date'] >= start_d) & (df_map_source['observation_date'] <= end_d)
                ]

                if df_map_source.empty:
                    st.info("Cap registre coincideix amb els filtres seleccionats.")
                else:
                    metric_col, metric_title = METRIC_COLS[map_metric_label]
                    if map_render_mode == "Bombolles per espècie":
                        group_cols = ["location_name", "species"]
                        df_metric = compute_metric_grouped(df_map_source, metric_col, group_cols)

                        if map_no_zeros and not df_metric.empty:
                            df_metric = df_metric[pd.to_numeric(df_metric[metric_col], errors='coerce') != 0]

                        if df_metric.empty:
                            st.info("No hi ha valors per mostrar al mapa amb aquesta configuració.")
                        else:
                            df_map = merge_metric_with_coordinates(df_metric)
                            df_map[metric_col] = pd.to_numeric(df_map[metric_col], errors='coerce')
                            df_map = df_map[df_map[metric_col].notna()].copy()

                            if df_map.empty:
                                st.warning("No s'han pogut enllaçar localitzacions amb coordenades per als filtres actuals.")
                            else:
                                df_map["species"] = df_map["species"].fillna("Sense espècie").astype(str)
                                palette = [
                                    [31, 119, 180, 190], [255, 127, 14, 190], [44, 160, 44, 190],
                                    [214, 39, 40, 190], [148, 103, 189, 190], [140, 86, 75, 190],
                                    [227, 119, 194, 190], [127, 127, 127, 190], [188, 189, 34, 190],
                                    [23, 190, 207, 190],
                                ]
                                species_values = sorted(df_map["species"].unique().tolist())
                                species_color = {s: palette[i % len(palette)] for i, s in enumerate(species_values)}
                                df_map["color"] = df_map["species"].astype(str).map(species_color)

                                vals = df_map[metric_col].astype(float)
                                vmin = float(vals.min())
                                vmax = float(vals.max())
                                if vmax > vmin:
                                    norm = ((vals - vmin) / (vmax - vmin)).clip(0, 1)
                                else:
                                    norm = pd.Series([0.5] * len(df_map), index=df_map.index)

                                if radius_scale == "Arrel quadrada":
                                    norm = np.sqrt(norm)
                                df_map["radius"] = min_radius + norm * (max_radius - min_radius)

                                df_map["latitude_plot"] = df_map["latitude"].astype(float)
                                df_map["longitude_plot"] = df_map["longitude"].astype(float)
                                if bubble_offset and offset_m > 0:
                                    df_map = df_map.sort_values(by=["location_name", metric_col], ascending=[True, False]).copy()
                                    df_map["species_rank"] = df_map.groupby("location_name").cumcount()
                                    df_map["species_count"] = df_map.groupby("location_name")["species"].transform("count")
                                    df_map["angle"] = (2 * np.pi * df_map["species_rank"]) / df_map["species_count"].clip(lower=1)

                                    lat_scale = offset_m / 111320.0
                                    safe_cos = np.cos(np.radians(df_map["latitude_plot"].astype(float))).clip(lower=0.2)
                                    lon_scale = offset_m / (111320.0 * safe_cos)

                                    df_map["latitude_plot"] = df_map["latitude_plot"] + lat_scale * np.sin(df_map["angle"])
                                    df_map["longitude_plot"] = df_map["longitude_plot"] + lon_scale * np.cos(df_map["angle"])

                                df_map["metric_value"] = np.round(df_map[metric_col].astype(float), 4)
                                map_center_lat = float(df_map["latitude"].mean())
                                map_center_lon = float(df_map["longitude"].mean())

                                layer = pdk.Layer(
                                    "ScatterplotLayer",
                                    data=df_map,
                                    get_position='[longitude_plot, latitude_plot]',
                                    get_fill_color='color',
                                    get_radius='radius',
                                    pickable=True,
                                    stroked=True,
                                    get_line_color=[25, 25, 25],
                                    line_width_min_pixels=1,
                                )

                                tooltip_html = (
                                    f"<b>{{location_name}}</b><br/>Espècie: {{species}}"
                                    f"<br/>{metric_title}: {{metric_value}}"
                                )
                                deck = pdk.Deck(
                                    map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                                    initial_view_state=pdk.ViewState(
                                        latitude=map_center_lat,
                                        longitude=map_center_lon,
                                        zoom=9,
                                        pitch=0,
                                    ),
                                    parameters={
                                        "scrollZoom": False,
                                        "dragPan": True,
                                        "doubleClickZoom": False,
                                        "touchRotate": False,
                                    },
                                    layers=[layer],
                                    tooltip={
                                        "html": tooltip_html,
                                        "style": {"backgroundColor": "#111111", "color": "#ffffff"},
                                    },
                                )
                                st.pydeck_chart(deck, width="stretch")
                                st.caption("Navegació: arrossega per desplaçar el mapa. El zoom es fa amb controls del trackpad/pellizc al mapa (scroll de pàgina desactivat dins del mapa).")

                                render_species_legend(species_color, "Llegenda d'espècies")

                                with st.expander("Detall de dades georeferenciades"):
                                    detail_df = build_map_detail_table(df_map, metric_col)
                                    st.dataframe(detail_df.sort_values(by=metric_col, ascending=False), width="stretch", hide_index=True)

                    elif map_render_mode == "Mapa d'escalfor":
                        group_cols = ["location_name"]
                        df_metric = compute_metric_grouped(df_map_source, metric_col, group_cols)

                        if map_no_zeros and not df_metric.empty:
                            df_metric = df_metric[pd.to_numeric(df_metric[metric_col], errors='coerce') != 0]

                        if df_metric.empty:
                            st.info("No hi ha valors per mostrar al mapa amb aquesta configuració.")
                        else:
                            df_map = merge_metric_with_coordinates(df_metric)
                            df_map[metric_col] = pd.to_numeric(df_map[metric_col], errors='coerce')
                            df_map = df_map[df_map[metric_col].notna()].copy()

                            if df_map.empty:
                                st.warning("No s'han pogut enllaçar localitzacions amb coordenades per als filtres actuals.")
                            else:
                                vals = df_map[metric_col].astype(float)
                                if len(vals) > 1:
                                    p_low = float(np.percentile(vals, 5))
                                    p_high = float(np.percentile(vals, 95))
                                else:
                                    p_low = float(vals.iloc[0])
                                    p_high = float(vals.iloc[0])

                                if p_high > p_low:
                                    norm = ((vals - p_low) / (p_high - p_low)).clip(0, 1)
                                else:
                                    norm = pd.Series([0.65] * len(df_map), index=df_map.index)

                                df_map["weight"] = norm + 0.02
                                df_map["support_radius"] = 140 + 520 * norm
                                df_map["metric_value"] = np.round(vals, 4)

                                heat_color_ranges = {
                                    "Inferno": [[0, 0, 4], [31, 12, 72], [85, 15, 109], [136, 34, 106], [186, 54, 85], [227, 89, 51], [249, 140, 10], [252, 195, 58], [252, 255, 164]],
                                    "Viridis": [[68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142], [38, 130, 142], [31, 158, 137], [53, 183, 121], [109, 205, 89], [180, 222, 44], [253, 231, 37]],
                                    "Turbo": [[48, 18, 59], [50, 64, 147], [31, 122, 184], [37, 173, 129], [133, 209, 63], [222, 216, 45], [251, 170, 24], [239, 96, 21], [180, 4, 38]],
                                    "Blau -> Vermell": [[49, 54, 149], [69, 117, 180], [116, 173, 209], [171, 217, 233], [224, 243, 248], [254, 224, 144], [253, 174, 97], [244, 109, 67], [215, 48, 39], [165, 0, 38]],
                                    "Verd -> Groc -> Vermell": [[0, 104, 55], [26, 152, 80], [102, 189, 99], [166, 217, 106], [217, 239, 139], [255, 255, 191], [254, 224, 139], [253, 174, 97], [244, 109, 67], [215, 48, 39], [165, 0, 38]],
                                }
                                color_range = heat_color_ranges.get(heat_palette, heat_color_ranges["Inferno"])

                                map_center_lat = float(df_map["latitude"].mean())
                                map_center_lon = float(df_map["longitude"].mean())

                                heat_layer = pdk.Layer(
                                    "HeatmapLayer",
                                    data=df_map,
                                    get_position='[longitude, latitude]',
                                    get_weight='weight',
                                    intensity=float(heat_intensity),
                                    threshold=float(heat_threshold),
                                    radiusPixels=int(heat_radius),
                                    colorRange=color_range,
                                    aggregation="SUM",
                                )

                                layers = [heat_layer]
                                if show_heat_points:
                                    support_layer = pdk.Layer(
                                        "ScatterplotLayer",
                                        data=df_map,
                                        get_position='[longitude, latitude]',
                                        get_fill_color=[18, 18, 18, 95],
                                        get_radius='support_radius',
                                        pickable=True,
                                        stroked=True,
                                        get_line_color=[245, 245, 245],
                                        line_width_min_pixels=1,
                                    )
                                    layers.append(support_layer)

                                tooltip_html = f"<b>{{location_name}}</b><br/>{metric_title}: {{metric_value}}"
                                deck = pdk.Deck(
                                    map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                                    initial_view_state=pdk.ViewState(
                                        latitude=map_center_lat,
                                        longitude=map_center_lon,
                                        zoom=9,
                                        pitch=25,
                                    ),
                                    parameters={
                                        "scrollZoom": False,
                                        "dragPan": True,
                                        "doubleClickZoom": False,
                                        "touchRotate": False,
                                    },
                                    layers=layers,
                                    tooltip={
                                        "html": tooltip_html,
                                        "style": {"backgroundColor": "#111111", "color": "#ffffff"},
                                    },
                                )
                                st.pydeck_chart(deck, width="stretch")
                                st.caption("Navegació: arrossega per desplaçar el mapa. El zoom amb scroll queda desactivat per evitar conflictes amb la pàgina.")

                                st.caption(
                                    f"Escala calor ({heat_palette}) · rang visualitzat: {float(vals.min()):.4f} - {float(vals.max()):.4f}"
                                )

                                with st.expander("Detall de dades georeferenciades"):
                                    detail_df = build_map_detail_table(df_map, metric_col)
                                    st.dataframe(detail_df.sort_values(by=metric_col, ascending=False), width="stretch", hide_index=True)

                    else:
                        st.info("Mode de visualització no disponible.")

    # ---------------- TAB 3: ESTATUS ----------------
    with tab_estatus:
        st.subheader("Salut i Metadades de la Base de Dades")
        st.markdown("A continuació es mostren les mètriques generals de les taules connectades.")
        
        # Add a refresh button within the tab
        if st.button("🔄 Refrescar Estatus"):
            st.rerun()
            
        with st.spinner("Connectant i calculant mètriques..."):
            try:
                # Real verification: Attempt to read table metadata for all 5 tables
                tables = ["file_registry", "weather_observations_history", "locations", "weather_metrics", "weather_stations"]
                counts = {}
                
                for table in tables:
                    query_resp = supabase_client.table(table).select("count", count='exact').limit(1).execute()
                    counts[table] = query_resp.count if query_resp.count is not None else 0
                
                # Display Information Cards natively using metric containers
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(label="file_registry", value=f"{counts['file_registry']} files")
                    st.metric(label="weather_metrics", value=f"{counts['weather_metrics']} mèt.")
                with col2:
                    st.metric(label="weather_obs_history", value=f"{counts['weather_observations_history']} obs.")
                    st.metric(label="weather_stations", value=f"{counts['weather_stations']} est.")
                with col3:
                    st.metric(label="locations", value=f"{counts['locations']} llocs")
                    st.metric(label="Estat General", value="🟢 Actiu", delta="Base de Dades", delta_color="normal")
                    
            except Exception as e:
                st.error(f"❌ Error establint o verificant connexió: {e}")

        st.divider()
        st.subheader("Llistats i Dades de Referència")
        
        col_list1, col_list2 = st.columns(2)
        
        with col_list1:
            st.markdown("**Mètriques Meteorològiques**")
            st.caption("Variables que s'estan recollint a la BD.")
            try:
                metrics_resp = supabase_client.table("weather_metrics").select("name_ca").order("name_ca").execute()
                if metrics_resp.data:
                    st.dataframe(pd.DataFrame(metrics_resp.data), width="stretch", hide_index=True)
                else:
                    st.info("Cap mètrica enregistrada.")
            except Exception as e:
                st.error(f"Error carregant mètriques: {e}")

        with col_list2:
            st.markdown("**Vista georeferenciada (locations_and_stations)**")
            st.caption("Mostra de registres retornats per la vista per a validació de camps.")
            try:
                loc_view_resp = supabase_client.table("locations_and_stations").select("*").limit(200).execute()
                if loc_view_resp.data:
                    st.dataframe(pd.DataFrame(loc_view_resp.data), width="stretch", hide_index=True)
                else:
                    st.info("La vista locations_and_stations no retorna registres.")
            except Exception as e:
                st.error(f"Error carregant la vista locations_and_stations: {e}")

    # ---------------- TAB 3: SYLLABUS / METODOLOGIA ----------------
    with tab_syllabus:
        st.header("Syllabus i Metodologia de Càlcul")
        st.markdown("Aquesta secció detalla la naturalesa de les dades recollides i com es calculen els indicadors d'activitat de l'aplicació per garantir la rigorositat i transparència científica.")
        
        st.subheader("1. Diccionari de Dades (Camps Principals)")
        st.markdown("""
        Cada registre de la base de dades representa un interval de gravació i procés acústic automàtic de l'estació autònoma.
        
        - **`observation_date`** / **`observation_hour`**: Marca temporal i franja horària associada a la gravació.
        - **`location_name`**: Nom del lloc de mostreig on està situada l'estació.
        - **`species`**: Espècie (o grup fònic) identificada pel programari d'anàlisi automàtic.
        - **`total_count` (Comptatge)**: Sumatori d'identificacions positives d'una espècie (contactes o "passes" acústics purs).
        - **`total_buzz` (Buzz)**: Sumatori d'identificacions de "feeding buzzes", un patró acústic accelerat emès en la fase final de captura d'un insecte. Representa exclusivament activitat de caça.
        - **Variables atmosfèriques** (`temp`, `rel_humidity`, `wind_speed`): Dades de l'entorn vinculades a l'interval de mostreig mitjançant estacions properes.
        """)
        
        st.subheader("2. Esforç de Mostreig ($N$)")
        st.markdown("""
        Per poder comparar correctament l'activitat entre espècies, localitzacions i períodes, l'aplicació calcula l'esforç de mostreig ($N$) de manera dinàmica segons els filtres actius.

        En camp, l'AudioMoth registra informació en intervals de **5 segons**, però en aquest dashboard els resultats es treballen **agregats per hora**.

        Per tant, **$N$ és simplement un comptatge de les mostres** dins de la selecció analitzada.
        No s'aplica cap base temporal més fina (ni minuts ni segons) en el càlcul de $N$ per a OA i OT.
        """)
        
        st.subheader("3. Indicadors Ecològics d'Activitat")
        st.markdown("""
        Per entendre l'ús real de l'hàbitat es fan servir tres índexs acústics que es calculen de forma totalment reactiva en aplicar filtres en la vista d'Accions. Això permet que l'estimació no variï artificialment segons on tallem les consultes temporals.
        
        #### OA (Ocupació Acústica)
        Indica el grau d'activitat general d'ús de l'espai (vol de desplaçament, navegació, caça) per unitat d'esforç.
        $$ OA = \\frac{\\text{Comptatge Total (Count)}}{N} $$
        
        #### OT (Ocupació Tròfica)
        Indica el grau d'activitat estrictament de caça per unitat d'esforç. És determinant per avaluar si un punt concret no és només una zona de pas sinó una autèntica zona d'alimentació establerta.
        $$ OT = \\frac{\\text{Total Buzz}}{N} $$
        
        #### IA (Intensitat Depredadora)
        És la proporció d'esforç de caça sobre l'activitat general de pas. Un IA alt indica que l'hàbitat s'utilitza majoritàriament per alimentar-se, permetent destacar zones vitals inclús si l'abundància numèrica (OA) sembla baixa.
        $$ IA = \\frac{\\text{Total Buzz}}{\\text{Comptatge Total (Count)}} $$
        *(Es protegeix la divisió per zero: si no hi ha activitat registrada o `Count` = 0, l'índex $IA$ és $0.0$).*
        """)

    # ---------------- TAB 3: ANÀLISI SEMÀNTICA ----------------
    with tab_chat:
        st.header("💬 Anàlisi Semàntica i Assistència de Dades")
        st.markdown("Fes preguntes en llenguatge natural sobre la base de dades i deixa que la intel·ligència artificial filtri les observacions i generi gràfics dinàmics a l'instant.")
        
        if df_full.empty:
            st.warning("No s'han pogut carregar les dades de ratpenats per a l'anàlisi semàntic.")
        else:
            import ai_helper
            
            # Mappings for Streamlit UI selectors
            METRIC_OPTS = {
                "total_count": "Comptatge",
                "total_buzz": "Buzz",
                "OA": "OA (Ocupació Acústica)",
                "OT": "OT (Ocupació Tròfica)",
                "IA": "IA (Intensitat Depredadora)",
                "temp": "Temperatura (°C)",
                "rel_humidity": "Humitat Relativa (%)",
                "wind_speed": "Velocitat del Vent (m/s)",
                "percip_mm": "Precipitació (mm)"
            }
            X_AXIS_OPTS = {
                "species": "Espècie",
                "location_name": "Localització",
                "observation_date": "Data",
                "month_year": "Mes - Any",
                "observation_hour": "Franja Horària (h)"
            }
            CHART_OPTS = {
                "cap": "Sense gràfic",
                "barres": "Barres",
                "línies": "Línies",
                "dispersió": "Dispersió",
                "mapa_calor": "Mapa de calor",
                "bombolles": "Bombolles (multidimensional)"
            }
            
            # Inicialitzar l'estat de sessió si no existeix
            if "chat_history" not in st.session_state:
                st.session_state.chat_history = [
                    {"role": "assistant", "content": "Hola! Soc el teu assistent d'anàlisi de ratpenats. Em pots demanar coses en llenguatge natural com:\n- *Mostra'm la intensitat depredadora (IA) de Miniopterus schreibersii a Cala Culip durant el juny de 2025*\n- *Quina espècie té més contactes en total?*\n- *Fes un gràfic de barres de l'ocupació acústica (OA) per a totes les localitzacions*"}
                ]
            
            if "query_id" not in st.session_state:
                st.session_state.query_id = 0
                
            if "ai_defaults" not in st.session_state:
                min_date_val = df_full['observation_date'].dropna().min()
                max_date_val = df_full['observation_date'].dropna().max()
                st.session_state.ai_defaults = {
                    "species": [],
                    "locations": [],
                    "start_date": min_date_val,
                    "end_date": max_date_val,
                    "metric": "total_count",
                    "x_axis": "species",
                    "chart_type": "barres",
                    "explanation": "Totes les dades inicials carregades.",
                    "chart_recommendation_reason": "Gràfic de barres per comparar dades entre espècies per defecte."
                }

            # Disseny split-screen: Esquerra = Xat (30%), Dreta = Visualització Activa (70%)
            col_chat, col_vis = st.columns([3, 7])
            
            with col_chat:
                st.subheader("Conversa amb l'assistent")
                # Contenidor per missatges de xat amb alçada fixa per tenir scroll
                chat_container = st.container(height=500)
                with chat_container:
                    for msg in st.session_state.chat_history:
                        with st.chat_message(msg["role"]):
                            st.write(msg["content"])
                
                # Input del xat
                user_input = st.chat_input("Escriu la teva consulta de dades aquí...")
                
                if user_input:
                    st.session_state.chat_history.append({"role": "user", "content": user_input})

                    with st.spinner("Analitzant la consulta amb Gemini..."):
                        try:
                            # Executar anàlisi amb Gemini
                            analysis = ai_helper.analyze_query_with_llm(
                                user_query=user_input, 
                                chat_history=st.session_state.chat_history[:-1], 
                                df_full=df_full
                            )
                            
                            # Parse dates safely
                            min_date_val = df_full['observation_date'].dropna().min()
                            max_date_val = df_full['observation_date'].dropna().max()
                            
                            try:
                                start_d = pd.to_datetime(analysis.filter_start_date).date() if analysis.filter_start_date else min_date_val
                            except Exception:
                                start_d = min_date_val
                                
                            try:
                                end_d = pd.to_datetime(analysis.filter_end_date).date() if analysis.filter_end_date else max_date_val
                            except Exception:
                                end_d = max_date_val
                                
                            # Actualitzar valors per defecte amb la resposta de la IA
                            st.session_state.ai_defaults = {
                                "species": analysis.filter_species or [],
                                "locations": analysis.filter_locations or [],
                                "start_date": start_d,
                                "end_date": end_d,
                                "metric": analysis.metric if analysis.metric in METRIC_OPTS else "total_count",
                                "x_axis": analysis.x_axis if analysis.x_axis in X_AXIS_OPTS else "species",
                                "chart_type": analysis.chart_type if analysis.chart_type in CHART_OPTS else "cap",
                                "explanation": analysis.explanation,
                                "chart_recommendation_reason": analysis.chart_recommendation_reason,
                                "secondary_metric": analysis.secondary_metric,
                                "use_dual_axis": bool(analysis.use_dual_axis),
                                "color_by": analysis.color_by,
                                "aggregation": analysis.aggregation or "auto",
                                "filter_hours": analysis.filter_hours,
                                "top_n": analysis.top_n
                            }
                            
                            # Estructurar resposta detallada de l'assistent en el xat
                            assistant_text = f"""**Anàlisi de la consulta:**\n{analysis.explanation}

**Resposta de Gemini:**

📊 **Configuració del gràfic:**
- **Mètrica Principal:** {METRIC_OPTS.get(analysis.metric, analysis.metric)}
- **Agrupació (Eix X):** {X_AXIS_OPTS.get(analysis.x_axis, analysis.x_axis)}
- **Tipus de gràfic:** {CHART_OPTS.get(analysis.chart_type, analysis.chart_type)}"""
                            
                            if analysis.use_dual_axis and analysis.secondary_metric:
                                assistant_text += f"\n- **Mètrica Secundària (Dual Axis):** {METRIC_OPTS.get(analysis.secondary_metric, analysis.secondary_metric)}"

                            if analysis.color_by:
                                assistant_text += f"\n- **Desglossament per color:** {X_AXIS_OPTS.get(analysis.color_by, analysis.color_by)}"

                            if analysis.top_n:
                                assistant_text += f"\n- **Rànquing (Top N):** {analysis.top_n}"
                            
                            assistant_text += f"""

🔍 **Filtres aplicats:**
- **Espècies:** {', '.join(analysis.filter_species) if analysis.filter_species else 'Totes'}
- **Localitzacions:** {', '.join(analysis.filter_locations) if analysis.filter_locations else 'Totes'}
- **Data inici:** {analysis.filter_start_date or 'No especificada'}
- **Data final:** {analysis.filter_end_date or 'No especificada'}

💡 **Raonament de la visualització:** {analysis.chart_recommendation_reason}"""

                            if analysis.conversational_answer:
                                assistant_text += f"\n\n📝 **Resposta a la pregunta:** {analysis.conversational_answer}"
                                
                            st.session_state.chat_history.append({"role": "assistant", "content": assistant_text})
                            
                            # Incrementar query_id per forçar re-creació dels components de Streamlit amb nous valors
                            st.session_state.query_id += 1
                            
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error processant la consulta: {e}")
                            st.session_state.chat_history.append({
                                "role": "assistant", 
                                "content": f"Ho sento, s'ha produït un error al processar la petició: {str(e)}"
                            })
                            st.rerun()

            with col_vis:
                st.subheader("Panell de Visualització Actiu")
                
                # Fetch species and location lists for multiselect options
                all_species = sorted(df_full['species'].dropna().unique().tolist())
                all_locations = sorted(df_full['location_name'].dropna().unique().tolist())
                min_date_val = df_full['observation_date'].dropna().min()
                max_date_val = df_full['observation_date'].dropna().max()
                
                # Renderitzar widgets de control híbrids (inicialitzats amb el de la IA, modificables per l'usuari)
                with st.expander("🛠️ Retocar filtres i gràfic manualment", expanded=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        # Selecció de mètrica
                        metric_list = list(METRIC_OPTS.keys())
                        default_metric_idx = metric_list.index(st.session_state.ai_defaults["metric"]) if st.session_state.ai_defaults["metric"] in metric_list else 0
                        sel_metric = st.selectbox(
                            "Mètrica:",
                            options=metric_list,
                            format_func=lambda x: METRIC_OPTS[x],
                            index=default_metric_idx,
                            key=f"metric_{st.session_state.query_id}"
                        )
                        
                        # Selecció d'eix X
                        x_axis_list = list(X_AXIS_OPTS.keys())
                        default_x_axis_idx = x_axis_list.index(st.session_state.ai_defaults["x_axis"]) if st.session_state.ai_defaults["x_axis"] in x_axis_list else 0
                        sel_x_axis = st.selectbox(
                            "Agrupació (Eix X):",
                            options=x_axis_list,
                            format_func=lambda x: X_AXIS_OPTS[x],
                            index=default_x_axis_idx,
                            key=f"x_axis_{st.session_state.query_id}"
                        )
                        
                        # Selecció de tipus de gràfic
                        chart_list = list(CHART_OPTS.keys())
                        default_chart_idx = chart_list.index(st.session_state.ai_defaults["chart_type"]) if st.session_state.ai_defaults["chart_type"] in chart_list else 0
                        sel_chart_type = st.selectbox(
                            "Tipus de gràfic:",
                            options=chart_list,
                            format_func=lambda x: CHART_OPTS[x],
                            index=default_chart_idx,
                            key=f"chart_{st.session_state.query_id}"
                        )

                        # Controls de doble eix Y (dual axis) per comparar dues mètriques
                        sel_dual_axis = st.checkbox(
                            "Doble eix Y (comparar 2 mètriques)",
                            value=bool(st.session_state.ai_defaults.get("use_dual_axis", False)),
                            key=f"dual_axis_{st.session_state.query_id}"
                        )

                        sel_secondary_metric = None
                        if sel_dual_axis:
                            secondary_list = [m for m in metric_list if m != sel_metric]
                            default_secondary = st.session_state.ai_defaults.get("secondary_metric")
                            default_secondary_idx = (
                                secondary_list.index(default_secondary)
                                if default_secondary in secondary_list else 0
                            )
                            sel_secondary_metric = st.selectbox(
                                "Mètrica secundària (eix dret):",
                                options=secondary_list,
                                format_func=lambda x: METRIC_OPTS[x],
                                index=default_secondary_idx,
                                key=f"secondary_metric_{st.session_state.query_id}"
                            )
                        
                    with c2:
                        # Multiselector d'espècies
                        default_sp = [s for s in st.session_state.ai_defaults["species"] if s in all_species]
                        sel_species = st.multiselect(
                            "Filtrar Espècie:",
                            options=all_species,
                            default=default_sp,
                            placeholder="Totes les espècies",
                            key=f"species_{st.session_state.query_id}"
                        )
                        
                        # Multiselector de localitzacions
                        default_loc = [l for l in st.session_state.ai_defaults["locations"] if l in all_locations]
                        sel_locations = st.multiselect(
                            "Filtrar Localització:",
                            options=all_locations,
                            default=default_loc,
                            placeholder="Totes les localitzacions",
                            key=f"locations_{st.session_state.query_id}"
                        )
                        
                        # Selector de rang de dates
                        def_start = st.session_state.ai_defaults["start_date"]
                        def_end = st.session_state.ai_defaults["end_date"]
                        if def_start < min_date_val: def_start = min_date_val
                        if def_end > max_date_val: def_end = max_date_val
                        
                        sel_dates = st.date_input(
                            "Rang de dates:",
                            value=(def_start, def_end),
                            min_value=min_date_val,
                            max_value=max_date_val,
                            key=f"dates_{st.session_state.query_id}"
                        )
                
                # Extraure el rang de dates correctament
                if isinstance(sel_dates, tuple) and len(sel_dates) == 2:
                    start_date_str = sel_dates[0].strftime("%Y-%m-%d")
                    end_date_str = sel_dates[1].strftime("%Y-%m-%d")
                elif isinstance(sel_dates, tuple) and len(sel_dates) == 1:
                    start_date_str = sel_dates[0].strftime("%Y-%m-%d")
                    end_date_str = sel_dates[0].strftime("%Y-%m-%d")
                else:
                    start_date_str = sel_dates.strftime("%Y-%m-%d") if sel_dates else None
                    end_date_str = sel_dates.strftime("%Y-%m-%d") if sel_dates else None

                # ---- Personalització visual del gràfic (independent de la consulta IA) ----
                COLOR_SCHEMES = {
                    "tableau10": "Tableau 10 (per defecte)",
                    "category10": "Category 10",
                    "set2": "Set 2 (pastel)",
                    "dark2": "Dark 2",
                    "tableau20": "Tableau 20 (moltes categories)",
                    "viridis": "Viridis (seqüencial)",
                    "plasma": "Plasma (seqüencial)",
                    "turbo": "Turbo (arc de Sant Martí)",
                }
                with st.expander("🎨 Personalització visual del gràfic", expanded=False):
                    sc1, sc2, sc3 = st.columns(3)
                    with sc1:
                        style_scheme = st.selectbox(
                            "Paleta de colors (categories):",
                            options=list(COLOR_SCHEMES.keys()),
                            format_func=lambda x: COLOR_SCHEMES[x],
                            index=0,
                            key="style_scheme"
                        )
                        style_primary = st.color_picker(
                            "Color principal (sèrie única):", value="#1f77b4", key="style_primary"
                        )
                        style_secondary = st.color_picker(
                            "Color secundari (doble eix):", value="#ff7f0e", key="style_secondary"
                        )
                    with sc2:
                        style_height = st.slider(
                            "Alçada del gràfic (px):", min_value=250, max_value=900, value=420, step=20, key="style_height"
                        )
                        style_opacity = st.slider(
                            "Opacitat de les marques:", min_value=0.1, max_value=1.0, value=0.85, step=0.05, key="style_opacity"
                        )
                        style_point_size = st.slider(
                            "Mida dels punts (dispersió):", min_value=20, max_value=300, value=80, step=10, key="style_point_size"
                        )
                        style_label_angle = st.slider(
                            "Angle etiquetes eix X:", min_value=-90, max_value=0, value=-45, step=15, key="style_label_angle"
                        )
                    with sc3:
                        style_log = st.checkbox("Escala logarítmica (eix Y)", value=False, key="style_log")
                        style_grid = st.checkbox("Mostrar quadrícula (eix Y)", value=True, key="style_grid")
                        style_points = st.checkbox("Mostrar punts (línies)", value=True, key="style_points")
                        style_interactive = st.checkbox("Zoom i desplaçament interactius", value=True, key="style_interactive")

                chart_style = {
                    "color_scheme": style_scheme,
                    "primary_color": style_primary,
                    "secondary_color": style_secondary,
                    "height": style_height,
                    "opacity": style_opacity,
                    "point_size": style_point_size,
                    "label_angle": style_label_angle,
                    "log_scale": style_log,
                    "show_grid": style_grid,
                    "show_points": style_points,
                    "interactive": style_interactive,
                }

                # Generar una QueryAnalysisSchema amb els valors actius actuals (retocats de la vista)
                from ai_helper import QueryAnalysisSchema

                # Coherència del dual axis: només actiu si hi ha mètrica secundària diferent.
                use_dual_axis = bool(sel_dual_axis and sel_secondary_metric and sel_secondary_metric != sel_metric)
                secondary_metric = sel_secondary_metric if use_dual_axis else None

                current_analysis = QueryAnalysisSchema(
                    explanation=st.session_state.ai_defaults["explanation"],
                    filter_species=sel_species if sel_species else None,
                    filter_locations=sel_locations if sel_locations else None,
                    filter_start_date=start_date_str,
                    filter_end_date=end_date_str,
                    metric=sel_metric,
                    x_axis=sel_x_axis,
                    chart_type=sel_chart_type,
                    chart_recommendation_reason=st.session_state.ai_defaults.get("chart_recommendation_reason", ""),
                    conversational_answer="",
                    secondary_metric=secondary_metric,
                    use_dual_axis=use_dual_axis,
                    color_by=st.session_state.ai_defaults.get("color_by") if not use_dual_axis else None,
                    aggregation=st.session_state.ai_defaults.get("aggregation", "auto"),
                    filter_hours=st.session_state.ai_defaults.get("filter_hours"),
                    top_n=st.session_state.ai_defaults.get("top_n")
                )
                
                # Aplicar els filtres i generar el gràfic a temps real
                df_filtered, chart, filters_summary = ai_helper.apply_filters_and_generate_chart(
                    df=df_full, 
                    analysis=current_analysis,
                    chart_style=chart_style
                )
                
                # Renderitzar el resultat
                with st.container(border=True):
                    st.info(f"🔍 **Filtres Actius al Gràfic:**\n{filters_summary}")
                    
                    if st.session_state.ai_defaults["explanation"]:
                        st.caption(f"*Motiu d'interpretació:* {st.session_state.ai_defaults['explanation']}")
                    
                    # Mostrar la raó de la recomendació del gràfic si existeix i és rellevant
                    chart_type = st.session_state.ai_defaults.get("chart_type", "cap")
                    chart_recommendation = st.session_state.ai_defaults.get("chart_recommendation_reason", "")
                    if chart_type != "cap" and chart_recommendation:
                        st.caption(f"💡 **Raó de la visualització:** {chart_recommendation}")
                        
                    # Dibuixar gràfic actiu
                    if chart is not None:
                        st.altair_chart(chart, width="stretch")
                    else:
                        st.info("No s'ha definit cap gràfic actiu (el tipus de gràfic és 'Sense gràfic'). Modifica el selector o demana-ho directament al xat!")
                        
                    # Desplegable per descarregar les dades filtrades
                    if df_filtered is not None and not df_filtered.empty:
                        with st.expander("Veure i descarregar dades filtrades (CSV)"):
                            st.dataframe(df_filtered, width="stretch")
                            csv_data = df_filtered.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label="📥 Descarregar dades filtrades com a CSV",
                                data=csv_data,
                                file_name="observacions_filtrades_ratpenats.csv",
                                mime="text/csv"
                            )

if __name__ == "__main__":
    main()
