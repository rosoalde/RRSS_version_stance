import asyncio
import csv
import json
import hashlib
import requests
import re
import os
import sys
import base64
from pathlib import Path
from datetime import datetime
import asyncpraw
from openai import OpenAI
from types import SimpleNamespace

# Configuración de rutas
ROOT_PATH = Path(__file__).resolve().parents[2]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

import clean_project.config.settings as config

# Cliente vLLM
client = OpenAI(base_url="http://localhost:8001/v1", api_key="local-token")
MODELO_VLM = "Qwen/Qwen2.5-VL-7B-Instruct"

# =====================================================
# 1. UTILIDADES
# =====================================================

def generar_id_anonimo(username):
    if not username: return "UNKNOWN"
    return hashlib.sha256(username.encode()).hexdigest()[:16].upper()

def download_to_base64(url):
    if not url: return None
    try:
        # Reddit a veces bloquea peticiones sin User-Agent
        headers = {'User-Agent': 'SocialInsight/2.0'}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return base64.b64encode(res.content).decode('utf-8')
    except: return None
    return None

def extraer_urls_imagenes(obj):
    """Extrae URLs de imágenes/GIFs de un post o comentario de Reddit."""
    urls = []
    # Caso 1: URL directa (Posts de imagen simple)
    if hasattr(obj, 'url'):
        if any(obj.url.lower().endswith(ext) for ext in ['.jpg', '.png', '.jpeg', '.gif']):
            urls.append(obj.url)
    
    # Caso 2: Media Metadata (Galerías, imágenes en comentarios o GIFs de Giphy)
    if hasattr(obj, 'media_metadata') and obj.media_metadata:
        for item in obj.media_metadata.values():
            # 's' es el objeto original, 'u' es la URL
            if 's' in item and 'u' in item['s']:
                urls.append(item['s']['u'])
    return list(set(urls)) # Deduplicar URLs

# =====================================================
# 2. EL PORTERO (GATEKEEPER) REDDIT
# =====================================================

async def verificar_relevancia_vlm_reddit(post, b64_images, u_conf):
    """
    Analiza la relevancia usando Texto + Imágenes + Nombre del Subreddit.
    """
    keywords_str = ", ".join(u_conf.general["keywords"])
    subreddit_name = post.subreddit.display_name
    
    prompt = f"""
    TAREA: Determinar si este contenido de Reddit es RELEVANTE.
    TEMA: {u_conf.tema}
    CONTEXTO: {u_conf.desc_tema}
    KEYWORDS: {keywords_str}
    UBICACIÓN OBJETIVO: {u_conf.population_scope}

    DATOS DE ENTRADA:
    - Subreddit: r/{subreddit_name}
    - Título: {post.title}
    - Texto: {post.selftext[:500]}

    REGLAS:
    1. Herencia de Contexto: Si el subreddit es de una ubicación ajena (ej: r/uruguay y buscas España), marca NO RELEVANTE.
    2. Prioridad semántica: Si trata sobre el tema o términos relacionados -> RELEVANTE.
    3. Imagen: Úsala para confirmar el contexto si el texto es breve.
    4. En caso de duda o si no se puede inferir ubicación, marcar como RELEVANTE.

    Responde en JSON: {{"relevante": true/false, "razon": "...", "idioma": "..."}}
    """

    content = [{"type": "text", "text": prompt}]
    # Añadimos hasta 2 imágenes para el análisis
    for b64 in b64_images[:2]:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

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
        return True, "Error en validación", "Desconocido"

# =====================================================
# 3. SCRAPER PRINCIPAL
# =====================================================

