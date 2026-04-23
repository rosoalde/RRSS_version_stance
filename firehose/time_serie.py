import numpy as np
from scipy.signal import savgol_filter
import matplotlib.pyplot as plt

serie = np.array([4, 23, 95, 39, 33, 13, 6])#4, 23, 95, 95, 39, 33, 13, 6, 4, 23, 95, 95, 39])
t = np.arange(len(serie))

# 1. Centrado
x_mean = np.mean(serie)
centered = serie - x_mean

# 2. Suavizado adaptado para serie corta (SavGol ~ LOWESS + SES)
smoothed = savgol_filter(centered, window_length=5, polyorder=2)

# 3. Etiquetado inicial
label = (smoothed > 0).astype(int)

# 4. Corrección k=6
label_final = label.copy()
n = len(serie)
for i in range(1, n):
    if label_final[i] == 1 and label_final[i-1] == 0:
        # Longitud aproximada de ola desde i
        wave_len = 1
        j = i + 1
        while j < n and label[j] == 1:
            wave_len += 1
            j += 1
        retro = max(1, int(wave_len / 1))  # Mínimo 1 para cortas
        start = max(0, i - retro)
        label_final[start:i] = 1

print("Serie original:", serie)
print("Etiquetas finales:", label_final)
print("Olas detectadas en posiciones:", np.where(label_final == 1)[0])

# 5. Visualización con colores
plt.figure(figsize=(10, 4))
plt.plot(t, serie, 'b-o', label='Original', linewidth=2)
plt.plot(t, smoothed + x_mean, 'orange', label='Suavizada', linewidth=2)

colors = ['cyan', 'purple', 'yellow']
wave_groups = []
i = 0
while i < n:
    if label_final[i] == 1:
        start, end = i, i
        while end < n and label_final[end] == 1:
            end += 1
        wave_groups.append((start, end-1))
        plt.fill_between(t[start:end], 0, serie[start:end], 
                        color=colors[len(wave_groups)%len(colors)], alpha=0.4)
        i = end
    else:
        i += 1

plt.title('COWAVE: Olas detectadas en serie corta')
plt.xlabel('Tiempo'); plt.ylabel('Valor')
plt.legend(); plt.grid(True, alpha=0.3)
plt.show()


