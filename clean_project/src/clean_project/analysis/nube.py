import os
from pathlib import Path
import pandas as pd
import re
from collections import Counter
from wordcloud import WordCloud
import nltk
from io import BytesIO
import base64
from nltk.util import ngrams
import unidecode
from deep_translator import GoogleTranslator

# Solo necesitamos el mapeo para saber qué NO es castellano
ES_VARIATIONS = {"castellano", "español", "es", "spanish"}

# ==========================================
# 1. CONFIGURACIÓN NLTK Y STOPWORDS
# ==========================================
NLTK_DATA_PATH = os.path.join(os.getcwd(), "nltk_data")
os.makedirs(NLTK_DATA_PATH, exist_ok=True)
nltk.data.path.append(NLTK_DATA_PATH)

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download("stopwords", download_dir=NLTK_DATA_PATH)

from nltk.corpus import stopwords
STOPWORDS_ES = set(stopwords.words("spanish"))

def limpiar_texto(texto):
    if not isinstance(texto, str): return ""
    texto = texto.lower()
    texto = re.sub(r"http\S+|www\S+", "", texto)
    texto = unidecode.unidecode(texto) # Normaliza acentos (publico = público)
    texto = re.sub(r"[^a-z\s]", "", texto)
    return texto.strip()

def obtener_stopwords_unificadas(df):
    """
    Carga stopwords de castellano + ruido social + keywords del proyecto.
    """
    stops = STOPWORDS_ES.copy()
    ruido_social = {
        "si", "no", "así", "hacer", "ver", "ir", "tan", "cada", "bien", "solo", "hace",
        "donde", "comentario", "video", "youtube", "twitter", "reddit", "bluesky",
        "hola", "gracias", "muchas", "felicidades", "bueno", "todo", "toda", "pero"
    }
    stops.update(ruido_social)
    
    if "KEYWORD" in df.columns:
        for kw_item in df["KEYWORD"].dropna().unique():
            stops.update(limpiar_texto(str(kw_item)).split())
    return stops

# ==========================================
# 2. PROCESAMIENTO CON TRADUCCIÓN
# ==========================================
def procesar_datos_para_nube_unificada(df_subset):
    word_counts = Counter()
    word_sentiments = {}
    stops = obtener_stopwords_unificadas(df_subset)
    
    # Configuramos traductor (Auto-detección -> Castellano)
    translator = GoogleTranslator(source='auto', target='es')

    print(f"🔄 Procesando y traduciendo {len(df_subset)} menciones...")

    for _, row in df_subset.iterrows():
        contenido_raw = str(row.get("CONTENIDO", ""))
        if len(contenido_raw) < 10: continue 

        idioma_ia = str(row.get("IDIOMA_IA", "es")).lower().strip()
        
        # --- TRADUCCIÓN AUTOMÁTICA SI NO ES CASTELLANO ---
        if idioma_ia not in ES_VARIATIONS:
            try:
                # Traducimos para unificar semánticamente (ej: Herria -> Pueblo)
                texto_final = translator.translate(contenido_raw)
            except:
                texto_final = contenido_raw # Fallback al original si falla internet
        else:
            texto_final = contenido_raw

        texto_limpio = limpiar_texto(texto_final)
        if not texto_limpio: continue
        
        score = pd.to_numeric(row.get("SENTIMIENTO", 0), errors='coerce')
        if pd.isna(score): score = 0

        # Tokenizar palabras de más de 3 letras
        tokens = [t for t in texto_limpio.split() if len(t) > 3 and t not in stops]
        if not tokens: continue

        # 1. Unigramas (Peso 1)
        for t in tokens:
            word_counts[t] += 1
            word_sentiments.setdefault(t, []).append(score)

        # 2. Bigramas (Peso 4 para resaltar conceptos compuestos)
        if len(tokens) >= 2:
            for ng in ngrams(tokens, 2):
                frase = " ".join(ng)
                word_counts[frase] += 4 
                for _ in range(4):
                    word_sentiments.setdefault(frase, []).append(score)

    # Filtrado de calidad
    min_apariciones = 3 if len(df_subset) > 20 else 2
    final_counts = {k: v for k, v in word_counts.items() if v >= min_apariciones}
    
    if not final_counts: final_counts = word_counts

    final_sentiments = {w: (sum(scores)/len(scores)) for w, scores in word_sentiments.items() if w in final_counts}

    return final_counts, final_sentiments

# ==========================================
# 3. GENERACIÓN DE IMAGEN Y DASHBOARD
# ==========================================
def generar_imagen_base64(counts, sentiments):
    if not counts: return None

    def color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        score = sentiments.get(word, 0)
        if score > 0.1: return "rgb(20, 160, 20)"   # Verde
        elif score < -0.1: return "rgb(220, 20, 20)" # Rojo
        else: return "rgb(100, 100, 100)"           # Gris

    try:
        wc = WordCloud(
            width=1000, height=600,
            background_color="white",
            max_words=50,
            color_func=color_func,
            collocations=False,
            prefer_horizontal=0.8,
            relative_scaling=0.5
        ).generate_from_frequencies(counts)

        buffer = BytesIO()
        wc.to_image().save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except: return None

def generar_nubes_dashboard(csv_path, target_languages=None):
    """
    Genera nubes unificadas en castellano.
    """
    resultados = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            sep = ';' if ';' in f.readline() else ','
        df = pd.read_csv(csv_path, sep=sep, encoding="utf-8", engine='python')
        df.columns = [c.upper() for c in df.columns] 

        if "CONTENIDO" not in df.columns: return {}
        
        # Filtro de relevancia (quitar sentimiento 2)
        if "SENTIMIENTO" in df.columns:
            df = df[df["SENTIMIENTO"].astype(str) != "2"]

        # 1. NUBE GLOBAL (Todo traducido a ES)
        c, s = procesar_datos_para_nube_unificada(df)
        resultados["nube_global"] = generar_imagen_base64(c, s)

        # 2. NUBES POR RED SOCIAL (Todo traducido a ES)
        if "FUENTE" in df.columns:
            for red in df["FUENTE"].dropna().unique():
                df_red = df[df["FUENTE"] == red]
                c, s = procesar_datos_para_nube_unificada(df_red)
                red_clean = str(red).lower().replace(" ", "")
                resultados[f"nube_{red_clean}"] = generar_imagen_base64(c, s)

    except Exception as e:
        print(f"❌ Error en motor de nubes: {e}")
    
    return resultados