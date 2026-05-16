import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add calculate_ecological_indices
func_str = """    return df

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
    "IA (Intensitat Depredadora)": ("IA", "Índex IA")
}
"""
content = content.replace("    return df", func_str, 1)

# 2. Section 1 (Species)
sec1_old = """                sp_vis_type = st.radio("Tipus de visualització:", ["Línies", "Barres"], horizontal=True, key="sp_vis")
                if sp_vis_type == "Barres":
                    sp_bar_metric = st.radio("Mètrica a visualitzar (Barres):", ["Comptatge", "Buzz"], horizontal=True, key="sp_met_bar")
            
            with col1_graf:
                st.markdown("##### Resultat Gràfic")
                if df_full.empty:
                    st.warning("No s'han trobat dades a la vista bat_observations_full.")
                else:
                    df_sp = df_full.copy()
                    
                    # Aplicar filtres
                    if "Totes" not in sp_esp_sel and sp_esp_sel:
                        df_sp = df_sp[df_sp['species'].isin(sp_esp_sel)]
                        
                    if "Totes" not in sp_loc_sel and sp_loc_sel:
                        df_sp = df_sp[df_sp['location_name'].isin(sp_loc_sel)]
                        
                    start_d, end_d = sp_date_sel
                    df_sp = df_sp[(df_sp['observation_date'] >= start_d) & (df_sp['observation_date'] <= end_d)]
                    
                    if df_sp.empty:
                        st.info("Cap registre coincideix amb els filtres seleccionats.")
                    else:
                        import altair as alt
                        
                        if sp_vis_type == "Línies":
                            # Agrupar dades per espècie
                            df_sp_grouped = df_sp.groupby("species", as_index=False)[["total_count", "total_buzz"]].sum()
                            
                            # Gràfic base
                            base = alt.Chart(df_sp_grouped).encode(
                                x=alt.X('species:N', title='Espècie', axis=alt.Axis(labelAngle=-45, grid=False))
                            )
                            
                            # Línia per total_count (Eix Y esquerra)
                            line_count = base.mark_line(color='#1f77b4', point=True).encode(
                                y=alt.Y('total_count:Q', title='Comptatge Total', axis=alt.Axis(titleColor='#1f77b4', grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]))
                            )
                            
                            # Línia per total_buzz (Eix Y dreta)
                            line_buzz = base.mark_line(color='#ff7f0e', point=True).encode(
                                y=alt.Y('total_buzz:Q', title='Total Buzz', axis=alt.Axis(titleColor='#ff7f0e', orient='right', grid=False))
                            )
                            
                            # Combinem les dues línies amb escales Y independents
                            chart_sp = alt.layer(line_count, line_buzz).resolve_scale(
                                y='independent'
                            ).properties(
                                height=400
                            ).configure_axis(
                                grid=False
                            )
                        else:
                            # Barres apilades per localització
                            df_sp_grouped = df_sp.groupby(["species", "location_name"], as_index=False)[["total_count", "total_buzz"]].sum()
                            
                            y_col = 'total_count' if sp_bar_metric == "Comptatge" else 'total_buzz'
                            y_title = 'Comptatge Total' if sp_bar_metric == "Comptatge" else 'Total Buzz'
                            
                            chart_sp = alt.Chart(df_sp_grouped).mark_bar().encode(
                                x=alt.X('species:N', title='Espècie', axis=alt.Axis(labelAngle=-45, grid=False)),
                                y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])),
                                color=alt.Color('location_name:N', title='Localització', legend=alt.Legend(orient="bottom", columns=3)),
                                tooltip=['species:N', 'location_name:N', f'{y_col}:Q']
                            ).properties(
                                height=400
                            ).configure_axis(
                                grid=False
                            )"""

sec1_new = """                sp_vis_type = st.radio("Tipus de visualització:", ["Línies", "Barres"], horizontal=True, key="sp_vis")
                
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
                            ).properties(height=400).configure_axis(grid=False)"""
content = content.replace(sec1_old, sec1_new)


