# ---------------------------------------------------------------
# Scraper de Bluesky: descarga posts según palabras clave
# ---------------------------------------------------------------
# Este script busca posts en la red social Bluesky usando tu usuario y contraseña,
# filtra por palabras clave y fechas, y guarda todos los datos en un archivo CSV
# que puedes abrir con Excel o Google Sheets.
# ---------------------------------------------------------------

# 1️⃣ Librerías que necesitamos
# 'requests' permite conectarse a la API de Bluesky y traer datos.
# 'csv' sirve para guardar los datos en un archivo que Excel puede leer.
# 'time' nos ayuda a pausar el script para no saturar el servidor.
# 'Path' sirve para crear carpetas automáticamente si no existen.
from clean_project.config import settings as config
import requests
import csv
import time
from pathlib import Path
from datetime import datetime, date

print("Bluesky SCRAPER INICIADO")


def parse_bluesky_date(fecha_iso):
    """
    Convierte '2025-10-01T01:48:00.123Z' → date (UTC)
    """
    try:
        return datetime.fromisoformat(
            fecha_iso.replace("Z", "+00:00")
        ).date()
    except Exception:
        return None

# ---------------------------------------------------------------
# 2️⃣ Función principal: todo el código está dentro de esta función
# ---------------------------------------------------------------
def run_bluesky(config):
    # ⚠️ Nota: este scraper solo extrae información del post principal.
    # No se descargan los comentarios de cada post; solo se registra
    # el número total de respuestas en la columna 'comments'.
    search_form_lang_map = config.general.get("search_form_lang_map", {})
    # Carpeta donde guardaremos el archivo CSV
    output_folder = config.general["output_folder"]
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/bluesky_global_dataset.csv"
    # Si el archivo ya existe, saltamos el scraper
    if Path(output_file).exists() and Path(output_file).stat().st_size > 0:
        print(f"⚠️ El archivo CSV de Bluesky ya existe en: {output_file}. Saltando este scraper...")
        return  # Salir de la función si el archivo ya existe 

    # Palabras clave que queremos buscar
    keywords = config.scraping["bluesky"]["query"]
    limit = config.scraping["bluesky"].get("limit", 100)  # Cuántos posts traer por página

    # Usuario y contraseña para entrar en Bluesky
    username = config.CREDENTIALS["bluesky"]["USERNAME_bluesky"]
    password = config.CREDENTIALS["bluesky"]["PASSWORD_bluesky"]

    # Fechas entre las cuales queremos buscar posts
    start_date = config.general["start_date"]
    end_date = config.general["end_date"]
    print(f"📅 Rango de Fechas Configurado Bluesky---------------: {start_date} <--> {end_date}")
    # ---------------------------------------------------------------
    # 3️⃣ Entrar en Bluesky (autenticación)
    # ---------------------------------------------------------------
    # Aquí pedimos un "token" que nos permite usar la API
    auth_resp = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={"identifier": username, "password": password},
    )
    access_token = auth_resp.json()["accessJwt"]  # Guardamos el token
    headers = {"Authorization": f"Bearer {access_token}"}  # Lo usamos para conectarnos después

    # Endpoint de búsqueda de posts
    url_search = "https://bsky.social/xrpc/app.bsky.feed.searchPosts"
    all_posts = []  # Lista donde guardaremos todos los posts

    # ---------------------------------------------------------------
    # 4️⃣ Buscar posts para cada palabra clave
    # ---------------------------------------------------------------


    for keyword in keywords:

        params = {
            "q": keyword,  # Palabra clave
            "limit": limit,  # Cantidad por página
            "since": f"{start_date}T00:00:00Z",
            "until": f"{end_date}T23:59:59Z",
        }
        print(f"🔹 Buscando posts para keyword: {params['q']}")
        print(f" Período de búsqueda: {params['since']} - {params['until']}")
        
        max_retries = 3  # Número máximo de intentos si hay error
        retry_count = 0
        cursor = None  # Se usa para pedir más páginas si hay muchos posts

        languages = search_form_lang_map.get(keyword, [])
        # ---------------------------------------------------------------
        # 5️⃣ Bucle que trae todos los posts usando paginación
        # ---------------------------------------------------------------
        while True:
            if cursor:
                params["cursor"] = cursor  # Continuar desde la última página

            try:
                response = requests.get(url_search, headers=headers, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                posts = data.get("posts", [])
                # guardamos las keywords y languages en cada post:
                for post in posts:
                    post["_search_keyword"] = keyword
                    post["_keyword_languages"] = languages
                    print("    ➡️ Post encontrado:")
                    print(f"{post.get("_search_keyword", "")}, {post.get("_keyword_languages", [])}")
                all_posts.extend(posts)  # Guardamos los posts encontrados
                print(f"  Recuperados {len(posts)} posts (total acumulado: {len(all_posts)})")

                cursor = data.get("cursor")  # Siguiente página
                if not cursor:
                    break  # No hay más posts, salir del bucle

                retry_count = 0
                time.sleep(0.5)  # Pausa corta para no saturar el servidor

            except requests.exceptions.RequestException as e:
                retry_count += 1
                print(f"❌ Error en la petición ({retry_count}/{max_retries}): {e}")
                if retry_count >= max_retries:
                    print("⚠️ Se alcanzó el máximo de reintentos. Saliendo del bucle...")
                    break
                time.sleep(2)  # Esperar antes de intentar de nuevo

    # ---------------------------------------------------------------
    # 6️⃣ Preparar las filas para el CSV
    # ---------------------------------------------------------------
    # Encabezados de nuestro archivo CSV
    fieldnames = [
        'usuario', 'Fullname', 'contenido', 'fecha', 'enlace', 
        'TipoDeTweet', 'UsuarioOriginal', 'EnlaceOriginal', 
        'comments', 'retweets', 'quotes', 'hearts', 'plays', 
        'Likes', 'Followers', 'Following', 'Tweets', 'Bio', 
        'Ubicacion', 'JoinDate', 'Website', 'IsVerified', 'IsProtected', 'search_keyword', 'keyword_languages'
    ]

    rows = []  # Lista donde guardaremos las filas finales
    filas_vistas = set()  # Para evitar filas duplicadas

    for post in all_posts:
        author = post.get("author", {})
        record = post.get("record", {})

        # Información básica del post
        usuario = author.get("handle")
        fullname = author.get("displayName", "")
        contenido = record.get("text", "")
        fecha = record.get("createdAt")
        fecha_post_date = parse_bluesky_date(fecha)

        start_date1 = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date1 = datetime.strptime(end_date, "%Y-%m-%d").date()
        if fecha_post_date > end_date1:
            print("ERROR: POST FUERA DE RANGO", fecha)
        # ⛔ Si no se puede parsear, descartamos
        if not fecha_post_date:
            continue
        # ⛔ FILTRO DURO POR RANGO
        if fecha_post_date < start_date1 or fecha_post_date > end_date1:
            continue
        uri = post.get("uri")
        post_id = uri.split("/")[-1] if uri else ""
        handle = author.get("handle")
        permalink = f"https://bsky.app/profile/{handle}/post/{post_id}"

        # Información del perfil del usuario
        profile_url = f"https://bsky.social/xrpc/app.bsky.actor.getProfile?actor={handle}"
        profile = requests.get(profile_url, headers=headers).json()
        Followers = profile.get("followersCount")
        Following = profile.get("followsCount")
        Tweets = profile.get("postsCount")
        Bio = profile.get("description")
        JoinDate = profile.get("createdAt")

        # Creamos la fila con todos los datos
        fila = {
            "usuario": usuario,
            "Fullname": fullname,
            "contenido": contenido,
            "fecha": fecha,
            "enlace": permalink,
            "TipoDeTweet": "Post",
            "UsuarioOriginal": "N/A",
            "EnlaceOriginal": "N/A",
            "comments": post.get("replyCount"),
            "retweets": post.get("repostCount"),
            "quotes": post.get("quoteCount"),
            "hearts": post.get("likeCount"),
            "Likes": "N/A",
            "Followers": Followers,
            "Following": Following,
            "Tweets": Tweets,
            "Bio": Bio,
            "Ubicacion": "N/A",
            "JoinDate": JoinDate,
            "Website": "N/A",
            "IsVerified": author.get("verified"),
            "IsProtected": "N/A",
            "plays": 0,
            "search_keyword": post.get("_search_keyword", ""),
            "keyword_languages": ",".join(post.get("_keyword_languages", []))
        }

        # Evitar duplicados exactos
        fila_tuple = tuple(fila.items())
        if fila_tuple in filas_vistas:
            continue
        filas_vistas.add(fila_tuple)

        rows.append(fila)

    # ---------------------------------------------------------------
    # 7️⃣ Guardar CSV
    # ---------------------------------------------------------------
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✅ CSV Bluesky guardado en: {output_file} ({len(rows)} filas)")
