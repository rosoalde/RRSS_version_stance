import clean_project.config.settings as config
import requests
import csv
import time
from pathlib import Path
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

"""La API devuelve resultados basados en relevancia y contexto, no en coincidencia exacta de palabras clave.

👉 Puede devolver vídeos que:

Tienen términos relacionados o parecidos

Son populares para ese tema

Incluyen información contextual sobre el tema aunque no aparezcan literalmente todas las palabras clave

Están asociados con términos relacionados en metadata o etiquetas internas

Es decir, YouTube evalúa semántica y relevancia más que coincidencia literal de texto. 

El scraper recoge vídeos que mencionan los términos establecidos o contextos similares aunque el título exacto no sea el mismo."""

# Convertir fechas de configuración
start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d")
end_date_raw   = datetime.strptime(config.general["end_date"], "%Y-%m-%d")
end_date = end_date_raw.replace(hour=23, minute=59, second=59)
# Definir las claves de API disponibles
api_keys = [
    config.CREDENTIALS["youtube"]["API_KEY_YOUTUBE"],
    config.CREDENTIALS["youtube"]["API_KEY_YOUTUBE2"]
]

def parse_fecha_tweet(fecha_str):
    """
    Convierte 'Nov 14, 2021 · 12:27 PM UTC' → date
    """
    try:
        fecha_limpia = fecha_str.replace(" UTC", "")
        dt = datetime.strptime(fecha_limpia, "%b %d, %Y · %I:%M %p")
        return dt.date()
    except Exception:
        return None
    
# Inicializar la variable de índice de la API Key actual
current_api_key_index = 0

# Función para cambiar la clave de API si la actual alcanza su cuota
def switch_api_key():
    global current_api_key_index
    current_api_key_index = (current_api_key_index + 1) % len(api_keys)
    print(f"🔑 Cambiando a la API Key {current_api_key_index + 1}")

# Inicializar la conexión a YouTube con la clave de API actual
def get_youtube_service():
    return build("youtube", "v3", developerKey=api_keys[current_api_key_index])
# youtube = build("youtube", "v3", developerKey=config.CREDENTIALS["youtube"]["API_KEY_YOUTUBE"])

youtube = get_youtube_service()
regionCode_0 = "ES"
relevanceLanguage_0 = "es"
# Variable para detectar si ambas claves han excedido su cuota
api_keys_exceeded = [False, False]
def search_videos(keyword, max_pages=10):
    global api_keys_exceeded
    global youtube  # <--- 🔴 CORRECCIÓN IMPORTANTE: Permite modificar la variable global
    videos = []
    next_page_token = None

    for _ in range(max_pages):  # máximo 10 → 500 vídeos
        try:
            response = youtube.search().list(
                part="snippet",
                q=keyword,
                type="video",
                maxResults=50,
                regionCode=regionCode_0,
                relevanceLanguage=relevanceLanguage_0,
                pageToken=next_page_token
            ).execute()
        except HttpError as e:
            # Si alcanzamos la cuota, cambiamos de clave de API
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                print("⚠️ Quota alcanzada para la API Key actual. Cambiando a la siguiente API Key...")
                switch_api_key()
                youtube = get_youtube_service()  # Reconectar con la nueva clave

                # Marcar la API como agotada
                api_keys_exceeded[current_api_key_index] = True

                # Verificar si ambas claves de API han excedido la cuota
                if all(api_keys_exceeded):
                    print("⚠️ Ambas claves de API han excedido la cuota. Terminando la búsqueda de videos.")
                    return None  # Retornar None para indicar que no hay más resultados disponibles

                return search_videos(keyword, max_pages)  # Volver a intentar la búsqueda con la nueva API Key
            else:
                print(f"Error al ejecutar la solicitud: {e}")
                return []  # Si el error no es de cuota, devolvemos lista vacía

        for item in response.get("items", []):
            videos.append({
                "videoId": item["id"]["videoId"],
                "title": item["snippet"]["title"]
            })

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    return videos

### ------------------------------------------------------------------
def preparar_query_youtube(keyword):
    """
    Convierte una keyword configurable en una query más estricta para YouTube.
    """
    palabras = keyword.strip().split()

    # si es una sola palabra o una frase corta, usar comillas por palabra
    if len(palabras) > 1:
        return " ".join(f'"{p}"' for p in palabras)
    else:
        return f'"{keyword}"'
### ------------------------------------------------------------------

def get_video_details(video_id):
    """Devuelve detalles completos del video."""
    response = youtube.videos().list(
        part="snippet,statistics",
        id=video_id
    ).execute()

    if not response["items"]:
        return None

    video = response["items"][0]
    snippet = video["snippet"]
    stats = video["statistics"]

    channel_id = snippet["channelId"]

    channel_info = youtube.channels().list(                                                 #info del canal
        part="statistics",
        id=channel_id
    ).execute()

    

    channel_info = youtube.channels().list(
        part="statistics",
        id=channel_id
    ).execute()

    subscribers = 0
    if channel_info.get("items"):
        subscribers = channel_info["items"][0]["statistics"].get("subscriberCount", 0)


    return {
        "titulo": snippet.get("title"),
        "id": video_id,
        "descripcion": snippet.get("description"),
        "fecha_publicacion": snippet.get("publishedAt"),
        "num_comentarios": stats.get("commentCount", 0),
        "num_likes": stats.get("likeCount", 0),
        "num_visualizaciones": stats.get("viewCount", 0),
        "canal_publica": snippet.get("channelTitle"),
        "num_comentarios": stats.get("commentCount", 0),
        "canal_id": channel_id,
        "canal_suscriptores": subscribers,
        "tags": snippet.get("tags", [])
    }


