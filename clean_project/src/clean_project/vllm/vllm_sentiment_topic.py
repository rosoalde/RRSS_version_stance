import pandas as pd
from pathlib import Path
import time
import re
import json
import concurrent.futures
from openai import OpenAI
from types import SimpleNamespace
import os

# =====================================================
# CONFIGURACIÓN vLLM
# =====================================================
client = OpenAI(base_url="http://localhost:8001/v1", api_key="local-token", timeout=30.0)
MODELO_VLLM = "Qwen/Qwen2.5-14B-Instruct" #"Qwen/Qwen2.5-7B-Instruct"

# Ajusta esto según tu GPU (30-50 es ideal para una 3090/4090)
MICRO_BATCH_SIZE = 10 #1 #30
MAX_RETRIES = 2
NUM_CTX = 3000

# Memoria Global de Tópicos
TOPIC_MEMORY = set()

# =====================================================
# EXTRACTOR JSON ULTRA ROBUSTO (TU ORIGINAL)
# =====================================================
def extraer_json_clasificacion(raw):
    if not raw or not isinstance(raw, str):
        return 2, "error", "Desconocido"

    raw = raw.strip()
    try:
        data = json.loads(raw)
        return validar_json(data)
    except: pass

    raw_clean = re.sub(r"```json|```", "", raw, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(raw_clean)
        return validar_json(data)
    except: pass

    def extract_largest_json(text):
        stack = []
        start_index = None
        candidates = []
        for i, char in enumerate(text):
            if char == "{":
                if not stack: start_index = i
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
        except: pass

    try:
        sent_match = re.search(r'"?sentimiento"?\s*:\s*"?(-?1|0|2)"?', raw, re.IGNORECASE)
        topic_match = re.search(r'"?topic"?\s*:\s*"([^"]+)"', raw, re.IGNORECASE)
        lang_match = re.search(r'"?Idioma_Real"?\s*:\s*"([^"]+)"', raw, re.IGNORECASE)
        sentimiento = int(sent_match.group(1)) if sent_match else 2
        topic = topic_match.group(1).strip() if topic_match else "error"
        idioma = lang_match.group(1).strip() if lang_match else None
        return sentimiento, topic, idioma
    except: pass

    return 2, "error", None

def validar_json(data):
    if not isinstance(data, dict): 
        return 2, "no relacionado", "Desconocido" # Sin idioma por defecto
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
# PREPARACIÓN TEXTO (TU ORIGINAL)
# =====================================================
def preparar_texto(row, num_ctx=NUM_CTX):
    def count_tokens(texto): return len(texto) // 4 if texto else 0
    def safe_text(val):
        if val is None or pd.isna(val) or str(val).strip().lower() == "nan": return ""
        return str(val).strip()

    comentario = safe_text(row.get("contenido"))
    # --- FILTRO PARA COMENTARIOS BORRADOS ---
    textos_basura = ["[removed]", "[deleted]", "nan", "", "none"]
    if comentario.lower() in textos_basura:
        return "BORRADO"
    # ----------------------------------------------------

    subreddit = safe_text(row.get("subreddit"))

    titulo = safe_text(row.get("post_title"))
    cuerpo = safe_text(row.get("post_selftext"))
    titulo_video = safe_text(row.get("titulo_video"))
    descripcion = safe_text(row.get("descripcion_video"))
    tweet_previo = safe_text(row.get("BeforeContenido"))

    texto_final = f"[COMENTARIO]\n{comentario}"
    
    if subreddit:
        texto_final = f"[ENLACE/FUENTE]\n{subreddit}\n" + texto_final

    total_tokens = count_tokens(comentario)

    if titulo or cuerpo:
        if titulo and total_tokens + count_tokens(titulo) < num_ctx:
            texto_final = f"[TÍTULO POST]\n{titulo}\n" + texto_final
            total_tokens += count_tokens(titulo)
        if cuerpo and total_tokens + count_tokens(cuerpo) < num_ctx:
            texto_final = f"[CUERPO POST]\n{cuerpo}\n" + texto_final
    elif titulo_video or descripcion:
        if titulo_video and total_tokens + count_tokens(titulo_video) < num_ctx:
            texto_final = f"[TÍTULO VIDEO]\n{titulo_video}\n" + texto_final
        if descripcion and total_tokens + count_tokens(descripcion) < num_ctx:
            texto_final = f"[DESCRIPCIÓN VIDEO]\n{descripcion}\n" + texto_final
    elif tweet_previo:
        if total_tokens + count_tokens(tweet_previo) < num_ctx:
            texto_final = f"[TWEET ANTERIOR]\n{tweet_previo}\n" + texto_final

    return texto_final


def build_prompts(tema, desc_tema, keywords_list, population_scope, languages):#population_scope, 
    keywords_str = ", ".join(keywords_list)
    # poblacion = ", ".join(population_scope) if isinstance(population_scope, list) else population_scope
    langs = ", ".join(languages) if languages else "Cualquiera"

    system = ("Eres un auditor de datos de alta seguridad para social listening. Tu prioridad absoluta es ELIMINAR ruido geográfico e idiomático antes de clasificar COMENTARIOS."
              "Eres escéptico por naturaleza: ante la duda, excluyes." "Todos los 'Topic' deben estar escritos en CASTELLANO, independientemente del idioma del COMENTARIO."
              "Tu salida debe ser exclusivamente JSON.")

    # Usamos {tema} y {keywords_str} directamente de u_conf
    # Población: {poblacion}
    user_template = f"""
--- MARCO DE CONTROL DEL PROYECTO ---
- Tema central de análisis: {tema}
- Descripción técnica: {desc_tema}
- Idiomas permitidos: {langs}
- Ubicación permitida: {population_scope}

--- INSTRUCCIONES DE EVALUACIÓN ---
Analiza el [COMENTARIO] y su contexto ([ENLACE/FUENTE], [TÍTULO POST] , [CUERPO POST], [TÍTULO VIDEO] , [DESCRIPCIÓN], [TWEET ANTERIOR], etc) para completar la verificación.


🚨 PASO 0: PROTOCOLO DE EXCLUSIÓN (ELIMINACIÓN DE RUIDO) 🚨
Antes de analizar, verifica si el [COMENTARIO] debe ser ELIMINADO. 
Debes marcar "Sentimiento": 2 y "Topic": "No relacionado" si:

1. IDIOMA: El texto del COMENTARIO NO está en {langs}. -> ELIMINA
2. GEOGRAFÍA AJENA (REGLA DE HERENCIA): El contexto proporcionado o el texto indican un lugar (barrio, ciudad o país) que NO forma parte del contexto geográfico objetivo: {population_scope}. El COMENTARIO se considera IRRELEVANTE  -> ELIMINA
3. RELEVANCIA TEMÁTICA: El tema es "{tema}". Si no se centra específica con el tema "{tema}" -> ELIMINA
4. PUBLICIDAD/VENTA: Intención comercial clara (precios, links, spam), mensajes sin texto coherente. -> ELIMINA
5. TOTALMENTE AJENO: No tiene NINGUNA RELACIÓN con el **MARCO DE CONTROL**. -> ELIMINA


**IMPORTANTE**: NO excluyas noticias ni citas.  Si informan sobre el tema en el contexto de {population_scope}, son RELEVANTES por su impacto en la opinión.

--- INSTRUCCIONES DE CLASIFICACIÓN (SOLO SI PASÓ EL PASO 0) ---
--- PASO 1: ANÁLISIS DE POSICIONAMIENTO RESPECTO AL TEMA ---
Solo si el mensaje PASÓ el **PASO 0**, es de {population_scope} y trata sobre {tema} (descripción: {desc_tema}), entonces determina la postura del autor del **[COMENTARIO]**, respecto a ese tema, basándote en el texto del COMENTARIO y su contexto.
- "1" (A favor / Apoyo / posicionamiento Positivo): Opinión favorable/ positiva o noticia que resalta beneficios sobre el tema: {tema} (descripción: {desc_tema}).
- "-1" (En contra/ crítica / posicionamiento Negativo): Opinión desfavorable, crítica, queja o noticia que resalta fallos/caos peligros o consecuencias negativas sobre el tema: {tema} (descripción: {desc_tema}).
- "0" (Neutra / Informativo / Equilibrado / posicionamiento Neutral): Datos objetivos, preguntas técnicas o noticias o citas neutrales sin sesgo claro sobre el tema: {tema} (descripción: {desc_tema}).
- "2": Irrelevante / Spam (según Paso 0).

⚠️ **REGLA DE ORO PARA PRENSA Y CITAS**:
- Si un titular dice: "La polémica ley causa el caos", clasifícalo como "-1" (posicionamiento negativo).
- Si alguien republica o menciona COMENTARIO o valoración personal de otra persona: "Esta ley es un avance", clasifícalo como "1" (posicionamiento positivo). 
- Si un titular dice:: "La ley entra en vigor mañana" -> "0".  

--- PASO 2: IDENTIFICACIÓN DEL TÓPICO (EL 'POR QUÉ' / ARGUMENTO) ---
🚨 REGLA DE CLARIDAD ARGUMENTATIVA (CRÍTICA) 🚨
1. **PROHIBICIÓN DE REDUNDANCIA**: NO uses "{tema}" ni los términos de búsqueda utilizados: "{keywords_str}", ni variaciones de estas como tópico. Ya sabemos que el COMENTARIO trata de eso.
2. EL TÓPICO ES EL ÁNGULO: Debe explicar POR QUÉ el usuario tiene ese posicionamiento.
3. **BUSCA EL ARGUMENTO**: ¿De qué arista del tema está hablando? El tópico es la RAZÓN o ARGUMENTO o el ÁNGULO específico de la opinión (ej: "seguridad pública", "libertad individual", "coste económico", "derechos humanos").
4. **COHERENCIA**: Revisa la lista de "TÓPICOS YA DETECTADOS" abajo. Si el argumento encaja en la lista de abajo, ÚSALO EXACTAMENTE IGUAL.
5. No uses palabras sueltas ambiguas. El Tópico debe explicar qué aspecto se valora y en qué sentido. 
6. El Tópico debe ser una frase breve (2-4 palabras) que se entienda por sí sola. Debe ser autoexplicativo para que no haya ambigüedad entre el nombre del tópico y el número de sentimiento.

Ejemplos de cómo construir el Tópico:
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

--- COMENTARIO A ANALIZAR ---
__COMENTARIO__

--- FORMATO DE SALIDA (JSON) ---
{{
  "Verificacion_Filtro": {{
    "Idioma_Real": "Indica un único idioma detectado del texto del COMENTARIO",
    "Ubicacion_Real": "Indica barrio/municipio/ciudad/país, hallado o inferido a partir del contexto o el texto del COMENTARIO". Si no hay pistas, indica 'Desconocida',
    "Relevancia_Tematica": "Explica brevemente si el COMENTARIO trata sobre '{tema}' basándote en la descripción técnica y el contexto proporcionado",
    "Pasa_el_filtro": "SÍ o NO"  
     }},
  "Topics": [
    {{ "Topic": "<argumento_especifico_en_castellano>", "Sentimiento": "<1|-1|0|2>" }}
  ]
}}
"""
    return system, user_template

def construir_contexto_topics():
    """Crea el bloque de texto que se inserta en el prompt"""
    if not TOPIC_MEMORY:
        return "\n(Aún no se han detectado tópicos específicos. Crea el primero basado en el argumento).\n"
    
    # Ordenamos alfabéticamente para que el modelo los encuentre fácil
    lista = sorted(list(TOPIC_MEMORY))[-30:] # Limitamos a 30 para no saturar
    return f"""
=== TÓPICOS YA DETECTADOS (Úsalos si el argumento coincide) ===
{", ".join(lista)}
==============================================================
"""

import unicodedata

def normalizar_topic(t):
    """Limpia el tópico antes de guardarlo en la memoria global"""
    if not t: return "error"
    t = str(t).strip().lower()
    t = re.sub(r'[^\w\s]', '', t).replace('_', ' ')  # Quita puntuación y guiones bajos
    t = re.sub(r'\s+', ' ', t)                       # Colapsa espacios dobles
    # Quitar acentos para unificar
    t = ''.join(c for c in unicodedata.normalize('NFD', t) 
                if unicodedata.category(c) != 'Mn')
    return t

# =====================================================
# TRABAJADOR vLLM (PARALELIZABLE)
# =====================================================
def call_vllm_worker(texto, system_prompt, user_template):
    # Si el texto es la señal de borrado, devolvemos "No relacionado" sin llamar a la IA
    if not texto or texto == "BORRADO": 
        return 2, "no relacionado", None
    
    # 1. Construimos la lista de tópicos que ya conocemos
    contexto_dinamico = construir_contexto_topics()
    
    # 2. Inyectamos esa lista Y el comentario en el template del prompt
    prompt_final = user_template.replace("__TOPICS_EXISTENTES__", contexto_dinamico)
    prompt_final = prompt_final.replace("__COMENTARIO__", texto)

    for intento in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=MODELO_VLLM,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_final}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            raw = response.choices[0].message.content
            sentimiento, topic_raw, idioma_ia = extraer_json_clasificacion(raw)
            
            # 3. Normalizamos lo que el modelo respondió
            topic_limpio = normalizar_topic(topic_raw)
            
            # 4. Si es un tópico nuevo y válido, lo añadimos a la memoria global
            # para que el PRÓXIMO hilo de ejecución lo vea en su prompt
            if topic_limpio not in ["error", "no relacionado", "comercialización"]:
                TOPIC_MEMORY.add(topic_limpio)
            if sentimiento in [1, -1, 0]:
                print(f"✅ Clasificación obtenida: Sentimiento={sentimiento}, Tópico='{topic_limpio}', Idioma IA='{idioma_ia}'")    
            return sentimiento, topic_limpio, idioma_ia
        except Exception:
            time.sleep(1)
    return 2, "error", None

