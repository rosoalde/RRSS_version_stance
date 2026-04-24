import pandas as pd
from pathlib import Path
import json
import re
import time
import concurrent.futures
from openai import OpenAI
from types import SimpleNamespace

# =====================================================
# 1. CONFIGURACIÓN vLLM
# =====================================================
client = OpenAI(base_url="http://localhost:8001/v1", api_key="local-token")
MODELO_VLLM = "Qwen/Qwen2.5-14B-Instruct"#"Qwen/Qwen2.5-7B-Instruct"

MICRO_BATCH_SIZE = 20 
MAX_RETRIES = 2
NUM_CTX = 5000 # Límite de contexto del modelo

PILARES = [
    "Legitimacion_sociopolítica",
    "Efectividad_percibida",
    "Justicia_y_equidad_percibida",
    "Confianza_y_legitimidad_institucional"
]
# =====================================================
# 2. PROMPT DE PILARES (CON CONTEXTO Y ENCUADRE)
# =====================================================

def get_prompt_pilares(tema, desc_tema, keywords_list,population_scope,languages):
    keywords_str = ", ".join(keywords_list)
    # poblacion = ", ".join(population_scope) if isinstance(population_scope, list) else population_scope
    langs = ", ".join(languages) if languages else "Cualquiera"

    system = ("Eres un experto en análisis de opiniones y comunicación política."
              f"Tu tarea es identificar juicios de valor subjetivos (incluyendo ironía/sarcasmo) sobre el tema: {tema} (descripción: {desc_tema})."
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

🚨 PASO 0: FILTRO DE EXCLUSIÓN TOTAL (Gatekeeper) 🚨
Eres un filtro de elegibilidad. Tu única tarea en este paso es decidir si el texto es una OPINIÓN válida (relevante para {population_scope}) o si debe EXCLUIRSE.

✅ PRINCIPIO CLAVE (anti-falsos excluidos):
- Si tienes DUDA razonable entre excluir o no, elige excluded=false y pasa al PASO 1.
- Solo usa excluded=true cuando el criterio de exclusión sea CLARO e INEQUÍVOCO.
- NO excluyas por “falta de contexto”: usa solo el texto.

REGLAS:
1) Si se cumple de forma CLARA e INEQUÍVOCA CUALQUIERA de los criterios de exclusión, responde con excluded=true, motivo_exclusion y asigna "2" a TODOS los pilares. DETENTE.
2) Si NO se cumple de forma clara ningún criterio, responde excluded=false y pasa al PASO 1.
3) No inventes contexto. Usa solo el texto.

CRITERIOS DE EXCLUSIÓN TOTAL (aplicar SOLO si es evidente):

A) IDIOMA:
EXCLUIR solo si el texto del COMENTARIO está principalmente en un idioma NO permitido.
Idiomas permitidos: {languages}.

B) GEOGRAFÍA AJENA (REGLA DE HERENCIA): 
EXCLUIR si el TEXTO del CONTEXTO proporcionado o el texto del COMENTARIO indican un lugar (barrio, ciudad o país) que NO forman parte del contexto geográfico objetivo: {population_scope}. 


C) TIPO DE TEXTO (TEXTO PURO, NO OPINIÓN):

C1 NOTICIA/INFORMATIVO (EXCLUIR SOLO SI ES TEXTO PURO):
Excluir SOLO si el texto se limita a informar/reproducir/resumir una noticia, titular o comunicado (p.ej. "BOE", "decreto", "comunicado", "según", "última hora") SIN expresar valoración personal.
Si hay CUALQUIER indicio de valoración (crítica, apoyo, indignación, ironía, burla, desconfianza, tono evaluativo, emojis de juicio), NO excluir.

C2 PUBLICIDAD/VENTA:
Excluir solo si hay intención comercial clara (precio, oferta, comprar, promo, enlace, venta) o es spam.

C3 DESCRIPCIÓN NEUTRA/TÉCNICA (EXCLUIR SOLO SI ES TEXTO PURO):
Excluir SOLO si el texto se limita a describir/explicar de forma impersonal (funcionamiento, datos, contexto) SIN evaluación personal, SIN emoción, SIN ironía/sarcasmo, SIN apoyo/queja.
Si hay cualquier juicio, queja, apoyo o crítica (aunque sea sutil o implícita), NO excluir.

