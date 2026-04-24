# youtube_scraper2.py - VERSIÓN CORREGIDA

import sys
import os
from pathlib import Path
root_path = str(Path(__file__).resolve().parents[2])
if root_path not in sys.path:
    sys.path.insert(0, root_path)

import clean_project.config.settings as config
import csv
import time
import re
import pandas as pd
import numpy as np
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi
import json
import hashlib

# ===========================================================================
# 1. TRANSCRIPCIÓN DE VIDEO
# ===========================================================================

def get_video_transcript(video_id, return_data=False):
    ytt_api = YouTubeTranscriptApi()
    try:
        transcript_list = ytt_api.list(video_id)
    except Exception as e:
        print(f"⚠️ No hay transcripción para {video_id}: {e}")
        return ("", "") if return_data else ""

    transcript = None

    # 1. Español MANUAL
    try:
        transcript = transcript_list.find_manually_created_transcript(['es'])
        print("✅ ES manual")
    except:
        pass

    # 2. Español AUTOMÁTICO
    if not transcript:
        try:
            transcript = transcript_list.find_generated_transcript(['es'])
            print("🤖 ES automático")
        except:
            pass

    # 3. Traducido a español
    if not transcript:
        try:
            base = next(t for t in transcript_list if t.is_translatable)
            transcript = base.translate('es')
            print(f"🌐 Traducido desde {base.language_code} → ES")
        except:
            pass

    # 4. Original (fallback)
    if not transcript:
        try:
            transcript = next(iter(transcript_list))
            print(f"🌍 Original: {transcript.language_code}")
        except:
            return ("", "") if return_data else ""

    # FETCH + LIMPIEZA
    data = transcript.fetch()
    text = " ".join(snippet.text for snippet in data)
    
    # Limpieza
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'[♪♫]+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    if return_data:
        return data, text
    return text

def save_transcript(video_id, data, base_folder):
    transcripts_folder = Path(base_folder) / "transcripts"
    transcripts_folder.mkdir(parents=True, exist_ok=True)
    path = transcripts_folder / f"{video_id}.json"
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            [{"text": s.text, "start": s.start, "duration": s.duration} for s in data],
            f, ensure_ascii=False, indent=2
        )
    return str(path)

# ===========================================================================
# 2. CONFIGURACIÓN API DE YOUTUBE (CORREGIDO)
# ===========================================================================

class YouTubeAPIManager:
    """Gestor de API Keys de YouTube con manejo de cuota"""
    
    def __init__(self, api_keys):
        self.api_keys = api_keys
        self.current_index = 0
        self.exceeded = [False] * len(api_keys)
        self.youtube = self._build_service()
    
    def _build_service(self):
        return build("youtube", "v3", developerKey=self.api_keys[self.current_index])
    
    def switch_key(self):
        """Cambia a la siguiente API key disponible"""
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        print(f"🔑 Cambiando a API Key {self.current_index + 1}")
        self.youtube = self._build_service()
    
    def mark_exceeded(self):
        """Marca la key actual como excedida"""
        self.exceeded[self.current_index] = True
    
    def all_exceeded(self):
        """Verifica si todas las keys se agotaron"""
        return all(self.exceeded)
    
    def get_service(self):
        return self.youtube

# ===========================================================================
# 3. FUNCIONES DE BÚSQUEDA Y FILTRADO
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
    """Prepara query con comillas para búsqueda exacta"""
    palabras = keyword.strip().split()
    return " ".join(f'"{p}"' for p in palabras) if len(palabras) > 1 else f'"{keyword}"'

def search_videos(api_manager, keyword, start_dt, end_dt, max_pages=1):
    """Busca videos con manejo de cuota de API"""
    videos = []
    next_page_token = None
    rfc_start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    rfc_end = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    for _ in range(max_pages):
        try:
            youtube = api_manager.get_service()
            response = youtube.search().list(
                part="snippet",
                q=keyword,
                type="video",
                order="date",
                publishedAfter=rfc_start,
                publishedBefore=rfc_end,
                maxResults=50,
                regionCode="ES",
                relevanceLanguage="es",
                pageToken=next_page_token
            ).execute()
            
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                print("⚠️ Quota alcanzada, cambiando key...")
                api_manager.mark_exceeded()
                if api_manager.all_exceeded():
                    print("❌ TODAS las API Keys agotadas")
                    return None
                api_manager.switch_key()
                return search_videos(api_manager, keyword, start_dt, end_dt, max_pages)
            else:
                print(f"❌ Error en búsqueda: {e}")
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

def get_video_details(api_manager, video_id):
    """Obtiene detalles del video"""
    try:
        youtube = api_manager.get_service()
        response = youtube.videos().list(
            part="snippet,statistics",
            id=video_id
        ).execute()
        
        if not response["items"]:
            return None
            
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
    except Exception as e:
        print(f"Error obteniendo detalles: {e}")
        return None

