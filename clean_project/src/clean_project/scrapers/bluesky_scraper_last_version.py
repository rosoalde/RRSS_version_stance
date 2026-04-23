# ---------------------------------------------------------------
# Scraper de Bluesky OPTIMIZADO (ASYNC) - CORREGIDO
# ---------------------------------------------------------------
import csv
import asyncio
import aiohttp
import sys
from pathlib import Path
from datetime import datetime

# Imports de tu proyecto
from clean_project.config import settings as config

print("Bluesky SCRAPER OPTIMIZADO INICIADO")

# Semáforo para no saturar la API (máximo 10 peticiones simultáneas)
SEM = asyncio.Semaphore(10)

def parse_bluesky_date(fecha_iso):
    try:
        return datetime.fromisoformat(fecha_iso.replace("Z", "+00:00")).date()
    except Exception:
        return None

# ---------------------------------------------------------------
# 1. FUNCIÓN PARA BUSCAR POSTS DE UNA KEYWORD (ASYNC)
# ---------------------------------------------------------------
async def fetch_posts_for_keyword(session, keyword, headers, limit, start_date, end_date, search_form_lang_map):
    url_search = "https://bsky.social/xrpc/app.bsky.feed.searchPosts"
    params = {
        "q": keyword,
        "limit": limit,
        "since": f"{start_date}T00:00:00Z",
        "until": f"{end_date}T23:59:59Z",
    }
    
    posts_collected = []
    cursor = None
    languages = search_form_lang_map.get(keyword, [])
    
    print(f"🔹 Iniciando búsqueda para: {keyword}")

    while True:
        if cursor: params["cursor"] = cursor
        
        async with SEM: # Respetar el límite de conexiones
            try:
                async with session.get(url_search, headers=headers, params=params, timeout=15) as response:
                    if response.status != 200:
                        print(f"⚠️ Error {response.status} en keyword {keyword}")
                        break
                    
                    data = await response.json()
                    posts = data.get("posts", [])
                    
                    for post in posts:
                        post["_search_keyword"] = keyword
                        post["_keyword_languages"] = languages
                    
                    posts_collected.extend(posts)
                    
                    cursor = data.get("cursor")
                    if not cursor:
                        break
                    
                    # Pequeña pausa para no ser bloqueado
                    await asyncio.sleep(0.2)
                    
            except Exception as e:
                print(f"❌ Error de red en keyword {keyword}: {e}")
                break
    
    print(f"✅ Fin keyword '{keyword}': {len(posts_collected)} posts.")
    return posts_collected

