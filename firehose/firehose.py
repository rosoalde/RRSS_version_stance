# -----------------------------
# IMPORTS
# -----------------------------
import asyncio
import websockets
import json
import praw
from mastodon import Mastodon, StreamListener, MastodonMalformedEventError
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import threading
import time
import sqlite3
from langdetect import detect, DetectorFactory, LangDetectException
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import re
import pandas as pd
import os

# Para que los resultados sean consistentes
DetectorFactory.seed = 0

# -----------------------------
# DATABASE CONNECTION
# -----------------------------
conn = sqlite3.connect("social_stream.db", check_same_thread=False)
cur = conn.cursor()
lock = threading.Lock()

# Crear tabla principal si no existe
cur.execute("""
CREATE TABLE IF NOT EXISTS social_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT,
    author TEXT,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# Columnas extra
columns_to_add = {
    "post_title": "TEXT",
    "post_body": "TEXT",
    "reddit_subreddit": "TEXT",
    "reddit_comment_id": "TEXT",
    "comment_score": "INTEGER",
    "post_id": "TEXT",
    "lang": "TEXT",
    "latitude": "REAL",
    "longitude": "REAL",
    "city": "TEXT",
    "country": "TEXT",
    "region": "TEXT",
    "location_text": "TEXT",
    "author_flair": "TEXT"
}

for col, col_type in columns_to_add.items():
    try:
        cur.execute(f"ALTER TABLE social_messages ADD COLUMN {col} {col_type}")
    except sqlite3.OperationalError:
        pass
conn.commit()

# -----------------------------
# SAVE MESSAGE FUNCTION
# -----------------------------
def save_message(
    platform, author, content,
    post_title=None, post_body=None,
    reddit_subreddit=None, reddit_comment_id=None,
    comment_score=None, post_id=None, lang=None,
    latitude=None, longitude=None, city=None, country=None, region=None,
    location_text=None, author_flair=None
):
    with lock:
        cur.execute("""
        INSERT INTO social_messages (
            platform, author, content,
            post_title, post_body, reddit_subreddit,
            reddit_comment_id, comment_score, post_id, lang,
            latitude, longitude, city, country, region,
            location_text, author_flair
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            platform, author, content,
            post_title, post_body, reddit_subreddit,
            reddit_comment_id, comment_score, post_id, lang,
            latitude, longitude, city, country, region,
            location_text, author_flair
        ))
        conn.commit()
        print(f"[{platform}] {author}: {content[:100]}...")

# -----------------------------
# GEOCODING
# -----------------------------
geolocator = Nominatim(user_agent="social_geo_pipeline")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

# Cargar base de datos local de municipios/comunidades de España
# Debe ser un CSV con columnas: name, type (municipio/provincia/comunidad), region, country
if os.path.exists("espana_places.csv"):
    df_places = pd.read_csv("espana_places.csv")
else:
    df_places = pd.DataFrame(columns=["name", "type", "region", "country"])

def get_geo_from_text(text):
    """Intenta detectar ciudad/comunidad/provincia de España"""
    if df_places.empty:
        return None, None, None, None, None
    text_lower = text.lower()
    match = df_places[df_places["name"].str.lower().apply(lambda x: x in text_lower)]
    if not match.empty:
        place = match.iloc[0]
        loc = geocode(place["name"])
        if loc:
            return loc.latitude, loc.longitude, place["name"], place["region"], place["country"]
    return None, None, None, None, None

def get_geo_from_location(location_text):
    if not location_text:
        return None, None, None, None, None
    loc = geocode(location_text)
    if loc:
        address = loc.raw.get("address", {})
        return loc.latitude, loc.longitude, address.get("city"), address.get("state"), address.get("country")
    return None, None, None, None, None

# -----------------------------
# BLUESKY STREAM
# -----------------------------
async def bluesky_stream():
    url = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"
    while True:
        try:
            async with websockets.connect(url) as ws:
                print("Connected to Bluesky")
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    commit = data.get("commit", {})
                    record = commit.get("record")
                    if record and "text" in record:
                        text = record["text"]
                        author = data.get("did", "unknown")
                        langs = record.get("langs", [])
                        target_langs = ["es", "ca", "gl", "eu", "fr", "pt", "it"]

                        # Prioridad: location_text > texto
                        location_text = record.get("location")
                        lat, lon, city, region, country = get_geo_from_location(location_text)
                        if not lat:
                            lat, lon, city, region, country = get_geo_from_text(text)

                        if any(lang in langs for lang in target_langs):
                            save_message(
                                platform="bluesky",
                                author=author,
                                content=text,
                                lang=", ".join([l for l in langs if l in target_langs]),
                                latitude=lat,
                                longitude=lon,
                                city=city,
                                region=region,
                                country=country,
                                location_text=location_text
                            )
        except Exception as e:
            print("Bluesky reconnecting:", e)
            await asyncio.sleep(5)

