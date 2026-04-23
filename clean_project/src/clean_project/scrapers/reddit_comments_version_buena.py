import asyncio
import csv
import sys
from types import SimpleNamespace
print("PYTHON USADO:", sys.executable)
import asyncpraw
from datetime import datetime
# 1. TUS CREDENCIALES
CLIENT_ID = "TXr9FuPxqBWzt5Se6B7O4w"
CLIENT_SECRET = "FDLxAYCobON7T1yadE-Ip52qtHJRBA"
USER_AGENT = "PruebaBasica/1.0"
#from langdetect import detect, LangDetectException
from concurrent.futures import ThreadPoolExecutor
from googletrans import Translator
import numpy as np
idiomas_reddit = {
    "en": "Inglés",
    "es": "Español",
    "fr": "Francés",
    "it": "Italiano",
    "pt": "Portugués",
    "eu": "Euskera",
    # Agrega más códigos de idioma y sus nombres si es necesario
}

# def _detectar_idioma_sync(texto):
#     try:
#         return detect(texto) if len(texto.strip()) > 5 else "unknown"
#     except LangDetectException:
#         return "unknown"
# _executor = ThreadPoolExecutor(max_workers=4)

async def detect_languages(texto):
    async with Translator() as translator:
        result = await translator.detect(texto)
        lenguage = result.lang
        return lenguage
    
async def detectar_idioma_async(texto):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _detectar_idioma_sync, texto)    

