import time
import csv
import re
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
from bs4 import BeautifulSoup

# Asumiendo que config se pasa correctamente
# import clean_project.config.settings as config 

print("▶ TWITTER SCRAPER INICIADO")

# ---------------------------------------------
BASE_URL = "https://nitter.poast.org"
MAX_CARGA_REINTENTOS = 3
PAUSA_ENTRE_CARGA_REINTENTOS = 2
PAUSA_ENTRE_PERFILES = 0.5
PAUSA_ENTRE_PAGINAS = 0.5
PAUSA_DETALLE_TWEET = 1.5 
# ---------------------------------------------

def daterange(start_date, end_date):
    for n in range((end_date - start_date).days + 1):
        yield start_date + timedelta(n)

def parse_fecha_tweet(fecha_str):
    try:
        fecha_limpia = fecha_str.replace(" UTC", "")
        dt = datetime.strptime(fecha_limpia, "%b %d, %Y · %I:%M %p")
        return dt.date()
    except:
        return None

def obtener_stat_por_icono(tweet_stats_div, icon_class):
    try:
        if not tweet_stats_div: return 0
        if icon_class == 'icon-quote':
            parent_element = tweet_stats_div.find('a', class_='tweet-stat')
        else:
            icon_span = tweet_stats_div.find('span', class_=icon_class)
            parent_element = icon_span.find_parent('span', class_='tweet-stat') if icon_span else None
        
        if parent_element:
            numbers = re.findall(r'\d+', parent_element.get_text(strip=True).replace(',', ''))
            if numbers:
                return int(numbers[-1])
    except:
        return 0
    return 0

def pasa_filtro_contenido(texto_tweet, keyword_query):
    if not texto_tweet: return False
    texto_norm = texto_tweet.lower()
    query_clean = keyword_query.replace('"','').lower()
    palabras_clave = [p.replace('*','') for p in query_clean.split()]
    for palabra in palabras_clave:
        patron = r'(?:^|\W)#?' + re.escape(palabra) + r'\w*'
        if not re.search(patron, texto_norm):
            return False
    return True

