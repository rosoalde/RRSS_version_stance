import clean_project.config.settings as config
import csv
import time
import re
from pathlib import Path
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ===========================================================================
# 1. CONFIGURACIÓN Y FECHAS
# ===========================================================================

print("YouTube SCRAPER INICIADO")

# Convertir fechas de configuración
#start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d")#datetime.strptime(config.general["start_date"], "%Y-%m-%d")

# Ajustamos la fecha fin al FINAL del día (23:59:59) para no perder datos del último día
#end_date_raw = datetime.strptime(config.general["end_date"], "%Y-%m-%d")
#end_date = datetime.strptime(config.general["end_date"], "%Y-%m-%d")#end_date_raw.replace(hour=23, minute=59, second=59)

#print(f"📅 Rango de Fechas Configurado: {start_date} <--> {end_date}")

# Definir las claves de API disponibles
api_keys = [
    config.CREDENTIALS["youtube"]["API_KEY_YOUTUBE"],
    config.CREDENTIALS["youtube"]["API_KEY_YOUTUBE2"],
    config.CREDENTIALS["youtube"]["API_KEY_YOUTUBE3"]
]

current_api_key_index = 0
api_keys_exceeded = [False] * len(api_keys)

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
# 4. SCRAPER PRINCIPAL (Bucle Lógico)
# ===========================================================================

def run_youtube(config):
    print("YouTube SCRAPER INICIADO")

    start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d")
    end_date   = datetime.strptime(config.general["end_date"], "%Y-%m-%d")

    print(f"📅 Rango de Fechas Configurado (DINÁMICO): {start_date} <--> {end_date}")

    keywords = config.scraping["youtube"]["query"]
    print(f"\n KEYWORDS QUE SE VAN A BUSCAR EN YOUTUBE: {keywords}\n")
    search_form_lang_map = config.general.get("search_form_lang_map", {})
    
    output_folder = config.general["output_folder"]
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/youtube_global_dataset.csv"

    # Verificar si ya existe para no sobrescribir sin querer
    if Path(output_file).exists() and Path(output_file).stat().st_size > 0:
        print(f"⚠️ El archivo CSV de YouTube ya existe en: {output_file}. Saltando...")
        return 
    
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        # Delimitador punto y coma (;) para Excel en español
        writer = csv.writer(f, delimiter=';') 

        # Cabeceras
        writer.writerow([
            "titulo_video", "descripcion_video",   # <--- NUEVA COLUMNA
            "usuario_comentario",  "contenido", "fecha_comentario", 
            "id_video", "fecha_publicacion_video", "numero_respuestas_al_comentario", 
            "likes_comentario", "nombre_canal", "likes_video", "hashtags_video", 
            "enlace_video", "numero_visualizaciones_video", "search_keyword", "keyword_languages"
        ])
        print(f"✅ CSV creado en: {output_file}")
        for keyword in keywords:
            languages = search_form_lang_map.get(keyword, [])
            print(f"🔹 Buscando videos para: {keyword}")
            query = preparar_query_youtube(keyword)
            print(f"   Query preparada: {query}")
            # 1. Búsqueda Optimizada por Fecha (Ahorra API)
            videos = search_videos(query, start_date, end_date, max_pages=1)# OJO AUMENTAR A 50 PARA PRODUCCIÓN

            if not videos:
                print("   No se encontraron videos en ese rango de fechas.")
                continue
            
            print(f"   --> Procesando {len(videos)} videos potenciales...")

            for vid in videos:
                vid_id = vid["videoId"]
                detalles = get_video_details(vid_id)
                
                if not detalles: continue

                # Preparar textos para contexto
                titulo_v = detalles["titulo"]
                descripcion_v = detalles["descripcion"] or ""
                texto_video_completo = titulo_v + " " + descripcion_v

                # Descargar comentarios
                comments = get_video_comments(vid_id)
                if not comments: continue

                for c in comments:
                    
                    # 2. FILTRO FECHA COMENTARIO (ESTRICTO)
                    fecha_str = c.get("fecha")
                    try:
                        # Parsear fecha formato ISO 8601
                        fecha_com_dt = datetime.strptime(fecha_str, "%Y-%m-%dT%H:%M:%SZ")
                    except:
                        continue # Si la fecha viene mal, ignorar
                    
                    if not (start_date <= fecha_com_dt <= end_date):
                        # Ignorar comentario fuera de fecha
                        continue

                    # 3. FILTRO DE CONTENIDO (CONTEXTO TOTAL)
                    contenido_c = c.get("contenido") or ""
                    
                    # Contexto: Título + Descripción + Comentario
                    texto_contexto = texto_video_completo + " " + contenido_c

                    if pasa_filtro_contenido(texto_contexto, keyword):
                        
                        EnlaceOriginal = f"https://www.youtube.com/watch?v={vid_id}"
                        
                        fila = [
                            titulo_v,         
                            descripcion_v,                
                            c.get("autor"),             
                            contenido_c,         
                            fecha_str,     
                            vid_id,
                            detalles["fecha_publicacion"], 
                            c.get("num_respuestas"),
                            c.get("likes"),
                            detalles["canal_publica"],
                            detalles["num_likes"],
                            detalles["tags"],
                            EnlaceOriginal,
                            detalles["num_visualizaciones"],
                            keyword,
                            ",".join(languages)
                        ]
                        writer.writerow(fila)
    
    print(f"\n✅ CSV YouTube guardado en: {output_file}")