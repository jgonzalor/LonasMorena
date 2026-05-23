
import base64
import html
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import folium
import pandas as pd
import streamlit as st
from folium.plugins import MarkerCluster, Fullscreen, MeasureControl
from streamlit_folium import st_folium

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
IMG_DIR = DATA_DIR / "evidencias"
REVIEWS_DIR = APP_DIR / "reviews"
REVIEWS_FILE = REVIEWS_DIR / "revisiones_lonas.json"
MAPEABLES_CSV = DATA_DIR / "lonas_mapeables.csv"
PENDIENTES_CSV = DATA_DIR / "lonas_pendientes_sin_coordenada.csv"

# Paleta visual inspirada en Morena: guinda, beige cálido, blanco y acentos dorados.
MORENA_GUINDA = "#8A1538"
MORENA_GUINDA_DARK = "#5B0F2E"
MORENA_GUINDA_SOFT = "#B44463"
MORENA_BEIGE = "#F6EFE7"
MORENA_BEIGE_2 = "#FBF8F4"
MORENA_DORADO = "#B08968"
MORENA_GREEN = "#1B8A5A"
TEXT_DARK = "#272124"

STATUS_OPTIONS = [
    "Pendiente",
    "Verificado",
    "Corregir ubicación",
    "Retirar/Reponer lona",
    "No localizada",
]

STATUS_COLORS = {
    "Pendiente": MORENA_GUINDA,
    "Verificado": MORENA_GREEN,
    "Corregir ubicación": "#F59E0B",
    "Retirar/Reponer lona": "#B91C1C",
    "No localizada": "#111827",
}

TILE_OPTIONS = {
    "Calles claro": {
        "tiles": "CartoDB positron",
        "attr": "CartoDB / OpenStreetMap",
    },
    "Calles OSM": {
        "tiles": "OpenStreetMap",
        "attr": "OpenStreetMap",
    },
    "Satélite": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Esri World Imagery",
    },
    "Terreno / relieve": {
        "tiles": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        "attr": "Map data: OpenStreetMap contributors, SRTM | Map style: OpenTopoMap",
    },
    "Oscuro": {
        "tiles": "CartoDB dark_matter",
        "attr": "CartoDB / OpenStreetMap",
    },
}

