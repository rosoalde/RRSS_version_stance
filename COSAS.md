### IMPORTANTE: ¿CÓMO PROTEGER EL ACCESO AL SISTEMA?  ¿CAMBIAMOS LAS CONTRASEÑAS?
El acceso al sistema se protege con inicio de sesiones de parte de los usuarios
- este inicio creará un token que se enviará al usuario, y el cual lo usará para identificarse
al sistema como su DNI
- Los ficheros con contraseñas están bién, son contraseñas que solo el backend usa,
y el usuaurio nunca podría siquiera tener acceso.
### ¿DE YOUTUBE SE PUEDE RECOGER DE QUÉ SE HABLA EN EL VIDEO?
- Se se usa la API habria que verla. Tengamosla pendiente
- Youtube usa IA y traducción en muchos videos suyos. Muy probablemente se pueda recoger esos datos.
Habría que ver qué tan accesible son y la parte "Legal"
### CREO QUE LO MAS IMPORTANTE ES  VER CÓMO HACEMOS PARA QUE VARIOS USUARIOS PUEDAN USAR EL SISTEMA A LA VEZ 
- Para que varios usuarios puedan hacerlo, se está implementando celerys como sistema de colas.
- Estoy reenfocando el asunto para que:
        1) La pagina tenga recursos fijos para las peticiones de los clientes
                (aí tenga capacidad de atenderlos a todos)
        2) Poner recursos dinámicos a parte para la ejecución de Scrappers + Analisis con IA
De esta manera, aunque el scrapper + IA se coma todo nuestro cómputo, siempre se podrá
responder al usuario, y no dejarlo tirado esperando a que algún recurso se libere.
Nota: muy probablemente haya que poner docker al fast api también.

A. Inferir aceptación de prefiles concretos (Romina Task)
        - ¿Podrías detallar esta parte, plis, no la entiendo? ^
        - Romina: Por esto no te preocupes!

B. Protocolo ajuste de modelos para aceptación de políticas públicas (Romina Task)

C. Si por ejemplo estoy ejecutando el indicador de aceptación, y me muevo  a la biblioteca, la ejecución del indicador se detiene.
        - CRISTHIAN:
          ¿Segura? No sería mejor dar una imagen de "carga" y que si el usuario se mueve, al volver vea si se ha terminado o no. Y que si se ha terminado, obtenga los resultados ya cargados?  
        - Romina: Estaba detallando el comportamiento actual. Lo que dices es lo que debería suceder, que el usuario se mueve, que detrás se siga ejecutando el análisis y cuando regrese si terminó que se muestre la ventana del informe y si no que siga mostrando como ahora "Calculando aceptación estrategica".
          
2. No se puede navegar a las otras pestañas mientras se está ejecutando un proyecto (extraccion o llm trabajando). (RELACIONADO CON EL PUNTO C)        

D. Botones deshabilitados temporalmente al clickear sobre seleccionar todas, se seleccionan las redes deshabilitadas temporalmente.
    - CRISTHIAN: CORREGIDO
    - Romina: Chequeado que funciona

E. Intentar agregar más datos de redes, ejemplo todos los comentarios de un post de Bluesky.

F. Cómo implementaríamos nuesta herramienta el servidor (redactar alguna guía o algo de los pasos que deberíamos seguir para levantar la web en el servidor) (Cristhian)

0. Limitar la extracción a las APIs oficiales. CRISTHIAN: CORREGIDO

1. AL EJECUTAR UNA ANÁLISIS SE MUESTRA EL SIGUIENTE MENSAJE:

Procesando datos...
Inicializando...

DEBERÍA MOSTRARSE UN MENSAJE DINÁMICO QUE VAYA CAMBIADO DE ACUERDO A LA ETAPA EN LA QUE SE ENCUENTRA, EJEMPLO, BUSCANDO DATOS EN REDDIT, BUSCANDO DATOS EN X, ANÁLISIS DE SENTIMIENTO

2. En la parte de Dashboard Pau sugería que las gráficas de Tendencias puedan ser dinámicas como las de https://www.google.com/finance/quote/META:NASDAQ?sa=X&ved=2ahUKEwi8i8Tp9vGSAxUUh_0HHbUeD5gQ3ecFKAR6BAg4EAU 1 día, 5D 1mes, 6M, YTD, 1 año, 5 años...

3. El filtro por topics, sólo debería actualizar los filtros, no todo el dashboard completo.

4. Mejorar las nubes, ver gephi (puede servir para topics/predicción análisis de perfiles)