# =====================================================
# PIPELINE PRINCIPAL (REEMPLAZO DE llm_analysis)
# =====================================================
def llm_analysis(u_conf):
    print("\n🚀 INICIANDO ANÁLISIS SENTIMIENTO + TOPIC (vLLM)")
    data_folder = Path(u_conf.general["output_folder"])
    
    memory_file = data_folder / "learned_topics.json"
    if memory_file.exists():
        with open(memory_file, "r", encoding="utf-8") as f:
            TOPIC_MEMORY.update(json.load(f))

    system_p, user_t = build_prompts(
        u_conf.tema, 
        u_conf.desc_tema,
        u_conf.general["keywords"], 
        u_conf.population_scope, 
        u_conf.languages
    )

    archivos_originales = list(data_folder.glob("*_global_dataset.csv"))
    
    for archivo in archivos_originales:
        analizado_path = archivo.with_name(archivo.stem + "_analizado.csv")
        path_a_cargar = analizado_path if analizado_path.exists() else archivo
        
        print(f"\n=== Revisando: {path_a_cargar.name} ===")

        # 1. Detectar separador
        try:
            with open(path_a_cargar, 'r', encoding='utf-8') as f:
                linea = f.readline()
                sep = ';' if ';' in linea else ','
        except:
            sep = ';'

        # 2. Cargar el DataFrame
        try:
            df = pd.read_csv(path_a_cargar, sep=sep, encoding='utf-8', engine='python', on_bad_lines='skip')
            
            # Limpieza de filas vacías
            if 'contenido' in df.columns:
                df = df.dropna(subset=['contenido'])
                df = df[df['contenido'].astype(str).str.strip() != ""]
                df = df.reset_index(drop=True)
            
            if df.empty: continue
        except Exception as e:
            print(f"❌ Error cargando archivo: {e}")
            continue

        # 3. FORZAR COLUMNAS A TIPO STRING (Esto evita el error de dtype int64)
        # Al convertirlas a string, podemos guardar cualquier valor y detectar vacíos fácilmente
        for col in ["sentimiento", "topic", "IDIOMA_IA"]:
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].fillna("").astype(str).str.strip()

        # 4. IDENTIFICAR PENDIENTES
        # Ahora es simple: si está vacío o es "nan", está pendiente
        mask_pendiente = (df["sentimiento"] == "") | (df["sentimiento"] == "nan") | \
                         (df["topic"] == "") | (df["topic"] == "nan")
        
        indices_pendientes = df[mask_pendiente].index.tolist()
        total = len(df)
        pendientes = len(indices_pendientes)

        if pendientes == 0:
            print(f"✅ {path_a_cargar.name} analizado al 100%.")
            continue
        
        print(f"📊 Pendientes: {pendientes} / {total}. Iniciando...")

        # 5. Procesar por lotes
        for i in range(0, pendientes, MICRO_BATCH_SIZE):
            batch_indices = indices_pendientes[i : i + MICRO_BATCH_SIZE]
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=MICRO_BATCH_SIZE) as executor:
                futures = {
                    executor.submit(call_vllm_worker, preparar_texto(df.loc[idx]), system_p, user_t): idx 
                    for idx in batch_indices
                }

                for future in concurrent.futures.as_completed(futures):
                    idx = futures[future]
                    try:
                        sent, top, idioma_ia = future.result()
                        # Guardamos todo como string para evitar conflictos de tipos
                        df.loc[idx, "sentimiento"] = str(sent)
                        df.loc[idx, "topic"] = str(top)
                        df.loc[idx, "IDIOMA_IA"] = str(idioma_ia)
                    except Exception as e:
                        print(f"❌ Error en fila {idx}: {e}")

            # Guardado de seguridad tras cada lote
            df.to_csv(analizado_path, index=False, sep=';', encoding='utf-8')
            print(f"✅ Lote completado. Guardado en {analizado_path.name}")

    print(f"✨ Proceso finalizado.")
