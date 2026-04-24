import pandas as pd
from pathlib import Path
import time
import re
import json
import concurrent.futures
from openai import OpenAI
from types import SimpleNamespace
import os
import base64
from collections import Counter
import numpy as np

# =====================================================
# CONFIGURACIÓN vLLM
# =====================================================

client = OpenAI(
    base_url="http://localhost:8001/v1",
    api_key="local-token",
    timeout=60.0
)

# MODELO MULTIMODAL para análisis con imágenes
MODELO_VISION = "Qwen/Qwen2.5-VL-7B-Instruct"
# MODELO TEXTO para análisis rápido sin imágenes
MODELO_TEXTO = "Qwen/Qwen2.5-VL-7B-Instruct"#"Qwen/Qwen2.5-14B-Instruct"

MICRO_BATCH_SIZE = 5  # Reducido para análisis multimodal
MAX_RETRIES = 2
NUM_CTX = 4000

# Memoria Global de Tópicos (con consolidación)
TOPIC_MEMORY = {}  # {topic_normalizado: count}
MAX_TOPICS = 20  # Límite máximo de topics únicos

# =====================================================
# UTILIDADES DE IMÁGENES
# =====================================================

def encode_image_base64(image_path):
    """Codifica imagen a base64 para el modelo"""
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        print(f"⚠️ Error codificando imagen {image_path}: {e}")
        return None

def load_image_from_path(media_path):
    """
    Carga imágenes desde media_path.
    Formato esperado: JSON array ["path1.jpg", "path2.png"]
    """
    if not media_path or pd.isna(media_path) or str(media_path).strip() in ["", "[]", "nan"]:
        return []
    
    try:
        paths = json.loads(media_path)
        if isinstance(paths, list):
            return [p for p in paths if p and os.path.exists(p)]
        elif isinstance(paths, str) and os.path.exists(paths):
            return [paths]
    except:
        # Si no es JSON, asumimos que es un path directo
        if os.path.exists(str(media_path)):
            return [str(media_path)]
    
    return []

def load_transcript(transcript_path):
    """Carga transcripción desde JSON"""
    if not transcript_path or pd.isna(transcript_path) or not os.path.exists(str(transcript_path)):
        return ""
    
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Formato: [{"text": "...", "start": ..., "duration": ...}, ...]
            if isinstance(data, list):
                return " ".join([segment.get("text", "") for segment in data])
            elif isinstance(data, str):
                return data
    except:
        pass
    
    return ""

# =====================================================
# EXTRACTOR JSON ROBUSTO
# =====================================================

