import time
import csv
import re
import urllib.parse
from datetime import date, timedelta, datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
from bs4 import BeautifulSoup

import clean_project.config.settings as config

print("Twitter SCRAPER INICIADO")


BASE_URL = "https://nitter.poast.org"  # URL base del servicio Nitter
MAX_CARGA_REINTENTOS = 3               # Reintentos si falla la carga de página
PAUSA_ENTRE_CARGA_REINTENTOS = 3      # Segundos entre reintentos
PAUSA_ENTRE_PERFILES = 1.0             # Pausa entre apertura de perfiles
PAUSA_ENTRE_PAGINAS = 2.0              # Pausa entre páginas de resultados

# -------------------------------------------------------------
# Función para generar rango de fechas (desde start_date hasta end_date)
# -------------------------------------------------------------
def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)
# -------------------------------------------------------------
def parse_fecha_tweet(fecha_str):
    """
    Convierte 'Nov 14, 2021 · 12:27 PM UTC' → date
    """
    try:
        fecha_limpia = fecha_str.replace(" UTC", "")
        dt = datetime.strptime(fecha_limpia, "%b %d, %Y · %I:%M %p")
        return dt.date()
    except Exception:
        return None
# -------------------------------------------------------------
# Función para extraer estadísticas de un tweet (likes, retweets, etc.)
# -------------------------------------------------------------
def obtener_stat_por_icono(tweet_stats_div, icon_class):
    try:
        if not tweet_stats_div:
            return 0
        if icon_class == 'icon-quote':
            parent_element = tweet_stats_div.find('a', class_='tweet-stat')
        else:
            icon_span = tweet_stats_div.find('span', class_=icon_class)
            parent_element = icon_span.find_parent('span', class_='tweet-stat') if icon_span else None
        if parent_element:
            numbers = re.findall(r'\d+', parent_element.get_text(strip=True).replace(',', ''))
            if numbers:
                return int(numbers[-1])
    except Exception:
        return 0
    return 0
# -------------------------------------------------------------
# Función para extraer información de perfil de un usuario
# -------------------------------------------------------------
def extraer_info_perfil(driver, username, perfil_cache):
    """
    Extrae información de un perfil y la almacena en un diccionario.
    Usa cache para no repetir la extracción de perfiles ya vistos.
    """
    if username in perfil_cache:
        return perfil_cache[username]

    info_perfil = {"Likes":"N/A","Followers":"N/A","Following":"N/A","Tweets":"N/A",
                   "Bio":"N/A","Ubicacion":"No especificada","Fullname":"N/A",
                   "JoinDate":"N/A","Website":"No especificado","IsVerified":"No verificado",
                   "IsProtected":"Pública"}

    ventana_principal = driver.current_window_handle
    try:
        driver.switch_to.new_window('tab')
        driver.get(f"{BASE_URL}/{username}")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "profile-card")))
        time.sleep(0.5)

        # Extraer cada campo del perfil si existe
        try: info_perfil['Likes'] = driver.find_element(By.XPATH, "//li[@class='likes']/span[@class='profile-stat-num']").text.replace(',', '')
        except: pass
        try: info_perfil['Followers'] = driver.find_element(By.XPATH, "//li[@class='followers']/span[@class='profile-stat-num']").text.replace(',', '')
        except: pass
        try: info_perfil['Following'] = driver.find_element(By.XPATH, "//li[@class='following']/span[@class='profile-stat-num']").text.replace(',', '')
        except: pass
        try: info_perfil['Tweets'] = driver.find_element(By.XPATH, "//li[@class='posts']/span[@class='profile-stat-num']").text.replace(',', '')
        except: pass
        try: info_perfil['Bio'] = driver.find_element(By.CLASS_NAME, "profile-bio").text.replace('\n',' ')
        except: pass
        try: info_perfil['Ubicacion'] = driver.find_element(By.XPATH, "//div[@class='profile-location']/span[last()]").text
        except: pass
        try: info_perfil['Fullname'] = driver.find_element(By.CLASS_NAME, "profile-card-fullname").get_attribute('title')
        except: pass
        try: info_perfil['JoinDate'] = driver.find_element(By.XPATH, "//div[@class='profile-joindate']/span").get_attribute('title')
        except: pass
        try: info_perfil['Website'] = driver.find_element(By.XPATH, "//div[@class='profile-website']//a").get_attribute('href')
        except: pass
        try: info_perfil['IsVerified'] = driver.find_element(By.CLASS_NAME, "verified-icon").get_attribute('title')
        except: pass
        try:
            driver.find_element(By.CLASS_NAME, "icon-lock")
            info_perfil['IsProtected'] = 'Protegida'
        except: pass

    except Exception:
        pass
    finally:
        try:
            driver.close()
            driver.switch_to.window(ventana_principal)
        except Exception:
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                break

    perfil_cache[username] = info_perfil
    return info_perfil

