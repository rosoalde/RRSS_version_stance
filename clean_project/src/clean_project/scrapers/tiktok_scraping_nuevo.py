from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import re
import csv
import os
from datetime import datetime, timedelta
import clean_project.config.settings as config        # Archivo externo de configuración
from pathlib import Path
#falta:
#scrollear comentarios
#capturar respuestas a comentarios
#scrollear en google (posiblemente) y que busque más resultados
def google(driver):
    driver.get("https://www.google.com/")

def aceptar_cookies(driver):
    # Aceptar cookies si aparece
    try:
        driver.find_element(By.XPATH, "//button[contains(., 'Aceptar')]").click()
    except:
        pass

def detectar_recaptcha(driver):
    try:
        # 1️⃣ Comprobar URL sospechosa
        if "sorry" in driver.current_url.lower():
            print("🛑 reCAPTCHA detectado (URL)")
            input("⏸ Resuelve el captcha y pulsa ENTER para continuar...")
            return True

        # 2️⃣ Buscar iframe de reCAPTCHA
        iframes = driver.find_elements(By.XPATH, "//iframe[contains(@src, 'recaptcha')]")
        if iframes:
            print("🛑 reCAPTCHA detectado (iframe)")
            input("⏸ Resuelve el captcha y pulsa ENTER para continuar...")
            return True

        # 3️⃣ Buscar textos típicos
        titulo = driver.title.lower()
        if "unusual" in titulo or "traffic" in titulo:
            print("🛑 reCAPTCHA detectado (título)")
            input("⏸ Resuelve el captcha y pulsa ENTER para continuar...")
            return True

    except Exception as e:
        print("Error comprobando captcha:", e)

    return False


def detectar_recaptcha_tiktok(driver):
    try:
        driver.find_element(
            By.CSS_SELECTOR, '//div[contains@class, "captcha-verify-container"]'
        )
        print("🛑 reCAPTCHA detectado de TikTok")
        input("⏸ Resuelve el captcha y pulsa ENTER para continuar...")
        return True
    
    except Exception as e:
        pass

    return False

def detectar_login_tiktok(driver):
    try:
        boton = driver.find_element(
            By.CSS_SELECTOR, '[data-e2e="modal-close-inner-button"]'
        )
        boton.click()
    except Exception as e:
        pass

    return False

def detectar_intereses_tiktok(driver):
    try:
        boton = driver.find_element(
            By.CSS_SELECTOR, "//button//div[contains(@class, 'TUXButton-label') and text()='Omitir']"
        )
        boton.click()
    except Exception as e:
        pass

    return False

def detectar_accesoRapido_tiktok(driver):
    try:
        # Espera hasta que el botón sea visible
        boton_cerrar = driver.find_element(
            By.XPATH, "//div[contains(@class, 'DivXMarkWrapper')]"
        )

        # Haz clic en el botón
        boton_cerrar.click()
        print("Botón cierre acceso rápido con éxito.")

    except Exception as e:
        pass

def busqueda_google(driver, config):
    after = str(config.general["end_date"])
    before = str(config.general["start_date"])

    query = (
    'site:tiktok.com '
    'after:'+ after + ' '
    'before:'+ before + ' '
    + '"'+config.scraping["tiktok"]["query"][0]+'"')#config.scraping["tiktok"]["query"])
    search_box = driver.find_element(By.NAME, "q")
    search_box.send_keys(query)
    search_box.send_keys(Keys.RETURN)

def gestionar_cookies_tiktok(driver, aceptar=True, timeout=5):
    time.sleep(timeout)
    try:
        if aceptar:
            texto = "Permitir"
        else:
            texto = "Rechazar"#"Decline optional cookies"
        
        banner = driver.find_element(
            By.XPATH,
            "//div[contains(@class,'cookie-content')]"#/ancestor::div[contains(@class,'tiktok-cookie-banner')]"
        )

        boton_cookie = banner.find_element(
            By.XPATH,
            ".//button[contains(text(),'"+texto+"')]"
        )
        
        boton_cookie.click()
        '''
        driver.execute_script(f"""
        const banner = document.querySelector('k-cookie-banner');
        if (!banner) return;
        const shadow = banner.shadowRoot;
        const buttons = shadow.querySelectorAll('button');
        for (let b of buttons) {{
            if (b.innerText.trim() === "{texto}") {{
                b.click();
                return;
            }}
        }}
        """)
        '''
        print("🍪 Cookies TikTok gestionadas correctamente")
        return True

    except Exception as e:
        print("❌ Error cookies TikTok:", e)
        return False