def get_video_comments(api_manager, video_id):
    """Obtiene comentarios del video (solo top-level)"""
    comments = []
    next_page_token = None
    
    try:
        while True:
            youtube = api_manager.get_service()
            response = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                textFormat="plainText",
                pageToken=next_page_token
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
            if not next_page_token:
                break
                
    except HttpError as e:
        if e.resp.status in [403, 404]:
            # Comentarios desactivados
            return []
        print(f"Error obteniendo comentarios: {e}")
        return []
    except Exception as e:
        print(f"Error inesperado en comentarios: {e}")
        return []
        
    return comments

# ===========================================================================
# 4. FILTRO LLM DE RELEVANCIA
# ===========================================================================

def check_relevance_llm(text, tema, desc_tema, keywords, geo_scope, languages):
    """
    Verifica si el contenido es relevante usando LLM.
    PLACEHOLDER: Implementar con vLLM real.
    """
    import ollama
    
    prompt = f"""Eres un filtro de relevancia.

**TEMA DE ANÁLISIS**: {tema}
**DESCRIPCIÓN DEL TEMA**: {desc_tema}
**ÁMBITO GEOGRÁFICO**: {geo_scope}
**IDIOMAS PERMITIDOS**:  {', '.join(languages)}
**KEYWORDS DE REFERENCIA**: {', '.join(keywords)}

**TEXTO**:
{text[:1000]}

**TAREA**: Determinar si este post/video es relevante para el análisis.

**CRITERIOS DE RELEVANCIA** (Deben cumplirse TODOS):

1. **IDIOMA**: El texto está principalmente en uno de los idiomas permitidos
2. **GEOGRAFÍA**: NO hay referencia fuera del ámbito geográfico (modismos correspondientes fuera de la región, referencias culturales, etc)
3. **TEMA**: El contenido se relaciona directamente con "{tema}"  cuya descripción es "{desc_tema}"
   - El post menciona explícitamente el tema o sus componentes clave
   - NO es solo una mención tangencial o indirecta
   
**CRITERIOS DE EXCLUSIÓN AUTOMÁTICA**:
- spam evidente
- Idioma totalmente diferente a los permitidos
- Sin relación alguna con {tema}
- Hay referencia implícita en el contexto o explícita en el contenido fuera del ámbito geográfico

**INSTRUCCIONES**:
- Sé PERMISIVO: En caso de duda razonable, marca como relevante
- Busca la intención: ¿Este post aporta algo al análisis de opinión sobre {tema}?
- Un post con opinión sobre {tema} es SIEMPRE relevante, incluso si parece noticia

**FORMATO DE SALIDA** (JSON):
{{
  "es_relevante": true o false,
  "confianza": 0.0-1.0,
  "razon": "breve explicación de 1-2 líneas"
}}

Responde SOLO con el JSON, sin texto adicional."""

    try:
        response = ollama.chat(
            model="Qwen/Qwen2.5-14B-Instruct",
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.0}
        )

        raw = response.choices[0].message.content
        data = json.loads(raw)
        
        return (
            data.get("es_relevante", False),
            data.get("confianza", 0.0),
            data.get("razon", "Sin razón")
        )
        
    except Exception as e:
        print(f"❌ Error en filtro LLM: {e}")
        # En caso de error, marcamos como relevante para no perder datos
        return (True, 0.0, f"Error: {str(e)}")
        

# ===========================================================================
# 5. SCRAPER PRINCIPAL
# ===========================================================================