# -------------------------------------------------------------
# -------------------------------------------------------------
# ... (imports y funciones anteriores se mantienen igual) ...
def pasa_filtro_contenido(texto_tweet, keyword_query):
    """
    Verifica si las palabras de la keyword aparecen realmente en el texto.
    Soporta coincidencias parciales al final (ej: 'dron' valida 'drones', '#dron', 'dron123').
    Devuelve True si TODAS las palabras de la query están en el texto.
    """
    if not texto_tweet:
        return False
        
    texto_norm = texto_tweet.lower()
    # Limpiamos la query de comillas si las tuviera y bajamos a minúsculas
    query_clean = keyword_query.replace('"', '').lower()
    
    # Si el usuario usó asteriscos en la config (ej: "vuelo*"), los quitamos para buscar la raíz
    palabras_clave = [p.replace('*', '') for p in query_clean.split()]

    for palabra in palabras_clave:
        # Explicación del Regex:
        # (?:^|\W) -> Que empiece la línea O haya un caracter no alfanumérico antes (espacio, punto, etc)
        # #?       -> Opcionalmente un hashtag
        # palabra  -> La palabra clave (ej: dron)
        # \w*      -> Opcionalmente más letras o números después (ej: es, s, 123)
        patron = r'(?:^|\W)#?' + re.escape(palabra) + r'\w*'
        
        if not re.search(patron, texto_norm):
            # Si falta ALGUNA de las palabras, el tweet no sirve.
            return False
            
    return True

