Loguin:
    1)No hay usuario
    -> frontend formulario (user, password) -> main.js (...)-> main.py (def login(..)) -> aux_main_login.py (login) -> bbdd (verifica_user) -> bbdd (obtiene user)
    #usuario cacheado en el backend
    #ahora le devolvemos el token del usuario frontend
    aux_main_login.py (login) [crea token con los datos usuario] -> main.py (def login) -> main.js -> frontend user

    2) Hay usuario #el usuario ya recibió el token, el cual lo guarda en el header
    -> frontend (token, parametros) -> main.js -> main.py -> aux_main_login.py (get_current_user) -> [confirma token] -> devuelve user de bbdd con el id del token del usuario 


Celerys:
    1) Sería bueno poner recursos fijos para las peticiones de clientes
        - Con esto siempre hay recursos para atender a los clientes. Es importante, de lo contrario podría unas cuantas ejecuciones parar cualquier tipo de petición hasta que se liberaran.
    2) También seráía bueno
        - Los recuros para el scraping + Analisis de IA poner recursos ampliados

    Con esta separación se podría tener levantada la pagina web en algún servidor local en INTRAS
    y tener el proceso de scrapping + IA en ejecutandose por ejemplo en los servidores de computo de la UV
