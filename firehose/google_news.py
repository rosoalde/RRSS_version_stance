import time
import random
import pandas as pd
from GoogleNews import GoogleNews
from newspaper import Article
from langdetect import detect, DetectorFactory
from sentence_transformers import SentenceTransformer
import hdbscan
from sklearn.preprocessing import StandardScaler
import sqlite3

DetectorFactory.seed = 0

# -----------------------------
# DATABASE
# -----------------------------
conn = sqlite3.connect("news_dataset.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT,
    title TEXT,
    desc TEXT,
    link TEXT UNIQUE,
    date TIMESTAMP,
    lang TEXT
)
""")
conn.commit()

# -----------------------------
# Helper functions
# -----------------------------

def scrape_article(url):
    """Extrae título y texto de un artículo con Newspaper3k."""
    for attempt in range(5):
        try:
            art = Article(url)
            art.download()
            art.parse()
            return art.title, art.text
        except Exception as e:
            wait = 2 ** attempt + random.random()
            print(f"⚠️ Error scraping {url}, retrying in {wait:.1f}s: {e}")
            time.sleep(wait)
    return None, None

def save_article(keyword, title, desc, link, date, lang):
    """Guarda noticia en SQLite evitando duplicados"""
    try:
        cur.execute("""
        INSERT OR IGNORE INTO news (keyword, title, desc, link, date, lang)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (keyword, title, desc, link, date, lang))
        conn.commit()
    except Exception as e:
        print("⚠️ Error guardando en DB:", e)

# -----------------------------
# Scraping + Query Expansion
# -----------------------------

def iterative_scrape(keywords, max_articles=5000, window_days=365, step_days=7):
    """Scraping retroactivo evitando duplicados en DB"""
    
    # Leer links ya guardados
    cur.execute("SELECT link FROM news")
    scraped_links = set([row[0] for row in cur.fetchall()])
    
    all_data = []
    googlenews = GoogleNews(lang='es', region='US')
    
    for kw in keywords:
        print(f"\n🔎 Scraping keyword: {kw}")
        days_left = window_days
        
        while days_left > 0 and sum(len(df) for df in all_data) < max_articles:
            start_date = (pd.Timestamp.today() - pd.Timedelta(days=days_left)).strftime("%m/%d/%Y")
            end_date = (pd.Timestamp.today() - pd.Timedelta(days=days_left - step_days)).strftime("%m/%d/%Y")
            
            try:
                googlenews.clear()
                googlenews.set_time_range(start_date, end_date)
                googlenews.search(kw)
                time.sleep(random.uniform(5, 10))  # pausa para evitar 429
                results = googlenews.results()
                df_fake = pd.DataFrame(results)
                if df_fake.empty or 'link' not in df_fake.columns:
                    days_left -= step_days
                    continue

                # Evitar duplicados
                df_fake = df_fake[~df_fake['link'].isin(scraped_links)]
                scraped_links.update(df_fake['link'].tolist())

                # Detectar idioma
                langs = []
                for t in df_fake['desc']:
                    try: langs.append(detect(t))
                    except: langs.append(None)
                df_fake['lang'] = langs
                df_fake['keyword'] = kw

                # Guardar progresivamente en DB
                for _, row in df_fake.iterrows():
                    save_article(row['keyword'], row['title'], row['desc'], row['link'], row['date'], row['lang'])

                all_data.append(df_fake)

                # Query expansion: nuevas palabras de los títulos
                new_keywords = list(set(" ".join(df_fake['title']).split()))
                for nk in new_keywords:
                    if nk.lower() not in [k.lower() for k in keywords]:
                        keywords.append(nk)

                days_left -= step_days
                time.sleep(random.uniform(1, 3))

            except Exception as e:
                wait = random.uniform(10, 30)
                print(f"⚠️ Error scraping {kw} ({start_date} → {end_date}), esperando {wait:.1f}s: {e}")
                time.sleep(wait)

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    else:
        return pd.DataFrame()# -----------------------------
# Embeddings + Clustering + First Story Detection
# -----------------------------

def fsd_topic_detection(df, min_cluster_size=5):
    """Transforma títulos y descripciones en embeddings, clusteriza y detecta first story"""
    model = SentenceTransformer('all-MiniLM-L6-v2')

    texts = (df['title'] + ". " + df['desc']).fillna("").tolist()
    embeddings = model.encode(texts, show_progress_bar=True)

    # Escalar para HDBSCAN
    scaler = StandardScaler()
    embeddings_scaled = scaler.fit_transform(embeddings)

    # Clustering HDBSCAN
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size)
    cluster_labels = clusterer.fit_predict(embeddings_scaled)
    df['topic'] = cluster_labels

    # First Story Detection: tomar la noticia más antigua de cada cluster
    fsd_rows = []
    for t in set(cluster_labels):
        if t == -1:
            continue
        cluster_df = df[df['topic']==t]
        first_story = cluster_df.sort_values('date').iloc[0]
        fsd_rows.append(first_story)
    df_fsd = pd.DataFrame(fsd_rows)
    return df, df_fsd

# -----------------------------
# EJEMPLO DE USO
# -----------------------------
initial_keywords = ["baliza V16"]
df_dataset = iterative_scrape(initial_keywords, max_articles=500)
print(f"\n✅ Dataset final: {len(df_dataset)} noticias")

# Después del scraping
if df_dataset.empty:
    print("⚠️ No hay noticias para procesar, revisa el scraping o el período de búsqueda")
    df_clustered = pd.DataFrame()
    df_fsd = pd.DataFrame()
else:
    df_clustered, df_fsd = fsd_topic_detection(df_dataset)
    print("📌 First Stories por tópico:")
    print(df_fsd[['topic','date','title','link']])
print("\n📌 First Stories por tópico:")
print(df_fsd[['topic','date','title','link']])