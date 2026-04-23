# Para un entorno profesional con FastAPI, Celery, Redis y multiusuario
# lo ideal es utilizar la vLLM API Server (arquitectura de microservicios)
# Arrancar el servidor vLLM API Server (en terminal aparte):
# =============================================================
# python -m vllm.entrypoints.openai.api_server \
#     --model Qwen/Qwen2.5-7B-Instruct \
#     --gpu-memory-utilization 0.9 \
#     --max-model-len 4096 \
#     --port 8000
# vllm serve Qwen/Qwen3-30B-A3B \
#   --port 8001 \
#   --dtype bfloat16 \
#   --max-model-len 8192 \
#   --gpu-memory-utilization 0.80 \
#   --enable-expert-parallel
# =============================================================
import json
from openai import OpenAI

import json
from openai import OpenAI

# ==============================
# Configuración del Cliente vLLM
# ==============================
client = OpenAI(
    base_url="http://localhost:8001/v1", 
    api_key="token-local-no-necesario"
)

MODELO = "Qwen/Qwen2.5-14B-Instruct" #"Qwen/Qwen2.5-7B-Instruct" #"Qwen/Qwen3-30B-A3B"
 
IDIOMAS_COOFICIALES = {"catalán", "valenciano", "euskera", "gallego"}

# ==============================
# Función para generar prompt
# ==============================
def get_prompt_keywords(tema: str, idioma: str, poblacion: str):
    prompt = f"""
Eres un experto en social listening y análisis de conversación ciudadana.
--- DATOS DE ENTRADA ---
Tema principal: {tema}
Idioma: {idioma}
Población: {poblacion}


--- OBJETIVO ---
Genera términos de búsqueda que aparezcan en comentarios reales sobre: {tema}.

--- TEST DE VALIDEZ OBLIGATORIO ---
Antes de incluir cada término, aplica este filtro mental:
❌ ELIMINAR si el término podría aparecer en comentarios sobre OTRO tema diferente.
✅ INCLUIR solo si el término está tan ligado a "{tema}" que difícilmente aparece en otro contexto

--- REGLAS OBLIGATORIAS ---
1. Máximo 8 términos. Calidad sobre cantidad.
2. Cada término debe tener entre 2 y 5 palabras.
3. El término debe contener una referencia EXPLÍCITA al objeto del tema: {tema}.
4. Prohibido incluir términos que sean solo conceptos abstractos sin referencia directa al tema: {tema}.
5. Usar el lenguaje coloquial que usaría la población en redes sociales.
6. Responder únicamente en el idioma indicado: {idioma}.


--- FORMATO DE SALIDA (JSON) ---
Devuelve únicamente un JSON así:

{{
  "keywords": [
    {{
      "keyword": "termino clave",
      "languages": "{idioma}"
    }}
  ]
}}
"""
    return prompt

# ==============================
# Función para generar keywords por idioma
# ==============================
def generar_keywords_por_idioma(tema, idioma, poblacion):
    prompt_content = get_prompt_keywords(tema, idioma, poblacion)
    try:
        response = client.chat.completions.create(
            model=MODELO,
            messages=[
                {"role": "system", "content": "Eres un keyword generator que responde solo en JSON."},
                {"role": "user", "content": prompt_content}
            ],
            response_format={ "type": "json_object" },
            temperature=0.1
        )
        raw_json = response.choices[0].message.content
        data = json.loads(raw_json)
        return data["keywords"]
    except Exception as e:
        print(f"❌ Error generando keywords para {idioma}: {e}")
        return []

# ==============================
# Función para combinar resultados
# ==============================
def combinar_keywords_multilingue(keywords_por_idioma):
    combinadas = {}
    for kw in keywords_por_idioma:
        key = kw["keyword"].strip()
        idioma = kw["languages"]
        if key in combinadas:
            # Añadir idioma si no está ya
            idiomas_existentes = set(combinadas[key].split(", "))
            idiomas_existentes.add(idioma)
            combinadas[key] = ", ".join(sorted(idiomas_existentes))
        else:
            combinadas[key] = idioma
    # Crear lista final
    return {"keywords": [{"keyword": k, "languages": v} for k, v in combinadas.items()]}

# ==============================
# EJECUCIÓN MANUAL (CON DATOS DE KEYWORDS)
# ==============================
if __name__ == "__main__":
    tema_test = "uso carril VAO"#"reducción iva 10'%' gasolina"
    idiomas_test = ["Castellano", "Catalán", "Gallego", "Euskera", "Inglés", "Francés", "Italiano", "Portugués"]
    poblacion_test = "Jovenes entre 18 y 30 años, residentes en España, interesados en política y redes sociales."

    all_keywords = []

    for idioma in idiomas_test:
        kws = generar_keywords_por_idioma(tema_test, idioma, poblacion_test)
        all_keywords.extend(kws)

    resultado_final = combinar_keywords_multilingue(all_keywords)

    print("\n✅ RESULTADO FINAL MULTILINGÜE:")
    print(json.dumps(resultado_final, indent=2, ensure_ascii=False))
    print(f"\nSe han generado {len(resultado_final['keywords'])} keywords únicas.")