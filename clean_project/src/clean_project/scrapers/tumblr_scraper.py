import pytumblr
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import clean_project.config.settings as config  # Archivo externo donde guardamos credenciales y configuraciones

# Autenticación con OAuth
client = pytumblr.TumblrRestClient(
  config.CREDENTIALS["tumblr"]["CONSUMER_KEY"],
  config.CREDENTIALS["tumblr"]["CONSUMER_SECRET"],
  config.CREDENTIALS["tumblr"]["OAUTH_TOKEN"],
  config.CREDENTIALS["tumblr"]["OAUTH_SECRET"]
)

''' Esto solo sirve para buscar en un blog específico la api de Tumblr no permite buscar en toda la plataforma'''

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import csv

# Configuración del driver
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service)
driver.implicitly_wait(10)

# Palabras clave a buscar
keywords = ["v16 balizas", "baliza v16"]

# Lista para guardar resultados
data = []

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import csv

# -----------------------------
# Configuración
# -----------------------------
keywords = ["v16 balizas", "baliza v16"]
limit_scrolls = 5  # cuántas veces hacer scroll para cargar posts

# Lista para guardar resultados
data = []

# Configurar driver
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service)
driver.implicitly_wait(10)

try:
    driver.get("https://www.tumblr.com/explore/trending")
    time.sleep(3)

    # -----------------------------
    # Eliminar cualquier overlay o banner que bloquee la página
    # -----------------------------
    driver.execute_script("""
    var overlays = document.querySelectorAll('div');
    for (var i=0; i<overlays.length; i++){
        var style = window.getComputedStyle(overlays[i]);
        if (style.position === 'fixed' && style.zIndex >= 1000){
            overlays[i].remove();
        }
    }
    """)
    time.sleep(1)

    for keyword in keywords:
        # Buscar input de búsqueda
        search_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@aria-label='Buscar' and @type='text']"))
        )

        # Hacer click y escribir keyword
        driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", search_input)
        search_input.clear()
        search_input.send_keys(keyword + "\n")
        time.sleep(3)  # esperar resultados

        # Scroll para cargar más posts
        for _ in range(limit_scrolls):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        # Extraer solo texto de los posts
        posts = driver.find_elements(By.XPATH, "//article//p")
        for post in posts:
            texto = post.text.strip()
            print(texto)
            if texto:
                data.append({
                    "keyword": keyword,
                    "contenido": texto
                })

    # -----------------------------
    # Guardar resultados en CSV (opcional)
    # -----------------------------
    # with open("tumblr_posts.csv", "w", newline="", encoding="utf-8") as f:
    #     writer = csv.DictWriter(f, fieldnames=["keyword", "contenido"])
    #     writer.writeheader()
    #     writer.writerows(data)

    # print(f"✅ Total posts extraídos: {len(data)}")

finally:
    driver.quit()
