"""
success_analysis.py
-------------------
ÍNDICE DE ÉXITO/VIABILIDAD NO SUPERVISADO (sin etiquetas) a partir del dataset analizado por tu pipeline.
 
✅ Ejecutable aislado (no depende de run_pipeline.py).
✅ Lee CSV/JSON analizado.
✅ Filtra filas irrelevantes: conserva solo posts con algún pilar sent_* == -1 o +1.
✅ Agrega por ventana temporal (W semanal por defecto).
✅ Calcula:
   - success_probability (0-1) PRINCIPAL (GMM si hay histórico suficiente; si no, fallback heurístico)
   - success_score (0-100) SECUNDARIO (heurístico)
   - pattern_probabilities / pattern_labels (si hay GMM)
   - uncertainty / confidence (versión “simple bayesiana”)
✅ Pesos NO subjetivos: calcula w_j con ENTROPY WEIGHTING (data-driven) sobre el histórico.
✅ Exporta:
   - report_success.json
   - success_timeseries.csv
   - success_posts_enriched.csv
   - success_plot.png
   - success_history_features.csv
   - success_model.joblib
   - risk_weights_entropy.csv
 
Dependencias:
pip install numpy pandas scikit-learn scipy matplotlib python-dateutil joblib
 
Ejemplo Windows: python success_analysis.py ^
--input "C:/Users/david/Desktop/clean_project/clean_project/prueba_david320251201_20260101/twitter_global_dataset_analizado.csv" ^
--outdir "C:/Users/david/Desktop/clean_project/clean_project/success_out" ^ --window W """
 
 
 
from __future__ import annotations
 
import argparse
import json
import math
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
 
import numpy as np
import pandas as pd
from dateutil import parser as dateparser
from joblib import dump
from scipy.stats import skew
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt
 
 
from typing import Tuple

def suggest_window(df, cfg: SuccessConfig):
    # Resolver columna fecha dinámicamente
    col_date = resolve_column(df, cfg.col_date, "fecha")

    df = df.copy()

    # Si quisieramos unir FECHA y HRS para un análisis de "Éxito por horas":
    # df['dt'] = pd.to_datetime(df['FECHA'] + ' ' + df['HRS'], errors='coerce')

    df['dt'] = pd.to_datetime(df[col_date], errors='coerce')
    df = df.dropna(subset=['dt'])
    
    if len(df) == 0:
        return "W", 0, 0, 0.0, "no hay fechas válidas en el dataset."

    first_date = df['dt'].min()
    last_date = df['dt'].max()
    total_days = (last_date - first_date).days + 1
    total_posts = len(df)
    posts_per_day = total_posts / max(total_days, 1)

    if total_days < 14:
        suggestion = "D"
        reason = f"tu dataset solo cubre {total_days} días."
    elif posts_per_day < 5:
        suggestion = "W"
        reason = f"pocos posts por día ({posts_per_day:.1f})."
    else:
        suggestion = "M"
        reason = "volumen y tiempo suficientes."

    return suggestion, total_days, total_posts, posts_per_day, reason

def resolve_column(df: pd.DataFrame, candidates: Tuple[str, ...], coltype: str) -> str:
    for c in candidates:
        if c in df.columns:
            return c
    raise ValueError(
        f"No encuentro columna para '{coltype}'. "
        f"Probé: {candidates}. "
        f"Disponibles: {list(df.columns)}"
    )    
# -------------------------
# Helpers (robust I/O + math)
# -------------------------
 
def clamp01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))
 
def safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)
 
def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
 
def parse_fecha_series(s: pd.Series) -> pd.Series:
    """
    Parsea fechas tipo: "Dec 5, 2025 · 9:10 AM UTC"
    y elimina timezone para evitar problemas con to_period.
    """
    def _parse_one(x):
        if pd.isna(x):
            return pd.NaT
        try:
            x2 = str(x).replace(" · ", " ")
            dt = dateparser.parse(x2)
            if getattr(dt, "tzinfo", None) is not None:
                dt = dt.replace(tzinfo=None)
            return dt
        except Exception:
            return pd.NaT
    return s.apply(_parse_one)
 
def gini(array: np.ndarray) -> float:
    """Coeficiente de Gini (0=igualitario, 1=muy concentrado)."""
    x = np.array(array, dtype=float)
    x = x[x >= 0]
    if x.size == 0 or np.allclose(x.sum(), 0.0):
        return 0.0
    x = np.sort(x)
    n = x.size
    cum = np.cumsum(x)
    return float((n + 1 - 2 * np.sum(cum) / cum[-1]) / n)
 
def normalized_entropy_from_probs(p: np.ndarray) -> float:
    """Entropía normalizada [0,1] de una distribución p."""
    p = np.array(p, dtype=float)
    p = p[p > 0]
    if p.size <= 1:
        return 0.0
    H = -float(np.sum(p * np.log(p)))
    Hmax = math.log(p.size)
    return float(H / Hmax) if Hmax > 0 else 0.0
 
def normalized_entropy_from_counts(counts: pd.Series) -> float:
    """Entropía normalizada [0,1] desde counts."""
    if counts.sum() <= 0:
        return 0.0
    p = (counts / counts.sum()).values
    return normalized_entropy_from_probs(p)
 
