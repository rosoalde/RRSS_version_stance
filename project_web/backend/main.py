from fastapi import FastAPI  # 1. Traemos la "caja de herramientas"
app = FastAPI()              # 2. Sacamos la herramienta y la encendemos (Creamos la App)

@app.get("/") # 4. Definimos una ruta para la raíz del servidor
def root():
    return {"message": "Backend funcionando"} # 5. Definimos la función que manejará las solicitudes a la raíz. Cuando alguien entra, devolvemos un mensaje



# CONFIGURACIÓN BÁSICA DE SEGURIDAD
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext

SECRET_KEY = "CAMBIA_ESTO_EN_PRODUCCION"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


fake_users_db = {
    "admin@example.com": {
        "email": "admin@example.com",
        "hashed_password": pwd_context.hash("admin123"),
        "role": "admin",
    }
}

from fastapi import HTTPException
from datetime import datetime

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@app.post("/login")
def login(email: str, password: str):
    user = fake_users_db.get(email)
    if not user or not verify_password(password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    token = create_access_token({
        "sub": user["email"],
        "role": user["role"]
    })

    return {"access_token": token, "token_type": "bearer"}