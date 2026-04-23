from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import time
import csv
import pandas as pd
from clean_project.config import settings as config
from pathlib import Path
from datetime import datetime, timedelta
import re
import json
import os
import urllib.parse  # <--- IMPORTANTE: Necesario para codificar la URL

print("Linkedin SCRAPER INICIADO")

username = config.CREDENTIALS["linkedin"]["LINKEDIN_EMAIL"]
password = config.CREDENTIALS["linkedin"]["LINKEDIN_PASSWORD"]
query = config.scraping["linkedin"]["query"]
output_folder = config.general["output_folder"]
Path(output_folder).mkdir(parents=True, exist_ok=True)
output_file = f"{output_folder}/linkedin_global_dataset.csv"
start_date = datetime.strptime(config.general["start_date"], "%Y-%m-%d").date()
end_date = datetime.strptime(config.general["end_date"], "%Y-%m-%d").date()
max_scrolls = 1000000

SESSION_FILE        = "sesion_linkedin"
COOKIES_FILE        = SESSION_FILE + "/" + "session_cookies"
LOCALSTORAGE_FILE   = SESSION_FILE + "/" + "session_localstorage"

# ... (Las funciones fecha_aproximada, save_to_csv_safe, login_linkedin, 
# load/save cookies/storage, is_logged_in, cargar_pag SE MANTIENEN IGUAL) ...
# COPIA AQUÍ TUS FUNCIONES AUXILIARES SI NO LAS HAS CAMBIADO
# (Para ahorrar espacio, solo pongo las que cambian drásticamente)

def fecha_aproximada(fecha_raw):
    # (Tu función original sigue igual)
    if not fecha_raw: return None
    texto = fecha_raw.lower()
    hoy = datetime.today()
    if "minuto" in texto:
        n = int(re.search(r"\d+", texto).group())
        return (hoy - timedelta(minutes=n)).date().isoformat()
    if "hora" in texto:
        n = int(re.search(r"\d+", texto).group())
        return (hoy - timedelta(hours=n)).date().isoformat()
    if "día" in texto:
        n = int(re.search(r"\d+", texto).group())
        return (hoy - timedelta(days=n)).date().isoformat()
    if "semana" in texto:
        n = int(re.search(r"\d+", texto).group())
        return (hoy - timedelta(weeks=n)).date().isoformat()
    if "mes" in texto:
        n = int(re.search(r"\d+", texto).group())
        return (hoy - timedelta(days=30*n)).date().isoformat()
    return None

def save_to_csv_safe(data, output_file):
    # (Tu función original sigue igual)
    if not data:
        print("No hay datos para guardar")
        return
    df = pd.DataFrame(data, columns=["usuario", "contenido", "Website", "fecha", "fecha_relativa", "total_reacciones"])
    df.to_csv(output_file, sep=";", index=False, header=True, encoding="utf-8")
    print(f"CSV guardado correctamente en {output_file}")

def login_linkedin(driver, username, password):
    # (Tu función original sigue igual)
    driver.get("https://www.linkedin.com/login")
    time.sleep(2)
    user_input = driver.find_element(By.ID, "username")
    time.sleep(1)
    pass_input = driver.find_element(By.ID, "password")
    time.sleep(2)
    user_input.send_keys(username)
    pass_input.send_keys(password)
    pass_input.send_keys(Keys.RETURN)
    time.sleep(4)

# -------------------------------------------------------------------------
# CAMBIO PRINCIPAL 1: Nueva función search_query basada en URL
# -------------------------------------------------------------------------
def search_query(driver, query):
    # Limpiamos comillas dobles extras si vienen en el string para evitar errores de URL
    clean_query = query.replace('"', '')
    
    # Codificamos la búsqueda (ej: "hola mundo" -> "hola%20mundo")
    encoded_query = urllib.parse.quote(clean_query)
    
    # Construimos la URL MÁGICA:
    # 1. /search/results/content/ -> Fuerza "Publicaciones"
    # 2. sortBy="date_posted"     -> Fuerza "Lo último"
    # 3. keywords=...             -> Tu búsqueda
    url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&sortBy=%22date_posted%22"
    
    print(f"--> Navegando directamente a URL filtrada: {url}")
    driver.get(url)
    time.sleep(5) # Esperamos a que cargue el feed

def scrape_results_page(driver):
    # (Tu función original sigue igual, solo me aseguro que los selectores sean genéricos)
    time.sleep(2)
    # A veces LinkedIn cambia la clase del contenedor. Si falla, prueba "div.occludable-update"
    results = driver.find_elements(By.CSS_SELECTOR, "div.feed-shared-update-v2")
    
    data = []
    filas_vistas = set() 
    continue_scroll = True
    
    for item in results:
        # (Lógica de extracción idéntica a tu código original...)
        try:
            author = item.find_element(By.CSS_SELECTOR, "a.update-components-actor__meta-link").text.strip().split("\n", 1)[0].strip()
        except: author = None
        try:
            author_link = item.find_element(By.CSS_SELECTOR, "a.update-components-actor__meta-link").get_attribute("href")
        except: author_link = None
        try:
            raw_date  = item.find_element(By.CSS_SELECTOR, "span.update-components-actor__sub-description").text
        except: raw_date = None
        
        fecha_relativa = raw_date    
        date = fecha_aproximada(raw_date)
        
        if date:
            date_obj = datetime.strptime(date, "%Y-%m-%d").date()
            if date_obj < start_date:
                return data, False, len(results)
            if date_obj > end_date:
                continue

        try:
            content = item.find_element(By.CSS_SELECTOR, "div.update-components-text").text
        except: content = None

        reactions = {}
        try:
            reaction_button = item.find_element(By.CSS_SELECTOR, 'button[class*="social-details-social-counts__count-value"]')
            total_reactions = reaction_button.find_element(By.CSS_SELECTOR, "span.social-details-social-counts__reactions-count").text.strip()
            total_reactions = int(total_reactions.replace(".", "").replace(",", ""))
        except:
            total_reactions = 0
        
        fila = {
            "usuario": author, "contenido": content, "Website": author_link,
            "fecha": date, "fecha_relativa": fecha_relativa, "total_reacciones": total_reactions
        }
        
        fila_tuple = tuple(fila.items())
        if fila_tuple in filas_vistas: continue
        filas_vistas.add(fila_tuple)    
        data.append(fila)

    return data, continue_scroll, len(results)

