# import requests
# from bs4 import BeautifulSoup
# import re

# # URL base de Google News
# url = "https://news.google.com"

# # Obtenemos la página principal
# html = requests.get(url).text
# soup = BeautifulSoup(html, "html.parser")

# # Buscamos todos los enlaces que contengan 'hl=' y 'gl='
# links = soup.find_all("a", href=True)

# ediciones = set()
# for link in links:
#     href = link['href']
#     if "hl=" in href and "gl=" in href:
#         ediciones.add(href)

# # Extraemos región e idioma
# regiones = set()
# idiomas = set()
# for e in ediciones:
#     lang_match = re.search(r"hl=([a-z-]+)", e)
#     region_match = re.search(r"gl=([A-Z]+)", e)
#     if lang_match:
#         idiomas.add(lang_match.group(1))
#     if region_match:
#         regiones.add(region_match.group(1))

# print("Idiomas disponibles:", sorted(idiomas))
# print("Regiones disponibles:", sorted(regiones))


from pytrends.request import TrendReq
import pandas as pd
import time
import random

# conexión a Google Trends
pytrends = TrendReq(
    hl='es-ES',
    tz=360,
    retries=3,
    backoff_factor=2
)

# términos a buscar
keywords = [
    "baliza V16",
    "triángulos emergencia coche",
    "luz emergencia coche"
]

# rango temporal
timeframe = "2018-01-01 2018-12-31"

results = []

for kw in keywords:

    success = False

    while not success:
        try:

            print(f"Consultando: {kw}")

            pytrends.build_payload(
                [kw],
                cat=0,
                timeframe=timeframe,
                geo='ES',
                gprop=''
            )

            data = pytrends.interest_over_time()

            if not data.empty:
                data = data.drop(columns=['isPartial'])
                data["keyword"] = kw
                results.append(data)

            success = True

            # pausa aleatoria para evitar bloqueos
            sleep_time = random.uniform(8,15)
            print(f"Esperando {sleep_time:.1f} segundos...")
            time.sleep(sleep_time)

        except Exception as e:

            print("Error detectado:", e)
            wait = random.uniform(30,60)
            print(f"Esperando {wait:.1f} segundos antes de reintentar...")
            time.sleep(wait)

# combinar resultados
df = pd.concat(results)

print(df)

# guardar
df.to_csv("google_trends_2018.csv")