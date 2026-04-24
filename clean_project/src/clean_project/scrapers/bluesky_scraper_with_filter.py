import csv
import asyncio
import aiohttp
import json
import hashlib
import re
import os
import sys
import base64
from pathlib import Path
from datetime import datetime
from openai import OpenAI

# Configuración de rutas relativas
ROOT_PATH = Path(__file__).resolve().parents[2]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

import clean_project.config.settings as config

# Cliente vLLM
client = OpenAI(base_url="http://localhost:8001/v1", api_key="local-token")
MODELO_VLM = "Qwen/Qwen2.5-VL-7B-Instruct"

# Semáforo para no saturar la red
SEM = asyncio.Semaphore(10)

# =====================================================
# 1. UTILIDADES DE APOYO
# =====================================================

def generar_id_anonimo(username):
    if not username: return "UNKNOWN"
    return hashlib.sha256(username.encode()).hexdigest()[:16].upper()

async def download_image_b64(session, url):
    """Descarga imagen de Bluesky y la pasa a B64 para el VLM."""
    if not url: return None
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                content = await resp.read()
                return base64.b64encode(content).decode('utf-8')
    except:
        return None

def parse_bluesky_date(fecha_iso):
    try:
        dt = datetime.fromisoformat(fecha_iso.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except:
        return None

# =====================================================
# 2. EL PORTERO (GATEKEEPER) MULTIMODAL
# =====================================================

async def verificar_relevancia_vlm(post_data, b64_image, u_conf):
    """
    Analiza si el post de Bluesky es relevante antes de bajar el hilo.
    """
    keywords_str = ", ".join(u_conf.general["keywords"])
    text = post_data.get("record", {}).get("text", "")
    author = post_data.get("author", {}).get("displayName", "Usuario")

    prompt = f"""
    TAREA: Determinar si este post de Bluesky es RELEVANTE.
    TEMA: {u_conf.tema}
    CONTEXTO PARA CONTEXTUALIZAR EL TEMA: {u_conf.desc_tema}
    KEYWORDS RELACIONADAS CON EL TEMA: {keywords_str}
    UBICACIÓN OBJETIVO: {u_conf.population_scope}

    DATOS DEL POST:
    - Autor: {author}
    - Texto: {text}

    REGLAS:
    1. Prioridad semántica: Si el texto trata sobre el tema o términos relacionados -> RELEVANTE.
    2. Inferencia: Si el autor o el contexto sugieren la ubicación {u_conf.population_scope} -> RELEVANTE.
    3. Imagen: Úsala solo si el texto es ambiguo.
    4. Descarte geográfico: descartar únicamente si los DATOS DEL POST mencionan explícitamente OTRO lugar no relacionado con {u_conf.population_scope}, pero no descartar solo por mencionar otras ubicaciones adicionales. 
    5. Si no se puede inferir ubicación marcar como RELEVANTE, no descartar por defecto.
    6. En caso de duda, marcar como RELEVANTE para no perder datos potencial

    Responde en JSON: {{"relevante": true/false, "razon": "...", "idioma": "..."}}
    """

    content = [{"type": "text", "text": prompt}]
    if b64_image:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}})

    try:
        response = client.chat.completions.create(
            model=MODELO_VLM,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            temperature=0
        )
        res = json.loads(response.choices[0].message.content)
        return res.get("relevante", False), res.get("razon", "N/A"), res.get("idioma", "Desconocido")
    except:
        return True, "Error en validación, se mantiene por precaución", "Desconocido"

# =====================================================
# 3. FUNCIONES DE COMUNICACIÓN BLUESKY
# =====================================================

async def fetch_posts(session, keyword, headers, start_date, end_date):
    url = "https://bsky.social/xrpc/app.bsky.feed.searchPosts"
    params = {
        "q": keyword, "limit": 50,
        "since": f"{start_date}T00:00:00Z",
        "until": f"{end_date}T23:59:59Z"
    }
    async with SEM:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status != 200: return []
            data = await resp.json()
            return data.get("posts", [])

async def fetch_thread(session, uri, headers):
    url = "https://bsky.social/xrpc/app.bsky.feed.getPostThread"
    async with SEM:
        async with session.get(url, headers=headers, params={"uri": uri, "depth": 1}) as resp:
            if resp.status != 200: return {}
            data = await resp.json()
            return data.get("thread", {})

# =====================================================
# 4. LÓGICA PRINCIPAL
# =====================================================

