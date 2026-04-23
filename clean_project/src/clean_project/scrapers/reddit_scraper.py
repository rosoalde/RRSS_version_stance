import praw           # Biblioteca oficial de Reddit para acceder a su API
import csv            # Para guardar los datos en un archivo CSV
from pathlib import Path  # Para manejar rutas y crear carpetas
from datetime import datetime  # Para manejar fechas
from langdetect import detect, LangDetectException  # Para detectar idioma
import time           # Para hacer pausas entre peticiones
import re             # Para expresiones regulares (filtro estricto)
#import clean_project.config.settings as config        # Archivo externo de configuración
import asyncpraw

print(f"REDDIT SCRAPER INICIADO")

# -------------------------------------------------------------------------
# FUNCIÓN DE FILTRO ESTRICTO
# -------------------------------------------------------------------------
def pasa_filtro_contenido(texto, keyword_query):
    """
    Verifica si las palabras de la keyword aparecen realmente en el texto.
    Devuelve True si TODAS las palabras de la query están en el texto.
    """
    if not texto:
        return False
        
    texto_norm = texto.lower()
    query_clean = keyword_query.replace('"', '').lower()
    palabras_clave = [p.replace('*', '') for p in query_clean.split()]

    for palabra in palabras_clave:
        # Busca la palabra exacta o con sufijos (ej: dron, drones)
        patron = r'(?:^|\W)#?' + re.escape(palabra) + r'\w*'
        if not re.search(patron, texto_norm):
            return False
    return True

