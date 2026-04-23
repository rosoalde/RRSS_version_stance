import ollama

MODELO = "qwen2.5:1.5b" #"gemma3:4b" #

print(f"Probando conexión con {MODELO}...")

try:
    res = ollama.chat(model=MODELO, messages=[{'role': 'user', 'content': 'hola'}])
    print("✅ RESPUESTA RAW:")
    print(res)
    print("-" * 20)
    print("Contenido:", res['message']['content'])
except Exception as e:
    print("❌ ERROR:")
    print(e)