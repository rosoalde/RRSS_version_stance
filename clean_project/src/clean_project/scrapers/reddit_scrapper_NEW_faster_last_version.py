import asyncio
import csv
import sys
import os
import asyncpraw
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace

# Intentar importar Translator (si no está, el código sigue)
try:
    from googletrans import Translator
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

print(f"REDDIT SCRAPER (VERSION FINAL - SINCRONIZADA) INICIADO")

# -------------------------------------------------------------------------
# FUNCIÓN TRABAJADORA
# -------------------------------------------------------------------------
async def extraer_todo_sin_filtros(reddit, keyword, config, start_date, end_date, seen_ids):
    rows_keyword = []
    
    # Acceso seguro a la configuración (u_conf.general es un dict)
    search_form_lang_map = config.general.get("search_form_lang_map", {})
    languages = search_form_lang_map.get(keyword, [])   

    print(f"--- 🔍 BUSCANDO: {keyword} ---")

    try:
        subreddit = await reddit.subreddit("all")
        # Acceso seguro a scraping (u_conf.scraping es un dict)
        limit_val = config.scraping.get("reddit", {}).get("limit", None)
        busqueda = subreddit.search(keyword, limit=limit_val) 

        async for post in busqueda:
            fecha_post = datetime.fromtimestamp(post.created_utc)
            
            if not (start_date <= fecha_post <= end_date):
                continue

            # Carga profunda para evitar errores de NoneType
            await post.load()
            
            titulo = post.title or ""
            cuerpo = post.selftext or ""
            texto_post_completo = titulo + " " + cuerpo 

            nombre_subreddit = post.subreddit.display_name or ""
            # 1. Guardar el POST (Deduplicado)
            post_key = (post.id, 0)
            if post_key not in seen_ids:
                seen_ids.add(post_key)
                rows_keyword.append({
                    "post_title": titulo,
                    "post_selftext": cuerpo,
                    "subreddit": nombre_subreddit,
                    "usuario": post.author.name if post.author else "[deleted]",
                    "Fullname": post.author.name if post.author else "[deleted]",
                    "contenido": cuerpo if cuerpo else titulo,
                    "fecha": fecha_post.strftime("%Y-%m-%d %H:%M"),
                    "enlace": f"https://reddit.com{post.permalink}",
                    "TipoDeTweet": "Post",
                    "Likes": post.score,
                    "search_keyword": keyword,
                    "keyword_languages": ",".join(languages),
                    "comments": post.num_comments,
                    "retweets": np.nan, "quotes": np.nan, "hearts": post.score,
                    "Followers": "", "Following": "", "Tweets": "", "Bio": "",
                    "Ubicacion": "", "JoinDate": "", "Website": "",
                    "IsVerified": "", "IsProtected": "", "plays": np.nan
                })

            # 2. Expandir y recorrer comentarios
            print(f"   ⏳ Expandiendo comentarios de: {post.id}")
            await post.comments.replace_more(limit=None)
            
            for comment in post.comments:
                fecha_com = datetime.fromtimestamp(comment.created_utc)
                # if not (start_date <= fecha_com <= end_date):
                #     continue

                comment_key = (post.id, comment.id)
                numero_respuestas = len(comment.replies)
                #if comment_key not in seen_ids:
                seen_ids.add(comment_key)
                rows_keyword.append({
                    "post_title": titulo,
                    "post_selftext": cuerpo,
                    "subreddit": nombre_subreddit,
                    "usuario": comment.author.name if comment.author else "[deleted]",
                    "Fullname": comment.author.name if comment.author else "[deleted]",
                    "contenido": comment.body,
                    "fecha": fecha_com.strftime("%Y-%m-%d %H:%M"),
                    "enlace": f"https://reddit.com{post.permalink}{comment.id}",
                    "TipoDeTweet": "Comentario",
                    "Likes": comment.score,
                    "search_keyword": keyword,
                    "keyword_languages": ",".join(languages),
                    "UsuarioOriginal": post.author.name if post.author else "[deleted]",
                    "EnlaceOriginal": f"https://reddit.com{post.permalink}",
                    "comments": numero_respuestas, "retweets": "", "quotes": "", "hearts": comment.score,
                    "Followers": "", "Following": "", "Tweets": "", "Bio": "",
                    "Ubicacion": "", "JoinDate": "", "Website": "",
                    "IsVerified": "", "IsProtected": "", "plays": np.nan
                })

    except Exception as e:
        print(f"⚠️ Error en keyword '{keyword}': {e}")
    
    return rows_keyword

# -------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL (Llamada por logica.py)
# -------------------------------------------------------------------------
async def run_reddit(config):
    # config.general es un dict
    output_folder = config.general["output_folder"]
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/reddit_global_dataset.csv"

    seen_ids = set()
    # config.scraping es un dict
    keywords = config.scraping["reddit"]["query"]
    
    start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d")
    end_date = datetime.strptime(config.general["end_date"], "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    
    all_rows = []
    
    # config.CREDENTIALS es un dict
    async with asyncpraw.Reddit(
            client_id=config.CREDENTIALS["reddit"]["reddit_client_id"],
            client_secret=config.CREDENTIALS["reddit"]["reddit_client_secret"],
            user_agent="SpainUserCollector/3.0"
        ) as reddit:
        
        for kw in keywords:
            res = await extraer_todo_sin_filtros(reddit, kw, config, start_date, end_date, seen_ids)
            all_rows.extend(res)

    if all_rows:
        df = pd.DataFrame(all_rows)
        df.to_csv(output_file, index=False, encoding="utf-8", sep=";")
        print(f"✅ CSV Reddit guardado: {output_file} ({len(all_rows)} filas)")
    else:
        print("\n⚠️ No se encontraron resultados en Reddit.")

    return all_rows

# -------------------------------------------------------------------------
#  DEBUG MANUAL (CORREGIDO PARA COINCIDIR CON LOGICA.PY)
# -------------------------------------------------------------------------
if __name__ == "__main__":
    # Esta es la configuración exacta que pasaste en el log
    DEBUG_CONFIG = SimpleNamespace(
        general={
            "output_folder": "/home/rrss/proyecto_web/debug_reddit/debug_reddit_NEW_faster",
            'start_date': '2025-11-25',
            'end_date': '2025-11-27',
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
        scraping = {
                'reddit': {
                    'enabled': True, 
                    'limit': None, 
                    'query': ['Rosalia Lux Tour', 'Concierto Rosalia', 'Fechas Rosalia Tour', 'Entradas Rosalia', 'Lux Tour Rosalia', 'Rosalia Lux', 'concert Rosalia', 'Lux tour', 'venda Rosalia', 'concertu Rosalia', 'vizuak Rosalia', 'Rosalia concert', 'Lux tour tickets', 'Rosalia live', 'Tour dates Rosalia', 'Rosalia fan', 'Lux tour review', 'Rosalia concerto', 'Lux Tour Italia', 'biglietti Rosalia', 'show Rosalia', 'tours Rosalia', 'tournée Rosalia']
                }
            },
        CREDENTIALS={
            'reddit': {
                'reddit_client_id': 'TXr9FuPxqBWzt5Se6B7O4w',
                'reddit_client_secret': 'FDLxAYCobON7T1yadE-Ip52qtHJRBA'
            }
        }
    )
    
    asyncio.run(run_reddit(DEBUG_CONFIG))