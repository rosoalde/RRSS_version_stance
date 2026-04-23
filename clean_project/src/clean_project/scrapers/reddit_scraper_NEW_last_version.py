import csv
import re
import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime
from langdetect import detect, LangDetectException
import asyncpraw
from concurrent.futures import ThreadPoolExecutor
import numpy as np

# Calculamos la ruta a la carpeta 'src'
# Archivo actual: .../src/clean_project/scrapers/archivo.py
# parents[0] = scrapers/
# parents[1] = clean_project/
# parents[2] = src/
ruta_src = str(Path(__file__).resolve().parents[2])
if ruta_src not in sys.path:
    sys.path.insert(0, ruta_src)

import clean_project.config.settings as config

print(f"REDDIT SCRAPER OPTIMIZADO INICIADO")

# -------------------------------------------------------------------------
# FUNCIÓN DE FILTRO (Regex es rápido, se queda igual)
# -------------------------------------------------------------------------
def pasa_filtro_contenido(texto, keyword_query):
    if not texto: return False
    texto_norm = texto.lower()
    query_clean = keyword_query.replace('"', '').lower()
    palabras_clave = [p.replace('*', '') for p in query_clean.split()]
    for palabra in palabras_clave:
        patron = r'(?:^|\W)#?' + re.escape(palabra) + r'\w*'
        if not re.search(patron, texto_norm): return False
    return True

# -------------------------------------------------------------------------
# DETECCIÓN DE IDIOMA NO BLOQUEANTE
# -------------------------------------------------------------------------
# langdetect es lento y bloquea el loop async. Lo corremos en un ThreadPool.
_executor = ThreadPoolExecutor(max_workers=4)

def _detectar_idioma_sync(texto):
    try:
        return detect(texto) if len(texto.strip()) > 5 else "unknown"
    except LangDetectException:
        return "unknown"

async def detectar_idioma_async(texto):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _detectar_idioma_sync, texto)

