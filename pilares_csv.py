import pandas as pd
import json
import ollama
from pathlib import Path
from tqdm import tqdm

# ======================================================
# CONFIGURACIÓN MANUAL
# ======================================================

CSV_PATH = "datos_sentimiento_filtrados.csv"  # <-- cambia aquí
OUTPUT_PATH = "datos_con_pilares.csv"
MODEL_NAME = "qwen2.5:1.5b"#"gemma3:4b"
BATCH_SIZE = 3
NUM_CTX = 4096

TEMA = "prohibición del burka en espacios públicos"
LANGUAGES = "Castellano"
GEO_SCOPE = "Global"

PILARES = [
    "Legitimación_sociopolítica",
    "Efectividad_percibida",
    "Justicia_y_equidad_percibida",
    "Confianza_y_legitimidad_institucional"
]

# ======================================================
# PROMPT ORIGINAL (EL TUYO COMPLETO)
# ======================================================

def get_prompt(tema, languages, geo_scope):
    return f'''Eres un experto en análisis de opiniones.
Tu tarea es identificar EXCLUSIVAMENTE juicios de valor subjetivos (incluyendo ironía/sarcasmo) sobre el tema {tema}.

🚨 PASO 0: FILTRO DE EXCLUSIÓN TOTAL (Gatekeeper) 🚨
Eres un filtro de elegibilidad. Tu única tarea en este paso es decidir si el texto es una OPINIÓN válida (relevante para {geo_scope}) o si debe EXCLUIRSE.

✅ PRINCIPIO CLAVE (anti-falsos excluidos):
- Si tienes DUDA razonable entre excluir o no, elige excluded=false y pasa al PASO 1.
- Solo usa excluded=true cuando el criterio de exclusión sea CLARO e INEQUÍVOCO.
- NO excluyas por “falta de contexto”: usa solo el texto.

CRITERIOS DE EXCLUSIÓN TOTAL:
A) IDIOMA:
Excluir solo si el texto está principalmente en un idioma NO permitido.
Idiomas permitidos: {languages}.

B) GEOGRAFÍA:
Excluir solo si trata principalmente sobre otro país Y NO hay referencia clara a {geo_scope}.

C) NOTICIA PURA:
Excluir SOLO si es texto informativo sin valoración personal.

D) PUBLICIDAD:
Excluir solo si hay intención comercial clara.

E) DESCRIPCIÓN NEUTRA:
Excluir SOLO si es descripción impersonal sin juicio.

⚠️ INSTRUCCIÓN CRÍTICA:
- Analiza EXCLUSIVAMENTE el bloque "COMENTARIO".
- El bloque "CONTEXTO" solo sirve para entender referencias implícitas.
- NO evalúes el título ni el cuerpo.
- Si el comentario es una opinión aunque el contexto sea noticia, NO excluir.

FORMATO SI excluded=true:
{{
  "Legitimación_sociopolítica": "2",
  "Efectividad_percibida": "2",
  "Justicia_y_equidad_percibida": "2",
  "Confianza_y_legitimidad_institucional": "2",
  "Marcos_discursivos_dominantes": "2"
}}

🚨 PASO 1: SOLO si excluded=false 🚨
Asigna SOLO un número string: "1", "-1", "0", "2"

Responde SOLO en JSON.
'''

# ======================================================
# TEXTO SEGURO CON LÍMITE DE CONTEXTO
# ======================================================