# 3. Section 2
sec2_old = """                loc_vis_type = st.radio("Tipus de visualització:", ["Línies", "Barres"], horizontal=True, key="loc_vis")
                if loc_vis_type == "Barres":
                    loc_bar_metric = st.radio("Mètrica a visualitzar (Barres):", ["Comptatge", "Buzz"], horizontal=True, key="loc_met_bar")
                    
            with col2_graf:
                st.markdown("##### Resultat Gràfic")
                if df_full.empty:
                    st.warning("No s'han trobat dades a la vista bat_observations_full.")
                else:
                    df_loc = df_full.copy()
                    
                    if "Totes" not in loc_esp_sel and loc_esp_sel:
                        df_loc = df_loc[df_loc['species'].isin(loc_esp_sel)]
                        
                    if "Totes" not in loc_loc_sel and loc_loc_sel:
                        df_loc = df_loc[df_loc['location_name'].isin(loc_loc_sel)]
                        
                    start_d, end_d = loc_date_sel
                    df_loc = df_loc[(df_loc['observation_date'] >= start_d) & (df_loc['observation_date'] <= end_d)]
                    
                    if df_loc.empty:
                        st.info("Cap registre coincideix amb els filtres seleccionats.")
                    else:
                        import altair as alt
                        
                        if loc_vis_type == "Línies":
                            df_loc_grouped = df_loc.groupby("location_name", as_index=False)[["total_count", "total_buzz"]].sum()
                            
                            base2 = alt.Chart(df_loc_grouped).encode(
                                x=alt.X('location_name:N', title='Localització', axis=alt.Axis(labelAngle=-45, grid=False))
                            )
                            
                            line_count2 = base2.mark_line(color='#1f77b4', point=True).encode(
                                y=alt.Y('total_count:Q', title='Comptatge Total', axis=alt.Axis(titleColor='#1f77b4', grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]))
                            )
                            
                            line_buzz2 = base2.mark_line(color='#ff7f0e', point=True).encode(
                                y=alt.Y('total_buzz:Q', title='Total Buzz', axis=alt.Axis(titleColor='#ff7f0e', orient='right', grid=False))
                            )
                            
                            chart_loc = alt.layer(line_count2, line_buzz2).resolve_scale(
                                y='independent'
                            ).properties(
                                height=400
                            ).configure_axis(
                                grid=False
                            )
                        else:
                            # Barres apilades per espècie
                            df_loc_grouped = df_loc.groupby(["location_name", "species"], as_index=False)[["total_count", "total_buzz"]].sum()
                            
                            y_col = 'total_count' if loc_bar_metric == "Comptatge" else 'total_buzz'
                            y_title = 'Comptatge Total' if loc_bar_metric == "Comptatge" else 'Total Buzz'
                            
                            chart_loc = alt.Chart(df_loc_grouped).mark_bar().encode(
                                x=alt.X('location_name:N', title='Localització', axis=alt.Axis(labelAngle=-45, grid=False)),
                                y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])),
                                color=alt.Color('species:N', title='Espècie', legend=alt.Legend(orient="bottom", columns=3)),
                                tooltip=['location_name:N', 'species:N', f'{y_col}:Q']
                            ).properties(
                                height=400
                            ).configure_axis(
                                grid=False
                            )"""

sec2_new = """                loc_vis_type = st.radio("Tipus de visualització:", ["Línies", "Barres"], horizontal=True, key="loc_vis")
                
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
                            ).properties(height=400).configure_axis(grid=False)"""
content = content.replace(sec2_old, sec2_new)


