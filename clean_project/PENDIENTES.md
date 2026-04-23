## TAREAS PENDIENTES ROMINA:
- ¿vamos a devolver en la app web los CSVs generados? En ese caso, deberíamos entregar los mínimos datos (asignar identificador a cada usuario y eliminar URL del post). GUARDAR DATOS ORIGINALES EN LOCAL, ENTREGAR FILTRADOS. (COMPLETADO ✓)
- prompt para generar palabras clave sobre un tema especifico fijado por el usuario (Ver comportamiento) ✓
- Crear aplicación web multiusuario (CRISTHIAN (TODO) - ROMINA (colaborar en el enlace DATA FRONT TAREA ACTUAL))
- AGREGAR OPCIÓN SELECCIONAR IDIOMA Y PODER FILTRAR LOS CSV POR IDIOMA TAMBIÉN. (En proceso Romina)
- FILTRAR LOS COMENTARIOS EXTRAIDOS POR TOPIC DADO, QUE SE PUEDE DEFINIR MANUALMENTE (NO DE LOS DETECTADOS POR EL MODELO DE LENGUAJE)

## MUY PRIORITARIAS (CRISTHIAN):
1. AGREGAR UNA EXCEPCIÓN A LINKEDIN. SI NO APARECE LA VERIFICACIÓN MANUAL, CONTINUAR CON LA BÚSQUEDA (solucionado ✓) 
2. VER TIKTOK (API de TIKTOK muy limitada y con consentimiento del dueño de la cuenta. No sirve para recabar información) (CRISTIAN:✓- ROMINA: INTEGRAR PENDIENTE)
3. MEJORAR APP (Cristhian ya vio que es posible agregar las gráficas a la app, VEREMOS SI ES POSIBLE PARALELIZAR INSTANCIAS- MÚLTIPLES USUARIOS)
4. ¿Queremos guardar los datos a medida que va buscando? (Sí)

## MUY PRIORITARIAS ROMINA:
1. IMPLEMENTAR ACEPTACIÓN GLOBAL (PILARES) (✓)
2. AGREGAR INSTRUCCIONES DETECCIÓN DE TEMAS AL PROMPT (Mejor analizar por separado, un prompt para cada tarea por cada comentario) (CHEQUEAR COMPORTAMIENTO ESPERADO)
3. GRAFICAS VISUALIZACIÓN PARA APP
4. INFORME AUTOMÁTICO QUE DESCRIBA EL INDICADOR GLOBAL (✓)

## PRIORITARIAS:

1. AGREGAR OTRAS FUENTES DE DATOS (CRISTIAN / BRUNO):

   * LINKEDIN (BRUNO/CRISTHIAN- VER CÓDIGO DE FENOLL: ./WebScraping.Selenium.Linkeding.ipynb- Extraen contenido texto publicaciones, usuario, fecha)
   * PERIÓDICOS DIGITALES (CRISTIAN)
   * INSTAGRAM (?)
   * FACEBOOK (CRISTHIAN)
   * YouTube – YouTube Data API v3 (BRUNO ✓)
   * Mastodon – REST API
   * Tumblr – Tumblr API (No sirve la API)
   * TikTok – TikTok API (Business/Research)
   * PARALELIZAR EL SISTEMA DE BÚSQUEDA (que a la vez busque en X, Reddit, Linkedin, etc)

2. MEJORAR LA HERRAMIENTA:

   * Generar prompt genérico para otros temas (✓) ./prompt_general.py (En prueba Romina)
   * Generar prompt genérico para aceptaciÓn de medidas públicas (En prueba David-Romina)
   * Panel de visualización de métricas
   * Mejorar métricas:

     * (ponderar por fecha de publicación (?))
     * ponderar por rasgos socio-psicológicos (?)

3\. DOCUMENTAR METODOLOGÍA Y PROCESO 

* Ajustar documento previo a los nuevos avances (En proceso continuo. David-Romina)
* Documentar con capturas los avances en la herramienta (Vamos a desarrollarla con CRISTHIAN)
  

## SECUNDARIAS

3. Predicción Aceptación de políticas públicas

   * Análisis perfiles Redes Sociales

4. Análisis de aceptación de medidas/objetivos (Mirar archivo DESARROLLO LOCAL / INFORME USO DE DRONES ESPAÑA)
5. Diseñar front (INSPECCIONANDO Romina /Cristhian)
6. Explorar automatización de informes
7. Explorar modelos bayesianos para fundamentar predicción
