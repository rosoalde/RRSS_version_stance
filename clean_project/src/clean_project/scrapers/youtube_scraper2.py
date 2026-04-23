import sys
import os
from pathlib import Path

# Detectar la ruta de la carpeta 'src' (subiendo 2 niveles desde scrapers/)
# Archivo: .../src/clean_project/scrapers/youtube_scraper2.py
# parents[0] = scrapers, parents[1] = clean_project, parents[2] = src
root_path = str(Path(__file__).resolve().parents[2])

if root_path not in sys.path:
    sys.path.insert(0, root_path)
import clean_project.config.settings as config
import csv
import time
import re
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi

# ===========================================================================
# 1. CONFIGURACIÓN Y FUNCIONES DE APOYO
# ===========================================================================

from youtube_transcript_api import YouTubeTranscriptApi

def get_video_transcript(video_id, return_data=False):
    ytt_api = YouTubeTranscriptApi()
    transcript_list = ytt_api.list(video_id)

    transcript = None

    # =========================
    # 1. 🥇 Español MANUAL
    # =========================
    try:
        transcript = transcript_list.find_manually_created_transcript(['es'])
        print("✅ ES manual")
    except:
        pass

    # =========================
    # 2. 🥈 Español AUTOMÁTICO (no manual)
    # =========================
    if not transcript:
        try:
            transcript = transcript_list.find_generated_transcript(['es'])
            print("🤖 ES automático")
        except:
            pass

    # =========================
    # 3. 🥉 Traducido a español
    # =========================
    if not transcript:
        try:
            # coger cualquiera que se pueda traducir
            base = next(t for t in transcript_list if t.is_translatable)
            transcript = base.translate('es')
            print(f"🌐 Traducido desde {base.language_code} → ES")
        except:
            pass

    # =========================
    # 4. 🌍 Original (fallback final)
    # =========================
    if not transcript:
        transcript = next(iter(transcript_list))
        print(f"🌍 Original: {transcript.language_code}")

    # =========================
    # FETCH + LIMPIEZA
    # =========================
    data = transcript.fetch()

    # 🔥 usar .text (no ['text'])
    text = " ".join(snippet.text for snippet in data)

    # =========================
    # 🧹 LIMPIEZA PRO
    # =========================

    # eliminar cosas tipo [Música], [Aplausos], etc
    text = re.sub(r'\[.*?\]', '', text)

    # eliminar (Música), (Risas), etc
    text = re.sub(r'\(.*?\)', '', text)

    # eliminar caracteres raros tipo ♪ ♫
    text = re.sub(r'[♪♫]+', '', text)

    # normalizar espacios
    text = re.sub(r'\s+', ' ', text).strip()
    if return_data:
        return data, text


    return text

import json
from pathlib import Path

def save_transcript(video_id, data, base_folder):
    transcripts_folder = Path(base_folder) / "transcripts"
    transcripts_folder.mkdir(parents=True, exist_ok=True)

    path = transcripts_folder / f"{video_id}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "text": s.text,
                    "start": s.start,
                    "duration": s.duration
                }
                for s in data
            ],
            f,
            ensure_ascii=False,
            indent=2
        )

    return str(path)

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
# 2. LÓGICA DE FILTRADO Y BÚSQUEDA
# ===========================================================================

def pasa_filtro_contenido(texto, keyword_query):
    if not texto:
        return False
    texto_norm = texto.lower()
    query_clean = keyword_query.replace('"', '').lower()
    palabras_clave = [p.replace('*', '') for p in query_clean.split()]
    for palabra in palabras_clave:
        patron = r'(?:^|\W)#?' + re.escape(palabra) + r'\w*'
        if not re.search(patron, texto_norm):
            return False
    return True

def preparar_query_youtube(keyword):
    palabras = keyword.strip().split()
    return " ".join(f'"{p}"' for p in palabras) if len(palabras) > 1 else f'"{keyword}"'

def search_videos(keyword, start_dt, end_dt, max_pages=1):
    global api_keys_exceeded, youtube
    videos = []
    next_page_token = None
    rfc_start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    rfc_end   = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    for _ in range(max_pages):
        try:
            response = youtube.search().list(
                part="snippet", q=keyword, type="video", order="date",
                publishedAfter=rfc_start, publishedBefore=rfc_end,
                maxResults=50, regionCode="ES", relevanceLanguage="es",
                pageToken=next_page_token
            ).execute()
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                api_keys_exceeded[current_api_key_index] = True
                if all(api_keys_exceeded): return None
                switch_api_key()
                return search_videos(keyword, start_dt, end_dt, max_pages)
            return []

        items = response.get("items", [])
        if not items: break
        for item in items:
            videos.append({"videoId": item["id"]["videoId"], "title": item["snippet"]["title"]})
        next_page_token = response.get("nextPageToken")
        if not next_page_token: break
    return videos

