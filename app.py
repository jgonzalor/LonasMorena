import base64
import hashlib
import html
import io
import json
import re
import sqlite3
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

import folium
import pandas as pd
import requests
import streamlit as st
from folium.plugins import MarkerCluster, Fullscreen, MeasureControl
from streamlit_folium import st_folium

try:
    import openpyxl
except Exception:
    openpyxl = None


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
IMG_DIR = DATA_DIR / "evidencias"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "lonas_supervision.db"
MAPEABLES_CSV = DATA_DIR / "lonas_mapeables.csv"
PENDIENTES_CSV = DATA_DIR / "lonas_pendientes_sin_coordenada.csv"

for folder in [DATA_DIR, IMG_DIR, UPLOADS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)


# Paleta Morena con contraste alto para escritorio y celular.
MORENA_GUINDA = "#7A0026"
MORENA_GUINDA_DARK = "#4A0018"
MORENA_GUINDA_SOFT = "#A51C48"
MORENA_BEIGE = "#F1E3D3"
MORENA_BEIGE_2 = "#FFF8EF"
MORENA_DORADO = "#C69A2D"
MORENA_GREEN = "#007A3D"
TEXT_DARK = "#1F171A"

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
    "Calles claro": {"tiles": "CartoDB positron", "attr": "CartoDB / OpenStreetMap"},
    "Calles OSM": {"tiles": "OpenStreetMap", "attr": "OpenStreetMap"},
    "Satélite": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Esri World Imagery",
    },
    "Terreno / relieve": {
        "tiles": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        "attr": "Map data: OpenStreetMap contributors, SRTM | Map style: OpenTopoMap",
    },
    "Oscuro": {"tiles": "CartoDB dark_matter", "attr": "CartoDB / OpenStreetMap"},
}