def scroll_down(driver, max_scrolls, pause_time=3):
    # (Tu función original sigue igual)
    last_height = driver.execute_script("return document.body.scrollHeight")
    for scroll in range(max_scrolls):
        print(f"Scroll {scroll + 1}/{max_scrolls}")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause_time)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            print("No se cargan más resultados.")
            break
        last_height = new_height

# -------------------------------------------------------------------------
# CAMBIO PRINCIPAL 2: Limpieza de run_linkedin
# -------------------------------------------------------------------------
def run_linkedin(config):
    output_folder = Path(config.general["output_folder"])
    output_folder.mkdir(parents=True, exist_ok=True) 
    output_file = f"{output_folder}/linkedin_global_dataset.csv"
    
    if Path(output_file).exists() and Path(output_file).stat().st_size > 0:
        print(f"⚠️ El archivo CSV de LinkedIn ya existe. Saltando...")
        return

    options = Options()
    options.add_argument("--start-maximized")
    # options.add_argument("--headless") # Opcional si no quieres ver el navegador

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    time.sleep(2)
    query = config.scraping["linkedin"]["query"]
    
    cargar_pag(driver)
    load_cookies(driver)
    load_localstorage(driver)
    driver.refresh()
    time.sleep(3)

    if is_logged_in(driver):
        print("✅ Sesión reutilizada")
    else:
        print("❌ Sesión no válida. Haciendo login...")
        login_linkedin(driver, username, password)
    
    save_cookies(driver)
    save_localstorage(driver)
    
    print("Continuando con el scraping...")
    all_data = []
    seen_posts = set()
    print(f"\n KEYWORDS: {query}\n")

    for keyword in query:
        print(f"\nBuscando keyword: {keyword}\n")
        
        # --- AQUÍ ESTÁ LA CLAVE ---
        # Usamos la nueva función que va directo a la URL filtrada
        # No hace falta poner comillas aquí, la función search_query se encarga
        search_query(driver, keyword)
        
        # --- ELIMINAMOS TODOS LOS CLICS A BOTONES (FILTROS) ---
        # Ya estamos en Publicaciones > Lo último gracias a la URL.
        # Solo dejamos el botón de "Mostrar resultados" por si acaso aparece, 
        # aunque con URL directa suele cargar solo.
        try:
            mostrar_btn = driver.find_element(By.XPATH, "//span[text()='Mostrar resultados']")
            mostrar_btn.click()
            time.sleep(2)
        except:
            pass # Si no está, seguimos, ya deben estar los posts

        # --- Lógica de Scroll y Extracción (Igual que antes) ---
        previous_count = 0
        same_count_retries = 0
        MAX_SAME_COUNT = 3

        for i in range(max_scrolls):
            print(f"Extrayendo resultados (scroll {i + 1})...")
            page_data, continue_scroll, current_count = scrape_results_page(driver)

            for post in page_data:
                key = (post["usuario"], post["contenido"])
                if key not in seen_posts:
                    seen_posts.add(key)
                    all_data.append(post)

            if not continue_scroll:
                print("Se alcanzó el límite de fechas.")
                break

            if current_count == previous_count:
                same_count_retries += 1
                print(f"Reintentando scroll ({same_count_retries}/{MAX_SAME_COUNT})")
            else:
                same_count_retries = 0

            if same_count_retries >= MAX_SAME_COUNT:
                print("Fin del scroll (no cargan más).")
                break

            previous_count = current_count
            scroll_down(driver, max_scrolls=1)

    driver.quit()
    save_to_csv_safe(all_data, output_file)
    return all_data

# ... (Resto de funciones de cookies/storage: cargar_pag, is_logged_in, load_cookies, etc. igual) ...
def cargar_pag(driver):
    driver.get("https://www.linkedin.com/")
def is_logged_in(driver):
    try:
        driver.find_element(By.CSS_SELECTOR, "[id^='global-nav']")
        return True
    except: return False
def load_cookies(driver, path=COOKIES_FILE):
    path = Path(path)
    if not path.exists(): return
    with open(path) as f:
        cookies = json.load(f)
    for cookie in cookies:
        try: driver.add_cookie(cookie)
        except: pass
def save_cookies(driver, path=COOKIES_FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: json.dump(driver.get_cookies(), f)
def load_localstorage(driver, path=LOCALSTORAGE_FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    path = Path(path)
    if not path.exists(): return
    with open(path) as f: storage = json.load(f)
    for k, v in storage.items():
        driver.execute_script("window.localStorage.setItem(arguments[0], arguments[1]);", k, v)
def save_localstorage(driver, path=LOCALSTORAGE_FILE):
    storage = driver.execute_script("return {...window.localStorage};")
    with open(path, "w") as f: json.dump(storage, f)