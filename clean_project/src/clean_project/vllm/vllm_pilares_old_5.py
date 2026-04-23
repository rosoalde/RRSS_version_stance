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
NUM_CTX = 4096 # Límite de contexto del modelo

PILARES = [
    "Legitimación_sociopolítica",
    "Efectividad_percibida",
    "Justicia_y_equidad_percibida",
    "Confianza_y_legitimidad_institucional",
    "Marcos_discursivos_dominantes"
]

# =====================================================
# 2. PROMPT DE PILARES (CON CONTEXTO Y ENCUADRE)
# =====================================================

def get_prompt_pilares(tema, desc_tema, languages, geo_scope):
    return f'''Eres un experto en análisis de opiniones y comunicación política.
Tu tarea es identificar juicios de valor subjetivos (incluyendo ironía/sarcasmo) sobre el tema: {tema} (descripción: {desc_tema}).

--- GUÍA DE ENTRADA (CONTEXTO) ---
El texto a analizar puede contener etiquetas para ayudarte a entender la intención:
- [TÍTULO POST] / [CUERPO POST]: Contexto original de Reddit.
- [TÍTULO VIDEO] / [DESCRIPCIÓN]: Contexto original de YouTube.
- [TWEET ANTERIOR]: Mensaje previo en un hilo de Twitter.
- [COMENTARIO]: Es la opinión principal que debes evaluar.

🚨 PASO 0: FILTRO DE EXCLUSIÓN TOTAL (Gatekeeper) 🚨
Eres un filtro de elegibilidad. Tu única tarea en este paso es decidir si el texto es una OPINIÓN válida (relevante para {geo_scope}) o si debe EXCLUIRSE.

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
Excluir solo si el texto está principalmente en un idioma NO permitido.
Idiomas permitidos: {languages}.

B) GEOGRAFÍA:
Excluir solo si NO hay refrealción clara con el ámbito geografico seleccionado {geo_scope}.
Si hay cualquier referencia razonable a al ámbito geográfico seleccionado, NO excluir.

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
Excluir solo si NO se refiere al objeto de opinión del tema: {tema}.
Si hay duda, NO excluir.

⚠️ INSTRUCCIÓN CRÍTICA:
- Analiza EXCLUSIVAMENTE el bloque "COMENTARIO".
- El bloque "CONTEXTO" solo sirve para entender referencias implícitas, relación con ámbito geográfico, o relación con tema de análisis.
- NO evalúes el título ni el cuerpo.
- Si el comentario es una opinión aunque el contexto sea noticia, NO excluir.

FORMATO DE SALIDA SI excluded=true:
Devuelve SOLO este JSON (sin texto extra):
{{
  "Legitimación_sociopolítica": "2",
  "Efectividad_percibida": "2",
  "Justicia_y_equidad_percibida": "2",
  "Confianza_y_legitimidad_institucional": "2",
  "Marcos_discursivos_dominantes": "2",
}}

🚨 PASO 1: SOLO si excluded=false 🚨
Analiza los 5 pilares y asigna SOLO un número en formato string ( "1", "-1", "0", "2" ):
- "1" = Positivo
- "-1" = Negativo
- "0" = Neutro/Ambivalente sin carga clara
- "2" = No aplica / No hay evidencia en el texto sobre ese pilar
IMPORTANTE: Usa "2" SOLO si de verdad no hay ninguna evidencia. Si hay indicios sutiles o implícitos, elige 1/-1/0 según corresponda.

1) Legitimación Sociopolítica
- "1": Acepta la medida/política como válida, necesaria o razonable.
- "-1": La rechaza por ilegítima, abusiva o prohibicionista.
- "0": Mención neutral o ambivalente.
- "2": No evalúa legitimidad.

2) Efectividad Percibida
- "1": Cree que funciona o es útil.
- "-1": Cree que es inútil/fracaso/contraproducente.
- "0": Ambivalente.
- "2": No evalúa efectividad.

3) Justicia y Equidad
- "1": La ve justa/equitativa/solidaria.
- "-1": La ve injusta/discriminatoria/desigual.
- "0": Ambivalente.
- "2": No evalúa justicia.

4) Confianza Institucional
- "1": Confía en autoridades/gestores (honestidad, competencia).
- "-1": Desconfía (corrupción, afán recaudatorio, incompetencia).
- "0": Ambivalente.
- "2": No menciona responsables o confianza.

5) Marcos Discursivos
- "1": Encuadre positivo (solución, progreso, seguridad, mejora).
- "-1": Encuadre negativo (amenaza, robo, control, miedo, manipulación).
- "0": Ambivalente o poco claro.
- "2": Sin encuadre identificable.

REGLAS DE FORMATO:
- Responde SOLO en JSON, sin texto adicional.
- Los valores deben ser SOLO el número en formato string.

FORMATO DE SALIDA SI excluded=false:
{{
  "Legitimación_sociopolítica": "<1|-1|0|2>",
  "Efectividad_percibida": "<1|-1|0|2>",
  "Justicia_y_equidad_percibida": "<1|-1|0|2>",
  "Confianza_y_legitimidad_institucional": "<1|-1|0|2>",
  "Marcos_discursivos_dominantes": "<1|-1|0|2>",
}}
'''