def ententido_tiktok(driver):
    try:
        boton = driver.find_element(
            By.XPATH,
            "//button[.//div[normalize-space()='Entendido']]"
        )

        boton.click()
        time.sleep(1)
        print("🍪 Cookies TikTok ENTENDIDO")
        return True

    except:
        print("❌ No apareció el botón 'Entendido'")
        return False

def inicializar_tiktok(driver):
    main_tab = driver.current_window_handle

    # Abrir nueva pestaña
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[-1])

    driver.get("https://www.tiktok.com")
    time.sleep(8)

    # Aceptar cookies
    detectar_login_tiktok(driver)
    detectar_intereses_tiktok(driver)
    gestionar_cookies_tiktok(driver, aceptar=False)
    detectar_accesoRapido_tiktok(driver)
    ententido_tiktok(driver)
    # (opcional) detectar captcha
    detectar_recaptcha(driver)

    # Cerrar pestaña TikTok
    driver.close()

    # Volver a la pestaña principal
    driver.switch_to.window(main_tab)

    print("✅ TikTok inicializado (cookies guardadas)")

def metadatos_video(driver):
    
    resultado = {}
    try:
        likes = driver.find_element(
            By.XPATH,
            "//strong[@data-e2e='like-count']"
        ).text

        n_comentarios = driver.find_element(
            By.XPATH,
            "//strong[@data-e2e='comment-count']"
        ).text

        guardados = driver.find_element(
            By.XPATH,
            "//strong[@data-e2e='undefined-count']"
        ).text

        compartidos = driver.find_element(
            By.XPATH,
            "//strong[@data-e2e='share-count']"
        ).text

        descripcion_general = driver.find_element(
            By.XPATH,
            "//div[@data-e2e='video-desc']"
        ).text.strip()
    
    except:
        print("❌ Falló los metadatos")
        return resultado
    
    print("metadatos básicos hecho")
    try:
        hashtag = []
        hashtag_vector = driver.find_elements(
            By.XPATH,
            "//a[@data-e2e='search-common-link']"
        )

        for hastag_single in hashtag_vector:
            hashtag.append(hastag_single.text)

        print(hashtag)
    except NoSuchElementException:
        print("fallo hastag")
        hashtag = []

    try:
        titulo = driver.find_element(
            By.XPATH,
            "//div[@data-e2e='v2t-title']"
        ).text
    except NoSuchElementException:
        print("fallo titulo")
        titulo = ""

    try:
        descripcion_especifica = driver.find_element(
            By.XPATH,
            "//div[@data-e2e='v2t-desc']"
        ).text
    except NoSuchElementException:
        print("fallo descipcion general")
        descripcion_especifica = ""
    
    try:
        descripcion_especifica = driver.find_element(
            By.XPATH,
            "//div[@data-e2e='v2t-desc']"
        ).text
    except NoSuchElementException:
        print("fallo descripcion especifica")
        descripcion_especifica = ""

    try:
        keywords = driver.find_element(
            By.XPATH,
            "//div[@data-e2e='v2t-keywords']"
        ).text
    except NoSuchElementException:
        print("fallo keywords")
        keywords = ""

    
    resultado = {"likes":likes, "comentarios":n_comentarios, "guardados":guardados, "compartidos":compartidos, 
                    "descripcion general":descripcion_general, "hashtag": hashtag, "titulo":titulo, 
                    "descripcion especifica": descripcion_especifica, "keywords": keywords
                }

    return resultado

def obtener_url_usuario(driver):
    try:
        autor = driver.find_element(
            By.XPATH, "//a[@data-e2e='video-author-avatar']"
        )
        url = autor.get_attribute("href")
        return url
    except:
        print("❌ No se pudo obtener la URL del usuario")
        return None
    
