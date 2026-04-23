from celery_app import celery_app
from logica_FORMAT import backend_analisis
import os, json, csv
from pathlib import Path
from fastapi.responses import JSONResponse
import uuid
from bbdd.response.user_response import UserResponse
from aux_main.aux_main_general import aux_ejecutar_analisis

@celery_app.task
def ejecutar_analisis_task_pruebas(data: dict):
    """
    Este es el task que Celery ejecutará en segundo plano.
    """
    # 1. Preparar carpetas por usuario
    username = data.get("username")
    os.makedirs(f"files/{username}", exist_ok=True)

    # 2. Ejecutar la lógica pesada
    resultado = backend_analisis(data)
    real_analysis_id = resultado.get("analysis_id")

    # 3. Guardar CSV simple
    file_path = f"files/analisis_{real_analysis_id}.csv"
    os.makedirs("files", exist_ok=True)
    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Red", "Éxito"])
        for r in data.get("results", []):
            writer.writerow([r.get("social"), r.get("success")])

    # 4. Guardar dashboard_data.json si existe
    output_folder = resultado.get("output_folder")
    dashboard_data = {}
    if output_folder:
        dashboard_path = Path(output_folder) / "dashboard_data.json"
        if dashboard_path.exists():
            with open(dashboard_path, "r", encoding="utf-8") as f:
                dashboard_data = json.load(f)

    # 5. Retornar resultado final (Celery puede guardarlo en Redis si quieres)
    return {
        "analysis_id": real_analysis_id,
        "resultado": resultado,
        "dashboard": dashboard_data,
    }

@celery_app.task
def ejecutar_analisis_task(data: dict):
    print("Datos recibidos: ", data)

    # Creamos un ID temporal solo para el nombre del archivo CSV local de FastAPI (opcional)
    temp_id = str(uuid.uuid4())

    try:
        # 📁 Carpeta por usuario
        analysis_path = os.path.join("files", data.get("username"))
        os.makedirs(analysis_path, exist_ok=True)

        # 1. EJECUTAR LÓGICA (Aquí se crea el ID real y se guarda en analysis_db.json)
        resultado = backend_analisis(data)

        # 2. OBTENER EL ID REAL GENERADO POR LOGICA.PY
        real_analysis_id = resultado.get("analysis_id")
        print(real_analysis_id)
        if not real_analysis_id:
            raise Exception("El backend no devolvió un analysis_id válido.")

        # ===============================
        # 📊 Leer dashboard_data.json
        # ===============================
        output_folder = resultado.get("output_folder")
        dashboard_data = {}
        
        if output_folder:
            dashboard_path = Path(output_folder) / "dashboard_data.json"
            if dashboard_path.exists():
                with open(dashboard_path, "r", encoding="utf-8") as f:
                    dashboard_data = json.load(f)

        # Guardar CSV simple de registro (opcional)
        file_path = f"files/analisis_{real_analysis_id}.csv"
        os.makedirs("files", exist_ok=True)
        with open(file_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Red", "Éxito"])
            for r in data["results"]:
                writer.writerow([r["social"], r["success"]])

        # 3. RETORNAR EL ID REAL AL FRONTEND
        return JSONResponse({
            "status": "ok",
            "user_id": real_analysis_id,  # <--- ¡AQUÍ ESTÁ EL CAMBIO IMPORTANTE!
            "data": resultado,
            "dashboard": dashboard_data,
        })

    except Exception as e:
        print("Error ejecutando análisis:", e)
        # Importante imprimir el traceback completo si puedes
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)})


@celery_app.task
def scrapear_y_analizar(data: dict, user: UserResponse):
    return aux_ejecutar_analisis(data, user)

import time
@celery_app.task
def prueba_task():
    print("Esperando 10s...")
    time.sleep(10)
    print("Esperando 30s...")
    time.sleep(30)

    return "hola"
