import csv
import time
import re
from pathlib import Path
import asyncio
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from clean_project.filters.llm_relevance_filter import LLMRelevanceFilter, PostContent
import clean_project.config.settings as config
# NUEVO: Importar filtro LLM
from clean_project.filters.llm_relevance_filter import check_relevance_sync
print("YouTube SCRAPER INICIADO (CON FILTRO LLM)")

# Definir las claves de API disponibles


def get_youtube_service():
    """Construye el servicio de YouTube con la clave actual."""
    return build("youtube", "v3", developerKey=api_keys[current_api_key_index])

youtube = get_youtube_service()

def switch_api_key():
    """Cambia a la siguiente API Key si la actual se agota."""
    global current_api_key_index, youtube
    current_api_key_index = (current_api_key_index + 1) % len(api_keys)
    print(f"🔑 Cambiando a la API Key {current_api_key_index + 1}")
    youtube = get_youtube_service()

# ===========================================================================
# 2. FUNCIÓN DE FILTRO ESTRICTO (REGEX)
# ===========================================================================
def pasa_filtro_contenido(texto, keyword_query):
    """
    Verifica si las palabras de la keyword aparecen realmente en el texto.
    Soporta coincidencias parciales al final (ej: 'dron' valida 'drones').
    """
    if not texto:
        return False
        
    texto_norm = texto.lower()
    query_clean = keyword_query.replace('"', '').lower()
    palabras_clave = [p.replace('*', '') for p in query_clean.split()]

    for palabra in palabras_clave:
        # Regex: inicio de palabra o simbolo (#) + palabra + sufijo opcional
        patron = r'(?:^|\W)#?' + re.escape(palabra) + r'\w*'
        if not re.search(patron, texto_norm):
            return False
    return True

def preparar_query_youtube(keyword):
    """Añade comillas para búsquedas más exactas en la API."""
    palabras = keyword.strip().split()
    if len(palabras) > 1:
        return " ".join(f'"{p}"' for p in palabras)
    else:
        return f'"{keyword}"'

# ===========================================================================
# 3. FUNCIONES DE BÚSQUEDA Y EXTRACCIÓN
# ===========================================================================

def search_videos(keyword, start_dt, end_dt, max_pages=1): #aumentar max_pages a 10 para producción
    """
    Busca videos filtrando DIRECTAMENTE en la API por fechas.
    Esto ahorra cuota al no descargar videos antiguos inservibles.
    """
    global api_keys_exceeded, youtube
    videos = []
    next_page_token = None
    regionCode_0 = "ES"
    relevanceLanguage_0 = "es"
    """
    📌 Explicación:

    - regionCode_0 = "ES"  
    Prioriza videos relevantes para España. No es un filtro estricto; videos de otros países aún pueden aparecer.

    - relevanceLanguage_0 = "es"  
    Prioriza videos relevantes para hablantes de español según YouTube. No garantiza que el video o los comentarios estén en español.

    ⚠️ Si la keyword está en inglés:
    1. YouTube buscará videos que coincidan con la keyword.
    2. Entre esos resultados, priorizará videos populares en España y que tengan más probabilidad de ser relevantes para hablantes de español.
    3. Los comentarios no se filtran por idioma: pueden estar en cualquier idioma.
    """

    # Convertir fechas al formato RFC 3339 (Requisito de YouTube API)
    rfc_start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    rfc_end   = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    for _ in range(max_pages):
        try:
            response = youtube.search().list(
                part="snippet",
                q=keyword,
                type="video",
                order="date",             # Ordenar: más reciente primero
                publishedAfter=rfc_start, # FILTRO API: Fecha Inicio
                publishedBefore=rfc_end,  # FILTRO API: Fecha Fin
                maxResults=50, #### OJO CAMBIAR A 50 PARA PRODUCCIÓN
                regionCode=regionCode_0,
                relevanceLanguage=relevanceLanguage_0,
                pageToken=next_page_token
            ).execute()

        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                print("⚠️ Quota alcanzada. Cambiando API Key...")
                api_keys_exceeded[current_api_key_index] = True
                if all(api_keys_exceeded):
                    print("⚠️ TODAS las API Keys agotadas.")
                    return None
                switch_api_key()
                # Reintentar llamada
                return search_videos(keyword, start_dt, end_dt, max_pages)
            else:
                print(f"Error búsqueda: {e}")
                return []

        items = response.get("items", [])
        if not items:
            break

        for item in items:
            videos.append({
                "videoId": item["id"]["videoId"],
                "title": item["snippet"]["title"]
            })

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break
            
    return videos