BASE_COLUMNS = [
    "id", "archivo_origen", "fila_excel", "fecha", "responsable", "municipio", "distrito_local",
    "seccion", "colonia", "direccion", "ciudad_comunidad", "nombre_enlace", "celular",
    "link_maps", "url_maps_expandida", "lonas_colocadas", "fotografia", "observaciones",
    "latitud", "longitud", "latitud_corregida", "longitud_corregida", "fuente_coordenada",
    "estado_coordenada", "estatus", "supervisor", "nota_supervision", "fecha_revision",
    "fecha_carga", "registro_hash",
]


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

    header[data-testid="stHeader"] {{
        background: transparent;
        height: 0rem;
        visibility: hidden;
    }}

    #MainMenu, footer {{
        visibility: hidden;
    }}

    .stApp {{
        background: linear-gradient(180deg, #fffaf2 0%, var(--beige2) 45%, #ffffff 100%);
        color: var(--texto);
    }}

    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #ffffff 0%, var(--beige) 100%);
        border-right: 2px solid rgba(122, 0, 38, .28);
    }}

    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] label {{
        color: var(--guinda-dark) !important;
        font-weight: 800 !important;
    }}

    .block-container {{
        padding-top: 1rem;
        padding-bottom: 4rem;
    }}

    .hero-card {{
        border-radius: 22px;
        padding: 24px 28px;
        margin-bottom: 18px;
        color: white;
        background: linear-gradient(135deg, var(--guinda-dark) 0%, var(--guinda) 55%, var(--guinda-soft) 100%);
        box-shadow: 0 18px 42px rgba(74, 0, 24, .32);
        border: 1px solid rgba(255,255,255,.35);
    }}

    .hero-title {{
        font-size: 2.08rem;
        line-height: 1.08;
        font-weight: 900;
        letter-spacing: -.02em;
        margin: 0 0 8px 0;
        color: #ffffff;
    }}

    .hero-subtitle {{
        font-size: 1rem;
        margin: 0;
        opacity: .96;
        color: #fff8ef;
        font-weight: 500;
    }}

    .kpi-card {{
        background: #ffffff;
        border: 2px solid rgba(122, 0, 38, .18);
        border-radius: 18px;
        padding: 16px 18px;
        box-shadow: 0 10px 25px rgba(74,0,24,.10);
        min-height: 98px;
    }}

    .kpi-label {{
        color: #4A0018;
        font-size: .78rem;
        text-transform: uppercase;
        letter-spacing: .09em;
        font-weight: 900;
        margin-bottom: 8px;
    }}

    .kpi-number {{
        color: var(--guinda);
        font-size: 2.15rem;
        font-weight: 900;
        line-height: 1;
    }}

    .section-card {{
        background: #ffffff;
        border: 2px solid rgba(122, 0, 38, .16);
        border-radius: 18px;
        padding: 16px 18px;
        box-shadow: 0 10px 24px rgba(74,0,24,.09);
        margin-bottom: 12px;
    }}

    .legend-dot {{
        display: inline-block;
        width: 13px;
        height: 13px;
        border-radius: 50%;
        margin-right: 8px;
        vertical-align: middle;
        border: 1px solid rgba(0,0,0,.20);
    }}

    .note-box {{
        background: #fff3df;
        border: 2px solid rgba(198,154,45,.45);
        border-left: 7px solid var(--dorado);
        border-radius: 14px;
        padding: 13px 15px;
        color: #3b2418;
        margin: 10px 0;
        font-weight: 600;
    }}

    .stButton > button,
    .stDownloadButton > button,
    div[data-testid="stFormSubmitButton"] button {{
        border-radius: 12px !important;
        border: 2px solid rgba(122, 0, 38, .30) !important;
        font-weight: 800 !important;
        color: var(--guinda-dark) !important;
        background: #ffffff !important;
    }}

    .stButton > button:hover,
    .stDownloadButton > button:hover {{
        border-color: var(--guinda) !important;
        color: var(--guinda) !important;
    }}

    div[data-testid="stFormSubmitButton"] button,
    .stDownloadButton > button[kind="primary"] {{
        background: var(--guinda) !important;
        color: white !important;
        border-color: var(--guinda-dark) !important;
    }}

    div[data-baseweb="tab-list"] {{
        gap: 8px;
        border-bottom: 2px solid rgba(122,0,38,.28);
        overflow-x: auto;
        white-space: nowrap;
        padding-bottom: 0px;
    }}

    button[data-baseweb="tab"] {{
        background: #ead8cd !important;
        color: #4A0018 !important;
        border-radius: 999px 999px 0 0 !important;
        padding: 10px 18px !important;
        border: 1px solid rgba(122,0,38,.18) !important;
        font-weight: 800 !important;
        opacity: 1 !important;
    }}

    button[data-baseweb="tab"] p {{
        color: #4A0018 !important;
        font-weight: 800 !important;
    }}

    button[data-baseweb="tab"][aria-selected="true"] {{
        background: var(--guinda) !important;
        color: #ffffff !important;
        border-bottom: 3px solid var(--dorado) !important;
        font-weight: 900 !important;
        box-shadow: 0 8px 18px rgba(74,0,24,.22);
    }}

    button[data-baseweb="tab"][aria-selected="true"] p {{
        color: #ffffff !important;
        font-weight: 900 !important;
    }}

    h1, h2, h3, h4 {{
        color: var(--guinda-dark);
        font-weight: 900;
    }}

    p, span, label, div {{
        color: inherit;
    }}

    iframe {{
        border-radius: 16px;
        border: 2px solid rgba(122,0,38,.24) !important;
        box-shadow: 0 12px 26px rgba(74,0,24,.12);
    }}

    @media screen and (max-width: 768px) {{
        .block-container {{
            padding-left: .85rem;
            padding-right: .85rem;
            padding-top: .6rem;
            padding-bottom: 6rem;
        }}
        .hero-card {{ padding: 18px 18px; border-radius: 18px; }}
        .hero-title {{ font-size: 1.55rem; }}
        .hero-subtitle {{ font-size: .9rem; }}
        .kpi-card {{ min-height: 86px; padding: 14px 15px; border: 2px solid rgba(122,0,38,.24); }}
        .kpi-number {{ font-size: 2rem; }}
        .kpi-label {{ font-size: .75rem; color: var(--guinda-dark); }}
        div[data-baseweb="tab-list"] {{
            background: #fff8ef;
            border-radius: 12px 12px 0 0;
            padding-top: 6px;
            padding-left: 4px;
            padding-right: 4px;
        }}
        button[data-baseweb="tab"] {{
            background: #e2c8bc !important;
            color: var(--guinda-dark) !important;
            padding: 10px 16px !important;
            min-width: max-content !important;
        }}
        button[data-baseweb="tab"][aria-selected="true"] {{ background: var(--guinda) !important; color: #ffffff !important; }}
        iframe {{ min-height: 560px !important; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# Base de datos SQLite
# -----------------------------
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lonas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archivo_origen TEXT,
                fila_excel INTEGER,
                fecha TEXT,
                responsable TEXT,
                municipio TEXT,
                distrito_local TEXT,
                seccion TEXT,
                colonia TEXT,
                direccion TEXT,
                ciudad_comunidad TEXT,
                nombre_enlace TEXT,
                celular TEXT,
                link_maps TEXT,
                url_maps_expandida TEXT,
                lonas_colocadas REAL DEFAULT 1,
                fotografia TEXT,
                observaciones TEXT,
                latitud REAL,
                longitud REAL,
                latitud_corregida REAL,
                longitud_corregida REAL,
                fuente_coordenada TEXT DEFAULT 'pendiente',
                estado_coordenada TEXT DEFAULT 'pendiente',
                estatus TEXT DEFAULT 'Pendiente',
                supervisor TEXT,
                nota_supervision TEXT,
                fecha_revision TEXT,
                fecha_carga TEXT,
                registro_hash TEXT UNIQUE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archivo TEXT,
                registros_leidos INTEGER,
                registros_insertados INTEGER,
                duplicados INTEGER,
                registros_mapeables INTEGER,
                registros_pendientes INTEGER,
                resolver_links INTEGER,
                fecha_carga TEXT
            )
            """
        )
        conn.commit()


def db_count_lonas() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM lonas").fetchone()
        return int(row["n"] or 0)


def clean_value(value: object) -> str:
    """
    Limpia valores escalares de Excel/SQLite.
    También evita el error: The truth value of a Series is ambiguous,
    que aparece cuando un Excel trae encabezados duplicados como CELULAR/CELULAR.
    """
    if value is None:
        return ""

    # Si por columnas duplicadas llega una Serie/lista, toma el primer valor útil.
    if isinstance(value, pd.Series):
        for item in value.tolist():
            cleaned = clean_value(item)
            if cleaned:
                return cleaned
        return ""

    if isinstance(value, (list, tuple, set)):
        for item in value:
            cleaned = clean_value(item)
            if cleaned:
                return cleaned
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    text = str(value).strip()
    if text.lower() in ["nan", "none", "nat"]:
        return ""
    return text


def to_float(value: object) -> Optional[float]:
    text = clean_value(value)
    if not text:
        return None
    text = text.replace(",", ".")
    try:
        return float(text)
    except Exception:
        return None


def build_hash(row: Dict[str, object]) -> str:
    parts = [
        clean_value(row.get("link_maps")),
        clean_value(row.get("direccion")),
        clean_value(row.get("colonia")),
        clean_value(row.get("responsable")),
        clean_value(row.get("distrito_local")),
        clean_value(row.get("seccion")),
        clean_value(row.get("nombre_enlace")),
        clean_value(row.get("celular")),
        clean_value(row.get("archivo_origen")),
        clean_value(row.get("fila_excel")),
    ]
    raw = "||".join(parts).lower()
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def insert_lona(row: Dict[str, object]) -> Tuple[bool, Optional[int]]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {col: row.get(col, "") for col in BASE_COLUMNS if col not in ["id"]}
    data["fecha_carga"] = data.get("fecha_carga") or now
    data["estatus"] = data.get("estatus") or "Pendiente"
    data["estado_coordenada"] = data.get("estado_coordenada") or "pendiente"
    data["fuente_coordenada"] = data.get("fuente_coordenada") or "pendiente"
    data["registro_hash"] = data.get("registro_hash") or build_hash(data)

    numeric_cols = ["fila_excel", "lonas_colocadas", "latitud", "longitud", "latitud_corregida", "longitud_corregida"]
    for col in numeric_cols:
        if col in ["fila_excel"]:
            try:
                data[col] = int(float(data[col])) if clean_value(data[col]) else None
            except Exception:
                data[col] = None
        else:
            data[col] = to_float(data[col])

    cols = list(data.keys())
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT OR IGNORE INTO lonas ({','.join(cols)}) VALUES ({placeholders})"

    with get_conn() as conn:
        cur = conn.execute(sql, [data[c] for c in cols])
        conn.commit()
        if cur.rowcount == 1:
            return True, int(cur.lastrowid)

        existing = conn.execute("SELECT id FROM lonas WHERE registro_hash = ?", (data["registro_hash"],)).fetchone()
        return False, int(existing["id"]) if existing else None


def update_upload_log(
    archivo: str,
    registros_leidos: int,
    registros_insertados: int,
    duplicados: int,
    registros_mapeables: int,
    registros_pendientes: int,
    resolver_links: bool,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO uploads
            (archivo, registros_leidos, registros_insertados, duplicados, registros_mapeables,
             registros_pendientes, resolver_links, fecha_carga)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                archivo,
                registros_leidos,
                registros_insertados,
                duplicados,
                registros_mapeables,
                registros_pendientes,
                1 if resolver_links else 0,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()


@st.cache_data(show_spinner=False)
def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def migrate_initial_csvs_if_needed() -> None:
    if db_count_lonas() > 0:
        return

    mapeables = load_csv(MAPEABLES_CSV)
    pendientes = load_csv(PENDIENTES_CSV)

    inserted = 0
    duplicates = 0

    if not mapeables.empty:
        for _, r in mapeables.iterrows():
            lat = to_float(r.get("latitud"))
            lon = to_float(r.get("longitud"))
            row = {
                "archivo_origen": "carga_inicial_csv_mapeables",
                "fila_excel": r.get("fila_excel"),
                "fecha": r.get("fecha", ""),
                "responsable": r.get("responsable", ""),
                "municipio": r.get("municipio", ""),
                "distrito_local": r.get("distrito_local", r.get("distrito", "")),
                "seccion": r.get("seccion", ""),
                "colonia": r.get("colonia", ""),
                "direccion": r.get("direccion", ""),
                "ciudad_comunidad": r.get("ciudad_comunidad", ""),
                "nombre_enlace": r.get("nombre_enlace", ""),
                "celular": r.get("celular", ""),
                "link_maps": r.get("link_maps", r.get("link_google_maps", "")),
                "lonas_colocadas": r.get("lonas_colocadas", 1),
                "fotografia": r.get("fotografia", r.get("evidencia", "")),
                "observaciones": r.get("observaciones", ""),
                "latitud": lat,
                "longitud": lon,
                "fuente_coordenada": "csv_inicial",
                "estado_coordenada": "exacta" if lat is not None and lon is not None else "pendiente",
                "estatus": "Pendiente",
            }
            ok, _ = insert_lona(row)
            inserted += int(ok)
            duplicates += int(not ok)

    if not pendientes.empty:
        for _, r in pendientes.iterrows():
            row = {
                "archivo_origen": "carga_inicial_csv_pendientes",
                "fila_excel": r.get("fila_excel"),
                "fecha": r.get("fecha", ""),
                "responsable": r.get("responsable", ""),
                "municipio": r.get("municipio", ""),
                "distrito_local": r.get("distrito_local", r.get("distrito", "")),
                "seccion": r.get("seccion", ""),
                "colonia": r.get("colonia", ""),
                "direccion": r.get("direccion", ""),
                "ciudad_comunidad": r.get("ciudad_comunidad", ""),
                "nombre_enlace": r.get("nombre_enlace", ""),
                "celular": r.get("celular", ""),
                "link_maps": r.get("link_maps", r.get("link_google_maps", "")),
                "lonas_colocadas": r.get("lonas_colocadas", 1),
                "fotografia": r.get("fotografia", r.get("evidencia", "")),
                "observaciones": r.get("observaciones", ""),
                "fuente_coordenada": "pendiente_csv_inicial",
                "estado_coordenada": "pendiente",
                "estatus": "Pendiente",
            }
            ok, _ = insert_lona(row)
            inserted += int(ok)
            duplicates += int(not ok)

    if inserted or duplicates:
        update_upload_log(
            archivo="migracion_inicial_csv",
            registros_leidos=len(mapeables) + len(pendientes),
            registros_insertados=inserted,
            duplicados=duplicates,
            registros_mapeables=int(db_count_mapeables()),
            registros_pendientes=int(db_count_pendientes()),
            resolver_links=False,
        )


def db_count_mapeables() -> int:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM lonas
            WHERE COALESCE(latitud_corregida, latitud) IS NOT NULL
              AND COALESCE(longitud_corregida, longitud) IS NOT NULL
            """
        ).fetchone()
        return int(row["n"] or 0)


def db_count_pendientes() -> int:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM lonas
            WHERE COALESCE(latitud_corregida, latitud) IS NULL
               OR COALESCE(longitud_corregida, longitud) IS NULL
            """
        ).fetchone()
        return int(row["n"] or 0)


def load_lonas_df() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM lonas ORDER BY id ASC", conn)

    if df.empty:
        return df

    for col in ["latitud", "longitud", "latitud_corregida", "longitud_corregida", "lonas_colocadas"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["latitud_mapa"] = df["latitud_corregida"].combine_first(df["latitud"])
    df["longitud_mapa"] = df["longitud_corregida"].combine_first(df["longitud"])
    df["estatus"] = df["estatus"].fillna("Pendiente").replace("", "Pendiente")
    df["distrito_local"] = df["distrito_local"].fillna("").astype(str)
    df["seccion"] = df["seccion"].fillna("").astype(str)
    return df


def load_uploads_df() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query("SELECT * FROM uploads ORDER BY id DESC", conn)


# -----------------------------
# Coordenadas y Google Maps
# -----------------------------
def extract_coords_from_google_url(url: str) -> Tuple[Optional[float], Optional[float]]:
    if not url:
        return None, None

    decoded = unquote(str(url))
    decoded = decoded.replace("%2C", ",")

    patterns = [
        r"@(-?\d+\.\d+),(-?\d+\.\d+)",
        r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
        r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)",
        r"[?&]ll=(-?\d+\.\d+),(-?\d+\.\d+)",
        r"[?&]center=(-?\d+\.\d+),(-?\d+\.\d+)",
        r"query=(-?\d+\.\d+),(-?\d+\.\d+)",
        r"destination=(-?\d+\.\d+),(-?\d+\.\d+)",
        r"daddr=(-?\d+\.\d+),(-?\d+\.\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, decoded)
        if match:
            lat = float(match.group(1))
            lon = float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon

    return None, None


def expand_google_maps_url(url: str, timeout: int = 12) -> str:
    original_url = clean_value(url)
    if not original_url:
        return ""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(
            original_url,
            headers=headers,
            allow_redirects=True,
            timeout=timeout,
        )
        final_url = response.url or original_url

        # Algunos links de Google esconden la URL larga dentro del HTML.
        text = response.text[:200000] if response.text else ""
        candidates = re.findall(r"https://www\.google\.com/maps[^'\"\\]+", text)
        if candidates:
            final_url = unquote(candidates[0])

        return final_url
    except Exception:
        return original_url


def resolve_maps_link(url: str, expand_short: bool = False) -> Dict[str, object]:
    original_url = clean_value(url)
    if not original_url:
        return {
            "latitud": None,
            "longitud": None,
            "url_maps_expandida": "",
            "fuente_coordenada": "sin_link",
            "estado_coordenada": "pendiente",
        }

    lat, lon = extract_coords_from_google_url(original_url)
    if lat is not None and lon is not None:
        return {
            "latitud": lat,
            "longitud": lon,
            "url_maps_expandida": original_url,
            "fuente_coordenada": "link_directo",
            "estado_coordenada": "exacta",
        }

    expanded = original_url
    if expand_short:
        expanded = expand_google_maps_url(original_url)
        lat, lon = extract_coords_from_google_url(expanded)
        if lat is not None and lon is not None:
            return {
                "latitud": lat,
                "longitud": lon,
                "url_maps_expandida": expanded,
                "fuente_coordenada": "link_corto_resuelto",
                "estado_coordenada": "exacta",
            }

    return {
        "latitud": None,
        "longitud": None,
        "url_maps_expandida": expanded,
        "fuente_coordenada": "link_no_resuelto" if original_url else "sin_link",
        "estado_coordenada": "pendiente",
    }


def resolve_pending_links(max_items: int = 50, sleep_sec: float = 0.15) -> Dict[str, int]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, link_maps FROM lonas
            WHERE (latitud IS NULL OR longitud IS NULL)
              AND COALESCE(link_maps, '') <> ''
            ORDER BY id ASC
            LIMIT ?
            """,
            (int(max_items),),
        ).fetchall()

    stats = {"procesados": 0, "resueltos": 0, "pendientes": 0}
    progress = st.progress(0) if rows else None

    for i, row in enumerate(rows, start=1):
        result = resolve_maps_link(row["link_maps"], expand_short=True)
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE lonas
                SET latitud = ?, longitud = ?, url_maps_expandida = ?,
                    fuente_coordenada = ?, estado_coordenada = ?
                WHERE id = ?
                """,
                (
                    result["latitud"],
                    result["longitud"],
                    result["url_maps_expandida"],
                    result["fuente_coordenada"],
                    result["estado_coordenada"],
                    row["id"],
                ),
            )
            conn.commit()

        stats["procesados"] += 1
        if result["latitud"] is not None and result["longitud"] is not None:
            stats["resueltos"] += 1
        else:
            stats["pendientes"] += 1

        if progress is not None:
            progress.progress(i / len(rows))
        time.sleep(sleep_sec)

    return stats


# -----------------------------
# Lectura de Excel flexible
# -----------------------------
def normalize_col_name(name: object) -> str:
    text = clean_value(name).lower()
    text = text.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    text = text.replace("ñ", "n")
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text


def canonical_col(name: object) -> Optional[str]:
    n = normalize_col_name(name)
    if not n:
        return None

    if n in ["fecha", "fecha de captura", "fecha captura"]:
        return "fecha"
    if "responsable" in n:
        return "responsable"
    if "municipio" in n:
        return "municipio"
    if "distrito" in n:
        return "distrito_local"
    if n in ["seccion", "seccion electoral", "secciones"] or "seccion" in n:
        return "seccion"
    if "colonia" in n:
        return "colonia"
    if "direccion" in n or "ubicacion" in n or "domicilio" in n:
        return "direccion"
    if ("google" in n and "map" in n) or n in ["link", "link maps", "maps", "google maps"]:
        return "link_maps"
    if "lona" in n and ("coloc" in n or "cantidad" in n or "total" in n):
        return "lonas_colocadas"
    if n == "lonas" or n == "lona":
        return "lonas_colocadas"
    if "foto" in n or "fotografia" in n or "evidencia" in n:
        return "fotografia"
    if "observ" in n:
        return "observaciones"
    if "ciudad" in n or "comunidad" in n:
        return "ciudad_comunidad"
    if "nombre" in n and ("enlace" in n or "vecino" in n or "contacto" in n):
        return "nombre_enlace"
    if n in ["enlace", "nombre enlace", "nombre del enlace"]:
        return "nombre_enlace"
    if "cel" in n or "telefono" in n or "whatsapp" in n:
        return "celular"
    if n in ["lat", "latitude", "latitud"]:
        return "latitud"
    if n in ["lon", "lng", "longitude", "longitud"]:
        return "longitud"
    return None


def find_header_row(raw_df: pd.DataFrame) -> int:
    best_idx = 0
    best_score = -1
    max_scan = min(25, len(raw_df))

    required_weights = {
        "fecha": 1,
        "responsable": 1,
        "municipio": 1,
        "distrito_local": 2,
        "seccion": 2,
        "colonia": 1,
        "direccion": 2,
        "link_maps": 3,
        "lonas_colocadas": 1,
        "observaciones": 1,
    }

    for idx in range(max_scan):
        row = raw_df.iloc[idx].tolist()
        found = set()
        for value in row:
            canon = canonical_col(value)
            if canon:
                found.add(canon)
        score = sum(required_weights.get(c, 1) for c in found)
        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx




def build_unique_import_headers(headers: List[object]) -> List[str]:
    """
    Convierte encabezados del Excel a nombres internos únicos.
    Soluciona archivos con columnas duplicadas, por ejemplo CELULAR en dos secciones.
    Regla práctica: si hay dos CELULAR, conserva el último como teléfono del enlace/contacto.
    """
    canon_by_index = [canonical_col(h) for h in headers]
    keep_index_by_canon: Dict[str, int] = {}

    for idx, canon in enumerate(canon_by_index):
        if not canon:
            continue

        if canon not in keep_index_by_canon:
            keep_index_by_canon[canon] = idx
        else:
            # En este formato existe CELULAR del responsable y CELULAR del enlace.
            # Para supervisión conviene conservar el último, que suele estar junto a NOMBRE DEL ENLACE.
            if canon == "celular":
                keep_index_by_canon[canon] = idx
            # Para las demás columnas repetidas, conserva la primera aparición.

    out: List[str] = []
    used_extra: Dict[str, int] = {}

    for idx, raw_header in enumerate(headers):
        canon = canon_by_index[idx]

        if canon and keep_index_by_canon.get(canon) == idx:
            out.append(canon)
            continue

        base = normalize_col_name(raw_header) or f"col_{idx + 1}"
        base = re.sub(r"[^a-z0-9_]+", "_", base).strip("_") or f"col_{idx + 1}"
        base = f"extra_{base[:28]}"
        used_extra[base] = used_extra.get(base, 0) + 1
        suffix = used_extra[base]
        out.append(base if suffix == 1 else f"{base}_{suffix}")

    # Garantía final: no permitir columnas duplicadas.
    final: List[str] = []
    counts: Dict[str, int] = {}
    for name in out:
        counts[name] = counts.get(name, 0) + 1
        final.append(name if counts[name] == 1 else f"{name}_{counts[name]}")

    return final

def read_excel_records(file_bytes: bytes, filename: str, resolve_links: bool = False) -> Tuple[pd.DataFrame, Dict[int, int]]:
    xls = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
    # Toma la primera hoja con más contenido.
    sheet_name = xls.sheet_names[0]
    best_rows = -1
    for s in xls.sheet_names:
        preview = pd.read_excel(io.BytesIO(file_bytes), sheet_name=s, header=None, nrows=40, engine="openpyxl")
        non_empty = int(preview.dropna(how="all").shape[0])
        if non_empty > best_rows:
            best_rows = non_empty
            sheet_name = s

    raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=None, engine="openpyxl")
    header_idx = find_header_row(raw)
    headers = raw.iloc[header_idx].tolist()
    data = raw.iloc[header_idx + 1 :].copy()
    data.columns = build_unique_import_headers(headers)
    data = data.dropna(how="all")

    # Defensa adicional contra encabezados duplicados o celdas combinadas.
    data = data.loc[:, ~pd.Index(data.columns).duplicated()].copy()

    for col in BASE_COLUMNS:
        if col not in data.columns and col not in ["id", "registro_hash", "fecha_carga", "estatus", "estado_coordenada", "fuente_coordenada"]:
            data[col] = ""

    keep_cols = [
        "fecha", "responsable", "municipio", "distrito_local", "seccion", "colonia", "direccion",
        "ciudad_comunidad", "nombre_enlace", "celular", "link_maps", "lonas_colocadas",
        "fotografia", "observaciones", "latitud", "longitud",
    ]
    data = data[[c for c in keep_cols if c in data.columns]].copy()

    # Limpieza básica y fila original de Excel.
    data["archivo_origen"] = filename
    data["fila_excel"] = [int(i + header_idx + 2) for i in range(len(data))]

    # Filtra renglones sin contenido operativo.
    meaningful_cols = ["link_maps", "direccion", "colonia", "seccion", "distrito_local", "responsable", "observaciones"]
    mask = pd.Series(False, index=data.index)
    for col in meaningful_cols:
        if col in data.columns:
            mask = mask | data[col].apply(lambda x: clean_value(x) != "")
    data = data[mask].copy()

    rows_out = []
    excel_row_to_temp_index: Dict[int, int] = {}

    progress = st.progress(0) if resolve_links and len(data) else None

    for pos, (_, r) in enumerate(data.iterrows(), start=1):
        row = {col: clean_value(r.get(col, "")) for col in data.columns}
        excel_row = int(row.get("fila_excel") or 0)
        link = row.get("link_maps", "")
        lat_direct = to_float(row.get("latitud"))
        lon_direct = to_float(row.get("longitud"))

        if lat_direct is not None and lon_direct is not None:
            coord = {
                "latitud": lat_direct,
                "longitud": lon_direct,
                "url_maps_expandida": link,
                "fuente_coordenada": "excel_lat_lon",
                "estado_coordenada": "exacta",
            }
        else:
            coord = resolve_maps_link(link, expand_short=resolve_links)

        row.update(coord)
        row["estatus"] = "Pendiente"
        row["registro_hash"] = build_hash(row)
        rows_out.append(row)
        excel_row_to_temp_index[excel_row] = len(rows_out) - 1

        if progress is not None:
            progress.progress(pos / len(data))

    return pd.DataFrame(rows_out), excel_row_to_temp_index


def save_uploaded_excel(file_bytes: bytes, filename: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_. -]+", "_", filename).strip() or "upload.xlsx"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = UPLOADS_DIR / f"{ts}_{safe_name}"
    out.write_bytes(file_bytes)
    return out


def extract_images_from_excel(file_bytes: bytes, filename: str, excel_row_to_db_id: Dict[int, int]) -> int:
    if openpyxl is None:
        return 0

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception:
        return 0

    total_saved = 0

    for ws in wb.worksheets:
        images = getattr(ws, "_images", [])
        counters: Dict[int, int] = {}
        for img in images:
            try:
                anchor = getattr(img, "anchor", None)
                if not anchor or not hasattr(anchor, "_from"):
                    continue
                excel_row = int(anchor._from.row) + 1
                db_id = excel_row_to_db_id.get(excel_row)
                if not db_id:
                    continue

                counters[db_id] = counters.get(db_id, 0) + 1
                img_bytes = img._data()
                ext = (getattr(img, "format", None) or "png").lower().replace("jpeg", "jpg")
                if ext not in ["png", "jpg", "jpeg", "webp"]:
                    ext = "png"
                out = IMG_DIR / f"registro_{db_id}_evidencia_{counters[db_id]}.{ext}"
                out.write_bytes(img_bytes)
                total_saved += 1
            except Exception:
                continue

    return total_saved


def import_excel_to_db(file_bytes: bytes, filename: str, resolve_links: bool = False) -> Dict[str, int]:
    save_uploaded_excel(file_bytes, filename)
    parsed, _ = read_excel_records(file_bytes, filename, resolve_links=resolve_links)

    stats = {
        "registros_leidos": int(len(parsed)),
        "insertados": 0,
        "duplicados": 0,
        "mapeables": 0,
        "pendientes": 0,
        "imagenes_extraidas": 0,
    }

    excel_row_to_db_id: Dict[int, int] = {}

    for _, r in parsed.iterrows():
        row = r.to_dict()
        ok, db_id = insert_lona(row)
        if ok:
            stats["insertados"] += 1
        else:
            stats["duplicados"] += 1
        if db_id:
            try:
                excel_row_to_db_id[int(row.get("fila_excel"))] = int(db_id)
            except Exception:
                pass

        if to_float(row.get("latitud")) is not None and to_float(row.get("longitud")) is not None:
            stats["mapeables"] += 1
        else:
            stats["pendientes"] += 1

    stats["imagenes_extraidas"] = extract_images_from_excel(file_bytes, filename, excel_row_to_db_id)

    update_upload_log(
        archivo=filename,
        registros_leidos=stats["registros_leidos"],
        registros_insertados=stats["insertados"],
        duplicados=stats["duplicados"],
        registros_mapeables=stats["mapeables"],
        registros_pendientes=stats["pendientes"],
        resolver_links=resolve_links,
    )

    return stats


# -----------------------------
# Mapas, popups y exportaciones
# -----------------------------
def image_files_for_record(record_id: int, fila_excel: Optional[int] = None) -> List[Path]:
    files = sorted([p for p in IMG_DIR.glob(f"registro_{int(record_id)}_evidencia_*.*") if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]])
    if files:
        return files

    # Compatibilidad con evidencias del primer paquete, nombradas por fila Excel.
    if fila_excel is not None and not pd.isna(fila_excel):
        return sorted([p for p in IMG_DIR.glob(f"fila_{int(fila_excel)}_evidencia_*.*") if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]])

    return []


def img_to_base64(path: Path) -> Optional[str]:
    try:
        data = path.read_bytes()
        ext = path.suffix.lower().lstrip(".") or "jpg"
        if ext == "jpg":
            ext = "jpeg"
        return f"data:image/{ext};base64," + base64.b64encode(data).decode("ascii")
    except Exception:
        return None


def make_popup_html(row: pd.Series, include_img: bool = True) -> str:
    record_id = int(row["id"])
    fila_excel = row.get("fila_excel", "")
    img_html = ""

    if include_img:
        imgs = image_files_for_record(record_id, fila_excel)
        if imgs:
            src = img_to_base64(imgs[0])
            if src:
                img_html = f"""
                <div style='margin-top:10px'>
                    <img src='{src}' style='max-width:260px; max-height:190px; border-radius:10px; border:1px solid #e5d8cf;'>
                </div>
                """

    maps_link = html.escape(str(row.get("link_maps", "") or ""))
    link_html = f"<a href='{maps_link}' target='_blank' style='color:{MORENA_GUINDA};font-weight:bold'>Abrir en Google Maps</a>" if maps_link else ""
    status = html.escape(str(row.get("estatus", "Pendiente") or "Pendiente"))
    status_color = STATUS_COLORS.get(str(row.get("estatus", "Pendiente") or "Pendiente"), MORENA_GUINDA)
    fuente = html.escape(str(row.get("fuente_coordenada", "") or ""))

    return f"""
    <div style='font-family:Arial; width:295px; color:#272124'>
      <h4 style='margin:0 0 8px 0; color:{MORENA_GUINDA_DARK}'>Lona | ID {record_id}</h4>
      <div style='display:inline-block;background:{status_color};color:white;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:bold;margin-bottom:8px'>{status}</div><br>
      <b>Archivo:</b> {html.escape(str(row.get('archivo_origen','')))}<br>
      <b>Fila Excel:</b> {html.escape(str(fila_excel))}<br>
      <b>Distrito:</b> {html.escape(str(row.get('distrito_local','')))} &nbsp; <b>Sección:</b> {html.escape(str(row.get('seccion','')))}<br>
      <b>Colonia:</b> {html.escape(str(row.get('colonia','')))}<br>
      <b>Dirección:</b> {html.escape(str(row.get('direccion','')))}<br>
      <b>Fuente coordenada:</b> {fuente}<br>
      <b>Observaciones:</b> {html.escape(str(row.get('observaciones','')))}<br>
      <b>Supervisor:</b> {html.escape(str(row.get('supervisor','')))}<br>
      <b>Nota:</b> {html.escape(str(row.get('nota_supervision','')))}<br>
      {link_html}
      {img_html}
    </div>
    """


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


def make_map(df: pd.DataFrame, selected_id: Optional[int] = None, selected_tile: str = "Calles claro", cluster_points: bool = False) -> folium.Map:
    valid = df.dropna(subset=["latitud_mapa", "longitud_mapa"]).copy()

    if valid.empty:
        m = folium.Map(location=[25.79, -109.0], zoom_start=8, tiles=None, control_scale=True)
        add_tile_layers(m, selected_tile)
        folium.LayerControl(collapsed=False).add_to(m)
        return m

    center = [valid["latitud_mapa"].mean(), valid["longitud_mapa"].mean()]
    m = folium.Map(location=center, zoom_start=13, tiles=None, control_scale=True)
    add_tile_layers(m, selected_tile)

    target_layer = MarkerCluster(name="Lonas agrupadas").add_to(m) if cluster_points else folium.FeatureGroup(name="Lonas", show=True).add_to(m)

    for _, row in valid.iterrows():
        rid = int(row["id"])
        status = str(row.get("estatus", "Pendiente") or "Pendiente")
        color = STATUS_COLORS.get(status, MORENA_GUINDA)
        radius = 12 if selected_id == rid else 7

        folium.CircleMarker(
            location=[float(row["latitud_mapa"]), float(row["longitud_mapa"])],
            radius=radius,
            popup=folium.Popup(make_popup_html(row), max_width=380),
            tooltip=f"ID {rid} | D{row.get('distrito_local','')} S{row.get('seccion','')} | {status}",
            color="#FFFFFF" if selected_id == rid else color,
            weight=3 if selected_id == rid else 2,
            fill=True,
            fill_color=color,
            fill_opacity=0.90,
        ).add_to(target_layer)

    if selected_id:
        sel = valid[valid["id"].astype(int) == int(selected_id)]
        if not sel.empty:
            row = sel.iloc[0]
            folium.Marker(
                location=[float(row["latitud_mapa"]), float(row["longitud_mapa"])],
                popup=folium.Popup(make_popup_html(row), max_width=380),
                tooltip="Registro seleccionado",
                icon=folium.Icon(color="darkred", icon="star"),
            ).add_to(m)

    Fullscreen().add_to(m)
    MeasureControl(primary_length_unit="meters", secondary_length_unit="kilometers").add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m


def make_supervision_cluster_map(df: pd.DataFrame, selected_tile: str = "Satélite") -> folium.Map:
    valid = df.dropna(subset=["latitud_mapa", "longitud_mapa"]).copy()

    if valid.empty:
        m = folium.Map(location=[25.79, -109.0], zoom_start=8, tiles=None, control_scale=True)
        add_tile_layers(m, selected_tile)
        Fullscreen().add_to(m)
        folium.LayerControl(collapsed=True).add_to(m)
        return m

    center = [valid["latitud_mapa"].mean(), valid["longitud_mapa"].mean()]
    m = folium.Map(location=center, zoom_start=8, tiles=None, control_scale=True)
    add_tile_layers(m, selected_tile)

    icon_create_function = f"""
    function(cluster) {{
        var count = cluster.getChildCount();
        var size = count < 10 ? 42 : count < 50 ? 50 : 60;
        return new L.DivIcon({{
            html: '<div style="background:{MORENA_GUINDA}; color:white; width:' + size + 'px; height:' + size + 'px; line-height:' + size + 'px; border-radius:50%; text-align:center; font-weight:900; border:4px solid {MORENA_DORADO}; box-shadow:0 8px 20px rgba(74,0,24,.42); font-size:17px;">' + count + '</div>',
            className: 'marker-cluster-morena',
            iconSize: new L.Point(size, size)
        }});
    }}
    """

    cluster = MarkerCluster(
        name="Total de lonas por distribución geográfica",
        icon_create_function=icon_create_function,
        options={
            "spiderfyOnMaxZoom": True,
            "showCoverageOnHover": True,
            "zoomToBoundsOnClick": True,
            "disableClusteringAtZoom": 18,
            "maxClusterRadius": 80,
        },
    ).add_to(m)

    for _, row in valid.iterrows():
        rid = int(row["id"])
        status = str(row.get("estatus", "Pendiente") or "Pendiente")
        color = STATUS_COLORS.get(status, MORENA_GUINDA)
        tooltip = f"ID {rid} | Distrito {row.get('distrito_local','')} | Sección {row.get('seccion','')} | {status}"

        folium.CircleMarker(
            location=[float(row["latitud_mapa"]), float(row["longitud_mapa"])],
            radius=7,
            popup=folium.Popup(make_popup_html(row), max_width=380),
            tooltip=tooltip,
            color="#FFFFFF",
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.92,
        ).add_to(cluster)

    Fullscreen().add_to(m)
    MeasureControl(primary_length_unit="meters", secondary_length_unit="kilometers").add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m


def kml_escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def hex_to_kml_color(hex_color: str, alpha: str = "ff") -> str:
    color = hex_color.lstrip("#")
    if len(color) != 6:
        color = "7A0026"
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
                rid = int(row["id"])
                status = str(row.get("estatus", "Pendiente") or "Pendiente")
                style = "verificado" if status == "Verificado" else "pendiente" if status in ["Pendiente", ""] else "alerta"

                imgs = image_files_for_record(rid, row.get("fila_excel"))
                img_html = ""
                if imgs:
                    img_path = f"files/{imgs[0].name}"
                    img_html = f"<br/><br/><img src='{img_path}' width='420'/>"

                desc = f"""
                <![CDATA[
                <div style='font-family:Arial'>
                  <h3>Lona | ID {rid}</h3>
                  <b>Archivo origen:</b> {html.escape(str(row.get('archivo_origen','')))}<br/>
                  <b>Fila Excel:</b> {html.escape(str(row.get('fila_excel','')))}<br/>
                  <b>Estatus:</b> {html.escape(status)}<br/>
                  <b>Distrito Local:</b> {html.escape(str(row.get('distrito_local','')))}<br/>
                  <b>Sección:</b> {html.escape(str(row.get('seccion','')))}<br/>
                  <b>Municipio:</b> {html.escape(str(row.get('municipio','')))}<br/>
                  <b>Colonia:</b> {html.escape(str(row.get('colonia','')))}<br/>
                  <b>Dirección:</b> {html.escape(str(row.get('direccion','')))}<br/>
                  <b>Fuente coordenada:</b> {html.escape(str(row.get('fuente_coordenada','')))}<br/>
                  <b>Observaciones origen:</b> {html.escape(str(row.get('observaciones','')))}<br/>
                  <b>Supervisor:</b> {html.escape(str(row.get('supervisor','')))}<br/>
                  <b>Nota supervisión:</b> {html.escape(str(row.get('nota_supervision','')))}<br/>
                  <b>Fecha revisión:</b> {html.escape(str(row.get('fecha_revision','')))}<br/>
                  {img_html}
                </div>
                ]]>
                """

                name = f"ID {rid} | D{row.get('distrito_local','')} S{row.get('seccion','')} | {status}"
                kml_parts.extend(
                    [
                        "<Placemark>",
                        f"<name>{kml_escape(name)}</name>",
                        f"<styleUrl>#{style}</styleUrl>",
                        f"<description>{desc}</description>",
                        "<Point>",
                        f"<coordinates>{float(row['longitud_mapa'])},{float(row['latitud_mapa'])},0</coordinates>",
                        "</Point>",
                        "</Placemark>",
                    ]
                )
            kml_parts.append("</Folder>")
        kml_parts.append("</Folder>")

    kml_parts.extend(["</Document>", "</kml>"])
    kml_text = "\n".join(kml_parts)

    buff = io.BytesIO()
    with zipfile.ZipFile(buff, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml_text.encode("utf-8"))
        added = set()
        for _, row in valid.iterrows():
            for img in image_files_for_record(int(row["id"]), row.get("fila_excel")):
                arc = f"files/{img.name}"
                if arc not in added:
                    zf.write(img, arc)
                    added.add(arc)
    return buff.getvalue()


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def render_kpi(label: str, value: object, note: str = "") -> None:
    note_html = f"<div style='font-size:.77rem;color:#4A0018;margin-top:6px;font-weight:600'>{html.escape(str(note))}</div>" if note else ""
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
        rows.append(
            f"<div style='margin:7px 0;font-weight:700;color:#1F171A'><span class='legend-dot' style='background:{STATUS_COLORS[status]}'></span>{html.escape(status)}</div>"
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def filter_df(df: pd.DataFrame, distritos, secciones, estatuses, query: str, only_mapeables: bool = False) -> pd.DataFrame:
    out = df.copy()
    if only_mapeables:
        out = out.dropna(subset=["latitud_mapa", "longitud_mapa"])
    if distritos:
        out = out[out["distrito_local"].astype(str).isin([str(x) for x in distritos])]
    if secciones:
        out = out[out["seccion"].astype(str).isin([str(x) for x in secciones])]
    if estatuses:
        out = out[out["estatus"].isin(estatuses)]

    q = clean_value(query).lower()
    if q:
        cols = [
            c for c in [
                "archivo_origen", "colonia", "direccion", "observaciones", "responsable", "municipio",
                "seccion", "distrito_local", "nombre_enlace", "celular", "link_maps"
            ] if c in out.columns
        ]
        mask = pd.Series(False, index=out.index)
        for col in cols:
            mask = mask | out[col].astype(str).str.lower().str.contains(re.escape(q), na=False, regex=True)
        out = out[mask]
    return out


def update_review(record_id: int, estatus: str, supervisor: str, nota: str, lat_corr: str, lon_corr: str) -> None:
    lat_val = to_float(lat_corr)
    lon_val = to_float(lon_corr)
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE lonas
            SET estatus = ?, supervisor = ?, nota_supervision = ?,
                latitud_corregida = ?, longitud_corregida = ?, fecha_revision = ?
            WHERE id = ?
            """,
            (
                estatus,
                supervisor.strip(),
                nota.strip(),
                lat_val,
                lon_val,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                int(record_id),
            ),
        )
        conn.commit()


def update_manual_coordinate(record_id: int, lat: str, lon: str, note: str = "") -> None:
    lat_f = to_float(lat)
    lon_f = to_float(lon)
    if lat_f is None or lon_f is None:
        raise ValueError("Coordenadas inválidas")
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        raise ValueError("Coordenadas fuera de rango")

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE lonas
            SET latitud = ?, longitud = ?, fuente_coordenada = 'captura_manual',
                estado_coordenada = 'exacta', nota_supervision = COALESCE(nota_supervision, '') || ?
            WHERE id = ?
            """,
            (lat_f, lon_f, f"\nCoordenada manual: {note}" if note else "\nCoordenada manual.", int(record_id)),
        )
        conn.commit()


# -----------------------------
# Inicio de app
# -----------------------------
init_db()
migrate_initial_csvs_if_needed()
df = load_lonas_df()

st.markdown(
    """
    <div class='hero-card'>
        <div class='hero-title'>📍 Supervisión de Lonas</div>
        <p class='hero-subtitle'>Mapa operativo con base SQLite para cargar Excel, resolver coordenadas, validar ubicación y exportar KMZ.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if df.empty:
    st.warning("La base de datos aún no tiene registros. Entra a la pestaña 'Cargar Excel' para importar tu primer archivo.")


# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.markdown("### Filtros")

all_distritos = sorted(df["distrito_local"].dropna().astype(str).unique().tolist(), key=lambda x: (len(x), x)) if not df.empty else []
sel_distritos = st.sidebar.multiselect("Distrito local", all_distritos, default=all_distritos)

seccion_source = df[df["distrito_local"].astype(str).isin(sel_distritos)] if (sel_distritos and not df.empty) else df
all_secciones = sorted(seccion_source["seccion"].dropna().astype(str).unique().tolist(), key=lambda x: (len(x), x)) if not seccion_source.empty else []
sel_secciones = st.sidebar.multiselect("Sección", all_secciones)
sel_estatus = st.sidebar.multiselect("Estatus", STATUS_OPTIONS, default=[])
query = st.sidebar.text_input("Buscar", placeholder="Colonia, dirección, sección...")
only_mapeables = st.sidebar.checkbox("Solo registros con coordenada", value=False)

st.sidebar.divider()
st.sidebar.markdown("### Visualización del mapa")
map_style = st.sidebar.selectbox("Tipo de mapa base", list(TILE_OPTIONS.keys()), index=0)
cluster_points = st.sidebar.checkbox("Agrupar puntos cercanos", value=False)

filtered = filter_df(df, sel_distritos, sel_secciones, sel_estatus, query, only_mapeables=only_mapeables) if not df.empty else df

st.sidebar.divider()
st.sidebar.markdown("### Base de datos")
st.sidebar.caption(f"SQLite: `{DB_PATH.name}`")
if not filtered.empty:
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
    render_kpi("Registros totales", len(df), "base SQLite")
with k2:
    render_kpi("En filtro", len(filtered), "según selección")
with k3:
    render_kpi("Mapeables", int(df.dropna(subset=["latitud_mapa", "longitud_mapa"]).shape[0]) if not df.empty else 0, "con coordenada")
with k4:
    render_kpi("Pendientes coord.", int(df["latitud_mapa"].isna().sum()) if not df.empty else 0, "sin punto GPS")
with k5:
    total_lonas = pd.to_numeric(df.get("lonas_colocadas", pd.Series(dtype=float)), errors="coerce").fillna(0).sum() if not df.empty else 0
    render_kpi("Lonas", int(total_lonas), "suma capturada")

st.write("")


# -----------------------------
# Tabs
# -----------------------------
tab_map, tab_supervision_map, tab_summary, tab_review, tab_table, tab_pending, tab_export, tab_help, tab_upload = st.tabs(
    [
        "Mapa",
        "Mapa de supervisión",
        "Resumen",
        "Supervisión",
        "Tabla de supervisión",
        "Pendientes sin coordenada",
        "Exportar",
        "Guía rápida",
        "Cargar Excel",
    ]
)

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
        selected_for_map = st.session_state.get("selected_record_id")
        m = make_map(filtered, selected_for_map, selected_tile=map_style, cluster_points=cluster_points)
        st_folium(m, width=1280, height=680, returned_objects=[])

with tab_supervision_map:
    st.subheader("Mapa de supervisión")
    st.caption("Vista general agrupada: cada burbuja muestra el total de lonas/registros en esa zona. Al acercarte con zoom, los puntos se despliegan individualmente.")
    ms1, ms2 = st.columns([3.25, 1])

    with ms2:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.write("**Configuración**")
        supervision_tile = st.selectbox("Mapa base", list(TILE_OPTIONS.keys()), index=list(TILE_OPTIONS.keys()).index(map_style) if map_style in TILE_OPTIONS else 0, key="supervision_tile")
        st.caption("El cluster muestra el total. Click sobre la burbuja para acercar y separar puntos.")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.write("**Totales en filtro**")
        render_kpi("Registros agrupados", len(filtered), "según filtros activos")
        if not filtered.empty:
            resumen_dist = filtered.groupby("distrito_local", dropna=False).size().reset_index(name="total").sort_values("total", ascending=False)
            st.dataframe(resumen_dist, hide_index=True, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.write("**Leyenda**")
        render_status_legend()
        st.markdown("</div>", unsafe_allow_html=True)

    with ms1:
        st_folium(make_supervision_cluster_map(filtered, selected_tile=supervision_tile), width=1280, height=720, returned_objects=[])

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
        st.write("**Coordenadas por fuente**")
        if not filtered.empty:
            st.dataframe(filtered["fuente_coordenada"].fillna("pendiente").replace("", "pendiente").value_counts().rename_axis("fuente").reset_index(name="total"), hide_index=True, use_container_width=True)
        st.write("**Avance general de supervisión**")
        total = len(df)
        verificados = int((df["estatus"] == "Verificado").sum()) if not df.empty else 0
        avance = (verificados / total * 100) if total else 0
        st.progress(avance / 100 if total else 0)
        st.caption(f"{avance:.1f}% verificado sobre registros totales.")

    st.write("**Historial de cargas**")
    uploads_df = load_uploads_df()
    if uploads_df.empty:
        st.caption("Sin cargas registradas todavía.")
    else:
        st.dataframe(uploads_df, hide_index=True, use_container_width=True)

with tab_review:
    st.subheader("Revisión individual")
    mapeables_filtered = filtered.dropna(subset=["latitud_mapa", "longitud_mapa"]) if not filtered.empty else filtered

    if mapeables_filtered.empty:
        st.warning("No hay registros mapeables con los filtros actuales.")
    else:
        filtered_options = mapeables_filtered.sort_values(["distrito_local", "seccion", "id"]).copy()
        option_labels = {
            int(row.id): f"ID {int(row.id)} | D{row.distrito_local} S{row.seccion} | {row.colonia} | {str(row.direccion)[:55]}"
            for _, row in filtered_options.iterrows()
        }
        default_id = st.session_state.get("selected_record_id")
        ids = list(option_labels.keys())
        default_index = ids.index(default_id) if default_id in ids else 0
        selected_id = st.selectbox("Selecciona el registro a revisar", ids, index=default_index, format_func=lambda x: option_labels.get(x, str(x)))
        st.session_state["selected_record_id"] = selected_id

        row = df[df["id"].astype(int) == int(selected_id)].iloc[0]
        left, right = st.columns([1.15, 1])

        with left:
            st.markdown(f"### ID {selected_id}")
            st.write(f"**Archivo:** {row.get('archivo_origen','')} | **Fila Excel:** {row.get('fila_excel','')}")
            st.write(f"**Distrito local:** {row.get('distrito_local','')}  |  **Sección:** {row.get('seccion','')}")
            st.write(f"**Colonia:** {row.get('colonia','')}")
            st.write(f"**Dirección:** {row.get('direccion','')}")
            st.write(f"**Fuente coordenada:** {row.get('fuente_coordenada','')}")
            st.write(f"**Observaciones origen:** {row.get('observaciones','')}")
            if str(row.get("link_maps", "")):
                st.link_button("Abrir link original de Google Maps", str(row.get("link_maps")))
            imgs = image_files_for_record(selected_id, row.get("fila_excel"))
            if imgs:
                st.markdown("**Evidencia fotográfica**")
                for img in imgs[:3]:
                    st.image(str(img), caption=img.name, use_container_width=True)
            else:
                st.info("No se encontró imagen de evidencia para este registro.")

        with right:
            with st.form("form_revision"):
                estatus_actual = row.get("estatus", "Pendiente") or "Pendiente"
                estatus = st.selectbox("Estatus de supervisión", STATUS_OPTIONS, index=STATUS_OPTIONS.index(estatus_actual) if estatus_actual in STATUS_OPTIONS else 0)
                supervisor = st.text_input("Supervisor", value=str(row.get("supervisor", "") or ""), placeholder="Nombre de quien revisa")
                nota = st.text_area("Nota de supervisión", value=str(row.get("nota_supervision", "") or ""), height=120)
                st.markdown("**Corrección opcional de coordenadas**")
                st.caption("Déjalas vacías si la ubicación original es correcta.")
                lat_corr = st.text_input("Latitud corregida", value="" if pd.isna(row.get("latitud_corregida")) else str(row.get("latitud_corregida")))
                lon_corr = st.text_input("Longitud corregida", value="" if pd.isna(row.get("longitud_corregida")) else str(row.get("longitud_corregida")))
                guardar = st.form_submit_button("Guardar revisión", use_container_width=True)

                if guardar:
                    if (clean_value(lat_corr) and not clean_value(lon_corr)) or (clean_value(lon_corr) and not clean_value(lat_corr)):
                        st.error("Captura latitud y longitud corregidas, o deja ambas vacías.")
                    else:
                        coord_ok = True
                        if clean_value(lat_corr) and clean_value(lon_corr):
                            lat_f = to_float(lat_corr)
                            lon_f = to_float(lon_corr)
                            coord_ok = lat_f is not None and lon_f is not None and -90 <= lat_f <= 90 and -180 <= lon_f <= 180
                        if not coord_ok:
                            st.error("Las coordenadas corregidas no son válidas.")
                        else:
                            update_review(selected_id, estatus, supervisor, nota, lat_corr, lon_corr)
                            st.success("Revisión guardada. El mapa se actualizará con el nuevo estatus/coordenada.")
                            st.rerun()

            st.markdown("**Vista rápida del punto**")
            mini = load_lonas_df()
            mini = mini[mini["id"].astype(int) == int(selected_id)]
            st_folium(make_map(mini, selected_id, selected_tile=map_style, cluster_points=False), width=650, height=320, returned_objects=[])

with tab_table:
    st.subheader("Tabla filtrada")
    show_cols = [
        "id", "archivo_origen", "fila_excel", "fecha", "municipio", "distrito_local", "seccion", "colonia",
        "direccion", "lonas_colocadas", "estatus", "estado_coordenada", "fuente_coordenada", "supervisor",
        "nota_supervision", "fecha_revision", "latitud_mapa", "longitud_mapa", "observaciones", "link_maps",
    ]
    show_cols = [c for c in show_cols if c in filtered.columns]
    if filtered.empty:
        st.caption("Sin registros con los filtros actuales.")
    else:
        st.dataframe(filtered[show_cols].sort_values(["distrito_local", "seccion", "id"]), use_container_width=True, hide_index=True)

with tab_pending:
    st.subheader("Registros pendientes sin coordenada directa")
    st.caption("Aquí puedes resolver links cortos o capturar coordenadas manualmente para que aparezcan en el mapa.")
    pending = df[df["latitud_mapa"].isna() | df["longitud_mapa"].isna()].copy() if not df.empty else pd.DataFrame()

    p1, p2 = st.columns([1, 1])
    with p1:
        max_resolve = st.number_input("Resolver automáticamente hasta N pendientes", min_value=1, max_value=5000, value=50, step=10)
    with p2:
        st.write("")
        st.write("")
        if st.button("Intentar resolver links cortos", use_container_width=True):
            stats = resolve_pending_links(max_items=int(max_resolve))
            st.success(f"Procesados: {stats['procesados']} | Resueltos: {stats['resueltos']} | Pendientes: {stats['pendientes']}")
            st.rerun()

    if pending.empty:
        st.success("No hay pendientes sin coordenada.")
    else:
        st.dataframe(
            pending[[c for c in ["id", "archivo_origen", "fila_excel", "responsable", "distrito_local", "seccion", "colonia", "direccion", "link_maps", "fuente_coordenada"] if c in pending.columns]],
            use_container_width=True,
            hide_index=True,
        )
        st.download_button("Descargar pendientes CSV", dataframe_to_csv_bytes(pending), file_name="lonas_pendientes_sin_coordenada.csv", mime="text/csv", use_container_width=True)

        st.markdown("### Captura manual de coordenada")
        pending_ids = pending["id"].astype(int).tolist()
        selected_pending = st.selectbox("Selecciona ID pendiente", pending_ids, format_func=lambda x: f"ID {x}")
        prow = pending[pending["id"].astype(int) == int(selected_pending)].iloc[0]
        st.write(f"**Dirección:** {prow.get('direccion','')}")
        if clean_value(prow.get("link_maps", "")):
            st.link_button("Abrir link de Maps", str(prow.get("link_maps")))
        with st.form("manual_coord_form"):
            man_lat = st.text_input("Latitud")
            man_lon = st.text_input("Longitud")
            man_note = st.text_input("Nota", placeholder="Ej. coordenada copiada manualmente de Google Maps")
            save_coord = st.form_submit_button("Guardar coordenada manual", use_container_width=True)
            if save_coord:
                try:
                    update_manual_coordinate(selected_pending, man_lat, man_lon, man_note)
                    st.success("Coordenada guardada. El registro ya aparecerá en el mapa.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

with tab_export:
    st.subheader("Exportaciones")
    st.write("Descarga la base SQLite convertida a CSV/JSON o genera un KMZ actualizado con estatus y coordenadas corregidas.")
    export_all = st.checkbox("Exportar todos los registros", value=True)
    export_df = df if export_all else filtered
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.download_button("CSV de supervisión", dataframe_to_csv_bytes(export_df), file_name="supervision_lonas.csv", mime="text/csv", use_container_width=True)
    with c2:
        st.download_button("JSON de base", export_df.to_json(orient="records", force_ascii=False, indent=2).encode("utf-8"), file_name="supervision_lonas.json", mime="application/json", use_container_width=True)
    with c3:
        kmz_bytes = build_kmz_bytes(export_df)
        st.download_button("KMZ actualizado", kmz_bytes, file_name="lonas_supervision_actualizado.kmz", mime="application/vnd.google-earth.kmz", use_container_width=True)
    with c4:
        if DB_PATH.exists():
            st.download_button("Base SQLite", DB_PATH.read_bytes(), file_name="lonas_supervision.db", mime="application/octet-stream", use_container_width=True)

    st.info("En Streamlit Cloud los archivos locales pueden reiniciarse. Para uso formal multiusuario conviene migrar esta misma estructura a Supabase o a un servidor propio.")

with tab_help:
    st.subheader("Guía rápida de uso")
    st.markdown(
        """
        **Flujo recomendado:**

        1. Entra a **Cargar Excel** y sube uno o varios archivos `.xlsx`.
        2. Si los links son cortos `maps.app.goo.gl`, puedes activar resolución automática, pero puede tardar.
        3. Los registros con coordenada aparecen en **Mapa** y **Mapa de supervisión**.
        4. Los registros sin coordenada aparecen en **Pendientes sin coordenada**.
        5. Desde pendientes puedes intentar resolver links cortos o capturar latitud/longitud manualmente.
        6. En **Supervisión** marcas estatus, supervisor, nota y coordenada corregida.
        7. En **Exportar** descargas CSV, JSON, KMZ o la base SQLite.

        **Estados de coordenada:**

        - `exacta`: se obtuvo de link directo, link resuelto, Excel con lat/lon o captura manual.
        - `pendiente`: no se pudo extraer coordenada todavía.

        **Nota operativa:** SQLite funciona bien para demo/local. Para varios supervisores en Streamlit Cloud, lo más seguro será Supabase.
        """
    )

with tab_upload:
    st.subheader("Cargar Excel")
    st.caption("Carga nuevos reportes con el formato de lonas. La app detecta encabezados, guarda en SQLite y separa mapeables/pendientes.")

    if openpyxl is None:
        st.error("Falta instalar openpyxl. Agrégalo a requirements.txt para leer archivos XLSX.")

    uploaded_files = st.file_uploader(
        "Sube uno o varios archivos Excel",
        type=["xlsx", "xlsm"],
        accept_multiple_files=True,
    )

    resolve_on_upload = st.checkbox(
        "Intentar resolver links cortos al cargar",
        value=False,
        help="Puede tardar si el archivo trae muchos links maps.app.goo.gl. Para 1,600 registros conviene cargar primero y resolver por bloques desde Pendientes.",
    )

    if uploaded_files:
        st.write("**Archivos recibidos:**")
        for uf in uploaded_files:
            st.write(f"- {uf.name}")

        if st.button("Procesar e integrar a la base SQLite", type="primary", use_container_width=True):
            total_stats = []
            for uf in uploaded_files:
                file_bytes = uf.getvalue()
                try:
                    with st.spinner(f"Procesando {uf.name}..."):
                        stats = import_excel_to_db(file_bytes, uf.name, resolve_links=resolve_on_upload)
                    total_stats.append({"archivo": uf.name, **stats})
                    st.success(
                        f"{uf.name}: leídos {stats['registros_leidos']}, insertados {stats['insertados']}, "
                        f"duplicados {stats['duplicados']}, mapeables {stats['mapeables']}, pendientes {stats['pendientes']}, "
                        f"imágenes {stats['imagenes_extraidas']}"
                    )
                except Exception as e:
                    st.error(f"Error procesando {uf.name}: {e}")

            if total_stats:
                st.dataframe(pd.DataFrame(total_stats), hide_index=True, use_container_width=True)
                st.info("Carga terminada. Actualizando app...")
                time.sleep(1)
                st.rerun()

    st.divider()
    st.markdown("### Vista de base actual")
    st.write(f"Registros totales en SQLite: **{len(df)}**")
    st.write(f"Mapeables: **{int(df.dropna(subset=['latitud_mapa', 'longitud_mapa']).shape[0]) if not df.empty else 0}**")
    st.write(f"Pendientes sin coordenada: **{int(df['latitud_mapa'].isna().sum()) if not df.empty else 0}**")