def run_twitter(config):
    search_form_lang_map = config.general.get("search_form_lang_map", {})

    start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d").date()
    end_date   = datetime.strptime(config.general["end_date"], "%Y-%m-%d").date()
    keywords = config.scraping["twitter"]["query"]

    output_folder = config.general.get("output_folder", "data")
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/twitter_global_dataset.csv"

    if Path(output_file).exists() and Path(output_file).stat().st_size > 0:
        print(f"⚠️ CSV ya existe: {output_file}. Saltando scraper.")
        return

    todos_los_posteos = []
    seen_tweets = set()

    # Configuración Selenium
    options = webdriver.FirefoxOptions()
    # options.add_argument("--headless") 
    options.set_preference("general.useragent.override",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
    )

    driver = webdriver.Firefox(service=Service(GeckoDriverManager().install()), options=options)

    try:
        for dia in daterange(start_date, end_date):
            fecha_since = dia.strftime("%Y-%m-%d")
            fecha_until = (dia + timedelta(days=1)).strftime("%Y-%m-%d")
            print(f"\n--- Procesando Fecha: {fecha_since} ---")

            for keyword in keywords:
                languages = search_form_lang_map.get(keyword, [])
                query_encoded = urllib.parse.quote_plus(f'"{keyword}"')
                url_busqueda = f"{BASE_URL}/search?f=tweets&q={query_encoded}&since={fecha_since}&until={fecha_until}"
                
                page_loaded = False
                for intento in range(MAX_CARGA_REINTENTOS):
                    try:
                        driver.get(url_busqueda)
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".timeline-item, .timeline-end, .timeline-none"))
                        )
                        page_loaded = True
                        break
                    except Exception as e:
                        print(f"  ⚠️ Intento {intento+1} fallido: {e}")
                        time.sleep(PAUSA_ENTRE_CARGA_REINTENTOS)
                
                if not page_loaded:
                    print(f"  ⚠️ No se pudo cargar la URL: {url_busqueda}")
                    continue

                while True:
                    soup = BeautifulSoup(driver.page_source, 'html.parser')

                    if soup.find('div', class_='timeline-none') or soup.find('h2', class_='timeline-end'):
                        break

                    posteos_en_pagina = soup.find_all('div', class_='timeline-item')
                    if not posteos_en_pagina:
                        break

                    nuevos = 0
                    for post in posteos_en_pagina:
                        contenido_div = post.find('div', class_='tweet-content')
                        if not contenido_div: continue
                        contenido = contenido_div.get_text(strip=True)
                        
                        if not pasa_filtro_contenido(contenido, keyword):
                            continue

                        enlace_tag = post.find('a', class_='tweet-link')
                        if not enlace_tag: continue
                        enlace = BASE_URL + enlace_tag['href']

                        usuario = post.find('a', class_='username').get_text(strip=True) if post.find('a', class_='username') else "N/A"
                        
                        fecha_span = post.find('span','tweet-date')
                        if fecha_span and fecha_span.find('a'):
                            fecha_post_raw = fecha_span.find('a')['title']
                        else:
                            fecha_post_raw = fecha_since
                            
                        fecha_post_date = parse_fecha_tweet(fecha_post_raw)
                        
                        if not fecha_post_date or fecha_post_date < start_date or fecha_post_date > end_date:
                            continue

                        stats_div = post.find('div', class_='tweet-stats')
                        comments = obtener_stat_por_icono(stats_div,'icon-comment')
                        retweets = obtener_stat_por_icono(stats_div,'icon-retweet')
                        quotes   = obtener_stat_por_icono(stats_div,'icon-quote')
                        hearts   = obtener_stat_por_icono(stats_div,'icon-heart')
                        plays    = obtener_stat_por_icono(stats_div,'icon-play')

                        info_perfil = {
                            "Likes":"N/A","Followers":"N/A","Following":"N/A","Tweets":"N/A",
                            "Bio":"N/A","Ubicacion":"No especificada","Fullname":"N/A",
                            "JoinDate":"N/A","Website":"No especificado","IsVerified":"No verificado",
                            "IsProtected":"Pública"
                        }

                        # ---------------------------------------------
                        # LÓGICA DE DETECCIÓN DE TIPO DE TWEET Y BEFORE-TWEET (MODIFICADA)
                        # ---------------------------------------------
                        tipo_tweet = "original"
                        tiene_before = False
                        before_usuario = "N/A"
                        before_contenido = "N/A"
                        before_enlace = "N/A"

                        # 1. Detectar Quote (Cita) - La info ESTÁ en el timeline
                        quote_div = post.find("div", class_="quote") or post.find("div", class_="quoted-tweet")
                        
                        if quote_div:
                            tipo_tweet = "quote"
                            tiene_before = True
                            
                            # Extraer datos directamente del div quote sin abrir pestaña
                            q_user = quote_div.find('a', class_='username')
                            q_text = quote_div.find('div', class_='quote-text')
                            q_link = quote_div.find('a', class_='quote-link')

                            if q_user: before_usuario = q_user.get_text(strip=True)
                            if q_text: before_contenido = q_text.get_text(strip=True)
                            if q_link: before_enlace = BASE_URL + q_link['href']

                        # 2. Detectar Reply (Respuesta) - La info NO suele estar completa en el timeline
                        replying_to_div = post.find('div', class_='replying-to')
                        
                        if replying_to_div:
                            # Si es reply, esto tiene precedencia sobre si es quote (a veces es ambos)
                            tipo_tweet = "reply" 
                            tiene_before = True
                            
                            try:
                                ventana_principal = driver.current_window_handle
                                driver.execute_script(f"window.open('{enlace}', '_blank');")
                                driver.switch_to.window(driver.window_handles[-1])
                                
                                try:
                                    WebDriverWait(driver, 10).until(
                                        EC.presence_of_element_located((By.CLASS_NAME, "main-tweet"))
                                    )
                                    soup_detalle = BeautifulSoup(driver.page_source, 'html.parser')
                                    lista_befores = soup_detalle.find_all('div', class_='before-tweet')
                                    
                                    if lista_befores:
                                        padre = lista_befores[-1]
                                        b_user = padre.find('a', class_='username')
                                        b_cont = padre.find('div', class_='tweet-content')
                                        b_link = padre.find('a', class_='tweet-link')
                                        
                                        if b_user: before_usuario = b_user.get_text(strip=True)
                                        if b_cont: before_contenido = b_cont.get_text(strip=True)
                                        if b_link: before_enlace = BASE_URL + b_link['href']
                                        
                                except Exception as e_wait:
                                    print(f"    ⚠️ Tiempo agotado buscando before-tweet: {e_wait}")
                                
                            except Exception as e_tab:
                                print(f"    ⚠️ Error pestañas: {e_tab}")
                            
                            finally:
                                if len(driver.window_handles) > 1:
                                    driver.close()
                                    driver.switch_to.window(ventana_principal)

                        # ---------------------------------------------
                        # Armado de fila
                        fila = {
                            "usuario": usuario, 
                            "Fullname": info_perfil["Fullname"], 
                            "contenido": contenido,
                            "fecha": fecha_post_raw, 
                            "enlace": enlace, 
                            "TipoDeTweet": tipo_tweet,
                            "TieneBeforeTweet": tiene_before,
                            "BeforeUsuario": before_usuario,
                            "BeforeContenido": before_contenido,
                            "BeforeEnlace": before_enlace,
                            "comments": comments, 
                            "retweets": retweets, 
                            "quotes": quotes,
                            "hearts": hearts, 
                            "plays": plays,
                            "search_keyword": keyword,
                            "keyword_languages": ",".join(languages)
                        }
                        fila.update(info_perfil)

                        tweet_key = (usuario, contenido, fecha_post_raw, enlace)
                        if tweet_key not in seen_tweets:
                            seen_tweets.add(tweet_key)
                            todos_los_posteos.append(fila)
                            nuevos += 1

                    if nuevos > 0:
                        print(f"  -> +{nuevos} tweets guardados (Total: {len(todos_los_posteos)})")

                    try:
                        load_more = driver.find_element(By.CSS_SELECTOR, ".show-more a")
                        driver.execute_script("arguments[0].scrollIntoView();", load_more)
                        load_more.click()
                        time.sleep(PAUSA_ENTRE_PAGINAS)
                    except:
                        break

    finally:
        driver.quit()

    fieldnames = [
        "usuario","Fullname","contenido","fecha","enlace","TipoDeTweet","TieneBeforeTweet",
        "BeforeUsuario","BeforeContenido","BeforeEnlace",
        "comments","retweets","quotes","hearts","plays",
        'Likes','Followers','Following','Tweets','Bio','Ubicacion','JoinDate','Website','IsVerified','IsProtected',
        "search_keyword", "keyword_languages"
    ]
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(todos_los_posteos)

    print(f"\n✅ CSV guardado: {output_file} con {len(todos_los_posteos)} filas")
    return todos_los_posteos