# 6. EJECUCIÓN MANUAL (CON DATOS DE PILARES)
# =====================================================
def modo_manual_test():
    """Crea datos ficticios para probar rápidamente el análisis"""
    u_conf_test = SimpleNamespace(
        tema="Prohibición del burka en espacios públicos",
        desc_tema="Propuesta legislativa para prohibir el uso del burka y niqab en espacios públicos en España, generando debate político.",
        population_scope="España",
        languages=["Castellano"],
        general={
            "output_folder": "./test_unified_results",
            "keywords": ["prohibición burka", "burka espacios públicos"]
        }
    )

    output_path = Path(u_conf_test.general["output_folder"])
    output_path.mkdir(exist_ok=True)

    data_unificada = pd.DataFrame({
        'ID': [1, 2, 3, 4, 5, 6, 7,8],
        'RED_SOCIAL': ["Twitter", "Twitter", "Reddit", "Reddit", "Bluesky", "Bluesky", "Bluesky", "Bluesky"],
        'CONTENIDO': [
            "Opinión impopular: Si me dan a elegir, que prohiban OnlyFans antes que el burka.",
            "COMPRE SU BURKA AQUÍ! Oferta exclusiva por tiempo limitado (2 EUROS). HTTP://BURKASUPER.COM",
            "VOX sobre la prohibición del burka que va a impulsar en el Congreso...",
            "Creo que la libertad individual debería estar por encima de todo.",
            "Es una vulneración de la Constitución española.",
            "La Comisión Islámica de Portugal advierte sobre las consecuencias de la prohibición.",
            "PP y VOX votan en el Congreso una propuesta para prohibir el velo integral.",
            "Estic a favor de la prohibició"
        ],
        'contenido': [ # Duplicado para preparar_texto
            "Opinión impopular: Si me dan a elegir, que prohiban OnlyFans antes que el burka.",
            "COMPRE SU BURKA AQUÍ! Oferta exclusiva por tiempo limitado (2 EUROS). HTTP://BURKASUPER.COM",
            "VOX sobre la prohibición del burka que va a impulsar en el Congreso...",
            "Creo que la libertad individual debería estar por encima de todo.",
            "Es una vulneración de la Constitución española.",
            "La Comisión Islámica de Portugal advierte sobre las consecuencias de la prohibición.",
            "PP y VOX votan en el Congreso una propuesta para prohibir el velo integral.",
            "Estic a favor de la prohibició"

        ],
        'post_title': ["", "", "El problema de eliminar el burka", "Yolanda Díaz avisa a las derechas sobre prohibir el burka: Vulnera la Constitución española en su artículo 14 y 16", "", "", "", ""],
        'BeforeContenido': ["¿Qué opinas sobre las nuevas leyes?", "", "", "", "", "", "", ""],
        'sentimiento': [""] * 8,
        'topic': [""] * 8
    })

    archivo_test = output_path / "unified_global_dataset.csv"
    data_unificada.to_csv(archivo_test, index=False)

    llm_analysis(u_conf_test)

    print("\n📊 RESULTADOS:")
    res_file = output_path / "unified_global_dataset_analizado.csv"
    if res_file.exists():
        res_df = pd.read_csv(res_file)
        print(res_df[['RED_SOCIAL', 'sentimiento', 'topic']])