def extraer_json_clasificacion(raw):
    """Extrae clasificación del JSON del modelo"""
    if not raw or not isinstance(raw, str):
        return 2, "error", "Desconocido"
    
    raw = raw.strip()
    
    # Intento 1: JSON directo
    try:
        data = json.loads(raw)
        return validar_json(data)
    except:
        pass
    
    # Intento 2: Limpiar markdown
    raw_clean = re.sub(r"```json|```", "", raw, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(raw_clean)
        return validar_json(data)
    except:
        pass
    
    # Intento 3: Extraer el JSON más grande
    def extract_largest_json(text):
        stack = []
        start_index = None
        candidates = []
        for i, char in enumerate(text):
            if char == "{":
                if not stack:
                    start_index = i
                stack.append(char)
            elif char == "}":
                if stack:
                    stack.pop()
                    if not stack and start_index is not None:
                        candidates.append(text[start_index:i+1])
        return max(candidates, key=len) if candidates else None
    
    bloque = extract_largest_json(raw_clean)
    if bloque:
        try:
            bloque = re.sub(r',\s*}', '}', bloque)
            bloque = re.sub(r',\s*]', ']', bloque)
            data = json.loads(bloque)
            return validar_json(data)
        except:
            pass
    
    # Intento 4: Regex de emergencia
    try:
        sent_match = re.search(r'"?sentimiento"?\s*:\s*"?(-?1|0|2)"?', raw, re.IGNORECASE)
        topic_match = re.search(r'"?topic"?\s*:\s*"([^"]+)"', raw, re.IGNORECASE)
        lang_match = re.search(r'"?Idioma_Real"?\s*:\s*"([^"]+)"', raw, re.IGNORECASE)
        
        sentimiento = int(sent_match.group(1)) if sent_match else 2
        topic = topic_match.group(1).strip() if topic_match else "error"
        idioma = lang_match.group(1).strip() if lang_match else None
        
        return sentimiento, topic, idioma
    except:
        pass
    
    return 2, "error", None

def validar_json(data):
    """Valida y extrae datos del JSON"""
    if not isinstance(data, dict):
        return 2, "no relacionado", "Desconocido"
    
    filtro = data.get("Verificacion_Filtro", {})
    idioma_detectado = str(filtro.get("Idioma_Real") or "Desconocido")
    pasa = str(filtro.get("Pasa_el_filtro", "")).upper()
    
    if "NO" in pasa:
        return 2, "no relacionado", idioma_detectado
    
    if "Topics" in data and isinstance(data["Topics"], list) and data["Topics"]:
        item = data["Topics"][0]
        topic = item.get("Topic", "no relacionado")
        sentimiento = item.get("Sentimiento", 2)
        
        try:
            sentimiento = int(sentimiento)
        except:
            sentimiento = 2
        
        if sentimiento not in [1, -1, 0, 2]:
            sentimiento = 2
        
        return sentimiento, str(topic).strip(), idioma_detectado
    
    return 2, "no relacionado", idioma_detectado

# =====================================================
# PREPARACIÓN DE CONTEXTO SEGÚN NUEVO ESQUEMA
# =====================================================

def preparar_contexto_multimodal(row, df_completo, red_social):
    """
    Prepara contexto completo incluyendo:
    - Texto del comentario
    - Contexto del post/video padre
    - Imágenes (si hay)
    - Transcripción (si hay)
    
    Returns:
        {
            "texto": str,
            "imagenes": [base64_strings],
            "tiene_media": bool
        }
    """
    
    def safe_text(val):
        if val is None or pd.isna(val) or str(val).strip().lower() in ["nan", "", "none"]:
            return ""
        return str(val).strip()
    
    # Textos basura
    contenido = safe_text(row.get("contenido"))
    if contenido.lower() in ["[removed]", "[deleted]", "nan", "", "none"]:
        return {"texto": "BORRADO", "imagenes": [], "tiene_media": False}
    
    tipo = safe_text(row.get("tipo"))
    es_comentario = tipo.lower() in ["comentario", "comment", "reply"]
    
    # ========================================
    # CONSTRUCCIÓN DE TEXTO
    # ========================================
    
    texto_partes = []
    
    # 1. CONTENIDO PRINCIPAL
    texto_partes.append(f"[CONTENIDO]\n{contenido}")
    
    # 2. CONTEXTO DEL PADRE (para comentarios)
    if es_comentario:
        if red_social == "reddit":
            # Buscar post padre por id_raiz
            id_raiz = safe_text(row.get("id_raiz"))
            if id_raiz:
                post_padre = df_completo[
                    (df_completo["tipo"] == "Post") & 
                    (df_completo["id_raiz"] == id_raiz)
                ]
                if not post_padre.empty:
                    padre_contenido = safe_text(post_padre.iloc[0].get("contenido"))
                    padre_fuente = safe_text(post_padre.iloc[0].get("fuente"))
                    
                    if padre_fuente:
                        texto_partes.insert(0, f"[SUBREDDIT]\n{padre_fuente}")
                    if padre_contenido:
                        texto_partes.insert(1, f"[POST PADRE]\n{padre_contenido[:500]}")
        
        elif red_social == "youtube":
            # Para YouTube, todos los comentarios comparten id_video
            id_video = safe_text(row.get("id_video"))
            titulo_video = safe_text(row.get("titulo_video"))
            
            if titulo_video:
                texto_partes.insert(0, f"[TÍTULO VIDEO]\n{titulo_video}")
            
            # Buscar transcripción del video
            transcripcion_path = safe_text(row.get("transcripcion"))
            if transcripcion_path:
                transcript_text = load_transcript(transcripcion_path)
                if transcript_text:
                    # Limitar transcripción a 1000 caracteres
                    texto_partes.insert(1, f"[TRANSCRIPCIÓN (extracto)]\n{transcript_text[:1000]}")
        
        elif red_social == "bluesky":
            # Buscar post padre por parent_uri
            parent_uri = safe_text(row.get("parent_uri"))
            if parent_uri:
                post_padre = df_completo[
                    (df_completo["tipo"] == "Post") & 
                    (df_completo["uri"] == parent_uri)
                ]
                if not post_padre.empty:
                    padre_contenido = safe_text(post_padre.iloc[0].get("contenido"))
                    if padre_contenido:
                        texto_partes.insert(0, f"[POST PADRE]\n{padre_contenido[:500]}")
    
    # 3. Para posts de YouTube, añadir transcripción completa
    elif red_social == "youtube" and tipo.lower() == "video":
        transcripcion_path = safe_text(row.get("transcripcion"))
        titulo_video = safe_text(row.get("titulo_video"))
        
        if titulo_video:
            texto_partes.insert(0, f"[TÍTULO]\n{titulo_video}")
        
        if transcripcion_path:
            transcript_text = load_transcript(transcripcion_path)
            if transcript_text:
                # Para videos (no comentarios), usar más transcripción
                texto_partes.append(f"[TRANSCRIPCIÓN]\n{transcript_text[:2000]}")
    
    texto_final = "\n\n".join(texto_partes)
    
    # ========================================
    # CARGA DE IMÁGENES
    # ========================================
    
    imagenes_base64 = []
    media_path = row.get("media_path")
    
    if media_path and not pd.isna(media_path):
        image_paths = load_image_from_path(media_path)
        
        # Limitar a 3 imágenes por eficiencia
        for img_path in image_paths[:3]:
            b64 = encode_image_base64(img_path)
            if b64:
                imagenes_base64.append(b64)
    
    return {
        "texto": texto_final,
        "imagenes": imagenes_base64,
        "tiene_media": len(imagenes_base64) > 0
    }

# =====================================================
# GESTIÓN DE TOPICS (CON CONSOLIDACIÓN)
# =====================================================

import unicodedata
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def normalizar_topic(t):
    """Normaliza topic para consolidación"""
    if not t:
        return "error"
    
    t = str(t).strip().lower()
    t = re.sub(r'[^\w\s]', '', t).replace('_', ' ')
    t = re.sub(r'\s+', ' ', t)
    
    # Quitar acentos
    t = ''.join(c for c in unicodedata.normalize('NFD', t) 
                if unicodedata.category(c) != 'Mn')
    
    return t

def consolidar_topic(nuevo_topic):
    """
    Consolida topics similares usando similitud semántica.
    Si el nuevo topic es muy similar a uno existente, usa el existente.
    """
    if not TOPIC_MEMORY:
        TOPIC_MEMORY[nuevo_topic] = 1
        return nuevo_topic
    
    # Vectorizar topics existentes + nuevo
    topics_existentes = list(TOPIC_MEMORY.keys())
    todos_topics = topics_existentes + [nuevo_topic]
    
    try:
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(todos_topics)
        
        # Calcular similitud del nuevo con todos los existentes
        similarities = cosine_similarity(
            tfidf_matrix[-1:],  # nuevo topic
            tfidf_matrix[:-1]   # existentes
        )[0]
        
        # Si hay similitud > 0.85, usar el existente más popular
        max_sim = max(similarities) if len(similarities) > 0 else 0
        
        if max_sim > 0.85:
            # Encontrar el más similar
            idx_similar = similarities.argmax()
            topic_similar = topics_existentes[idx_similar]
            
            # Incrementar contador
            TOPIC_MEMORY[topic_similar] += 1
            return topic_similar
        else:
            # Es suficientemente diferente, añadir como nuevo
            TOPIC_MEMORY[nuevo_topic] = 1
            
            # Si superamos el límite, eliminar el menos frecuente
            if len(TOPIC_MEMORY) > MAX_TOPICS:
                topic_menos_comun = min(TOPIC_MEMORY, key=TOPIC_MEMORY.get)
                del TOPIC_MEMORY[topic_menos_comun]
            
            return nuevo_topic
            
    except Exception as e:
        # Si falla la consolidación, añadir directamente
        TOPIC_MEMORY[nuevo_topic] = TOPIC_MEMORY.get(nuevo_topic, 0) + 1
        return nuevo_topic

def construir_contexto_topics():
    """Crea bloque de topics para el prompt"""
    if not TOPIC_MEMORY:
        return "\n(Aún no se han detectado tópicos. Crea el primero basado en el argumento).\n"
    
    # Ordenar por frecuencia (más comunes primero)
    topics_ordenados = sorted(
        TOPIC_MEMORY.items(),
        key=lambda x: x[1],
        reverse=True
    )[:15]  # Top 15
    
    topics_str = ", ".join([t[0] for t in topics_ordenados])
    
    return f"""
=== TÓPICOS MÁS COMUNES (Úsalos si el argumento coincide) ===
{topics_str}

⚠️ REGLA CRÍTICA: Si el argumento del comentario es muy similar a uno de estos,
USA EXACTAMENTE el tópico existente. No crees variantes.
"""

# =====================================================
# PROMPTS
# =====================================================

def build_prompts(tema, desc_tema, keywords_list, population_scope, languages):
    keywords_str = ", ".join(keywords_list)
    langs = ", ".join(languages) if languages else "Cualquiera"
    geo_instruction = ""
    if "GLOBAL" in population_scope.upper():
        geo_instruction = "2. GEOGRAFÍA:\n"
        geo_instruction += " Filtro desactivado. Acepta comentarios de cualquier ubicación geográfica."
    else:
        geo_instruction = f"2. GEOGRAFÍA:\n"
        geo_instruction += f" Considerar RELEVANTE si el autor, el contexto o la falta de información permiten inferir la ubicación {population_scope}."
        geo_instruction += f" Descartar únicamente cuando los datos indiquen de forma explícita otra ubicación no relacionada con {population_scope},"
        geo_instruction += f" sin penalizar menciones adicionales de otros lugares."
    
    system = (
        "Eres un auditor de datos para social listening. "
        "Tu prioridad es ELIMINAR ruido antes de clasificar. "
        "Todos los 'Topic' deben estar en CASTELLANO. "
        "Salida: JSON exclusivamente."
    )
    
    user_template = f"""
--- MARCO DE CONTROL ---
- Tema central de análisis: {tema}
- Descripción técnica: {desc_tema}
- Idiomas permitidos: {langs}
- Ubicación permitida: {population_scope}

--- INSTRUCCIONES CLARAS ---
1. ANALIZA SOLO el bloque [CONTENIDO] para sentimiento y topic
2. Usa [TÍTULO POST], [TRANSCRIPCIÓN], etc. SOLO como contexto auxiliar
3. El topic explica el ARGUMENTO del [CONTENIDO], NO repetir el tema general

--- CONTENIDO A ANALIZAR ---
CONTENIDO_ANALIZAR

🚨 PASO 0: FILTRO DE EXCLUSIÓN 🚨

Excluye (marca Sentimiento=2, Topic="no relacionado") si:
1. IDIOMA: El texto del COMENTARIO NO está en {langs}
{geo_instruction}
3. SPAM/PUBLICIDAD: mensajes sin texto coherente o que promueven productos/servicios sin relación con "{tema}".
4. AJENO: No relacionado con "{tema}"

⚠️ NO excluyas noticias/citas relevantes al tema.

--- PASO 1: POSICIONAMIENTO (solo si PASÓ filtro) ---

Determina la POSTURA sobre "{tema}":
- "1": A favor / Positivo / Beneficios
- "-1": En contra / Crítica / Problemas
- "0": Neutro / Informativo / Equilibrado
- "2": Irrelevante (según Paso 0)

--- PASO 2: TÓPICO (el PORQUÉ del posicionamiento) ---

🚨 REGLAS CRÍTICAS:
1. NO uses "{tema}" ni "{keywords_str}" como tópico
2. El tópico es el ARGUMENTO o ÁNGULO específico
3. Revisa TÓPICOS EXISTENTES abajo - si coincide, USA EL MISMO
4. Debe ser autoexplicativo (2-4 palabras en castellano)

Ejemplos de construcción:
- Si el usuario apoya o se posiciona positivamente con respecto al tema (1): 
    1. Resaltando un beneficio: "Mejora de [aspecto]", "Eficiencia en [aspecto]", "Necesidad de [aspecto]".
    2. Apoyando el tema criticando un obstáculo: Usa "Crítica a [problema/entidad]", "Denuncia de [obstáculo]", "Rechazo a [lo que impide el tema]".
- Si el usuario critica o se posiciona negativamente con respecto al tema (-1):
    1. Resaltando un fallo: "Riesgo de [consecuencia]", "Impacto negativo en [aspecto]", "Falta de [recurso]".
    2. Criticando el diseño/coste: "Coste excesivo", "Mala gestión de [aspecto]", "Inviabilidad de [tema]".
    3. Expresa un valor ético: "Injusticia en [aspecto]", "Vulneración de [derecho/norma]".
- Si el usuario es NEUTRAL (0):
    1. Describe la acción: "Información sobre [aspecto]", "Consulta técnica", "Procedimiento de [tema]".    


__TOPICS_EXISTENTES__

--- FORMATO JSON ---
{{
  "Verificacion_Filtro": {{
    "Idioma_Real": "<idioma detectado en el texto del CONTENIDO>",
    "Ubicacion_Real": "<lugar mencionado o 'Desconocida' hallado o inferido a partir del CONTENIDO_ANALIZAR>",
    "Relevancia_Tematica": "Explica brevemente si el CONTENIDO está relacionado con el tema central o no, basándote en el texto y contexto. Si es irrelevante, explica por qué.",
    "Pasa_el_filtro": "SÍ o NO"
  }},
  "Topics": [
    {{
      "Topic": "<argumento_especifico_en_castellano>",
      "Sentimiento": "<1|-1|0|2>"
    }}
  ]
}}
"""
    
    return system, user_template

# =====================================================
# TRABAJADOR vLLM
# =====================================================

def call_vllm_worker(contexto, system_prompt, user_template, usar_vision=False):
    """
    Llama al modelo vLLM con o sin imágenes.
    
    Args:
        contexto: dict con {texto, imagenes, tiene_media}
        system_prompt: prompt del sistema
        user_template: template del usuario
        usar_vision: bool, si usar modelo de visión
    """
    
    if contexto["texto"] == "BORRADO":
        return 2, "no relacionado", None
    
    # Construir contexto de topics
    contexto_topics = construir_contexto_topics()
    
    # Inyectar en prompt
    prompt_final = user_template.replace("__TOPICS_EXISTENTES__", contexto_topics)
    prompt_final = prompt_final.replace("__CONTENIDO_ANALIZAR__", contexto["texto"])
    
    # Decidir modelo
    modelo = MODELO_VISION #if usar_vision and contexto["tiene_media"] else MODELO_TEXTO
    
    # Construir mensajes
    messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    # Si hay imágenes, añadirlas al contenido
    if usar_vision and contexto["tiene_media"]:
        user_content = [
            {"type": "text", "text": prompt_final}
        ]
        
        # Añadir imágenes (máx 3)
        for img_b64 in contexto["imagenes"][:3]:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}"
                }
            })
        
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": prompt_final})
    
    # Llamar al modelo
    for intento in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=modelo,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=3000
            )
            
            raw = response.choices[0].message.content
            sentimiento, topic_raw, idioma_ia = extraer_json_clasificacion(raw)
            
            # Normalizar y consolidar topic
            topic_norm = normalizar_topic(topic_raw)
            
            if topic_norm not in ["error", "no relacionado", "comercializacion"]:
                topic_final = consolidar_topic(topic_norm)
            else:
                topic_final = topic_norm
            
            if sentimiento in [1, -1, 0]:
                print(f"✅ Clasificado: Sent={sentimiento}, Topic='{topic_final}', Idioma='{idioma_ia}'")
            
            return sentimiento, topic_final, idioma_ia
            
        except Exception as e:
            print(f"⚠️ Error en intento {intento + 1}: {e}")
            time.sleep(1)
    
    return 2, "error", None