# 4. Section 3
sec3_old = """                date_vis_type = st.radio("Tipus de visualització:", ["Línies", "Barres"], horizontal=True, key="date_vis")
                if date_vis_type == "Barres":
                    date_bar_metric = st.radio("Mètrica a visualitzar (Barres):", ["Comptatge", "Buzz"], horizontal=True, key="date_met_bar")
                    
            with col3_graf:
                st.markdown("##### Resultat Gràfic")
                if df_full.empty:
                    st.warning("No s'han trobat dades a la vista bat_observations_full.")
                else:
                    df_date = df_full.copy()
                    
                    if "Totes" not in date_esp_sel and date_esp_sel:
                        df_date = df_date[df_date['species'].isin(date_esp_sel)]
                        
                    if "Totes" not in date_loc_sel and date_loc_sel:
                        df_date = df_date[df_date['location_name'].isin(date_loc_sel)]
                        
                    start_d, end_d = date_date_sel
                    df_date = df_date[(df_date['observation_date'] >= start_d) & (df_date['observation_date'] <= end_d)]
                    
                    if df_date.empty:
                        st.info("Cap registre coincideix amb els filtres seleccionats.")
                    else:
                        # Convertim observation_date a datetime i agrupem per l'inici del mes per a tenir-ho ordenat temporalment
                        df_date['obs_dt'] = pd.to_datetime(df_date['observation_date'])
                        df_date['month_year'] = df_date['obs_dt'].dt.to_period('M').dt.to_timestamp()
                        
                        import altair as alt
                        
                        if date_vis_type == "Línies":
                            df_date_grouped = df_date.groupby("month_year", as_index=False)[["total_count", "total_buzz"]].sum()
                            
                            base3 = alt.Chart(df_date_grouped).encode(
                                x=alt.X('month_year:T', title='Data (Mes - Any)', axis=alt.Axis(format='%m-%Y', labelAngle=-45, grid=False, tickCount='month'))
                            )
                            
                            line_count3 = base3.mark_line(color='#1f77b4', point=True).encode(
                                y=alt.Y('total_count:Q', title='Comptatge Total', axis=alt.Axis(titleColor='#1f77b4', grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]))
                            )
                            
                            line_buzz3 = base3.mark_line(color='#ff7f0e', point=True).encode(
                                y=alt.Y('total_buzz:Q', title='Total Buzz', axis=alt.Axis(titleColor='#ff7f0e', orient='right', grid=False))
                            )
                            
                            chart_date = alt.layer(line_count3, line_buzz3).resolve_scale(
                                y='independent'
                            ).properties(
                                height=400
                            ).configure_axis(
                                grid=False
                            )
                        else:
                            # Barres apilades per espècie
                            df_date_grouped = df_date.groupby(["month_year", "species"], as_index=False)[["total_count", "total_buzz"]].sum()
                            
                            y_col = 'total_count' if date_bar_metric == "Comptatge" else 'total_buzz'
                            y_title = 'Comptatge Total' if date_bar_metric == "Comptatge" else 'Total Buzz'
                            
                            # Forcem l'amplada de la barra amb 'size' perquè en l'eix temporal no es vegi com una línia
                            chart_date = alt.Chart(df_date_grouped).mark_bar(size=35).encode(
                                x=alt.X('month_year:T', title='Data (Mes - Any)', axis=alt.Axis(format='%m-%Y', labelAngle=-45, grid=False, tickCount='month')),
                                y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])),
                                color=alt.Color('species:N', title='Espècie', legend=alt.Legend(orient="bottom", columns=3)),
                                tooltip=['month_year:T', 'species:N', f'{y_col}:Q']
                            ).properties(
                                height=400
                            ).configure_axis(
                                grid=False
                            )"""

sec3_new = """                date_vis_type = st.radio("Tipus de visualització:", ["Línies", "Barres"], horizontal=True, key="date_vis")
                
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
                            ).properties(height=400).configure_axis(grid=False)"""
content = content.replace(sec3_old, sec3_new)

