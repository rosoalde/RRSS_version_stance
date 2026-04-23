# ---------------------------------------------------------------
# Scraper de Bluesky OPTIMIZADO (ASYNC) - VERSIÓN FINAL PRO
# ---------------------------------------------------------------
import csv
import asyncio
import aiohttp
import sys
import re
from pathlib import Path
from datetime import datetime

# Imports de tu proyecto
try:
    from clean_project.config import settings as config
except ImportError:
    config = None
from clean_project.filters.llm_relevance_filter import check_relevance_sync
print("Bluesky SCRAPER OPTIMIZADO (MODO SIN LÍMITES) INICIADO")

# Semáforo para no saturar la API
SEM = asyncio.Semaphore(10)

def parse_bluesky_date(fecha_iso):
    try:
        # Convertimos a datetime y quitamos zona horaria para comparar (Naive)
        dt = datetime.fromisoformat(fecha_iso.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except Exception:
        return None

# ---------------------------------------------------------------
# 1. FUNCIÓN PARA BUSCAR POSTS (PAGINACIÓN TOTAL)
# ---------------------------------------------------------------
async def fetch_posts_for_keyword(session, keyword, headers, start_date, end_date, search_form_lang_map):
    url_search = "https://bsky.social/xrpc/app.bsky.feed.searchPosts"
    params = {
        "q": keyword,
        "limit": 100, 
        "since": f"{start_date}T00:00:00Z",
        "until": f"{end_date}T23:59:59Z",
        "sort": "latest" 
    }
    
    posts_collected = []
    cursor = None
    languages = search_form_lang_map.get(keyword, [])
    
    print(f"🔹 Iniciando búsqueda profunda para: {keyword}")

    while True:
        if cursor: params["cursor"] = cursor
        
        async with SEM:
            try:
                async with session.get(url_search, headers=headers, params=params, timeout=20) as response:
                    if response.status != 200:
                        break
                    
                    data = await response.json()
                    posts = data.get("posts", [])
                    
                    if not posts:
                        break 
                    
                    for post in posts:
                        post["_search_keyword"] = keyword
                        post["_keyword_languages"] = languages
                    
                    posts_collected.extend(posts)
                    cursor = data.get("cursor")
                    if not cursor:
                        break
                    
                    await asyncio.sleep(0.1)
            except Exception as e:
                print(f"❌ Error en keyword {keyword}: {e}")
                break
    
    return posts_collected

# ---------------------------------------------------------------
# 1.5 FUNCIÓN PARA OBTENER EL HILO (COMENTARIOS)
# ---------------------------------------------------------------
async def fetch_post_thread(session, post_uri, headers):
    url_thread = "https://bsky.social/xrpc/app.bsky.feed.getPostThread"
    params = {"uri": post_uri, "depth": 1}
    
    async with SEM:
        try:
            async with session.get(url_thread, headers=headers, params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("thread", {})
        except:
            return {}
    return {}

# ---------------------------------------------------------------
# 2. FUNCIÓN PARA DESCARGAR PERFILES
# ---------------------------------------------------------------
async def fetch_profile_batch(session, batch, headers):
    url_profiles = "https://bsky.social/xrpc/app.bsky.actor.getProfiles"
    params = [("actors", h) for h in batch]
    
    async with SEM:
        try:
            async with session.get(url_profiles, headers=headers, params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("profiles", [])
        except:
            return []
    return []

# ---------------------------------------------------------------
# 3. LÓGICA PRINCIPAL ASÍNCRONA
# ---------------------------------------------------------------
async def _run_bluesky_async(config):
    search_form_lang_map = config.general.get("search_form_lang_map", {})
    output_folder = Path(config.general["output_folder"])
    output_folder.mkdir(parents=True, exist_ok=True)
    output_file = output_folder / "bluesky_global_dataset.csv"
    
    if output_file.exists() and output_file.stat().st_size > 0:
        print(f"⚠️ El archivo CSV de Bluesky ya existe. Saltando...")
        return

    keywords = config.scraping["bluesky"]["query"]
    username = config.CREDENTIALS["bluesky"]["USERNAME_bluesky"]
    password = config.CREDENTIALS["bluesky"]["PASSWORD_bluesky"]
    start_date = config.general["start_date"]
    end_date = config.general["end_date"]
    tema = config.general.get("tema", "")
    desc_tema = config.general.get("desc_tema", "")
    geo_scope = config.general.get("population_scope", "España")
    languages = config.general.get("languages", [])
    keywords = config.scraping["youtube"]["query"]

    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)

    async with aiohttp.ClientSession() as session:
        # --- A. AUTENTICACIÓN ---
        async with session.post(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            json={"identifier": username, "password": password}
        ) as resp:
            if resp.status != 200:
                print(f"❌ Error Auth Bluesky: {resp.status}")
                return
            auth_data = await resp.json()
            headers = {"Authorization": f"Bearer {auth_data['accessJwt']}"}

        # --- B. BÚSQUEDA DE POSTS ---
        tasks_posts = [
            fetch_posts_for_keyword(session, kw, headers, start_date, end_date, search_form_lang_map)
            for kw in keywords
        ]
        results_posts = await asyncio.gather(*tasks_posts)
        
        seen_uris = set()
        unique_posts = []
        for sublist in results_posts:
            for p in sublist:
                if p["uri"] not in seen_uris:
                    seen_uris.add(p["uri"])
                    unique_posts.append(p)

        # --- B.2 OBTENER COMENTARIOS Y CONTEXTO ---
        print(f"💬 Buscando hilos para {len(unique_posts)} posts únicos...")
        all_elements = []
        filtered_posts = []
        stats_relevantes = 0
        stats_filtrados = 0

        for p in unique_posts:
            text = p.get("record", {}).get("text", "")

            es_relevante = check_relevance_sync(
                text=text,
                # images=None,  # Bluesky no ofrece imágenes en el endpoint de texto, se podría mejorar en el futuro con análisis de enlaces o similar
                tema=tema,
                keywords=keywords,
                geo_scope=geo_scope,
                languages=languages,
                desc_tema=desc_tema
            )

            if not es_relevante:
                stats_filtrados += 1
                continue

            p["_llm_relevante"] = "SI"
            filtered_posts.append(p)
            stats_relevantes += 1
        # Mapeo para no perder la relación post-hilo
        posts_to_fetch = [p for p in filtered_posts if p.get("replyCount", 0) > 0]
        tasks_threads = [fetch_post_thread(session, p["uri"], headers) for p in posts_to_fetch]
        
        # Añadir posts originales primero
        for p in unique_posts:
            p["_is_comment"] = False
            all_elements.append(p)

        if tasks_threads:
            results_threads = await asyncio.gather(*tasks_threads)
            for i, thread_obj in enumerate(results_threads):
                parent_post_data = posts_to_fetch[i]
                replies = thread_obj.get("replies", [])
                for r in replies:
                    comment_data = r.get("post")
                    if comment_data and comment_data["uri"] not in seen_uris:
                        fecha_c = parse_bluesky_date(comment_data["record"].get("createdAt", ""))
                        #if fecha_c and start_dt <= fecha_c <= end_dt:
                        seen_uris.add(comment_data["uri"])
                        comment_data["_is_comment"] = True
                        comment_data["_parent_text"] = parent_post_data["record"].get("text", "")
                        comment_data["_parent_author"] = parent_post_data["author"].get("handle")
                        comment_data["_search_keyword"] = parent_post_data.get("_search_keyword")
                        comment_data["_keyword_languages"] = parent_post_data.get("_keyword_languages")
                        all_elements.append(comment_data)

        # --- C. DESCARGA DE PERFILES ---
        unique_handles = list(set(p["author"]["handle"] for p in all_elements if p.get("author", {}).get("handle")))
        profile_map = {}
        for i in range(0, len(unique_handles), 25):
            batch = unique_handles[i : i + 25]
            profiles = await fetch_profile_batch(session, batch, headers)
            for prof in profiles:
                profile_map[prof["handle"]] = prof

        # --- D. GENERAR CSV ---
        fieldnames = [
            'post_title', 'post_selftext', 'usuario', 'Fullname', 'contenido', 'fecha', 'enlace', 
            'TipoDeTweet', 'UsuarioOriginal', 'EnlaceOriginal', 
            'comments', 'retweets', 'quotes', 'hearts', 'plays', 
            'Likes', 'Followers', 'Following', 'Tweets', 'Bio', 
            'Ubicacion', 'JoinDate', 'Website', 'IsVerified', 'IsProtected', 
            'search_keyword', 'keyword_languages'
        ]

        rows = []
        for post in all_elements:
            author = post.get("author", {})
            record = post.get("record", {})
            handle = author.get("handle")
            profile = profile_map.get(handle, {})
            is_comment = post.get("_is_comment", False)

            rows.append({
                "post_title": post.get("_parent_text", "") if is_comment else "",
                "post_selftext": post.get("_parent_text", "") if is_comment else "",
                "usuario": handle,
                "Fullname": author.get("displayName", ""),
                "contenido": record.get("text", ""),
                "fecha": record.get("createdAt", ""),
                "enlace": f"https://bsky.app/profile/{handle}/post/{post.get('uri').split('/')[-1]}",
                "TipoDeTweet": "Comentario" if is_comment else "Post",
                "UsuarioOriginal": post.get("_parent_author", "N/A"),
                "EnlaceOriginal": "N/A",
                "comments": post.get("replyCount", 0),
                "retweets": post.get("repostCount", 0),
                "quotes": post.get("quoteCount", 0),
                "hearts": post.get("likeCount", 0),
                "Likes": post.get("likeCount", 0),
                "Followers": profile.get("followersCount", 0),
                "Following": profile.get("followsCount", 0),
                "Tweets": profile.get("postsCount", 0),
                "Bio": profile.get("description", "").replace("\n", " ") if profile.get("description") else "",
                "Ubicacion": "N/A",
                "JoinDate": profile.get("createdAt", ""),
                "Website": "N/A",
                "IsVerified": author.get("verified", False),
                "IsProtected": "N/A",
                "plays": 0,
                "search_keyword": post.get("_search_keyword", ""),
                "keyword_languages": ",".join(post.get("_keyword_languages", [])),
                "llm_relevante": "SI" 
            })

        rows.sort(key=lambda x: x['fecha'], reverse=True)
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"✅ CSV Bluesky guardado: {output_file} ({len(rows)} filas)")
        print(f"\n📊 ESTADÍSTICAS:")
        print(f"  Posts encontrados: {stats['posts_encontrados']}")
        print(f"  Posts relevantes: {stats['posts_relevantes']}")
        print(f"  Posts filtrados: {stats['posts_filtrados']}")

# 🔥 CAMBIO CRÍTICO: Función principal ahora es ASYNC
async def run_bluesky(config):
    await _run_bluesky_async(config)