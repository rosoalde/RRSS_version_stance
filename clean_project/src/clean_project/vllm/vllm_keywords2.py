import json
from openai import OpenAI
from ddgs import DDGS
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==============================
# Configuración
# ==============================
client = OpenAI(
    base_url="http://localhost:8001/v1",#"http://localhost:8001/v1",
    api_key="token-local"
)
# vllm serve Qwen/Qwen2.5-14B-Instruct \
#   --port 8001 \
#   --dtype bfloat16 \
#   --max-model-len 7000 \
#   --gpu-memory-utilization 0.95
MODELO = "Qwen/Qwen2.5-14B-Instruct" #"Qwen/Qwen2.5-7B-Instruct" #"Qwen/Qwen3-30B-A3B"

IDIOMAS_COOFICIALES = {"catalán", "valenciano", "euskera", "gallego"}


# ==============================
# Búsqueda web (DuckDuckGo)
# ==============================
def buscar_contexto_web(tema: str, max_results: int = 5) -> str:
    """
    Busca información actual sobre el tema en la web.
    Devuelve un texto con los snippets más relevantes.
    Si falla (sin internet, proxy bloqueado), devuelve cadena vacía
    y el pipeline continúa sin contexto web.
    """
    try:
        with DDGS() as ddgs:
            resultados = ddgs.text(tema, max_results=max_results)
            if not resultados:
                return ""
            textos = []
            for r in resultados:
                titulo = r.get("title", "")
                cuerpo = r.get("body", "")
                if cuerpo:
                    textos.append(f"- {titulo}: {cuerpo}")
            contexto = "\n".join(textos)
            print(f"   🌐 Contexto web obtenido ({len(textos)} resultados)")
            return contexto
    except Exception as e:
        print(f"   ⚠️  Búsqueda web no disponible: {e}")
        return ""
 
 
# ==============================
# Capa 1: Expansión del tema
# ==============================
def get_prompt_topic_expansion(tema: str, population_scope: str, contexto_web: str = "") -> str:
 
    seccion_web = ""
    if contexto_web:
        seccion_web = f"""
--- CONTEXTO ACTUAL (fuentes web recientes) ---
{contexto_web}
 
Usa este contexto para enriquecer tu análisis con información actual.
"""
 
    return f"""
Eres un analista de medios y redes sociales.
 
Dado este tema de interés público: "{tema}" y contexto geográfico asociado: "{population_scope}", tu tarea es expandirlo y enriquecerlo con información actual obtenida de la web.
{seccion_web}
Devuelve un JSON con esta estructura:
{{
  "tema_normalizado": "nombre oficial o formal del tema",
  "descripcion_breve": "qué es exactamente en 2 frases",
  "terminos_oficiales": ["términos usados por medios o instituciones"],
  "hashtags_probables": ["#ejemploHashtag"],
  "temas_relacionados_confundibles": ["temas similares que HAY QUE EVITAR mezclar"]
}}
 
Responde SOLO en JSON, sin texto adicional, sin bloques de código.
"""
 
