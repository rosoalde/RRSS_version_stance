import pandas as pd
import json
import hashlib
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================
BASE_PATH = Path(".")  # carpeta actual
OUTPUT_DIR = BASE_PATH

# ============================================================
# HELPER: TEXTO UNIFICADO
# ============================================================
def preparar_texto_unificado(row, red):

    if red == "reddit":
        titulo = str(row.get("post_title", "")).strip()
        cuerpo = str(row.get("post_selftext", "")).strip()
    elif red == "youtube":
        titulo = str(row.get("titulo_video", "")).strip()
        cuerpo = str(row.get("descripcion_video", "")).strip()
    elif red == "twitter":
        titulo = str(row.get("BeforeContenido", "")).strip()
        cuerpo = ""
    else:
        titulo = ""
        cuerpo = ""

    if titulo.lower() == "nan": titulo = ""
    if cuerpo.lower() == "nan": cuerpo = ""

    contenido = str(row.get("contenido", "")).strip()
    if contenido.lower() == "nan": contenido = ""

    keyword = str(row.get("search_keyword", "")).strip()
    language = str(row.get("keyword_languages", "")).strip()

    return titulo, cuerpo, contenido, keyword, language

# ============================================================
# ESTANDARIZADOR
# ============================================================
def estandarizar_para_excel_simple(df, red):

    nuevo_df = pd.DataFrame()

    # ID
    col_user = 'usuario_comentario' if red == 'youtube' else 'usuario'
    if col_user in df.columns:
        nuevo_df['ID'] = df[col_user].astype(str).fillna('unknown').apply(
            lambda x: hashlib.sha256(x.encode()).hexdigest()[:16].upper()
        )
    else:
        nuevo_df['ID'] = 'UNKNOWN'

    # FECHA
    col_date = 'fecha_comentario' if red == 'youtube' else 'fecha'
    fechas_list = []

    if col_date in df.columns:
        raw_dates = df[col_date]

        if raw_dates.dtype == "object":
            raw_dates = (
                raw_dates
                    .str.replace("·", "", regex=False)
                    .str.replace("UTC", "", regex=False)
                    .str.strip()
            )

        print("Ejemplos de fechas crudas:")
        print(raw_dates.head(10))
        sample = raw_dates.dropna().iloc[0]

        if "T" in sample and "-" in sample:
            fechas_dt = pd.to_datetime(raw_dates, format="ISO8601", errors="coerce", utc=True)
        elif "," in sample and "AM" in sample or "PM" in sample:
            raw_dates = raw_dates.str.replace(r"\s{2,}", " ", regex=True).str.strip()
            fechas_dt = pd.to_datetime(raw_dates, format="%b %d, %Y %I:%M %p", errors="coerce")
        else:
            fechas_dt = pd.to_datetime(raw_dates, errors="coerce")

        for dt in fechas_dt:
            if pd.notna(dt):
                fechas_list.append(dt.strftime('%Y-%m-%d'))
            else:
                fechas_list.append("")
    else:
        fechas_list = [""] * len(df)

    nuevo_df['FECHA'] = fechas_list

    # TEXTO
    titulos, cuerpos, contenidos, keywords, languages = [], [], [], [], []

    for _, row in df.iterrows():
        t, c, cont, k, l = preparar_texto_unificado(row, red)
        titulos.append(t)
        cuerpos.append(c)
        contenidos.append(cont)
        keywords.append(k)
        languages.append(l)

    nuevo_df['TITULO'] = titulos
    nuevo_df['CUERPO'] = cuerpos
    nuevo_df['CONTENIDO'] = contenidos
    nuevo_df['KEYWORD'] = keywords
    nuevo_df['LANGUAGE'] = languages

    # FUENTE
    def normalizar_red(r):
        r = str(r).lower()
        if 'twitter' in r or r == 'x': return 'X (Twitter)'
        if 'youtube' in r: return 'Youtube'
        if 'reddit' in r: return 'Reddit'
        if 'bluesky' in r: return 'BlueSky'
        return r.capitalize()

    nuevo_df['FUENTE'] = normalizar_red(red)

    # SENTIMIENTO
    posibles_s = ['sentimiento_1', 'Sentimiento', 'sentimiento', 'SENTIMIENTO', 'score', 'sentiment']
    col_s = next((c for c in df.columns if c in posibles_s or c.lower() in posibles_s), None)

    if col_s:
        nuevo_df['SENTIMIENTO'] = pd.to_numeric(df[col_s], errors='coerce').fillna(2)
    else:
        nuevo_df['SENTIMIENTO'] = 2

        # TOPIC
    posibles_t = ['topic', 'Topic', 'TOPIC', 'topics', 'Topics', 'TOPICS']
    col_t = next((c for c in df.columns if c in posibles_t or c.lower() in posibles_t), None)

    if col_t:
        nuevo_df['TOPIC'] = df[col_t].astype(str).fillna("").str.strip()
    else:
        nuevo_df['TOPIC'] = ""

    if "IDIOMA_IA" in df.columns:
        nuevo_df['IDIOMA_IA'] = df['IDIOMA_IA'].fillna("Desconocido")
    else:
        nuevo_df['IDIOMA_IA'] = "Desconocido"
        
    # FILTRAR sentimiento 2
    nuevo_df = nuevo_df[nuevo_df['SENTIMIENTO'] != 2].copy()

    return nuevo_df


