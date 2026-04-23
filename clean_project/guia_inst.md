¿Cómo instalar todo desde cero?: 
**Anaconda → VS Code → entorno → requirements → ejecutar main.py**.

---

# 🚀 Guía de instalación y ejecución

Sigue estos pasos para poner en marcha el proyecto desde cero, incluso en un equipo nuevo.

---

## **1️⃣ Instalar Anaconda (recomendado)**

1. Descarga Anaconda desde la web oficial:
   👉 [https://www.anaconda.com/products/distribution](https://www.anaconda.com/products/distribution)

2. Instálalo siguiendo los pasos (Next → Next → Finish).

3. Abre **Anaconda Prompt** (muy importante).

---

## **2️⃣ Instalar Visual Studio Code**

1. Descarga VS Code desde:
   👉 [https://code.visualstudio.com/](https://code.visualstudio.com/)

2. Durante la instalación, activa la opción:
   ✔ “Add to PATH (recommended)”

3. Abre VS Code.

---

## **3️⃣ Crear un entorno virtual con Anaconda**

En **Anaconda Prompt**, dentro de la carpeta del proyecto:

```bash
cd ruta/de/tu/proyecto
```

Crear entorno:

```bash
conda create -n rrss_analysis_env python=3.10 -y
```

Activar entorno:

```bash
conda activate rrss_analysis_env
```

---

# 🎯 **4️⃣ Instalar dependencias**

Con el entorno virtual **ya activado**, instala todas las librerías necesarias:

```bash
# pip install langdetect praw requests selenium webdriver_manager pandas google-api-python-client beautifulsoup4 ollama unidecode pyngrok streamlit
pip install -r requirements.txt
```

---

## 🔥 **Dependencias para usar modelos locales (Ollama)**

Usamos **LLM locales** para el análisis de sentimiento, necesitamos instalar **Ollama** y bajar el modelo.

### 🟦 1. **Instalar Ollama**

Descárgalo desde aquí:
👉 [https://ollama.com/download](https://ollama.com/download)

---

### 🟩 2. **Instalar el cliente Python de Ollama**

```bash
pip install ollama
```

---

### 🟧 3. **Descargar el modelo LLaMA 3**

```bash
ollama run nombre_modelo  # "qwen2.5:1.5b"# gemma3:4b → qwen2.5:14b # pull llama3 
```

> 💡 **Recuerda:** Ollama debe estar *ejecutándose* antes de iniciar el proyecto.
> En sistemas donde no se inicia solo:

```bash
ollama serve
```
# Chequear que use gpu: nvidia-smi

---

## **5️⃣ Abrir el proyecto desde VS Code**

```bash
code .
```

En VS Code, selecciona del menú:

`Ctrl + Shift + P → Python: Select Interpreter → rrss_analysis_env`

---
Hay dos formas de ejecutar el proyecto:

## **6️⃣ Ejecutar el proyecto en consola**

En la terminal integrada de VS Code (o desde Anaconda Prompt):

```bash
python run_pipeline.py
```

Esto ejecutará automáticamente el pipeline completo:

1. Scraping de Bluesky, Reddit, LinkedIn, YouTube y X/Twitter
2. Detección de temas y análisis de sentimiento. Clasificación de sentimiento por pilares con LLM
3. Cálculo de aceptación global
5. Guardado de resultados en `/data`

---

# 🎉 ¡Listo!

## **6️⃣ Ejecutar el proyecto en la aplicación web**
1. Configurar Ngrok (Solo la primera vez):
TOKEN: 36jrQECiuJYtj0YbV0agVLgEo4X_4jjQdW7VQ911omrtHGPLM

```bash
ngrok config add-authtoken TOKEN_AQUÍ
```
2. Lanzar la web
```bash
python run_app.py
```