# -------------------------------------------------------------------------
# SCRAPER PRINCIPAL
# -------------------------------------------------------------------------
async def run_reddit(config):
    search_form_lang_map = config.general.get("search_form_lang_map", {})

    
    # Preparar carpeta y archivo
    output_folder = config.general["output_folder"]
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/reddit_global_dataset.csv"

    # Si ya existe, no sobrescribir
    if Path(output_file).exists() and Path(output_file).stat().st_size > 0:
        print(f"⚠️ El archivo CSV de Reddit ya existe en: {output_file}. Saltando...")
        return

    # Configuración de búsqueda
    keywords = config.scraping["reddit"]["query"]
    limit = config.scraping["reddit"].get("limit", None)
    start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d")
    end_date_raw   = datetime.strptime(config.general["end_date"], "%Y-%m-%d")
    end_date = end_date_raw.replace(hour=23, minute=59, second=59)
    print(f"📅 Rango configurado: {start_date} <--> {end_date}")
    # Conexión API
    

    IDIOMAS = ["en", "es", "ca", "eu", "pt", "fr","gl", "it"]  # Inglés, Español, Catalán, Vasco, Portugués, Francés, Gallego, Italiano
    all_rows = []
    seen_rows = set()

    print(f"\n KEYWORDS QUE SE VAN A BUSCAR EN REDDIT: {keywords}\n")
    async with asyncpraw.Reddit(
            client_id=config.CREDENTIALS["reddit"]["reddit_client_id"],
            client_secret=config.CREDENTIALS["reddit"]["reddit_client_secret"],
            user_agent="SpainUserCollector/1.0"
        ) as reddit:
        for keyword in keywords:
            print(f"🔹 Buscando posts Reddit para keyword: {keyword}")
            languages = search_form_lang_map.get(keyword, [])

            # Búsqueda inicial (Reddit API devuelve coincidencias aproximadas)
            subreddit = await reddit.subreddit("all")
            resultados = subreddit.search(keyword, limit=limit)  # ✅ No await aquí
            async for post in resultados:
                
                # --- 1. Filtro de Fecha ---
                fecha_post = datetime.fromtimestamp(post.created_utc)
                if not (start_date <= fecha_post <= end_date):
                    continue

                # --- 2. Preparar el Texto del Post (Título + Cuerpo) ---
                titulo = post.title or ""
                cuerpo = post.selftext or ""
                
                # Unimos todo para analizarlo junto
                texto_post_completo = titulo + " " + cuerpo 
                
                # --- 3. Filtro de Idioma ---
                try:
                    idioma = detect(texto_post_completo) if len(texto_post_completo.strip()) > 5 else "unknown"
                except LangDetectException:
                    idioma = "unknown"

                if idioma not in IDIOMAS:
                    continue

                # --- 4. PROCESAR FILA "POST" ---
                # Guardamos el Post SOLO si (Título + Cuerpo) contienen la palabra clave.
                if pasa_filtro_contenido(texto_post_completo, keyword):
                    row_post = {
                        "post_title": titulo,
                        "post_selftext": cuerpo,          # <--- Guardamos el cuerpo original separado
                        "usuario": post.author.name if post.author else "[deleted]",
                        "Fullname": post.author.name if post.author else "[deleted]",
                        "contenido": texto_post_completo, # <--- Aquí va Título + Cuerpo juntos
                        "fecha": fecha_post.strftime("%Y-%m-%d %H:%M"),
                        "enlace": f"https://reddit.com{post.permalink}",
                        "TipoDeTweet": "Post",
                        "UsuarioOriginal": "",
                        "EnlaceOriginal": "",
                        "comments": post.num_comments,
                        "retweets": 0, 
                        "quotes": 0,
                        "hearts": post.score, 
                        "Likes": post.score,
                        "Followers": "", "Following": "", "Tweets": "", "Bio": "", 
                        "Ubicacion": "", "JoinDate": "", "Website": "", 
                        "IsVerified": "", "IsProtected": "", "plays": 0, 
                        "search_keyword": keyword,
                        "keyword_languages": ",".join(languages)
                    }
                    
                    fila_tuple = tuple(row_post.items())
                    if fila_tuple not in seen_rows:
                        seen_rows.add(fila_tuple)
                        all_rows.append(row_post)

                # --- 5. PROCESAR COMENTARIOS ---
                try:
                    await post.comments.replace_more(limit=0)
                    comments_list = post.comments.list()
                except Exception:
                    comments_list = []

                for comment in comments_list:
                    fecha_com = datetime.fromtimestamp(comment.created_utc)
                    # print(f"fecha_post: {fecha_post}")
                    # print(f"fecha_comment: {fecha_com}")
                    # print(f"start_date: {start_date}")
                    # print(f"end_date: {end_date}")
                    if not (start_date <= fecha_com <= end_date):
                        # ESTO TE MOSTRARÁ EN PANTALLA QUE EL FILTRO SÍ ESTÁ TRABAJANDO
                        # print(f"❌ Comentario RECHAZADO por fecha: {fecha_com}") 
                        continue

                    texto_comentario = comment.body or ""
                    
                    # Para saber si el comentario es relevante, miramos el CONTEXTO TOTAL:
                    # (Título del Post + Cuerpo del Post + Texto del Comentario)
                    texto_contexto_completo = texto_post_completo + " " + texto_comentario

                    if pasa_filtro_contenido(texto_contexto_completo, keyword):
                        
                        row_comment = {
                            "post_title": titulo,
                            "post_selftext": cuerpo,      # <--- Incluimos el cuerpo del padre para contexto
                            "usuario": comment.author.name if comment.author else "[deleted]",
                            "Fullname": comment.author.name if comment.author else "[deleted]",
                            "contenido": texto_comentario, # <--- Aquí SOLO el texto del comentario
                            "fecha": fecha_com.strftime("%Y-%m-%d %H:%M"),
                            "enlace": f"https://reddit.com{post.permalink}",
                            "TipoDeTweet": "Comentario",
                            "UsuarioOriginal": post.author.name if post.author else "[deleted]",
                            "EnlaceOriginal": f"https://reddit.com{post.permalink}",
                            "comments": "", "retweets": "", "quotes": "",
                            "hearts": comment.score, 
                            "Likes": comment.score,
                            "Followers": "", "Following": "", "Tweets": "", "Bio": "",
                            "Ubicacion": "", "JoinDate": "", "Website": "",
                            "IsVerified": "", "IsProtected": "", "plays": 0, "search_keyword": comment.get("_search_keyword", ""), 
                            "search_keyword": keyword,
                            "keyword_languages": ",".join(languages)
                            }
                        fila_tuple = tuple(row_comment.items())
                        if fila_tuple not in seen_rows:
                            seen_rows.add(fila_tuple)
                            all_rows.append(row_comment)

                time.sleep(1)

    # Guardar CSV
    fieldnames = list(all_rows[0].keys()) if all_rows else []
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n✅ CSV Reddit guardado en: {output_file} ({len(all_rows)} filas)")
    return all_rows

# -------------------------------------------------------------------------
#  DEBUG MANUAL
# -------------------------------------------------------------------------
if __name__ == "__main__":
    from types import SimpleNamespace
    import asyncio
    
    # 🎮 CONFIG COMO OBJETO
    DEBUG_CONFIG = SimpleNamespace(
        general={
            "output_folder": "./debug_reddit/",
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "search_form_lang_map": {"LUX Tour Rosalia": ["en"]}
        },
        scraping={
            "reddit": {
                "query": ["LUX Tour Rosalia"],
                "limit": None
            }
        },
        CREDENTIALS={
            "reddit": {
                "reddit_client_id": "TXr9FuPxqBWzt5Se6B7O4w",
                "reddit_client_secret": "FDLxAYCobON7T1yadE-Ip52qtHJRBA"
            }
        }
    )
    
    # 🔥 EJECUTAR
    print("🎮 MODO DEBUG ACTIVADO")
    asyncio.run(run_reddit(DEBUG_CONFIG))