async def run_bluesky(u_conf):
    print(f"🚀 Bluesky Scraper Multimodal para: {u_conf.tema}")
    
    output_folder = Path(u_conf.general["output_folder"])
    output_folder.mkdir(parents=True, exist_ok=True)
    media_folder = output_folder / "media"
    media_folder.mkdir(exist_ok=True)
    start_date = config.general["start_date"]
    end_date = config.general["end_date"]
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    
    csv_path = output_folder / "bluesky_global_dataset.csv"
    
    username = config.CREDENTIALS["bluesky"]["USERNAME_bluesky"]
    password = config.CREDENTIALS["bluesky"]["PASSWORD_bluesky"]

    async with aiohttp.ClientSession() as session:
        # Auth
        async with session.post("https://bsky.social/xrpc/com.atproto.server.createSession",
                                json={"identifier": username, "password": password}) as resp:
            auth = await resp.json()
            headers = {"Authorization": f"Bearer {auth['accessJwt']}"}

        seen_uris = set()
        
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow([
                "tipo", "uri", "parent_uri", "fecha", "usuario", "id_anonimo", "contenido", 
                "likes", "reposts", "replies", "media_path", "idioma_ia", "relevancia_ia"
            ])

            for kw in u_conf.general["keywords"]:
                print(f"🔍 Buscando en Bluesky: {kw}")
                posts = await fetch_posts(session, kw, headers, u_conf.general["start_date"], u_conf.general["end_date"])

                for p in posts:
                    uri = p["uri"]
                    fecha_p_raw = p["record"]["createdAt"]
                    fecha_p = datetime.fromisoformat(fecha_p_raw.replace("Z", "+00:00")).replace(tzinfo=None) 
                    if not (start_dt <= fecha_p <= end_dt): continue
                    if uri in seen_uris: continue
                    seen_uris.add(uri)

                    # Extraer imagen si existe
                    img_url = None
                    embed = p.get("embed", {})
                    if embed.get("$type") == "app.bsky.embed.images":
                        img_url = embed["images"][0]["fullsize"]
                    
                    b64_img = await download_image_b64(session, img_url)

                    # --- PASO PORTERO ---
                    es_relevante, razon, idioma = await verificar_relevancia_vlm(p, b64_img, u_conf)
                    
                    if not es_relevante:
                        print(f"⏩ SALTADO: {p['record'].get('text', '')[:50]}... \n   └─ RAZÓN: {razon}")
                        continue

                    # Guardar imagen local
                    local_img_path = ""
                    if b64_img:
                        filename = f"bsky_{generar_id_anonimo(uri)}.jpg"
                        with open(media_folder / filename, "wb") as img_f:
                            img_f.write(base64.b64decode(b64_img))
                        local_img_path = f"media/{filename}"

                    # Guardar Post Original
                    writer.writerow([
                        "POST", uri, uri, p["record"]["createdAt"], p["author"]["handle"],
                        generar_id_anonimo(p["author"]["handle"]), p["record"]["text"],
                        p.get("likeCount", 0), p.get("repostCount", 0), p.get("replyCount", 0),
                        local_img_path, idioma, "SI"
                    ])

                    # Descargar Comentarios del hilo
                    if p.get("replyCount", 0) > 0:
                        thread = await fetch_thread(session, uri, headers)
                        for reply in thread.get("replies", []):
                            rep_post = reply.get("post", {})
                            
                            if not rep_post: continue

                            rep_local_img_path = ""
                            rep_embed = rep_post.get("embed", {})
                            
                            if rep_embed.get("$type") == "app.bsky.embed.images":
                                rep_img_url = rep_embed["images"][0]["fullsize"]
                                
                                # Descargamos la imagen de la respuesta
                                rep_b64 = await download_image_b64(session, rep_img_url)
                                if rep_b64:
                                    rep_filename = f"bsky_reply_{generar_id_anonimo(rep_post['uri'])}.jpg"
                                    with open(media_folder / rep_filename, "wb") as img_f:
                                        img_f.write(base64.b64decode(rep_b64))
                                    rep_local_img_path = f"media/{rep_filename}"    

                            writer.writerow([
                                "COMENTARIO", rep_post["uri"], uri, rep_post["record"]["createdAt"],
                                rep_post["author"]["handle"], generar_id_anonimo(rep_post["author"]["handle"]),
                                rep_post["record"]["text"], rep_post.get("likeCount", 0),
                                rep_post.get("repostCount", 0), rep_post.get("replyCount", 0),
                                rep_local_img_path, idioma, "SI"
                            ])

    print(f"✅ Bluesky finalizado. Datos en: {csv_path}")

# =====================================================
# DEBUG AISLADO
# =====================================================
if __name__ == "__main__":
    from types import SimpleNamespace
    mock_conf = SimpleNamespace(
        tema="Pantalán de Sagunto",
        desc_tema="Infraestructura portuaria renovada en Sagunto, Valencia.",
        population_scope="España",
        general={
            "output_folder": "./debug_bsky",
            "keywords": ["pantalán sagunto", "puerto sagunto"],
            "start_date": "2025-02-01",
            "end_date": "2026-04-21"
        }
    )
    asyncio.run(run_bluesky_with_filter(mock_conf))