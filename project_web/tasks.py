from celery_app import celery_app
from logica import backend_analisis
import os, json, csv
from pathlib import Path

@celery_app.task
def ejecutar_analisis_task(data: dict):
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