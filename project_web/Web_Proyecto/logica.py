from concurrent.futures import ThreadPoolExecutor, as_completed
import sys, json
from pathlib import Path
import os
import copy
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import asyncio
import nest_asyncio
import ollama
import re
import pandas as pd
import csv
from collections import Counter
import base64
import numpy as np



# --- NUEVO IMPORT PARA TOPICS ---
try:
    from sentence_transformers import SentenceTransformer, util
    print("✅ SentenceTransformers importado correctamente.")
except ImportError:
    print("⚠️ SentenceTransformers no encontrado. El filtrado por topic no funcionará.")
    SentenceTransformer = None
# -------------------------------
from temp_json import sync_analysis_db
try:
    from project_local.app_ORIGINAL import BASE_DIR
except ModuleNotFoundError:
    print("⚠️ project_local no encontrado, usando BASE_DIR_1 desde cwd")
    BASE_DIR_1 = Path.cwd()  # usa carpeta actual
#nest_asyncio.apply()

#================  Romina ================  
# ANALYSIS_DB = BASE_DIR_1 / "analysis_db.json"
ANALYSIS_DB = Path("analysis_db.json").resolve()
def save_analysis(record):
    db = []
    print("1")
    if ANALYSIS_DB.exists():
        db = json.loads(ANALYSIS_DB.read_text())
    print("2")
    db.append(record)
    ANALYSIS_DB.write_text(json.dumps(db, indent=2))
    print("3")