def run_youtube(config):
    """Scraper principal de YouTube con filtro LLM"""
    print("🎥 YouTube SCRAPER INICIADO (CON FILTRO LLM)")
    
    # Fechas
    start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d")
    end_date = datetime.strptime(config.general["end_date"], "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    
    # Keywords y configuración
    keywords = config.scraping["youtube"]["query"]
    search_form_lang_map = config.general.get("search_form_lang_map", {})
    tema = getattr(config, 'tema', 'Análisis General')
    geo_scope = getattr(config, 'geo_scope', 'España')
    desc_tema = getattr(config, 'desc_tema', '')
    languages = getattr(config, 'languages', [])
    
    # Output
    output_folder = config.general["output_folder"]
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/youtube_global_dataset.csv"
    
    # Inicializar API Manager
    api_keys = [
        config.CREDENTIALS["youtube"]["API_KEY_YOUTUBE"],
        config.CREDENTIALS["youtube"]["API_KEY_YOUTUBE2"],
        config.CREDENTIALS["youtube"]["API_KEY_YOUTUBE3"]
    ]
    api_manager = YouTubeAPIManager(api_keys)
    
    # IDs vistos (deduplicación)
    seen_ids = set()
    
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
            "tipo", "titulo_video", "descripcion_video", "transcripcion_path",
            "usuario_comentario", "contenido", "fecha_comentario",
            "id_video", "fecha_publicacion_video", "numero_respuestas_al_comentario",
            "likes_comentario", "nombre_canal", "likes_video", "hashtags_video",
            "enlace_video", "numero_visualizaciones_video", "num_comentarios_video",
            "search_keyword", "keyword_languages", "usuario_hash", "llm_relevante"
        ])
        
        for keyword in keywords:
            languages = search_form_lang_map.get(keyword, [])
            print(f"\n🔹 Buscando videos para: {keyword}")
            
            query = preparar_query_youtube(keyword)
            videos = search_videos(api_manager, query, start_date, end_date, max_pages=10)
            
            if videos is None:
                print("❌ Error de cuota, finalizando...")
                break
            if not videos:
                print("⚠️ No se encontraron videos")
                continue
            
            print(f"   📹 Procesando {len(videos)} videos...")
            
            for vid in videos:
                stats["videos_encontrados"] += 1
                vid_id = vid["videoId"]
                
                detalles = get_video_details(api_manager, vid_id)
                if not detalles:
                    continue
                
                titulo = detalles["titulo"]
                descripcion = detalles["descripcion"] or ""
                texto_completo = f"{titulo} {descripcion}"
                
                # ===================================================================
                # FILTRO LLM DE RELEVANCIA
                # ===================================================================
                print(f"\n🤖 Verificando relevancia: {titulo[:60]}...")
                
                es_relevante, confianza, razon = check_relevance_llm(
                    text=texto_completo,
                    tema=tema,
                    keywords=[keyword],
                    geo_scope=geo_scope,
                    languages=languages
                )
                
                if not es_relevante:
                    print(f"  ⏭️  Video NO relevante. Saltando.")
                    stats["videos_filtrados"] += 1
                    continue
                
                print(f"  ✅ Video RELEVANTE. Descargando comentarios...")
                stats["videos_relevantes"] += 1
                # ===================================================================
                
                # Obtener transcripción
                transcript_path = ""
                try:
                    data, text_trans = get_video_transcript(vid_id, return_data=True)
                    if data:
                        transcript_path = save_transcript(vid_id, data, output_folder)
                except:
                    pass
                
                enlace = f"https://www.youtube.com/watch?v={vid_id}"
                
                # Hash del canal
                canal_hash = hashlib.sha256(
                    detalles["canal_publica"].encode()
                ).hexdigest()[:16]
                
                # Guardar fila de VIDEO
                if (vid_id, "VIDEO") not in seen_ids:
                    writer.writerow([
                        "VIDEO", titulo, descripcion, transcript_path,
                        detalles["canal_publica"], descripcion[:200],
                        detalles["fecha_publicacion"], vid_id,
                        detalles["fecha_publicacion"], 0, 0,
                        detalles["canal_publica"], detalles["num_likes"],
                        str(detalles["tags"]), enlace,
                        detalles["num_visualizaciones"],
                        detalles["num_comentarios"], keyword,
                        ",".join(languages), canal_hash, "SI"
                    ])
                    seen_ids.add((vid_id, "VIDEO"))
                
                # Obtener comentarios
                comments = get_video_comments(api_manager, vid_id)
                
                for c in comments:
                    # Filtro de fecha
                    try:
                        fecha_com = datetime.strptime(c["fecha"], "%Y-%m-%dT%H:%M:%SZ")
                    except:
                        continue
                    
                    if not (start_date <= fecha_com <= end_date):
                        continue
                    
                    # Hash del usuario
                    usuario_hash = hashlib.sha256(
                        c["autor"].encode()
                    ).hexdigest()[:16]
                    
                    writer.writerow([
                        "COMENTARIO", titulo, descripcion, "",
                        c["autor"], c["contenido"], c["fecha"],
                        vid_id, detalles["fecha_publicacion"],
                        c["num_respuestas"], c["likes"],
                        detalles["canal_publica"], detalles["num_likes"],
                        str(detalles["tags"]), enlace,
                        detalles["num_visualizaciones"],
                        detalles["num_comentarios"], keyword,
                        ",".join(languages), usuario_hash, "PENDIENTE"
                    ])
                    stats["comentarios_guardados"] += 1
    
    print(f"\n✅ YouTube completado: {output_file}")
    print(f"\n📊 ESTADÍSTICAS:")
    print(f"  Videos encontrados: {stats['videos_encontrados']}")
    print(f"  Videos relevantes: {stats['videos_relevantes']}")
    print(f"  Videos filtrados: {stats['videos_filtrados']}")
    print(f"  Comentarios guardados: {stats['comentarios_guardados']}")

# ===========================================================================
# DEBUG
# ===========================================================================

if __name__ == "__main__":
    from types import SimpleNamespace
    
    mock_config = SimpleNamespace(
        general={
            "start_date": "2026-04-01",
            "end_date": "2026-04-24",
            "output_folder": "./test_youtube",
            "search_form_lang_map": {"transporte público valencia": ["Castellano"]}
        },
        scraping={
            "youtube": {"query": ["transporte público valencia"]}
        },
        CREDENTIALS=config.CREDENTIALS,
        tema="Transporte público",
        geo_scope="Valencia"
    )
    
    run_youtube(mock_config)