def modo_carpeta_real():
    """Procesa los archivos CSV que tengas en una carpeta específica"""
    ruta = "/home/rrss/proyecto_web/RRSS_version_stance/project_web/Web_Proyecto/datos/admin/pantalan_sagunto"#"/home/rrss/proyecto_web/RRSS_version_stance/project_web/Web_Proyecto/datos/admin/carril_bus_vao_con_descripción_de_tema (1)"#"/home/rrss/proyecto_web/RRSS_version_stance/project_web/Web_Proyecto/datos/admin/viernes_17c" #    
    u_conf_folder = SimpleNamespace(
        tema= "Pantalán de Sagunto",#"carril bus vao",#"autobuses sagunto", #
        desc_tema= "Es una infraestructura portuaria que ha sido renovada y transformada en un espacio turístico y cultural, ofreciendo vistas panorámicas del mar Mediterráneo y la ciudad.",#"Es un carril exclusivo en vías de acceso a ciudades españolas, diseñado para vehículos de alta ocupación y autobuses, con el fin de mejorar la movilidad y reducir el tráfico.",#"prohibición burka en espacios públicos",
        # "El servicio de autobuses en Sagunto ofrece conexiones locales e interurbanas, incluyendo rutas hacia Valencia y Madrid, facilitando el transporte público para los residentes y visitantes.",#"El carril Bus VAO es una vía exclusiva para vehículos de alta ocupación y autobuses en ciertas áreas urbanas de España, diseñada para reducir congestión y promover el uso de transporte público y vehículos eficientes.",
        #population_scope="Público general",
        languages=["Castellano", "Catalan", "Euskera", "Ingles", "Italiano", "Portugues", "Frances"],
        population_scope="Sagunto",#"España",#
        general={
            "output_folder": ruta,
            "keywords": ["pantalán sagunto", "paseo pantalán sagunto", "pantalán puerto sagunto"
                         , "sagunto turismo", "pantalán vista mar", "paseo marítimo sagunto", "pantalán cultural sagunto", 
                         "pantalán panorámico sagunto", "pantalán renovado sagunto", "pantalán turístico sagunto", 
                         "sagunto pier", "sagunto promenade", "sagunto harbor", "sagunto viewpoint", "sagunto waterfront", 
                         "sagunto cultural hub", "sagunto tourist spot", "sagunto marina", "sagunto coastal walk", 
                         "sagunto seaside", "cais sagunto", "passeio sagunto", "vista sagunto", "turismo sagunto", "cais renovado", 
                         "passeio marítimo", "sagunto cais", "vista mar", "cais turístico", "saguntoko pantalán", 
                         "itsas pasealekua", "saguntoko kaia", "pantalanaren aurkezpena", "saguntoko ikastegia", 
                         "mariko ikusgaiak", "saguntoko urdaitza", "pantalanaren aldaketa", "saguntoko turismoa", 
                         "saguntoko pasealekua", "pantalà sagunt", "pantalà port sagunt", "espai turístic sagunt", 
                         "vistes panoràmiques sagunt", "pantalà renovat sagunt", "port de sagunt", "pantalà cultural sagunt", 
                         "passeig maritim sagunt", "turisme sagunt", "pantalà vista mar", "molo di sagunto", "porto di sagunto", 
                         "lungomare di sagunto", "viste panoramiche sagunto", "sagunto cultura", "porto turistico sagunto", 
                         "molo panoramico", "sagunto vista mare", "luogo storico sagunto", "jetée sagonte", "promenade sagonte", 
                         "vue sur sagonte", "port sagonte", "jetée méditerranée", "sagonte culture", "jetée turisme", "jetée renové", 
                         "vue mer sagonte"]
                # "carril bus vao","vao bus", "carril vao", "carril alta ocupación", "carril autobús", 
                #          "vehículos vao", "carril multiocupante", "circulación vao", "carril vao urbano",
                #          "carril bus exclusivo"
                        #  #"autobuses sagunto", "servicio autobuses sagunto", "conexiones sagunto", "autobuses sagunto valencia", "autobuses sagunto madrid", "transporte sagunto", "rutas sagunto", "viajar sagunto", "tarifa autobus sagunto", "autobus sagunto"]
                        #  ]
        }
    )

    print(f"📂 Carpeta de salida: {Path(u_conf_folder.general['output_folder'])}")
    llm_analysis(u_conf_folder)        

