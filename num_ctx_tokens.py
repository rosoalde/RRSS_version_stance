import pandas as pd
from pathlib import Path

TEMA = "Opinión pública sobre la movilidad de los adultos mayores"
GEO_SCOPE = ["Provincia de Valencia"]

def build_prompts(tema, geo_scope):
    system = (
        "Eres un clasificador automático.\n"
        "NO expliques.\n"
        "NO escribas texto adicional.\n"
        "Responde SOLO un número."
    )

    user = f"""
Tema de análisis: {tema}

Ámbito geográfico válido:
{", ".join(geo_scope)}

Definiciones importantes:
- Solo considera relacionados los textos donde se expresa claramente una opinión, valoración o experiencia sobre {tema} en {geo_scope}.
- Textos informativos, noticias, estadísticas, anuncios o enlaces → NO relacionado (2).
- Si NO habla del tema → NO relacionado (2).
- Si ocurre fuera del ámbito → NO relacionado (2).

Texto a clasificar:
\"\"\"{{texto}}\"\"\"

Reglas de salida:
1  → positivo
-1 → negativo
0  → neutral
2  → no relacionado

Devuelve SOLO uno de estos valores:
1
-1
0
2
"""
    return system, user

SYSTEM_PROMPT, USER_TEMPLATE = build_prompts(TEMA, GEO_SCOPE)

# =====================================================
# CONFIG
# =====================================================
NUM_CTX = 2048  # límite de tokens del modelo

# =====================================================
# DETECCIÓN DE RED POR NOMBRE DE ARCHIVO
# =====================================================
def detectar_red_por_archivo(path: Path) -> str:
    name = path.name.lower()
    if "reddit" in name: return "reddit"
    if "youtube" in name: return "youtube"
    if "twitter" in name or "x_" in name: return "twitter"
    if "bluesky" in name: return "bluesky"
    return "generic"

# =====================================================
# PREPARAR TEXTO SEGÚN RED
# =====================================================
def preparar_texto(row, red):
    texto = row.get("contenido", "")
    if not texto or pd.isna(texto): return None

    partes = []

    if red == "reddit":
        titulo = row.get("post_title", "")
        cuerpo = row.get("post_selftext", "")
        if titulo or cuerpo:
            partes.append(f"[REDDIT] Título: {titulo} Cuerpo: {cuerpo}")

    elif red == "youtube":
        titulo = row.get("titulo_video", "")
        desc = row.get("descripcion_video", "")
        if titulo or desc:
            partes.append(f"[YOUTUBE] Título: {titulo} Descripción: {desc}")

    elif red == "twitter":
        previo = row.get("BeforeContenido", "")
        if previo:
            partes.append(f"[TWITTER] Tweet previo: {previo}")

    partes.append(f"[COMENTARIO] {texto}")
    return "\n".join(partes)

# =====================================================
# CONTAR TOKENS
# =====================================================
def tokens(texto):
    if not texto or pd.isna(texto):
        return 0
    return len(str(texto)) // 4  # aprox 1 token ≈ 4 caracteres

def contar_tokens_componentes(row):
    titulo = tokens(row.get("post_title", ""))
    cuerpo = tokens(row.get("post_selftext", ""))
    comentario = tokens(row.get("contenido", ""))
    total = titulo + cuerpo + comentario
    return titulo, cuerpo, comentario, total

def contar_tokens_totales(texto):
    """
    Incluye system prompt + user prompt + texto real
    """
    user_filled = USER_TEMPLATE.format(texto=texto)
    total_caracteres = len(SYSTEM_PROMPT) + len(user_filled)
    return total_caracteres // 4

# =====================================================
# ITERAR CSVs Y CALCULAR TOKENS
# =====================================================
def analizar_tokens_csv(folder: Path):
    archivos = list(folder.glob("*_global_dataset.csv"))
    if not archivos:
        print("No se encontraron CSVs en la carpeta.")
        return

    for archivo in archivos:
        print(f"\n=== Analizando {archivo.name} ===")
        with open(archivo, 'r', encoding='utf-8') as f:
            primera_linea = f.readline()
            sep = ';' if ';' in primera_linea else ','

        df = pd.read_csv(archivo, sep=sep, encoding='utf-8', engine='python')
        red = detectar_red_por_archivo(archivo)
        print(f"🔎 Red detectada: {red}")

        tokens_list = []
        tokens_total_list = []
        tokens_titulo_list = []
        tokens_cuerpo_list = []
        tokens_comentario_list = []

        for idx, row in df.iterrows():
            if red == "reddit":
                t, c, com, total = contar_tokens_componentes(row)
                tokens_titulo_list.append(t)
                tokens_cuerpo_list.append(c)
                tokens_comentario_list.append(com)
                texto_final = preparar_texto(row, red)
            else:
                texto_final = preparar_texto(row, red)
                if not texto_final:
                    continue
                total = tokens(texto_final)

            tokens_list.append(total)

            # Contar total incluyendo prompts
            total_con_prompt = contar_tokens_totales(texto_final)
            tokens_total_list.append(total_con_prompt)

            if total_con_prompt > NUM_CTX:
                print(f"⚠️ Fila {idx} supera num_ctx (total tokens ≈ {total_con_prompt})")

        if tokens_list:
            print(f"Total textos procesados: {len(tokens_list)}")
            print(f"Tokens promedio por texto: {sum(tokens_list)/len(tokens_list):.1f}")
            print(f"Tokens máximo por texto: {max(tokens_list)}")
            print(f"Tokens promedio incluyendo prompts: {sum(tokens_total_list)/len(tokens_total_list):.1f}")
            print(f"Tokens máximo incluyendo prompts: {max(tokens_total_list)}")

        if red == "reddit":
            print(f"Tokens promedio título: {sum(tokens_titulo_list)/len(tokens_titulo_list):.1f}")
            print(f"Tokens promedio cuerpo: {sum(tokens_cuerpo_list)/len(tokens_cuerpo_list):.1f}")
            print(f"Tokens promedio comentario: {sum(tokens_comentario_list)/len(tokens_comentario_list):.1f}")
            print(f"Tokens máximo título: {max(tokens_titulo_list)}")
            print(f"Tokens máximo cuerpo: {max(tokens_cuerpo_list)}")
            print(f"Tokens máximo comentario: {max(tokens_comentario_list)}")
        else:
            print("No se procesaron textos en este CSV.")

# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    analizar_tokens_csv(Path("C:\\Users\\DATS004\\Romina.albornoz Dropbox\\Romina Albornoz\\14. DS4M - Social Media Research\\git\\project_web\\Web_Proyecto\\datos\\admin\\prueba_git"))