def expandir_tema(tema: str, population_scope: str) -> dict | None:
    print("   🔎 Buscando contexto web...")
    contexto_web = buscar_contexto_web(tema)
 
    prompt = get_prompt_topic_expansion(tema, population_scope, contexto_web)
    print(f"   📝 Prompt generado: {prompt}")
    try:
        response = client.chat.completions.create(
            model=MODELO,
            messages=[
                {
                    "role": "system",
                    "content": "Eres un analista experto. Respondes únicamente en JSON válido."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        raw = response.choices[0].message.content
        return json.loads(raw)
    except Exception as e:
        print(f"❌ Error en expansión del tema: {e}")
        return None
 
def get_ejemplos_por_idioma(idioma: str) -> str:
    idioma_lower = idioma.lower()
    
    # --- BLOQUE DE IDIOMAS COOFICIALES Y EXTRANJEROS (Específicos para corregir errores de traducción) ---
    if idioma_lower in ["catalan", "català", "valenciano"]:
        return """
--- EJEMPLOS ESPECÍFICOS PARA CATALÁN ---
✅ BIEN: "pantalà de sagunt" (Término correcto)
✅ BIEN: "passeig marítim de sagunt" (Adaptación natural)
❌ MAL: "pantallà sagunt" (Palabra inventada / error ortográfico)
❌ MAL: "vistes pantalà" (Demasiado genérico)
"""
    elif idioma_lower in ["euskera", "basque"]:
        return """
--- EJEMPLOS ESPECÍFICOS PARA EUSKERA ---
✅ BIEN: "saguntoko kaia" (Traducción natural de muelle/pantalán)
✅ BIEN: "saguntoko itsas pasealekua" (Adaptación correcta)
❌ MAL: "pantalanaren bide maritimoa" (Traducción literal robótica)
❌ MAL: "sagunton pantalan" (Gramática incorrecta)
"""
    elif idioma_lower in ["ingles", "english", "en"]:
        return """
--- EJEMPLOS ESPECÍFICOS PARA INGLÉS ---
✅ BIEN: "sagunto pier" (Traducción natural)
✅ BIEN: "sagunto promenade" (Adaptación correcta)
❌ MAL: "sagunto harbor walk" (Artificial / poco usado)
❌ MAL: "pantalan sagunto" (No está traducido)
"""
    elif idioma_lower in ["frances", "french", "fr"]:
        return """
--- EJEMPLOS ESPECÍFICOS PARA FRANCÉS ---
✅ BIEN: "jetée de sagonte" (Traducción natural)
✅ BIEN: "promenade de sagonte" (Adaptación correcta)
❌ MAL: "espacio urbain sagunto" (Mezcla de idiomas / Spanglish)
❌ MAL: "pantalan maritime" (Palabra inventada en francés)
"""
    elif idioma_lower in ["portugues", "portuguese", "pt"]:
        return """
--- EJEMPLOS ESPECÍFICOS PARA PORTUGUÉS ---
✅ BIEN: "cais de sagunto" (Traducción natural)
✅ BIEN: "passeio marítimo de sagunto" (Adaptación correcta)
❌ MAL: "pantilhão sagunto" (Palabra inventada / falso amigo)
❌ MAL: "passeio pantilhão" (No existe en portugués)
"""
    elif idioma_lower in ["italiano", "italian", "it"]:
        return """
--- EJEMPLOS ESPECÍFICOS PARA ITALIANO ---
✅ BIEN: "molo di sagunto" (Traducción natural)
✅ BIEN: "lungomare di sagunto" (Adaptación correcta)
❌ MAL: "pantalone sagunto" (Traducción ridícula / falso amigo)
❌ MAL: "connesso città porto" (Frase robótica sin sentido)
"""

    # --- BLOQUE CASTELLANO (Ejemplos generales de lógica de búsqueda) ---
    else: 
        return """
--- EJEMPLOS DE LÓGICA DE BÚSQUEDA (CASTELLANO) ---

Para el tema "Pantalán de Sagunto":
✅ "pantalán de sagunto" (Término central)
✅ "paseo marítimo sagunto" (Variante natural)
❌ "pantallán sagunto" (Error ortográfico)
❌ "zona sagunto" (Demasiado genérico)

Para el tema "carril VAO":
✅ "carril VAO"               → término central
✅ "carril vehículo alta ocupación"  → nombre oficial completo
✅ "vao autopista"            → variante contextualizada
✅ "carril bus VAO"           → variante con tipo de vía
✅ "carril multiocupante"     → sinónimo técnico real
✅ "viajar en VAO"            → forma verbal natural
❌ "carril vao hoy"           → temporal
❌ "vaovao"                   → inventado
❌ "movilidad sostenible"     → demasiado genérico

Para el tema "prohibición burka":
✅ "prohibición burka"        → término central
✅ "burka prohibida"          → variante 
✅ "burka prohibida en espacios públicos" → referencia directa
❌ "identidad oculta"         → demasiado genérico
❌ "seguridad ciudadana"      → demasiado genérico
❌ "velo integral"            → demasiado genérico no se usa en comentarios reales.    

Para el tema "Regularización de Inmigrantes":
✅ "regularización de inmigrantes" → término central
✅ "regularización inmigrantes" → variante común
✅ "legalizar inmigrantes" → sinónimo real usado en redes
✅ "regularización extraordinaria inmigrantes" → variante común
✅ "amnistía inmigrantes" → genérico
❌ "decreto regularización" → genérico
❌ "regularización masiva" → demasiado genérico
❌ "regularización marroquíes" → demasiado específico

Para el tema "balizas v16":
✅ "balizas v16" → término central
✅ "balizas emergencia v16" → variante común
❌ "triángulo nuevo" → inventado
❌ "baliza v16 hoy" → temporal
❌ "dispositivo emergencia" → demasiado genérico
"""
# ==============================
# Capa 2: Generación de keywords
# ==============================
def get_instruccion_lengua_cooficial(idioma: str) -> str:
    if idioma.lower() in IDIOMAS_COOFICIALES:

        return f"""
⚠️ IMPORTANTE: Responde EXCLUSIVAMENTE en {idioma}.
No mezcles con castellano ni ningún otro idioma.
Si no tienes suficientes términos en {idioma},
usa los términos en castellano que la comunidad de esa región
usaría realmente en redes sociales, ya que el code-switching
(mezcla de lenguas) es habitual en Twitter/X, Instagram y TikTok.
"""
    return ""
 
 
def get_prompt_keywords(tema: str, population_scope: str, idioma: str, brief: dict) -> str:
    instruccion_lengua = get_instruccion_lengua_cooficial(idioma)
    ejemplos_dinamicos = get_ejemplos_por_idioma(idioma)
    return f"""
Eres un experto en recuperación de información para redes sociales. Tu objetivo es generar términos de búsqueda específicos en el idioma **{idioma.upper()}**.

--- REGLA DE ORO ---
1. El idioma de trabajo es **{idioma.upper()}**. 
2. Está TERMINANTEMENTE PROHIBIDO usar palabras en otro idioma si existe una traducción natural en {idioma}.
3. Usa la gramática y léxico propio del idioma: **{idioma.upper()}**.
--- CONTEXTO DEL TEMA ---
Tema original: {tema}
Tema normalizado: {brief.get("tema_normalizado", tema)}
Descripción: {brief.get("descripcion_breve", "")}
Términos coloquiales reales: {", ".join(brief.get("terminos_coloquiales", []))}
⚠️ NO confundir con: {", ".join(brief.get("temas_relacionados_confundibles", []))}

--- OBJETIVO ---
Traduce mentalmente el tema "{tema}", el tema normalizado "{brief.get("tema_normalizado", tema)}" y su descripción "{brief.get("descripcion_breve", "")}" al {idioma}.
Genera variantes y sinónimos del concepto que un usuario nativo de {idioma} usaría en redes sociales para referirse a este tema.
NO HAGAS TRADUCCIONES ROBÓTICAS. Piensa en cómo escribiría un ciudadano nativo de {idioma} en Bluesky, Reddit, YouTube, Twitter/X, Instagram, TikTok otras redes sociales o foros.

El objetivo es maximizar la cobertura de comentarios sobre este tema,
independientemente de si son positivos, negativos o neutros.

--- ESTRATEGIA ---
- Piensa en todas las referencias DIRECTAS al tema: {brief.get("tema_normalizado", tema)}

{ejemplos_dinamicos}

--- REGLAS ---
1. Sólo términos relevantes. Maximo 10 términos.
2. Entre 2 y 4 palabras por término.
4. PROHIBIDO inventar términos o siglas que no existan en el habla real.
5. Idioma: {idioma}.





--- FORMATO DE SALIDA (JSON) ---
{{
    "configuracion": {{
    "idioma_solicitado": "{idioma}",
    "traduccion_fiel_del_tema": "Escribe aquí el nombre del tema traducido al {idioma}"
  }},
  "keywords": [
    {{
      "keyword": "termino clave",
      "languages": "{idioma}",
      "razon_tema": "por qué es específico de este tema y no de otro",
      "razon_idioma": "explicación en castellano de por qué este término es natural en {idioma}"
    }}
  ]
}}
"""
 
 
def generar_keywords_por_idioma(tema: str, idioma: str, population_scope: str, brief: dict) -> list:
    prompt = get_prompt_keywords(tema, population_scope, idioma, brief)
    print(f"   📝 Prompt para {idioma}:\n{prompt}")
    try:
        response = client.chat.completions.create(
            model=MODELO,
            messages=[
                {
                    "role": "system",
                    "content": "Eres un keyword generator experto en redes sociales. Respondes solo en JSON válido."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        return data.get("keywords", [])
    except Exception as e:
        print(f"❌ Error generando keywords para {idioma}: {e}")
        return []
 
 
# ==============================
# Capa 3: Combinación y deduplicación
# ==============================
def combinar_keywords_multilingue(keywords_por_idioma: list) -> dict:
    combinadas = {}
    razones = {}
 
    for kw in keywords_por_idioma:
        key = kw["keyword"].strip().lower()
        idioma = kw.get("languages", "")
        razon = kw.get("razon", "")
 
        if key in combinadas:
            idiomas_existentes = set(combinadas[key].split(", "))
            idiomas_existentes.add(idioma)
            combinadas[key] = ", ".join(sorted(idiomas_existentes))
        else:
            combinadas[key] = idioma
            razones[key] = razon
 
    return {
        "keywords": [
            {
                "keyword": k,
                "languages": v,
                "razon": razones.get(k, "")
            }
            for k, v in combinadas.items()
        ]
    }
 
 
# ==============================
# Pipeline principal
# ==============================

def generar_keywords(tema: str, population_scope: str, idiomas: list) -> dict:
    print(f"\n🔍 Tema recibido: '{tema}'")

    print("📋 Expandiendo contexto del tema...")
    brief = expandir_tema(tema, population_scope)
    if not brief:
        print("⚠️  No se pudo expandir el tema. Abortando.")
        return {}

    print(f"✅ Tema normalizado: {brief.get('tema_normalizado')}")

    # Llamadas paralelas por idioma
    print(f"🚀 Generando keywords en {len(idiomas)} idiomas en paralelo...")
    todas_las_keywords = []

    with ThreadPoolExecutor(max_workers=len(idiomas)) as executor:
        futuros = {
            executor.submit(generar_keywords_por_idioma, tema, population_scope, idioma, brief): idioma
            for idioma in idiomas
        }
        for futuro in as_completed(futuros):
            idioma = futuros[futuro]
            try:
                kws = futuro.result()
                print(f"   ✅ {idioma}: {len(kws)} keywords")
                todas_las_keywords.extend(kws)
            except Exception as e:
                print(f"   ❌ {idioma}: error — {e}")

    resultado = combinar_keywords_multilingue(todas_las_keywords)
    print(f"\n✅ Total keywords únicas: {len(resultado['keywords'])}")

    return {
        "tema_original": tema,
        "brief": brief,
        "resultado": resultado
    }
# ==============================
# Ejemplo de uso
# ==============================
if __name__ == "__main__":
 
    IDIOMAS = [
        "castellano",
        # "catalán",
        # "valenciano",
        # "euskera",
        # "gallego",
        # "inglés",
        # "francés",
        # "italiano",
        # "portugués"
    ]
 
    temas_ejemplo = [
        "regularización de inmigrantes",
        # "balizas V16"
        # "uso carril VAO",
        # "reducción IVA 10%",
        # "prohibición burka",
    ]
 
    for tema in temas_ejemplo:
        output = generar_keywords(tema, IDIOMAS)
 
        print("\n--- RESULTADO FINAL ---")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        print("\n" + "=" * 60 + "\n")
 