# ---------------------------------------------------------------
# 2. FUNCIÓN PARA DESCARGAR UN LOTE DE PERFILES (ASYNC)
# ---------------------------------------------------------------
async def fetch_profile_batch(session, batch, headers):
    url_profiles = "https://bsky.social/xrpc/app.bsky.actor.getProfiles"
    # La API espera ?actors=user1&actors=user2...
    params = [("actors", h) for h in batch]
    
    async with SEM:
        try:
            async with session.get(url_profiles, headers=headers, params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("profiles", [])
        except Exception as e:
            print(f"⚠️ Error descargando lote de perfiles: {e}")
    return []

# ---------------------------------------------------------------
# 3. LÓGICA PRINCIPAL ASÍNCRONA (Renombrada con guion bajo)
# ---------------------------------------------------------------
async def _run_bluesky_async(config):
    search_form_lang_map = config.general.get("search_form_lang_map", {})
    output_folder = config.general["output_folder"]
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/bluesky_global_dataset.csv"
    
    if Path(output_file).exists() and Path(output_file).stat().st_size > 0:
        print(f"⚠️ El archivo CSV de Bluesky ya existe. Saltando...")
        return

    keywords = config.scraping["bluesky"]["query"]
    limit = config.scraping["bluesky"].get("limit", 100)
    username = config.CREDENTIALS["bluesky"]["USERNAME_bluesky"]
    password = config.CREDENTIALS["bluesky"]["PASSWORD_bluesky"]
    start_date = config.general["start_date"]
    end_date = config.general["end_date"]
    
    print(f"📅 Rango: {start_date} <--> {end_date}")

    async with aiohttp.ClientSession() as session:
        # --- A. AUTENTICACIÓN ---
        try:
            async with session.post(
                "https://bsky.social/xrpc/com.atproto.server.createSession",
                json={"identifier": username, "password": password},
                timeout=10
            ) as resp:
                if resp.status != 200:
                    print(f"❌ Error Auth: {resp.status}")
                    return
                auth_data = await resp.json()
                access_token = auth_data["accessJwt"]
                headers = {"Authorization": f"Bearer {access_token}"}
        except Exception as e:
            print(f"❌ Excepción Auth: {e}")
            return

        # --- B. BÚSQUEDA DE POSTS (PARALELA) ---
        print("🚀 Lanzando búsquedas de keywords en paralelo...")
        tasks_posts = [
            fetch_posts_for_keyword(session, kw, headers, limit, start_date, end_date, search_form_lang_map)
            for kw in keywords
        ]
        results_posts = await asyncio.gather(*tasks_posts)
        
        # Aplanar lista de listas
        all_posts = [p for sublist in results_posts for p in sublist]
        print(f"📦 Total posts recolectados: {len(all_posts)}")

        # --- C. DESCARGA DE PERFILES (PARALELA POR LOTES) ---
        print("🚀 Descargando perfiles en paralelo...")
        unique_handles = list(set(p.get("author", {}).get("handle") for p in all_posts if p.get("author", {}).get("handle")))
        
        batch_size = 25
        tasks_profiles = []
        
        for i in range(0, len(unique_handles), batch_size):
            batch = unique_handles[i : i + batch_size]
            tasks_profiles.append(fetch_profile_batch(session, batch, headers))
            
        results_profiles = await asyncio.gather(*tasks_profiles)
        
        # Construir mapa de perfiles
        profile_map = {}
        for batch_res in results_profiles:
            for prof in batch_res:
                profile_map[prof["handle"]] = prof

        # --- D. GENERAR CSV ---
        print("💾 Guardando CSV...")
        fieldnames = [
            'usuario', 'Fullname', 'contenido', 'fecha', 'enlace', 
            'TipoDeTweet', 'UsuarioOriginal', 'EnlaceOriginal', 
            'comments', 'retweets', 'quotes', 'hearts', 'plays', 
            'Likes', 'Followers', 'Following', 'Tweets', 'Bio', 
            'Ubicacion', 'JoinDate', 'Website', 'IsVerified', 'IsProtected', 'search_keyword', 'keyword_languages'
        ]

        rows = []
        filas_vistas = set()
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()

        for post in all_posts:
            author = post.get("author", {})
            record = post.get("record", {})
            handle = author.get("handle")

            # Filtro fecha estricto
            fecha_str = record.get("createdAt")
            if not fecha_str: continue
            fecha_post_date = parse_bluesky_date(fecha_str)
            if not fecha_post_date: continue
            if fecha_post_date < start_date_obj or fecha_post_date > end_date_obj: continue

            profile = profile_map.get(handle, {})
            uri = post.get("uri")
            post_id = uri.split("/")[-1] if uri else ""
            permalink = f"https://bsky.app/profile/{handle}/post/{post_id}"

            fila = {
                "usuario": handle,
                "Fullname": author.get("displayName", ""),
                "contenido": record.get("text", ""),
                "fecha": fecha_str,
                "enlace": permalink,
                "TipoDeTweet": "Post",
                "UsuarioOriginal": "N/A",
                "EnlaceOriginal": "N/A",
                "comments": post.get("replyCount", 0),
                "retweets": post.get("repostCount", 0),
                "quotes": post.get("quoteCount", 0),
                "hearts": post.get("likeCount", 0),
                "Likes": "N/A",
                "Followers": profile.get("followersCount", 0),
                "Following": profile.get("followsCount", 0),
                "Tweets": profile.get("postsCount", 0),
                "Bio": profile.get("description", "").replace("\n", " "),
                "Ubicacion": "N/A",
                "JoinDate": profile.get("createdAt", ""),
                "Website": "N/A",
                "IsVerified": author.get("verified", False),
                "IsProtected": "N/A",
                "plays": 0,
                "search_keyword": post.get("_search_keyword", ""),
                "keyword_languages": ",".join(post.get("_keyword_languages", []))
            }

            fila_tuple = tuple(fila.items())
            if fila_tuple in filas_vistas: continue
            filas_vistas.add(fila_tuple)
            rows.append(fila)

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"✅ CSV Bluesky guardado: {output_file} ({len(rows)} filas)")

# ---------------------------------------------------------------
# 4. PUNTO DE ENTRADA SÍNCRONO (WRAPPER)
# ---------------------------------------------------------------
def run_bluesky(config):
    """
    Esta función es la que llama pipeline.py.
    Se encarga de ejecutar la lógica asíncrona dentro de asyncio.run()
    """
    # Solución específica para Windows si usas Python 3.8+ y aiohttp
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(_run_bluesky_async(config))