def get_video_details(video_id):
    try:
        response = youtube.videos().list(part="snippet,statistics", id=video_id).execute()
        if not response["items"]: return None
        video = response["items"][0]
        return {
            "titulo": video["snippet"].get("title"),
            "descripcion": video["snippet"].get("description"),
            "fecha_publicacion": video["snippet"].get("publishedAt"),
            "num_comentarios": video["statistics"].get("commentCount", 0),
            "num_likes": video["statistics"].get("likeCount", 0),
            "num_visualizaciones": video["statistics"].get("viewCount", 0),
            "canal_publica": video["snippet"].get("channelTitle"),
            "tags": video["snippet"].get("tags", [])
        }
    except: return None

def get_video_comments(video_id):
    comments = []
    next_page_token = None
    try:
        while True:
            response = youtube.commentThreads().list(
                part="snippet", videoId=video_id, maxResults=100, textFormat="plainText", pageToken=next_page_token
            ).execute()
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
            if not next_page_token: break
    except: pass
    return comments

# ===========================================================================
# 3. SCRAPER PRINCIPAL
# ===========================================================================

def run_youtube(config):
    print("YouTube SCRAPER INICIADO")
    start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d")
    end_date   = datetime.strptime(config.general["end_date"], "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    
    keywords = config.scraping["youtube"]["query"]
    search_form_lang_map = config.general.get("search_form_lang_map", {})
    output_folder = config.general["output_folder"]
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/youtube_global_dataset.csv"

    seen_ids = set() # Para deduplicación

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=';') 
        writer.writerow([
            "tipo", "titulo_video", "descripcion_video", "transcripcion_video",
            "usuario_comentario", "contenido", "fecha_comentario", 
            "id_video", "fecha_publicacion_video", "numero_respuestas_al_comentario", 
            "likes_comentario", "nombre_canal", "likes_video", "hashtags_video", 
            "enlace_video", "numero_visualizaciones_video", "num_comentarios_video",
            "search_keyword", "keyword_languages"
        ])

        for keyword in keywords:
            languages = search_form_lang_map.get(keyword, [])
            query = preparar_query_youtube(keyword)
            videos = search_videos(query, start_date, end_date, max_pages=1)
            if not videos: continue

            for vid in videos:
                vid_id = vid["videoId"]
                detalles = get_video_details(vid_id)
                if not detalles: continue
                enlace_v = f"https://www.youtube.com/watch?v={vid_id}"
                # --- A. DEDUPLICACIÓN Y FILA DE VIDEO ---
                if (vid_id, "VIDEO_ROOT") not in seen_ids:
                    data, text = get_video_transcript(vid_id, return_data=True)
                    if data:
                        path = save_transcript(vid_id, data, output_folder)
                    else:
                        path = ""
                    writer.writerow([
                        "VIDEO", detalles["titulo"], detalles["descripcion"], path,
                        detalles["canal_publica"], detalles["descripcion"][:200], detalles["fecha_publicacion"],
                        vid_id, detalles["fecha_publicacion"], 0, 0,
                        detalles["canal_publica"], detalles["num_likes"], detalles["tags"],
                        enlace_v, detalles["num_visualizaciones"],
                        detalles["num_comentarios"], keyword, ",".join(languages)
                    ])
                    seen_ids.add((vid_id, "VIDEO_ROOT"))

                # --- B. PROCESAR COMENTARIOS ---
                comments = get_video_comments(vid_id)
                for c in comments:
                    # Deduplicación de comentario por contenido
                    # comment_key = (vid_id, c.get("contenido"))
                    # if comment_key in seen_ids: continue
                    
                    # try:
                    #     fecha_com_dt = datetime.strptime(c.get("fecha"), "%Y-%m-%dT%H:%M:%SZ")
                    # except: continue
                    
                    # if not (start_date <= fecha_com_dt <= end_date): continue

                    # if pasa_filtro_contenido(detalles["titulo"] + " " + c.get("contenido"), keyword):
                    writer.writerow([
                        "COMENTARIO", detalles["titulo"], detalles["descripcion"], "",
                        c.get("autor"), c.get("contenido"), c.get("fecha"),
                        vid_id, detalles["fecha_publicacion"], c.get("num_respuestas"),
                        c.get("likes"), detalles["canal_publica"], detalles["num_likes"],
                        detalles["tags"], f"https://www.youtube.com/watch?v={vid_id}",
                        detalles["num_visualizaciones"], detalles["num_comentarios"],
                        keyword, ",".join(languages)
                    ])
                        # seen_ids.add(comment_key)
    
    print(f"✅ Proceso completado. Archivo guardado en: {output_file}")

# ===========================================================================
# 4. BLOQUE DE EJECUCIÓN AISLADA (DEBUG)
# ===========================================================================

if __name__ == "__main__":
    from types import SimpleNamespace
    
    # Configuración de prueba manual
    mock_config = SimpleNamespace(
        general={
            "start_date": "2025-10-01",
            "end_date": "2026-04-20",
            "output_folder": "./test_youtube_results",
            "search_form_lang_map": {"Sagunto": ["Castellano"]}
        },
        scraping={
            "youtube": {"query": ["Sagunto"]}
        },
        CREDENTIALS=config.CREDENTIALS 
    )
    
    run_youtube(mock_config)