# -------------------------------------------------------------------------
# PROCESADOR DE UNA SOLA KEYWORD (Worker)
# -------------------------------------------------------------------------
async def procesar_keyword(reddit, keyword, config, start_date, end_date, IDIOMAS, limit,global_seen_ids, semaphore):
    """
    Procesa una única keyword de principio a fin y devuelve sus filas.
    """
    async with semaphore:
        rows_keyword = []
        seen_ids = set() # Para evitar duplicados dentro de la misma keyword
        search_form_lang_map = config.general.get("search_form_lang_map", {})
        languages = search_form_lang_map.get(keyword, [])
        
        print(f"🔹 Iniciando búsqueda para: {keyword}")
        
        try:
            subreddit = await reddit.subreddit("all")
            # AsyncPRAW maneja la paginación asíncrona
            async for post in subreddit.search(keyword, limit=limit):
                if post.id in global_seen_ids:
                    continue
                print(f"keyword: {keyword}")
                print(f"limit: {limit}")
                # 1. Filtro Fecha
                await post.load() # Esto descarga toda la información que falta, incluyendo los comentarios
                
                print(f"[2] Expandiendo todos los hilos de comentarios (esto puede tardar)...")
                # Ahora que el post está cargado, replace_more ya no dará error
                await post.comments.replace_more(limit=None)
                # print(f"=================================================")    
                # print(len(post.comments))
                # print(f"=================================================")    

                fecha_post = datetime.fromtimestamp(post.created_utc)
                if not (start_date <= fecha_post <= end_date):
                    continue

                # 2. Preparar Texto
                titulo = post.title or ""
                cuerpo = post.selftext or ""
                texto_post_completo = titulo + " " + cuerpo 

                # 3. Filtro Idioma (Optimizado)
                # idioma = await detectar_idioma_async(texto_post_completo)
                # if idioma not in IDIOMAS:
                #     continue

                # 4. Procesar POST
                #if pasa_filtro_contenido(texto_post_completo, keyword):
                global_seen_ids.add(post.id) # Marcar este ID como visto a nivel global
                row_post = {
                    "post_title": titulo,
                    "post_selftext": cuerpo,
                    "usuario": post.author.name if post.author else "[deleted]",
                    "Fullname": post.author.name if post.author else "[deleted]",
                    "contenido": texto_post_completo,
                    "fecha": fecha_post.strftime("%Y-%m-%d %H:%M"),
                    "enlace": f"https://reddit.com{post.permalink}",
                    "TipoDeTweet": "Post",
                    "UsuarioOriginal": "", 
                    "EnlaceOriginal": "",
                    "comments": post.num_comments,
                    "retweets": np.nan, 
                    "quotes": np.nan,
                    "hearts": post.score, 
                    "Likes": post.score,
                    "Followers": "", 
                    "Following": "", 
                    "Tweets": "", 
                    "Bio": "", 
                    "Ubicacion": "", "JoinDate": "", 
                    "Website": "", 
                    "IsVerified": "", 
                    "IsProtected": "", 
                    "plays": np.nan, 
                    "search_keyword": keyword,
                    "keyword_languages": ",".join(languages)
                }
                # if post.id not in seen_ids:
                #     seen_ids.add(post.id)
                rows_keyword.append(row_post)

                # 5. Procesar COMENTARIOS
                # Solo cargamos comentarios si el post pasó los filtros básicos de fecha/idioma
                try:
                    # replace_more(limit=0) es lo más eficiente (solo top level, sin sub-hilos profundos)
                    await post.comments.replace_more(limit=0)
                    comments_list = post.comments.list()
                except Exception:
                    comments_list = []

                for comment in post.comments:
                    fecha_com = datetime.fromtimestamp(comment.created_utc)
                    if not (start_date <= fecha_com <= end_date):
                        continue

                    texto_comentario = comment.body or ""
                    texto_contexto_completo = texto_post_completo + " " + texto_comentario

                    #if pasa_filtro_contenido(texto_contexto_completo, keyword):
                    row_comment = {
                        "post_title": titulo,
                        "post_selftext": cuerpo,
                        "usuario": comment.author.name if comment.author else "[deleted]",
                        "Fullname": comment.author.name if comment.author else "[deleted]",
                        "contenido": texto_comentario,
                        "fecha": fecha_com.strftime("%Y-%m-%d %H:%M"),
                        "enlace": f"https://reddit.com{post.permalink}",
                        "TipoDeTweet": "Comentario",
                        "UsuarioOriginal": post.author.name if post.author else "[deleted]",
                        "EnlaceOriginal": f"https://reddit.com{post.permalink}",
                        "comments": "", 
                        "retweets": "", "quotes": "",
                        "hearts": comment.score, 
                        "Likes": comment.score,
                        "Followers": "", "Following": "", "Tweets": "", "Bio": "",
                        "Ubicacion": "", "JoinDate": "", "Website": "",
                        "IsVerified": "", "IsProtected": "", 
                        "plays": np.nan, 
                        "search_keyword": keyword,
                        "keyword_languages": ",".join(languages)
                    }
                    # Usamos ID del comentario para evitar duplicados
                    # if comment.id not in seen_ids:
                    #     seen_ids.add(comment.id)
                    rows_keyword.append(row_comment)
                
                # Pequeña pausa NO BLOQUEANTE para ser amables con la API
                await asyncio.sleep(0.1) 

        except Exception as e:
            print(f"⚠️ Error buscando keyword '{keyword}': {e}")
        
    print(f"✅ Fin búsqueda '{keyword}': {len(rows_keyword)} items encontrados.")
    return rows_keyword

# -------------------------------------------------------------------------
# SCRAPER PRINCIPAL
# -------------------------------------------------------------------------
async def run_reddit(config):
    output_folder = config.general["output_folder"]
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/reddit_global_dataset.csv"

    if Path(output_file).exists() and Path(output_file).stat().st_size > 0:
        print(f"⚠️ El archivo CSV de Reddit ya existe. Saltando...")
        return
    global_seen_ids = set()
    semaphore = asyncio.Semaphore(5)
    keywords = config.scraping["reddit"]["query"]
    limit = config.scraping["reddit"].get("limit", None)
    start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d")
    end_date_raw = datetime.strptime(config.general["end_date"], "%Y-%m-%d")
    end_date = end_date_raw.replace(hour=23, minute=59, second=59)
    
    print(f"📅 Rango: {start_date} <--> {end_date}")
    IDIOMAS = ["en", "es", "ca", "eu", "pt", "fr","gl", "it"]

    all_rows = []
    
    # Iniciamos cliente AsyncPRAW
    async with asyncpraw.Reddit(
            client_id=config.CREDENTIALS["reddit"]["reddit_client_id"],
            client_secret=config.CREDENTIALS["reddit"]["reddit_client_secret"],
            user_agent="SpainUserCollector/1.0"
        ) as reddit:
        
        # 🚀 PARALELISMO REAL: Creamos una tarea por cada keyword
        # tasks = [
        #     procesar_keyword(reddit, kw, config, start_date, end_date, IDIOMAS, limit) 
        #     for kw in keywords
        # ]
        
        # print(f"🚀 Lanzando {len(tasks)} tareas de búsqueda simultáneas...")
        for kw in keywords:
            res = await procesar_keyword(reddit, kw, config, start_date, end_date, IDIOMAS, limit, global_seen_ids, semaphore) 

        # Esperamos a que todas terminen y recolectamos resultados
        # resultados_listas = await asyncio.gather(*tasks)
        
        # Aplanamos la lista de listas
        # for lista in resultados_listas:
        #     all_rows.extend(lista)
        all_rows.extend(res)
    # Guardar CSV
    if all_rows:
        fieldnames = list(all_rows[0].keys())
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\n✅ CSV Reddit guardado en: {output_file} ({len(all_rows)} filas)")
    else:
        print("\n⚠️ No se encontraron resultados en Reddit.")

    return all_rows