async def extraer_todo_sin_filtros(keyword,config, start_date, end_date):
    rows_keyword = []
    async with asyncpraw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent=USER_AGENT
    ) as reddit:

        rows_keyword = []
        search_form_lang_map = config.general.get("search_form_lang_map", {})
        languages = search_form_lang_map.get(keyword, [])   
            
        

        print(f"--- 🔍 BUSCANDO POSTS QUE CONTENGAN: {keyword} ---")
        print(f" search_form_lang_map: {search_form_lang_map}")
        print(f" languages: {languages}")

        subreddit = await reddit.subreddit("all") # Busca en todas las publicaciones de todos los subreddits públicos
        busqueda = subreddit.search(keyword, limit=None) # Lista completa de todos los posts que contienen la palabra clave, sin límite

        async for post in busqueda:
            fecha_post = datetime.fromtimestamp(post.created_utc)
            print(f"\n📅 POST FECHA: {fecha_post} | SUBREDDIT: {post.subreddit.display_name}")
            if not (start_date <= fecha_post <= end_date):
                print(f"   ⚠️ El post no está dentro del rango de fechas especificado ({start_date} - {end_date}). Se omite.")
                continue
            titulo = post.title or ""
            cuerpo = post.selftext or ""
            texto_post_completo = titulo + " " + cuerpo 

            # 3. Filtro Idioma (Optimizado)
            # ================== DESCOMENTAR ==================
            # # idioma_langdetect = await detectar_idioma_async(texto_post_completo)
            # translator = Translator()

            # try:
            #     idioma_google = translator.detect(texto_post_completo).lang if texto_post_completo.strip() else "unknown"
            # except Exception:
            #     idioma_google = "unknown"
            #     print(idioma_google)


            # # print("languages:", languages, type(languages))
            # # print("idioma_google:", idioma_google, type(idioma_google))  
            # print(f"texto_post_completo: {texto_post_completo}") # Muestra un fragmento del texto para verificar
            # if idioma_google not in languages:
            #     # print(f"   ⚠️ El idioma detectado es {idioma_langdetect} (LangDetect) y {idioma_google} (Google Translate), que no coincide con los idiomas esperados: {languages} para esta keyword. Se omite.")
            #     continue
            # ================== DESCOMENTAR ==================

            # if str(idioma_google) not in languages:
            #     print(f"   ⚠️ El idioma detectado es {idioma_langdetect}, que no coincide con los idiomas esperados: {languages} para esta keyword. Se omite.")
            #     continue

            row_post = {
                "post_title": titulo,
                "post_selftext": cuerpo,
                "usuario": post.author.name if post.author else "[deleted]",
                "Fullname": post.author.name if post.author else "[deleted]",
                "contenido": cuerpo,
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
            post_key = (post.id, 0)
            if post_key not in seen_ids:
                seen_ids.add(post_key)
                rows_keyword.append(row_post)

            print(f"\n\n" + "█"*80)
            print(f"TITULO DEL POST: {post.title}")
            print(f"ID DEL POST: {post.id}")
            print(f"URL: https://www.reddit.com{post.permalink}")
            print("█"*80)

            # --- SOLUCIÓN AL ERROR ---
            print(f"\n[1] Cargando datos completos del post...")
            await post.load() # Esto descarga toda la información que falta, incluyendo los comentarios
            
            print(f"[2] Expandiendo todos los hilos de comentarios (esto puede tardar)...")
            # Ahora que el post está cargado, replace_more ya no dará error
            await post.comments.replace_more(limit=None)

            
            # print(len(post.comments), len(post.comments.list())) #Diferencia entre comentarios de primer nivel y todos los comentarios (incluyendo respuestas)
            # print(f"[3] Aplanando el árbol de comentarios...")
            # todos_los_comentarios = post.comments.list() # Esto devuelve una lista plana de TODOS los comentarios, sin importar su nivel de anidación
            # print(f"[4] Imprimiendo los {len(todos_los_comentarios)} comentarios encontrados:\n")
            for comment in post.comments:    
                fecha_com = datetime.fromtimestamp(comment.created_utc)
                if not (start_date <= fecha_com <= end_date):
                    print(f"   ⚠️ El comentario no está dentro del rango de fechas especificado ({start_date} - {end_date}). Se omite.")
                    continue
                print(f"comment.id: {comment.id} | comment.author: {comment.author} | comment.created_utc: {comment.created_utc}")
                
                texto_comentario = comment.body or ""
                print(f"   🗣️ Comentario: {texto_comentario[:100]}...") # Muestra un fragmento del comentario para verificar
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
                comment_key = (post.id, comment.id)
                if comment_key not in seen_ids:
                    seen_ids.add(comment_key)
                    rows_keyword.append(row_comment)

                        

            #     print(fecha_com)
            # if not todos_los_comentarios:
            #     print("   ⚠️ Este post no tiene comentarios.")
            # for i, comentario in enumerate(todos_los_comentarios, 1):
            #     autor = comentario.author.name if comentario.author else "[Borrado]"
            #     print(f"   ({i}) DE: {autor}")
            #     print(f"       DICE: {comentario.body}")
            #     print(f"       " + "-"*40)
    return rows_keyword
if __name__ == "__main__":
    try:
        start_date = "2025-11-25" # "2025-03-01" # '2026-03-01'
        end_date = "2025-11-27" # "2026-04-01" # '2026-04-01'
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date_raw = datetime.strptime(end_date, "%Y-%m-%d")
        end_date = end_date_raw.replace(hour=23, minute=59, second=59)
        keyword = "euskaldunak" #"LUX Tour Rosalia"
        config = SimpleNamespace(
        general={
            "output_folder": "./debug_reddit/",
            'start_date': '2025-11-25',
            'end_date': '2025-11-27', #"start_date": "2026-03-01", # "2026-03-01",
            #"end_date": "2026-04-01", # "2026-03-31",
            # "search_form_lang_map": {"euskaldunak": ["eu", "es"], "LUX Tour Rosalia": ["en"]} # {"LUX Tour Rosalia": ["en"]}
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
            },
            "scraping": {'reddit': {'enabled': True, 'limit': None, 'query': ['Rosalia Lux Tour', 'Concierto Rosalia', 'Fechas Rosalia Tour', 'Entradas Rosalia', 'Lux Tour Rosalia', 'Rosalia Lux', 'concert Rosalia', 'Lux tour', 'venda Rosalia', 'concertu Rosalia', 'vizuak Rosalia', 'Rosalia concert', 'Lux tour tickets', 'Rosalia live', 'Tour dates Rosalia', 'Rosalia fan', 'Lux tour review', 'Rosalia concerto', 'Lux Tour Italia', 'biglietti Rosalia', 'show Rosalia', 'tours Rosalia', 'tournée Rosalia']}}
        }
        )
        seen_ids=set() 
        all_rows = []
        keywords = config.general["scraping"]["reddit"]["query"]
        limit = config.general["scraping"]["reddit"]["limit"]

        # keywords = list(config.general.get("search_form_lang_map", {}).keys())
        for keyword in keywords:
            resultados_keywords = asyncio.run(extraer_todo_sin_filtros(keyword=keyword, config=config, start_date=start_date, end_date=end_date))
            all_rows.extend(resultados_keywords)
        output_file = "/home/rrss/proyecto_web/debug_reddit/reddit_comments2.csv"   
        if all_rows:
            fieldnames = list(all_rows[0].keys())
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            print(f"\n✅ CSV Reddit guardado en: {output_file} ({len(all_rows)} filas)")
        else:
            print("\n⚠️ No se encontraron resultados en Reddit.")

    except Exception as e:
        print(f"❌ Ocurrió un error: {e}")