# =====================================================
# PIPELINE PRINCIPAL
# =====================================================

def llm_analysis(u_conf, usar_vision=False):
    """
    Análisis principal con soporte multimodal opcional.
    
    Args:
        u_conf: configuración
        usar_vision: bool, si activar análisis de imágenes
    """
    
    print("\n🚀 ANÁLISIS DE SENTIMIENTO + STANCE (vLLM)")
    print(f"   Modo visión: {'✅ ACTIVADO' if usar_vision else '❌ DESACTIVADO'}")
    
    data_folder = Path(u_conf.general["output_folder"])
    
    # Cargar memoria de topics
    memory_file = data_folder / "learned_topics.json"
    if memory_file.exists():
        with open(memory_file, "r", encoding="utf-8") as f:
            topics_previos = json.load(f)
            for t in topics_previos:
                TOPIC_MEMORY[t] = TOPIC_MEMORY.get(t, 0) + 1
    
    # Construir prompts
    system_p, user_t = build_prompts(
        u_conf.tema,
        u_conf.desc_tema,
        u_conf.general["keywords"],
        u_conf.population_scope,
        u_conf.languages
    )
    
    # Buscar archivos de datos
    archivos = list(data_folder.glob("*_global_dataset.csv"))
    
    for archivo in archivos:
        # Detectar red social
        nombre = archivo.stem.lower()
        if "reddit" in nombre:
            red_social = "reddit"
        elif "youtube" in nombre:
            red_social = "youtube"
        elif "bluesky" in nombre:
            red_social = "bluesky"
        else:
            continue
        
        print(f"\n=== Procesando: {archivo.name} ({red_social}) ===")
        
        # Cargar DataFrame
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                sep = ';' if ';' in f.readline() else ','
            
            df = pd.read_csv(archivo, sep=sep, encoding='utf-8', 
                           engine='python', on_bad_lines='skip')
            
            # Limpiar filas vacías
            if 'contenido' in df.columns:
                df = df.dropna(subset=['contenido'])
                df = df[df['contenido'].astype(str).str.strip() != ""]
                df = df.reset_index(drop=True)
            
            if df.empty:
                continue
                
        except Exception as e:
            print(f"❌ Error cargando: {e}")
            continue
        
        # Añadir columnas de análisis si no existen
        for col in ["sentimiento", "topic", "IDIOMA_IA"]:
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].fillna("").astype(str).str.strip()
        
        # Identificar pendientes
        mask_pendiente = (
            (df["sentimiento"] == "") | (df["sentimiento"] == "nan") |
            (df["topic"] == "") | (df["topic"] == "nan")
        )
        
        # FILTRO ADICIONAL: Solo analizar contenido RELEVANTE según LLM previo
        if "relevancia_ia" in df.columns:
            mask_pendiente = mask_pendiente & (df["relevancia_ia"] == "SI")
        
        indices_pendientes = df[mask_pendiente].index.tolist()
        total = len(df)
        pendientes = len(indices_pendientes)
        
        if pendientes == 0:
            print(f"✅ Ya analizado al 100%")
            continue
        
        print(f"📊 Pendientes: {pendientes} / {total}")
        
        # Procesar por lotes
        analizado_path = archivo.with_name(archivo.stem + "_analizado.csv")
        
        for i in range(0, pendientes, MICRO_BATCH_SIZE):
            batch_indices = indices_pendientes[i : i + MICRO_BATCH_SIZE]
            
            print(f"\n  Lote {i//MICRO_BATCH_SIZE + 1} ({len(batch_indices)} items)...")
            
            # Preparar contextos multimodales
            contextos = {}
            for idx in batch_indices:
                contextos[idx] = preparar_contexto_multimodal(
                    df.loc[idx],
                    df,  # DataFrame completo para buscar padres
                    red_social
                )
            
            # Procesar en paralelo
            with concurrent.futures.ThreadPoolExecutor(max_workers=MICRO_BATCH_SIZE) as executor:
                futures = {
                    executor.submit(
                        call_vllm_worker,
                        contextos[idx],
                        system_p,
                        user_t,
                        usar_vision
                    ): idx
                    for idx in batch_indices
                }
                
                for future in concurrent.futures.as_completed(futures):
                    idx = futures[future]
                    try:
                        sent, top, idioma = future.result()
                        df.loc[idx, "sentimiento"] = str(sent)
                        df.loc[idx, "topic"] = str(top)
                        df.loc[idx, "IDIOMA_IA"] = str(idioma)
                    except Exception as e:
                        print(f"❌ Error en fila {idx}: {e}")
            
            # Guardar progreso
            df.to_csv(analizado_path, index=False, sep=';', encoding='utf-8')
            print(f"  💾 Guardado")
        
        print(f"\n✅ {archivo.name} completado")
    
    # Guardar memoria de topics
    with open(memory_file, "w", encoding="utf-8") as f:
        json.dump(list(TOPIC_MEMORY.keys()), f, ensure_ascii=False, indent=2)
    
    # Mostrar estadísticas de topics
    print(f"\n📊 TOPICS DETECTADOS ({len(TOPIC_MEMORY)}):")
    for topic, count in sorted(TOPIC_MEMORY.items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"  • {topic}: {count}")
    
    print(f"\n✨ Análisis finalizado")

# =====================================================
# EJECUCIÓN
# =====================================================

if __name__ == "__main__":
    
    # Configuración de prueba
    u_conf = SimpleNamespace(
        tema="LUX TOUR",#"Transporte público Valencia",
        desc_tema="La cuarta gira de conciertos de la cantante española Rosalía, promoviendo su álbum 'Lux', comenzará el 16 de marzo de 2026 en Lyon, Francia, y finalizará el 3 de septiembre de 2026 en San Juan, Puerto Rico.",
        population_scope="GLOBAL",
        languages=["Castellano", "Catalan"],
        general={
            "output_folder": "/home/rrss/proyecto_web/RRSS_version_stance/project_web/Web_Proyecto/datos/admin/ROSALIA",
            "keywords": ["Rosalía LUX 2026", "conciertos rosalía 2026", "lux tour rosalía", "rosalía en gira 2026"]
        }
    )
    
    # Ejecutar con o sin visión
    USAR_VISION = True  # Cambiar a True para análisis con imágenes
    
    llm_analysis(u_conf, usar_vision=USAR_VISION)