def get_video_comments(video_id):
    comments = []
    next_page_token = None

    while True:
        try:
            response = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                textFormat="plainText",
                pageToken=next_page_token
            ).execute()

        except HttpError as e:
            # Comentarios desactivados u otros errores comunes
            if e.resp.status in [403, 404]:
                print(f"⚠️ Comentarios desactivados o inaccesibles para el video {video_id}")
                return []   # ← CLAVE: no romper el scraping
            else:
                raise e  # otros errores sí los queremos ver

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

def run_youtube(config):
    keywords = config.scraping["youtube"]["query"]
    print(f"\n KEYWORDS QUE SE VAN A BUSCAR EN YOUTUBE: {keywords}\n")
    output_folder = config.general["output_folder"]
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/youtube_global_dataset.csv"
    # Si el archivo ya existe, saltamos el scraper
    if Path(output_file).exists() and Path(output_file).stat().st_size > 0:
        print(f"⚠️ El archivo CSV de YouTube ya existe en: {output_file}. Saltando este scraper...")
        return  # Salir de la función si el archivo ya existe 
    
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=';')                                                                   # q ue el csv separe --->       ;

        writer.writerow([
            "titulo_video", "usuario_comentario",  "contenido", "fecha_comentario", "id_video", "fecha_publicacion_video", 
            "numero_respuestas_al_comentario", "likes_comentario", "numero_suscriptores_usuario_comentario", "fecha_suscripcion_usuario_comentario",
            "nombre_canal", "likes_video", "hashtags_video", "enlace_video", "numero_visualizaciones_video"
        ])

        for keyword in keywords:
            print("keyword:", keyword)
            print(f"\nBuscando videos con la palabra: {keyword}")
            query = preparar_query_youtube(keyword)
            videos = search_videos(query, max_pages=50)

            if not videos:
                print("No se encontraron videos con esa palabra clave")
                continue

            for vid in videos:
                vid_id = vid["videoId"]
                detalles_video = get_video_details(vid_id)
            
                titulo_v = detalles_video["titulo"]
                idvideo_v = detalles_video["id"]

                #descripcion_v = detalles_video["descripcion"]
                descripcion_v = None

                fecha_publicacion_v = detalles_video["fecha_publicacion"]

                fecha_video = datetime.strptime(fecha_publicacion_v, "%Y-%m-%dT%H:%M:%SZ").date()
                if not (start_date.date() <= fecha_video <= end_date.date()):
                    print(f"⚠️ Video {idvideo_v} fuera del rango de fechas, se ignora")
                    continue
                num_comentarios_v = detalles_video["num_comentarios"]
                likes_v = detalles_video["num_likes"]
                visualizaciones_v = detalles_video["num_visualizaciones"]
                canal_v = detalles_video["canal_publica"]
                canalid_v = detalles_video["canal_id"]
                numero_suscriptores_v = detalles_video["canal_suscriptores"]
                tags_v = detalles_video["tags"]

                comments = get_video_comments(vid_id)

                if not comments:
                    print("No hay comentarios para este video (según la API)")
                    continue

                for i, c in enumerate(comments, 1):

                    autor_comentario_c = c.get("autor")
                    fecha_comentario_c = c.get("fecha")
                    likes_comentario_c = c.get("likes")
                    contenido_c = c.get("contenido")
                    numero_respuestas_comentario_c = c.get("num_respuestas")
                    id_comentario_c = i

                    # Obtener datos del canal del autor del comentario
                    author_channel_id = c.get("author_channel_id")  # añadido en get_video_comments

                  
                    channel_info = {}  # valor por defecto
                    
                    Followers_c = 0
                    JoinDate_c = "!!! canal oculto"

                    if author_channel_id:
                        channel_info = youtube.channels().list(
                        part="snippet,statistics",
                        id=author_channel_id
                        ).execute()

                    if channel_info.get("items"):  # verificamos que exista items
                        channel_data = channel_info["items"][0]
                        Followers_c = channel_data["statistics"].get("subscriberCount", 0)
                        JoinDate_c = channel_data["snippet"].get("publishedAt", "")


                   
                    #EnlaceOriginal = f"https://www.youtube.com/watch?v={idvideo_v}"
                    # 🔴 CORRECCIÓN: Sintaxis de string f corregida
                    EnlaceOriginal = f"https://www.youtube.com/watch?v={vid_id}"

                    # Fila final
                    fila = [
                        titulo_v,                         
                        autor_comentario_c,             
                        contenido_c,         
                        fecha_comentario_c,     
                        idvideo_v,
                        fecha_publicacion_v, 
                        numero_respuestas_comentario_c,
                        likes_comentario_c,
                        Followers_c,
                        JoinDate_c,
                        canal_v,
                        likes_v,
                        tags_v,
                        EnlaceOriginal,
                        visualizaciones_v
                    ]

                    writer.writerow(fila)
    
    print(f"\n✅ CSV YouTube guardado en: {output_file}")