# ============================================================
# DASHBOARD BASE
# ============================================================
def calcular_dashboard_base(df):

    df = df.copy()

    df["SENTIMIENTO"] = pd.to_numeric(df["SENTIMIENTO"], errors="coerce").fillna(0).astype(int)

    map_sent = {-1: "Negativo", 0: "Neutro", 1: "Positivo"}
    df["sent_label"] = df["SENTIMIENTO"].map(map_sent)

    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA"])
    df["FECHA"] = df["FECHA"].dt.strftime("%Y-%m-%d")

    kpis = {
        "total": len(df),
        "positivos": (df["SENTIMIENTO"] == 1).sum(),
        "neutros": (df["SENTIMIENTO"] == 0).sum(),
        "negativos": (df["SENTIMIENTO"] == -1).sum(),
    }

    tendencia_global = df.groupby("FECHA").size().to_dict()

    tendencia_sentimiento = (
        df.groupby(["FECHA", "sent_label"])
          .size()
          .unstack(fill_value=0)
          .to_dict(orient="index")
    )

    volumen_por_red = df["FUENTE"].value_counts().to_dict()

    tendencia_por_red = {}

        # ============================================================
    # TOPICS CON VOLUMEN Y SENTIMIENTO PROMEDIO
    # ============================================================

    df_topics = df.copy()

    # eliminar vacíos
    df_topics = df_topics[df_topics["TOPIC"].astype(str).str.strip() != ""]

    topics_grouped = (
        df_topics
        .groupby("TOPIC")
        .agg(
            volumen=("TOPIC", "count"),
            sentimiento_prom=("SENTIMIENTO", "mean")
        )
        .reset_index()
        .sort_values(by="volumen", ascending=False)
        .head(15)
    )

    topics_list = []

    for _, row in topics_grouped.iterrows():
        topics_list.append({
            "TOPIC": row["TOPIC"],
            "volumen": int(row["volumen"]),
            "sentimiento_prom": float(round(row["sentimiento_prom"], 2))
        })


    for red in df["FUENTE"].unique():
        df_red = df[df["FUENTE"] == red]

        tendencia_por_red[red] = {
            "total": df_red.groupby("FECHA").size().to_dict(),
            "sentimiento": (
                df_red.groupby(["FECHA", "sent_label"])
                      .size()
                      .unstack(fill_value=0)
                      .to_dict(orient="index")
            )
        }

    return {
        "kpis": kpis,
        "tendencia_global": tendencia_global,
        "tendencia_sentimiento": tendencia_sentimiento,
        "volumen_por_red": volumen_por_red,
        "tendencia_por_red": tendencia_por_red,
        "topics": topics_list
    }


# ============================================================
# MAIN
# ============================================================
def main():

    print("📂 Buscando *_analizado.csv...")

    archivos = list(BASE_PATH.glob("*_analizado.csv"))

    if not archivos:
        print("❌ No se encontraron archivos")
        return

    lista_dfs = []

    for archivo in archivos:
        print(f"📂 Procesando {archivo.name}")
        try:
            df = pd.read_csv(archivo, sep=None, engine="python", encoding="utf-8")
        except:
            df = pd.read_csv(archivo, sep=";", engine="python", encoding="latin1")


        red = archivo.name.split("_")[0].lower()

        df_std = estandarizar_para_excel_simple(df, red)

        if not df_std.empty:
            lista_dfs.append(df_std)

    if not lista_dfs:
        print("❌ No hay datos válidos")
        return

    df_final = pd.concat(lista_dfs, ignore_index=True)

    # Guardar Excel
    df_final.to_excel("reporte_analisis.xlsx", index=False)

    # Guardar CSV filtrado
    df_final.to_csv("datos_sentimiento_filtrados.csv", index=False, encoding="utf-8")

    # Generar dashboard
    dashboard_data = calcular_dashboard_base(df_final)

    def convertir_numpy(obj):
        if isinstance(obj, dict):
            return {k: convertir_numpy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convertir_numpy(v) for v in obj]
        elif hasattr(obj, "item"):  # numpy types
            return obj.item()
        else:
            return obj

    dashboard_data = convertir_numpy(dashboard_data)

    with open("dashboard_data.json", "w", encoding="utf-8") as f:
        json.dump(dashboard_data, f, indent=2, ensure_ascii=False)


    print("✅ Reporte regenerado correctamente")


if __name__ == "__main__":
    main()
