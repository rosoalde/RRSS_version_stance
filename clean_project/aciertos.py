import pandas as pd
import os

INPUT_CSV = "C:\\Users\\DATS004\\Dropbox\\PERSONAL\\clean_project\\DRONES_INFORME20250401_20250930\\DATASET_FINAL_RELEVANTE_ANONIMIZADO.csv"
OUTPUT_CSV = "C:\\Users\\DATS004\\Dropbox\\PERSONAL\\clean_project\\DRONES_INFORME20250401_20250930\\dataset_anotado.csv"

HUMAN_FIELDS = [
    ("sentimiento_general", "sentimiento_general_HUMANO"),
    ("score_legitimacion", "score_legitimacion_HUMANO"),
    ("score_efectividad", "score_efectividad_HUMANO"),
    ("score_justicia_equidad", "score_justicia_equidad_HUMANO"),
    ("score_confianza_institucional", "score_confianza_institucional_HUMANO"),
    ("score_marcos_discursivos", "score_marcos_discursivos_HUMANO"),
]

def cargar_dataset():
    if os.path.exists(OUTPUT_CSV):
        print("📂 Cargando dataset anotado existente...")
        return pd.read_csv(OUTPUT_CSV)
    else:
        print("📂 Cargando dataset original...")
        df = pd.read_csv(INPUT_CSV)

        for _, human_col in HUMAN_FIELDS:
            if human_col not in df.columns:
                df[human_col] = ""

        df.to_csv(OUTPUT_CSV, index=False)
        return df

def pedir_valor(contenido, campo_auto, valor_auto, campo_humano):
    print("\n" + "-" * 80)
    print("CONTENIDO:")
    print(contenido)
    print("\n" + campo_auto + " (AUTOMÁTICO):", valor_auto)
    print(f"👉 Introduce {campo_humano} (ENTER para dejar vacío):")
    return input("> ").strip()

def main():
    df = cargar_dataset()

    for idx, row in df.iterrows():
        contenido = row["contenido"]

        for campo_auto, campo_humano in HUMAN_FIELDS:
            if pd.isna(row[campo_humano]) or row[campo_humano] == "":
                valor = pedir_valor(
                    contenido,
                    campo_auto,
                    row[campo_auto],
                    campo_humano
                )

                if valor != "":
                    df.at[idx, campo_humano] = valor

                # Guardado inmediato (clave para poder retomar)
                df.to_csv(OUTPUT_CSV, index=False)

    print("\n✅ Etiquetado completado.")

if __name__ == "__main__":
    main()