# -------------------------------------------------------------
# LÓGICA PRINCIPAL (RUN TWITTER)
# -------------------------------------------------------------
def run_twitter(config):
    search_form_lang_map = config.general.get("search_form_lang_map", {})

    # Configuración de fechas y carpetas
    start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d").date()
    end_date   = datetime.strptime(config.general["end_date"], "%Y-%m-%d").date()
    keywords = config.scraping["twitter"]["query"]
    
    output_folder = config.general.get("output_folder", "data")
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/twitter_global_dataset.csv"
    
    # Verificar si ya existe para no repetir
    if Path(output_file).exists() and Path(output_file).stat().st_size > 0:
        print(f"⚠️ El archivo CSV ya existe en: {output_file}. Saltando...")
        return

    perfiles_cache = {}
    todos_los_posteos = []
    seen_tweets = set()
    
    options = webdriver.FirefoxOptions()
    # options.add_argument("--headless") # Descomenta si quieres ocultar el navegador
    driver = webdriver.Firefox(service=Service(GeckoDriverManager().install()), options=options)

    try:
        for dia in daterange(start_date, end_date):
            fecha_since = dia.strftime("%Y-%m-%d")
            fecha_until = (dia + timedelta(days=1)).strftime("%Y-%m-%d")
            print(f"\n--- Procesando Fecha: {fecha_since} ---")

            for keyword in keywords:
                languages = search_form_lang_map.get(keyword, [])
                print(f"\n🔹 Buscando tweets para keyword: '{keyword}' con idiomas: {languages}")
                # 1. URL con comillas forzadas para búsqueda exacta
                query_encoded = urllib.parse.quote_plus(f'"{keyword}"')
                print(f"\nBuscando keyword: '{keyword}'")
                url_busqueda = f"{BASE_URL}/search?f=tweets&q={query_encoded}&since={fecha_since}&until={fecha_until}"
                # print(f"DEBUG URL: {url_busqueda}")

                # 2. Carga con reintentos
                page_loaded = False
                for intento in range(MAX_CARGA_REINTENTOS):
                    try:
                        driver.get(url_busqueda)
                        # Esperamos cualquier indicio de carga: items, fin, o "no results"
                        WebDriverWait(driver, 8).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".timeline-item, .timeline-end, .timeline-none"))
                        )
                        page_loaded = True
                        break
                    except Exception:
                        time.sleep(PAUSA_ENTRE_CARGA_REINTENTOS)
                
                if not page_loaded:
                    print(f"  ⚠️ Timeout cargando keyword: {keyword}")
                    continue

                # 3. Bucle de Paginación
                while True:
                    soup = BeautifulSoup(driver.page_source, 'html.parser')

                    # Verificación explícita de "No results"
                    if soup.find('div', class_='timeline-none'):
                        # print(f"  ⛔ Sin resultados para '{keyword}' en esta fecha.")
                        break

                    posteos_en_pagina = soup.find_all('div', class_='timeline-item')
                    if not posteos_en_pagina:
                        break

                    nuevos = 0
                    for post in posteos_en_pagina:
                        # --- EXTRACCIÓN DEL CONTENIDO PARA FILTRADO ---
                        contenido_div = post.find('div', class_='tweet-content')
                        if not contenido_div: continue
                        contenido = contenido_div.get_text(strip=True)

                        # --- FILTRO ANTISPAM / EXACTITUD ---
                        if not pasa_filtro_contenido(contenido, keyword):
                            continue
                        # --------------------------------------------

                        # Si pasa el filtro, extraemos todo lo demás
                        enlace_tag = post.find('a', class_='tweet-link')
                        if not enlace_tag: continue
                        enlace = BASE_URL + enlace_tag['href']
                        
                        usuario = post.find('a', class_='username').get_text(strip=True)
                        fecha_span = post.find('span','tweet-date')
                        # Usamos title para la fecha exacta, o fallback a la fecha de búsqueda
                        fecha_post = fecha_span.find('a')['title'] if fecha_span else fecha_since
                        fecha_post_raw = fecha_span.find('a')['title'] if fecha_span else None
                        fecha_post_date = parse_fecha_tweet(fecha_post_raw)
                        if not fecha_post_date:
                            continue

                        # ⛔ FILTRO DURO POR RANGO
                        if fecha_post_date < start_date or fecha_post_date > end_date:
                            continue
                        # Stats
                        stats_div = post.find('div', class_='tweet-stats')
                        comments = obtener_stat_por_icono(stats_div,'icon-comment')
                        retweets = obtener_stat_por_icono(stats_div,'icon-retweet')
                        quotes = obtener_stat_por_icono(stats_div,'icon-quote')
                        hearts = obtener_stat_por_icono(stats_div,'icon-heart')
                        plays = obtener_stat_por_icono(stats_div,'icon-play')

                        # Perfil (con cache)
                        usuario_limpio = usuario.replace('@','')
                        if usuario_limpio not in perfiles_cache:
                            info_perfil = extraer_info_perfil(driver, usuario_limpio, perfiles_cache)
                            perfiles_cache[usuario_limpio] = info_perfil
                            time.sleep(PAUSA_ENTRE_PERFILES)
                        else:
                            info_perfil = perfiles_cache[usuario_limpio]

                        fila_original = {
                            "usuario": usuario, "Fullname": info_perfil.get('Fullname',''), "contenido": contenido,
                            "fecha": fecha_post, "enlace": enlace, "TipoDeTweet": "Original",
                            "UsuarioOriginal": "N/A", "EnlaceOriginal": "N/A",
                            "comments": comments, "retweets": retweets, "quotes": quotes, "hearts": hearts, "plays": plays,
                            "search_keyword": keyword,
                            "keyword_languages": ",".join(languages)
 }
                        fila_original.update(info_perfil)

                        # Verificación de duplicados
                        tweet_key = (usuario, contenido, fecha_post, enlace)
                        if tweet_key not in seen_tweets:
                            seen_tweets.add(tweet_key)
                            todos_los_posteos.append(fila_original)
                            nuevos += 1

                            # -----------------------------------------------------------
                            # IMPRESIÓN DETALLADA DEL TWEET RELEVANTE
                            # -----------------------------------------------------------
                            # print("\n" + "="*70)
                            # print(f"✅ TWEET RELEVANTE AGREGADO (Match con Query: '{keyword}')")
                            # print(f"   -> Fecha Escrapeo: {fecha_since}")
                            # print(f"   -> Fecha Tweet:    {fecha_post}")
                            # print(f"👤 Autor: {usuario} ({info_perfil.get('Fullname', 'N/A')})")
                            # print(f"🔗 Enlace: {enlace}")
                            # print("-" * 30)
                            # print(f"{contenido}")
                            # print("="*70 + "\n")
                            # -----------------------------------------------------------

                    if nuevos > 0:
                        print(f"  -> +{nuevos} tweets guardados (Total acumulado: {len(todos_los_posteos)})")

                    # Lógica de "Cargar más" / Paginación
                    if soup.find('h2', class_='timeline-end'):
                        # print("  ⛔ Fin del timeline.")
                        break

                    try:
                        load_more = driver.find_element(By.CSS_SELECTOR, ".show-more a")
                        driver.execute_script("arguments[0].scrollIntoView();", load_more)
                        load_more.click()
                        time.sleep(PAUSA_ENTRE_PAGINAS)
                    except Exception:
                        # Si no hay botón load more y no hubo timeline-end, asumimos fin
                        break

    finally:
        driver.quit()

    # Guardar CSV Final
    fieldnames = [
        "usuario","Fullname","contenido","fecha","enlace","TipoDeTweet","UsuarioOriginal","EnlaceOriginal",
        "comments","retweets","quotes","hearts","plays",
        'Likes','Followers','Following','Tweets','Bio','Ubicacion','JoinDate',
        'Website','IsVerified','IsProtected', "search_keyword", "keyword_languages"
    ]
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(todos_los_posteos)

    print(f"\n✅ PROCESO FINALIZADO. CSV guardado: {output_file} con {len(todos_los_posteos)} filas.")
    return todos_los_posteos