def clean_types(obj):
    import numpy as np
    import pandas as pd

    if isinstance(obj, dict):
        return {str(k): clean_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_types(v) for v in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        if np.isnan(obj) or np.isinf(obj):
            return 0.0
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif pd.isna(obj): # Maneja valores nulos de Pandas (NaN)
        return None
    else:
        return obj    
# ================ Romina ================    

'''
# A continuación agrego lo que me pidió Cristhian
'''
# =========================================================================
# 📍 CONFIGURACIÓN DE RUTAS
# =========================================================================
# Ruta ABSOLUTA a donde esta 'clean_project'
#RUTA_CLEAN_PROJECT = r"C:\Users\DATS004\Romina.albornoz Dropbox\Romina Albornoz\PERSONAL\clean_project\src\clean_project"

# Path(__file__).resolve() #Convierte la ruta de este arichivo en una ruta absoluta real
# parents[0] no es el archivo, es la carpeta que lo contiene

# Calculamos la ruta base del proyecto 'clean_project'
# Estructura asumida:
#   /social_media_opinion_analysis
#       /project_web/Web_Proyecto/ (donde está este archivo)
#       /clean_project/src/        (lo que queremos agregar al path)

ROOT_DIR = Path(__file__).resolve().parents[2] # Sube 2 niveles desde Web_Proyecto
RUTA_CLEAN_PROJECT = ROOT_DIR / "clean_project" / "src"

# Convertimos a STRING (Crucial para sys.path en algunos entornos)
ruta_str = str(RUTA_CLEAN_PROJECT)

print(f"=== RUTA CALCULADA: {ruta_str}")
# Añadimos esa ruta al sistema para que Python pueda encontrar los módulos
# Añadimos la ruta al INICIO del sistema (Prioridad máxima)
if ruta_str not in sys.path:
    sys.path.insert(0, ruta_str)
    print(f"✅ Ruta añadida a sys.path[0]")

# =========================================================================
# 3. PROBAR LOS IMPORTS (Sin ejecutar nada)
# =========================================================================
print("\n🧪 Intentando importar módulos...")

try:
    
    # Intentamos importar uno por uno para ver cuál falla
    print("   - Importando settings...", end=" ")
    import clean_project.config.settings as base_settings
    print("OK ✅")

    print("   - Importando Bluesky...", end=" ")
    # from clean_project.scrapers.bluesky_scraper_NEW_last_version import run_bluesky
    from clean_project.scrapers.bluesky_scraper_with_filter import run_bluesky
    print("OK ✅")

    print("   - Importando Reddit...", end=" ")
    # from clean_project.scrapers.reddit_scrapper_NEW_faster_last_version import run_reddit
    from clean_project.scrapers.reddit_scraper_with_filter import run_reddit
    print("OK ✅")

    # print("   - Importando Twitter...", end=" ")
    # from clean_project.scrapers.twitter_scraper_last_version import run_twitter
    # print("OK ✅")

    # print("   - Importando LinkedIn...", end=" ")
    # from clean_project.scrapers.linkedin_scraper import run_linkedin    
    # print("OK ✅")

    print("   - Importando YouTube...", end=" ")
    # from clean_project.scrapers.youtube_scraper2 import run_youtube
    from clean_project.scrapers.youtube_scraper_with_filter import run_youtube

    print("OK ✅")
    from clean_project.filters.llm_relevance_filter import check_relevance_sync
    # print("   - Importando TikTok...", end=" ")
    # from clean_project.scrapers.tiktok_scraping_last_version import scrape_tiktok as run_tiktok #run_tiktok #import scape_tiktok as run_tiktok            
    # print("OK ✅")
    
    print("   - Importando procesamiento de las keywords...", end=" ")
    from clean_project.keyword_processing.keyword_expansion import generate_search_forms
    print("OK ✅")

    ##  ✅ NUEVO ↓ (ROMINA)
    from clean_project.prompts.builder import build_sentiment_prompt, build_acceptance_prompt
    ##  ✅ NUEVO ↑ (ROMINA)

    try:
        #from clean_project.analysis.llm_analysis import llm_analysis
        from clean_project.analysis.first_analysis import llm_analysis

        print("IMPORT llm_analysis OK")
        #llm_analysis()
    except Exception as e:
        print("ERROR:", e)

    # try:
    #     from clean_project.analysis.only_pilares import ejecutar_pilares_analysis
    # except Exception as e:
    #     print("⚠️ No se pudo importar ejecutar_pilares_analysis:", e)
    #     ejecutar_pilares_analysis = None

    try:
        from clean_project.analysis.metrics import metrics
    except Exception as e:
        print("⚠️ No se pudo importar metrics:", e)
        metrics = None    

    ##### Export dataset en excel
    # try:
    #     from clean_project.analysis.export_dataset import metrics
    #     print("IMPORT METRICS OK")
        #metrics()    
    # except Exception as e:
    #     print("ERROR:", e)
    #####
    
    from clean_project.analysis.first_report import cargar_datos_para_reporte, generar_excel_sentimiento
    print("\n🎉 ¡ÉXITO TOTAL! Todos los imports funcionan.")
    print("Ya puedes usar estas funciones en tu backend.")

    try:
        from clean_project.prompts.keywords import get_prompt_keywords
        print("IMPORT OK")
    except Exception as e:
        print("ERROR:", e)    
except ImportError as e:
    print("\n❌ FALLÓ UN IMPORT.")
    print(f"Detalle del error: {e}")
    print("Asegúrate de que dentro de 'src' existe una carpeta llamada 'clean_project' y dentro tiene '__init__.py' o los archivos correctos.")

except Exception as e:
    print(f"\n❌ Ocurrió otro error: {e}")

try:
    from clean_project.analysis.first_report import generar_excel_sentimiento, cargar_datos_para_reporte
    print("IMPORT reporting OK ✅")
except Exception as e:
    print("ERROR REPORTING:", e)


try:
    from clean_project.analysis.nube import generar_nubes_dashboard
except Exception as e:
    print("ERROR NUBE:", e)

try: 
    from clean_project.vllm.vllm_keywords2 import expandir_tema, generar_keywords_por_idioma, combinar_keywords_multilingue
except Exception as e:
    print("ERROR VLLM KEYWORDS:", e)
try:
    from clean_project.vllm.vllm_sentiment_topic import llm_analysis as vllm_sentiment_analysis
except Exception as e:    
    print("ERROR VLLM SENTIMENT:", e)
try:    
    from clean_project.vllm.vllm_pilares import ejecutar_pilares_analysis as vllm_pilares_analysis
except Exception as e:
    print("ERROR VLLM PILARES:", e)
    
def limpiar_topic(texto: str) -> str:
    if not texto:
        return ""
    
    texto = str(texto).strip().lower()
    
    # Reemplazar guiones bajos por espacio
    texto = texto.replace("_", " ")
    
    # Quitar múltiples espacios
    texto = re.sub(r"\s+", " ", texto)
    
    # Opcional: quitar caracteres raros
    texto = re.sub(r"[^\w\s]", "", texto)
    
    return texto


def extraer_json(texto: str):
    if not texto: return None
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", texto)
        if match:
            try: return json.loads(match.group(0))
            except: return None
    return None



def calcular_dashboard_base(df):
    df = df.copy()
    # Normalización de seguridad
    df["SENTIMIENTO"] = pd.to_numeric(df["SENTIMIENTO"], errors="coerce").fillna(0).astype(int)
    df["TOPIC"] = df["TOPIC"].fillna("Otros").astype(str).str.strip()
    
    map_sent = {-1: "Negativo", 0: "Neutro", 1: "Positivo"}
    df["sent_label"] = df["SENTIMIENTO"].map(map_sent)

    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA"])
    df["FECHA"] = df["FECHA"].dt.strftime("%Y-%m-%d")

    # 1. KPIs Globales
    kpis = {
        "total": len(df),
        "positivos": (df["SENTIMIENTO"] == 1).sum(),
        "neutros": (df["SENTIMIENTO"] == 0).sum(),
        "negativos": (df["SENTIMIENTO"] == -1).sum(),
    }

    # 2. TÓPICOS (La parte que te falta)
    # Agrupamos y contamos sentimientos por cada tema
    df_topics = df[df["TOPIC"].str.lower() != "otros"].copy()
    topics_list = (
        df_topics.groupby("TOPIC")
        .agg(
            volumen=("ID", "count"),
            pos=("SENTIMIENTO", lambda x: (x == 1).sum()),
            neu=("SENTIMIENTO", lambda x: (x == 0).sum()),
            neg=("SENTIMIENTO", lambda x: (x == -1).sum()),
            sentimiento_prom=("SENTIMIENTO", "mean")
        )
        .reset_index()
        .sort_values(by="volumen", ascending=False)
        .head(15) # Top 15 temas
        .to_dict(orient="records")
    )

    # 3. Tendencias y Redes
    tendencia_global = df.groupby("FECHA").size().to_dict()
    volumen_por_red = df["FUENTE"].value_counts().to_dict()
    tendencia_por_red = {}
    tendencia_sentimiento = (
        df.groupby(["FECHA", "sent_label"])
          .size()
          .unstack(fill_value=0)
          .to_dict(orient="index")
    )

    for red in df["FUENTE"].unique():
        df_red = df[df["FUENTE"] == red]
        tendencia_por_red[red] = {
            "total": df_red.groupby("FECHA").size().to_dict(),
            "sentimiento": (
                df_red.groupby(["FECHA", "sent_label"])
                      .size()
                      .unstack(fill_value=0)
                      .to_dict(orient="index")
            )
        }

    return {
        "kpis": kpis,
        "tendencia_global": tendencia_global,
        "tendencia_sentimiento": tendencia_sentimiento,
        "volumen_por_red": volumen_por_red,
        "tendencia_por_red": tendencia_por_red,
        "topics": topics_list 
    }

def generar_keywords_con_ia(tema: str, target_languages: list[str], population_scope: str):
    #Si population_scope llega como lista, conviértela a texto
    print(f"🔍 DEBUG BACKEND - Population recibida: '{population_scope}' (Tipo: {type(population_scope)})")

    poblacion_str = ""
    if isinstance(population_scope, list):
        poblacion_str = ", ".join(population_scope) if population_scope else "público general"
    else:
        poblacion_str = str(population_scope).strip() or "público general"
    
    if not tema: 
        return []

    print(f"\n🚀 [INICIO] Probando generación para: '{tema}' | Idiomas: {target_languages} | Población objetivo: {poblacion_str}")

    # # 1. CHECK OLLAMA VIVO
    # print("👉 Paso 1: Verificando conexión con Ollama...")
    # try:
    #     models = ollama.list()
    #     print("   ✅ Ollama está corriendo. Modelos disponibles:",
    #           [m["model"] for m in models["models"][:3]])
    # except Exception as e:
    #     print(f"   ❌ ERROR FATAL: Ollama no responde. Detalles: {e}")
    #     return []

    # # 2. Generar prompt con idiomas
    # prompt = get_prompt_keywords(tema, target_languages, poblacion_str)

    # model_name = "qwen2.5:1.5b"#"gemma3:4b" #"qwen2.5:0.5b" # "gemma3:4b" #"qwen2.5:1.5b" #"llama3:latest" # "qwen2.5:1.5b" # 

    # print(f"👉 Paso 2: Enviando prompt al modelo '{model_name}'...")

    # try:
    #     response = ollama.chat(
    #         model=model_name,
    #         messages=[{"role": "user", "content": prompt}],
    #         options={
    #             "temperature": 0.1,
    #             "num_ctx": 4096,
    #         }
    #     )
    #     raw_content = response.get("message", {}).get("content", "")
    #     print(f"\n👉 Paso 3: Respuesta cruda recibida:\n{'-'*40}\n{raw_content}\n{'-'*40}")
        
    #     data = extraer_json(raw_content)
    #     if data and "keywords" in data:
    #         print(f"\n✅ ¡ÉXITO! Keywords extraídas: {data['keywords']}")
    #         return data["keywords"]
    #     else:
    #         print(f"\n⚠️ El modelo respondió, pero no se pudo extraer JSON válido.")
    #         return []

    # except Exception as e:
    #     print(f"\n❌ ERROR DURANTE LA GENERACIÓN: {e}")
    #     return []
    # ==============================
    # all_keywords_raw = []

    # # Iteramos por cada idioma solicitado usando la nueva lógica vLLM
    # for idioma in target_languages:
    #     print(f"🌐 Generando términos en {idioma}...")
    #     kws = generar_keywords_por_idioma(tema, idioma)#, poblacion_str)
    #     all_keywords_raw.extend(kws)

    # # Combinamos y eliminamos duplicados semánticos
    # resultado_final = combinar_keywords_multilingue(all_keywords_raw)
    
    # print(f"✅ ¡ÉXITO! {len(resultado_final['keywords'])} keywords únicas generadas.")
    # return resultado_final["keywords"]
    # ==============================
    # Capa 1: expandir tema (incluye búsqueda web)
    
    brief = expandir_tema(tema,population_scope)
    print(f"\n BRIEF: {brief['descripcion_breve']}")
    if not brief:
        print("⚠️ No se pudo expandir el tema.")
        return []

    # Capa 2: keywords en paralelo
    todas = []
    with ThreadPoolExecutor(max_workers=len(target_languages)) as executor:
        futuros = {
            executor.submit(generar_keywords_por_idioma, tema, idioma, population_scope, brief): idioma
            for idioma in target_languages
        }
        for futuro in as_completed(futuros):
            idioma = futuros[futuro]
            try:
                kws = futuro.result()
                print(f"   ✅ {idioma}: {len(kws)} keywords")
                todas.extend(kws)
            except Exception as e:
                print(f"   ❌ {idioma}: {e}")

    # Capa 3: combinar
    resultado = combinar_keywords_multilingue(todas)
    print(f"✅ ¡ÉXITO! {len(resultado['keywords'])} keywords únicas generadas: {resultado['keywords']}")
    return {
        "keywords": resultado["keywords"],
        "brief": brief.get('descripcion_breve', "")
    }


# =========================================================================
# 📍 NUEVAS FUNCIONES PARA FILTRO GEOGRÁFICO
# =========================================================================
def clean_types(obj):
    if isinstance(obj, dict):
        return {k: clean_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_types(v) for v in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        if np.isnan(obj):
            return 0.0
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj


# =========================================================================
# 🧠 LÓGICA DE FILTRADO SEMÁNTICO (Traída de retrive_topics.py)
# =========================================================================
_embedding_model = None

def get_model():
    """Carga el modelo solo una vez (Singleton) para ahorrar memoria."""
    global _embedding_model
    if _embedding_model is None and SentenceTransformer is not None:
        print("⏳ Cargando modelo de embeddings (esto puede tardar un poco)...")
        # Usamos el modelo que tenías en retrive_topics.py
        _embedding_model = SentenceTransformer("intfloat/multilingual-e5-large", device="cpu")
        print("✅ Modelo cargado.")
    return _embedding_model

def search_by_user_topic(df, user_topic, threshold=0.65):
    """
    Filtra el DataFrame buscando similitud semántica en las columnas Topic_N.
    """
    model = get_model()
    if not model or not user_topic:
        return df

    print(f"🔍 Ejecutando búsqueda semántica para: '{user_topic}' con umbral {threshold}")

    # 1. Identificar columnas de topics
    topic_cols = [c for c in df.columns if c.startswith("Topic_") or c == "TOPIC"]
    
    # 2. Extraer topics únicos del DataFrame
    all_topics = set()
    for col in topic_cols:
        # Aseguramos que sean strings y no nulos
        unique_vals = df[col].dropna().unique()
        for val in unique_vals:
            s_val = str(val).strip().lower()
            if s_val and s_val not in ["", "no relacionado", "otros"]:
                all_topics.add(s_val)
    
    all_topics_list = list(all_topics)
    
    if not all_topics_list:
        return df

    # 3. Calcular Embeddings
    # Prefijo "passage:" y "query:" es específico del modelo e5-large
    topic_embeddings = model.encode([f"passage: {t}" for t in all_topics_list])
    query_embedding = model.encode([f"query: {user_topic}"])

    # 4. Calcular Similitud Coseno
    from sklearn.metrics.pairwise import cosine_similarity
    scores = cosine_similarity(query_embedding, topic_embeddings)[0]

    # 5. Filtrar topics que superan el umbral
    similar_topics = [
        all_topics_list[i] for i, score in enumerate(scores)
        if score >= threshold
    ]
    
    print(f"   Topics encontrados ({len(similar_topics)}): {similar_topics[:5]} ...")

    if not similar_topics:
        print("   ⚠️ No se encontraron topics similares.")
        # Retornar dataframe vacío pero con columnas
        return df.iloc[0:0]

    similar_topics_norm = set(similar_topics)

    # 6. Filtrar filas que contengan alguno de los topics similares
    # Función auxiliar para aplicar a cada fila
    def row_has_topic(row):
        for col in topic_cols:
            val = str(row.get(col, "")).strip().lower()
            if val in similar_topics_norm:
                return True
        return False

    mask = df.apply(row_has_topic, axis=1)
    df_filtered = df[mask]
    
    print(f"   Registros tras filtro semántico: {len(df_filtered)}")
    return df_filtered

def asegurar_nubes_dashboard(output_folder: Path):
    """
    Verifica si existen las nubes del dashboard.
    Si no existen, las genera automáticamente.
    """

    print("🔎 Verificando nubes del dashboard...")

    # CSV base del que salen las nubes
    csv_base = output_folder / "datos_sentimiento_filtrados.csv"

    if not csv_base.exists():
        print("⚠️ No existe CSV base para generar nubes.")
        return {}

    # Detectar si ya existen imágenes
    existentes = list(output_folder.glob("nube_*.png"))

    if existentes:
        print(f"✅ Ya existen {len(existentes)} nubes. No se regeneran.")
        return {}

    print("☁️ No hay nubes → generando automáticamente...")

    nubes_dict = generar_nubes_dashboard(csv_base)

    # Guardar en PNG
    for nombre, b64_str in nubes_dict.items():
        if b64_str:
            with open(output_folder / f"{nombre}.png", "wb") as f:
                f.write(base64.b64decode(b64_str))

    print("✅ Nubes regeneradas correctamente.")

    return nubes_dict

def filtrar_y_recalcular_dashboard(csv_path, output_folder, terminos_geo, custom_topic=None):
    """
    1. Carga CSV.
    2. Aplica Filtro Geográfico (Regex).
    3. Aplica Filtro por Topic (Semántico).
    4. Recalcula Dashboard.
    """
    # 1. Cargar datos
    print(f"\n=== Analizando {csv_path.name} ===")
    with open(csv_path, 'r', encoding='utf-8') as f:
        primera_linea = f.readline()
        sep = ';' if ';' in primera_linea else ','

    df = pd.read_csv(csv_path, sep=sep, encoding='utf-8', engine='python', on_bad_lines='skip')

    
    # Normalizar columnas
    col_map = {
        "titulo": "TITULO", "comentario_texto": "CONTENIDO", "cuerpo": "CUERPO",
        "fuente": "FUENTE", "fecha": "FECHA", "sentimiento": "SENTIMIENTO",
        "topic": "TOPIC"
    }
    df.rename(columns=col_map, inplace=True)

    # Asegurar columnas de texto
    cols_busqueda = ["TITULO", "CUERPO", "CONTENIDO"]
    for col in cols_busqueda:
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna("").astype(str)

    # B. Métricas (NUEVO: Asegurar que sean números)
    cols_metricas = ['LIKES', 'COMMENTS', 'SHARES', 'VIEWS', 'FOLLOWERS']
    for col in cols_metricas:
        if col not in df.columns: df[col] = 0
        else: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    # C. Sentimiento
    if "SENTIMIENTO" in df.columns:
        df["SENTIMIENTO"] = pd.to_numeric(df["SENTIMIENTO"], errors='coerce').fillna(0).astype(int)
    
    # -------------------------------------------------------
    # 2. FILTRO GEOGRÁFICO (Regex)
    # -------------------------------------------------------
    if terminos_geo and len(terminos_geo) > 0:
        print(f"📍 Aplicando filtro geográfico: {terminos_geo}")
        patron = "|".join([re.escape(t.strip()) for t in terminos_geo if t.strip()])
        if patron:
            mask = (
                df["TITULO"].str.contains(patron, case=False, regex=True) |
                df["CUERPO"].str.contains(patron, case=False, regex=True) |
                df["CONTENIDO"].str.contains(patron, case=False, regex=True)
            )
            df = df[mask]
    
    # -------------------------------------------------------
    # 3. FILTRO POR TOPIC (Semántico) - NUEVO
    # -------------------------------------------------------
    if custom_topic and custom_topic.strip():
        print(f"🧠 Aplicando filtro por topic usuario: {custom_topic}")
        # Llamamos a la función que integra sentence_transformers
        df = search_by_user_topic(df, custom_topic, threshold=0.82) # Umbral ajustable

    print(f"📊 Registros finales tras todos los filtros: {len(df)}")

    # 4. Recalcular Dashboard Base
    dashboard_data = calcular_dashboard_base(df)
    
    # Raw data para JSON
    df_json = df.fillna("")
    dashboard_data["raw_data"] = df_json.to_dict(orient="records")

    # Recalcular Topics (Bloque C)
    if "TOPIC" in df.columns:
        df["TOPIC"] = (
            df["TOPIC"].apply(limpiar_topic)
        )
        topics = (
            df.groupby("TOPIC")
            .agg(
                volumen=("TOPIC", "count"),
                pos=("SENTIMIENTO", lambda x: (x == 1).sum()),   # <--- NUEVO
                neu=("SENTIMIENTO", lambda x: (x == 0).sum()),   # <--- NUEVO
                neg=("SENTIMIENTO", lambda x: (x == -1).sum()),  # <--- NUEVO
                sentimiento_prom=("SENTIMIENTO", "mean")

            )
            .reset_index()
            .to_dict(orient="records")
        )
        dashboard_data["topics"] = topics
    else:
        dashboard_data["topics"] = []

    # 5. Recalcular Nubes (Usando CSV temporal)
    temp_csv = Path(output_folder) / "temp_filtered_dashboard.csv"
    df.to_csv(temp_csv, index=False)
    
    nubes_base64 = {}
    try:
        nubes_dict = generar_nubes_dashboard(temp_csv)
        nubes_base64 = nubes_dict
    except Exception as e:
        print(f"⚠️ Error regenerando nubes: {e}")
    finally:
        if temp_csv.exists():
            try:
                os.remove(temp_csv)
            except: pass

    dashboard_data["nubes"] = nubes_base64
    dashboard_data = clean_types(dashboard_data)
    
    return dashboard_data

# def ejecutar_indicador_aceptacion(analysis_id: str, user: dict):
#     """
#     Ejecuta metrics_pilares sobre datos_sentimiento_filtrados.csv
#     del análisis que pertenece al usuario.
#     """

#     db = sync_analysis_db()

#     if not db:
#         raise Exception("No hay análisis registrados")

#     # Buscar análisis del usuario
#     # analysis = None
#     # for a in db:
#     #     if a.get("username") != user.get("username"):
#     #         continue
#     #     if a.get("status") == "deleted":
#     #         continue
#     #     if a.get("id") == analysis_id:
#     #         analysis = a
#     #         break

#     analysis = next((a for a in db if a.get("id") == analysis_id), None)

#     if not analysis:
#         raise Exception("No tienes permiso sobre este análisis")

#     output_folder = Path(analysis.get("output_folder"))
#     if not output_folder.is_absolute():
#         output_folder = (BASE_DIR_1 / output_folder).resolve()
#     if not output_folder.exists():
#         raise Exception("Carpeta del análisis no encontrada")
    
#     print(f"📄 Usando carpeta existente: {output_folder}")

#     # 🔹 Crear configuración dinámica (u_conf)
#     # CORRECCIÓN: Pasamos existing_output_folder para que NO cree una nueva
#     u_conf = crear_config_dinamica({
#         "username": user.get("username"),
#         "project_name": analysis.get("project_name"),
#         "start_date": analysis.get("start_date"),
#         "end_date": analysis.get("end_date"),
#         "keywords": analysis.get("keywords", []),
#         "population_scope": analysis.get("population_scope", ""),
#         "languages": analysis.get("languages", []),
#         "tema": analysis.get("tema") # Aseguramos pasar el tema
#     }, existing_output_folder=output_folder)

#     print(f"✅ Configuración dinámica creada para el análisis: {u_conf.general['output_folder']}")

#     # dataset_path = output_folder / "datos_con_pilares.csv"

#     # Si no existe el CSV con pilares, lo generamos
#     # if not dataset_path.exists():
#     #     print("⚠️ datos_con_pilares.csv no existe, ejecutando análisis LLM de pilares...")
#     #     
#     # ejecutar_pilares_analysis(u_conf)
#     vllm_pilares_analysis(u_conf)  # Usamos la función vLLM para generar los pilares y el CSV correspondiente
#     # Ejecutar métrica
#     metrics(u_conf)

#     result_path = output_folder / "aceptacion_global.json"

#     if not result_path.exists():
#         raise Exception("No se generó aceptacion_global.json")

#     result_data = json.loads(result_path.read_text(encoding="utf-8"))

#     return {
#         "analysis_id": analysis_id,
#         **result_data,   # ← aquí está la clave
#         "files": {
#             "json": str(output_folder / "aceptacion_global.json"),
#             "csv": str(output_folder / "aceptacion_global.csv"),
#             "txt": str(output_folder / "aceptacion_global.txt"),
#         }
#     }

# # =========================================================================
# # 🧠 2. FUNCIÓN PARA CREAR LA CONFIGURACIÓN DINÁMICA
# # =========================================================================

def recalcular_filas_incompletas(df):
    '''
    cols_indicadores = [
        'sent_Legitimación_sociopolítica',
        'sent_Efectividad_percibida',
        'sent_Justicia_y_equidad_percibida',
        'sent_Confianza_y_legitimidad_institucional'
    ]
    
    filas_incompletas = df[df[cols_indicadores].isna().any(axis=1)]
    for idx, fila in filas_incompletas.iterrows():
        resultados = vllm_pilares_analysis(fila) # ejecutar_pilares_analysis(fila)
        for col in cols_indicadores:
            df.at[idx, col] = resultados.get(col, 0)
    '''
    return df


# from clean_project.analysis.metrics import (
#      mapear_columnas_pilares, PILARES, aceptacion_global_promedio_pilares, generar_informe
# )

# def recalcular_aceptacion_filtrada(analysis_id: str, user: dict, terminos_geo: list):
#     """
#     Busca el análisis, carga sus datos con pilares y aplica el filtro geográfico.
#     """
#     # 1. Buscar el análisis en la base de datos (igual que en ejecutar_indicador_aceptacion)
#     db = sync_analysis_db()
#     analysis = next((a for a in db if a.get("id") == analysis_id and a.get("username") == user.get("username")), None)
    
#     if not analysis:
#         raise Exception("No tienes permiso sobre este análisis o no existe.")

#     output_folder = Path(analysis.get("output_folder"))
#     if not output_folder.is_absolute():
#         output_folder = (BASE_DIR_1 / output_folder).resolve()
#     # El archivo base para la aceptación es el que tiene los pilares calculados
#     csv_path = output_folder / "datos_con_pilares.csv"
    
#     if not csv_path.exists():
#         # Si no existe con pilares, intentamos el filtrado normal
#         csv_path = output_folder / "datos_sentimiento_filtrados.csv"

#     if not csv_path.exists():
#         raise Exception("No se encontraron datos para este análisis. Ejecute el análisis primero.")

#     # 2. Cargar el DataFrame
#     with open(csv_path, 'r', encoding='utf-8') as f:
#         primera_linea = f.readline()
#         sep = ';' if ';' in primera_linea else ','
    
#     df = pd.read_csv(csv_path, sep=sep, encoding='utf-8', engine='python', on_bad_lines='skip')

#     # Asegurar columnas de texto para el filtro
#     for col in ["TITULO", "CUERPO", "CONTENIDO"]:
#         if col in df.columns:
#             df[col] = df[col].fillna("").astype(str)

#     # 3. Aplicar filtro geográfico
#     print(f"📍 Aplicando filtro geo en recalcular: {terminos_geo}")
#     patron = "|".join([re.escape(t.strip()) for t in terminos_geo if t.strip()])
    
#     if patron:
#         mask = (
#             df["TITULO"].str.contains(patron, case=False, na=False) |
#             df["CUERPO"].str.contains(patron, case=False, na=False) |
#             df["CONTENIDO"].str.contains(patron, case=False, na=False)
#         )
#         df_filtrado = df[mask].copy()
#     else:
#         df_filtrado = df.copy()

#     print(f" Filas después de filtrar: {len(df_filtrado)} / {len(df)}")

#     # 4. Recalcular métricas (Usando las funciones importadas de metrics.py)
#     # Agrupamos por 'FUENTE'
#     all_rows = [(red, group.copy()) for red, group in df_filtrado.groupby("FUENTE")]
    
#     # PILARES y las funciones de cálculo deben estar disponibles
#     resultados = aceptacion_global_promedio_pilares(all_rows, PILARES)
#     informe = generar_informe(resultados, all_rows, PILARES)

#     # Devolver el resultado en el formato que espera el frontend
#     return {
#         "analysis_id": analysis_id,
#         **informe
#     }
        
# --- EN LOGICA.PY ---

def ejecutar_indicador_aceptacion(analysis_id: str, user: dict):
    """
    Se ejecuta al pulsar el botón 'Calcular Aceptación'.
    """
    # 1. Cargar DB usando ruta absoluta
    db_path = Path(__file__).resolve().parent / "analysis_db.json"
    if not db_path.exists():
        raise Exception("Base de datos no encontrada")
    
    db = json.loads(db_path.read_text(encoding="utf-8"))
    analysis = next((a for a in db if a.get("id") == analysis_id), None)

    if not analysis:
        raise Exception(f"Análisis {analysis_id} no encontrado en la DB")

    # 2. Resolver carpeta de salida
    folder_raw = Path(analysis.get("output_folder"))
    if folder_raw.is_absolute():
        folder_path = folder_raw
    else:
        folder_path = (BASE_DIR_1 / folder_raw).resolve()

    # 3. RECONSTRUCCIÓN DE DATOS FALTANTES (Para registros incompletos)
    # Si el registro de la DB no tiene tema o idiomas, los recuperamos o usamos defaults
    tema_recuperado = analysis.get("tema") or analysis.get("project_name") or "Análisis General"
    idiomas_recuperados = analysis.get("languages") or ["Castellano"]
    keywords_recuperadas = analysis.get("keywords") or []
    if isinstance(keywords_recuperadas, str):
        try: keywords_recuperadas = json.loads(keywords_recuperadas)
        except: keywords_recuperadas = []

    # 4. Crear u_conf dinámico
    u_conf = crear_config_dinamica({
        "username": analysis.get("username") or user.get("username"),
        "project_name": analysis.get("project_name"),
        "tema": tema_recuperado,
        "desc_tema": analysis.get("desc_tema", ""),
        "start_date": analysis.get("start_date"),
        "end_date": analysis.get("end_date"),
        "keywords": keywords_recuperadas,
        "languages": idiomas_recuperados,"population_scope": analysis.get("population_scope", "Público General")
    }, existing_output_folder=folder_path)

    # 5. EJECUTAR ANÁLISIS DE PILARES (vLLM)
    # Esta función leerá 'datos_sentimiento_filtrados.csv' y creará 'datos_con_pilares.csv'
    print(f"🧠 Ejecutando vLLM Pilares en: {folder_path}")
    print(f"\n Configuración: {u_conf}")
    vllm_pilares_analysis(u_conf)

    # 6. CALCULAR MÉTRICAS FINALES
    from clean_project.analysis.metrics import metrics
    metrics(u_conf)

    result_path = folder_path / "aceptacion_global.json"
    if not result_path.exists():
        raise Exception("Error: No se pudo generar el resumen de aceptación.")

    return json.loads(result_path.read_text(encoding="utf-8"))


def recalcular_aceptacion_filtrada(analysis_id: str, user: dict, terminos_geo: list):
    """
    Filtra los datos de aceptación. 
    DEBE leer 'datos_con_pilares.csv' obligatoriamente.
    """
    db_path = Path(__file__).resolve().parent / "analysis_db.json"
    db = json.loads(db_path.read_text(encoding="utf-8"))
    analysis = next((a for a in db if a.get("id") == analysis_id), None)
    
    if not analysis:
        return {"error": "Análisis no encontrado"}

    folder_raw = Path(analysis.get("output_folder"))
    folder_path = folder_raw if folder_raw.is_absolute() else (BASE_DIR_1 / folder_raw).resolve()
    print(f"📂 Carpeta del análisis: {folder_path}")

    # 🔥 EL CAMBIO CLAVE: Solo leer el archivo que tiene los pilares
    csv_path = folder_path / "datos_con_pilares.csv"

    print(f"📄 Buscando datos en: {csv_path}")
    
    if not csv_path.exists():        
        print(f"🚀 Archivo {csv_path.name} no encontrado. Iniciando ejecución automática...")
        try:
            ejecutar_indicador_aceptacion(analysis_id, user)
        except Exception as e:
            return {"error": f"No se pudo generar el análisis automáticamente: {str(e)}"}

    # Leer CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        sep = ';' if ';' in f.readline() else ','
    df = pd.read_csv(csv_path, sep=sep, encoding='utf-8', engine='python')
    df.columns = [c.upper() for c in df.columns]

    if "RED_SOCIAL" in df.columns:
        df.rename(columns={"RED_SOCIAL": "FUENTE"}, inplace=True)
    
    # 3. Aseguramos columnas de texto para el filtro
    for col in ["CONTENIDO", "TITULO", "CUERPO"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    # Aplicar filtro geográfico
    if terminos_geo:
        patron = "|".join([re.escape(t.strip()) for t in terminos_geo if t.strip()])
        mask = df["CONTENIDO"].astype(str).str.contains(patron, case=False, na=False) | \
               df["TITULO"].astype(str).str.contains(patron, case=False, na=False)
        df_filtrado = df[mask].copy()
    else:
        df_filtrado = df.copy()
        print("df_filtrado creado sin filtro geográfico porque no se proporcionaron términos.")
    # Recalcular métricas
    from clean_project.analysis.metrics import aceptacion_global_promedio_pilares, generar_informe, PILARES
    all_rows = [(red, group.copy()) for red, group in df_filtrado.groupby("FUENTE")]
    resultados = aceptacion_global_promedio_pilares(all_rows, PILARES)
    return generar_informe(resultados, all_rows, PILARES)

def crear_config_dinamica(data, existing_output_folder=None):
    print("⚙️ Creando configuración aislada...")

    # 1. Estructura base
    u_conf = SimpleNamespace(
        general=copy.deepcopy(base_settings.general),
        scraping=copy.deepcopy(base_settings.scraping),
        keywords_base=[],
        CREDENTIALS=base_settings.CREDENTIALS 
    )

    # 2. Fechas
    u_conf.general["start_date"] = data.get("start_date")
    u_conf.general["end_date"] = data.get("end_date")
    u_conf.desc_tema = data.get("desc_tema") or "Sin descripción disponible" 

    # 3. Carpeta de Salida
    if existing_output_folder:
        output_path = Path(existing_output_folder)
        u_conf.general["output_folder"] = str(output_path)
    else:
        project_name = data.get("project_name", "sin_nombre").replace(" ", "_")
        output_path = BASE_DIR_1 / "datos" / f"{data.get('username')}/{project_name}"
        i=0
        while output_path.exists():
            i += 1
            output_path = BASE_DIR_1 / "datos" / f"{data.get('username')}/{project_name} ({i})"
        output_path.mkdir(parents=True, exist_ok=True)
        u_conf.general["output_folder"] = str(output_path)

    # 4. Credenciales (Resumido para no ocupar espacio, mantén tu lógica de credenciales aquí)
    creds = u_conf.CREDENTIALS
    if "bluesky" in creds:
        u_conf.USERNAME_bluesky = creds["bluesky"].get("USERNAME_bluesky", "")
        u_conf.PASSWORD_bluesky = creds["bluesky"].get("PASSWORD_bluesky", "")
    # ... (Mantén el resto de tus credenciales igual) ...
    if "reddit" in creds:
        u_conf.REDDIT_CLIENT_ID = creds["reddit"].get("reddit_client_id", "")
        u_conf.REDDIT_CLIENT_SECRET = creds["reddit"].get("reddit_client_secret", "")

    # 5. Procesamiento de Keywords y Idiomas
    raw_keywords = data.get("keywords", [])
    if isinstance(raw_keywords, str):
        try: raw_keywords = json.loads(raw_keywords)  # convertir string JSON a lista de dicts
        except: raw_keywords = []

    unique_search_forms = []
    search_form_lang_map = {}
    for item in raw_keywords:
        if isinstance(item, dict) and item.get("keyword"):
            keyword = item["keyword"]
            language = item.get("languages")
            unique_search_forms.append(item.get("keyword"))
            search_form_lang_map[keyword] = [language]  # ⚠️ lista de idiomas por keyword
    
    # Guardar en configuración
    u_conf.general["keywords"] = unique_search_forms
    u_conf.general["search_form_lang_map"] = search_form_lang_map
    for red in u_conf.scraping:
        u_conf.scraping[red]["query"] = unique_search_forms
    # Dentro de crear_config_dinamica()
    # u_conf.general["search_form_lang_map"] = {}

    # for kw in unique_search_forms:
    #     # Aquí asignas los idiomas que quieras para cada keyword
    #     u_conf.general["search_form_lang_map"][kw] = u_conf.languages
    
    ## u_conf.keywords = unique_search_forms  # 🔥 AÑADIR ESTA LÍNEA
    # 6. ASIGNACIÓN CRÍTICA DE VARIABLES PARA EL PROMPT
    # Tema
    u_conf.tema = data.get("tema") or data.get("asistente") or "Análisis General"
    
    # Idiomas (Asegurar que sea lista)
    raw_langs = data.get("languages", [])
    if isinstance(raw_langs, str):
        u_conf.languages = [raw_langs]
    else:
        u_conf.languages = raw_langs if raw_langs else ["Español"] # Default si vacío

    # Geo Scope / Population (Manejo del string vacío del JSON)
    raw_pop = data.get("population_scope") or data.get("population") or ""
    
    if isinstance(raw_pop, list):
        # Si ya es lista, úsala, si está vacía pon Global
        u_conf.geo_scope = ", ".join(raw_pop) if raw_pop else "Público General"
    elif isinstance(raw_pop, str):
        # Si es string y no está vacío, úsalo. Si es "", pon Global
        u_conf.geo_scope = raw_pop if raw_pop.strip() else "Público General"
    else:
        u_conf.geo_scope = "Público General"

    # Asignamos population_scope igual para compatibilidad
    u_conf.population_scope = u_conf.geo_scope

    print(f"Configuración lista. Tema: {u_conf.tema} | Idiomas: {u_conf.languages}| Geo: {u_conf.geo_scope} ")
    
    return u_conf
# Crear funcion que entre solamente a cada run_{red} sin ejecutar todo, solo para evitar errores de importacion. 
# Probar que entra solamente sin ejecutar run_{red}
def ejecutar_analisis(data):
    print("Iniciando análisis de datos...")

    resultados = []

    for item in data["results"]:
        red_social = item["social"]

        # if red_social == "twitter":
        #     try:
        #         resultado = run_twitter()
        #     except:
        #         print("Error al ejecutar run_twitter")    
        # elif red_social == "linkedin":
        #     try:
        #         resultado = run_linkedin()
        #     except:
        #         print("Error al ejecutar run_linkedin")    
        # elif red_social == "youtube":
        #     try:
        #         resultado = run_youtube()
        #     except:
        #         print("Error al ejecutar run_youtube")
        # elif red_social == "tiktok":
        #     try:
        #         resultado = run_tiktok()
        #     except:
        #         print("Error al ejecutar run_tiktok")
        if red_social == "reddit":
            try:
                async def ejecutar_scraper():
                    resultados_reddit = await run_reddit(u_conf)
                    return resultados_reddit
            except:
                print("Error al ejecutar run_reddit")
        elif red_social == "bluesky":
            try:
                resultado = run_bluesky(u_conf)
            except:
                print("Error al ejecutar run_bluesky")
        else:
            resultado = {"error": f"Red social '{red_social}' no soportada."}

    return print("Análisis de datos completado.")

'''
# A continuación el código original de Cristhian
'''
async def backend_analisis(data,analysis_id): # 1. Asegurar que es async
    print("######################")
    print("BACKEND")
    print("######################")
    
    raw_pop = data.get("population_scope") or data.get("population") or ""
    #analysis_id = str(uuid.uuid4())

    try:
        u_conf = crear_config_dinamica(data)
        output_folder = Path(u_conf.general["output_folder"])
        
        # Lógica de ruta relativa para la DB
        try:
            relative_output_folder = Path(output_folder).relative_to(BASE_DIR_1).as_posix()
        except Exception:
            relative_output_folder = Path(output_folder).name

        # Guardar registro inicial en la DB
        output_folder = u_conf.general["output_folder"]
        analysis_record = {
            "id": analysis_id,
            "project_name": data.get("project_name"),
            "tema": data.get("tema") or data.get("asistente"),
            "desc_tema": data.get("desc_tema", ""),
            "username": data.get("username"),
            "output_folder": relative_output_folder,
            "sources": data.get("sources", []),
            "keywords": data.get("keywords", []),
            "languages": data.get("languages", []),
            "population_scope": u_conf.population_scope,
            "start_date": data.get("start_date"),
            "end_date": data.get("end_date"),
            "status": "completed",
            "created_at": datetime.now().isoformat()
        }
        save_analysis(analysis_record)

    except Exception as e:
        return {"mensaje": f"Error creando configuración: {e}", "resultados": []}
    
    # 2. Ejecución de Scrapers con await
    redes_seleccionadas = data.get("sources", [])
    for red in redes_seleccionadas: 
        try:
            if red == "bluesky":
                print(f"🌐 Iniciando {red}...")
                # LLAMADA LIMPIA: Sin hilos, sin loops anidados
                await run_bluesky(u_conf) 
                print(f"✅ Bluesky completado")
                # try:
                #     run_bluesky(u_conf)
                # except Exception as e:
                #     # Si da el error de "running event loop", lo ejecutamos en un hilo
                #     print(f"⚠️ Reintentando Bluesky en hilo separado por conflicto de loop...")
                #     import concurrent.futures
                #     loop = asyncio.get_event_loop()
                #     with concurrent.futures.ThreadPoolExecutor() as pool:
                #         def sync_wrapper():
                #             # Creamos un nuevo loop en el hilo para el scraper
                #             new_loop = asyncio.new_event_loop()
                #             asyncio.set_event_loop(new_loop)
                #             return new_loop.run_until_complete(run_bluesky(u_conf))
                #         await loop.run_in_executor(pool, sync_wrapper)
                #     print(f"✅ Bluesky completado (vía thread)")    
            elif red == "reddit":
                await run_reddit(u_conf)  # await corregido
            # elif red == "twitter":
            #     await run_twitter(u_conf)
            elif red == "youtube":
                await run_youtube(u_conf)
            # elif red == "linkedin":
            #     await run_linkedin(u_conf)
            # elif red == "tiktok":
            #     await run_tiktok(u_conf)
                # ... (lógica de filtrado de fechas de tiktok se mantiene igual)
            print(f"✅ {red} completado")
        except Exception as e:
            print(f"❌ Error ejecutando {red}: {e}")

    # 3. Análisis de Sentimiento y Tópico (vLLM)
    try:
        print("🧠 Ejecutando análisis de sentimiento y tópico con vLLM...")
        print(u_conf)
        vllm_sentiment_analysis(u_conf)
    except Exception as e:
        print("❌ Error ejecutando LLM Sentiment:", e)  

    # --- NOTA: HEMOS QUITADO PILARES DE AQUÍ PARA QUE NO SEA AUTOMÁTICO ---

    # 4. Generación de Reportes y Dashboard
    try:
        all_rows = cargar_datos_para_reporte(u_conf)
        output_folder_path = Path(u_conf.general["output_folder"])

        if all_rows:
            df_final, _ = generar_excel_sentimiento(all_rows, output_folder_path)
            
            if df_final is not None and not df_final.empty:
                # Normalizar nombres de columnas
                print(f"📊 Registros antes de filtrar: {len(df_final)}")

                # 1. FILTRO DE RELEVANCIA: Quitar Sentimiento 2 (No relacionado)
                # Usamos .astype(str) para evitar problemas si vienen como int o string
                df_final = df_final[df_final["sentimiento"].astype(str) != "2"]

                # 2. FILTRO DE IDIOMA: Solo idiomas permitidos por el usuario
                if hasattr(u_conf, 'languages') and u_conf.languages:
                    from clean_project.analysis.nube import CSV_LANG_TO_CODE
                    
                    # Convertimos la lista del frontend (ej: ["Castellano", "Inglés"]) a códigos (["es", "en"])
                    allowed_codes = [CSV_LANG_TO_CODE.get(l.lower()) for l in u_conf.languages if CSV_LANG_TO_CODE.get(l.lower())]
                    
                    if "IDIOMA_IA" in df_final.columns:
                        # Mapeamos el idioma que detectó la IA a su código de 2 letras
                        df_final["lang_check"] = df_final["IDIOMA_IA"].str.lower().map(CSV_LANG_TO_CODE)
                        
                        # Mantenemos solo las filas cuyo idioma esté en la lista permitida
                        df_final = df_final[df_final["lang_check"].isin(allowed_codes)]
                        
                        # Limpiamos la columna temporal
                        df_final = df_final.drop(columns=["lang_check"])

                print(f"✅ Registros tras filtrar (Relevancia + Idioma): {len(df_final)}")

                # 3. NORMALIZACIÓN DE COLUMNAS PARA EL DASHBOARD
                col_map = {
                    "sentimiento": "SENTIMIENTO", 
                    "topic": "TOPIC", 
                    "contenido": "CONTENIDO", 
                    "fecha": "FECHA"
                }
                df_final.rename(columns=col_map, inplace=True)

                # Normalizar tipos de datos
                if "FECHA" in df_final.columns:
                    df_final["FECHA"] = pd.to_datetime(df_final["FECHA"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
                
                df_final["SENTIMIENTO"] = pd.to_numeric(df_final.get("SENTIMIENTO", 0), errors="coerce").fillna(0).astype(int)

                # Calcular Dashboard Base
                dashboard_base = calcular_dashboard_base(df_final)
                dashboard_base["raw_data"] = df_final.fillna("").to_dict(orient="records")

                # 5. CORRECCIÓN: Usar df_final en lugar de df
                if "TOPIC" in df_final.columns:
                    df_final["TOPIC"] = df_final["TOPIC"].apply(limpiar_topic)
                    topics = (
                        df_final.groupby("TOPIC")
                        .agg(volumen=("TOPIC", "count"), sentimiento_prom=("SENTIMIENTO", "mean"))
                        .reset_index()
                        .to_dict(orient="records")
                    )
                    dashboard_base["topics"] = topics

                # Guardar JSON
                with open(output_folder_path / "dashboard_data.json", "w", encoding="utf-8") as f:
                    json.dump(dashboard_base, f, indent=2, default=str)
                
                print("✅ Dashboard JSON inicial guardado correctamente.")

    except Exception as e:
        print(f"❌ Error generando reportes: {e}")
        import traceback
        traceback.print_exc()

    # 6. Nubes de palabras
    try:
        csv_filtrado = Path(u_conf.general["output_folder"]) / "datos_sentimiento_filtrados.csv"
        if csv_filtrado.exists():
            nubes_dict = generar_nubes_dashboard(csv_filtrado,u_conf.languages)
            for nombre, b64_str in nubes_dict.items():
                if b64_str:
                    with open(Path(u_conf.general["output_folder"]) / f"{nombre}.png", "wb") as f:
                        f.write(base64.b64decode(b64_str))
    except Exception as e:
        print(f"❌ Error generando nubes: {e}")

    return {
        "mensaje": "Análisis completado",
        "analysis_id": analysis_id,
        "output_folder": str(u_conf.general["output_folder"]), 
        "dashboard": {
            "path": str(u_conf.general["output_folder"]),
            "json": "dashboard_data.json"
        }   
    }

# Bloque principal
if __name__ == "__main__":
    # FastAPI pasa los datos como argumento JSON
    print("hola caracola")
    if len(sys.argv) < 2:
        print("Error: Se esperaba un argumento JSON con los datos")
        sys.exit(1)

    data_json = sys.argv[1]
    try:
        data = json.loads(data_json)
    except json.JSONDecodeError:
        print("Error: No se pudo decodificar el JSON")
        sys.exit(1)

    ejecutar_analisis(data)
    # Obtener de datos: {'project_name': 'robots', 'keywords': 'robots domesticos', 'start_date': '2026-01-01', 'end_date': '2026-01-14', 'sources': ['bluesky', 'reddit', 'twitter', 'youtube', 'linkedin', 'tiktok'], 'results': [{'social': 'BlueSky', 'success': False}, {'social': 'Reddit', 'success': False}, {'social': 'Twitter / X', 'success': False}, {'social': 'Youtube', 'success': True}, {'social': 'Linkedin', 'success': True}, {'social': 'Tiktok', 'success': True}]}
    # poject_name para usarlo como  nombre de directorio sin espacios ni caracteres raros
    
def preparar_texto_unificado(row, red):
    # Extraer contexto según la red
    if red == "reddit":
        titulo = str(row.get("post_title", "")).strip()
        cuerpo = str(row.get("post_selftext", "")).strip()
    elif red == "youtube":
        titulo = str(row.get("titulo_video", "")).strip()
        cuerpo = str(row.get("descripcion_video", "")).strip()
    elif red == "twitter":
        titulo = str(row.get("BeforeContenido", "")).strip()
        cuerpo = ""
    else:
        titulo, cuerpo = "", ""

    contenido = str(row.get("contenido", "")).strip()
    keyword = str(row.get("search_keyword", "")).strip()
    language = str(row.get("keyword_languages", "")).strip()
    
    return (titulo if titulo.lower() != "nan" else ""), \
           (cuerpo if cuerpo.lower() != "nan" else ""), \
           (contenido if contenido.lower() != "nan" else ""), \
           keyword, language

def estandarizar_para_dashboard(df, red):
    import hashlib
    nuevo_df = pd.DataFrame()
    
    # ID
    col_user = 'usuario_comentario' if red == 'youtube' else 'usuario'
    nuevo_df['ID'] = df[col_user].astype(str).fillna('unknown').apply(
        lambda x: hashlib.sha256(x.encode()).hexdigest()[:16].upper()
    )

    # Fecha
    col_date = 'fecha_comentario' if red == 'youtube' else 'fecha'
    nuevo_df['FECHA'] = pd.to_datetime(df[col_date], errors='coerce').dt.strftime('%Y-%m-%d')

    # Textos y Contexto
    titulos, cuerpos, contenidos, keywords, languages = [], [], [], [], []
    for _, row in df.iterrows():
        t, c, cont, k, l = preparar_texto_unificado(row, red)
        titulos.append(t)
        cuerpos.append(c)
        contenidos.append(cont)
        keywords.append(k)
        languages.append(l)

    nuevo_df['TITULO'] = titulos
    nuevo_df['CUERPO'] = cuerpos
    nuevo_df['CONTENIDO'] = contenidos
    nuevo_df['KEYWORD'] = keywords
    nuevo_df['LANGUAGE'] = languages
    nuevo_df['FUENTE'] = red.capitalize()

    # MÉTRICAS (Likes, Comments, etc.) - IMPORTANTE PARA EL DASHBOARD
    for col in ['LIKES', 'COMMENTS', 'SHARES', 'FOLLOWERS', 'VIEWS']:
        source_col = col.lower() if col.lower() in df.columns else col
        if source_col in df.columns:
            nuevo_df[col] = pd.to_numeric(df[source_col], errors='coerce').fillna(0).astype(int)
        else:
            nuevo_df[col] = 0

    # Sentimiento y Topic
    nuevo_df['SENTIMIENTO'] = pd.to_numeric(df['sentimiento'], errors='coerce').fillna(2)
    nuevo_df['TOPIC'] = df['topic'].astype(str).fillna("Otros").str.strip()
    
    if "IDIOMA_IA" in df.columns:
        nuevo_df['IDIOMA_IA'] = df['IDIOMA_IA'].fillna("Desconocido")
    else:
        nuevo_df['IDIOMA_IA'] = "Desconocido"

    return nuevo_df[nuevo_df['SENTIMIENTO'] != 2].copy()
def reconstruir_dashboard_desde_csv(folder_path, analysis_id):
    folder = Path(folder_path)
    archivos = list(folder.glob("*_analizado.csv"))
    if not archivos: return None

    # 1. Cargar descripción desde la DB
    db_path = Path(__file__).resolve().parent / "analysis_db.json"
    db = json.loads(db_path.read_text(encoding="utf-8"))
    analysis = next((a for a in db if a["id"] == analysis_id), None)
    desc_tema = analysis.get("desc_tema", "") if analysis else ""

    # 2. Unificar DataFrames
    lista_dfs = []
    for archivo in archivos:
        try:
            df = pd.read_csv(archivo, sep=';', encoding='utf-8', engine='python', on_bad_lines='skip')
            red = archivo.name.split("_")[0].lower()
            df_std = estandarizar_para_dashboard(df, red)
            if not df_std.empty: lista_dfs.append(df_std)
        except: continue

    if not lista_dfs: return None
    df_final = pd.concat(lista_dfs, ignore_index=True)
    
    # 3. Guardar CSV unificado (necesario para las nubes)
    csv_path = folder / "datos_sentimiento_filtrados.csv"
    df_final.to_csv(csv_path, index=False, sep=';', encoding="utf-8")
    
    # 4. Generar Dashboard Data
    db_data = calcular_dashboard_base(df_final)
    db_data["desc_tema"] = desc_tema
    db_data["raw_data"] = df_final.fillna("").to_dict(orient="records")
    
    # 5. Generar Nubes de palabras
    try:
        asegurar_nubes_dashboard(folder)
    except Exception as e:
        print(f"⚠️ Error generando nubes en reconstrucción: {e}")

    # 6. Limpiar y Guardar JSON
    db_data = clean_types(db_data)
    with open(folder / "dashboard_data.json", "w", encoding="utf-8") as f:
        json.dump(db_data, f, indent=2, ensure_ascii=False)
    
    return db_data