
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime, timedelta, timezone
from typing import Optional
import os
from bbdd.querys.general_querys import obtener_usuario_bbdd, verificar_user_bbdd
from bbdd.response.user_response import UserResponse

##
#
#   Pipeline: Usuario no logueado -> es redirigido a loguearse -> main.js completa formulario logueo ->
#               main_FORMAT.login lo recoge -> aux_main.login_user lo recoge y verifica y el user -> bbdd
#               bbdd devuelve el user -> aux_main.login_user crea token y devuelve datos de user ->
#               main_FORMAT.login    devuelve token y datos user -> main.js guarda en cookies el token + user
#
##


ALGORITHM = "HS256"
SECRET_KEY = "ServidorEncriptandoUwU"
#SECRET_KEY =  os.getenv("SECRET_KEY")  #Poner este linea en lugar de la otra. La contraseña estará más segura
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)


'''
Esta función es para crear un token de usuario al loguear un usuario.
Este token es devuelto al frontend del usuario, y lo usará como DNI para identificarse al backend
'''
def create_access_token(user_id: int):
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def aux_login_post(username:str, password:str):
    #Si existe, debe devolver el id del user; sino nada
    user_exist = verificar_user_bbdd(username, password)
    
    if not user_exist:
        return None

    user = obtener_usuario_bbdd(user_exist)

    token = create_access_token(user.id)

    return token
    '''
    return {
        "access_token": token,
        "token_type": "bearer",        
    }
    '''
'''    return {
        "access_token": token,
        "token_type": "bearer",
            "user": {
                    "id": user.id,
                    "username": user.username,
                    "nombre": user.nombre,
                    "apellidos": user.apellidos,
                    "telefono": user.telefono,
                    "email": user.email
                    }
    }'''

def get_current_user(request: Request) -> UserResponse:
    token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token Inválido")

    user = obtener_usuario_bbdd(user_id)

    if not user:
        raise HTTPException(401, "Usuario no encontrado")

    return user

def get_current_user_optional(request: Request) -> Optional[UserResponse]:

    token = request.cookies.get("access_token")

    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except JWTError:
        return None

    user = obtener_usuario_bbdd(user_id)
    return user




def get_current_user_oauth2(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(401, "Token inválido")

    user = obtener_usuario_bbdd(user_id)

    if not user:
        raise HTTPException(401, "Usuario no encontrado")

    return user



def get_current_user_optional_oauth2(token: str = Depends(oauth2_scheme)) -> Optional[UserResponse]:

    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except JWTError:
        return None

    user = obtener_usuario_bbdd(user_id)
    return user


