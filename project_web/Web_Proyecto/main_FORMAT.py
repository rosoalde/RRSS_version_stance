from jose import jwt
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Response, Form, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from typing import Optional, List
#from aux_main.aux_main_general import get_analyses_for_user
from jose import JWTError


from bbdd.response.user_response import UserResponse

from aux_main.aux_main_login import get_current_user_optional, get_current_user, aux_login_post
from aux_main.aux_main_general import aux_mis_analisis, aux_analysis_by_id, aux_filter_analysis_geo, aux_dashboard_data, aux_run_aceptacion, aux_filter_aceptacion_geo, aux_download_aceptacion_txt, aux_download_analysis, aux_generate_keywords
from aux_main.classes_main import FilterRequest
from bbdd.database import Base

###################################
#   Se crea este main para estructurar los datos, poner seguridad y evitar complejidad y bugs
#
#   El formato que se seguirá será el siguiente:
#   1) Todas las librerías deberán estar ARRIBA (al principio de la pagina)
#   2) Las funciones deberán funcionar de la siguiente manera:
#           @app....
#           def my_function(user, params)
#               verificar_user(user)
#               verificar_
#       
#       El objetivo es que en el code se haga lo siguiente:
#           1) La validación por token
#           2) La lógica se desarrollará en la carpeta "aux_main"
#           3) Cosas muy básica y sencillas +  Redirección  
###################################

templates = Jinja2Templates(directory="templates")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

########################################################################
#  Funciones      
########################################################################

# El usuario en la bbdd podrá disponer de varios roles
# Pero para web solo dispondrá de uno en concreto.
# Y será en subcripciones donde el usuario cambie de rol


##                  
#                    INICIALIZAMOS EL DATASET
##



def require_roles(allowed_roles: List[str]):
    def dependency(current_user: UserResponse = Depends(get_current_user)):
        if(current_user.role not in allowed_roles):
            raise HTTPException(403, "No tienes permisos suficientes")
        return current_user
    return Depends(dependency)

'''
    Obejtivo: Redireccionamos por defecto al usuario al portal login si no está logueado
                si está logueado, entonces lo redireccionamos a "analisis"
'''
@app.get("/")
def root(current_user: UserResponse | None = Depends(get_current_user_optional)):

    if not current_user:
        return RedirectResponse(url="/login", status_code=302)      # No logueado → login

    return RedirectResponse(url="/analisis", status_code=302)       # Logueado → análisis      

'''
    Objetivo: Redireccionamos el login a analisis si el usuario ya está logueado
                pero se quiere ir al portal login
'''
@app.get("/login")
def login(request: Request, current_user: UserResponse | None = Depends(get_current_user_optional)):

    if not current_user:            # No logueado → login
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": None
            }
        )      

    return RedirectResponse(url="/analisis", status_code=302)       # Logueado → análisis 

@app.post("/login")
def login_post(request: Request, response: Response, username: str = Form(...), password: str = Form(...)):

    token_user = aux_login_post(username, password)

    if not token_user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Usuario o contraseña incorrectos"
            }
        )

    response.set_cookie(
        key="access_token",
        value=token_user,
        httponly=True,
        samesite="lax",
        secure=False  # True si usas HTTPS
    )

    return {"message": "Login correcto"}


@app.post("/logout")
def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=302)
    # Borrar cookie del token
    response.delete_cookie(key="access_token")
    return response

##########################
# index.html
##########################
from tasks import scrapear_y_analizar
@app.post("/ejecutar-analisis") # 2
async def ejecutar_analisis(request: Request, current_user: UserResponse = require_roles(["analista", "admin"])):
    data = await request.json()
    #tarea = scrapear_y_analizar.apply_async(data, current_user)

    from aux_main.aux_main_general import aux_ejecutar_analisis
    tarea = await aux_ejecutar_analisis(data, current_user)

    return tarea