# 5. Section 4
sec4_old = """                hour_vis_type = st.radio("Tipus de visualització:", ["Línies", "Barres"], horizontal=True, key="hour_vis")
                if hour_vis_type == "Barres":
                    hour_bar_metric = st.radio("Mètrica a visualitzar (Barres):", ["Comptatge", "Buzz"], horizontal=True, key="hour_met_bar")
                    
            with col4_graf:
                st.markdown("##### Resultat Gràfic")
                if df_full.empty:
                    st.warning("No s'han trobat dades a la vista bat_observations_full.")
                else:
                    df_hour = df_full.copy()
                    
                    if "Totes" not in hour_esp_sel and hour_esp_sel:
                        df_hour = df_hour[df_hour['species'].isin(hour_esp_sel)]
                        
                    if "Totes" not in hour_loc_sel and hour_loc_sel:
                        df_hour = df_hour[df_hour['location_name'].isin(hour_loc_sel)]
                        
                    start_d, end_d = hour_date_sel
                    df_hour = df_hour[(df_hour['observation_date'] >= start_d) & (df_hour['observation_date'] <= end_d)]
                    
                    if df_hour.empty:
                        st.info("Cap registre coincideix amb els filtres seleccionats.")
                    else:
                        import altair as alt
                        
                        # Assegurar que l'hora sigui string per mostrar-la com a categoria seqüencial (ordinal)
                        if 'observation_hour' in df_hour.columns:
                            # Omplim amb zeros a l'esquerra per garantir l'ordre correcte (ex: '09', '10')
                            df_hour['hora'] = df_hour['observation_hour'].astype(str).str.zfill(2)
                        else:
                            df_hour['hora'] = 'Desconeguda'
                            
                        # Ordre nocturn per a l'eix X (de 16:00 a 15:00)
                        ordre_nocturn = [str(i).zfill(2) for i in range(16, 24)] + [str(i).zfill(2) for i in range(0, 16)]
                            
                        if hour_vis_type == "Línies":
                            df_hour_grouped = df_hour.groupby("hora", as_index=False)[["total_count", "total_buzz"]].sum()
                            
                            base4 = alt.Chart(df_hour_grouped).encode(
                                x=alt.X('hora:O', title='Franja Horària (h)', sort=ordre_nocturn, axis=alt.Axis(labelAngle=0, grid=False))
                            )
                            
                            line_count4 = base4.mark_line(color='#1f77b4', point=True).encode(
                                y=alt.Y('total_count:Q', title='Comptatge Total', axis=alt.Axis(titleColor='#1f77b4', grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4]))
                            )
                            
                            line_buzz4 = base4.mark_line(color='#ff7f0e', point=True).encode(
                                y=alt.Y('total_buzz:Q', title='Total Buzz', axis=alt.Axis(titleColor='#ff7f0e', orient='right', grid=False))
                            )
                            
                            chart_hour = alt.layer(line_count4, line_buzz4).resolve_scale(
                                y='independent'
                            ).properties(
                                height=400
                            ).configure_axis(
                                grid=False
                            )
                        else:
                            # Barres apilades per espècie
                            df_hour_grouped = df_hour.groupby(["hora", "species"], as_index=False)[["total_count", "total_buzz"]].sum()
                            
                            y_col = 'total_count' if hour_bar_metric == "Comptatge" else 'total_buzz'
                            y_title = 'Comptatge Total' if hour_bar_metric == "Comptatge" else 'Total Buzz'
                            
                            # Size 20-25 sol quedar molt bé en gràfics ordinals de 24 hores
                            chart_hour = alt.Chart(df_hour_grouped).mark_bar(size=22).encode(
                                x=alt.X('hora:O', title='Franja Horària (h)', sort=ordre_nocturn, axis=alt.Axis(labelAngle=0, grid=False)),
                                y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(grid=True, gridColor='gray', gridOpacity=0.3, gridDash=[4, 4])),
                                color=alt.Color('species:N', title='Espècie', legend=alt.Legend(orient="bottom", columns=3)),
                                tooltip=['hora:O', 'species:N', f'{y_col}:Q']
                            ).properties(
                                height=400
                            ).configure_axis(
                                grid=False
                            )"""

sec4_new = """                hour_vis_type = st.radio("Tipus de visualització:", ["Línies", "Barres"], horizontal=True, key="hour_vis")
                
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
                            ).properties(height=400).configure_axis(grid=False)"""
content = content.replace(sec4_old, sec4_new)

# 6. Section 5
sec5_old = """                st.markdown("##### Variables de Regressió")
                reg_y_var = st.selectbox("Variable Eix Y (Dependent):", ["Comptatge", "Buzz"], key="reg_y_var")
                
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
                    
                    y_col = 'total_count' if reg_y_var == "Comptatge" else 'total_buzz'
                    x_col = reg_x_col"""

sec5_new = """                st.markdown("##### Variables de Regressió")
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
                    x_col = reg_x_col"""
content = content.replace(sec5_old, sec5_new)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Patch applied successfully.")