def metadatos_perfil(driver):
    
    resultado = {}

    try:
        # 👤 Username (@)
        username = driver.find_element(
            By.XPATH, "//h1[@data-e2e='user-title']"
        ).text

        # 🧑 Nombre completo
        full_name = driver.find_element(
            By.XPATH, "//h2[@data-e2e='user-subtitle']"
        ).text

        # 📝 Bio
        bio = driver.find_element(
            By.XPATH, "//h2[@data-e2e='user-bio']"
        ).text

        # ➕ Siguiendo
        following = driver.find_element(
            By.XPATH, "//strong[@data-e2e='following-count']"
        ).text

        # 👥 Seguidores
        followers = driver.find_element(
            By.XPATH, "//strong[@data-e2e='followers-count']"
        ).text

        # ❤️ Likes totales
        likes_totales = driver.find_element(
            By.XPATH, "//strong[@data-e2e='likes-count']"
        ).text

        resultado = {"username":username, "full_name":full_name, "bio":bio, "following":following, "followers":followers, "likes_totales":likes_totales}

        #return resultado

    except Exception as e:
        print("❌ Error scrapeando usuario:", e)
        return None


    try:
        web_url = driver.find_element(
            By.XPATH, "//span[contains(@class, 'SpanLink')]"

        ).text

    except Exception as es:
        web_url = ""

    
    resultado["web_url"] = web_url
    
    return resultado

from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

def expandir_respuestas_comentario(elem):
    while True:
        try:
            boton = elem.find_element(
                By.XPATH,
                ".//button[contains(., 'respuestas') or contains(., 'Ver')]"
            )
            boton.click()
            time.sleep(1)  # espera a que carguen las respuestas
        except NoSuchElementException:
            break

def scroll_to_bottom_comentarios(driver):

    try:
        # Localiza el contenedor de comentarios
        #comments_container = driver.find_element(By.XPATH, "//*[contains(@class, 'DivCommentListContainer')]")
        comments_container = driver.find_element(By.XPATH, "//*[contains(@class, 'DivCommentMain')]")
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", comments_container)
        # Desplazar hacia abajo para cargar más comentarios
        time.sleep(3)  # Esperar un poco a que carguen más comentarios
    except NoSuchElementException:
        # Si no se encuentra el contenedor de comentarios, no hace nada
        print("Contenedor de comentarios no encontrado.")
        return

def normalizar_fechas(texto_fecha):
    """
    Convierte fechas tipo:
    - '2025-12-27'
    - 'Hace 1 día(s)'
    - 'Hace 6 día(s)'
    - 'Hace 42 min'
    
    a formato: YYYY-MM-DD
    """
    
    texto_fecha = texto_fecha.strip()
    hoy = datetime.today()

    # 1️⃣ Caso: ya viene como YYYY-MM-DD
    try:
        fecha = datetime.strptime(texto_fecha, "%Y-%m-%d")
        return fecha.strftime("%Y-%m-%d")
    except ValueError:
        pass

    # 2️⃣ Caso: Hace X día(s)
    match_dias = re.search(r"Hace\s+(\d+)\s*día", texto_fecha)
    if match_dias:
        dias = int(match_dias.group(1))
        fecha = hoy - timedelta(days=dias)
        return fecha.strftime("%Y-%m-%d")

    # 3️⃣ Caso: Hace X min / minutos / horas → hoy
    match_min = re.search(r"Hace\s+\d+\s*(min|hora)", texto_fecha)
    if match_min:
        return hoy.strftime("%Y-%m-%d")

    # 4️⃣ Fallback (por si aparece algo raro)
    return hoy.strftime("%Y-%m-%d")

