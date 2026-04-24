"""
Calculadora de ScoreOP (Score de Posición Social).
Implementación de da Silva (2021) + Oueslati (2023).
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Tuple


class ScoreOPCalculator:
    """
    Calcula Score de Posición Social ponderado por esfuerzo social.
    
    ScoreOP(Post) = 0.4 × [Stance(Post) × I(Post)] + 
                    0.6 × Σ [Stance(Comment) × I(Comment)]
    
    Donde:
    - I(x) = Impacto = (R × W_reac) + (S × W_comp) + (C × W_comm)
    - W = Pesos dinámicos (TSE / M) / Total_Métrica
    """
    
    def __init__(self, plataforma: str):
        """
        Args:
            plataforma: 'reddit', 'youtube', 'bluesky'
        """
        self.plataforma = plataforma
        self.config = self._get_platform_config()
    
    def _get_platform_config(self) -> Dict:
        """Configuración de métricas por plataforma"""
        configs = {
            'reddit': {
                'M': 1,  # Solo comentarios (upvotes son netos)
                'col_reacciones': None,
                'col_compartidos': None,
                'col_comentarios': 'comments'
            },
            'youtube': {
                'M': 2,  # Likes + Comentarios (vistas son pasivas)
                'col_reacciones': 'likes',
                'col_compartidos': None,
                'col_comentarios': 'comentarios'
            },
            'bluesky': {
                'M': 3,  # Likes + Reposts + Replies
                'col_reacciones': 'hearts',
                'col_compartidos': 'retweets',
                'col_comentarios': 'comments'
            }
        }
        return configs.get(self.plataforma.lower(), configs['reddit'])
    
    def calcular_tse_y_pesos(self, df: pd.DataFrame) -> Dict:
        """
        Calcula TSE (Total Sample Engagement) y pesos dinámicos.
        
        Returns:
            {
                'TSE': float,
                'R': float, 'S': float, 'C': float,
                'W_reac': float, 'W_comp': float, 'W_comm': float,
                'M': int
            }
        """
        # Solo contenido relevante
        df_rel = df[df['llm_relevante'] == 'SI'].copy()
        
        M = self.config['M']
        
        # Totales
        R = S = C = 0
        
        if self.config['col_reacciones']:
            col = self.config['col_reacciones']
            R = df_rel[col].fillna(0).sum() if col in df_rel.columns else 0
        
        if self.config['col_compartidos']:
            col = self.config['col_compartidos']
            S = df_rel[col].fillna(0).sum() if col in df_rel.columns else 0
        
        if self.config['col_comentarios']:
            col = self.config['col_comentarios']
            C = df_rel[col].fillna(0).sum() if col in df_rel.columns else 0
        
        TSE = R + S + C
        
        if TSE == 0:
            return {'TSE': 0, 'R': 0, 'S': 0, 'C': 0, 'W_reac': 0, 'W_comp': 0, 'W_comm': 0, 'M': M}
        
        # Pesos dinámicos: (TSE / M) / Total_Métrica
        W_reac = (TSE / M) / R if R > 0 else 0
        W_comp = (TSE / M) / S if S > 0 else 0
        W_comm = (TSE / M) / C if C > 0 else 0
        
        return {
            'TSE': TSE, 'R': R, 'S': S, 'C': C,
            'W_reac': W_reac, 'W_comp': W_comp, 'W_comm': W_comm,
            'M': M
        }
    
    def calcular_impacto(self, row: pd.Series, pesos: Dict) -> float:
        """
        I(x) = (Metric_R × W_reac) + (Metric_S × W_comp) + (Metric_C × W_comm)
        """
        impacto = 0.0
        
        if self.config['col_reacciones']:
            val = row.get(self.config['col_reacciones'], 0)
            impacto += float(val if pd.notna(val) else 0) * pesos['W_reac']
        
        if self.config['col_compartidos']:
            val = row.get(self.config['col_compartidos'], 0)
            impacto += float(val if pd.notna(val) else 0) * pesos['W_comp']
        
        if self.config['col_comentarios']:
            val = row.get(self.config['col_comentarios'], 0)
            impacto += float(val if pd.notna(val) else 0) * pesos['W_comm']
        
        return impacto
    
    def obtener_stance(self, row: pd.Series) -> int:
        """
        Obtiene stance agregado de pilares.
        Stance ∈ {1, 0, -1}
        """
        pilares = [
            "Legitimación_sociopolítica",
            "Efectividad_percibida",
            "Justicia_y_equidad_percibida",
            "Confianza_institucional",
            "Marcos_discursivos"
        ]
        
        valores = []
        for pilar in pilares:
            if pilar in row:
                val = row[pilar]
                if pd.notna(val) and str(val) in ['1', '-1', '0']:
                    valores.append(int(val))
        
        if not valores:
            return 0
        
        # Mayoría simple
        suma = sum(valores)
        return 1 if suma > 0 else (-1 if suma < 0 else 0)
    
    def calcular_scoreop(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula ScoreOP para cada post.
        
        Returns:
            DataFrame con ScoreOP por post
        """
        # Calcular pesos
        pesos = self.calcular_tse_y_pesos(df)
        
        print(f"\n📊 Pesos dinámicos ({self.plataforma}):")
        print(f"  TSE: {pesos['TSE']:.0f}")
        print(f"  M: {pesos['M']}")
        print(f"  W_reac: {pesos['W_reac']:.4f}")
        print(f"  W_comp: {pesos['W_comp']:.4f}")
        print(f"  W_comm: {pesos['W_comm']:.4f}")
        
        resultados = []
        
        # Posts relevantes
        posts = df[
            (df['tipo_contenido'] == 'Post') &
            (df['llm_relevante'] == 'SI')
        ].copy()
        
        for idx, post_row in posts.iterrows():
            enlace = post_row['enlace']
            
            # Stance e impacto del post
            stance_post = self.obtener_stance(post_row)
            impacto_post = self.calcular_impacto(post_row, pesos)
            
            # Comentarios de este post
            comentarios = df[
                (df['enlace_original'] == enlace) &
                (df['tipo_contenido'] == 'Comentario') &
                (df['llm_relevante'] == 'SI')
            ]
            
            # Suma de comentarios
            suma_comentarios = 0.0
            for _, com_row in comentarios.iterrows():
                stance_com = self.obtener_stance(com_row)
                impacto_com = self.calcular_impacto(com_row, pesos)
                suma_comentarios += stance_com * impacto_com
            
            # ScoreOP = 0.4 × (stance_post × I_post) + 0.6 × Σ(stance_com × I_com)
            scoreop = 0.4 * (stance_post * impacto_post) + 0.6 * suma_comentarios
            
            resultados.append({
                'enlace_post': enlace,
                'contenido_post': post_row['contenido'][:100],
                'stance_post': stance_post,
                'impacto_post': impacto_post,
                'num_comentarios': len(comentarios),
                'suma_impacto_comentarios': suma_comentarios,
                'ScoreOP': scoreop
            })
        
        return pd.DataFrame(resultados)


