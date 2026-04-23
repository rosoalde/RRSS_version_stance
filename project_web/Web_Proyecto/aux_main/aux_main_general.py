from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from jose import jwt, JWTError
from temp_json import sync_analysis_db
from pathlib import Path
from datetime import datetime
from bbdd.response.user_response import UserResponse
import json
from logica_FORMAT import recalcular_filas_incompletas, backend_analisis, generar_keywords_con_ia, calcular_dashboard_base
from logica_FORMAT import ejecutar_indicador_aceptacion, asegurar_nubes_dashboard, recalcular_aceptacion_filtrada
import pandas as pd
import base64
from .classes_main import FilterRequest
import os
import asyncio
import math

import io, zipfile
import csv


BASE_DIR = "../"
def aux_mis_analisis(user: UserResponse):


    ANALYSIS_DB = Path("../analysis_db.json").resolve()
    print("Syncing DB en:", ANALYSIS_DB)

    # 🔄 Sync automático inteligente (solo agrega nuevos)
    db = sync_analysis_db()

    # Si no hay datos, devolver lista vacía
    if not db:
        return []

    user_analyses = []

    for a in db:
        if a.get("username") != user.username:
            continue

        # Saltar eliminados
        if a.get("status") == "deleted":
            continue

        created_raw = a.get("created_at")
        try:
            created_dt = datetime.fromisoformat(created_raw)
            created_str = created_dt.strftime("%d-%m-%Y %H:%M")
        except:
            created_dt = datetime.min
            created_str = "Fecha desconocida"

        folder_name = Path(a.get("output_folder")).name if a.get("output_folder") else a.get("project_name")

        user_analyses.append({
            "id": a.get("id"),
            "project_name": folder_name,
            "created_at": created_str,
            "order_by": created_dt,
            "status": a.get("status", "completed"),
            "progress": 100 if a.get("status") == "completed" else 0,
            "download_url": f"/analisis/{a.get('id')}/download"
        })

    # Ordenar más nuevos primero
    return sorted(user_analyses, key=lambda x: x["order_by"], reverse=True)



def aux_analysis_by_id(analysis_id: str, user: UserResponse):
    ANALYSIS_DB = Path("../analysis_db.json").resolve()

    if not ANALYSIS_DB.exists():
        raise HTTPException(status_code=404, detail="No hay análisis guardados")

    db = json.loads(ANALYSIS_DB.read_text())

    analysis = next(
        (a for a in db 
         if a.get("id") == analysis_id 
         and a.get("username") == user.username),
        None
    )

    if not analysis:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")

    return analysis


def aux_dashboard_data(analysis_id: str):
    """
    Lee el dashboard. Si detecta formato antiguo o error, regenera desde el CSV
    manejando correctamente el separador (; o ,).
    """
    # 1. Buscar en la "Base de Datos"
    ANALYSIS_DB = Path("analysis_db.json").resolve()
    if not ANALYSIS_DB.exists():
        return JSONResponse({"error": "Base de datos no encontrada"}, status_code=404)

    try:
        db = json.loads(ANALYSIS_DB.read_text(encoding="utf-8"))
    except Exception as e:
        return JSONResponse({"error": f"Error leyendo DB: {str(e)}"}, status_code=500)
    
    analysis = next((a for a in db if a["id"] == analysis_id), None)
    if not analysis:
        return JSONResponse({"error": "Análisis no encontrado"}, status_code=404)

    # LÓGICA DE RUTA ROBUSTA
    folder_raw = Path(analysis["output_folder"])
    if folder_raw.is_absolute():
        folder = folder_raw  # Soporte legado (JSONs viejos)
    else:
        folder = (BASE_DIR / folder_raw).resolve() # La forma correcta para Linux/Win
        folder = folder_raw
    # ============================================================