def recopilar_respuestas(driver):
    all_data = []
    
    resputas_fin = False
    respuestas = []
    try:
        driver.find_element(By.XPATH, ".//*[contains(@class, 'DivViewMoreRepliesWrapper')]")
    except NoSuchElementException:
        resputas_fin = True

    while(resputas_fin == False):
        try:
            boton_respuesta = driver.find_element(By.XPATH, ".//*[contains(@class, 'DivViewRepliesContainer')]")
            if(boton_respuesta.text.find("Ver") != -1):
                boton_respuesta.click()
            elif(boton_respuesta.text.find("Ocultar") != -1):
                resputas_fin = True
            respuestas = driver.find_elements(By.XPATH, ".//div[contains(@class, 'DivCommentItemWrapper')]")
            time.sleep(2)

        except NoSuchElementException:
            print("Ocurrió una exceptción buscando respuesta.")

    print("Scrolleo los comentarios")     
    for respuesta in respuestas:
        datos = {}
        print("prueba")
        try:
            user = respuesta.find_element(
                By.XPATH,
                ".//a[@class='link-a11y-focus']"
            ).text
        except NoSuchElementException:
            user = ""
            #break

        # 📝 Texto del comentario
        try:
            texto = respuesta.find_element(
                By.XPATH,
                #".//span[contains(@data-e2e, 'comment-level-2')]"
                ".//span[@data-e2e='comment-level-2']"
            ).text
        except NoSuchElementException:
            texto = ""
            #break

        try:
            likes = respuesta.find_element(
                By.XPATH,
                ".//div[contains(@class, 'DivLikeContainer')]/span"
            ).text
        except NoSuchElementException:
            likes = ""

        try:
            fecha_publicacion = respuesta.find_element(
                By.XPATH,
                ".//div[contains(@class,'DivCommentSubContentWrapper')]/span[1]"
            ).text
            
            fecha_publicacion = normalizar_fechas(fecha_publicacion)
            
        except NoSuchElementException:
            print("Error: Fecha no encontrada!!!")
            fecha_publicacion = "9999-9-9"
        
        if(texto != ""):
            datos["user"]  = user
            datos["texto"] = texto
            datos["likes"] = likes
            datos["fecha"] = fecha_publicacion

            print(datos)

            all_data.append(datos)
    
    return all_data


def recopilar_comentarios(driver):
    all_comments = []
    salida = False
    size_comments = 0

    time.sleep(3)  # Esperar a que se cargue la página correctamente

    try:
        boton_comentario = driver.find_elements(
            By.XPATH,
            "//button[contains(@aria-label, 'comentarios')]"
        )

        if len(boton_comentario) > 0:
            boton_comentario[0].click()
        else:
            print("Botón de comentarios no encontrado.")
            return all_comments
    except Exception as e:
        print(f"No se encontró el botón de comentario: {e}")
        return all_comments

    # Realiza un scroll hacia abajo varias veces para cargar más comentarios (si es necesario)
    for _ in range(3):  # Hacer scroll 3 veces, puedes ajustar esto según necesites
        scroll_to_bottom_comentarios(driver)
    print("Scrolleando comentarios...")
    while(salida == False):
        # Obtener todos los comentarios
        scroll_to_bottom_comentarios(driver)
        
        comments = driver.find_elements(
            By.XPATH,
            #"//div[contains(@class, 'DivCommentItemWrapper')]"
            "//div[contains(@class, 'DivCommentObjectWrapper')]"
        )

        #print(f"💬 Comentarios encontrados: {len(comments)}")

        if(len(comments) == size_comments):
            salida = True
        else:
            size_comments = len(comments)
        
    print("- Comentarios leídos: " + str(size_comments))
    # Verificar que estamos recorriendo todos los comentarios
    for comment in comments:
        
        data = {}

        try:
            user = comment.find_element(
                By.XPATH,
                #".//span[contains(@data-e2e, 'comment-level-2')]"
                ".//a[@class='link-a11y-focus']"
            ).text
        except NoSuchElementException:
            user = ""

        # 📝 Texto del comentario
        try:
            texto = comment.find_element(
                By.XPATH,
                ".//span[contains(@class, 'StyledTUXText')]"
            ).text
        except NoSuchElementException:
            texto = ""

        # ❤️ Likes del comentario
        try:
            likes = comment.find_element(
                By.XPATH,
               # ".//div[contains(@class, 'css-bww7mr')]//span"
               ".//div[contains(@class, 'DivLikeContainer')]"
            ).text
        except NoSuchElementException:
            likes = "-1"

        # 💬 Número de respuestas
        try:
            respuestas_texto = comment.find_element(
                By.XPATH,
                ".//div[contains(@class, 'DivViewRepliesContainer')]//span"
            ).text
            
            # Extraer número (ej: "Ver 1822 respuestas")
            match = re.search(r'(\d+)', respuestas_texto)
            num_respuestas = match.group(1) if match else "0"
            
        except NoSuchElementException:
            num_respuestas = "0"

        # Fecha publicacion
        try:
            fecha_publicacion = comment.find_element(
                By.XPATH,
                ".//div[contains(@class,'DivCommentSubContentWrapper')]/span[1]"
            ).text
            
            fecha_publicacion = normalizar_fechas(fecha_publicacion)
            
        except NoSuchElementException:
            print("Error: Fecha no encontrada!!!")
            fecha_publicacion = "9999-9-9"

        data_respuestas = recopilar_respuestas(comment)
        #print("Datos de respuestas")
        
        #data_respuestas[0:2]
        data = {
            "user": user,
            "texto": texto,
            "likes": likes,
            "num_respuestas": num_respuestas,
            "fecha": fecha_publicacion,
            "respuestas": data_respuestas
        }

        print("comentarios--------------------")
        print(data)
        all_comments.append(data)

    return all_comments