D) FALSO POSITIVO:
Excluir solo si NO se refiere al objeto de opinión del tema: {tema} con descripción: {desc_tema}.
Si hay duda, NO excluir.

⚠️ INSTRUCCIÓN CRÍTICA:
- Analiza EXCLUSIVAMENTE el bloque "COMENTARIO".
- El bloque "CONTEXTO" solo sirve para entender referencias implícitas, relación con ámbito geográfico, o relación con tema de análisis.
- NO evalúes el título ni el cuerpo.
- Si el texto del COMENTARIO es una opinión aunque el CONTEXTO sea noticia, NO excluir.

FORMATO DE SALIDA SI excluded=true:
Devuelve SOLO este JSON (sin texto extra):
{{
  "Legitimación_sociopolítica": "2",
  "Efectividad_percibida": "2",
  "Justicia_y_equidad_percibida": "2",
  "Confianza_y_legitimidad_institucional": "2"
}}

🚨 PASO 1: SOLO si excluded=false 🚨
Bloque de reglas generales:
REGLAS GENERALES DE ANÁLISIS (OBLIGATORIAS)
1) Analiza únicamente el texto del COMENTARIO.
- No evalúes el título ni el CONTEXTO como si fueran la opinión.
- El CONTEXTO solo sirve para entender mejor el COMENTARIO.
2) Detecta juicios de valor, no información.
- Analiza opiniones, valoraciones o interpretaciones.
- No analices descripciones neutras o información factual.
3) Cada pilar mide una dimensión diferente.
- Evalúa cada pilar de forma independiente.
- Un mismo COMENTARIO puede activar varios pilares a la vez.
- No asumas ningún pilar por defecto. Cada pilar debe activarse solo si hay evidencia específica.
4) Prioriza el significado implícito.
- Ten en cuenta ironía, sarcasmo y tono.
- Interpreta la intención real del COMENTARIO.
5) No infieras más allá del texto.
- No inventes intención si no hay indicios.
- Si el significado es ambiguo, usa "0" (neutro).
6) Diferencia entre "0" y "2":
- "0" → hay referencia al pilar pero es ambigua o sin orientación clara.
- "2" → no hay ninguna referencia interpretable a ese pilar.
- En caso de duda leve, usa "0" en lugar de "2".
7) Si hay evidencia, clasifica (evita el "2").
- Usa "2" solo si NO hay absolutamente ninguna evidencia.

