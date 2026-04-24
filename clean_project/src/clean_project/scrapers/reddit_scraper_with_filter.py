import praw
import csv
from pathlib import Path
from datetime import datetime
from langdetect import detect, LangDetectException
import time
import re
import asyncpraw

# NUEVO: Importar filtro LLM
from clean_project.filters.llm_relevance_filter import LLMRelevanceFilter, PostContent
from clean_project.filters.llm_relevance_filter import check_relevance_sync
filter_instance = LLMRelevanceFilter() 
print(f"REDDIT SCRAPER INICIADO (CON FILTRO LLM)")

# -------------------------------------------------------------------------
# SCRAPER PRINCIPAL CON FILTRO LLM
# -------------------------------------------------------------------------
async def run_reddit(config):
    search_form_lang_map = config.general.get("search_form_lang_map", {})
    
    # Preparar carpeta y archivo
    output_folder = config.general["output_folder"]
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/reddit_global_dataset.csv"

    if Path(output_file).exists() and Path(output_file).stat().st_size > 0:
        print(f"⚠️ El archivo CSV de Reddit ya existe en: {output_file}. Saltando...")
        return

    # Configuración
    keywords = config.scraping["reddit"]["query"]
    limit = config.scraping["reddit"].get("limit", None)
    start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d")
    end_date_raw = datetime.strptime(config.general["end_date"], "%Y-%m-%d")
    end_date = end_date_raw.replace(hour=23, minute=59, second=59)
    
    # NUEVO: Configuración para filtro LLM
    tema = config.general.get("tema", "")
    geo_scope = config.general.get("population_scope", "España")
    desc_tema = config.general.get("desc_tema", "")
    languages = config.general.get("languages", [])

    
    print(f"📅 Rango configurado: {start_date} <--> {end_date}")
    print(f"🎯 Tema de análisis: {tema}")
    
    IDIOMAS = ["en", "es", "ca", "eu", "pt", "fr", "gl", "it"]
    all_rows = []
    seen_rows = set()
    
    # Estadísticas
    stats = {
        "posts_encontrados": 0,
        "posts_relevantes": 0,
        "posts_filtrados": 0,
        "comentarios_guardados": 0
    }

    print(f"\n KEYWORDS QUE SE VAN A BUSCAR EN REDDIT: {keywords}\n")
    
    async with asyncpraw.Reddit(
        client_id=config.CREDENTIALS["reddit"]["reddit_client_id"],
        client_secret=config.CREDENTIALS["reddit"]["reddit_client_secret"],
        user_agent="SpainUserCollector/1.0"
    ) as reddit:
        for keyword in keywords:
            print(f"🔹 Buscando posts Reddit para keyword: {keyword}")
            languages = search_form_lang_map.get(keyword, [])

            subreddit = await reddit.subreddit("all")
            resultados = subreddit.search(keyword, limit=limit)
            
            async for post in resultados:
                stats["posts_encontrados"] += 1
                
                # --- 1. Filtro de Fecha ---
                fecha_post = datetime.fromtimestamp(post.created_utc)
                if not (start_date <= fecha_post <= end_date):
                    continue
                try:
                    await post.load()
                except Exception as e:
                    print(f"⚠️ Error cargando post: {e}")
                    continue

                # --- 2. Preparar Texto ---
                titulo = post.title or ""
                cuerpo = post.selftext or ""
                texto_post_completo = titulo + " " + cuerpo

                import hashlib
                user_name = post.author.name if post.author else "[deleted]"
                user_hash = hashlib.sha256(user_name.encode()).hexdigest()[:16]
                
                # --- 3. Filtro de Idioma ---
                try:
                    idioma = detect(texto_post_completo) if len(texto_post_completo.strip()) > 5 else "unknown"
                except LangDetectException:
                    idioma = "unknown"

                if idioma not in IDIOMAS:
                    continue

                # ===================================================================
                # NUEVO: FILTRO LLM DE RELEVANCIA
                # ===================================================================
                print(f"\n📝 Verificando relevancia del post: {titulo[:60]}...")
                
                es_relevante, confianza, razon = await filter_instance.check_relevance(
                    post=PostContent(text=texto_post_completo),
                    images=None,  # Reddit no incluye imágenes en API de texto
                    tema=tema,
                    keywords=keywords,
                    geo_scope=geo_scope,
                    languages=languages,
                    desc_tema=desc_tema
                )
                
                if not es_relevante:
                    print(f"  ⏭️  Post NO relevante. Saltando comentarios.")
                    stats["posts_filtrados"] += 1
                    continue
                
                print(f"  ✅ Post RELEVANTE. Descargando comentarios...")
                stats["posts_relevantes"] += 1
                # ===================================================================

                # --- 4. GUARDAR POST ---
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
                    "retweets": 0, 
                    "quotes": 0,
                    "hearts": post.score, 
                    "Likes": post.score,
                    "Followers": "", "Following": "", "Tweets": "", "Bio": "", 
                    "Ubicacion": "", "JoinDate": "", "Website": "", 
                    "IsVerified": "", "IsProtected": "", "plays": 0, 
                    "search_keyword": keyword,
                    "keyword_languages": ",".join(languages),
                    "llm_relevante": "SI"  # NUEVO CAMPO
                }
                
                fila_tuple = tuple(row_post.items())
                if fila_tuple not in seen_rows:
                    seen_rows.add(fila_tuple)
                    all_rows.append(row_post)

                # --- 5. COMENTARIOS DIRECTOS ÚNICAMENTE (NO RESPUESTAS ANIDADAS) ---
                try:
                    await post.comments.replace_more(limit=0)  # No expandir respuestas
                    
                    # SOLO top-level comments (comentarios directos al post)
                    for comment in post.comments:
                        if not hasattr(comment, 'body'):
                            continue
                            
                        fecha_com = datetime.fromtimestamp(comment.created_utc)
                        if not (start_date <= fecha_com <= end_date):
                            continue

                        texto_comentario = comment.body or ""
                        
                        # Guardar comentario directo
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
                            "comments": "", "retweets": "", "quotes": "",
                            "hearts": comment.score, 
                            "Likes": comment.score,
                            "Followers": "", "Following": "", "Tweets": "", "Bio": "",
                            "Ubicacion": "", "JoinDate": "", "Website": "",
                            "IsVerified": "", "IsProtected": "", "plays": 0,
                            "search_keyword": keyword,
                            "keyword_languages": ",".join(languages),
                            "llm_relevante": "PENDIENTE"  # Se filtrará en fase 2
                        }
                        
                        fila_tuple = tuple(row_comment.items())
                        if fila_tuple not in seen_rows:
                            seen_rows.add(fila_tuple)
                            all_rows.append(row_comment)
                            stats["comentarios_guardados"] += 1
                            
                except Exception as e:
                    print(f"Error obteniendo comentarios: {e}")

                time.sleep(1)

    # Guardar CSV
    fieldnames = list(all_rows[0].keys()) if all_rows else []
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n✅ CSV Reddit guardado en: {output_file}")
    print(f"\n📊 ESTADÍSTICAS:")
    print(f"  Posts encontrados: {stats['posts_encontrados']}")
    print(f"  Posts relevantes: {stats['posts_relevantes']}")
    print(f"  Posts filtrados: {stats['posts_filtrados']}")
    print(f"  Comentarios guardados: {stats['comentarios_guardados']}")
    
    return all_rows