def scrape_video(driver):

    resultado = []

    main_tab = driver.current_window_handle
    metadata_video = metadatos_video(driver)

    url_usuario = obtener_url_usuario(driver)

    if url_usuario:
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(url_usuario)
            time.sleep(3)
            detectar_recaptcha(driver)
            metadata_perfil = metadatos_perfil(driver)
            metadata_perfil["url_perfil"] = url_usuario

            driver.close()
            driver.switch_to.window(main_tab)
    
    print(metadata_video)
    print(metadata_perfil)

    comentarios = recopilar_comentarios(driver)
    print(comentarios[0:5])

    resultado.append(metadata_video)
    resultado.append(metadata_perfil)
    resultado.append(comentarios)

    return resultado

def guardar_datos(datos, archivo):
    """
    Guarda los datos en CSV en modo append (uno detrás de otro)
    """

    metadata_video = datos[0]
    metadata_perfil = datos[1]
    comentarios = datos[2]

    existe = os.path.isfile(archivo)

    with open(archivo, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Escribir cabecera solo si el archivo NO existe
        if not existe:
            writer.writerow([
                "video_titulo","video_likes", "video_comentarios", "video_guardados", "video_compartidos",
                "video_descripcion_general", "video_descripcion_especifica", "keywords","video_hashtags",
                "username", "followers", "likes_totales", "url_perfil",
                "comentario_user","contenido", "comentario_likes", "comentario_fecha",
                "num_respuestas", "respuesta_user","respuesta", "respuesta_likes", "respuesta_fecha"
            ])

        # Hashtags como string
        hashtags = ",".join(metadata_video.get("hashtag", []))

        for comentario in comentarios:
            # 🔹 Comentario principal
            writer.writerow([
                metadata_video.get("titulo", ""),
                metadata_video.get("likes", ""),
                metadata_video.get("comentarios", ""),
                metadata_video.get("guardados", ""),
                metadata_video.get("compartidos", ""),
                metadata_video.get("descripcion general", ""),
                metadata_video.get("descripcion especifica", ""),
                metadata_video.get("keywords", ""),
                hashtags,
                metadata_perfil.get("username", ""),
                metadata_perfil.get("followers", ""),
                metadata_perfil.get("likes_totales", ""),
                metadata_perfil.get("url_perfil", ""),
                comentario.get("user", ""),
                comentario.get("texto", ""),
                comentario.get("likes", ""),
                comentario.get("fecha", ""),
                "NO"
            ])

            # 🔹 Respuestas al comentario
            for r in comentario.get("respuestas", []):
                writer.writerow([
                    metadata_video.get("titulo", ""),
                    metadata_video.get("likes", ""),
                    metadata_video.get("comentarios", ""),
                    metadata_video.get("guardados", ""),
                    metadata_video.get("compartidos", ""),
                    metadata_video.get("descripcion general", ""),
                    metadata_video.get("descripcion especifica", ""),
                    metadata_video.get("keywords", ""),
                    hashtags,
                    metadata_perfil.get("username", ""),
                    metadata_perfil.get("followers", ""),
                    metadata_perfil.get("likes_totales", ""),
                    metadata_perfil.get("url_perfil", ""),
                    r.get("user", ""),
                    r.get("texto", ""),
                    r.get("likes", ""),
                    r.get("fecha", ""),
                    "SI"
                ])


def scrape_datos(driver, config, limit=10):
    '''
    Docstring for scrape_datos
    
    :param driver: driver
    :param config: config
    :param limit: Por lo general google devulve en cada pestaña una búsqueda con 10 resultados
    '''
    time.sleep(2)
    output_folder = Path(config.general["output_folder"])
    # 1️⃣ Obtener enlaces de los resultados de Google
    resultados = driver.find_elements(By.XPATH, "//a[h3]")

    urls = []
    for r in resultados:
        url = r.get_attribute("href")
        if url and "tiktok.com" in url:
            urls.append(url)

    urls = urls[0:limit-1]
    print(f"Se encontraron {len(urls)} URLs")

    main_tab = driver.current_window_handle
    
    inicializar_tiktok(driver)
    detectar_recaptcha(driver)
    time.sleep(2)
    #input("Prueba 1")
    # 2️⃣ Abrir cada URL en una nueva pestaña
    for url in urls:
        # Abrir nueva pestaña
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])

        driver.get(url)
        time.sleep(3)
        detectar_recaptcha(driver)
        detectar_login_tiktok(driver)
        detectar_intereses_tiktok(driver)
        detectar_accesoRapido_tiktok(driver)
        detectar_recaptcha_tiktok(driver)
        datos = scrape_video(driver)

        print("Guardando datos...")
        guardar_datos(datos, archivo=output_folder / "tiktok_global_dataset.csv")
        # 👉 AQUÍ puedes scrapear lo que quieras del TikTok
        # Ejemplo (solo como referencia):
        # titulo = driver.find_element(By.TAG_NAME, "title").text
        # print(titulo)
        
        # 3️⃣ Cerrar pestaña actual
        driver.close()
        time.sleep(3)

        # 4️⃣ Volver a Google
        driver.switch_to.window(main_tab)