REGLAS DE DESAMBIGUACIÓN GLOBAL (MUY IMPORTANTES)
Cada pilar representa un tipo distinto de juicio.
Un mismo COMENTARIO puede contener varios juicios a la vez.
Evalúa cada pilar de forma independiente.
Un COMENTARIO puede activar varios pilares simultáneamente.
No elijas un único pilar dominante si hay varios juicios distintos.
--------------------------------------------------
IDENTIFICACIÓN POR TIPO DE JUICIO:
1) LEGITIMIDAD / LEGALIDAD / AJUSTE A NORMAS → Legitimacion
- ¿La medida se percibe como legal, legítima, válida o acorde a normas, ley, justicia o razón?
2) RESULTADO de la medida → Efectividad percibida
- ¿Funciona? ¿Sirve? ¿Tiene impacto real?
3) IMPACTO sobre las personas → Justicia y equidad percibida
- ¿Es justo o injusto? ¿A quién beneficia o perjudica?
4) ACTORES o responsables → Confianza institucional
- ¿Se critica o valora al gobierno, políticos o instituciones?
--------------------------------------------------
REGLA DE RESOLUCIÓN DE AMBIGÜEDAD:
Si una misma expresión puede pertenecer a varios pilares:
- Identifica el tipo de juicio principal de esa expresión concreta (legitimidad, resultado, impacto o actor)
- Esto NO impide que el comentario active varios pilares si contiene varios juicios distintos
--------------------------------------------------
REGLAS CLAVE DE SEPARACIÓN:
- Hablar de legalidad, legitimidad o ajuste con normas → Legitimacion
- Evaluar resultados → Efectividad
- Hablar de impacto en personas → Justicia
- Criticar actores → Confianza institucional
--------------------------------------------------
CASOS FRECUENTES:
- “esto es ilegal” → Legitimacion (-1)
- “no sirve para nada” → Efectividad (-1)
- “es injusto” → Justicia (-1)
- “solo quieren recaudar” → Confianza (-1)
--------------------------------------------------
CASOS AMBIGUOS:
Palabras como “aceptable”, “válido”, “correcto”, “ilegítimo”:
- Si se refieren a conformidad con ley, normas o legitimidad → Legitimacion
- Si se refieren al impacto en personas o reparto → Justicia
--------------------------------------------------
REGLA FINAL:
Si hay duda:
- Identifica primero el tipo de juicio
- NO uses "2" si hay cualquier indicio interpretable
Bloque de los pilares:
1) LEGITIMACION
--------------------------------------------------
Se refiere a si el comentario evalúa la medida en términos de legalidad, legitimidad o ajuste con las normas.
Legitimar significa convertir algo en legítimo, lícito o conforme a la ley, justicia o razón.
Pregunta clave:
¿El comentario sugiere que la medida es legal, legítima, válida o acorde con la ley, la justicia, las normas o la razón?
--------------------------------------------------
QUÉ INCLUYE:
- Si la medida es legal o ilegal
- Si la medida se percibe como legítima o ilegítima
- Si se ajusta o no a la ley, a las normas o a principios considerados válidos
- Si se presenta como aceptable o inaceptable por razones normativas o legales
- Juicios sobre si “debería poder hacerse” o “no deberían poder hacer esto”
--------------------------------------------------
EVIDENCIA POSITIVA (1):
Se asigna cuando el comentario expresa o sugiere que la medida es legal,
legítima, válida o conforme con las normas, la ley, la justicia o la razón.
Esto incluye:
- percepción de conformidad legal
- aceptación de la medida como válida o legítima
- valoración positiva de su ajuste con normas o principios
Ejemplos:
- “es legal”
- “es legítimo”
- “es válido”
- “es correcto”
- “cumple la ley”
También implícito:
- “tiene base legal”
- “no veo problema en que lo hagan”
- “es una medida aceptable”
- “está dentro de lo normal”
--------------------------------------------------
EVIDENCIA NEGATIVA (-1):
Se asigna cuando el comentario expresa o sugiere que la medida es ilegal,
ilegítima, inválida o contraria a normas, ley, justicia o razón.
Esto incluye:
- percepción de ilegalidad o ilegitimidad
- rechazo por falta de base normativa o legal
- juicio de que la medida “no debería permitirse”
Ejemplos:
- “es ilegal”
- “es ilegítimo”
- “va contra la ley”
- “no deberían poder hacer esto”
- “esto no es válido”
También implícito:
- “esto no tiene base legal”
- “no es aceptable”
- “se están saltando las normas”
- “esto no debería permitirse”
--------------------------------------------------
EVIDENCIA NEUTRA (0):
Se asigna cuando el comentario hace referencia a la legalidad o legitimidad de la medida,
pero NO expresa una valoración clara (ni positiva ni negativa).
Esto incluye:
- duda o incertidumbre sobre si es legal o legítima
- evaluaciones ambiguas o poco definidas
- menciones a normas o ley sin juicio claro
Ejemplos:
- “no sé si es legal”
- “habría que ver si esto cumple la ley”
- “no tengo claro si esto es legítimo”
- “no sé hasta qué punto se ajusta a la norma”
--------------------------------------------------
NO INCLUYE:
- Resultados → Efectividad
- Impacto social → Justicia
- Actores → Confianza
--------------------------------------------------
REGLA FINAL:
Si hay cualquier evaluación sobre legalidad, legitimidad o ajuste con normas → NO uses "2"
2) EFECTIVIDAD PERCIBIDA
--------------------------------------------------
Se refiere a si el comentario evalúa los RESULTADOS o la UTILIDAD de la medida.
Pregunta clave:
¿El comentario sugiere que la medida funciona, no funciona o tendrá impacto?
--------------------------------------------------
QUÉ INCLUYE:
- Si funciona o no funciona
- Si sirve o no sirve
- Si tendrá efectos reales
- Si mejorará o empeorará la situación
- Expectativas de impacto (aunque sean subjetivas)
--------------------------------------------------
EVIDENCIA POSITIVA (1):
Se asigna cuando el comentario expresa o sugiere que la medida es eficaz,
útil o tendrá un impacto positivo en la realidad.
Esto incluye:
- creencias de que la medida funciona o funcionará
- expectativas de mejora o solución de un problema
- valoración positiva del impacto o resultados de la medida
Ejemplos:
- “funciona”
- “sirve”
- “va a mejorar”
- “es útil”
- “tendrá efecto”
También implícito:
- “esto ayudará”
- “puede solucionar el problema”
- “esto sí que arregla las cosas”
- “puede funcionar bien”
--------------------------------------------------
EVIDENCIA NEGATIVA (-1):
Se asigna cuando el comentario expresa o sugiere que la medida es ineficaz,
inútil o no tendrá impacto real (o incluso empeorará la situación).
Esto incluye:
- negación de eficacia o utilidad
- expectativas de fracaso o ausencia de resultados
- creencias de que la medida no cambiará nada o tendrá efectos negativos
Ejemplos:
- “no sirve para nada”
- “es inútil”
- “no va a cambiar nada”
- “no funcionará”
- “es un fracaso”
También implícito:
- “esto no arregla nada”
- “no tiene ningún efecto”
- “esto no sirve”
- “no soluciona el problema”
- “esto va a empeorar las cosas”
--------------------------------------------------
EVIDENCIA NEUTRA (0):
Se asigna cuando el comentario hace referencia a la posible eficacia de la medida,
pero NO expresa una valoración clara (ni positiva ni negativa).
Esto incluye:
- duda o incertidumbre sobre si funcionará
- evaluaciones ambiguas o poco definidas
- comentarios que reconocen la posibilidad de distintos resultados sin posicionarse
Ejemplos:
- “no sé si funcionará”
- “puede que sí o puede que no”
- “habrá que ver si funciona”
- “no está claro si tendrá efecto”
--------------------------------------------------
NO INCLUYE:
- Legitimacion → Legitimacion
- Justicia → Justicia
- Críticas a actores → Confianza
--------------------------------------------------
REGLA FINAL:
Si hay cualquier evaluación sobre resultados o impacto → NO uses "2"
3) JUSTICIA Y EQUIDAD PERCIBIDA
--------------------------------------------------
Se refiere a si la medida se percibe como justa o injusta en cómo afecta a las personas.
Pregunta clave:
¿El COMENTARIO evalúa si la medida trata a las personas de forma justa?
--------------------------------------------------
QUÉ INCLUYE:
- Quién gana y quién pierde
- Reparto de costes y beneficios
- Desigualdad o discriminación
- Impacto en grupos sociales
- Justicia del proceso de decisión
--------------------------------------------------
EVIDENCIA POSITIVA (1):
Se asigna cuando el comentario expresa o sugiere que la medida es justa,
equitativa o distribuye de forma adecuada sus efectos entre las personas.
Esto incluye:
- percepción de reparto equilibrado de costes y beneficios
- trato igualitario entre individuos o grupos
- valoración positiva del impacto social de la medida
Ejemplos:
- “es justo”
- “es equitativo”
- “beneficia a todos”
También implícito:
- “es equilibrado”
- “reparte bien el impacto”
- “afecta a todos por igual”
- “no perjudica a nadie en particular”
--------------------------------------------------
EVIDENCIA NEGATIVA (-1):
Se asigna cuando el comentario expresa o sugiere que la medida es injusta,
desigual o afecta de forma negativa o desproporcionada a ciertos grupos.
Esto incluye:
- percepción de desigualdad o discriminación
- reparto injusto de costes o beneficios
- impacto negativo en personas o colectivos de forma no equitativa
Ejemplos:
- “es injusto”
- “discrimina”
- “perjudica a la gente”
- “siempre pagan los mismos”
También implícito:
- “esto castiga a la mayoría”
- “beneficia a unos y perjudica a otros”
- “los de siempre salen perdiendo”
- “esto afecta sobre todo a la gente normal”
--------------------------------------------------
EVIDENCIA NEUTRA (0):
Se asigna cuando el comentario hace referencia a la justicia o al impacto social,
pero NO expresa una valoración clara (ni positiva ni negativa).
Esto incluye:
- duda o ambivalencia sobre si es justo
- evaluaciones poco definidas o sin posicionamiento claro
- menciones al impacto social sin juicio explícito
Ejemplos:
- “no sé si es justo”
- “puede ser justo o no”
- “habría que ver si es equitativo”
--------------------------------------------------
NO INCLUYE:
- Legitimidad o legalidad → Legitimacion
- Resultados → Efectividad
- Actores → Confianza
--------------------------------------------------
REGLA FINAL:
Si hay referencia al impacto social → NO uses "2"
4) CONFIANZA INSTITUCIONAL
--------------------------------------------------
Se refiere a la confianza o desconfianza hacia los actores responsables.
Pregunta clave:
¿El COMENTARIO evalúa a los responsables de la medida?
--------------------------------------------------
QUÉ INCLUYE:
- Intenciones (honestas vs interesadas)
- Competencia (capaces vs incompetentes)
- Corrupción o intereses ocultos
--------------------------------------------------
EVIDENCIA POSITIVA (1):
Se asigna cuando el comentario expresa o sugiere que los actores responsables 
(gobierno, políticos o instituciones) son confiables, competentes o actúan con buenas intenciones.
Esto incluye:
- confianza en su capacidad para gestionar la medida
- percepción de profesionalidad o competencia
- atribución de intenciones honestas o responsables
Ejemplos:
- “confío en que lo harán bien”
- “son competentes”
También implícito:
- “están haciendo lo correcto”
- “parece que saben lo que hacen”
- “lo están gestionando bien”
--------------------------------------------------
EVIDENCIA NEGATIVA (-1):
Se asigna cuando el comentario expresa o sugiere desconfianza hacia los actores responsables,
atribuyéndoles incompetencia, malas intenciones o intereses propios.
Esto incluye:
- sospecha de intereses ocultos (dinero, política, beneficio propio)
- percepción de corrupción o manipulación
- percepción de incompetencia o mala gestión
Ejemplos:
- “solo quieren recaudar”
- “son corruptos”
- “no tienen ni idea”
También implícito:
- “no me fío de ellos”
- “lo hacen por su beneficio”
- “esto es puro interés político”
- “solo miran por ellos mismos”
--------------------------------------------------
EVIDENCIA NEUTRA (0):
Se asigna cuando el comentario menciona o implica a los actores responsables,
pero NO expresa una valoración clara (ni positiva ni negativa) sobre ellos.
Esto incluye:
- duda o ambivalencia
- evaluaciones débiles o poco definidas
- menciones sin juicio claro
Ejemplos:
- “no sé si lo hacen bien”
- “puede que tengan buenas intenciones”
- “el gobierno ha propuesto esto” (sin valoración)
--------------------------------------------------
REGLA CLAVE:
Debe haber referencia a actores (gobierno, políticos, instituciones).
--------------------------------------------------
NO INCLUYE:
- Legitimidad o legalidad → Legitimacion
- Resultados → Efectividad
- Impacto → Justicia
--------------------------------------------------
CASOS LÍMITE:
- “esto es ilegal porque el gobierno se ha pasado” → Legitimacion (-1) + Confianza (-1)
- “no me fío del gobierno aunque quizá funcione” → Confianza (-1) + Efectividad (0 o 1/-1 según el resto del comentario)
--------------------------------------------------
REGLA FINAL:
Si se evalúan actores → NO uses "2"
--------------------------------------------------
REGLAS DE FORMATO:
- Responde SOLO en JSON, sin texto adicional.
- Los valores deben ser SOLO el número en formato string.


