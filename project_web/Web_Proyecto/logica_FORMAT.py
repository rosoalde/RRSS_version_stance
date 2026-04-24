import psycopg2

def get_db():
    return psycopg2.connect(
        host="localhost",
        database="tu_db",
        user="tu_user",
        password="tu_password"
    )


import psycopg2

def get_db():
    return psycopg2.connect(
        host="localhost",
        database="tu_db",
        user="tu_user",
        password="tu_password"
    )


from datetime import datetime

def save_job(conn, job):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO analysis_jobs (id, status, progress, created_at)
            VALUES (%s, %s, %s, NOW())
        """, (job["id"], job["status"], job["progress"]))
    conn.commit()


def update_job(conn, job_id, **fields):
    set_clause = ", ".join([f"{k} = %s" for k in fields.keys()])
    values = list(fields.values())

    query = f"""
        UPDATE analysis_jobs
        SET {set_clause}, updated_at = NOW()
        WHERE id = %s
    """

    with conn.cursor() as cur:
        cur.execute(query, values + [job_id])

    conn.commit()

from celery_app import celery_app
#from db.jobs import update_job, get_db
from datetime import datetime

@celery_app.task(bind=True)
def run_analysis_task(self, data, job_id):

    conn = get_db()

    try:
        update_job(conn, job_id,
                   status="running",
                   started_at=datetime.now(),
                   step="Inicializando")

        result = backend_analisis_core(data, job_id, conn)

        update_job(conn, job_id,
                   status="completed",
                   progress=100,
                   finished_at=datetime.now(),
                   step="Finalizado")

        return result

    except Exception as e:
        update_job(conn, job_id,
                   status="failed",
                   error=str(e),
                   finished_at=datetime.now())

        raise
    finally:
        conn.close()
'''
update_job(conn, job_id, progress=10, step="Configuración")

update_job(conn, job_id, progress=30, step="Scraping redes")

update_job(conn, job_id, progress=60, step="LLM análisis")

update_job(conn, job_id, progress=80, step="Generando dashboard")

update_job(conn, job_id, progress=95, step="Nubes de palabras")
'''

import uuid

def start_analysis(request):

    conn = get_db()

    job_id = str(uuid.uuid4())

    save_job(conn, {
        "id": job_id,
        "status": "pending",
        "progress": 0
    })

    run_analysis_task.delay(request.json, job_id)

    conn.close()

    return {"job_id": job_id}


def get_status(job_id):

    conn = get_db()

    with conn.cursor() as cur:
        cur.execute("SELECT status, progress, step, error FROM analysis_jobs WHERE id = %s", (job_id,))
        row = cur.fetchone()

    conn.close()

    return {
        "status": row[0],
        "progress": row[1],
        "step": row[2],
        "error": row[3]
    }

#conn = get_db()

####################################################################
####################################################################
####################################################################
####################################################################

def crear_tarea_bbdd(tipo_tarea, tarea_id, user_id):
    pass

def backend_analisis():
    pass

def generar_keywords_con_ia():
    pass

def recalcular_filas_incompletas():
    pass

def calcular_dashboard_base():
    pass


def ejecutar_indicador_aceptacion():
    pass

def asegurar_nubes_dashboard():
    pass

def recalcular_aceptacion_filtrada():
    pass