def calcular_scoreop_completo(config):
    """
    Función principal para calcular ScoreOP en todos los datasets.
    """
    print("\n=== CÁLCULO DE SCOREOP ===")
    
    from clean_project.utils.csv_schema import unify_all_csvs
    
    # 1. Unificar CSVs
    output_folder = config.general["output_folder"]
    csv_unificado = unify_all_csvs(output_folder)
    
    # 2. Cargar datos
    df = pd.read_csv(csv_unificado, sep=';', encoding='utf-8')
    
    # 3. Calcular ScoreOP por plataforma
    resultados_totales = []
    
    for plataforma in df['red_social'].unique():
        print(f"\n📡 Procesando {plataforma}...")
        
        df_plat = df[df['red_social'] == plataforma]
        calculator = ScoreOPCalculator(plataforma)
        
        df_scores = calculator.calcular_scoreop(df_plat)
        df_scores['plataforma'] = plataforma
        
        resultados_totales.append(df_scores)
    
    # 4. Consolidar resultados
    df_final = pd.concat(resultados_totales, ignore_index=True)
    
    # 5. Guardar
    output_path = Path(output_folder) / "scoreop_resultados.csv"
    df_final.to_csv(output_path, index=False, encoding='utf-8', sep=';')
    
    print(f"\n✅ ScoreOP guardado en: {output_path}")
    print(f"\n📈 Top 10 posts por ScoreOP:")
    print(df_final.nlargest(10, 'ScoreOP')[['plataforma', 'contenido_post', 'ScoreOP']])
    
    return df_final


if __name__ == "__main__":
    from types import SimpleNamespace
    
    # Test
    config = SimpleNamespace(
        general={
            "output_folder": "./test_output"
        }
    )
    
    calcular_scoreop_completo(config)