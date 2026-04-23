import streamlit as st
import sqlite3
import pandas as pd
import os
import re
import nltk
from langdetect import detect, LangDetectException
import altair as alt
import subprocess

# ========================
# CONFIGURACIÓN STREAMLIT
# ========================
st.set_page_config(layout="wide")
st.title("📡 Social Media Firehose Dashboard (Multilang con Ollama)")

# ========================
# DATABASE
# ========================
conn = sqlite3.connect("social_stream.db")

@st.cache_data(ttl=10)
def load_data():
    query = """
    SELECT id, platform, author, content, post_title, post_body, reddit_subreddit,
           reddit_comment_id, comment_score, post_id, lang, created_at, latitude, longitude, city, country, region
    FROM social_messages
    ORDER BY created_at DESC
    LIMIT 5000
    """
    df = pd.read_sql_query(query, conn)
    df["created_at"] = pd.to_datetime(df["created_at"])
    return df

df = load_data()

# ========================
# SELECCIÓN DE IDIOMA
# ========================
target_langs = {
    "es": "Español",
    "ca": "Catalán",
    "gl": "Gallego",
    "eu": "Euskera",
    "fr": "Francés",
    "pt": "Portugués",
    "it": "Italiano",
    "en": "Inglés"
}

selected_lang = st.sidebar.selectbox("Filtrar por idioma:", ["Todos"] + list(target_langs.values()))

if selected_lang != "Todos":
    lang_code = [k for k, v in target_langs.items() if v == selected_lang][0]
    df_lang = df[df['lang'].str.contains(lang_code, na=False)]
else:
    lang_code = None
    df_lang = df

# ========================
# VOLUME BY PLATFORM
# ========================
st.subheader("📊 Volumen por plataforma")
platform_counts = df_lang["platform"].value_counts().reset_index()
platform_counts.columns = ["platform", "count"]

chart = alt.Chart(platform_counts).mark_bar().encode(
    x='platform',
    y='count',
    color='platform',
    tooltip=['platform', 'count']
)
st.altair_chart(chart, use_container_width=True)
# ========================
# POSTS PER MINUTE
# ========================
st.subheader("⏱ Posts por minuto")
df_lang["minute"] = df_lang["created_at"].dt.floor("min")
posts_per_minute = df_lang.groupby("minute").size().reset_index(name='count')

line = alt.Chart(posts_per_minute).mark_line(point=True).encode(
    x='minute',
    y='count',
    tooltip=['minute', 'count']
)
st.altair_chart(line, use_container_width=True)

# ========================
# STOPWORDS
# ========================
nltk_data_path = r"./nltk_data"
os.makedirs(nltk_data_path, exist_ok=True)
nltk.data.path.append(nltk_data_path)
nltk.download('stopwords', download_dir=nltk_data_path)
from nltk.corpus import stopwords

stopwords_dir = r"./stopwords"

def cargar_stopwords_externas(carpeta):
    stops = set()
    if not os.path.isdir(carpeta):
        return stops
    for fname in os.listdir(carpeta):
        if fname.endswith(".txt"):
            with open(os.path.join(carpeta, fname), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip().lower()
                    if line:
                        stops.add(line)
    return stops

STOPWORDS_DICT = {
    "es": set(stopwords.words("spanish")) | cargar_stopwords_externas(os.path.join(stopwords_dir, "spanish")),
    "en": set(stopwords.words("english")) | cargar_stopwords_externas(os.path.join(stopwords_dir, "english")),
    "fr": set(stopwords.words("french"))  | cargar_stopwords_externas(os.path.join(stopwords_dir, "french")),
    "it": set(stopwords.words("italian")) | cargar_stopwords_externas(os.path.join(stopwords_dir, "italian")),
    "pt": set(stopwords.words("portuguese")) | cargar_stopwords_externas(os.path.join(stopwords_dir, "portuguese")),
    "ca": cargar_stopwords_externas(os.path.join(stopwords_dir, "catalan")),
    "eu": cargar_stopwords_externas(os.path.join(stopwords_dir, "basque")),
    "gl": cargar_stopwords_externas(os.path.join(stopwords_dir, "galician"))
}

# ========================
# FUNCIONES DE LIMPIEZA
# ========================
def clean_text(text):
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ\s]", "", text)
    text = text.replace("None", "")
    return text.strip().lower()

# ========================
# FUNCIONES DE TOPICS CON OLLAMA
# ========================
import subprocess
import math

def chunk_texts(texts, max_per_chunk=50):
    """Divide la lista de textos en chunks de tamaño máximo max_per_chunk"""
    return [texts[i:i + max_per_chunk] for i in range(0, len(texts), max_per_chunk)]

import ollama

def etiquetar_topics_ollama(texts, lang_name, model="qwen2.5:1.5b", max_per_chunk=50):
    """
    Etiqueta automáticamente los topics usando Ollama Python SDK.
    Devuelve un string con los topics detectados.
    """
    if not texts:
        return "No hay textos suficientes para analizar."
    
    # Dividir en chunks para no saturar el prompt
    resultados = []
    for i in range(0, len(texts), max_per_chunk):
        chunk = texts[i:i + max_per_chunk]
        prompt = f"""
Analiza estos {len(chunk)} textos en {lang_name} y devuelve:
1) Hasta 5 temas principales como etiquetas cortas (una o dos palabras).
2) Breve descripción de cada tema.

Textos:
{" ||| ".join(chunk)}
"""
        try:
            res = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            resultados.append(res['message']['content'])
        except Exception as e:
            resultados.append(f"Error al procesar chunk: {e}")

    # Combinar todos los resultados
    return "\n\n".join(resultados)


# ========================
# Temas emergentes con Ollama
# ========================
st.subheader("🔥 Temas emergentes (LLM etiquetado con Ollama)")

for lang, lang_name in target_langs.items():
    if lang not in STOPWORDS_DICT:
        continue

    # Filtrar posts en este idioma y no vacíos
    df_sub = df[df['lang'].str.contains(lang, na=False) & df['content'].notna()]
    if df_sub.empty:
        continue

    texts_cleaned = []
    stops = STOPWORDS_DICT[lang]
    EXTRA_STOPWORDS = {"bskysocial", "pls", "lol", "hello", "hi", "yes", "no"}

    for _, row in df_sub.iterrows():
        text = str(row.get("content", "")).strip()
        if not text:
            continue
        try:
            detected_lang = detect(text)
        except LangDetectException:
            continue
        if detected_lang != lang:
            continue
        t_clean = clean_text(text)
        tokens = [w for w in t_clean.split() if w not in stops and w not in EXTRA_STOPWORDS and len(w) > 2 and w.lower() != "none"]
        if tokens:
            texts_cleaned.append(" ".join(tokens))

    if len(texts_cleaned) < 10:
        continue

    # Etiquetado de topics usando Ollama
    topics_text = etiquetar_topics_ollama(texts_cleaned, lang_name)
    st.write(f"### 🔥 Temas emergentes ({lang_name})")
    st.text(topics_text)

# ========================
# LIVE FEED
# ========================
st.subheader("🧵 Live Feed (últimos 50 posts)")
columns_order = [
    "created_at", "platform", "lang", "author",
    "reddit_subreddit", "reddit_comment_id", "post_id",
    "post_title", "post_body", "content", "comment_score", 
    "latitude", "longitude", "city", "country", "region"
]
st.dataframe(
    df_lang[columns_order]
           .sort_values(by="created_at", ascending=False)
           .head(50),
    width='stretch'
)
#streamlit run dashboard.py