import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from folium.plugins import MarkerCluster, MiniMap
from streamlit_folium import st_folium
import re
import os

st.set_page_config(
    page_title="Tissu Agricole du Togo",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

REGIONS = ["Toutes", "Maritime", "Plateaux", "Centrale", "Kara", "Savanes"]
REGION_COLORS = {
    "Maritime": "#2196F3",
    "Plateaux": "#4CAF50",
    "Centrale": "#FF9800",
    "Kara": "#9C27B0",
    "Savanes": "#F44336",
}
LAYER_COLORS = {
    "Grandes Exploitations": "#E53935",
    "Plantations": "#8BC34A",
    "Pépinières": "#FF9800",
    "Coopératives": "#3F51B5",
    "Marchés": "#009688",
    "ZAAPs (formes)": "#795548",
    "ZAAPs (champs)": "#607D8B",
    "Petites Exploitations": "#F06292",
}

# --- Helpers ------------------------------------------------------------------

def extract_point(geom_str):
    """Return (lat, lon) from WKT POINT or centroid of polygon."""
    if not isinstance(geom_str, str):
        return None, None
    m = re.search(r'POINT\s*\(([0-9.\-]+)\s+([0-9.\-]+)\)', geom_str)
    if m:
        return float(m.group(2)), float(m.group(1))  # lat, lon
    # For polygons/multipolygons, extract first coordinate pair as centroid proxy
    coords = re.findall(r'([0-9.\-]+)\s+([0-9.\-]+)', geom_str)
    if coords:
        lons = [float(c[0]) for c in coords]
        lats = [float(c[1]) for c in coords]
        return sum(lats)/len(lats), sum(lons)/len(lons)
    return None, None

def get_polygon_coords(geom_str):
    """Extract list of [lat, lon] pairs from first polygon ring."""
    if not isinstance(geom_str, str):
        return []
    ring = re.search(r'\(\(([^)]+)\)', geom_str)
    if not ring:
        ring = re.search(r'\(([^()]+)\)', geom_str)
    if not ring:
        return []
    pairs = re.findall(r'([0-9.\-]+)\s+([0-9.\-]+)', ring.group(1))
    return [[float(p[1]), float(p[0])] for p in pairs]  # [lat, lon]

@st.cache_data(show_spinner=False)
def load_data():
    dfs = {}
    files = {
        "grandes": "grandes_exploitations.csv",
        "petites": "petites_exploitations.csv",
        "plantations": "plantations_agricoles.csv",
        "cooperatives": "cooperatives.csv",
        "marches": "marches.csv",
        "pepinieres": "pepinieres.csv",
        "zaaps_formes": "zaaps_formes.csv",
        "zaaps_champs": "zaaps_champs_ind.csv",
    }
    for key, fname in files.items():
        path = os.path.join(DATA_DIR, fname)
        df = pd.read_csv(path, encoding="utf-8", low_memory=False)
        df["lat"], df["lon"] = zip(*df["geometry"].apply(extract_point))
        df = df.dropna(subset=["lat", "lon"])
        dfs[key] = df
    return dfs

# --- Sidebar ------------------------------------------------------------------

with st.sidebar:
    col_logo = st.columns([1, 4, 2])
    with col_logo[1]:
        st.image(os.path.join(os.path.dirname(__file__), "images", "LOGO.jpg"), width=180)
    st.title("🌱 Tissu Agricole")
    st.caption("Togo - Données 2024")
    st.divider()

    region_filter = st.selectbox("Région", REGIONS)
    st.divider()

    st.markdown("**Couches cartographiques**")
    show_grandes = st.checkbox("Grandes Exploitations", True)
    show_plantations = st.checkbox("Plantations", True)
    show_pepinieres = st.checkbox("Pépinières", True)
    show_cooperatives = st.checkbox("Coopératives", True)
    show_marches = st.checkbox("Marchés", True)
    show_zaaps = st.checkbox("ZAAPs (périmètres)", True)
    show_petites = st.checkbox("Petites Exploitations", False)
    st.divider()

    st.markdown("**Sources**")
    st.caption("geodata.gouv.tg · opendata.gouv.tg")

with st.spinner("Chargement des données..."):
    dfs = load_data()

def filter_region(df):
    if region_filter == "Toutes":
        return df
    return df[df["region_nom_bdd"] == region_filter]

grandes = filter_region(dfs["grandes"])
petites = filter_region(dfs["petites"])
plantations = filter_region(dfs["plantations"])
cooperatives = filter_region(dfs["cooperatives"])
marches = filter_region(dfs["marches"])
pepinieres = filter_region(dfs["pepinieres"])
zaaps_formes = filter_region(dfs["zaaps_formes"])
zaaps_champs = filter_region(dfs["zaaps_champs"])

# --- Header -------------------------------------------------------------------

st.title("🌿 Géographie du Tissu Agricole au Togo")
st.caption(f"Région sélectionnée : **{region_filter}** · Données 2024")

# --- KPIs ---------------------------------------------------------------------

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Grandes Exploitations", f"{len(grandes):,}")
k2.metric("Petites Exploitations", f"{len(petites):,}")
k3.metric("Plantations", f"{len(plantations):,}")
k4.metric("Coopératives", f"{len(cooperatives):,}")
k5.metric("Marchés", f"{len(marches):,}")
k6.metric("ZAAPs", f"{len(zaaps_formes):,}")

st.divider()

# --- Tabs ---------------------------------------------------------------------

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🗺️ Carte Interactive",
    "📊 Densités & Distributions",
    "🤝 Réseau Coopératif",
    "🏞️ Couverture ZAAPs",
    "🛒 Marchés & Services",
])