# -------------------------------------------------------------------------
#  DEBUG MANUAL (ACTUALIZADO CON CONFIG DE ROSALÍA)
# -------------------------------------------------------------------------
if __name__ == "__main__":
    from types import SimpleNamespace
    import asyncio
    
    # 🎮 CONFIGURACIÓN REPLICADA DEL LOG
    DEBUG_CONFIG = SimpleNamespace(
        general={
            'start_date': '2025-11-25',
            'end_date': '2025-11-27',
            'output_folder': '/home/rrss/proyecto_web/debug_reddit', # Puedes cambiar esto a la ruta real si prefieres
            'tema': 'rosalia lux tour',
            'languages': ['Castellano', 'Catalan', 'Euskera', 'Ingles', 'Italiano', 'Portugues', 'Frances'],
            'search_form_lang_map': {
                'Rosalia Lux Tour Madrid': ['Castellano'], 
                'Concierto Rosalia Lux': ['Castellano'], 
                'Entradas Rosalia Lux': ['Castellano'], 
                'Rosalia Lux Barcelona': ['Castellano'], 
                'Fotos Rosalia Lux Tour': ['Castellano'], 
                'Rosalia Lux': ['Catalan'], 
                'concert Rosalia': ['Catalan, Français, Portugues'], 
                'Lux tour': ['Catalan'], 
                'fotos Rosalia Lux': ['Catalan'], 
                'venda Rosalia': ['Catalan, Portugues'], 
                'Rosalia Lux Tour': ['Euskera'], 
                'concertu Rosalia': ['Euskera'], 
                'fotiz Rosalia': ['Euskera'], 
                'vizuak Rosalia': ['Euskera'], 
                'Rosalia concert': ['Ingles'], 
                'Lux tour tickets': ['Ingles'], 
                'Rosalia live': ['Français, Ingles, Italiano'], 
                'Tour dates Rosalia': ['Ingles'], 
                'Rosalia fan': ['Ingles'], 
                'Lux tour review': ['Ingles'], 
                'Rosalia concerto': ['Italiano'], 
                'Lux Tour Italia': ['Italiano'], 
                'biglietti Rosalia': ['Italiano'], 
                'show Rosalia': ['Français, Portugues'], 
                'fãs Rosalia': ['Portugues'], 
                'Luz Tour': ['Portugues'], 
                'tournée Rosalia': ['Français']
            }
        },
        scraping={
            'reddit': {
                'enabled': True,
                'limit': None, # Traerá todo lo que encuentre
                'query': [
                    'Rosalia Lux Tour Madrid', 'Concierto Rosalia Lux', 'Entradas Rosalia Lux', 
                    'Rosalia Lux Barcelona', 'Fotos Rosalia Lux Tour', 'Rosalia Lux', 
                    'concert Rosalia', 'Lux tour', 'fotos Rosalia Lux', 'venda Rosalia', 
                    'Rosalia Lux Tour', 'concertu Rosalia', 'fotiz Rosalia', 'vizuak Rosalia', 
                    'Rosalia concert', 'Lux tour tickets', 'Rosalia live', 'Tour dates Rosalia', 
                    'Rosalia fan', 'Lux tour review', 'Rosalia concerto', 'Lux Tour Italia', 
                    'biglietti Rosalia', 'show Rosalia', 'fãs Rosalia', 'Luz Tour', 'tournée Rosalia'
                ]
            }
        },
        CREDENTIALS={
            'reddit': {
                'reddit_client_id': 'TXr9FuPxqBWzt5Se6B7O4w',
                'reddit_client_secret': 'FDLxAYCobON7T1yadE-Ip52qtHJRBA'
            }
        }
    )
    
    # 🔥 EJECUTAR
    print("🎮 MODO DEBUG ACTIVADO CON CONFIGURACIÓN DE ROSALÍA")
    try:
        asyncio.run(run_reddit(DEBUG_CONFIG))
    except KeyboardInterrupt:
        print("\n🛑 Proceso detenido por el usuario.")
    except Exception as e:
        print(f"❌ Error en el debug: {e}")