'''
from ruptures import Pelt
from scipy.signal import find_peaks
import numpy as np
import pandas as pd

def universal_cpd(serie):
    # 1. PELT (tendencias)
    pelt = Pelt(model="rbf").fit(serie).predict(pen=3)
    
    # 2. Picos (eventos locales)
    peaks, _ = find_peaks(serie, height=np.mean(serie)*1.5)
    
    # 3. Caídas
    valleys, _ = find_peaks(-serie, height=np.std(serie)*1.5)
    
    return sorted(set(pelt + list(peaks) + list(valleys)))

# Prueba cualquier serie
print(universal_cpd(np.array([4,23,95,39,33,13,6,96])))

import matplotlib.pyplot as plt

def graficar_eventos(serie, eventos):
    plt.figure(figsize=(12, 6))
    
    # Serie principal
    plt.plot(serie, 'o-', linewidth=4, markersize=12, color='#1f77b4', label='Serie temporal')
    
    # Líneas ROJAS en eventos (PELT + picos + valles)
    for i in eventos:
        if i < len(serie):  # Evita el "7" final
            plt.axvline(i, color='red', linewidth=4, linestyle='--', 
                       label=f'Evento (día {i})' if i == eventos[0] else "")
    
    # Ventanas VERDES entre eventos
    ventanas = [0] + [e for e in eventos if e < len(serie)] + [len(serie)]
    for i in range(len(ventanas)-1):
        plt.axvspan(ventanas[i], ventanas[i+1]-0.5, alpha=0.25, color='green',
                   label='Estabilidad' if i == 0 else "")
    
    plt.title('Event Detection Universal - Tu serie', fontsize=14, fontweight='bold')
    plt.ylabel('Volumen', fontsize=12)
    plt.xlabel('Tiempo (días)', fontsize=12)
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


import numpy as np
import matplotlib.pyplot as plt
from ruptures import Pelt
from scipy.signal import find_peaks

def graficar_universal(serie, eventos, titulo):
    plt.figure(figsize=(12, 4))
    plt.plot(serie, 'o-', linewidth=3, markersize=8, color='#1f77b4')
    
    # Eventos ROJOS
    for i in eventos:
        if i < len(serie):
            plt.axvline(i, color='red', linewidth=3, linestyle='--')
    
    # Ventanas VERDES
    ventanas = [0] + [e for e in eventos if e < len(serie)] + [len(serie)]
    for i in range(len(ventanas)-1):
        plt.axvspan(ventanas[i], ventanas[i+1]-0.5, alpha=0.3, color='green')
    
    plt.title(titulo)
    plt.ylabel('Valor')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()

# 5 SERIES ALEATORIAS CON EVENTOS REALES
np.random.seed(42)

print("=== TESTING universal_cpd ===\n")

# 1. SERIE 1: Nivel bajo → ALTO → BAJO
serie1 = np.concatenate([
    np.random.normal(20, 5, 15),  # bajo
    np.random.normal(80, 10, 10), # ALTO (evento)
    np.random.normal(30, 8, 12)   # bajo
])
eventos1 = universal_cpd(serie1)
print("Serie 1:", eventos1)
graficar_universal(serie1, eventos1, "Serie 1: Nivel bajo→ALTO→bajo")

# 2. SERIE 2: Tendencia + PICO
x = np.arange(40)
serie2 = np.concatenate([
    10 + 0.5*x[:15] + np.random.normal(0, 3, 15),  # tendencia
    [80],                                           # PICO
    25 + 0.2*(x[16:]) + np.random.normal(0, 4, 24) # tendencia suave
])
eventos2 = universal_cpd(serie2)
print("Serie 2:", eventos2)
graficar_universal(serie2, eventos2, "Serie 2: Tendencia + PICO")

# 3. SERIE 3: 3 NIVELES DISTINTOS
serie3 = np.concatenate([
    np.random.normal(10, 2, 12),   # nivel 1
    np.random.normal(50, 8, 15),   # nivel 2  
    np.random.normal(90, 12, 18)   # nivel 3
])
eventos3 = universal_cpd(serie3)
print("Serie 3:", eventos3)
graficar_universal(serie3, eventos3, "Serie 3: 3 niveles distintos")

# 4. TU SERIE ORIGINAL
serie4 = np.array([4,23,95,39,33,13,6])
eventos4 = universal_cpd(serie4)
print("Tu serie:", eventos4)
graficar_universal(serie4, eventos4, "Tu serie original")

# 5. SERIE RUIDOSA con 2 eventos
serie5 = np.random.normal(0, 1, 50)
serie5[15:25] = 5 + np.random.normal(0, 0.5, 10)  # evento 1
serie5[35:42] = -3 + np.random.normal(0, 0.5, 7)  # evento 2
eventos5 = universal_cpd(serie5)
print("Serie 5 (ruidosa):", eventos5)
graficar_universal(serie5, eventos5, "Serie 5: Ruidosa con 2 eventos")

# USO:
serie = np.array([4,23,95,39,33,13,6])
eventos = universal_cpd(serie)
print("Eventos detectados:", eventos)

# ¡Gráfica exacta como tu imagen!
graficar_eventos(serie, eventos)

'''
'''
# ====================================
# 1. Datos
# ====================================
dates = ["2026-02-15", "2026-02-16", "2026-02-17",
         "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-21"]

values = np.array([4, 23, 95, 39, 33, 13, 6])

data = pd.DataFrame({"date": dates, "comments": values})

data["date"] = pd.to_datetime(data["date"])
data.set_index("date", inplace=True)


import numpy as np
import matplotlib.pyplot as plt
from pyepidemics.models import SIR

# serie temporal (comentarios diarios)
cases = np.array([4,23,95,39,33,13,6])

# población ficticia (solo para escalar el modelo)
population = 10000

# crear modelo
model = SIR(population)

# ajustar el modelo a los datos
model.fit(cases)

# simular evolución
t = np.arange(len(cases))
simulation = model.predict(t)

# graficar
plt.plot(cases, label="Datos reales")
plt.plot(simulation["I"], label="Infectados (modelo)")
plt.legend()
plt.title("Ajuste modelo SIR")
plt.show()

'''