@app.post("/generate_keywords")
async def generate_keywords(request: Request, current_user: UserResponse = require_roles(["analista", "admin"])):
    data = await request.json()

    keywords = aux_generate_keywords(data)
    keywords = ["ayuda", "pruebas", "balizav16", "ayuda", "pruebas", "balizav16","ayuda", "pruebas", "balizav16","ayuda", "pruebas", "balizav16"]

    return JSONResponse({"success": True, "keywords": keywords})

##########################
# index.html
##########################
@app.get("/analisis")
def home(request: Request, current_user: UserResponse = Depends(get_current_user)):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "resultado": None, "user":current_user}
    )

@app.get("/analisis/{analysis_id}")
def view_analysis(request: Request, analysis_id: str, current_user: UserResponse = Depends(get_current_user)):
    analyses = aux_analysis_by_id(analysis_id, current_user)

    return templates.TemplateResponse(
        "analysis_dashboard.html",
        {
            "request": request,
            "user": current_user,
            "analysis": analyses
        }
    )

@app.get("/analisis/{analysis_id}/download")
async def download_analysis(analysis_id: str, current_user: UserResponse = require_roles(["analista", "admin"])):
    zip_buffer = await aux_download_analysis(analysis_id, current_user)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=resultados_{analysis_id}.zip"}
    )

@app.get("/analisis/{analysis_id}/dashboard")
def get_dashboard_data(request: Request, analysis_id: str, current_user: UserResponse = Depends(get_current_user)):
    return aux_dashboard_data(analysis_id)


@app.post("/analisis/{analysis_id}/filter-geo")
def filter_analysis_geo(request: Request, analysis_id: str, payload: FilterRequest, current_user: UserResponse = Depends(get_current_user)):
    
    return aux_filter_analysis_geo(analysis_id, payload)

@app.post("/analisis/{analysis_id}/aceptacion")
async def run_aceptacion(request: Request, analysis_id: str, current_user: UserResponse = Depends(get_current_user)):
    try:
        result = await aux_run_aceptacion(analysis_id, current_user)

        return JSONResponse(
            content=jsonable_encoder(result)
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))   

@app.post("/analisis/{analysis_id}/aceptacion/filter-geo")
def filter_aceptacion_geo(request: Request, analysis_id: str, payload: FilterRequest, current_user: UserResponse = Depends(get_current_user)):
    
    results = aux_filter_aceptacion_geo(analysis_id, payload, current_user)

    return results

@app.get("/analisis/{analysis_id}/aceptacion/download-txt")
async def download_aceptacion_txt(request: Request, analysis_id: str, current_user: UserResponse = Depends(get_current_user)):
    
    txt_path = await aux_download_aceptacion_txt(analysis_id, current_user)

    # 4. Devolver el archivo para descarga
    return FileResponse(
        path=txt_path, 
        filename=f"informe_aceptacion_{analysis_id}.txt",
        media_type="text/plain"
    )

@app.get("/mis-analisis")
def mis_analisis(request: Request, current_user: UserResponse = Depends(get_current_user)):

    analyses = aux_mis_analisis(current_user)

    return templates.TemplateResponse(
        "mis_analisis.html",
        {
            "request": request,
            "analyses": analyses,
            "user": current_user
        }
    )


@app.get("/analizar-datasets")
def analizar_datasets(request: Request, current_user: UserResponse = Depends(get_current_user)):

    analyses = aux_mis_analisis(current_user)

    return templates.TemplateResponse(
        "analizar_datasets.html",
        {
            "request": request,
            "user": current_user,
            "analyses": analyses
        }
    )

@app.get("/configuracion")
def mis_analisis(request: Request, current_user: UserResponse = Depends(get_current_user)):

    return templates.TemplateResponse(
        "ajustes.html",
        {
            "request": request,
            "user": current_user
        }
    )


@app.get("/suscripciones")
def mis_analisis(request: Request, current_user: UserResponse = Depends(get_current_user)):

    return templates.TemplateResponse(
        "suscripciones.html",
        {
            "request": request,
            "user": current_user
        }
    )
