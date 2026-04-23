import pandas as pd

FILE_USERS          = "users.csv"
FILE_PROYECTOS      = "proyectos.csv"
FILE_TIPOS_PERMISOS = "tipos_permisos.csv"
FILE_USERS_PERMISOS = "users_permisos.csv"


users = pd.read_csv(FILE_USERS)
users_permisos = pd.read_csv(FILE_USERS_PERMISOS)
tipos_permisos = pd.read_csv(FILE_TIPOS_PERMISOS)
proyectos = pd.read_csv(FILE_PROYECTOS)

def get_user_by_id(user_id):
    return users.loc[users["id"] == user_id].iloc[0]

def get_user_by_username(username):
    return users.loc[users["username"] == username].iloc[0]

def get_projects_by_user(user_id, only_active=True):
    df = proyectos.loc[proyectos["id_user"] == user_id]

    if only_active:
        df = df.loc[df["status"] == 1]

    return df

def get_user_permissions(user_id):
    permisos_ids = users_permisos.loc[
        users_permisos["id_user"] == user_id, "id_permiso"
    ]

    return tipos_permisos.loc[
        tipos_permisos["id_permiso"].isin(permisos_ids),
        "nombre"
    ].tolist()

def user_has_permission(user_id, permiso_nombre):
    permisos = get_user_permissions(user_id)
    return permiso_nombre in permisos

get_user_permissions(0)
# ['admin']

def add_user(username, nombre, apellidos, email, telefono):
    global users

    new_id = get_next_id(users, "id")

    new_user = {
        "id": new_id,
        "username": username,
        "nombre": nombre,
        "apellidos": apellidos,
        "email": email,
        "telefono": telefono
    }

    users = pd.concat([users, pd.DataFrame([new_user])], ignore_index=True)
    save_df(users, "users.csv")

    return new_id

def add_permission_to_user(user_id, permiso_nombre):
    global users_permisos

    permiso_id = tipos_permisos.loc[
        tipos_permisos["nombre"] == permiso_nombre,
        "id_permiso"
    ].iloc[0]

    exists = (
        (users_permisos["id_user"] == user_id) &
        (users_permisos["id_permiso"] == permiso_id)
    ).any()

    if exists:
        return False

    new_row = {
        "id_permiso": permiso_id,
        "id_user": user_id
    }

    users_permisos = pd.concat(
        [users_permisos, pd.DataFrame([new_row])],
        ignore_index=True
    )

    save_df(users_permisos, "users_permisos.csv")
    return True

def delete_user(user_id):
    global users, users_permisos, proyectos

    # eliminar usuario
    users = users.loc[users["id"] != user_id]

    # eliminar permisos
    users_permisos = users_permisos.loc[
        users_permisos["id_user"] != user_id
    ]

    # eliminar proyectos del usuario
    proyectos = proyectos.loc[
        proyectos["id_user"] != user_id
    ]

    save_df(users, "users.csv")
    save_df(users_permisos, "users_permisos.csv")
    save_df(proyectos, "proyectos.csv")

from datetime import datetime

def add_project(user_id, name_proyecto, url, status=1):
    global proyectos

    new_id = get_next_id(proyectos, "id_proyecto")

    new_project = {
        "id_proyecto": new_id,
        "id_user": user_id,
        "name_proyecto": name_proyecto,
        "url": url,
        "fecha": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "status": status
    }

    proyectos = pd.concat(
        [proyectos, pd.DataFrame([new_project])],
        ignore_index=True
    )

    save_df(proyectos, "proyectos.csv")
    return new_id


def delete_project(project_id):
    global proyectos

    proyectos = proyectos.loc[
        proyectos["id_proyecto"] != project_id
    ]

    save_df(proyectos, "proyectos.csv")

def deactivate_project(project_id):
    global proyectos

    proyectos.loc[
        proyectos["id_proyecto"] == project_id,
        "status"
    ] = 0

    save_df(proyectos, "proyectos.csv")


def save_df(df, filename):
    df.to_csv(filename, index=False)


df = pd.read_csv("datos.csv")

# ver las primeras filas
print(df.head())

# “queries”
df[df["edad"] > 30]
df[["nombre", "email"]]