st.set_page_config(
    page_title="Supervisión de Lonas",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
    :root {{
        --guinda: {MORENA_GUINDA};
        --guinda-dark: {MORENA_GUINDA_DARK};
        --guinda-soft: {MORENA_GUINDA_SOFT};
        --beige: {MORENA_BEIGE};
        --beige2: {MORENA_BEIGE_2};
        --dorado: {MORENA_DORADO};
        --texto: {TEXT_DARK};
    }}

    .stApp {{
        background: linear-gradient(180deg, #fffdf9 0%, var(--beige2) 45%, #ffffff 100%);
        color: var(--texto);
    }}

    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #ffffff 0%, var(--beige) 100%);
        border-right: 1px solid rgba(138, 21, 56, .14);
    }}

    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] label {{
        color: var(--guinda-dark) !important;
    }}

    .block-container {{
        padding-top: 1.4rem;
        padding-bottom: 2rem;
    }}

    .hero-card {{
        border-radius: 22px;
        padding: 22px 26px;
        margin-bottom: 18px;
        color: white;
        background: linear-gradient(135deg, var(--guinda-dark) 0%, var(--guinda) 52%, var(--guinda-soft) 100%);
        box-shadow: 0 18px 42px rgba(91, 15, 46, .22);
        border: 1px solid rgba(255,255,255,.25);
    }}

    .hero-title {{
        font-size: 2.05rem;
        line-height: 1.1;
        font-weight: 800;
        letter-spacing: -.02em;
        margin: 0 0 6px 0;
    }}

    .hero-subtitle {{
        font-size: .98rem;
        margin: 0;
        opacity: .92;
    }}

    .kpi-card {{
        background: rgba(255,255,255,.92);
        border: 1px solid rgba(138, 21, 56, .13);
        border-radius: 18px;
        padding: 15px 17px;
        box-shadow: 0 10px 25px rgba(39,33,36,.06);
        min-height: 92px;
    }}

    .kpi-label {{
        color: #6b5f64;
        font-size: .78rem;
        text-transform: uppercase;
        letter-spacing: .08em;
        font-weight: 700;
        margin-bottom: 7px;
    }}

    .kpi-number {{
        color: var(--guinda-dark);
        font-size: 2rem;
        font-weight: 800;
        line-height: 1;
    }}

    .section-card {{
        background: rgba(255,255,255,.94);
        border: 1px solid rgba(138, 21, 56, .12);
        border-radius: 18px;
        padding: 16px 18px;
        box-shadow: 0 10px 22px rgba(39,33,36,.055);
        margin-bottom: 12px;
    }}

    .legend-dot {{
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        margin-right: 8px;
        vertical-align: middle;
        border: 1px solid rgba(0,0,0,.10);
    }}

    .note-box {{
        background: #fff8ef;
        border: 1px solid rgba(176,137,104,.35);
        border-left: 5px solid var(--dorado);
        border-radius: 14px;
        padding: 12px 14px;
        color: #4d3a2e;
        margin: 10px 0;
    }}

    .stButton > button,
    .stDownloadButton > button,
    div[data-testid="stFormSubmitButton"] button {{
        border-radius: 12px !important;
        border: 1px solid rgba(138, 21, 56, .18) !important;
        font-weight: 700 !important;
    }}

    div[data-testid="stFormSubmitButton"] button,
    .stDownloadButton > button[kind="primary"] {{
        background: var(--guinda) !important;
        color: white !important;
    }}

    div[data-baseweb="tab-list"] {{
        gap: 8px;
        border-bottom: 1px solid rgba(138,21,56,.16);
    }}

    button[data-baseweb="tab"] {{
        background: rgba(138,21,56,.06);
        border-radius: 999px 999px 0 0;
        padding: 8px 16px;
    }}

    button[data-baseweb="tab"][aria-selected="true"] {{
        color: var(--guinda) !important;
        border-bottom-color: var(--guinda) !important;
        font-weight: 800;
    }}

    iframe {{
        border-radius: 16px;
        border: 1px solid rgba(138,21,56,.18) !important;
        box-shadow: 0 12px 26px rgba(39,33,36,.08);
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# Utilidades de carga y limpieza
# -----------------------------
@st.cache_data(show_spinner=False)
def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    for col in ["latitud", "longitud", "lonas_colocadas", "meta", "avance"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "fila_excel" in df.columns:
        df["fila_excel"] = pd.to_numeric(df["fila_excel"], errors="coerce").astype("Int64")
    return df


def ensure_reviews_file() -> None:
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    if not REVIEWS_FILE.exists():
        REVIEWS_FILE.write_text("{}", encoding="utf-8")


def load_reviews() -> Dict[str, dict]:
    ensure_reviews_file()
    try:
        return json.loads(REVIEWS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_reviews(reviews: Dict[str, dict]) -> None:
    ensure_reviews_file()
    REVIEWS_FILE.write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def image_files_for_row(row_id: int) -> List[Path]:
    if pd.isna(row_id):
        return []
    pattern = f"fila_{int(row_id)}_evidencia_"
    return sorted([p for p in IMG_DIR.glob(f"{pattern}*.*") if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]])


def img_to_base64(path: Path) -> Optional[str]:
    try:
        data = path.read_bytes()
        ext = path.suffix.lower().lstrip(".") or "jpg"
        if ext == "jpg":
            ext = "jpeg"
        return f"data:image/{ext};base64," + base64.b64encode(data).decode("ascii")
    except Exception:
        return None


def apply_reviews(df: pd.DataFrame, reviews: Dict[str, dict]) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    out["estatus"] = "Pendiente"
    out["supervisor"] = ""
    out["nota_supervision"] = ""
    out["latitud_corregida"] = pd.NA
    out["longitud_corregida"] = pd.NA
    out["fecha_revision"] = ""

    for idx, row in out.iterrows():
        key = str(int(row["fila_excel"])) if not pd.isna(row.get("fila_excel")) else ""
        review = reviews.get(key, {})
        if review:
            out.at[idx, "estatus"] = review.get("estatus", "Pendiente") or "Pendiente"
            out.at[idx, "supervisor"] = review.get("supervisor", "")
            out.at[idx, "nota_supervision"] = review.get("nota_supervision", "")
            out.at[idx, "fecha_revision"] = review.get("fecha_revision", "")
            latc = review.get("latitud_corregida", "")
            lonc = review.get("longitud_corregida", "")
            out.at[idx, "latitud_corregida"] = pd.to_numeric(latc, errors="coerce")
            out.at[idx, "longitud_corregida"] = pd.to_numeric(lonc, errors="coerce")

    out["latitud_mapa"] = out["latitud_corregida"].combine_first(out["latitud"])
    out["longitud_mapa"] = out["longitud_corregida"].combine_first(out["longitud"])
    return out


def filter_df(df: pd.DataFrame, distritos, secciones, estatuses, query: str) -> pd.DataFrame:
    out = df.copy()
    if distritos:
        out = out[out["distrito_local"].astype(str).isin([str(x) for x in distritos])]
    if secciones:
        out = out[out["seccion"].astype(str).isin([str(x) for x in secciones])]
    if estatuses:
        out = out[out["estatus"].isin(estatuses)]
    q = normalize_text(query).lower()
    if q:
        cols = [c for c in ["colonia", "direccion", "observaciones", "responsable", "municipio", "seccion", "distrito_local"] if c in out.columns]
        mask = pd.Series(False, index=out.index)
        for col in cols:
            mask = mask | out[col].astype(str).str.lower().str.contains(re.escape(q), na=False, regex=True)
        out = out[mask]
    return out


def make_popup_html(row: pd.Series, include_img: bool = True) -> str:
    row_id = int(row["fila_excel"])
    img_html = ""
    if include_img:
        imgs = image_files_for_row(row_id)
        if imgs:
            src = img_to_base64(imgs[0])
            if src:
                img_html = f"""
                <div style='margin-top:10px'>
                    <img src='{src}' style='max-width:260px; max-height:190px; border-radius:10px; border:1px solid #e5d8cf;'>
                </div>
                """
    maps_link = html.escape(str(row.get("link_maps", "")))
    link_html = f"<a href='{maps_link}' target='_blank' style='color:{MORENA_GUINDA};font-weight:bold'>Abrir en Google Maps</a>" if maps_link else ""
    status = html.escape(str(row.get('estatus','Pendiente')))
    status_color = STATUS_COLORS.get(str(row.get('estatus','Pendiente')), MORENA_GUINDA)
    body = f"""
    <div style='font-family:Arial; width:290px; color:#272124'>
      <h4 style='margin:0 0 8px 0; color:{MORENA_GUINDA_DARK}'>Lona | Fila Excel {row_id}</h4>
      <div style='display:inline-block;background:{status_color};color:white;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:bold;margin-bottom:8px'>{status}</div><br>
      <b>Distrito:</b> {html.escape(str(row.get('distrito_local','')))} &nbsp; <b>Sección:</b> {html.escape(str(row.get('seccion','')))}<br>
      <b>Colonia:</b> {html.escape(str(row.get('colonia','')))}<br>
      <b>Dirección:</b> {html.escape(str(row.get('direccion','')))}<br>
      <b>Observaciones:</b> {html.escape(str(row.get('observaciones','')))}<br>
      <b>Supervisor:</b> {html.escape(str(row.get('supervisor','')))}<br>
      <b>Nota:</b> {html.escape(str(row.get('nota_supervision','')))}<br>
      {link_html}
      {img_html}
    </div>
    """
    return body


def add_tile_layers(m: folium.Map, selected_tile: str) -> None:
    selected_tile = selected_tile if selected_tile in TILE_OPTIONS else "Calles claro"
    for name, cfg in TILE_OPTIONS.items():
        folium.TileLayer(
            tiles=cfg["tiles"],
            attr=cfg["attr"],
            name=name,
            overlay=False,
            control=True,
            show=(name == selected_tile),
        ).add_to(m)


def make_map(
    df: pd.DataFrame,
    selected_row_id: Optional[int] = None,
    selected_tile: str = "Calles claro",
    cluster_points: bool = False,
) -> folium.Map:
    valid = df.dropna(subset=["latitud_mapa", "longitud_mapa"]).copy()
    if valid.empty:
        m = folium.Map(location=[25.79, -109.0], zoom_start=12, tiles=None, control_scale=True)
        add_tile_layers(m, selected_tile)
        folium.LayerControl(collapsed=False).add_to(m)
        return m

    center = [valid["latitud_mapa"].mean(), valid["longitud_mapa"].mean()]
    m = folium.Map(location=center, zoom_start=13, tiles=None, control_scale=True)
    add_tile_layers(m, selected_tile)

    target_layer = MarkerCluster(name="Lonas agrupadas").add_to(m) if cluster_points else folium.FeatureGroup(name="Lonas", show=True).add_to(m)

    for _, row in valid.iterrows():
        row_id = int(row["fila_excel"])
        status = str(row.get("estatus", "Pendiente")) or "Pendiente"
        color = STATUS_COLORS.get(status, MORENA_GUINDA)
        radius = 12 if selected_row_id == row_id else 7
        folium.CircleMarker(
            location=[float(row["latitud_mapa"]), float(row["longitud_mapa"])],
            radius=radius,
            popup=folium.Popup(make_popup_html(row), max_width=360),
            tooltip=f"Fila {row_id} | D{row.get('distrito_local','')} S{row.get('seccion','')} | {status}",
            color="#FFFFFF" if selected_row_id == row_id else color,
            weight=3 if selected_row_id == row_id else 2,
            fill=True,
            fill_color=color,
            fill_opacity=0.90,
        ).add_to(target_layer)

    if selected_row_id:
        sel = valid[valid["fila_excel"].astype(int) == int(selected_row_id)]
        if not sel.empty:
            row = sel.iloc[0]
            folium.Marker(
                location=[float(row["latitud_mapa"]), float(row["longitud_mapa"])],
                popup=folium.Popup(make_popup_html(row), max_width=360),
                tooltip="Registro seleccionado",
                icon=folium.Icon(color="darkred", icon="star"),
            ).add_to(m)

    Fullscreen().add_to(m)
    MeasureControl(primary_length_unit="meters", secondary_length_unit="kilometers").add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m


def kml_escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def hex_to_kml_color(hex_color: str, alpha: str = "ff") -> str:
    color = hex_color.lstrip("#")
    if len(color) != 6:
        color = "8A1538"
    rr, gg, bb = color[0:2], color[2:4], color[4:6]
    return f"{alpha}{bb}{gg}{rr}"


def build_kmz_bytes(df: pd.DataFrame, filename_prefix: str = "lonas_supervision") -> bytes:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    valid = df.dropna(subset=["latitud_mapa", "longitud_mapa"]).copy()
    kml_parts = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        "<kml xmlns='http://www.opengis.net/kml/2.2'>",
        "<Document>",
        f"<name>{filename_prefix}</name>",
        f"<description>KMZ generado desde la app de supervisión. Fecha: {kml_escape(now)}</description>",
        f"<Style id='pendiente'><IconStyle><color>{hex_to_kml_color(MORENA_GUINDA)}</color><scale>1.1</scale><Icon><href>http://maps.google.com/mapfiles/kml/pushpin/red-pushpin.png</href></Icon></IconStyle></Style>",
        f"<Style id='verificado'><IconStyle><color>{hex_to_kml_color(MORENA_GREEN)}</color><scale>1.1</scale><Icon><href>http://maps.google.com/mapfiles/kml/pushpin/grn-pushpin.png</href></Icon></IconStyle></Style>",
        f"<Style id='alerta'><IconStyle><color>{hex_to_kml_color('#B91C1C')}</color><scale>1.1</scale><Icon><href>http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png</href></Icon></IconStyle></Style>",
    ]

    for distrito, df_d in valid.groupby(valid["distrito_local"].astype(str), dropna=False):
        kml_parts.append(f"<Folder><name>Distrito Local {kml_escape(distrito)}</name>")
        for seccion, df_s in df_d.groupby(df_d["seccion"].astype(str), dropna=False):
            kml_parts.append(f"<Folder><name>Sección {kml_escape(seccion)}</name>")
            for _, row in df_s.iterrows():
                row_id = int(row["fila_excel"])
                status = str(row.get("estatus", "Pendiente")) or "Pendiente"
                style = "verificado" if status == "Verificado" else "alerta" if status not in ["Pendiente", ""] else "pendiente"
                imgs = image_files_for_row(row_id)
                img_html = ""
                if imgs:
                    img_path = f"files/{imgs[0].name}"
                    img_html = f"<br/><br/><img src='{img_path}' width='420'/>"
                desc = f"""
                <![CDATA[
                <div style='font-family:Arial'>
                  <h3>Lona | Fila Excel {row_id}</h3>
                  <b>Estatus:</b> {html.escape(status)}<br/>
                  <b>Distrito Local:</b> {html.escape(str(row.get('distrito_local','')))}<br/>
                  <b>Sección:</b> {html.escape(str(row.get('seccion','')))}<br/>
                  <b>Municipio:</b> {html.escape(str(row.get('municipio','')))}<br/>
                  <b>Colonia:</b> {html.escape(str(row.get('colonia','')))}<br/>
                  <b>Dirección:</b> {html.escape(str(row.get('direccion','')))}<br/>
                  <b>Observaciones origen:</b> {html.escape(str(row.get('observaciones','')))}<br/>
                  <b>Supervisor:</b> {html.escape(str(row.get('supervisor','')))}<br/>
                  <b>Nota supervisión:</b> {html.escape(str(row.get('nota_supervision','')))}<br/>
                  <b>Fecha revisión:</b> {html.escape(str(row.get('fecha_revision','')))}<br/>
                  {img_html}
                </div>
                ]]>
                """
                name = f"Fila {row_id} | D{row.get('distrito_local','')} S{row.get('seccion','')} | {status}"
                kml_parts.extend([
                    "<Placemark>",
                    f"<name>{kml_escape(name)}</name>",
                    f"<styleUrl>#{style}</styleUrl>",
                    f"<description>{desc}</description>",
                    "<Point>",
                    f"<coordinates>{float(row['longitud_mapa'])},{float(row['latitud_mapa'])},0</coordinates>",
                    "</Point>",
                    "</Placemark>",
                ])
            kml_parts.append("</Folder>")
        kml_parts.append("</Folder>")

    kml_parts.extend(["</Document>", "</kml>"])
    kml_text = "\n".join(kml_parts)

    buff = io.BytesIO()
    with zipfile.ZipFile(buff, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml_text.encode("utf-8"))
        added = set()
        for row_id in valid["fila_excel"].dropna().astype(int).tolist():
            for img in image_files_for_row(row_id):
                arc = f"files/{img.name}"
                if arc not in added:
                    zf.write(img, arc)
                    added.add(arc)
    return buff.getvalue()


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def render_kpi(label: str, value: object, note: str = "") -> None:
    note_html = f"<div style='font-size:.77rem;color:#7b6c72;margin-top:6px'>{html.escape(str(note))}</div>" if note else ""
    st.markdown(
        f"""
        <div class='kpi-card'>
            <div class='kpi-label'>{html.escape(str(label))}</div>
            <div class='kpi-number'>{html.escape(str(value))}</div>
            {note_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_legend() -> None:
    rows = []
    for status in STATUS_OPTIONS:
        rows.append(f"<div style='margin:7px 0'><span class='legend-dot' style='background:{STATUS_COLORS[status]}'></span>{html.escape(status)}</div>")
    st.markdown("".join(rows), unsafe_allow_html=True)


# -----------------------------
# Carga de datos
# -----------------------------
raw = load_csv(MAPEABLES_CSV)
pendientes = load_csv(PENDIENTES_CSV)
reviews = load_reviews()
df = apply_reviews(raw, reviews)

st.markdown(
    """
    <div class='hero-card'>
        <div class='hero-title'>📍 Supervisión de Lonas</div>
        <p class='hero-subtitle'>Mapa operativo para validar ubicación, evidencia fotográfica y estatus de revisión.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if df.empty:
    st.error("No se encontraron datos mapeables. Verifica que exista data/lonas_mapeables.csv.")
    st.stop()

# -----------------------------
# Sidebar: filtros y mapa
# -----------------------------
st.sidebar.markdown("### Filtros")
all_distritos = sorted(df["distrito_local"].dropna().astype(str).unique().tolist(), key=lambda x: (len(x), x))
sel_distritos = st.sidebar.multiselect("Distrito local", all_distritos, default=all_distritos)

seccion_source = df[df["distrito_local"].astype(str).isin(sel_distritos)] if sel_distritos else df
all_secciones = sorted(seccion_source["seccion"].dropna().astype(str).unique().tolist(), key=lambda x: (len(x), x))
sel_secciones = st.sidebar.multiselect("Sección", all_secciones)
sel_estatus = st.sidebar.multiselect("Estatus", STATUS_OPTIONS, default=[])
query = st.sidebar.text_input("Buscar", placeholder="Colonia, dirección, sección...")

st.sidebar.divider()
st.sidebar.markdown("### Visualización del mapa")
map_style = st.sidebar.selectbox("Tipo de mapa base", list(TILE_OPTIONS.keys()), index=0)
cluster_points = st.sidebar.checkbox("Agrupar puntos cercanos", value=False)

filtered = filter_df(df, sel_distritos, sel_secciones, sel_estatus, query)

st.sidebar.divider()
st.sidebar.markdown("### Acciones rápidas")
st.sidebar.download_button(
    "Descargar revisión filtrada CSV",
    dataframe_to_csv_bytes(filtered),
    file_name="revision_lonas_filtrada.csv",
    mime="text/csv",
    use_container_width=True,
)
# -----------------------------
# KPIs
# -----------------------------
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    render_kpi("Registros mapeados", len(df), "con coordenada")
with k2:
    render_kpi("En filtro", len(filtered), "según selección")
with k3:
    render_kpi("Verificados", int((df["estatus"] == "Verificado").sum()), "validación positiva")
with k4:
    render_kpi("Pendientes", int((df["estatus"] == "Pendiente").sum()), "por revisar")
with k5:
    render_kpi("Sin coordenada", len(pendientes), "requieren captura")

st.write("")

# -----------------------------
# Tabs
# -----------------------------
tab_map, tab_summary, tab_review, tab_table, tab_pending, tab_export, tab_help = st.tabs([
    "Mapa",
    "Resumen",
    "Supervisión",
    "Tabla de supervisión",
    "Pendientes sin coordenada",
    "Exportar",
    "Guía rápida",
])

with tab_map:
    c1, c2 = st.columns([3.25, 1])
    with c2:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.subheader("Leyenda")
        render_status_legend()
        st.caption(f"Mapa base activo: {map_style}")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.write("**Distribución por estatus**")
        if filtered.empty:
            st.caption("Sin registros con los filtros actuales.")
        else:
            st.dataframe(filtered["estatus"].value_counts().rename_axis("estatus").reset_index(name="total"), hide_index=True, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='note-box'>Puedes cambiar el mapa base desde el panel izquierdo: calles, satélite, terreno o modo oscuro.</div>", unsafe_allow_html=True)
    with c1:
        selected_for_map = st.session_state.get("selected_row_id")
        m = make_map(filtered, selected_for_map, selected_tile=map_style, cluster_points=cluster_points)
        st_folium(m, width=1280, height=680, returned_objects=[])

with tab_summary:
    st.subheader("Resumen operativo")
    a, b = st.columns([1, 1])
    with a:
        st.write("**Registros por distrito y sección**")
        if filtered.empty:
            st.warning("No hay registros con los filtros actuales.")
        else:
            dist = filtered.groupby(["distrito_local", "seccion"], dropna=False).size().reset_index(name="total")
            st.dataframe(dist.sort_values(["distrito_local", "seccion"]), hide_index=True, use_container_width=True)
    with b:
        st.write("**Estatus de supervisión**")
        status_df = filtered["estatus"].value_counts().rename_axis("estatus").reset_index(name="total") if not filtered.empty else pd.DataFrame(columns=["estatus", "total"])
        st.dataframe(status_df, hide_index=True, use_container_width=True)
        st.write("**Avance general**")
        total = len(df)
        verificados = int((df["estatus"] == "Verificado").sum())
        avance = (verificados / total * 100) if total else 0
        st.progress(avance / 100)
        st.caption(f"{avance:.1f}% verificado sobre registros mapeados.")

with tab_review:
    st.subheader("Revisión individual")
    if filtered.empty:
        st.warning("No hay registros con los filtros actuales.")
    else:
        filtered_options = filtered.sort_values(["distrito_local", "seccion", "fila_excel"]).copy()
        option_labels = {
            int(row.fila_excel): f"Fila {int(row.fila_excel)} | D{row.distrito_local} S{row.seccion} | {row.colonia} | {str(row.direccion)[:55]}"
            for _, row in filtered_options.iterrows()
        }
        default_id = st.session_state.get("selected_row_id")
        ids = list(option_labels.keys())
        default_index = ids.index(default_id) if default_id in ids else 0
        selected_id = st.selectbox(
            "Selecciona el registro a revisar",
            ids,
            index=default_index,
            format_func=lambda x: option_labels.get(x, str(x)),
        )
        st.session_state["selected_row_id"] = selected_id
        row = df[df["fila_excel"].astype(int) == int(selected_id)].iloc[0]
        key = str(int(selected_id))
        current_review = reviews.get(key, {})

        left, right = st.columns([1.15, 1])
        with left:
            st.markdown(f"### Fila Excel {selected_id}")
            st.write(f"**Distrito local:** {row.get('distrito_local','')}  |  **Sección:** {row.get('seccion','')}")
            st.write(f"**Colonia:** {row.get('colonia','')}")
            st.write(f"**Dirección:** {row.get('direccion','')}")
            st.write(f"**Observaciones origen:** {row.get('observaciones','')}")
            if str(row.get("link_maps", "")):
                st.link_button("Abrir link original de Google Maps", str(row.get("link_maps")))

            imgs = image_files_for_row(selected_id)
            if imgs:
                st.markdown("**Evidencia fotográfica**")
                for img in imgs[:3]:
                    st.image(str(img), caption=img.name, use_container_width=True)
            else:
                st.warning("No se encontró imagen de evidencia para este registro.")

        with right:
            with st.form("form_revision"):
                estatus_actual = current_review.get("estatus", row.get("estatus", "Pendiente")) or "Pendiente"
                estatus = st.selectbox("Estatus de supervisión", STATUS_OPTIONS, index=STATUS_OPTIONS.index(estatus_actual) if estatus_actual in STATUS_OPTIONS else 0)
                supervisor = st.text_input("Supervisor", value=current_review.get("supervisor", ""), placeholder="Nombre de quien revisa")
                nota = st.text_area("Nota de supervisión", value=current_review.get("nota_supervision", ""), height=120)

                st.markdown("**Corrección opcional de coordenadas**")
                st.caption("Déjalas vacías si la ubicación original es correcta.")
                lat_corr = st.text_input("Latitud corregida", value=str(current_review.get("latitud_corregida", "") or ""))
                lon_corr = st.text_input("Longitud corregida", value=str(current_review.get("longitud_corregida", "") or ""))

                guardar = st.form_submit_button("Guardar revisión", use_container_width=True)
                if guardar:
                    lat_val = lat_corr.strip()
                    lon_val = lon_corr.strip()
                    if (lat_val and not lon_val) or (lon_val and not lat_val):
                        st.error("Captura latitud y longitud corregidas, o deja ambas vacías.")
                    else:
                        coord_ok = True
                        if lat_val and lon_val:
                            try:
                                lat_f = float(lat_val)
                                lon_f = float(lon_val)
                                if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
                                    coord_ok = False
                            except Exception:
                                coord_ok = False
                        if not coord_ok:
                            st.error("Las coordenadas corregidas no son válidas.")
                        else:
                            reviews[key] = {
                                "estatus": estatus,
                                "supervisor": supervisor.strip(),
                                "nota_supervision": nota.strip(),
                                "latitud_corregida": lat_val,
                                "longitud_corregida": lon_val,
                                "fecha_revision": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            }
                            save_reviews(reviews)
                            st.success("Revisión guardada. El mapa se actualizará con el nuevo estatus/coordenada.")
                            st.rerun()

            st.markdown("**Vista rápida del punto**")
            mini = apply_reviews(df[df["fila_excel"].astype(int) == int(selected_id)], reviews)
            st_folium(make_map(mini, selected_id, selected_tile=map_style, cluster_points=False), width=650, height=320, returned_objects=[])

with tab_table:
    st.subheader("Tabla filtrada")
    show_cols = [
        "fila_excel", "fecha", "municipio", "distrito_local", "seccion", "colonia", "direccion",
        "lonas_colocadas", "meta", "avance", "estatus", "supervisor", "nota_supervision", "fecha_revision",
        "latitud_mapa", "longitud_mapa", "observaciones", "link_maps",
    ]
    show_cols = [c for c in show_cols if c in filtered.columns]
    st.dataframe(filtered[show_cols].sort_values(["distrito_local", "seccion", "fila_excel"]), use_container_width=True, hide_index=True)

with tab_pending:
    st.subheader("Registros pendientes sin coordenada directa")
    st.caption("Estos registros traen links cortos de Google Maps o no contienen latitud/longitud directa. Hay que resolverlos o capturar coordenadas manualmente.")
    if pendientes.empty:
        st.success("No hay pendientes sin coordenada.")
    else:
        st.dataframe(pendientes, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar pendientes CSV",
            dataframe_to_csv_bytes(pendientes),
            file_name="lonas_pendientes_sin_coordenada.csv",
            mime="text/csv",
            use_container_width=True,
        )

with tab_export:
    st.subheader("Exportaciones")
    st.write("Descarga los avances de supervisión y genera un KMZ actualizado con los estatus y coordenadas corregidas.")

    export_all = st.checkbox("Exportar todos los registros mapeados", value=True)
    export_df = df if export_all else filtered

    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "CSV de supervisión",
            dataframe_to_csv_bytes(export_df),
            file_name="supervision_lonas.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with c2:
        st.download_button(
            "JSON de revisiones",
            json.dumps(reviews, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="revisiones_lonas.json",
            mime="application/json",
            use_container_width=True,
        )
    with c3:
        kmz_bytes = build_kmz_bytes(export_df)
        st.download_button(
            "KMZ actualizado",
            kmz_bytes,
            file_name="lonas_supervision_actualizado.kmz",
            mime="application/vnd.google-earth.kmz",
            use_container_width=True,
        )

    st.info("En Streamlit Cloud el archivo JSON local puede ser temporal. Para uso formal multiusuario conviene conectar Supabase, Firebase o una base SQLite persistente en servidor propio.")

with tab_help:
    st.subheader("Guía rápida de uso")
    st.markdown(
        """
        **Flujo recomendado:**

        1. Filtra por distrito local, sección, estatus o colonia.
        2. Cambia el mapa base desde el panel izquierdo si necesitas vista de calles, satélite, terreno o modo oscuro.
        3. Revisa el punto en el mapa y abre la evidencia fotográfica.
        4. Entra a **Supervisión**, selecciona la fila y marca el estatus.
        5. Si la ubicación está mal, captura latitud y longitud corregidas.
        6. Exporta CSV/JSON/KMZ actualizado desde la pestaña **Exportar**.

        **Estatus sugeridos:**

        - **Pendiente:** aún no revisado.
        - **Verificado:** ubicación y evidencia correctas.
        - **Corregir ubicación:** se detectó que el punto requiere ajuste.
        - **Retirar/Reponer lona:** hay incidencia física con la lona.
        - **No localizada:** no se encontró en campo.

        **Compartir avances:** esta versión ya no incluye botón directo de WhatsApp. Lo recomendado es subirla a Streamlit Cloud y compartir el enlace privado o exportar el KMZ/CSV.
        """
    )