5. Desagrupar el Dashboard Resultados en el menú de la derecha con submenus. Al tocar Dahsboard Resultados solamente se muestran los resultados globales (Volumen de Menciones Análisis de Sentimiento Global). En el submenú tenemos  Análisis de sentimiento por red. Luego en el submenú tenemos Temas principales, y otro sector de Nube de palabras. Cuidado con el filtro Geográfico ¿debería actuar solamente para volumen y análisis de sentimiento o para topics y nubes de palabras también?

6. PROTOLOCO SERVIDOR

7. Entre cada una de las secciones, debería haber una explicación breve de lo que hay en cada apartado (VOLUMEN, SENTIMIENTO, TOPICS, NUBES)

8. Agregar en la memoria que usamos github

9. Preguntar JM lo del servidor levantado siempre


# =========================================================================

#### OTROS OBJETIVOS VIEJOS, ALGUNOS YA HAN SIDO ABORDADOS####

1. Al terminar la generación de términos echo en falta un botón de deseleccionar todo (AGREGADO)


Checkear
1. Al generar keywords con asistente ia dos veces (o más),
las keywords generadas se acumulan (se agregan al final de las anteriores en lugar de reemplazarlas), necesitamos limpiar el contenedor generatedContainer antes de agregar los nuevos elementos.
        - CRISTHIAN:
            ¿Cómo debería ser el comportamiento?
                a) Los keywords se acumulan y solo se eliminan los repetidos
                b) Cada generación de keywords elimina completamente todo de las anteriores (incluso las que fueron seleccionadas)
                c) Cada generacón de keywords elimina solo los que el usuario no seleccionó y las reemplaza por las nuevas
        - Romina: Esto era un problema del pasado que ya está solucionado! Perdón que te he liado        

Si modificamos la función del evento click del botón generateKeywordsBtn dentro main.js, gregando la línea generatedContainer.innerHTML = ""; justo después de recibir los datos y antes del bucle forEach, tampoco funciona. VER SOLUCIÓN, ME LO CARGUÉ....NO ME LO CARGUÉ, PARECE QUE EL LLM SE HA VUELTO LOCO, LO CAMBIO POR GEMMA VOY A PROBAR SI, EL LLM SE VUELVE LOCO A VECES. 



3. Mejorar prompt (cambiar modelo esto funcionaba mejor antes) para generar keywords más adecuadas. (CONTINUO REFINAMIENTO: DAVID, ROMINA)

4. Ver cómo generar cuenta, con permiso adicional (¿cómo se van a ejecutar proyectos de diferentes cuentas en el servidor?). (CRISTHIAN)

5. Ver lo del motor de búsqueda inteligente (ejemplo comportamiento Youtube, YouTube recoge videos que aunque no tengan la palabra clave en el título, son semánticamente similares) (ROMINA)
6. Crear nube de palabras con los mensajes / sentimiento. NUBES MÁS BONITAS
7. Nube de frases/ sentimiento?

Checkeado:
4. voy a probar reddit vs reddit_last (funcionan igual, PROBADO)
5. tiktok no funciona

# =========================================================================

#### Tutorial para anclar nuevas funcionalidades ####
Tutorial para anclar nuevas funcionalidades ejemplo ámbito geográfico. En index agregamos un class, luego en main.py en class AnalisisData(BaseModel): agregamos geo_scope: str

ademas en main.js en const dataToSend = { agregamos geo_scope: formData.get("geography"),  // <-- AÑADIDO si en logica.py imprimimos vemos que geo_Scope se está cogiendo.
# =========================================================================

#### GIT ####
Git-2.53.0-64-bit descargado e instalado
R-4.5.2-win descargado e instalado
RStudio-2026.01.0-392 descargado e instalado

Git Bash $ git config --global user.name rsadl
 git config --global email romina.albornoz@uv.es


$ git config list
diff.astextplain.textconv=astextplain
filter.lfs.clean=git-lfs clean -- %f
filter.lfs.smudge=git-lfs smudge -- %f
filter.lfs.process=git-lfs filter-process
filter.lfs.required=true
http.sslbackend=schannel
core.autocrlf=true
core.fscache=true
core.symlinks=false
pull.rebase=false
credential.helper=manager
credential.https://dev.azure.com.usehttppath=true
init.defaultbranch=master
user.name=rsadl
user.email=romina.albornoz@uv.es

abrir Rstudio-> New Project ->version control -> git -> Repository url - code local https-> create -> rama main arriba a la derecha -> creamos un archivo nuevo

OBLIGATORIO PRIMERO pull (descarga la última versión)

Luego commit, seleccionamos el archivo donde hemos hecho los cambios y agregamos comentario entre corchetes [rsadl ]

luego push

Para ir a otro proyecto me voy a close project a la derecha


antes de empezar pull

gitignore (no queremos que se vean ciertas cosas)