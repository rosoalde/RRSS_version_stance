from pathlib import Path
import base64
import pandas as pd
from io import BytesIO
import sys




from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent

# Apuntamos a la carpeta "src"
SRC_PATH = ROOT_DIR / "clean_project" / "src"

# Añadir al sys.path
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
    print(f"✅ SRC añadido a sys.path: {SRC_PATH}")

from clean_project.analysis.nube import generar_nubes_dashboard

BASE_PATH = Path(r"C:\Users\DATS004\Romina.albornoz Dropbox\Romina Albornoz\14. DS4M - Social Media Research\git\project_web\Web_Proyecto\datos\admin")

for carpeta in BASE_PATH.glob("*"):
    if carpeta.is_dir():
        csv_path = carpeta / "datos_sentimiento_filtrados.csv"
        
        if csv_path.exists():
            print(f"🔄 Procesando: {carpeta.name}")
            
            nubes_dict = generar_nubes_dashboard(csv_path)

            for nombre, b64_str in nubes_dict.items():
                if b64_str:
                    with open(carpeta / f"{nombre}.png", "wb") as f:
                        f.write(base64.b64decode(b64_str))

            print(f"✅ {len(nubes_dict)} imágenes generadas en {carpeta.name}")
