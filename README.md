# Supervisión de Lonas - Streamlit

Aplicación operativa para supervisar lonas en mapa interactivo.

## Cambios de esta versión

- Diseño visual en paleta guinda/beige/dorado inspirada en Morena.
- Se retiraron las opciones de compartir por WhatsApp.
- Selector de tipo de mapa base: calles claro, calles OSM, satélite, terreno/relieve y oscuro.
- Opción para activar/desactivar agrupación de puntos cercanos.
- Pestañas: Mapa, Resumen, Supervisión, Tabla, Pendientes sin coordenada, Exportar y Guía rápida.
- Exportación a CSV, JSON y KMZ actualizado.

## Ejecución local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Despliegue en Streamlit Cloud

1. Sube esta carpeta a un repositorio de GitHub.
2. En Streamlit Cloud selecciona `app.py` como archivo principal.
3. Comparte el enlace de la app con los supervisores.

## Nota de persistencia

La app guarda revisiones en `reviews/revisiones_lonas.json`. En Streamlit Cloud ese almacenamiento puede ser temporal; para uso multiusuario formal se recomienda Supabase, Firebase o una base persistente en un servidor propio.