# ==============================================================================
# TAB 1 - CARTE INTERACTIVE
# ==============================================================================

with tab1:
    st.subheader("Carte Interactive du Tissu Agricole")

    center_lat, center_lon = 8.0, 1.0
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=7,
        tiles="CartoDB positron",
        control_scale=True,
    )
    MiniMap(toggle_display=True).add_to(m)

    # Helper to add a cluster layer
    def add_point_layer(df, label, color, icon_name="leaf"):
        if df.empty:
            return
        cluster = MarkerCluster(name=label, show=True)
        sample = df.head(800)  # limit for performance
        for _, row in sample.iterrows():
            popup_html = f"<b>{label}</b><br>"
            for col in ["region_nom_bdd", "prefecture_nom_bdd", "commune_nom_bdd", "nom_localite"]:
                if col in row and pd.notna(row[col]):
                    popup_html += f"{col.replace('_nom_bdd','').replace('_',' ').title()}: {row[col]}<br>"
            for col in ["cooperative_nom", "marche_nom", "exploitation_nom", "etab_nom", "zaap_nom"]:
                if col in row and pd.notna(row[col]):
                    popup_html += f"<b>{row[col]}</b><br>"
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=5,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.7,
                popup=folium.Popup(popup_html, max_width=250),
            ).add_to(cluster)
        cluster.add_to(m)

    if show_grandes:
        add_point_layer(grandes, "Grandes Exploitations", LAYER_COLORS["Grandes Exploitations"])
    if show_plantations:
        add_point_layer(plantations, "Plantations", LAYER_COLORS["Plantations"])
    if show_pepinieres:
        add_point_layer(pepinieres, "Pépinières", LAYER_COLORS["Pépinières"])
    if show_cooperatives:
        add_point_layer(cooperatives, "Coopératives", LAYER_COLORS["Coopératives"])
    if show_marches:
        add_point_layer(marches, "Marchés", LAYER_COLORS["Marchés"])
    if show_petites:
        add_point_layer(petites, "Petites Exploitations", LAYER_COLORS["Petites Exploitations"])

    # ZAAPs as polygons
    if show_zaaps:
        zaap_group = folium.FeatureGroup(name="ZAAPs (périmètres)", show=True)
        for _, row in zaaps_formes.iterrows():
            coords = get_polygon_coords(str(row["geometry"]))
            if len(coords) > 2:
                name = row.get("zaap_nom", "ZAAP")
                folium.Polygon(
                    locations=coords,
                    color="#795548",
                    fill=True,
                    fill_color="#795548",
                    fill_opacity=0.3,
                    weight=2,
                    popup=folium.Popup(f"<b>{name}</b><br>{row.get('prefecture_nom_bdd','')}", max_width=200),
                ).add_to(zaap_group)
        zaap_group.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # Legend
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;
         padding:10px 14px;border-radius:8px;box-shadow:2px 2px 6px rgba(0,0,0,.3);font-size:12px;">
    <b>Légende</b><br>
    """
    for label, color in LAYER_COLORS.items():
        legend_html += f'<span style="color:{color}">●</span> {label}<br>'
    legend_html += "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))

    st_folium(m, width="100%", height=600, returned_objects=[])

    st.caption("💡 Les marqueurs sont regroupés automatiquement. Cliquez pour zoomer et explorer.")

# ==============================================================================
# TAB 2 - DENSITES & DISTRIBUTIONS
# ==============================================================================

with tab2:
    st.subheader("Densités et Distributions par Région")

    # Combine all point datasets for regional summary
    summary_data = []
    datasets_info = [
        (dfs["grandes"], "Grandes Exploitations"),
        (dfs["plantations"], "Plantations"),
        (dfs["cooperatives"], "Coopératives"),
        (dfs["marches"], "Marchés"),
        (dfs["pepinieres"], "Pépinières"),
        (dfs["petites"], "Petites Exploitations"),
    ]
    for df, label in datasets_info:
        cnt = df.groupby("region_nom_bdd").size().reset_index(name="count")
        cnt["type"] = label
        summary_data.append(cnt)

    summary = pd.concat(summary_data, ignore_index=True)

    c1, c2 = st.columns(2)

    with c1:
        # Stacked bar by region
        pivot = summary.pivot_table(index="region_nom_bdd", columns="type", values="count", fill_value=0)
        fig_stack = px.bar(
            pivot.reset_index(),
            x="region_nom_bdd",
            y=[c for c in pivot.columns],
            title="Entités agricoles par région",
            labels={"region_nom_bdd": "Région", "value": "Nombre", "variable": "Type"},
            color_discrete_map=LAYER_COLORS,
            barmode="stack",
            height=400,
        )
        fig_stack.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig_stack, use_container_width=True)

    with c2:
        # Treemap total
        total_by_type = summary.groupby("type")["count"].sum().reset_index()
        fig_tree = px.treemap(
            total_by_type,
            path=["type"],
            values="count",
            title="Répartition globale par type d'entité",
            color="type",
            color_discrete_map=LAYER_COLORS,
            height=400,
        )
        fig_tree.update_traces(textinfo="label+value+percent root")
        st.plotly_chart(fig_tree, use_container_width=True)

    # Région focus
    st.markdown("#### Focus par type d'entité")
    c3, c4 = st.columns(2)
    with c3:
        fig_grandes = px.bar(
            dfs["grandes"].groupby("region_nom_bdd").size().reset_index(name="count"),
            x="region_nom_bdd", y="count",
            title="Grandes Exploitations par région",
            color="region_nom_bdd",
            color_discrete_map={r: REGION_COLORS.get(r, "#888") for r in REGIONS[1:]},
            labels={"region_nom_bdd": "Région", "count": "Nombre"},
            height=300,
        )
        fig_grandes.update_layout(showlegend=False)
        st.plotly_chart(fig_grandes, use_container_width=True)

    with c4:
        if "exploitation_annee" in dfs["grandes"].columns:
            ann = dfs["grandes"].copy()
            ann = ann[pd.to_numeric(ann["exploitation_annee"], errors="coerce").notna()]
            ann["exploitation_annee"] = ann["exploitation_annee"].astype(int)
            fig_year = px.histogram(
                ann, x="exploitation_annee",
                title="Grandes Exploitations - Année de création",
                nbins=20,
                color_discrete_sequence=["#E53935"],
                labels={"exploitation_annee": "Année", "count": "Nombre"},
                height=300,
            )
            st.plotly_chart(fig_year, use_container_width=True)

    c5, c6 = st.columns(2)
    with c5:
        fig_coop_region = px.bar(
            dfs["cooperatives"].groupby("region_nom_bdd").size().reset_index(name="count"),
            x="region_nom_bdd", y="count",
            title="Coopératives par région",
            color="region_nom_bdd",
            color_discrete_map={r: REGION_COLORS.get(r, "#888") for r in REGIONS[1:]},
            labels={"region_nom_bdd": "Région", "count": "Nombre"},
            height=300,
        )
        fig_coop_region.update_layout(showlegend=False)
        st.plotly_chart(fig_coop_region, use_container_width=True)

    with c6:
        fig_plant = px.bar(
            dfs["plantations"].groupby("region_nom_bdd").size().reset_index(name="count"),
            x="region_nom_bdd", y="count",
            title="Plantations par région",
            color="region_nom_bdd",
            color_discrete_map={r: REGION_COLORS.get(r, "#888") for r in REGIONS[1:]},
            labels={"region_nom_bdd": "Région", "count": "Nombre"},
            height=300,
        )
        fig_plant.update_layout(showlegend=False)
        st.plotly_chart(fig_plant, use_container_width=True)

    # Petites exploitations - top préfectures
    st.markdown("#### Petites Exploitations - Top 15 préfectures")
    top_pref = (
        dfs["petites"]
        .groupby(["region_nom_bdd", "prefecture_nom_bdd"])
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .head(15)
    )
    top_pref["label"] = top_pref["prefecture_nom_bdd"] + " (" + top_pref["region_nom_bdd"] + ")"
    fig_pref = px.bar(
        top_pref.sort_values("count"),
        x="count", y="label",
        orientation="h",
        title="Top 15 préfectures - Petites Exploitations Agricoles",
        color="region_nom_bdd",
        color_discrete_map={r: REGION_COLORS.get(r, "#888") for r in REGIONS[1:]},
        labels={"count": "Nombre", "label": "Préfecture", "region_nom_bdd": "Région"},
        height=450,
    )
    st.plotly_chart(fig_pref, use_container_width=True)

# ==============================================================================
# TAB 3 - RESEAU COOPERATIF
# ==============================================================================

with tab3:
    st.subheader("Réseau Coopératif Agricole")

    df_coop = dfs["cooperatives"] if region_filter == "Toutes" else cooperatives

    c1, c2 = st.columns([1, 1])

    with c1:
        # Cooperative type breakdown
        if "cooperative_statut" in df_coop.columns:
            statut_cnt = df_coop["cooperative_statut"].value_counts().reset_index()
            statut_cnt.columns = ["statut", "count"]
            fig_statut = px.pie(
                statut_cnt,
                names="statut", values="count",
                title="Statut des Coopératives",
                color_discrete_sequence=px.colors.qualitative.Set2,
                height=350,
            )
            fig_statut.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig_statut, use_container_width=True)

    with c2:
        # Type breakdown
        if "cooperative_type" in df_coop.columns:
            type_cnt = df_coop["cooperative_type"].value_counts().reset_index()
            type_cnt.columns = ["type", "count"]
            fig_type = px.bar(
                type_cnt.head(10),
                x="count", y="type",
                orientation="h",
                title="Types de Coopératives",
                color_discrete_sequence=["#3F51B5"],
                labels={"count": "Nombre", "type": "Type"},
                height=350,
            )
            st.plotly_chart(fig_type, use_container_width=True)

    # Region / prefecture breakdown
    st.markdown("#### Distribution géographique")
    c3, c4 = st.columns(2)
    with c3:
        coop_reg = df_coop.groupby("region_nom_bdd").size().reset_index(name="count")
        fig_creg = px.bar(
            coop_reg.sort_values("count", ascending=True),
            x="count", y="region_nom_bdd",
            orientation="h",
            title="Coopératives par région",
            color="region_nom_bdd",
            color_discrete_map={r: REGION_COLORS.get(r, "#888") for r in REGIONS[1:]},
            labels={"count": "Nombre", "region_nom_bdd": "Région"},
            height=300,
        )
        fig_creg.update_layout(showlegend=False)
        st.plotly_chart(fig_creg, use_container_width=True)

    with c4:
        top_pref_coop = (
            df_coop.groupby("prefecture_nom_bdd").size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
            .head(10)
        )
        fig_cpref = px.bar(
            top_pref_coop.sort_values("count"),
            x="count", y="prefecture_nom_bdd",
            orientation="h",
            title="Top 10 préfectures - Coopératives",
            color_discrete_sequence=["#5C6BC0"],
            labels={"count": "Nombre", "prefecture_nom_bdd": "Préfecture"},
            height=300,
        )
        st.plotly_chart(fig_cpref, use_container_width=True)

    # Carte coopératives
    st.markdown("#### Carte des Coopératives")
    m_coop = folium.Map(location=[8.0, 1.0], zoom_start=7, tiles="CartoDB positron")
    coop_cluster = MarkerCluster()
    for _, row in df_coop.head(1000).iterrows():
        coop_type = str(row.get("cooperative_type", ""))
        coop_nom = row.get("cooperative_nom", "N/A")
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=5,
            color=LAYER_COLORS["Coopératives"],
            fill=True,
            fill_color=LAYER_COLORS["Coopératives"],
            fill_opacity=0.8,
            popup=folium.Popup(
                f"<b>{coop_nom}</b><br>Type: {coop_type}<br>{row.get('prefecture_nom_bdd','')}<br>{row.get('commune_nom_bdd','')}",
                max_width=250,
            ),
        ).add_to(coop_cluster)
    coop_cluster.add_to(m_coop)
    st_folium(m_coop, width="100%", height=400, returned_objects=[])

# ==============================================================================
# TAB 4 - ZAAPs
# ==============================================================================

with tab4:
    st.subheader("Zones d'Aménagement Agricole Planifiées (ZAAPs)")

    df_zaap_f = dfs["zaaps_formes"] if region_filter == "Toutes" else zaaps_formes
    df_zaap_c = dfs["zaaps_champs"] if region_filter == "Toutes" else zaaps_champs

    c1, c2, c3 = st.columns(3)
    c1.metric("Périmètres ZAAP", len(df_zaap_f))
    c2.metric("Champs Individuels", len(df_zaap_c))
    c3.metric("Préfectures couvertes", df_zaap_f["prefecture_nom_bdd"].nunique() if not df_zaap_f.empty else 0)

    c1, c2 = st.columns(2)

    with c1:
        zaap_reg = df_zaap_f.groupby("region_nom_bdd").size().reset_index(name="count")
        fig_zreg = px.bar(
            zaap_reg.sort_values("count", ascending=True),
            x="count", y="region_nom_bdd",
            orientation="h",
            title="Périmètres ZAAP par région",
            color="region_nom_bdd",
            color_discrete_map={r: REGION_COLORS.get(r, "#888") for r in REGIONS[1:]},
            labels={"count": "Nombre de ZAAPs", "region_nom_bdd": "Région"},
            height=300,
        )
        fig_zreg.update_layout(showlegend=False)
        st.plotly_chart(fig_zreg, use_container_width=True)

    with c2:
        zaap_champs_reg = df_zaap_c.groupby("region_nom_bdd").size().reset_index(name="count")
        fig_zcreg = px.bar(
            zaap_champs_reg.sort_values("count", ascending=True),
            x="count", y="region_nom_bdd",
            orientation="h",
            title="Champs individuels ZAAP par région",
            color="region_nom_bdd",
            color_discrete_map={r: REGION_COLORS.get(r, "#888") for r in REGIONS[1:]},
            labels={"count": "Nombre", "region_nom_bdd": "Région"},
            height=300,
        )
        fig_zcreg.update_layout(showlegend=False)
        st.plotly_chart(fig_zcreg, use_container_width=True)

    # Type de coopérative dans les champs ZAAP
    if "cooperative_type" in df_zaap_c.columns:
        st.markdown("#### Types d'organisation dans les champs ZAAP")
        # Parse multi-valued field
        type_series = df_zaap_c["cooperative_type"].dropna().str.strip("{}")
        all_types = []
        for val in type_series:
            types = [t.strip() for t in val.split(",") if t.strip() and t.strip() not in ("Nsp", "nsp")]
            all_types.extend(types)
        if all_types:
            type_df = pd.Series(all_types).value_counts().reset_index()
            type_df.columns = ["type", "count"]
            fig_zaap_type = px.bar(
                type_df.head(10),
                x="count", y="type",
                orientation="h",
                title="Types d'organisation dans les champs ZAAP/ZAPB",
                color_discrete_sequence=["#795548"],
                labels={"count": "Nombre", "type": "Type"},
                height=350,
            )
            st.plotly_chart(fig_zaap_type, use_container_width=True)

    # Carte ZAAPs
    st.markdown("#### Carte des périmètres ZAAPs")
    m_zaap = folium.Map(location=[8.0, 1.0], zoom_start=7, tiles="CartoDB positron")

    for _, row in df_zaap_f.iterrows():
        coords = get_polygon_coords(str(row["geometry"]))
        if len(coords) > 2:
            folium.Polygon(
                locations=coords,
                color="#795548",
                fill=True,
                fill_color="#4CAF50",
                fill_opacity=0.4,
                weight=2,
                popup=folium.Popup(
                    f"<b>{row.get('zaap_nom','ZAAP')}</b><br>{row.get('canton_nom_bdd','')}<br>{row.get('prefecture_nom_bdd','')}",
                    max_width=200,
                ),
            ).add_to(m_zaap)

    zaap_champ_cluster = MarkerCluster(name="Champs individuels")
    for _, row in df_zaap_c.head(500).iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=4,
            color="#607D8B",
            fill=True,
            fill_color="#607D8B",
            fill_opacity=0.6,
            popup=folium.Popup(
                f"Champ: {row.get('cooperative_nom','N/A')}<br>{row.get('prefecture_nom_bdd','')}",
                max_width=200,
            ),
        ).add_to(zaap_champ_cluster)
    zaap_champ_cluster.add_to(m_zaap)
    folium.LayerControl().add_to(m_zaap)
    st_folium(m_zaap, width="100%", height=450, returned_objects=[])

# ==============================================================================
# TAB 5 - MARCHES & SERVICES
# ==============================================================================

with tab5:
    st.subheader("Marchés & Services Agricoles")

    df_marche = dfs["marches"] if region_filter == "Toutes" else marches
    df_pep = dfs["pepinieres"] if region_filter == "Toutes" else pepinieres

    c1, c2, c3 = st.columns(3)
    c1.metric("Marchés recensés", len(df_marche))
    c2.metric("Pépinières agricoles", len(df_pep))
    c3.metric("Préfectures avec marché", df_marche["prefecture_nom_bdd"].nunique() if not df_marche.empty else 0)

    c1, c2 = st.columns(2)

    with c1:
        marche_reg = df_marche.groupby("region_nom_bdd").size().reset_index(name="count")
        fig_mreg = px.bar(
            marche_reg.sort_values("count", ascending=True),
            x="count", y="region_nom_bdd",
            orientation="h",
            title="Marchés par région",
            color="region_nom_bdd",
            color_discrete_map={r: REGION_COLORS.get(r, "#888") for r in REGIONS[1:]},
            labels={"count": "Nombre", "region_nom_bdd": "Région"},
            height=300,
        )
        fig_mreg.update_layout(showlegend=False)
        st.plotly_chart(fig_mreg, use_container_width=True)

    with c2:
        pep_reg = df_pep.groupby("region_nom_bdd").size().reset_index(name="count")
        fig_preg = px.bar(
            pep_reg.sort_values("count", ascending=True),
            x="count", y="region_nom_bdd",
            orientation="h",
            title="Pépinières par région",
            color="region_nom_bdd",
            color_discrete_map={r: REGION_COLORS.get(r, "#888") for r in REGIONS[1:]},
            labels={"count": "Nombre", "region_nom_bdd": "Région"},
            height=300,
        )
        fig_preg.update_layout(showlegend=False)
        st.plotly_chart(fig_preg, use_container_width=True)

    # Jours de marché
    if "jour" in df_marche.columns:
        st.markdown("#### Fréquence d'ouverture des marchés")
        def count_days(jour_str):
            if not isinstance(jour_str, str):
                return 0
            days = re.findall(r'lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche', jour_str.lower())
            return len(days)
        df_marche_copy = df_marche.copy()
        df_marche_copy["nb_jours"] = df_marche_copy["jour"].apply(count_days)
        day_dist = df_marche_copy["nb_jours"].value_counts().sort_index().reset_index()
        day_dist.columns = ["nb_jours", "count"]
        day_dist["label"] = day_dist["nb_jours"].apply(
            lambda x: "7j/7" if x == 7 else f"{x} jour(s)/sem." if x > 0 else "Non renseigné"
        )
        fig_days = px.pie(
            day_dist,
            names="label", values="count",
            title="Répartition des marchés par nombre de jours d'ouverture",
            color_discrete_sequence=px.colors.sequential.Teal,
            height=350,
        )
        fig_days.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig_days, use_container_width=True)

    # Terrain type pépinières
    if "terrain" in df_pep.columns:
        st.markdown("#### Type de terrain - Pépinières")
        terrain_cnt = df_pep["terrain"].value_counts().reset_index()
        terrain_cnt.columns = ["terrain", "count"]
        fig_terrain = px.bar(
            terrain_cnt,
            x="count", y="terrain",
            orientation="h",
            title="Pépinières par type de terrain",
            color_discrete_sequence=["#FF9800"],
            labels={"count": "Nombre", "terrain": "Type de terrain"},
            height=300,
        )
        st.plotly_chart(fig_terrain, use_container_width=True)

    # Carte Marchés + Pépinières
    st.markdown("#### Carte des Marchés et Pépinières")
    m_serv = folium.Map(location=[8.0, 1.0], zoom_start=7, tiles="CartoDB positron")

    marche_group = folium.FeatureGroup(name="Marchés", show=True)
    for _, row in df_marche.head(600).iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=6,
            color=LAYER_COLORS["Marchés"],
            fill=True,
            fill_color=LAYER_COLORS["Marchés"],
            fill_opacity=0.7,
            popup=folium.Popup(
                f"<b>{row.get('marche_nom','Marché')}</b><br>{row.get('prefecture_nom_bdd','')}<br>Jours: {row.get('jour','')}",
                max_width=250,
            ),
        ).add_to(marche_group)
    marche_group.add_to(m_serv)

    pep_group = folium.FeatureGroup(name="Pépinières", show=True)
    for _, row in df_pep.iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=5,
            color=LAYER_COLORS["Pépinières"],
            fill=True,
            fill_color=LAYER_COLORS["Pépinières"],
            fill_opacity=0.8,
            popup=folium.Popup(
                f"<b>{row.get('etab_nom','Pépinière')}</b><br>{row.get('prefecture_nom_bdd','')}<br>Terrain: {row.get('terrain','')}",
                max_width=250,
            ),
        ).add_to(pep_group)
    pep_group.add_to(m_serv)

    folium.LayerControl().add_to(m_serv)
    st_folium(m_serv, width="100%", height=450, returned_objects=[])

# --- Footer -------------------------------------------------------------------
st.divider()
st.caption(
    "📊 **Dashboard Tissu Agricole du Togo** · "
    "Données : geodata.gouv.tg & opendata.gouv.tg · "
    "Défi Data Agriculture #1 · Juin 2026"
)