'''
# ====================================
# 2. Train / Test split
# ====================================
train = data.iloc[:-1]   # primeros 4 días
test = data.iloc[-1:]    # últimos 3 días (datos reales)
print(len(test))

# ====================================
# 3. Modelo
# ====================================
modelo = SimpleExpSmoothing(train["comments"]).fit()

forecast = modelo.forecast(steps=len(test))

# ====================================
# 4. Evaluación
# ====================================
mae = mean_absolute_error(test["comments"], forecast)

print("Predicción:")
print(forecast)

print("\nDatos reales:")
print(test["comments"])

print("\nMAE (error medio absoluto):", mae)

# ====================================
# 5. Gráfica
# ====================================
plt.figure(figsize=(10,5))

plt.plot(train.index, train["comments"], marker='o', label="Train")
plt.plot(test.index, test["comments"], marker='o', label="Real")

plt.plot(test.index, forecast, marker='x', linestyle='--', label="Pronóstico")

plt.title("Comparación Pronóstico vs Real")
plt.xlabel("Fecha")
plt.ylabel("Comentarios")

plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()


from statsmodels.tsa.arima.model import ARIMA

model = ARIMA(train["comments"], order=(1,1,1))
model_fit = model.fit()

forecast_arima = model_fit.forecast(steps=len(test))
print(forecast_arima)

plt.plot(train.index, train["comments"], label="Train")
plt.plot(test.index, test["comments"], label="Real")
plt.plot(test.index, forecast_arima, label="Forecast ARIMA")
plt.plot(test.index, forecast, marker='x', linestyle='--', label="Pronóstico")

plt.legend()
plt.show()


from statsmodels.tsa.holtwinters import Holt

holt_model = Holt(train["comments"]).fit()
forecast_holt = holt_model.forecast(steps=len(test))

from statsmodels.tsa.holtwinters import ExponentialSmoothing

hw_model = ExponentialSmoothing(train["comments"], trend="add").fit()
forecast_hw = hw_model.forecast(steps=len(test))

window = 3
moving_avg = train["comments"].rolling(window).mean().iloc[-1]

forecast_ma = [moving_avg] * len(test)



naive_value = train["comments"].iloc[-1]
forecast_naive = [naive_value] * len(test)

plt.figure(figsize=(10,5))

plt.plot(train.index, train["comments"], marker="o", label="Train")
plt.plot(test.index, test["comments"], marker="o", label="Real")

plt.plot(test.index, forecast, label="SES")
plt.plot(test.index, forecast_arima, label="ARIMA")
plt.plot(test.index, forecast_holt, label="Holt")
plt.plot(test.index, forecast_hw, label="Holt-Winters")
plt.plot(test.index, forecast_naive, label="Naive")
plt.plot(test.index, forecast_ma, label="Moving Avg")

plt.legend()
plt.show()

results = {
    "SES": mean_absolute_error(test["comments"], forecast),
    "ARIMA": mean_absolute_error(test["comments"], forecast_arima),
    "Holt": mean_absolute_error(test["comments"], forecast_holt),
    "HW": mean_absolute_error(test["comments"], forecast_hw),
    "Naive": mean_absolute_error(test["comments"], forecast_naive),
    "MA": mean_absolute_error(test["comments"], forecast_ma),
}

print(pd.Series(results).sort_values())


import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Serie de ejemplo
time = np.arange(len(values))

# Tamaño de ventana
for w in range(1, 5):  # probar con diferentes tamaños de ventana
    # Scan statistic: media móvil
    scan_score = np.array([np.mean(values[i:i+w]) for i in range(len(values)-w+1)])
    scan_time = time[w-1:]  # alineación final de la ventana

    # Umbral para evento (por ejemplo percentil 90)
    threshold = np.percentile(scan_score, 90)

    # Detectar ventanas-evento
    events = scan_score > threshold

    # Gráfico
    plt.figure(figsize=(10,4))
    plt.plot(time, values, marker='o', label="Signal")
    plt.plot(scan_time, scan_score, marker='x', label="Scan score")
    plt.hlines(threshold, time[0], time[-1], color='red', linestyle='--', label="Threshold")
    for t,e in zip(scan_time, events):
        if e:
            plt.axvspan(t-w+1, t, color='green', alpha=0.2)
    plt.legend()
    plt.show()



import numpy as np
import matplotlib.pyplot as plt
from hmmlearn.hmm import GaussianHMM
import matplotlib.patches as mpatches

# Serie de comentarios
dates = ["2026-02-15", "2026-02-16", "2026-02-17",
         "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-21"]
values = np.array([4, 23, 95, 39, 33, 13, 6])
X = values.reshape(-1,1)

# Número de fases
n_states = 3
model = GaussianHMM(n_components=n_states, covariance_type="full", n_iter=100)
model.fit(X)
states = model.predict(X)

# ordenar estados por valor medio
# calcular media de cada estado
means = []
for s in range(n_states):
    if np.any(states == s):
        means.append((s, X[states == s].mean()))
    else:
        means.append((s, 0))

# ordenar estados por valor medio
means_sorted = sorted(means, key=lambda x: x[1])

# crear mapa nuevo de estados
state_map = {old:new for new,(old,_) in enumerate(means_sorted)}

states_ordered = np.array([state_map[s] for s in states])

# Colores y nombres
colors = ["#A6CEE3","#FDBF6F","#FB9A99","#B2DF8A","#CAB2D6"]
phase_names = ["Incubación","Brote","Pico","Declive","Calma"]

# Gráfico
plt.figure(figsize=(10,5))
plt.plot(dates, values, marker="o", color="black", label="Comentarios")

# rellenar áreas por fase
i = 0
while i < len(states_ordered):
    j = i
    while j+1 < len(states_ordered) and states_ordered[j+1]==states_ordered[i]:
        j += 1
    plt.axvspan(i-0.5, j+0.5, color=colors[states_ordered[i]], alpha=0.4)
    i = j+1

# leyenda
patches = [mpatches.Patch(color=colors[i], alpha=0.4, label=phase_names[i]) for i in range(n_states)]
plt.legend(handles=patches, bbox_to_anchor=(1.05,1))

plt.title("Fases automáticas del ciclo de opinión con HMM")
plt.xlabel("Fecha")
plt.ylabel("Número de comentarios")
plt.xticks(range(len(dates)), dates, rotation=45)
plt.tight_layout()
plt.show()


import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import lognorm
from scipy.optimize import curve_fit

# serie temporal
values = np.array([4,23,95,39,33,13,6])
t = np.arange(len(values))

# función lognormal
def lognormal_curve(t, s, scale, amplitude):
    return amplitude * lognorm.pdf(t+1, s=s, scale=scale)

# ajustar curva
params, _ = curve_fit(lognormal_curve, t, values, maxfev=10000)

s, scale, amplitude = params

# curva ajustada
t_fit = np.linspace(0, len(values)-1, 100)
y_fit = lognormal_curve(t_fit, s, scale, amplitude)

# detectar pico
peak_index = np.argmax(values)

# graficar
plt.figure(figsize=(8,4))
plt.scatter(t, values, label="Datos reales")
plt.plot(t_fit, y_fit, label="Curva log-normal ajustada")

plt.axvline(peak_index, linestyle="--", label="Pico")

plt.title("Ciclo de atención ajustado con modelo log-normal")
plt.xlabel("Tiempo")
plt.ylabel("Comentarios")
plt.legend()
plt.show()
'''