# -----------------------------
# REDDIT STREAM
# -----------------------------
def reddit_stream():
    reddit = praw.Reddit(
        client_id="TXr9FuPxqBWzt5Se6B7O4w",
        client_secret="FDLxAYCobON7T1yadE-Ip52qtHJRBA",
        user_agent="social_stream_research_bot v1.0"
    )
    print("Connected to Reddit")
    target_langs = ["es", "ca", "gl", "eu", "fr", "pt", "it"]
    for comment in reddit.subreddit("all").stream.comments(skip_existing=True):
        try:
            text = comment.body
            try:
                lang = detect(text)
            except LangDetectException:
                lang = None

            author_flair = comment.author_flair_text
            subreddit_name = str(comment.subreddit)

            # Geo: primero autor_flair, luego subreddit, luego texto
            lat, lon, city, region, country = get_geo_from_location(author_flair)
            if not lat:
                lat, lon, city, region, country = get_geo_from_location(subreddit_name)
            if not lat:
                lat, lon, city, region, country = get_geo_from_text(text)

            if lang in target_langs:
                submission = comment.submission
                save_message(
                    platform="reddit",
                    author=str(comment.author),
                    content=text,
                    post_title=submission.title,
                    post_body=submission.selftext,
                    reddit_subreddit=subreddit_name,
                    reddit_comment_id=comment.id,
                    comment_score=comment.score,
                    post_id=submission.id,
                    lang=lang,
                    latitude=lat,
                    longitude=lon,
                    city=city,
                    region=region,
                    country=country,
                    author_flair=author_flair
                )
        except Exception as e:
            print("Reddit stream error:", e)

# -----------------------------
# MASTODON STREAM
# -----------------------------
class Listener(StreamListener):
    def on_update(self, status):
        try:
            content = status.get("content") if isinstance(status, dict) else None
            if content:
                content = re.sub("<.*?>", "", content)
                account = status.get("account", {}) if isinstance(status, dict) else {}
                author = account.get("username", "unknown")
                location_text = account.get("location")
                lat, lon, city, region, country = get_geo_from_location(location_text)
                if not lat:
                    lat, lon, city, region, country = get_geo_from_text(content)
                save_message("mastodon", author, content,
                             latitude=lat, longitude=lon, city=city,
                             region=region, country=country, location_text=location_text)
        except Exception as e:
            print("Mastodon parse error:", e)

    def on_notification(self, notification): pass
    def on_delete(self, status_id): pass
    def on_unknown_event(self, name, content): pass
    def on_abort(self, err): print("Stream abort:", err)

def mastodon_stream():
    mastodon = Mastodon(
        access_token="iLzW0jLj35210PxMFuKl9Rpb_4KyJYjpPfSiji4XhTE",
        api_base_url="https://mastodon.social"
    )
    print("Connected to Mastodon")
    while True:
        try:
            mastodon.stream_public(Listener(), timeout=None)
        except MastodonMalformedEventError as e:
            print("MastodonMalformedEventError ignored:", e)
        except Exception as e:
            print("Mastodon reconnecting due to:", e)
            time.sleep(5)

# -----------------------------
# TOPIC DETECTION
# -----------------------------
def detect_topics():
    while True:
        time.sleep(300)
        cur.execute("SELECT content FROM social_messages ORDER BY created_at DESC LIMIT 1000")
        texts = [r[0] for r in cur.fetchall()]
        if len(texts) < 50: continue
        vectorizer = TfidfVectorizer(stop_words="english")
        X = vectorizer.fit_transform(texts)
        kmeans = KMeans(n_clusters=5)
        kmeans.fit(X)
        terms = vectorizer.get_feature_names_out()
        print("\nEmerging topics:\n")
        for i, center in enumerate(kmeans.cluster_centers_):
            top_terms = center.argsort()[-10:]
            topic_words = [terms[t] for t in top_terms]
            print(f"Topic {i+1}:", ", ".join(topic_words))

# -----------------------------
# RUN EVERYTHING
# -----------------------------
def start_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bluesky_stream())

loop = asyncio.new_event_loop()
threads = [
    threading.Thread(target=start_async_loop, args=(loop,)),
    threading.Thread(target=reddit_stream),
    # threading.Thread(target=mastodon_stream),
    threading.Thread(target=detect_topics)
]

for t in threads: t.start()
for t in threads: t.join()        