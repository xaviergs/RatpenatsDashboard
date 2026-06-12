import os
import streamlit as st
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

@st.cache_data(ttl=300, show_spinner=False)
def load_bat_observations():
    client = init_connection()
    all_records = []
    offset = 0
    max_rows = 1000
    
    while True:
        try:
            res = client.table("bat_observations_full").select("*").range(offset, offset + max_rows - 1).execute()
            if res.data:
                all_records.extend(res.data)
            
            if not res.data or len(res.data) < max_rows:
                break
                
            offset += max_rows
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


def main():
    st.title("Ratpenats al Cap de Creus")
    st.markdown(f"**Port de Desplegament**: `{port}` (Punt per a Cloud Run)")
    st.divider()
    
    # Initialize connection
    supabase_client = init_connection()
    
    # Carreguem totes les observacions inicials per a toda l'app
    with st.spinner("Carregant dades generals de ratpenats..."):
        df_full = load_bat_observations()
        
    # Create Layout Tabs
    tab_accions, tab_estatus, tab_syllabus, tab_chat = st.tabs(["🚀 Accions", "📊 Estatus", "📖 Syllabus", "💬 Anàlisi Semàntica"])

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
                
                opcions_metrica = list(METRIC_COLS.keys())
                if sp_vis_type == "Línies":
                    opcions_metrica = ["Comptatge i Buzz (Doble Eix)"] + opcions_metrica
                
                sp_metric = st.selectbox("Mètrica a visualitzar:", opcions_metrica, key="sp_met_bar")
            
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
                        
                        if sp_vis_type == "Línies":
                            df_sp_grouped = calculate_ecological_indices(df_sp, df_unfiltered, ["species"])
                            
                            base = alt.Chart(df_sp_grouped).encode(
                                x=alt.X('species:N', title='Espècie', axis=alt.Axis(labelAngle=-45, grid=False))
                            )
                            
                            if sp_metric == "Comptatge i Buzz (Doble Eix)":
                                line_count = base.mark_line(color='#1f77b4', point=True).encode(
                                    y=alt.Y('total_count:Q', title='Comptatge Total', axis=alt.Axis(titleColor='#1f77b4', grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]))
                                )
                                line_buzz = base.mark_line(color='#ff7f0e', point=True).encode(
                                    y=alt.Y('total_buzz:Q', title='Total Buzz', axis=alt.Axis(titleColor='#ff7f0e', orient='right', grid=False))
                                )
                                chart_sp = alt.layer(line_count, line_buzz).resolve_scale(y='independent').properties(height=400).configure_axis(grid=False)
                            else:
                                y_col, y_title = METRIC_COLS[sp_metric]
                                chart_sp = base.mark_line(color='#1f77b4', point=True).encode(
                                    y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])),
                                    tooltip=['species:N', f'{y_col}:Q']
                                ).properties(height=400).configure_axis(grid=False)
                        else:
                            df_sp_grouped = calculate_ecological_indices(df_sp, df_unfiltered, ["species", "location_name"])
                            
                            if sp_metric == "Comptatge i Buzz (Doble Eix)":
                                sp_metric = "Comptatge"
                            
                            y_col, y_title = METRIC_COLS[sp_metric]
                            
                            chart_sp = alt.Chart(df_sp_grouped).mark_bar().encode(
                                x=alt.X('species:N', title='Espècie', axis=alt.Axis(labelAngle=-45, grid=False)),
                                y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])),
                                color=alt.Color('location_name:N', title='Localització', legend=alt.Legend(orient="bottom", columns=3)),
                                tooltip=['species:N', 'location_name:N', f'{y_col}:Q']
                            ).properties(height=400).configure_axis(grid=False)
                            
                        st.altair_chart(chart_sp, use_container_width=True)

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
                
                opcions_metrica = list(METRIC_COLS.keys())
                if loc_vis_type == "Línies":
                    opcions_metrica = ["Comptatge i Buzz (Doble Eix)"] + opcions_metrica
                
                loc_metric = st.selectbox("Mètrica a visualitzar:", opcions_metrica, key="loc_met_bar")
                    
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
                        
                        if loc_vis_type == "Línies":
                            df_loc_grouped = calculate_ecological_indices(df_loc, df_unfiltered, ["location_name"])
                            
                            base2 = alt.Chart(df_loc_grouped).encode(
                                x=alt.X('location_name:N', title='Localització', axis=alt.Axis(labelAngle=-45, grid=False))
                            )
                            
                            if loc_metric == "Comptatge i Buzz (Doble Eix)":
                                line_count2 = base2.mark_line(color='#1f77b4', point=True).encode(
                                    y=alt.Y('total_count:Q', title='Comptatge Total', axis=alt.Axis(titleColor='#1f77b4', grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]))
                                )
                                line_buzz2 = base2.mark_line(color='#ff7f0e', point=True).encode(
                                    y=alt.Y('total_buzz:Q', title='Total Buzz', axis=alt.Axis(titleColor='#ff7f0e', orient='right', grid=False))
                                )
                                chart_loc = alt.layer(line_count2, line_buzz2).resolve_scale(y='independent').properties(height=400).configure_axis(grid=False)
                            else:
                                y_col, y_title = METRIC_COLS[loc_metric]
                                chart_loc = base2.mark_line(color='#1f77b4', point=True).encode(
                                    y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])),
                                    tooltip=['location_name:N', f'{y_col}:Q']
                                ).properties(height=400).configure_axis(grid=False)
                        else:
                            df_loc_grouped = calculate_ecological_indices(df_loc, df_unfiltered, ["location_name", "species"])
                            
                            if loc_metric == "Comptatge i Buzz (Doble Eix)":
                                loc_metric = "Comptatge"
                                
                            y_col, y_title = METRIC_COLS[loc_metric]
                            
                            chart_loc = alt.Chart(df_loc_grouped).mark_bar().encode(
                                x=alt.X('location_name:N', title='Localització', axis=alt.Axis(labelAngle=-45, grid=False)),
                                y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])),
                                color=alt.Color('species:N', title='Espècie', legend=alt.Legend(orient="bottom", columns=3)),
                                tooltip=['location_name:N', 'species:N', f'{y_col}:Q']
                            ).properties(height=400).configure_axis(grid=False)
                            
                        st.altair_chart(chart_loc, use_container_width=True)

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
                
                opcions_metrica = list(METRIC_COLS.keys())
                if date_vis_type == "Línies":
                    opcions_metrica = ["Comptatge i Buzz (Doble Eix)"] + opcions_metrica
                
                date_metric = st.selectbox("Mètrica a visualitzar:", opcions_metrica, key="date_met_bar")
                    
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
                        
                        if date_vis_type == "Línies":
                            df_date_grouped = calculate_ecological_indices(df_date, df_unfiltered, ["month_year"])
                            
                            base3 = alt.Chart(df_date_grouped).encode(
                                x=alt.X('month_year:T', title='Data (Mes - Any)', axis=alt.Axis(format='%m-%Y', labelAngle=-45, grid=False, tickCount='month'))
                            )
                            
                            if date_metric == "Comptatge i Buzz (Doble Eix)":
                                line_count3 = base3.mark_line(color='#1f77b4', point=True).encode(
                                    y=alt.Y('total_count:Q', title='Comptatge Total', axis=alt.Axis(titleColor='#1f77b4', grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]))
                                )
                                line_buzz3 = base3.mark_line(color='#ff7f0e', point=True).encode(
                                    y=alt.Y('total_buzz:Q', title='Total Buzz', axis=alt.Axis(titleColor='#ff7f0e', orient='right', grid=False))
                                )
                                chart_date = alt.layer(line_count3, line_buzz3).resolve_scale(y='independent').properties(height=400).configure_axis(grid=False)
                            else:
                                y_col, y_title = METRIC_COLS[date_metric]
                                chart_date = base3.mark_line(color='#1f77b4', point=True).encode(
                                    y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])),
                                    tooltip=['month_year:T', f'{y_col}:Q']
                                ).properties(height=400).configure_axis(grid=False)
                        else:
                            df_date_grouped = calculate_ecological_indices(df_date, df_unfiltered, ["month_year", "species"])
                            
                            if date_metric == "Comptatge i Buzz (Doble Eix)":
                                date_metric = "Comptatge"
                                
                            y_col, y_title = METRIC_COLS[date_metric]
                            
                            chart_date = alt.Chart(df_date_grouped).mark_bar(size=35).encode(
                                x=alt.X('month_year:T', title='Data (Mes - Any)', axis=alt.Axis(format='%m-%Y', labelAngle=-45, grid=False, tickCount='month')),
                                y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])),
                                color=alt.Color('species:N', title='Espècie', legend=alt.Legend(orient="bottom", columns=3)),
                                tooltip=['month_year:T', 'species:N', f'{y_col}:Q']
                            ).properties(height=400).configure_axis(grid=False)
                            
                        st.altair_chart(chart_date, use_container_width=True)

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
                
                opcions_metrica = list(METRIC_COLS.keys())
                if hour_vis_type == "Línies":
                    opcions_metrica = ["Comptatge i Buzz (Doble Eix)"] + opcions_metrica
                
                hour_metric = st.selectbox("Mètrica a visualitzar:", opcions_metrica, key="hour_met_bar")
                    
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
                        
                        if 'observation_hour' in df_unfiltered.columns:
                            df_unfiltered['hora'] = df_unfiltered['observation_hour'].astype(str).str.zfill(2)
                            df_hour['hora'] = df_hour['observation_hour'].astype(str).str.zfill(2)
                        else:
                            df_unfiltered['hora'] = 'Desconeguda'
                            df_hour['hora'] = 'Desconeguda'
                            
                        ordre_nocturn = [str(i).zfill(2) for i in range(16, 24)] + [str(i).zfill(2) for i in range(0, 16)]
                            
                        if hour_vis_type == "Línies":
                            df_hour_grouped = calculate_ecological_indices(df_hour, df_unfiltered, ["hora"])
                            
                            base4 = alt.Chart(df_hour_grouped).encode(
                                x=alt.X('hora:O', title='Franja Horària (h)', sort=ordre_nocturn, axis=alt.Axis(labelAngle=0, grid=False))
                            )
                            
                            if hour_metric == "Comptatge i Buzz (Doble Eix)":
                                line_count4 = base4.mark_line(color='#1f77b4', point=True).encode(
                                    y=alt.Y('total_count:Q', title='Comptatge Total', axis=alt.Axis(titleColor='#1f77b4', grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]))
                                )
                                line_buzz4 = base4.mark_line(color='#ff7f0e', point=True).encode(
                                    y=alt.Y('total_buzz:Q', title='Total Buzz', axis=alt.Axis(titleColor='#ff7f0e', orient='right', grid=False))
                                )
                                chart_hour = alt.layer(line_count4, line_buzz4).resolve_scale(y='independent').properties(height=400).configure_axis(grid=False)
                            else:
                                y_col, y_title = METRIC_COLS[hour_metric]
                                chart_hour = base4.mark_line(color='#1f77b4', point=True).encode(
                                    y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])),
                                    tooltip=['hora:O', f'{y_col}:Q']
                                ).properties(height=400).configure_axis(grid=False)
                        else:
                            df_hour_grouped = calculate_ecological_indices(df_hour, df_unfiltered, ["hora", "species"])
                            
                            if hour_metric == "Comptatge i Buzz (Doble Eix)":
                                hour_metric = "Comptatge"
                                
                            y_col, y_title = METRIC_COLS[hour_metric]
                            
                            chart_hour = alt.Chart(df_hour_grouped).mark_bar(size=22).encode(
                                x=alt.X('hora:O', title='Franja Horària (h)', sort=ordre_nocturn, axis=alt.Axis(labelAngle=0, grid=False)),
                                y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])),
                                color=alt.Color('species:N', title='Espècie', legend=alt.Legend(orient="bottom", columns=3)),
                                tooltip=['hora:O', 'species:N', f'{y_col}:Q']
                            ).properties(height=400).configure_axis(grid=False)
                            
                        st.altair_chart(chart_hour, use_container_width=True)

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
                
                # Mapa de variables climàtiques per l'eix X
                clim_vars_ca = {
                    "Temperatura (temp)": "temp",
                    "Humitat (rel_humidity)": "rel_humidity",
                    "Vent (wind_speed)": "wind_speed"
                }
                reg_x_var_ca = st.selectbox("Variable Eix X (Independent):", list(clim_vars_ca.keys()), key="reg_x_var")
                reg_x_col = clim_vars_ca[reg_x_var_ca]
                
                st.markdown("##### Opcions d'Anàlisi")
                reg_outliers = st.checkbox("Mostra tots els punts (Inclou Outliers)", value=True, key="reg_outliers")
                
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
                    
                    # Eliminar files on X o Y siguin NaN per no falsejar la regressió
                    df_reg_clean = df_reg.dropna(subset=[x_col, y_col]).copy()
                    
                    if not reg_outliers and not df_reg_clean.empty:
                        # Mètode IQR (Interquartile Range) per netejar outliers en ambdues variables
                        for col in [x_col, y_col]:
                            Q1 = df_reg_clean[col].quantile(0.25)
                            Q3 = df_reg_clean[col].quantile(0.75)
                            IQR = Q3 - Q1
                            lower_bound = Q1 - 1.5 * IQR
                            upper_bound = Q3 + 1.5 * IQR
                            df_reg_clean = df_reg_clean[(df_reg_clean[col] >= lower_bound) & (df_reg_clean[col] <= upper_bound)]

                    
                    if df_reg_clean.empty or len(df_reg_clean) < 2:
                        st.info("No hi ha prou dades vàlides per aquesta combinació (mínim 2 punts amb valors no nuls).")
                    else:
                        import altair as alt
                        import numpy as np
                        
                        # Càlcul de la regressió lineal
                        x_vals = df_reg_clean[x_col].values
                        y_vals = df_reg_clean[y_col].values
                        
                        # polyfit grau 1 retorna [pendent, intercept]
                        m, b = np.polyfit(x_vals, y_vals, 1)
                        
                        # R2
                        corr_matrix = np.corrcoef(x_vals, y_vals)
                        corr = corr_matrix[0, 1]
                        r_squared = corr ** 2
                        
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
                            x=alt.X(f'{x_col}:Q', title=reg_x_var_ca, scale=alt.Scale(zero=False)),
                            y=alt.Y(f'{y_col}:Q', title=reg_y_var),
                            tooltip=[f'{x_col}:Q', f'{y_col}:Q', 'species:N', 'location_name:N']
                        )
                        
                        # Línia de regressió
                        regression_line = alt.Chart(df_reg_clean).mark_line(color='red', size=3).encode(
                            x=f'{x_col}:Q',
                            y='prediction:Q'
                        )
                        
                        chart_reg = (scatter + regression_line).properties(height=350)
                        
                        st.altair_chart(chart_reg, use_container_width=True)

    # ---------------- TAB 2: ESTATUS ----------------
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
                    st.dataframe(pd.DataFrame(metrics_resp.data), use_container_width=True, hide_index=True)
                else:
                    st.info("Cap mètrica enregistrada.")
            except Exception as e:
                st.error(f"Error llegint mètriques: {e}")
                
        with col_list2:
            st.markdown("**Xarxa d'Estacions**")
            st.caption("Ubicació i altitud on es recullen dades.")
            try:
                stations_resp = supabase_client.table("weather_stations").select("name, longitude, latitude, altitude").order("name").execute()
                if stations_resp.data:
                    st.dataframe(pd.DataFrame(stations_resp.data), use_container_width=True, hide_index=True)
                else:
                    st.info("Cap estació enregistrada.")
            except Exception as e:
                st.error(f"Error llegint estacions: {e}")

        st.divider()
        st.subheader("Registres per Localització")
        st.caption("Mostra la quantitat de fitxers únics del registre (file_registry) agrupats per localització.")
        
        with st.spinner("Verificant i agrupant dades..."):
            try:
                # To simulate the GROUP BY logic natively with Supabase's PostgREST library,
                # we fetch the joined relation and process the grouping using pandas.
                fr_locations_resp = supabase_client.table("file_registry").select("file_name, locations!inner(display_name)").execute()
                fr_records = fr_locations_resp.data
                
                if fr_records:
                    # Flatten the JSON dynamically
                    df_fr = pd.json_normalize(fr_records)
                    
                    # Ensure the join successfully brought the display_name column
                    if 'locations.display_name' in df_fr.columns:
                        # Achieve the same result as:
                        # SELECT LO.display_name, COUNT(DISTINCT FR.file_name)
                        # FROM file_registry INNER JOIN locations ON ... GROUP BY 1 ORDER BY 1
                        df_grouped = df_fr.groupby('locations.display_name')['file_name'].nunique().reset_index()
                        df_grouped.columns = ['Localització', 'Quantitat de Fitxers']
                        df_grouped = df_grouped.sort_values(by='Localització')
                        
                        import altair as alt
                        chart_loc = alt.Chart(df_grouped).mark_bar().encode(
                            x=alt.X('Quantitat de Fitxers:Q', title='Quantitat de Fitxers'),
                            y=alt.Y('Localització:N', title='Localització'),
                            tooltip=['Localització', 'Quantitat de Fitxers']
                        ).properties(height=350)
                        
                        st.altair_chart(chart_loc, use_container_width=True)
                    else:
                        st.info("La columna 'locations.display_name' no s'ha trobat en els resultats del Join.")
                else:
                    st.info("Actualment no hi ha cap arxiu vinculat a localitzacions.")
            except Exception as e:
                st.error(f"Error aglutinant els fitxers per localització: {e}")

        st.divider()
        st.subheader("Observacions de Ratpenats")
        st.caption("Mostra el nombre de mostres per mes i localització.")
        
        @st.cache_data(ttl=300, show_spinner=False)
        def carregar_agrupacio_ratpenats():
            client = init_connection()
            try:
                # Query directa sobre la view sol·licitada per l'usuari
                all_records = []
                offset = 0
                max_rows = 1000
                
                while True:
                    res = client.table("days_by_location").select("*").range(offset, offset + max_rows - 1).execute()
                    if res.data:
                        all_records.extend(res.data)
                    
                    if not res.data or len(res.data) < max_rows:
                        break
                        
                    offset += max_rows
                    
                if not all_records:
                    return pd.DataFrame()
                
                df_view = pd.DataFrame(all_records)
                
                # Assegurar format correcte a la columna 'mes' si ve en format string des de la View SQL
                if 'mes' in df_view.columns:
                    df_view['mes'] = pd.to_datetime(df_view['mes'])
                    
                return df_view
            except Exception as e:
                st.error(f"Error de lectura a la vista days_by_location: {e}")
                return pd.DataFrame()

        with st.spinner("Carregant observacions..."):
            df_gen = carregar_agrupacio_ratpenats()
            
        if not df_gen.empty:
            try:
                df_net = df_gen.dropna(subset=['mes', 'display_name']).copy()
                
                if not df_net.empty:
                    # Mapeig manual en català pur sense dependre de les llibreries regionals del servidor
                    mesos_ca = {1: 'Gen', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Oct', 11: 'Nov', 12: 'Des'}
                    df_net['mes_etiq'] = df_net['mes'].dt.month.map(mesos_ca) + df_net['mes'].dt.strftime('%y')
                    
                    import altair as alt
                    chart = alt.Chart(df_net).mark_circle(opacity=0.8).encode(
                        x=alt.X('mes_etiq:N', sort=alt.EncodingSortField(field='mes', op='min', order='ascending'), title='Mes', axis=alt.Axis(labelAngle=-45)),
                        y=alt.Y('display_name:N', title='Localització'),
                        size=alt.Size('nombre_mostres:Q', title='Nombre de mostres', scale=alt.Scale(range=[50, 1000])),
                        color=alt.Color('display_name:N', legend=None),
                        tooltip=[alt.Tooltip('mes_etiq:N', title='Mes'), alt.Tooltip('display_name:N', title='Localització'), alt.Tooltip('nombre_mostres:Q', title='Mostres')]
                    ).properties(height=450)
                    
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.warning("La vista conté registres però falten els encapçalaments ('mes', 'display_name').")
            except Exception as e:
                st.error(f"Error processant les columnes per crear la gràfica (verifica els noms de la vista): {e}")
        else:
            st.warning("No s'han pogut carregar les dades o bé la vista està buida.")

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
        Per estandarditzar i comparar els índexs, l'aplicació mesura de manera dinàmica l'esforç d'observació efectiu ($N$).
        Donat que el detector només es dispara amb el so, s'extreu el temps complet de l'actuació de cada sessió:
        
        1. **Agrupació:** S'identifiquen les hores úniques de sessió (per localització i data).
        2. **Multiplicador:** S'assumeix una resolució o granularitat per cada hora (actualment establert a **60** intervals hipotètics, corresponent a 1 minut d'observació base).
        3. **Fórmula Base:**  $N = \text{Hores Úniques} \\times 60$.
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
                "IA": "IA (Intensitat Depredadora)"
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
                "dispersió": "Dispersió"
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
                    # Afegir missatge de l'usuari
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
                                "chart_recommendation_reason": analysis.chart_recommendation_reason
                            }
                            
                            # Estructurar resposta de l'assistent en el xat
                            assistant_text = f"**Anàlisi de filtre:** {analysis.explanation}\n\n"
                            if analysis.conversational_answer:
                                assistant_text += f"**Resposta:** {analysis.conversational_answer}"
                            else:
                                assistant_text += "He generat i filtrat el gràfic sol·licitat al panell de la dreta."
                                
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
                
                # Generar una QueryAnalysisSchema amb els valors actius actuals (retocats de la vista)
                from ai_helper import QueryAnalysisSchema
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
                    conversational_answer=""
                )
                
                # Aplicar els filtres i generar el gràfic a temps real
                df_filtered, chart, filters_summary = ai_helper.apply_filters_and_generate_chart(
                    df=df_full, 
                    analysis=current_analysis
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
                        st.altair_chart(chart, use_container_width=True)
                    else:
                        st.info("No s'ha definit cap gràfic actiu (el tipus de gràfic és 'Sense gràfic'). Modifica el selector o demana-ho directament al xat!")
                        
                    # Desplegable per descarregar les dades filtrades
                    if df_filtered is not None and not df_filtered.empty:
                        with st.expander("Veure i descarregar dades filtrades (CSV)"):
                            st.dataframe(df_filtered, use_container_width=True)
                            csv_data = df_filtered.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label="📥 Descarregar dades filtrades com a CSV",
                                data=csv_data,
                                file_name="observacions_filtrades_ratpenats.csv",
                                mime="text/csv"
                            )

if __name__ == "__main__":
    main()