# 🔥 ASEGURAR QUE LAS NUBES EXISTEN (Lazy Generation)
# ============================================================
    try:
        asegurar_nubes_dashboard(folder)
    except Exception as e:
        print(f"⚠️ Error asegurando nubes: {e}")
    json_path = folder / "dashboard_data.json"
    
    # Buscamos el CSV
    csv_path = folder / "datos_sentimiento_filtrados.csv"
    if not csv_path.exists():
        csv_path = folder / "tiktok_global_dataset.csv"

    data = {}
    regenerar = False

    # 2. Intentar leer JSON existente
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            # Si falta la clave "kpis", es viejo.
            if "kpis" not in data:
                print(f"⚠️ JSON antiguo detectado en {analysis_id}. Regenerando...")
                regenerar = True
        except Exception as e:
            print(f"⚠️ Error leyendo JSON: {e}")
            regenerar = True
    else:
        regenerar = True

    # 3. REGENERACIÓN AUTOMÁTICA
    if regenerar:
        if csv_path.exists():
            try:
                print(f"🔄 Recalculando dashboard desde: {csv_path.name}")
                
                # --- CORRECCIÓN DEL SEPARADOR ---
                try:

                    print(f"\n=== Analizando {csv_path.name} ===")
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        primera_linea = f.readline()
                        sep = ';' if ';' in primera_linea else ','

                    df = pd.read_csv(csv_path, sep=sep, encoding='utf-8', engine='python', on_bad_lines='skip')    

                except:
                    print(f"❌ Error leyendo CSV con pandas. Intentando lectura manual para detectar problemas.")

                    

                # Normalizar nombres (Mapeo seguro)
                # Tu CSV ya tiene mayúsculas, pero por si acaso mapeamos las minúsculas
                col_map = {
                    "titulo": "TITULO", "comentario_texto": "CONTENIDO", 
                    "cuerpo": "CUERPO", "fuente": "FUENTE", 
                    "fecha": "FECHA", "sentimiento": "SENTIMIENTO",
                    "topic": "TOPIC", "likes": "LIKES", 
                    "comments": "COMMENTS", "shares": "SHARES", 
                    "followers": "FOLLOWERS"
                }
                df.rename(columns=col_map, inplace=True)

                # Limpieza de Textos
                cols_str = ["TITULO", "CUERPO", "CONTENIDO", "TOPIC", "FUENTE", "ID"]
                for c in cols_str:
                    if c in df.columns: df[c] = df[c].fillna("").astype(str)
                
                # Limpieza de Métricas (Tus nuevos campos)
                cols_num = ["LIKES", "COMMENTS", "SHARES", "FOLLOWERS", "VIEWS"]
                for c in cols_num:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
                    else:
                        df[c] = 0 # Si no existe, rellenamos con 0

                # Limpieza Sentimiento
                if "SENTIMIENTO" in df.columns:
                    df["SENTIMIENTO"] = pd.to_numeric(df["SENTIMIENTO"], errors='coerce').fillna(0).astype(int)

                # 🔥 CALCULAR ESTRUCTURA NUEVA
                df = recalcular_filas_incompletas(df)
                data = calcular_dashboard_base(df)
                
                # Agregar raw_data
                data["raw_data"] = df.fillna("").to_dict(orient="records")
                
                # Recalcular Topics
                if "TOPIC" in df.columns:
                    df["TOPIC"] = (
                        df["TOPIC"]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                        .str.lower()
                    )
                    topics = (
                        df.groupby("TOPIC")
                        .agg(
                            volumen=("TOPIC", "count"),
                            sentimiento_prom=("SENTIMIENTO", "mean")
                        )
                        .reset_index()
                        .to_dict(orient="records")
                    )
                    data["topics"] = topics
                else:
                    data["topics"] = []

                # 💾 GUARDAR EL JSON NUEVO
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, default=str)
                
                print("✅ Dashboard regenerado correctamente.")

            except Exception as e:
                print(f"❌ Error fatal regenerando dashboard: {e}")
                import traceback
                traceback.print_exc()
                data = {}
        else:
            data = {}

    # 4. Cargar imágenes
    data["nubes"] = {}
    for img_file in folder.glob("nube_*.png"):
        try:
            with open(img_file, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                data["nubes"][img_file.stem] = encoded_string
        except Exception:
            pass

    return JSONResponse(data)




def aux_filter_analysis_geo(analysis_id: str, payload: FilterRequest):
    
    """
    Recibe términos geográficos Y/O un topic personalizado.
    """
    print(f"📍 Petición de filtro para {analysis_id}. Geo: {payload.terms}, Topic: {payload.custom_topic}")

    # 1. Buscar ruta del análisis
    ANALYSIS_DB = Path("analysis_db.json").resolve()
    if not ANALYSIS_DB.exists():
        raise HTTPException(status_code=404, detail="Base de datos no encontrada")

    db = json.loads(ANALYSIS_DB.read_text(encoding="utf-8"))
    analysis = next((a for a in db if a["id"] == analysis_id), None)

    if not analysis:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")

    # LÓGICA DE RUTA ROBUSTA
    folder_raw = Path(analysis["output_folder"])
    if folder_raw.is_absolute():
        output_folder = folder_raw  # Soporte legado (JSONs viejos)
    else:
        output_folder = (BASE_DIR / folder_raw).resolve() # La forma correcta para Linux/Win
        output_folder = folder_raw
    
    # Buscar CSV fuente
    csv_path = output_folder / "datos_sentimiento_filtrados.csv"
    if not csv_path.exists():
        csv_path = output_folder / "tiktok_global_dataset.csv" 
        if not csv_path.exists():
             raise HTTPException(status_code=404, detail="Archivo de datos (CSV) no encontrado")

    try:
        from logica_FORMAT import filtrar_y_recalcular_dashboard
        
        # Ejecutar lógica con AMBOS parámetros
        new_dashboard_data = filtrar_y_recalcular_dashboard(
            csv_path=csv_path,
            output_folder=output_folder,
            terminos_geo=payload.terms,
            custom_topic=payload.custom_topic # <--- NUEVO PARÁMETRO
        )
        
        return JSONResponse(content=jsonable_encoder(new_dashboard_data))

    except Exception as e:
        print(f"❌ Error en filtro avanzado: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


async def aux_run_aceptacion(analysis_id: str, user: UserResponse):
    if user.role == "user":
            filename = f"datos/user/user_{analysis_id}.json"

            if not os.path.exists(filename):
                raise HTTPException(
                    status_code=404,
                    detail=f"No existe el archivo {filename}"
                )

            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)

            return {
                "ok": True,
                **data
            }

    result = await asyncio.to_thread(
        ejecutar_indicador_aceptacion,
        analysis_id,
        user
    )

    return {
        "ok": True,
        **result
    }



def aux_filter_aceptacion_geo(analysis_id: str, payload: FilterRequest, current_user: UserResponse):
    
    result = recalcular_aceptacion_filtrada(
        analysis_id=analysis_id,
        user=current_user,
        terminos_geo=payload.terms
    )
    result = clean_nans(result)
    
    return JSONResponse(content=jsonable_encoder(result))


def clean_nans(obj):
    if isinstance(obj, dict):
        return {k: clean_nans(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nans(v) for v in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return 0
    else:
        return obj
    


async def aux_download_aceptacion_txt(analysis_id: str):

    ANALYSIS_DB = Path("analysis_db.json").resolve()

    if not ANALYSIS_DB.exists():
        raise HTTPException(status_code=404, detail="Base de datos no encontrada")

    db = json.loads(ANALYSIS_DB.read_text(encoding="utf-8"))

    analysis = next((a for a in db if a["id"] == analysis_id), None)

    if not analysis:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")

    folder_raw = Path(analysis["output_folder"])

    if folder_raw.is_absolute():
        output_folder = folder_raw
    else:
        output_folder = (BASE_DIR / folder_raw).resolve()
        output_folder = folder_raw

    txt_path = output_folder / "aceptacion_global.txt"

    if not txt_path.exists():
        raise HTTPException(
            status_code=404,
            detail="El informe TXT aún no ha sido generado."
        )

    return txt_path




async def aux_download_analysis(analysis_id: str, user: UserResponse):
    ANALYSIS_DB = Path("analysis_db.json").resolve()

    if not ANALYSIS_DB.exists():
        raise HTTPException(status_code=404, detail="No hay análisis guardados")

    db = json.loads(ANALYSIS_DB.read_text(encoding="utf-8"))

    analysis = next((a for a in db if a["id"] == analysis_id), None)
    if not analysis:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")

    # Validación de permisos
    if user.role != "admin" and analysis["username"] != user.username:
        raise HTTPException(status_code=403, detail="No autorizado")

    project_name = analysis.get("project_name", f"proyecto_{analysis_id}").replace(" ", "_")

    folder_raw = Path(analysis["output_folder"])
    if folder_raw.is_absolute():
        folder = folder_raw
    else:
        folder = (BASE_DIR / folder_raw).resolve()

    folder = folder_raw
    print(folder_raw)
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Carpeta de resultados no existe")

    # Creamos ZIP en memoria
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        # 1️⃣ Archivos permitidos
        for file in folder.iterdir():
            if not file.is_file():
                continue

            if (
                file.name == "reporte_analisis.xlsx"
                or file.name.endswith("datos_con_pilares.csv")
                or file.name.endswith("datos_sentimiento_filtrados.csv") 
                or file.name.endswith("_global_dataset.csv")
                or file.name.endswith("datos_combinados.csv")
            ):
                arcname = f"{project_name}/{file.name}"
                zipf.write(file, arcname=arcname)

        # 2️⃣ Crear TXT informativo
        # Población objetivo:
        # {analysis.get("population_scope", "No especificado")}
        info_text = f"""
        INFORMACIÓN DEL ANÁLISIS
        ------------------------

        Proyecto: {analysis.get("project_name")}
        ID: {analysis.get("id")}
        Usuario: {analysis.get("username")}

        Tema:
        {analysis.get("tema", "No disponible")}

        Keywords:
        {analysis.get("keywords", "No disponible")}

        Fuentes:
        {", ".join(analysis.get("sources", []))}

        Idiomas:
        {", ".join(analysis.get("languages", []))}

        Fecha inicio búsqueda:
        {analysis.get("start_date", "No disponible")}

        Fecha fin búsqueda:
        {analysis.get("end_date", "No disponible")}

        Fecha creación análisis:
        {analysis.get("created_at")}
        """
        zipf.writestr(f"{project_name}/info_busqueda.txt", info_text.strip())

    buffer.seek(0)
    return buffer



def aux_generate_keywords(data: dict) -> list[str]:

    context = data.get("context", "")
    languages = data.get("languages", [])
    population = data.get("population", "")

    # Aquí llamamos a tu función que hace la IA
    keywords = generar_keywords_con_ia(context, languages, population)
    
    return keywords


def crear_tarea_dataset():
    pass


async def aux_ejecutar_analisis(data: dict, user: UserResponse):


    try:
        # 📁 Carpeta por usuario
        analysis_path = os.path.join("files", user.username)
        os.makedirs(analysis_path, exist_ok=True)
        
        data["username"] = user.username
        data["role"] = user.role

        # 1. EJECUTAR LÓGICA (Aquí se crea el ID real y se guarda en analysis_db.json)
        resultado = backend_analisis(data)
        print("RESULTADO BACKEND:", resultado)

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