def preparar_texto_seguro(row, base_prompt):

    def count_tokens(texto):
        if not texto or pd.isna(texto):
            return 0
        return len(str(texto)) // 4

    comentario = str(row.get("CONTENIDO", "")).strip()
    titulo = str(row.get("TITULO", "")).strip()
    cuerpo = str(row.get("CUERPO", "")).strip()

    tokens_prompt = count_tokens(base_prompt)
    estructura_fija = """
    === CONTEXTO (NO ANALIZAR, SOLO PARA ENTENDER) ===

    === COMENTARIO (ANALIZAR SOLO ESTO) ===
    """

    tokens_estructura = count_tokens(estructura_fija)

    presupuesto = NUM_CTX - tokens_prompt - tokens_estructura - 200


    print(f"Presupuesto disponible: {presupuesto}")

    # 1️⃣ El comentario SIEMPRE va completo o truncado
    tokens_com = count_tokens(comentario)

    if tokens_com > presupuesto:
        comentario = comentario[:presupuesto * 4]
        print("⚠ Comentario truncado")

    texto_final = "\n\n=== CONTEXTO (NO ANALIZAR, SOLO PARA ENTENDER) ===\n"

    usados = count_tokens(comentario)

    espacio_restante = presupuesto - usados

    # 2️⃣ Añadir contexto SOLO si queda espacio
    if espacio_restante > 100:

        contexto = ""

        if titulo:
            contexto += f"[TITULO]\n{titulo}\n\n"

        if cuerpo:
            max_chars = espacio_restante * 4
            contexto += f"[CUERPO]\n{cuerpo[:max_chars]}\n"

        texto_final += contexto

    texto_final += "\n\n=== COMENTARIO (ANALIZAR SOLO ESTO) ===\n"
    texto_final += comentario

    print("Tokens finales estimados:", count_tokens(texto_final))

    return texto_final
# ======================================================
# PARSER JSON ROBUSTO
# ======================================================

def safe_parse_json(text):

    print("\n--- RAW RESPONSE ---")
    print(text)

    try:
        return json.loads(text)
    except:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            return json.loads(text[start:end])
        except Exception as e:
            print("❌ Error parseando JSON:", e)
            return None

# ======================================================
# LLAMADA LLM
# ======================================================

def call_llm_batch(prompts):

    responses = []

    for prompt in prompts:

        print("\n" + "="*100)
        print("PROMPT ENVIADO:")
        print(prompt)
        print("="*100)

        try:
            response = ollama.chat(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": 0.0,
                    "num_ctx": NUM_CTX
                }
            )

            content = response["message"]["content"]

        except Exception as e:
            print("❌ Error llamando modelo:", e)
            content = "{}"

        responses.append(content)

    return responses

# ======================================================
# EJECUCIÓN COMPLETA
# ======================================================

def main():

    print(f"\n=== Analizando {CSV_PATH.name} ===")
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        primera_linea = f.readline()
        sep = ';' if ';' in primera_linea else ','

    df = pd.read_csv(CSV_PATH, sep=sep, encoding='utf-8', engine='python', on_bad_lines='skip')

    print("Filas totales:", len(df))

    # columnas debug nuevas
    for p in PILARES:
        df[f"debug_{p}"] = None

    base_prompt = base_prompt = get_prompt(TEMA, LANGUAGES, GEO_SCOPE)


    indices = list(df.index)

    for i in range(0, len(indices), BATCH_SIZE):

        batch_indices = indices[i:i+BATCH_SIZE]
        prompts = []

        print(f"\n\n########## BATCH {i//BATCH_SIZE + 1} ##########")

        for idx in batch_indices:

            texto = preparar_texto_seguro(df.loc[idx], base_prompt)


            prompt = f"{base_prompt}\n\nTEXTO A ANALIZAR:\n\"\"\"\n{texto}\n\"\"\""

            prompts.append(prompt)

        responses = call_llm_batch(prompts)

        for idx_df, response in zip(batch_indices, responses):

            print(f"\nProcesando respuesta fila {idx_df}")

            data = safe_parse_json(response)

            print("\nJSON PARSEADO:")
            print(data)

            if not data:
                continue

            for p in PILARES:
                valor = str(data.get(p, "MISSING"))
                df.at[idx_df, f"debug_{p}"] = valor
                print(f"✔ {p} → {valor}")

        df.to_csv(OUTPUT_PATH, index=False)
        print("\n💾 Guardado incremental.")

    print("\n\n✅ FINALIZADO. Resultado en:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