def get_video_details(video_id):
    """Devuelve estadísticas y detalles del video."""
    try:
        response = youtube.videos().list(
            part="snippet,statistics",
            id=video_id
        ).execute()
    except HttpError:
        return None

    if not response["items"]:
        return None

    video = response["items"][0]
    snippet = video["snippet"]
    stats = video["statistics"]
    
    # Intentamos obtener suscriptores del canal UNA VEZ por video (no por comentario)
    channel_id = snippet["channelId"]
    subscribers = 0
    try:
        channel_info = youtube.channels().list(
            part="statistics",
            id=channel_id
        ).execute()
        if channel_info.get("items"):
            subscribers = channel_info["items"][0]["statistics"].get("subscriberCount", 0)
    except:
        pass

    return {
        "titulo": snippet.get("title"),
        "id": video_id,
        "descripcion": snippet.get("description"),
        "fecha_publicacion": snippet.get("publishedAt"),
        "num_comentarios": stats.get("commentCount", 0),
        "num_likes": stats.get("likeCount", 0),
        "num_visualizaciones": stats.get("viewCount", 0),
        "canal_publica": snippet.get("channelTitle"),
        "canal_id": channel_id,
        "canal_suscriptores": subscribers,
        "tags": snippet.get("tags", [])
    }

def get_video_comments(video_id):
    """Obtiene los hilos de comentarios principales."""
    comments = []
    next_page_token = None

    while True:
        try:
            response = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=1000, #OJO CAMBIAR A 100 PARA PRODUCCIÓN
                textFormat="plainText",
                pageToken=next_page_token
            ).execute()

        except HttpError as e:
            if e.resp.status in [403, 404]: # Comentarios desactivados
                return [] 
            else:
                print(f"Error obteniendo comentarios: {e}")
                return []

        for item in response.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "autor": top.get("authorDisplayName"),
                "fecha": top.get("publishedAt"),
                "likes": top.get("likeCount"),
                "contenido": top.get("textDisplay"),
                "num_respuestas": item["snippet"].get("totalReplyCount", 0)
            })

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    return comments