'''
def run_twitter(config):
    # Leer fechas y keywords desde configuración
    start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d").date()
    end_date   = datetime.strptime(config.general["end_date"], "%Y-%m-%d").date()
    keywords = config.scraping["twitter"]["query"] 
    print(f"keywords: {keywords}")
    output_folder = config.general.get("output_folder", "data")
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    output_file = f"{output_folder}/twitter_global_dataset.csv"
    # Si el archivo ya existe, saltamos el scraper
    if Path(output_file).exists() and Path(output_file).stat().st_size > 0:
        print(f"⚠️ El archivo CSV de Twitter ya existe en: {output_file}. Saltando este scraper...")
        return  # Salir de la función si el archivo ya existe 
    perfiles_cache = {}       # Cache de perfiles ya extraídos
    todos_los_posteos = []    # Lista final de todos los posts y citas
    #seen_rows = set()         # Verificación de duplicados exactos por fila completa
    seen_tweets = set()  # Verificación de tweets únicos por usuario, contenido, fecha y enlace
    options = webdriver.FirefoxOptions()
    # options.add_argument("--headless")  # Descomenta si no quieres ver el navegador
    driver = webdriver.Firefox(service=Service(GeckoDriverManager().install()), options=options)

    try:
        for dia in daterange(start_date, end_date):
            fecha_since = dia.strftime("%Y-%m-%d")
            fecha_until = (dia + timedelta(days=1)).strftime("%Y-%m-%d")
            print(f"Procesando {fecha_since}")
            print(f"\n KEYWORDS QUE SE VAN A BUSCAR EN TWITTER: {keywords}\n")

            for keyword in keywords:
                keyword_query = keyword
                query = keyword_query #urllib.parse.quote_plus(keyword_query)
                #query = urllib.parse.quote_plus(keyword)
                #url_busqueda = f"{BASE_URL}/search?f=tweets&q={query}&since={fecha_since}&until={fecha_until}&near="
                # url_busqueda = f"{BASE_URL}/search?f=tweets&q={query}&since={fecha_since}&until={fecha_until}"
                url_busqueda = f"{BASE_URL}/search?f=tweets&q={urllib.parse.quote_plus(query)}&since={fecha_since}&until={fecha_until}&near="#f"{BASE_URL}/search?f=tweets&q={urllib.parse.quote_plus(query)}&since={fecha_since}&until={fecha_until}&near="
                print(f"url_busqueda: {url_busqueda}")

                # Reintentos si la página no carga
                page_loaded = False
                for intento in range(MAX_CARGA_REINTENTOS):
                    try:
                        driver.get(url_busqueda)
                        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "timeline-item")))
                        page_loaded = True
                        break
                    except Exception:
                        time.sleep(PAUSA_ENTRE_CARGA_REINTENTOS)
                if not page_loaded:
                    print("  No se pudo cargar la página, saltando keyword")
                    continue

                # Leer posts de la página
                while True:
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    # ⛔ CORTE DEFINITIVO: no hay más resultados para ESTE DÍA
                    if soup.find('h2', class_='timeline-end'):
                        print("  ⛔ No more items → pasar al siguiente día")
                        break

                    posteos_en_pagina = soup.find_all('div', class_='timeline-item')
                    if not posteos_en_pagina:
                        break

                    nuevos = 0
                    for post in posteos_en_pagina:
                        enlace_tag = post.find('a', class_='tweet-link')
                        if not enlace_tag:
                            continue
                        enlace = BASE_URL + enlace_tag['href']

                        usuario = post.find('a', class_='username').get_text(strip=True)
                        contenido = post.find('div', class_='tweet-content').get_text(strip=True)
                        print(f"Contenido: {contenido}")
                        fecha_post = post.find('span','tweet-date').find('a')['title']
                        print(f"fecha_post: {fecha_post}")


                        stats_div = post.find('div', class_='tweet-stats')
                        comments = obtener_stat_por_icono(stats_div,'icon-comment')
                        retweets = obtener_stat_por_icono(stats_div,'icon-retweet')
                        quotes = obtener_stat_por_icono(stats_div,'icon-quote')
                        hearts = obtener_stat_por_icono(stats_div,'icon-heart')
                        plays = obtener_stat_por_icono(stats_div,'icon-play')

                        usuario_limpio = usuario.replace('@','')
                        if usuario_limpio not in perfiles_cache:
                            info_perfil = extraer_info_perfil(driver, usuario_limpio, perfiles_cache)
                            perfiles_cache[usuario_limpio] = info_perfil
                            time.sleep(PAUSA_ENTRE_PERFILES)
                        else:
                            info_perfil = perfiles_cache[usuario_limpio]

                        # -------------------------------------------------------------
                        # Construir fila del post
                        # -------------------------------------------------------------
                        
                        
                        fila_original = {
                            "usuario": usuario, "Fullname": info_perfil.get('Fullname',''), "contenido": contenido,
                            "fecha": fecha_post, "enlace": enlace, "TipoDeTweet": "Original",
                            "UsuarioOriginal": "N/A", "EnlaceOriginal": "N/A",
                            "comments": comments, "retweets": retweets, "quotes": quotes, "hearts": hearts, "plays": plays
                        }
                        fila_original.update(info_perfil)

                        # -------------------------------------------------------------
                        # Verificación de duplicado exacto de fila completa
                        # -------------------------------------------------------------
                        
                        # fila_tuple = tuple(fila_original.items())
                        # if fila_tuple not in seen_rows:
                        #     seen_rows.add(fila_tuple)
                        #     todos_los_posteos.append(fila_original)
                        #     nuevos += 1
                        tweet_key = (usuario, contenido, fecha_post, enlace)

                        if tweet_key not in seen_tweets:
                            seen_tweets.add(tweet_key)
                            todos_los_posteos.append(fila_original)
                            nuevos += 1
                        # -------------------------------------------------------------
                        # Extraer citas del post si las tiene
                        # -------------------------------------------------------------
                        # if quotes > 0:
                        #     filas_citas = extraer_info_de_citas(driver, enlace, usuario, perfiles_cache)
                        #     for fila in filas_citas:
                        #         cita_key = (fila['usuario'], fila['contenido'], fila['fecha'], fila['enlace'])
                        #         if cita_key not in seen_tweets:
                        #             seen_tweets.add(cita_key)
                        #             todos_los_posteos.append(fila)

                    if nuevos > 0:
                        print(f"  -> Extraídos {nuevos} nuevos (acumulado {len(todos_los_posteos)})")

                    # Paginar: click en "Cargar más"
                    try:
                        load_more = driver.find_element(By.CSS_SELECTOR, ".show-more a")
                        load_more.click()
                        time.sleep(PAUSA_ENTRE_PAGINAS)
                    except Exception:
                        break

    finally:
        driver.quit()

    # Guardar CSV final
    fieldnames = [
        "usuario","Fullname","contenido","fecha","enlace","TipoDeTweet","UsuarioOriginal","EnlaceOriginal",
        "comments","retweets","quotes","hearts","plays",
        'Likes','Followers','Following','Tweets','Bio','Ubicacion','JoinDate','Website','IsVerified','IsProtected'
    ]
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(todos_los_posteos)

    print(f"\n✅ CSV global guardado: {output_file} con {len(todos_los_posteos)} filas")
    return todos_los_posteos
'''