# =====================================================
# 3. PREPARACIÓN DE TEXTO SEGURO (CONTROL DE LONGITUD)
# =====================================================

def preparar_texto_pilares_seguro(row, base_prompt):
    def count_tokens(texto):
        return len(str(texto)) // 4 if texto else 0

    def safe_text(val):
        if val is None or pd.isna(val) or str(val).strip().lower() == "nan": return ""
        return str(val).strip()

    # 1. Capturar todos los campos posibles
    comentario = safe_text(row.get("CONTENIDO", row.get("contenido", "")))
    if not comentario: return None

    titulo = safe_text(row.get("post_title", row.get("TITULO", "")))
    cuerpo = safe_text(row.get("post_selftext", row.get("CUERPO", "")))
    tweet_previo = safe_text(row.get("BeforeContenido", ""))
    
    # 2. Calcular presupuesto de tokens
    # Dejamos un margen de 400 tokens para el sistema y la respuesta JSON
    tokens_prompt = count_tokens(base_prompt)
    presupuesto_total = NUM_CTX - tokens_prompt - 400
    
    # 3. El COMENTARIO es la prioridad
    tokens_com = count_tokens(comentario)
    if tokens_com > presupuesto_total:
        comentario = comentario[:presupuesto_total * 4] # Truncar comentario si es masivo
        return f"[COMENTARIO]: {comentario}"

    # 4. Añadir contexto si queda espacio
    espacio_restante = presupuesto_total - tokens_com
    contexto_str = ""
    
    # Prioridad de contexto: Título > Tweet Anterior > Cuerpo
    if titulo and espacio_restante > 50:
        label = "[TÍTULO POST]" if row.get("RED_SOCIAL") == "Reddit" else "[CONTEXTO]"
        contexto_str += f"{label}: {titulo}\n"
        espacio_restante -= count_tokens(contexto_str)

    if tweet_previo and espacio_restante > 50:
        contexto_str += f"[TWEET ANTERIOR]: {tweet_previo}\n"
        espacio_restante -= count_tokens(contexto_str)

    if cuerpo and espacio_restante > 100:
        max_chars_cuerpo = espacio_restante * 4
        contexto_str += f"[CUERPO POST]: {cuerpo[:max_chars_cuerpo]}\n"

    return f"{contexto_str}\n[COMENTARIO]: {comentario}"

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

def call_vllm_worker_pilares(texto, base_prompt):
    if not texto: return {p: "2" for p in PILARES}
    prompt_final = f"{base_prompt}\n\nTEXTO A ANALIZAR:\n\"\"\"\n{texto}\n\"\"\""
    print(prompt_final)
    try:
        response = client.chat.completions.create(
            model=MODELO_VLLM,
            messages=[
                {"role": "system", "content": "Eres un experto en análisis político. Responde solo en JSON."},
                {"role": "user", "content": prompt_final}
            ],
            temperature=0, response_format={"type": "json_object"}
        )
        data = safe_parse_json(response.choices[0].message.content)
        return {p: str(data.get(p, "2")) for p in PILARES} if data else {p: "2" for p in PILARES}
    except: return {p: "2" for p in PILARES}

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
    
    for p in PILARES:
        col = f"sent_{p}"
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(object)

    base_prompt = get_prompt_pilares(u_conf.tema, u_conf.desc_tema, u_conf.languages, getattr(u_conf, "geo_scope", "España"))
    indices = df.index.tolist()

    for i in range(0, len(indices), MICRO_BATCH_SIZE):
        batch = indices[i : i + MICRO_BATCH_SIZE]
        with concurrent.futures.ThreadPoolExecutor(max_workers=MICRO_BATCH_SIZE) as executor:
            # Mapeamos el futuro al índice original
            future_to_idx = {
                executor.submit(call_vllm_worker_pilares, preparar_texto_pilares_seguro(df.iloc[idx], base_prompt), base_prompt): idx 
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
        population_scope="Público general",
        languages=["Castellano"],
        geo_scope="España",
        general={"output_folder": "./test_pilares_manual"}
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

    # Seleccionamos dinámicamente todas las columnas que empiezan por 'sent_' 
    # (esto incluye sentimiento general y los 5 pilares)
    cols_pilares = [c for c in res_df.columns if c.startswith('sent_')]
    cols_mostrar = ['RED_SOCIAL', 'sentimiento', 'topic'] + cols_pilares

    # Ajustamos el ancho de la consola para que no se corte la tabla
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)

    print(res_df[cols_mostrar])


def modo_carpeta_real():
    """Procesa archivos reales en una carpeta específica"""
    ruta = "/home/rrss/proyecto_web/RRSS_version_stance/project_web/Web_Proyecto/datos/admin/martes24b_copy"
    
    u_conf_folder = SimpleNamespace(
        tema="prohibición burka en espacios públicos",
        languages=["Castellano"],
        geo_scope="España",
        general={
            "output_folder": ruta,
            "keywords": ["burka", "prohibición burka"]
        }
    )
    ejecutar_pilares_analysis(u_conf_folder)


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