if __name__ == "__main__":
    
    # OPCIONES: "manual" o "carpeta"
    MODO = "carpeta" #"manual"  # o "carpeta"
    
    if MODO == "manual":
        print("🛠️ Ejecutando MODO MANUAL (Datos de prueba)...")
        modo_manual_test()
    else:
        print("📂 Ejecutando MODO CARPETA (Datos reales)...")
        modo_carpeta_real()    

'''
# =====================================================
# PROMPTS (ORIGINAL + MEMORIA)
# =====================================================
# def build_prompts_original(tema, desc_tema, keywords_list, languages): # population_scope, 
#     keywords_str = ", ".join(keywords_list)
#     # poblacion = ", ".join(population_scope) if isinstance(population_scope, list) else population_scope
#     langs = ", ".join(languages) if languages else "Cualquiera"
#     # Población objetivo: {population_scope} (si está vacía, asumir 'público general')
#     system = "Eres un analista experto en social listening. Responde ÚNICAMENTE con un JSON válido."

#     user_template = f"""
# --- MARCO DE CONTROL (ESTRICTO) ---
# Título del tema general: {tema} 
# Descripción del tema: {desc_tema}
# Listado de términos de búsqueda: [{keywords_str}]
# Idiomas objetivo: {langs} 

# --- COMENTARIO A ANALIZAR ---
# __COMENTARIO__

# 🚨 **PASO 0: FILTRO DE EXCLUSIÓN TOTAL** 🚨
# Eres un filtro de elegibilidad...

# Tu única tarea es decidir si un COMENTARIO es una OPINIÓN estrictamente relacionada con el tema: {tema} o si debe EXCLUIRSE. Para que entiendas más el tema la descripción es: {desc_tema}).

# INSTRUCCIONES:
# 1) Si se cumple CUALQUIERA de los criterios de exclusión, responde inmediatamente con:
#    topic="No relacionado", sentimiento="2", excluded=true.
# 2) Si NO se cumple ningún criterio de exclusión, responde excluded=false y NO pongas topic="No relacionado".
# 3) No inventes contexto. Usa solo el COMENTARIO.

# CRITERIOS DE EXCLUSIÓN TOTAL:
# A) IDIOMA: el COMENTARIO está principalmente en un idioma NO permitido.

# B) TIPO DE TEXTO (NO OPINIÓN):
#    B1 NOTICIA/INFORMATIVO: El texto debe excluirse SOLO si se limita a informar, reproducir o resumir
# una noticia, comunicado oficial o hecho objetivo, SIN expresar ningún tipo
# de valoración personal.
#    B2 PUBLICIDAD/VENTA: intención comercial (precio, oferta, comprar, link en bio, promoción).
#    B3 DESCRIPCIÓN NEUTRA: El texto debe excluirse SOLO si se limita a describir o explicar
# una situación, medida o hecho SIN expresar valoración personal.

# Se considera NOTICIA/INFORMATIVO excluible cuando:
# - Reproduce titulares, avisos o comunicados (p.ej., "Última hora", "según...",
#   "comunicado oficial", "BOE", "decreto", "se aprueba", "entra en vigor").
# - Describe hechos de forma neutra o institucional.
# - No contiene juicio, opinión, reacción personal ni lenguaje evaluativo.

# Se considera descripción neutra excluible cuando:
# - Describe hechos, contextos o situaciones de forma objetiva o explicativa.
# - No muestra apoyo, rechazo, crítica ni preocupación.
# - No incluye ironía, sarcasmo, burla, desconfianza ni lenguaje emocional.
# - Podría ser leído como una explicación impersonal sin cambiar el sentido.

# NO debe excluirse si el texto:
# - Comenta, reacciona o valora una noticia, aunque la mencione explícitamente.
# - Expresa crítica, apoyo, ironía, sarcasmo, burla, desconfianza o indignación.
# - Incluye lenguaje coloquial, emocional o interpretativo del autor.
# - Incluye interpretación personal, aunque sea implícita.
# - Sugiere evaluación mediante tono, elección de palabras o contexto.
# - Utiliza ironía, exageración o lenguaje coloquial con carga valorativa.

# C) FALSO POSITIVO: aparece un termino de búsqueda pero no se refiere al objeto de opinión del tema de investigación.

# --- TOPIC EXTRACTION ---
# Analiza SOLO el bloque __COMENTARIO__.
# No uses los términos de búsqueda ni el tema general para crear el topic.
# El topic debe ser breve (1–3 palabras).
# **PASO 1: Extracción de Topic y Sentimiento (Solo si pasa el filtro)**

# Si hay una **OPINIÓN PERSONAL EXPLÍCITA**:
# 1. **Topic**: Identifica el MOTIVO o ASPECTO concreto evaluado (ej: "precio", "seguridad", "ruido", "rescate", "regulación"). 
# **No uses los posibles términos de búsqueda del "Listado de términos de búsqueda" ni el "Tema general" ni sus posibles variantes semánticas para establecer el topic**.  
# El Topic debe ser una etiqueta corta (1–3 palabras máximo) en **castellano**. No usar frases. 
# 2. **Sentimiento**: Asigna SOLO el número:
#    - "1": Elogio, apoyo, valoración positiva explícita.
#    - "-1": Queja, crítica, rechazo, preocupación explícita, valoración negativa explícita.
#    - "0": Mención neutra u opinión ambivalente sin carga clara, el COMENTARIO solo reporta o cita opiniones de terceros sin expresar una valoración propia clara.
#    - "2": (Irrelevante) Si no hay juicio de valor claro, no esta relacionado, noticia.

# ⚠️ INSTRUCCIÓN CRÍTICA:
# - Analiza EXCLUSIVAMENTE el bloque "COMENTARIO".
# - El bloque "CONTEXTO" solo sirve para entender referencias implícitas, relación con ámbito geográfico, o relación con Tema general de análisis.
# - NO evalúes el título ni el cuerpo.
# - Si el COMENTARIO es una opinión aunque el contexto sea noticia, NO excluir.
   
# **Formato de respuesta JSON ESTRICTO**:
# - El campo "Sentimiento" debe contener SOLO el número en formato string, NADA de texto adicional.
# - Si es excluido, devuelve: {{ "Topics": [{{ "Topic": "No relacionado", "Sentimiento": "2" }}]}}

# {{
#   "Topics": [
#     {{ "Topic": "<aspecto concreto o 'No relacionado'>", "Sentimiento": "<1|-1|0|2>" }}
#   ]
# }}
# """

#     return system, user_template

# def build_prompts_v1(tema, keywords_list, languages): #population_scope, 
#     keywords_str = ", ".join(keywords_list)
#     # poblacion = ", ".join(population_scope) if isinstance(population_scope, list) else population_scope
#     langs = ", ".join(languages) if languages else "Cualquiera"

#     system = "Eres un analista experto en comunicación política y social listening. Tu objetivo es detectar el posicionamiento y el encuadre (framing) de la conversación."
#     # Población objetivo: {population_scope}
#     user_template = f"""
# --- DATOS DE ENTRADA ---
# Tema general: {tema} 


# --- COMENTARIO A ANALIZAR ---
# __COMENTARIO__

# 🚨 **PASO 0: FILTRO DE EXCLUSIÓN (SOLO BASURA REAL)** 🚨
# Excluye ÚNICAMENTE si el COMENTARIO es:
# A) PUBLICIDAD/VENTA: Intención comercial clara (precios, links de compra, spam).
# B) TOTALMENTE AJENO: No tiene nada que ver con el tema.
# C) TÉCNICO/ADMINISTRATIVO PURO: Solo si es una cita de un boletín oficial o una fecha sin ningún tipo de contexto o adjetivación (ej: "Ley 3/2023, artículo 4").

# **IMPORTANTE**: NO excluyas noticias de prensa ni citas de terceros. Si el texto informa sobre el tema, es RELEVANTE por su capacidad de influir en la opinión.

# --- PASO 1: ANÁLISIS DE POSICIONAMIENTO Y ENCUADRE ---
# Analiza el bloque __COMENTARIO__ buscando el sesgo, la intención o el impacto:

# 1. **Topic**: Identifica el ASPECTO específico de la política que se menciona (ej: "coste económico", "derechos civiles", "seguridad", "implementación").
#    - Debe ser breve (1-3 palabras).

# 2. **Sentimiento (Posicionamiento)**:
#    - **"1" (Apoyo/Encuadre Positivo)**: Opinión favorable, o noticia que resalta beneficios, éxitos o necesidad de la medida.
#    - **"-1" (Crítica/Encuadre Negativo)**: Opinión desfavorable, queja, o noticia que resalta fallos, costes excesivos, riesgos o protestas. Incluye ironía y sarcasmo.
#    - **"0" (Informativo/Equilibrado)**: El texto es puramente descriptivo, presenta ambas caras de la moneda o cita a otros sin un encuadre claro de ataque o defensa.
#    - **"2"**: Solo si tras este análisis el texto resulta ser spam o totalmente irrelevante.

# ⚠️ **REGLA DE ORO PARA PRENSA Y CITAS**:
# - Si un periódico titula: "La polémica ley causa el caos en los hospitales", clasifícalo como **"-1"** (el encuadre es negativo y genera rechazo).
# - Si un usuario republica a un político diciendo: "Esta ley es un avance histórico", clasifícalo como **"1"** (está amplificando un mensaje positivo).

# **Formato de respuesta JSON ESTRICTO**:
# {{
#   "Topics": [
#     {{ "Topic": "<aspecto>", "Sentimiento": "<1|-1|0|2>" }}
#   ]
# }}
# """
#     return system, user_template

'''        