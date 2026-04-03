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
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_connection() -> Client:
    """
    Initialize and return a singleton connection to Supabase.
    Uses @st.cache_resource to prevent re-initializing the client on every rerun.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        st.error("No s'han trobat les credencials de Supabase. Si us plau, configureu les variables d'entorn SUPABASE_URL i SUPABASE_KEY.")
        st.stop()
        
    return create_client(url, key)

def main():
    st.title("Ratpenats al Cap de Creus")
    st.markdown(f"**Port de Desplegament**: `{port}` (Punt per a Cloud Run)")
    st.divider()
    
    # Initialize connection
    supabase_client = init_connection()
    
    # Create Layout Tabs
    tab_accions, tab_estatus = st.tabs(["🚀 Accions", "📊 Estatus"])

    # ---------------- TAB 1: ACCIONS ----------------
    with tab_accions:
        st.subheader("Àrea d'Accions")
        st.markdown("Aquesta àrea està reservada per a futures funcionalitats. De moment no hi ha cap acció activa configurada.")
        st.info("Pots navegar a la pestanya **Estatus** per verificar les mètriques de connectivitat en temps real.")

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

if __name__ == "__main__":
    main()