# ===========================================================================
filter_instance = LLMRelevanceFilter()
async def run_youtube(config):
    api_keys = [
    config.CREDENTIALS["youtube"]["API_KEY_YOUTUBE"],
    config.CREDENTIALS["youtube"]["API_KEY_YOUTUBE2"],
    config.CREDENTIALS["youtube"]["API_KEY_YOUTUBE3"]
]

    current_api_key_index = 0
    api_keys_exceeded = [False] * len(api_keys)
    print("YouTube SCRAPER INICIADO CON FILTRO LLM")
    
    start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d")
    end_date = datetime.strptime(config.general["end_date"], "%Y-%m-%d")
    
    # NUEVO: Config para filtro LLM
    tema = config.general.get("tema", "")
    desc_tema = config.general.get("desc_tema", "")
    geo_scope = config.general.get("population_scope", "España")
    languages = config.general.get("languages", [])
    keywords = config.scraping["youtube"]["query"]
    search_form_lang_map = config.general.get("search_form_lang_map", {})
    
    output_folder = config.general["output_folder"]
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/youtube_global_dataset.csv"

    if Path(output_file).exists() and Path(output_file).stat().st_size > 0:
        print(f"⚠️ El archivo CSV de YouTube ya existe: {output_file}. Saltando...")
        return 
    
    # Estadísticas
    stats = {
        "videos_encontrados": 0,
        "videos_relevantes": 0,
        "videos_filtrados": 0,
        "comentarios_guardados": 0
    }
    
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=';')
        
        writer.writerow([
            "titulo_video", "descripcion_video", "usuario_comentario", 
            "contenido", "fecha_comentario", "id_video", "fecha_publicacion_video", 
            "numero_respuestas_al_comentario", "likes_comentario", "nombre_canal", 
            "likes_video", "hashtags_video", "enlace_video", 
            "numero_visualizaciones_video", "search_keyword", "keyword_languages",
            "llm_relevante"  # NUEVO CAMPO
        ])
        
        for keyword in keywords:
            languages = search_form_lang_map.get(keyword, [])
            print(f"🔹 Buscando videos para: {keyword}")
            
            query = preparar_query_youtube(keyword)
            videos = search_videos(query, start_date, end_date, max_pages=10)

            if not videos:
                continue
            
            print(f"   --> Procesando {len(videos)} videos potenciales...")

            for vid in videos:
                stats["videos_encontrados"] += 1
                vid_id = vid["videoId"]
                detalles = get_video_details(vid_id)
                
                if not detalles:
                    continue

                titulo_v = detalles["titulo"]
                descripcion_v = detalles["descripcion"] or ""
                texto_video_completo = titulo_v + " " + descripcion_v

                # ===================================================================
                # NUEVO: FILTRO LLM DE RELEVANCIA
                # ===================================================================
                print(f"\n🎥 Verificando relevancia del video: {titulo_v[:60]}...")
                
                es_relevante, confianza, razon = await filter_instance.check_relevance(
                    post=PostContent(text=texto_video_completo),
                    #images=None,  # Podríamos añadir thumbnail si queremos
                    tema=tema,
                    keywords=keywords,
                    geo_scope=geo_scope,
                    languages=languages,
                    desc_tema=desc_tema
                )
                
                if not es_relevante:
                    print(f"  ⏭️  Video NO relevante. Saltando comentarios.")
                    stats["videos_filtrados"] += 1
                    continue
                
                print(f"  ✅ Video RELEVANTE. Descargando comentarios...")
                stats["videos_relevantes"] += 1
                # ===================================================================

                # Descargar solo comentarios directos
                comments = get_video_comments(vid_id)
                if not comments:
                    continue

                for c in comments:
                    # Filtro fecha comentario
                    fecha_str = c.get("fecha")
                    try:
                        fecha_com_dt = datetime.strptime(fecha_str, "%Y-%m-%dT%H:%M:%SZ")
                    except:
                        continue
                    
                    if not (start_date <= fecha_com_dt <= end_date):
                        continue

                    contenido_c = c.get("contenido") or ""
                    EnlaceOriginal = f"https://www.youtube.com/watch?v={vid_id}"
                    
                    fila = [
                        titulo_v, descripcion_v, c.get("autor"), contenido_c,
                        fecha_str, vid_id, detalles["fecha_publicacion"],
                        c.get("num_respuestas"), c.get("likes"),
                        detalles["canal_publica"], detalles["num_likes"],
                        detalles["tags"], EnlaceOriginal,
                        detalles["num_visualizaciones"], keyword,
                        ",".join(languages),
                        "PENDIENTE"  # Se filtrará en fase 2
                    ]
                    writer.writerow(fila)
                    stats["comentarios_guardados"] += 1
    
    print(f"\n✅ CSV YouTube guardado en: {output_file}")
    print(f"\n📊 ESTADÍSTICAS:")
    print(f"  Videos encontrados: {stats['videos_encontrados']}")
    print(f"  Videos relevantes: {stats['videos_relevantes']}")
    print(f"  Videos filtrados: {stats['videos_filtrados']}")
    print(f"  Comentarios guardados: {stats['comentarios_guardados']}")