def choose_gmm_components(X: np.ndarray, k_min: int = 3, k_max: int = 6, random_state: int = 42) -> int:
    """
    Elige nº de componentes por BIC dentro de [k_min,k_max],
    con guardrail por tamaño muestral.
    """
    n = X.shape[0]
    feasible_max = min(k_max, max(k_min, n // 10)) if n >= 30 else k_min
    feasible_max = max(k_min, feasible_max)
 
    best_k = k_min
    best_bic = None
    for k in range(k_min, feasible_max + 1):
        try:
            gmm = GaussianMixture(
                n_components=k,
                covariance_type="full",
                random_state=random_state,
                reg_covar=1e-6
            )
            gmm.fit(X)
            bic = gmm.bic(X)
            if best_bic is None or bic < best_bic:
                best_bic = bic
                best_k = k
        except Exception:
            continue
    return best_k
 
def generate_text_report(data):
    """
    Genera un informe narrativo detallado basado en los resultados del modelo.
    Traduce métricas técnicas a lenguaje estratégico para toma de decisiones.
    """
    # Extracción de métricas clave (ajustando escalas)
    prob = data['success_probability'] * 100  # Convertimos 0-1 a 0-100%
    score = data['success_score']             # Ya viene en 0-100
    conf = data['confidence'] * 100           # Convertimos 0-1 a 0-100%
    risks = data['risk_dimensions']
    weights = data['risk_weights_entropy']
    
    # Diccionario de definiciones metodológicas (según PDF)
    DEFINICIONES = {
        "polarization": "Grado de división: mide si la opinión está partida en dos bandos enfrentados.",
        "negativity_momentum": "Tendencia: mide si las críticas están creciendo a gran velocidad.",
        "negative_amplification": "Viralidad: mide si los mensajes negativos se comparten más que los positivos.",
        "negative_influence": "Poder de difusión: mide si las cuentas con muchos seguidores están atacando.",
        "narrative_concentration": "Enfoque de críticas: mide si los ataques se centran en un solo punto débil.",
        "negative_user_concentration": "Efecto eco: mide si las críticas vienen de unos pocos usuarios o de muchos.",
        "negativity_persistence": "Resistencia: mide cuánto tiempo lleva el conflicto activo sin calmarse."
    }

    lines = []
    lines.append("="*90)
    lines.append(f"INFORME ESTRATÉGICO DE VIABILIDAD - MODELO DE PREDICCIÓN")
    lines.append("="*90)
    lines.append(f"Análisis generado el: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Datos: {data['n_posts_relevant']} posts | Ventana: {data['window']} | Fuente: {os.path.basename(data['input'])}")
    lines.append("-" * 90)

    # 1. DIAGNÓSTICO PRINCIPAL (Comparación Aceptación vs Probabilidad)
    lines.append(f"\n[1. DIAGNÓSTICO DE ÉXITO]")
    lines.append(f"-> Aceptación Social Actual (Heurística): {score:.1f}%")
    lines.append(f"-> Probabilidad Real de Éxito (Modelo GMM): {prob:.1f}%")
    
    # Lógica de interpretación de la brecha (Gap Analysis)
    if score > (prob + 15):
        lines.append("\n⚠️ ALERTA: 'FRAGILIDAD OCULTA'. La aceptación parece alta en la superficie,")
        lines.append("   pero el modelo detecta patrones de riesgo que bajan la viabilidad real.")
    elif prob > (score + 15):
        lines.append("\n✅ DIAGNÓSTICO: 'RESILIENCIA'. Aunque hay críticas, la estructura del debate")
        lines.append("   indica que el proyecto tiene una base sólida para resistir y estabilizarse.")
    else:
        lines.append("\nℹ️ ESTADO: 'ESTABILIDAD'. La opinión pública y la viabilidad están alineadas.")

    # 2. ANÁLISIS DE CONFIANZA
    lines.append(f"\n[2. FIABILIDAD DEL PRONÓSTICO]")
    if conf >= 85:
        lines.append(f"🟢 CONFIANZA ALTA ({conf:.1f}%): El volumen de datos es robusto y los patrones")
        lines.append("   son claros. Este informe es una base sólida para tomar decisiones.")
    elif conf >= 55:
        lines.append(f"🟡 CONFIANZA MEDIA ({conf:.1f}%): Existe volatilidad en los datos.")
        lines.append("   Se recomienda no tomar medidas drásticas y observar la tendencia 48h más.")
    else:
        lines.append(f"🔴 CONFIANZA BAJA ({conf:.1f}%): Datos insuficientes o ruido excesivo.")
        lines.append("   El análisis podría estar sesgado por unos pocos posts. Usar con cautela.")

    # 3. RADIOGRAFÍA DE RIESGOS (Basado en Sección 3.1 del PDF)
    lines.append(f"\n[3. RADIOGRAFÍA DE RIESGOS (Escala 0 a 1)]")
    lines.append(f"{'Dimensión de Riesgo':<30} | {'Valor':<6} | {'Estado':<12} | {'Definición'}")
    lines.append("-" * 90)
    
    for k, v in risks.items():
        name_clean = k.replace('_',' ').title()
        # Rangos de alerta
        if v >= 0.8: status = "🚨 CRÍTICO"
        elif v >= 0.4: status = "⚠️ MEDIO"
        else: status = "✅ BAJO"
        
        def_text = DEFINICIONES.get(k, "Sin definición.")
        # Formato correcto para evitar errores de alineación
        lines.append(f"{name_clean:<30} | {v:<6.2f} | {status:<12} | {def_text}")

    # 4. DINÁMICA DE LA CONVERSACIÓN (Interpretación de la Entropía)
    top_weight_key = max(weights, key=weights.get)
    top_risk_key = max(risks, key=risks.get)

    lines.append(f"\n[4. DINÁMICA ESTRUCTURAL]")
    lines.append(f"-> Factor más SENSIBLE: '{top_weight_key.replace('_',' ').title()}'")
    lines.append(f"   (Es la variable que más 'mueve la aguja' del éxito debido a su importancia histórica).")
    
    if risks[top_risk_key] >= 0.7:
        lines.append(f"-> Amenaza más URGENTE: '{top_risk_key.replace('_',' ').title()}'")
        lines.append(f"   (Es el riesgo con valor más alto hoy; es prioritario mitigar esta dimensión).")

    # 5. ESTADO LATENTE (GMM - Sección 2 del PDF)
    if data['pattern_probabilities']:
        # Identificar el patrón dominante
        active_pattern = max(data['pattern_probabilities'], key=data['pattern_probabilities'].get)
        label = data['pattern_labels'].get(active_pattern, "N/A")
        
        lines.append(f"\n[5. PATRÓN DE COMPORTAMIENTO IDENTIFICADO]")
        lines.append(f"El sistema se encuentra en un estado de: {label.upper().replace('_', ' ')}")
        
        if "high_risk" in label.lower():
            lines.append("Análisis: El debate ha entrado en una fase crítica de rechazo estructural.")
        elif "low_risk" in label.lower():
            lines.append("Análisis: El debate se mantiene dentro de los parámetros de aceptación normal.")

    lines.append("\n" + "="*90)
    lines.append("INFORME GENERADO AUTOMÁTICAMENTE - BASADO EN JUSTIFICACIÓN METODOLÓGICA GMM + ENTROPÍA")
    lines.append("="*90)
    
    return "\n".join(lines)

# -------------------------
# Config
# -------------------------
 
@dataclass
class SuccessConfig:
    window: str = "W"
    min_posts_for_any_score: int = 30
    random_state: int = 42

    # Column aliases
    col_text: Tuple[str, ...] = ("contenido", "CONTENIDO")
    col_date: Tuple[str, ...] = ("fecha", "FECHA")
    col_user: Tuple[str, ...] = ("usuario", "ID")
    col_followers: Tuple[str, ...] = ("followers", "FOLLOWERS")
    col_topic: Tuple[str, ...] = ("Topic_1", "TOPIC")
    col_sentiment: Tuple[str, ...] = ("Sentimiento_1", "SENTIMIENTO")

    engagement_cols: Tuple[str, ...] = (
        "retweets", "RETWEETS",
        "quotes", "QUOTES",
        "comments", "COMMENTS",
        "hearts", "HEARTS",
        "likes", "LIKES",
        "shares", "SHARES", "FOLLOWERS", "followers"
    ) 
 
# -------------------------
# Robust input reading
# -------------------------
 
def load_input(path: str) -> pd.DataFrame:
    """
    Lee CSV/JSON de forma robusta:
    - encodings típicos Windows/Excel
    - separador ',' o ';'
    - motor python y on_bad_lines para CSVs con texto difícil
    """
    if path.lower().endswith(".csv"):
        encodings = ["utf-8", "utf-8-sig", "cp1252", "latin1"]
        attempts = [
            dict(sep=",", engine="c"),
            dict(sep=";", engine="c"),
            dict(sep=",", engine="python"),
            dict(sep=";", engine="python"),
            dict(sep=",", engine="python", on_bad_lines="skip"),
            dict(sep=";", engine="python", on_bad_lines="skip"),
        ]
        last_err = None
 
        for enc in encodings:
            for opts in attempts:
                try:
                    return pd.read_csv(
                        path,
                        encoding=enc,
                        quotechar='"',
                        escapechar="\\",
                        **opts,
                    )
                except UnicodeDecodeError as e:
                    last_err = e
                    break
                except pd.errors.ParserError as e:
                    last_err = e
                    continue
                except Exception as e:
                    last_err = e
                    continue
 
        raise RuntimeError(f"No se pudo leer el CSV de forma robusta. Último error: {last_err}")
 
    if path.lower().endswith(".json"):
        try:
            return pd.read_json(path, lines=True)
        except Exception:
            return pd.read_json(path)
 
    raise ValueError(f"Formato no soportado: {path}. Usa .csv o .json")
 
 
# -------------------------
# Feature engineering
# -------------------------
 
def detect_pillar_cols(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if c.lower().startswith("sent_")]
 
def filter_relevant_rows(df: pd.DataFrame, pillar_cols: List[str]) -> pd.DataFrame:
    """
    Conserva solo filas con al menos un pilar sent_* == -1 o +1.
    """
    if not pillar_cols:
        return df.copy()
    mat = df[pillar_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    mask = (mat == -1).any(axis=1) | (mat == 1).any(axis=1)
    return df.loc[mask].copy()
 
def compute_post_acceptance(df: pd.DataFrame, pillar_cols: List[str]) -> pd.Series:
    """
    acceptance por post = media de pilares solo en {-1,+1}; ignora 0 y 2.
    """
    if not pillar_cols:
        return pd.Series(np.nan, index=df.index)
    mat = df[pillar_cols].apply(pd.to_numeric, errors="coerce")
    mat = mat.where(mat.isin([-1, 1]), np.nan) # Si un pilar tiene un 0 (neutro) o un 2 (no aplica), esta línea lo borra y lo convierte en NaN
    return mat.mean(axis=1, skipna=True) # Calcula la media solo con los pilares que quedaron como -1 o +1, ignorando los NaN (que eran 0 o 2)
    # Ejemplo Justicia=1, Legitimidad=NaN, Efectividad=1 -> acceptance = (1 + 1) / 2 = 1.0
 
def compute_engagement(df: pd.DataFrame, cfg: SuccessConfig) -> pd.Series:
    parts = []
    for c in cfg.engagement_cols:
        if c in df.columns:
            parts.append(safe_numeric(df[c]))
    if not parts:
        return pd.Series(0.0, index=df.index)
    return sum(parts)
 
def aggregate_window_features(df: pd.DataFrame, cfg: SuccessConfig, pillar_cols: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Devuelve:
      - ts: features agregadas por ventana (para GMM / score)
      - post_df: posts enriquecidos (para export)
    """
    df = df.copy()
 
    # Resolver columnas reales
    col_date = resolve_column(df, cfg.col_date, "fecha")
    col_sentiment = resolve_column(df, cfg.col_sentiment, "sentimiento")
    col_followers = resolve_column(df, cfg.col_followers, "followers")

    col_user = None
    for c in cfg.col_user:
        if c in df.columns:
            col_user = c
            break

    col_topic = None
    for c in cfg.col_topic:
        if c in df.columns:
            col_topic = c
            break

    col_text = None
    for c in cfg.col_text:
        if c in df.columns:
            col_text = c
            break

    # Ahora sí usar las columnas resueltas
    df["dt"] = parse_fecha_series(df[col_date])
    df = df.dropna(subset=["dt"])
 
    df["followers"] = safe_numeric(df[col_followers])
    df["sentiment"] = safe_numeric(df[col_sentiment])
    df["post_acceptance"] = compute_post_acceptance(df, pillar_cols).fillna(0.0)
    df["engagement"] = compute_engagement(df, cfg)
 
    df["is_negative"] = (df["sentiment"] < 0) | (df["post_acceptance"] < 0) # Falso si ambos son positivos o neutros; Verdadero si alguno es negativo
 
    df["window"] = df["dt"].dt.to_period(cfg.window).dt.start_time
 
    df["w_follow"] = np.log1p(df["followers"]) # Logaritmo Natural de (1 + followers)
    df["neg_w_follow"] = df["w_follow"] * df["is_negative"].astype(float) #Solo los post críticos tienen valor. Los que apoyan la medida "valen cero" en esta columna.
 
    df["neg_eng"] = df["engagement"] * df["is_negative"].astype(float) # Amplificación Negativa: solo el engagement de los posts negativos cuenta para esta métrica.
 
    topic_col = col_topic
 
    rows = []
    for w, g in df.groupby("window"):
        n = len(g)
        if n == 0:
            continue
 
        neg_share = float(g["is_negative"].mean())
        sent_mean = float(g["sentiment"].mean())
        acc_mean = float(g["post_acceptance"].mean())
        acc_var = float(g["post_acceptance"].var(ddof=0)) if n > 1 else 0.0 # Varianza poblacional (ddof=0) para evitar división por cero cuando n=1, si usamos la varianza muestral (ddof=1) con n=1, el resultado sería NaN, lo cual no es deseable. Con ddof=0, si n=1, la varianza se calcula normalmente y da un resultado numérico.
        # La varianza (nos indica cuánta pelea hay, la asimetría nos dice hacia qué lado se inclina la "cola" de la discusión)
        # Coeficiente de asimetría de Fisher (skewness): mide la asimetría de la distribución de aceptación. Un valor positivo indica una cola más larga hacia la derecha (más posts con alta aceptación), mientras que un valor negativo indica una cola más larga hacia la izquierda (más posts con baja aceptación). Un valor cercano a cero sugiere una distribución simétrica.
        acc_skew = float(skew(g["post_acceptance"].values)) if n > 2 else 0.0 # Skewness requiere al menos 3 puntos para ser significativo; con 2 o menos, lo tratamos como 0 (simétrico).
        # Límite de skeeness: +- \sqrt(n).
        eng_total = float(g["engagement"].sum())
        eng_neg = float(g["neg_eng"].sum())
        amp_neg_ratio = float(eng_neg / eng_total) if eng_total > 0 else 0.0
 
        wsum = float(g["w_follow"].sum())
        infl_neg_ratio = float(g["neg_w_follow"].sum() / wsum) if wsum > 0 else 0.0
 
        if col_user is not None:
            neg_g = g[g["is_negative"]] # Filtra para quedarse solo con los post negativos de la ventana actual. Esto es porque queremos medir la concentración de usuarios que están criticando.
            if len(neg_g) > 0:
                counts = neg_g[col_user].value_counts()
                user_gini_neg = gini(counts.values) if len(counts) else 0.0 # Concentración de usuarios negativos. Rebelión de la mayoría (Gini bajo) o a una campaña de desprestigio de unos pocos (Gini alto). 
            else:
                user_gini_neg = 0.0
        else:
            user_gini_neg = 0.0
        
        topic_entropy = 0.0
        topic_conc_risk = 0.0
        if topic_col:
            neg_g = g[g["is_negative"]]
            if len(neg_g) > 0:
                tcounts = neg_g[topic_col].fillna("NA").value_counts()
                # Para la Entropía calculamos Frecuencia Relativa (pi): Es la "porción del pastel" que ocupa cada tópico. Se calcula dividiendo el recuento de cada topic entre el total de posts
                # H/Hmax = ​ −∑pi​ln(pi​) / ln(N) donde N es el número de topics distintos. Esto nos da una medida de cuán dispersa o concentrada está la discusión en torno a los diferentes tópicos. Un valor cercano a 1 indica que la discusión está muy dispersa entre muchos tópicos, mientras que un valor cercano a 0 indica que la discusión está muy concentrada en unos pocos tópicos.
                topic_entropy = normalized_entropy_from_counts(tcounts) # 
                topic_conc_risk = float(1.0 - topic_entropy)
 
        rows.append({
            "window": w,
            "n_posts": int(n),
            "neg_share": neg_share,
            "sent_mean": sent_mean,
            "acc_mean": acc_mean,
            "acc_var": acc_var,
            "acc_skew": acc_skew,
            "amp_neg_ratio": amp_neg_ratio,
            "infl_neg_ratio": infl_neg_ratio,
            "user_gini_neg": float(user_gini_neg),
            "topic_entropy_neg": float(topic_entropy),
            "topic_conc_risk": float(topic_conc_risk),
        })
 
    ts = pd.DataFrame(rows).sort_values("window").reset_index(drop=True)
 
    if len(ts) >= 3:
        # t representa el eje X (tiempo/ventanas). Usamos Regresión Lineal (Grado 1) para hallar la tendencia global.
        t = np.arange(len(ts), dtype=float)

        # neg_momentum: Es el "velocímetro de la crisis". 
        # Calcula la pendiente (m) de la proporción de negativos. 
        # Si > 0: El rechazo social está escalando y ganando terreno.
        # Si < 0: La crisis se está desinflando (buena señal para el éxito).
        ts["neg_momentum"] = float(np.polyfit(t, ts["neg_share"].values, 1)[0])
        
        # acc_momentum: Es el "sensor de erosión del apoyo".
        # Calcula la pendiente de la aceptación media (pilares de justicia, legitimidad, etc.).
        # Si < 0: Indica que los argumentos a favor están perdiendo fuerza o la gente se está radicalizando.
        # Es una métrica predictiva: un valor muy negativo avisa de un colapso de viabilidad inminente.
        ts["acc_momentum"] = float(np.polyfit(t, ts["acc_mean"].values, 1)[0])
    else:
        ts["neg_momentum"] = 0.0
        ts["acc_momentum"] = 0.0
 
    persist = 0
    for x in ts["neg_share"].iloc[::-1].values: # ordenamos empezamos por el día más reciente y vamos hacia atrás en el tiempo.
        if x > 0.5: # ¿Es la mayoría de la conversación negativa (> 50%)?
            persist += 1  # Si sí, sumamos un día a la racha.
        else:
            break # En cuanto encontramos un día "bueno", la racha se rompe y paramos de contar.
    ts["neg_persistence_tail"] = int(persist)
 
    # post_df export (contenido first)
    cols = []
    if col_text is not None:
        cols.append(col_text)

    cols += ["dt", "window"]

    if col_user is not None:
        cols.append(col_user)
    cols += ["followers", "sentiment", "post_acceptance", "is_negative", "engagement"]
 
    post_df = df[cols].copy()
    if topic_col:
        post_df[topic_col] = df[topic_col]
 
    for c in cfg.engagement_cols:
        if c in df.columns:
            post_df[c] = safe_numeric(df[c])
 
    if col_text is not None and col_text in post_df.columns:
        first = [col_text]
        rest = [c for c in post_df.columns if c != col_text]
        post_df = post_df[first + rest]
 
    return ts, post_df
 
 
# -------------------------
# Risk dimensions (from features) + Entropy weights
# -------------------------
 
RISK_DIM_ORDER = [
    "polarization",
    "negativity_momentum",
    "negative_amplification",
    "negative_influence",
    "narrative_concentration",
    "negative_user_concentration",
    "negativity_persistence",
]
 
def risk_dimensions_from_row(row: pd.Series) -> Dict[str, float]:
    """
    Convierte features -> dimensiones de riesgo normalizadas aprox [0,1]
    """
    polarization = min(1.0, float(row.get("acc_var", 0.0)) / 0.50)
    momentum_neg = sigmoid(6.0 * float(row.get("neg_momentum", 0.0)))
    amplification = min(1.0, float(row.get("amp_neg_ratio", 0.0)))
    influence = min(1.0, float(row.get("infl_neg_ratio", 0.0)))
    narrative = min(1.0, float(row.get("topic_conc_risk", 0.0)))
    user_conc = min(1.0, float(row.get("user_gini_neg", 0.0)))
    persistence = min(1.0, float(row.get("neg_persistence_tail", 0.0)) / 4.0)
 
    return {
        "polarization": float(polarization),
        "negativity_momentum": float(momentum_neg),
        "negative_amplification": float(amplification),
        "negative_influence": float(influence),
        "narrative_concentration": float(narrative),
        "negative_user_concentration": float(user_conc),
        "negativity_persistence": float(persistence),
    }
 
def entropy_weights_from_history(history_features: pd.DataFrame) -> Dict[str, float]:
    """
    Entropy weighting (objetivo, no supervisado) sobre las DIMENSIONES DE RIESGO.
 
    Pasos:
      1) calcular riesgos por ventana: r_{t,j} in [0,1]
      2) min-max por columna -> z_{t,j} in [0,1]
      3) p_{t,j} = z_{t,j} / sum_t z_{t,j}
      4) E_j = -sum_t p_{t,j} log(p_{t,j}) / log(T)
      5) d_j = 1 - E_j
      6) w_j = d_j / sum_j d_j
    """
    if history_features is None or len(history_features) < 3:
        # Muy poco histórico -> pesos iguales
        m = len(RISK_DIM_ORDER)
        return {k: 1.0 / m for k in RISK_DIM_ORDER}
 
    # 1) construir matriz de riesgos por ventana
    R = []
    for _, row in history_features.iterrows():
        r = risk_dimensions_from_row(row)
        R.append([r[k] for k in RISK_DIM_ORDER])
    R = np.array(R, dtype=float)  # shape (T, m)
 
    T, m = R.shape
    if T < 3:
        return {k: 1.0 / m for k in RISK_DIM_ORDER}
 
    # 2) min-max por columna
    Z = np.zeros_like(R)
    for j in range(m):
        col = R[:, j]
        cmin = float(np.min(col))
        cmax = float(np.max(col))
        if math.isclose(cmax, cmin):
            Z[:, j] = 0.0
        else:
            Z[:, j] = (col - cmin) / (cmax - cmin)
 
    # 3) p_{t,j}
    eps = 1e-12
    P = np.zeros_like(Z)
    for j in range(m):
        s = float(np.sum(Z[:, j]))
        if s <= eps:
            # Sin variación/información -> distribución uniforme (entropía máxima)
            P[:, j] = 1.0 / T
        else:
            P[:, j] = Z[:, j] / s
 
    # 4) entropía normalizada por dimensión
    logT = math.log(T) if T > 1 else 1.0
    E = np.zeros(m, dtype=float)
    for j in range(m):
        pj = P[:, j]
        pj = np.clip(pj, eps, 1.0)  # evita log(0)
        Hj = -float(np.sum(pj * np.log(pj)))
        E[j] = float(Hj / logT) if logT > 0 else 1.0
        E[j] = clamp01(E[j])
 
    # 5) d_j = 1 - E_j
    d = 1.0 - E
    d = np.clip(d, 0.0, None)
 
    # 6) pesos
    denom = float(np.sum(d))
    if denom <= eps:
        # Si todo parece igual de "no informativo", pesos iguales
        return {k: 1.0 / m for k in RISK_DIM_ORDER}
 
    w = d / denom
    return {RISK_DIM_ORDER[j]: float(w[j]) for j in range(m)}
 
 
# -------------------------
# Heuristic risk + score (NOW uses entropy weights)
# -------------------------
 
def compute_success_score(row: pd.Series, weights: Dict[str, float]) -> Tuple[float, Dict[str, float], float]:
    """
    risk_total = sum_j w_j * risk_j   (w_j aprendidos por entropy weighting)
    success_score = 100*(1-risk_total)
    """
    risks = risk_dimensions_from_row(row)
 
    # garantizar pesos para todas las keys
    w = {k: float(weights.get(k, 0.0)) for k in RISK_DIM_ORDER}
    s = sum(w.values())
    if s <= 0:
        # fallback pesos iguales
        m = len(RISK_DIM_ORDER)
        w = {k: 1.0 / m for k in RISK_DIM_ORDER}
    else:
        # renormaliza por si acaso
        w = {k: v / s for k, v in w.items()}
 
    risk_total = float(sum(risks[k] * w[k] for k in RISK_DIM_ORDER))
    risk_total = clamp01(risk_total)
 
    success_score = float(100.0 * (1.0 - risk_total))
    success_score = max(0.0, min(100.0, success_score))
    return success_score, risks, risk_total
 
 
# -------------------------
# GMM training + probabilities
# -------------------------
 
def train_gmm_and_save(history_features: pd.DataFrame, model_path: str, cfg: SuccessConfig):
    feature_cols = [
        "neg_share", "sent_mean", "acc_mean", "acc_var", "acc_skew",
        "amp_neg_ratio", "infl_neg_ratio", "user_gini_neg", "topic_conc_risk",
        "neg_momentum", "acc_momentum", "neg_persistence_tail"
    ]
    H = history_features.dropna(subset=feature_cols).copy()
    if len(H) < 10:
        return None, None, feature_cols
 
    X = H[feature_cols].values
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
 
    k = choose_gmm_components(Xs, k_min=3, k_max=6, random_state=cfg.random_state)
    gmm = GaussianMixture(n_components=k, covariance_type="full", random_state=cfg.random_state, reg_covar=1e-6)
    gmm.fit(Xs)
 
    dump({"scaler": scaler, "gmm": gmm, "feature_cols": feature_cols}, model_path)
    return scaler, gmm, feature_cols
 
def gmm_probabilities(timeseries: pd.DataFrame, scaler: StandardScaler, gmm: GaussianMixture, feature_cols: List[str]) -> np.ndarray:
    X = timeseries[feature_cols].fillna(0.0).values
    Xs = scaler.transform(X)
    return gmm.predict_proba(Xs)
 
def compute_component_intrinsic_risk(
    scaler: StandardScaler,
    gmm: GaussianMixture,
    feature_cols: List[str],
    weights: Dict[str, float],
) -> np.ndarray:
    """
    Para cada componente k:
      - tomamos su media (centro) en el espacio original
      - calculamos risk_k con los PESOS ENTROPY
    """
    means_scaled = gmm.means_
    means = scaler.inverse_transform(means_scaled)
    idx = {name: j for j, name in enumerate(feature_cols)}
 
    risks_out = []
    for i in range(means.shape[0]):
        row_min = pd.Series({
            "acc_var": float(means[i, idx.get("acc_var", 0)]) if "acc_var" in idx else 0.0,
            "neg_momentum": float(means[i, idx.get("neg_momentum", 0)]) if "neg_momentum" in idx else 0.0,
            "amp_neg_ratio": float(means[i, idx.get("amp_neg_ratio", 0)]) if "amp_neg_ratio" in idx else 0.0,
            "infl_neg_ratio": float(means[i, idx.get("infl_neg_ratio", 0)]) if "infl_neg_ratio" in idx else 0.0,
            "topic_conc_risk": float(means[i, idx.get("topic_conc_risk", 0)]) if "topic_conc_risk" in idx else 0.0,
            "user_gini_neg": float(means[i, idx.get("user_gini_neg", 0)]) if "user_gini_neg" in idx else 0.0,
            "neg_persistence_tail": float(means[i, idx.get("neg_persistence_tail", 0)]) if "neg_persistence_tail" in idx else 0.0,
        })
        _, _, risk_total = compute_success_score(row_min, weights)
        risks_out.append(risk_total)
 
    return np.array(risks_out, dtype=float)
 
def label_patterns_and_success_probability(probs_last: np.ndarray, component_risk: np.ndarray):
    k = probs_last.shape[0]
    pattern_probs = {f"pattern_{i+1}": float(probs_last[i]) for i in range(k)}
 
    order = np.argsort(component_risk)  # low -> high
    labels = ["medium_risk"] * k
    if k == 2:
        labels[order[0]] = "low_risk"
        labels[order[1]] = "high_risk"
    elif k >= 3:
        low_cut = max(1, k // 3)
        high_cut = max(1, k // 3)
        for idx_ in order[:low_cut]:
            labels[idx_] = "low_risk"
        for idx_ in order[-high_cut:]:
            labels[idx_] = "high_risk"
 
    pattern_labels = {f"pattern_{i+1}": labels[i] for i in range(k)}
 
    success_prob = float(np.sum(probs_last * (1.0 - component_risk)))
    success_prob = clamp01(success_prob)
    return pattern_probs, pattern_labels, success_prob
 
 
# -------------------------
# Uncertainty (simple)
# -------------------------
 
def compute_uncertainty_bayesian_simple(n_posts_relevant: int, probs_last: Optional[np.ndarray]) -> Dict[str, float]:
    """
    size_uncertainty    = 1/sqrt(n)
    pattern_uncertainty = entropía normalizada de P(pattern|x_last)
    uncertainty         = sqrt(size^2 + pattern^2) recortada a [0,1]
    confidence          = 1 - uncertainty
    """
    n = max(0, int(n_posts_relevant))
    size_u = 1.0 if n <= 0 else float(1.0 / math.sqrt(n))
    size_u = clamp01(size_u)
 
    if probs_last is None or len(probs_last) <= 1:
        pattern_u = 1.0
    else:
        pattern_u = float(normalized_entropy_from_probs(probs_last))
    pattern_u = clamp01(pattern_u)
 
    u = float(math.sqrt(size_u ** 2 + pattern_u ** 2))
    u = clamp01(u)
 
    return {
        "uncertainty": u,
        "confidence": float(1.0 - u),
        "size_uncertainty": size_u,
        "pattern_uncertainty": pattern_u,
    }
 
 
# -------------------------
# Plot
# -------------------------
 
def make_plot(ts: pd.DataFrame, outpath: str):
    plt.figure()
    plt.plot(ts["window"], ts["success_probability"], label="success_probability (0-1)")
    plt.plot(ts["window"], ts["success_score"] / 100.0, label="success_score/100")
    plt.xticks(rotation=45, ha="right")
    plt.xlabel("Ventana temporal")
    plt.ylabel("Probabilidad / score normalizado")
    plt.legend()
    plt.tight_layout()
    plt.savefig(outpath, dpi=160)
    plt.close()
 
 
# -------------------------
# Main
# -------------------------
 
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Ruta al CSV/JSON analizado")
    parser.add_argument("--outdir", required=True, help="Carpeta de salida")
    parser.add_argument("--window", default=None, help="Ventana temporal: W (semanal), D (diaria), M (mensual)")
    parser.add_argument("--history", default=None, help="Ruta al histórico features (csv). Si no se da, se crea en outdir.")
    parser.add_argument("--model", default=None, help="Ruta al modelo joblib. Si no se da, se crea en outdir.")
    args = parser.parse_args()
 
    clean_window = str(args.window).strip().strip('"').strip("'")

    # 1) Load input (MOVER AQUÍ)
    df = load_input(args.input)

    # --- BLOQUE DE SUGERENCIA AUTOMÁTICA ---
    # Usamos la columna de fecha configurada en SuccessConfig (por defecto 'fecha')
    cfg_tmp = SuccessConfig(window=clean_window)

    # 2) Filter relevant
    pillar_cols = detect_pillar_cols(df)
    df_rel = filter_relevant_rows(df, pillar_cols)
    n_total = int(len(df_rel))

    if args.window is not None:
        final_window = args.window.upper()
        print(f" -> Usando ventana definida en argumentos: {final_window}")
    else:
        # Aquí va el bloque interactivo del input()
        sugg, days, n_posts, dens, reason = suggest_window(df_rel, cfg_tmp)
        
        print(f"\n" + "="*60)
        print(f" ANALIZADOR DE DATOS: Sugerencia de Ventana Temporal")
        print(f" ="*60)
        print(f" -> Datos RELEVANTES detectados: {n_posts} posts en {days} días.")
        print(f" -> Densidad REAL: {dens:.2f} posts/día.")
        print(f" -> Sugerencia: Usar ventana '{sugg}' porque {reason}")
        print(f" " + "-"*60)
        
        # 2) Preguntar al usuario (Interacción)
        print(" ¿Qué ventana quieres aplicar para el cálculo de Éxito?")
        print(f" [D] DIARIA:  Recomendada para ver el impacto día a día ({days} puntos).")
        print(f" [W] SEMANAL: Agrupa por semanas (tendrías {max(1, days//7)} puntos).")
        print(f" [M] MENSUAL: Visión estratégica a largo plazo.")
        
        # Esta línea detiene el código y espera tu teclado
        user_choice = input(f"\n Selecciona [D/W/M] (ENTER para '{sugg}'): ").strip().upper()
        final_window = user_choice if user_choice in ["D", "W", "M"] else sugg
    
    print("="*70 + "\n")

    # 4) Actualizar la configuración con la decisión final
    cfg = SuccessConfig(window=final_window)
 
    os.makedirs(args.outdir, exist_ok=True)
    history_path = args.history or os.path.join(args.outdir, "success_history_features.csv")
    model_path = args.model or os.path.join(args.outdir, "success_model.joblib")
 
    
 
    # 3) Aggregate window features (NO score yet)
    ts, post_df = aggregate_window_features(df_rel, cfg, pillar_cols)
 
    if len(ts) == 0:
        report = {
            "input": args.input,
            "n_posts_relevant": n_total,
            "window": cfg.window,
            "success_probability": None,
            "success_score": None,
            "risk_dimensions": None,
            "risk_weights_entropy": None,
            "pattern_probabilities": None,
            "pattern_labels": None,
            "uncertainty": 1.0,
            "confidence": 0.0,
            "note": "No hay datos suficientes tras filtrar (sin fechas válidas o sin filas relevantes).",
        }
        with open(os.path.join(args.outdir, "report_success.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return
 
    # 4) Historical accumulation (robust read)
    hist_append = ts.copy()
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8", errors="ignore") as f:
                hist_prev = pd.read_csv(f)
        except Exception:
            hist_prev = pd.read_csv(history_path)
 
        merged = pd.concat([hist_prev, hist_append], ignore_index=True)
        merged = merged.drop_duplicates(subset=["window"], keep="last")
        history_features = merged
    else:
        history_features = hist_append
 
    history_features.to_csv(history_path, index=False)
 
    # 5) Compute ENTROPY weights from history
    risk_weights = entropy_weights_from_history(history_features)
 
    # also export weights
    w_csv = os.path.join(args.outdir, "risk_weights_entropy.csv")
    pd.DataFrame([risk_weights]).to_csv(w_csv, index=False)
 
    # 6) Now compute success_score per window using entropy weights
    risks_list = []
    scores = []
    risk_totals = []
    for _, row in ts.iterrows():
        sc, risks, rtot = compute_success_score(row, risk_weights)
        scores.append(sc)
        risks_list.append(risks)
        risk_totals.append(rtot)
    ts["success_score"] = scores
    ts["risk_total"] = risk_totals
 
    # 7) GMM
    scaler, gmm, feature_cols = train_gmm_and_save(history_features, model_path, cfg)
 
    pattern_probs_dict = None
    pattern_labels_dict = None
    success_probability_last = None
    probs_last = None
 
    if scaler is not None and gmm is not None:
        probs = gmm_probabilities(ts, scaler, gmm, feature_cols)  # (n_windows, K)
        for k in range(probs.shape[1]):
            ts[f"pattern_p{k+1}"] = probs[:, k]
 
        probs_last = probs[-1, :]
        component_risk = compute_component_intrinsic_risk(scaler, gmm, feature_cols, risk_weights)
 
        pattern_probs_dict, pattern_labels_dict, success_probability_last = label_patterns_and_success_probability(
            probs_last=probs_last,
            component_risk=component_risk
        )
 
        success_prob_series = np.sum(probs * (1.0 - component_risk.reshape(1, -1)), axis=1)
        ts["success_probability"] = np.clip(success_prob_series, 0.0, 1.0)
    else:
        ts["success_probability"] = np.clip(ts["success_score"].values / 100.0, 0.0, 1.0)
        success_probability_last = float(ts["success_probability"].iloc[-1])
        probs_last = None
 
    # 8) Summary = última ventana
    overall_success_score = float(ts["success_score"].iloc[-1])
    overall_success_probability = float(success_probability_last)
    overall_risks = {k: float(v) for k, v in risks_list[-1].items()}
 
    # 9) Uncertainty
    unc = compute_uncertainty_bayesian_simple(n_total, probs_last)
 
    note = None
    if n_total < cfg.min_posts_for_any_score:
        note = f"Pocos posts relevantes (n={n_total} < {cfg.min_posts_for_any_score}). Interpretar con cautela."
 
    report = {
        "input": args.input,
        "n_posts_relevant": n_total,
        "window": cfg.window,
        "success_probability": overall_success_probability,
        "success_score": overall_success_score,
        "risk_dimensions": overall_risks,
        "risk_weights_entropy": {k: float(v) for k, v in risk_weights.items()},
        "pattern_probabilities": pattern_probs_dict,
        "pattern_labels": pattern_labels_dict,
        **unc,
        "note": note,
    }
 
    # 10) Save outputs
    out_json = os.path.join(args.outdir, "report_success.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
 
    out_ts_csv = os.path.join(args.outdir, "success_timeseries.csv")
    ts.to_csv(out_ts_csv, index=False)
 
    out_posts_csv = os.path.join(args.outdir, "success_posts_enriched.csv")
    post_df.to_csv(out_posts_csv, index=False)
 
    out_png = os.path.join(args.outdir, "success_plot.png")
    make_plot(ts, out_png)

    # 11) Generar y Guardar Reporte de Lectura Humana
    report_text = generate_text_report(report)
    out_txt = os.path.join(args.outdir, "REPORTE_LECTURA.txt")
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"[OK] Reporte narrativo: {out_txt}")
    print(f"[OK] Report: {out_json}")
    print(f"[OK] Timeseries: {out_ts_csv}")
    print(f"[OK] Posts enriched: {out_posts_csv}")
    print(f"[OK] Plot: {out_png}")
    print(f"[OK] History features: {history_path}")
    print(f"[OK] Model (if trained): {model_path}")
    print(f"[OK] Entropy weights: {w_csv}")
 
 
if __name__ == "__main__":

    DEBUG = True   # ← cambiamos a True cuando queremos debuggear localmente con rutas hardcodeadas

    # -----------------------------------------------------------------------------------------
    # GUÍA RÁPIDA DE DEPURACIÓN (Debugger shortcuts en VS Code):
    # -----------------------------------------------------------------------------------------
    # F10 (Step Over):  Avanza a la siguiente línea del 'main' (pasa por encima de las funciones).
    #                   Úsalo para avanzar rápido sin perderte en los detalles internos.
    #
    # F11 (Step Into):  Entra "dentro" de la función (ej. suggest_window o compute_success_score).
    #                   Úsalo para ver cómo se calculan los riesgos y la probabilidad paso a paso.
    #
    # Shift + F11 (Step Out): Termina la función actual y te devuelve a la línea del 'main'.
    #                         Úsalo cuando ya hayas visto lo que querías dentro de una función.
    #
    # F5 (Continue):    Ejecuta el código de golpe hasta el siguiente punto de interrupción 
    #                   (punto rojo) o hasta que el análisis termine por completo.
    # -----------------------------------------------------------------------------------------

    if DEBUG:
        import sys
        sys.argv = [
            "./david_pred_model.py",
            "--input", "C:\\Users\\DATS004\\Dropbox\\14. DS4M - Social Media Research\\git\\project_web\\Web_Proyecto\\datos\\admin\\martes24b\\datos_con_pilares.csv",
            "--outdir", "C:\\Users\\DATS004\\Dropbox\\14. DS4M - Social Media Research\\git\\project_web\\Web_Proyecto\\datos\\admin\\martes24b\\success_output",
            #"--window", "W"
        ]
    main()