--- COMENTARIO A ANALIZAR ---
__COMENTARIO__


FORMATO DE SALIDA SI excluded=false:

{{
  "Legitimacion_sociopolítica": "<1|-1|0|2>",
  "Efectividad_percibida": "<1|-1|0|2>",
  "Justicia_y_equidad_percibida": "<1|-1|0|2>",
  "Confianza_y_legitimidad_institucional": "<1|-1|0|2>"
}}
"""
    return system, user_template

# =====================================================
# 3. PREPARACIÓN DE TEXTO SEGURO (CONTROL DE LONGITUD)
# =====================================================

def preparar_texto_pilares_seguro(row, num_ctx=NUM_CTX):
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

# =====================================================
# 4. TRABAJADOR Y PIPELINE
# =====================================================

def safe_parse_json(text):
    try: return json.loads(text)
    except:
        try:
            start, end = text.find("{"), text.rfind("}") + 1
            return json.loads(text[start:end])
        except: return None

def call_vllm_worker_pilares(texto, system_prompt, user_template):
    
    if not texto: 
        return {p: "2" for p in PILARES}
    
    prompt_final = user_template.replace("__COMENTARIO__", texto)
    print(prompt_final)
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
            data = safe_parse_json(response.choices[0].message.content)
            return {p: str(data.get(p, "2")) for p in PILARES} if data else {p: "2" for p in PILARES}
        except Exception:
            time.sleep(1) 
    return {p: "2" for p in PILARES}

def ejecutar_pilares_analysis(u_conf):
    print("\n🚀 INICIANDO ANÁLISIS DE PILARES (vLLM - SAFE CONTEXT)")
    data_folder = Path(u_conf.general["output_folder"])
    print(f"📂 Buscando archivos en: {data_folder}")    
    # Intentar encontrar el archivo filtrado
    csv_path = data_folder / "datos_sentimiento_filtrados.csv"
    if not csv_path.exists():
        print(f"❌ ERROR: No existe el archivo {csv_path}. ¿Terminó el análisis de sentimiento?")
        # Fallback: buscar cualquier archivo analizado si el filtrado no existe
        archivos = list(data_folder.glob("*_analizado.csv"))
        if archivos: csv_path = archivos[0]
        else: raise Exception(f"No se encontró el archivo CSV en {data_folder}")

    # 🔥 LECTURA ROBUSTA DEL CSV (Detectar separador)
    with open(csv_path, 'r', encoding='utf-8') as f:
        primera_linea = f.readline()
        sep = ';' if ';' in primera_linea else ','
    
    print(f"📖 Leyendo {csv_path.name} (Separador: '{sep}')")
    df = pd.read_csv(csv_path, sep=sep, encoding='utf-8', on_bad_lines='skip', engine='python')
    
    # --- CAMBIO 1: Normalizar columnas a minúsculas (COMO EN EL DE SENTIMIENTO) ---
    df.columns = [c.lower() for c in df.columns]
    # ------------------------------------------------------------------------------

    for p in PILARES:
        col = f"sent_{p}"
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(object)

    system_p, user_t  = get_prompt_pilares(u_conf.tema, getattr(u_conf, "desc_tema", ""),  u_conf.general["keywords"], getattr(u_conf, "geo_scope", "España"), u_conf.languages)
    
    indices = df.index.tolist()

    for i in range(0, len(indices), MICRO_BATCH_SIZE):
        batch = indices[i : i + MICRO_BATCH_SIZE]
        with concurrent.futures.ThreadPoolExecutor(max_workers=MICRO_BATCH_SIZE) as executor:
            future_to_idx = {
                # --- CAMBIO 2: Usar .loc[idx] en lugar de .iloc[idx] ---
                executor.submit(call_vllm_worker_pilares, preparar_texto_pilares_seguro(df.loc[idx]), system_p, user_t): idx 
                for idx in batch
            }
            for future in concurrent.futures.as_completed(future_to_idx):
                idx_original = future_to_idx[future]
                res_dict = future.result()
                for p in PILARES:
                    df.at[idx_original, f"sent_{p}"] = res_dict[p]


    df.to_csv(data_folder / "datos_con_pilares.csv", index=False)
    print(f"✨ Finalizado. Guardado en datos_con_pilares.csv")

# =====================================================
# 6. FUNCIONES DE EJECUCIÓN (PARA JUGAR CON ELLAS)
# =====================================================

def modo_manual_test():
    """Crea datos ficticios para probar rápido"""
    u_conf_test = SimpleNamespace(
        tema="Prohibición del burka en espacios públicos",
        desc_tema="Regulación legal que prohíbe el uso del velo integral en espacios públicos.",
        population_scope="España",
        languages=["Castellano"],
        geo_scope="España",
        general={"output_folder": "./test_pilares_manual",
                 "keywords": ["burka", "velo integral", "prohibición del burka", 
                              "regulación del burka"]}
    )
    Path(u_conf_test.general["output_folder"]).mkdir(exist_ok=True)

    data_unificada = pd.DataFrame({
        'ID': [1, 2, 3, 4, 5, 6, 7],
        'RED_SOCIAL': ["Twitter", "Twitter", "Reddit", "Reddit", "Bluesky", "Bluesky", "Bluesky"],
        'CONTENIDO': [
            "Opinión impopular: Si me dan a elegir, que prohiban OnlyFans antes que el burka.",
            "COMPRE SU BURKA AQUÍ! Oferta exclusiva por tiempo limitado (2 EUROS). HTTP://BURKASUPER.COM",
            "VOX sobre la prohibición del burka que va a impulsar en el Congreso...",
            "Me parece que la libertad individual debe estar por encima de todo.",
            "Es una vulneración de la Constitución española.",
            "La Comisión Islámica de Portugal advierte sobre las consecuencias de la prohibición.",
            "PP y VOX votan en el Congreso una propuesta para prohibir el velo integral."
        ],
        'post_title': ["", "", "El problema de eliminar el burka", "Yolanda Díaz avisa a las derechas", "", "", ""],
        'sentimiento': [-1, 2, 0, 1, -1, 0, 0],
        'topic': ["libertad individual", "comercialización", "legislación", "libertad individual", "constitución", "legislación", "legislación"]
    })

    # Guardamos con el nombre que espera la función de carpeta para que sea compatible
    data_unificada.to_csv(Path(u_conf_test.general["output_folder"]) / "datos_sentimiento_filtrados.csv", index=False)
    ejecutar_pilares_analysis(u_conf_test)
    res_df = pd.read_csv(Path(u_conf_test.general["output_folder"]) / "datos_con_pilares.csv")

    print("\n📊 RESULTADOS FINALES (TODOS LOS PILARES):")

    # --- CORRECCIÓN AQUÍ: Todo en minúsculas ---
    cols_pilares = [c for c in res_df.columns if c.startswith('sent_')]
    cols_mostrar = ['red_social', 'sentimiento', 'topic'] + cols_pilares
    # -------------------------------------------

    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)

    print(res_df[cols_mostrar])


def modo_carpeta_real():
    """Procesa archivos reales en una carpeta específica"""
    ruta = "/home/rrss/proyecto_web/RRRS_last_version/project_web/Web_Proyecto/datos/admin/martes24b_copy"
    
    u_conf_test = SimpleNamespace(
        tema="Prohibición del burka en espacios públicos",
        # --- ESTA LÍNEA ES LA QUE FALTA Y CAUSA EL ERROR ---
        desc_tema="Regulación legal que prohíbe el uso del velo integral en espacios públicos.",
        # --------------------------------------------------
        population_scope="Público general",
        languages=["Castellano"],
        geo_scope="España",
        general={"output_folder": "./test_pilares_manual",
                 "keywords": ["burka", "velo integral", "prohibición del burka", 
                              "regulación del burka"]} # <--- AGREGADO PARA QUE EL PROMPT FUNCIONE
    )
    ejecutar_pilares_analysis(u_conf_test)


# =====================================================
# BLOQUE PRINCIPAL: CAMBIA EL INTERRUPTOR AQUÍ
# =====================================================
if __name__ == "__main__":
    
    # OPCIONES: "manual" o "carpeta"
    MODO = "manual" #"manual"  #"carpeta" # <--- CAMBIA ESTO PARA JUGAR
    
    if MODO == "manual":
        print("🛠️ Ejecutando MODO MANUAL (Datos de prueba)...")
        modo_manual_test()
    else:
        print("📂 Ejecutando MODO CARPETA (Datos reales)...")
        modo_carpeta_real()