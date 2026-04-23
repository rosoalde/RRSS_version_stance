import csv
from bbdd.response.user_response import UserResponse

##simulamos bbdd

def get_users():
    users = []
    with open("static/bbdd/bbdd_acceso.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            users.append(row)
    return users

def get_user_by_id(user_id: str):
    users = get_users()
    return next((u for u in users if u["user_id"] == str(user_id)), None)

def obtener_usuario_bbdd(user_id:str) -> UserResponse:
    user = get_user_by_id(user_id=user_id)

    return UserResponse(
        id=int(user["user_id"]),
        username=user["username"],
        email=user["email"],
        phone=user["phone"],
        first_name=user["first_name"],
        last_name=user["last_name"],
        role=user["role"]
    )

def verificar_user_bbdd(username: str, password: str) -> UserResponse | None:
    users = get_users()

    for user in users:
        if user["username"] == username and user["password"] == password:
            return user["user_id"]

    return None
