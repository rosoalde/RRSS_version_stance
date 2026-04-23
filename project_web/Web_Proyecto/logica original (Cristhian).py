import sys, json

def backend_analisis(data):
    print("######################")
    print("BACKEND")
    print("######################")
    
    print(data)

    # EJEMPLO de resultado real
    resultados = []

    for r in data["results"]:
        resultados.append({
            "social": r["social"],
            "success": r["success"],
            "metricas": {
                "likes": 120,
                "comentarios": 45
            }
        })
    
    return {
        "mensaje": "Análisis completado",
        "resultados": resultados
    }
'''
# Bloque principal
if __name__ == "__main__":
    # FastAPI pasa los datos como argumento JSON
    print("hola caracola")
    if len(sys.argv) < 2:
        print("Error: Se esperaba un argumento JSON con los datos")
        sys.exit(1)

    data_json = sys.argv[1]
    try:
        data = json.loads(data_json)
    except json.JSONDecodeError:
        print("Error: No se pudo decodificar el JSON")
        sys.exit(1)

    ejecutar_analisis(data)
'''