async def run_reddit(u_conf):
    print(f"🚀 Reddit Scraper Multimodal para: {u_conf.tema}")
    
    output_folder = Path(u_conf.general["output_folder"])
    output_folder.mkdir(parents=True, exist_ok=True)
    media_folder = output_folder / "media" / "reddit"
    media_folder.mkdir(parents=True, exist_ok=True)
    
    csv_path = output_folder / "reddit_global_dataset.csv"
    
    async with asyncpraw.Reddit(
        client_id=config.CREDENTIALS["reddit"]["reddit_client_id"],
        client_secret=config.CREDENTIALS["reddit"]["reddit_client_secret"],
        user_agent="SocialInsight/2.0"
    ) as reddit:

        all_rows = []
        seen_ids = set()
        start_dt = datetime.strptime(u_conf.general["start_date"], "%Y-%m-%d")
        end_dt = datetime.strptime(u_conf.general["end_date"], "%Y-%m-%d").replace(hour=23, minute=59, second=59)

        for kw in u_conf.general["keywords"]:
            print(f"🔍 Buscando: {kw}")
            subreddit_all = await reddit.subreddit("all")
            search_results = subreddit_all.search(f'"{kw}"', sort="relevance")

            async for post in search_results:
                if post.id in seen_ids: continue
                fecha_p = datetime.fromtimestamp(post.created_utc)
                if not (start_dt <= fecha_p <= end_dt): continue
                
                await post.load()
                seen_ids.add(post.id)

                # --- A. PROCESAR MEDIA DEL POST ---
                img_urls = extraer_urls_imagenes(post)
                b64_imgs = [download_to_base64(u) for u in img_urls]
                b64_imgs = [img for img in b64_imgs if img]

                # --- B. GATEKEEPER ---
                es_relevante, razon, idioma = await verificar_relevancia_vlm_reddit(post, b64_imgs, u_conf)

                if not es_relevante:
                    print(f"  ⏩ SALTADO: {post.title[:50]}... (Razón: {razon})")
                    continue

                # Guardar imágenes localmente
                local_paths = []
                for i, b64 in enumerate(b64_imgs):
                    filename = f"red_{post.id}_{i}.jpg"
                    with open(media_folder / filename, "wb") as f: f.write(base64.b64decode(b64))
                    local_paths.append(f"media/reddit/{filename}")

                # --- C. GUARDAR FILA POST ---
                all_rows.append({
                    "tipo": "POST",
                    "id_raiz": post.id,
                    "id_propio": post.id,
                    "fecha": fecha_p.strftime("%Y-%m-%d %H:%M"),
                    "usuario": post.author.name if post.author else "[deleted]",
                    "id_anonimo": generar_id_anonimo(post.author.name if post.author else "deleted"),
                    "contenido": post.selftext if post.selftext else post.title,
                    "likes": post.score,
                    "comments": post.num_comments,
                    "media_path": "|".join(local_paths),
                    "fuente": f"r/{post.subreddit.display_name}",
                    "idioma_ia": idioma,
                    "relevancia_ia": "SI"
                })

                # --- D. COMENTARIOS DIRECTOS ---
                await post.comments.replace_more(limit=0)
                for comment in post.comments:
                    # Extraer media de comentarios (Reddit permite 1 imagen/GIF por comentario)
                    c_urls = extraer_urls_imagenes(comment)
                    c_b64 = download_to_base64(c_urls[0]) if c_urls else None
                    c_local_path = ""
                    if c_b64:
                        c_filename = f"red_comm_{comment.id}.jpg"
                        with open(media_folder / c_filename, "wb") as f: f.write(base64.b64decode(c_b64))
                        c_local_path = f"media/reddit/{c_filename}"

                    all_rows.append({
                        "tipo": "COMENTARIO",
                        "id_raiz": post.id,
                        "id_propio": comment.id,
                        "fecha": datetime.fromtimestamp(comment.created_utc).strftime("%Y-%m-%d %H:%M"),
                        "usuario": comment.author.name if comment.author else "[deleted]",
                        "id_anonimo": generar_id_anonimo(comment.author.name if comment.author else "deleted"),
                        "contenido": comment.body,
                        "likes": comment.score,
                        "comments": len(comment.replies),
                        "media_path": c_local_path,
                        "fuente": f"r/{post.subreddit.display_name}",
                        "idioma_ia": idioma,
                        "relevancia_ia": "SI"
                    })

        # Guardar CSV
        if all_rows:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=all_rows[0].keys(), delimiter=';')
                writer.writeheader()
                writer.writerows(all_rows)


# =====================================================
# DEBUG AISLADO
# =====================================================
if __name__ == "__main__":
    mock_conf = SimpleNamespace(
        tema="Pantalán de Sagunto",
        desc_tema="Renovación de la infraestructura portuaria en Sagunto.",
        population_scope="España",
        languages=["es"],
        general={
            "output_folder": "./debug_reddit",
            "keywords": ["pantalán sagunto", "puerto sagunto"],
            "start_date": "2025-02-01",
            "end_date": "2026-04-21"
        },
        scraping={"reddit": {"limit": 10}}
    )
    asyncio.run(run_reddit(mock_conf))