def next_page_google(driver, actual_page):

    next_page_int = int(actual_page) + 1

    next_page = "Page "+str(next_page_int)

    try:
        print(next_page)
        boton_next = driver.find_element(By.XPATH, ".//a[@aria-label='"+next_page+"']")
        boton_next.click()
        
        return True
    except NoSuchElementException:
        print("No se encontraron más páginas")
        return False
    
def scrape_busqueda(driver, config):

    limit = 10
    max_busquedas = 200
    more_search = True
    n_search_actual = 0
    actual_page = 1

    while(more_search == True and n_search_actual < max_busquedas):
        time.sleep(2)
        len_search_actual = len(driver.find_elements(By.XPATH, "//a[h3]")) # Por lo genera, por pestaña suelen ser 10, pero a veces son 9 busquedas por pestaña
        #Se mira si el número de busquedas ya se pasará o no en la búsqueda
        if(n_search_actual + len_search_actual >= max_busquedas):
            more_search = False
            limit = max_busquedas - n_search_actual
            n_search_actual = max_busquedas
        else:
            limit = len_search_actual
            n_search_actual = n_search_actual + len_search_actual

        scrape_datos(driver, config, limit)
        
        if(next_page_google(driver, actual_page)):
            actual_page = actual_page + 1
        else:
            more_search = False


def scrape_tiktok(config):

    # Configuración básica
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    '''
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    '''
    driver = webdriver.Chrome(options=options)

    time.sleep(2)
    # 1️⃣ Ir a Google
    google(driver)
    time.sleep(2)
    detectar_recaptcha(driver)

    aceptar_cookies(driver)
    # 2️⃣ Buscar TikTo
    busqueda_google(driver, config)

    detectar_recaptcha(driver)

    time.sleep(3)

    scrape_busqueda(driver, config)
    
    #scrape_datos(driver, config)

    # ⚠️ NO cerrar si estás inspeccionando
    driver.quit()

# import config
# scrape_tiktok(config)