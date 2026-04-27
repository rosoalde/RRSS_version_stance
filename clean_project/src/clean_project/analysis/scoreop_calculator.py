"""
Calculadora de ScoreOP (Score de Posición Social).
Implementación adaptada a las columnas reales del proyecto.
Basado en da Silva (2021) + Oueslati (2023).

IMPORTANTE: Usa la columna 'sentimiento' (no pilares) como stance.
Filtra por sentimiento != 2 (solo analiza contenido relevante: 1, 0, -1)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
import json


class ScoreOPCalculator:
    """
    Calcula Score de Posición Social ponderado por esfuerzo social.
    
    Fórmula:
    ScoreOP(Post) = 0.4 × [Stance(Post) × I(Post)] + 
                    0.6 × Σ [Stance(Comment) × I(Comment)]
    
    Donde:
    - Stance = sentimiento (1, 0, -1)
    - I(x) = Impacto = (R × W_reac) + (S × W_comp) + (C × W_comm)
    - W = Pesos dinámicos: (TSE / M) / Total_Métrica
    - TSE = Total Sample Engagement (solo de contenido con sentimiento != 2)
    """
    
    def __init__(self, plataforma: str):
        """
        Args:
            plataforma: 'reddit', 'youtube', 'bluesky'
        """
        self.plataforma = plataforma.lower()
        self.config = self._get_platform_config()
    
    def _get_platform_config(self) -> Dict:
        """
        Configuración de columnas y métricas por plataforma.
        
        Esquema de columnas:
        - Reddit: tipo, id_raiz, likes, comments
        - YouTube: tipo, id_video, likes, comments
        - Bluesky: tipo, uri, parent_uri, likes, reposts, replies
        """
        configs = {
            'reddit': {
                'M': 1,  # Solo 1 métrica (comments, likes son netos)
                'col_id_post': 'id_raiz',
                'col_id_comentario': 'id_propio',
                'col_reacciones': None,  # Likes son netos (up-down)
                'col_compartidos': None,
                'col_comentarios': 'comments',
                'identificar_post': lambda row: row.get('tipo', '').lower() == 'post',
                'identificar_comentario': lambda row: row.get('tipo', '').lower() in ['comentario', 'comment'],
                'get_post_id': lambda row: row.get('id_raiz'),
                'match_comentario_a_post': lambda com, post: com.get('id_raiz') == post.get('id_raiz')
            },
            'youtube': {
                'M': 2,  # Likes + Comments (vistas son pasivas)
                'col_id_post': 'id_video',
                'col_id_comentario': None,
                'col_reacciones': 'likes',
                'col_compartidos': None,
                'col_comentarios': 'comments',
                'identificar_post': lambda row: row.get('tipo', '').lower() in ['video', 'post'],
                'identificar_comentario': lambda row: row.get('tipo', '').lower() in ['comentario', 'comment'],
                'get_post_id': lambda row: row.get('id_video'),
                'match_comentario_a_post': lambda com, post: com.get('id_video') == post.get('id_video')
            },
            'bluesky': {
                'M': 3,  # Likes + Reposts + Replies
                'col_id_post': 'uri',
                'col_id_comentario': 'uri',
                'col_reacciones': 'likes',
                'col_compartidos': 'reposts',
                'col_comentarios': 'replies',
                'identificar_post': lambda row: row.get('tipo', '').lower() == 'post',
                'identificar_comentario': lambda row: row.get('tipo', '').lower() in ['comentario', 'comment'],
                'get_post_id': lambda row: row.get('uri'),
                'match_comentario_a_post': lambda com, post: com.get('parent_uri') == post.get('uri')
            }
        }
        return configs.get(self.plataforma, configs['reddit'])
    
    def filtrar_contenido_relevante(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filtra solo contenido con sentimiento válido (1, 0, -1).
        Excluye sentimiento = 2 (irrelevante/spam).
        """
        # Convertir sentimiento a numérico
        df['sentimiento_num'] = pd.to_numeric(df['sentimiento'], errors='coerce')
        
        # Filtrar solo sentimiento en {1, 0, -1}
        df_relevante = df[df['sentimiento_num'].isin([1, 0, -1])].copy()
        
        print(f"  📊 Contenido filtrado:")
        print(f"     Total filas: {len(df)}")
        print(f"     Relevantes (sent ∈ {{1,0,-1}}): {len(df_relevante)}")
        print(f"     Excluidos (sent = 2): {len(df) - len(df_relevante)}")
        
        return df_relevante
    
    def calcular_tse_y_pesos(self, df: pd.DataFrame) -> Dict:
        """
        Calcula TSE (Total Sample Engagement) y pesos dinámicos.
        Solo sobre contenido con sentimiento != 2.
        
        TSE = R + S + C (suma de todas las interacciones relevantes)
        W_x = (TSE / M) / Total_x (peso de cada métrica)
        
        Returns:
            {
                'TSE': float,
                'R': float (total reacciones),
                'S': float (total compartidos),
                'C': float (total comentarios),
                'W_reac': float (peso reacciones),
                'W_comp': float (peso compartidos),
                'W_comm': float (peso comentarios),
                'M': int (número de métricas)
            }
        """
        M = self.config['M']
        
        # Calcular totales de cada métrica
        R = 0  # Reacciones (likes)
        S = 0  # Compartidos (shares/reposts)
        C = 0  # Comentarios (replies)
        
        if self.config['col_reacciones']:
            col = self.config['col_reacciones']
            if col in df.columns:
                R = df[col].fillna(0).astype(float).sum()
        
        if self.config['col_compartidos']:
            col = self.config['col_compartidos']
            if col in df.columns:
                S = df[col].fillna(0).astype(float).sum()
        
        if self.config['col_comentarios']:
            col = self.config['col_comentarios']
            if col in df.columns:
                C = df[col].fillna(0).astype(float).sum()
        
        TSE = R + S + C
        
        if TSE == 0:
            print(f"  ⚠️ TSE = 0, no hay engagement")
            return {
                'TSE': 0, 'R': 0, 'S': 0, 'C': 0,
                'W_reac': 0, 'W_comp': 0, 'W_comm': 0,
                'M': M
            }
        
        # Calcular pesos dinámicos: (TSE / M) / Total_Métrica
        # Esto garantiza que cada métrica tenga el mismo peso total en el cálculo final
        W_reac = (TSE / M) / R if R > 0 else 0
        W_comp = (TSE / M) / S if S > 0 else 0
        W_comm = (TSE / M) / C if C > 0 else 0
        
        return {
            'TSE': TSE,
            'R': R,
            'S': S,
            'C': C,
            'W_reac': W_reac,
            'W_comp': W_comp,
            'W_comm': W_comm,
            'M': M
        }
    
    def calcular_impacto(self, row: pd.Series, pesos: Dict) -> float:
        """
        Calcula el impacto I(x) de una unidad de contenido (post o comentario).
        
        I(x) = (Metric_R × W_reac) + (Metric_S × W_comp) + (Metric_C × W_comm)
        
        Args:
            row: Fila del DataFrame (post o comentario)
            pesos: Diccionario con pesos W_reac, W_comp, W_comm
        
        Returns:
            Impacto total (float)
        """
        impacto = 0.0
        
        # Reacciones (likes)
        if self.config['col_reacciones']:
            col = self.config['col_reacciones']
            val = row.get(col, 0)
            if pd.notna(val):
                impacto += float(val) * pesos['W_reac']
        
        # Compartidos (shares/reposts)
        if self.config['col_compartidos']:
            col = self.config['col_compartidos']
            val = row.get(col, 0)
            if pd.notna(val):
                impacto += float(val) * pesos['W_comp']
        
        # Comentarios (replies)
        if self.config['col_comentarios']:
            col = self.config['col_comentarios']
            val = row.get(col, 0)
            if pd.notna(val):
                impacto += float(val) * pesos['W_comm']
        
        return impacto
    
    def obtener_stance(self, row: pd.Series) -> int:
        """
        Obtiene el stance de la fila.
        Stance = sentimiento ∈ {1, 0, -1}
        
        Args:
            row: Fila del DataFrame
        
        Returns:
            1 (positivo), 0 (neutro), -1 (negativo)
        """
        sent = row.get('sentimiento_num', 0)
        
        if pd.notna(sent) and sent in [1, 0, -1]:
            return int(sent)
        
        return 0  # Default neutro
    
    def calcular_scoreop(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula ScoreOP para cada post.
        
        ScoreOP(Post_i) = 0.4 × [Stance(Post_i) × I(Post_i)] + 
                          0.6 × Σ[Stance(Com_k) × I(Com_k)]
        
        Args:
            df: DataFrame con todos los datos (posts + comentarios)
        
        Returns:
            DataFrame con ScoreOP por post
        """
        # 1. Filtrar solo contenido relevante (sentimiento != 2)
        df_rel = self.filtrar_contenido_relevante(df)
        
        if df_rel.empty:
            print(f"  ⚠️ No hay contenido relevante")
            return pd.DataFrame()
        
        # 2. Calcular pesos dinámicos
        pesos = self.calcular_tse_y_pesos(df_rel)
        
        print(f"\n  📊 Pesos dinámicos calculados:")
        print(f"     TSE (Total Engagement): {pesos['TSE']:.0f}")
        print(f"     M (métricas): {pesos['M']}")
        print(f"     R (Reacciones): {pesos['R']:.0f} → W_reac: {pesos['W_reac']:.4f}")
        print(f"     S (Compartidos): {pesos['S']:.0f} → W_comp: {pesos['W_comp']:.4f}")
        print(f"     C (Comentarios): {pesos['C']:.0f} → W_comm: {pesos['W_comm']:.4f}")
        
        # 3. Identificar posts
        posts = df_rel[df_rel.apply(self.config['identificar_post'], axis=1)].copy()
        
        if posts.empty:
            print(f"  ⚠️ No hay posts relevantes")
            return pd.DataFrame()
        
        print(f"\n  🔍 Procesando {len(posts)} posts...")
        
        # 4. Calcular ScoreOP para cada post
        resultados = []
        
        for idx, post_row in posts.iterrows():
            # ID del post
            post_id = self.config['get_post_id'](post_row)
            
            # Stance e impacto del post
            stance_post = self.obtener_stance(post_row)
            impacto_post = self.calcular_impacto(post_row, pesos)
            
            # Encontrar comentarios de este post
            comentarios = df_rel[
                df_rel.apply(self.config['identificar_comentario'], axis=1) &
                df_rel.apply(lambda row: self.config['match_comentario_a_post'](row, post_row), axis=1)
            ]
            
            # Calcular suma ponderada de comentarios
            suma_comentarios = 0.0
            desglose_comentarios = []
            
            for _, com_row in comentarios.iterrows():
                stance_com = self.obtener_stance(com_row)
                impacto_com = self.calcular_impacto(com_row, pesos)
                contribucion = stance_com * impacto_com
                suma_comentarios += contribucion
                
                desglose_comentarios.append({
                    'stance': stance_com,
                    'impacto': impacto_com,
                    'contribucion': contribucion
                })
            
            # Calcular ScoreOP final
            # 40% del post, 60% de los comentarios
            scoreop = 0.4 * (stance_post * impacto_post) + 0.6 * suma_comentarios
            
            resultados.append({
                'post_id': post_id,
                'contenido_post': str(post_row.get('contenido', ''))[:100],
                'fecha': post_row.get('fecha', ''),
                'usuario': post_row.get('usuario', ''),
                'id_anonimo': post_row.get('id_anonimo', ''),
                'stance_post': stance_post,
                'impacto_post': impacto_post,
                'num_comentarios': len(comentarios),
                'suma_impacto_comentarios': suma_comentarios,
                'ScoreOP': scoreop,
                'topic': post_row.get('topic', 'no relacionado')
            })
        
        df_resultado = pd.DataFrame(resultados)
        
        # Estadísticas
        if not df_resultado.empty:
            print(f"\n  ✅ ScoreOP calculado para {len(df_resultado)} posts")
            print(f"     Media: {df_resultado['ScoreOP'].mean():.2f}")
            print(f"     Min: {df_resultado['ScoreOP'].min():.2f}")
            print(f"     Max: {df_resultado['ScoreOP'].max():.2f}")
        
        return df_resultado


def calcular_scoreop_por_dataset(data_folder: str, plataforma: str) -> pd.DataFrame:
    """
    Calcula ScoreOP para un dataset específico.
    
    Args:
        data_folder: Carpeta con los datos
        plataforma: 'reddit', 'youtube', 'bluesky'
    
    Returns:
        DataFrame con ScoreOP por post
    """
    print(f"\n{'='*60}")
    print(f"CALCULANDO SCOREOP: {plataforma.upper()}")
    print(f"{'='*60}")
    
    folder = Path(data_folder)
    
    # Buscar archivo analizado
    archivos_posibles = [
        folder / f"{plataforma}_global_dataset_analizado.csv",
        folder / f"{plataforma}_dataset_analizado.csv",
        folder / f"{plataforma}_analizado.csv"
    ]
    
    archivo = None
    for f in archivos_posibles:
        if f.exists():
            archivo = f
            break
    
    if not archivo:
        print(f"❌ No se encontró archivo analizado para {plataforma}")
        return pd.DataFrame()
    
    print(f"📂 Archivo: {archivo.name}")
    
    # Detectar separador
    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            primera_linea = f.readline()
            sep = ';' if ';' in primera_linea else ','
    except:
        sep = ';'
    
    # Cargar datos
    try:
        df = pd.read_csv(archivo, sep=sep, encoding='utf-8', engine='python')
        print(f"  📊 Filas cargadas: {len(df)}")
    except Exception as e:
        print(f"❌ Error cargando {archivo}: {e}")
        return pd.DataFrame()
    
    # Verificar que tenga columna sentimiento
    if 'sentimiento' not in df.columns:
        print(f"❌ El archivo no tiene columna 'sentimiento'")
        return pd.DataFrame()
    
    # Calcular ScoreOP
    calculator = ScoreOPCalculator(plataforma)
    df_scoreop = calculator.calcular_scoreop(df)
    
    # Añadir plataforma
    if not df_scoreop.empty:
        df_scoreop['plataforma'] = plataforma
    
    return df_scoreop


def calcular_scoreop_completo(data_folder: str, plataformas: List[str] = None) -> Dict:
    """
    Calcula ScoreOP para todas las plataformas.
    
    Args:
        data_folder: Carpeta con los datos
        plataformas: Lista de plataformas ['reddit', 'youtube', 'bluesky']
                     Si es None, intenta todas
    
    Returns:
        {
            'reddit': DataFrame,
            'youtube': DataFrame,
            'bluesky': DataFrame,
            'consolidado': DataFrame (todos juntos)
        }
    """
    if plataformas is None:
        plataformas = ['reddit', 'youtube', 'bluesky']
    
    print(f"\n{'='*70}")
    print(f"CÁLCULO DE SCOREOP - ANÁLISIS COMPLETO")
    print(f"{'='*70}")
    print(f"Carpeta: {data_folder}")
    print(f"Plataformas: {', '.join(plataformas)}")
    
    resultados = {}
    dfs_consolidado = []
    
    for plataforma in plataformas:
        df_scoreop = calcular_scoreop_por_dataset(data_folder, plataforma)
        
        if not df_scoreop.empty:
            resultados[plataforma] = df_scoreop
            dfs_consolidado.append(df_scoreop)
            
            # Guardar resultado individual
            output_path = Path(data_folder) / f"{plataforma}_scoreop.csv"
            df_scoreop.to_csv(output_path, index=False, sep=';', encoding='utf-8')
            print(f"  💾 Guardado: {output_path.name}")
    
    # Consolidar todos los resultados
    if dfs_consolidado:
        df_consolidado = pd.concat(dfs_consolidado, ignore_index=True)
        resultados['consolidado'] = df_consolidado
        
        # Guardar consolidado
        output_consolidado = Path(data_folder) / "scoreop_consolidado.csv"
        df_consolidado.to_csv(output_consolidado, index=False, sep=';', encoding='utf-8')
        
        print(f"\n{'='*70}")
        print(f"✅ SCOREOP COMPLETADO")
        print(f"{'='*70}")
        print(f"  📊 Total posts analizados: {len(df_consolidado)}")
        print(f"  💾 Consolidado: {output_consolidado.name}")
        
        # Top 10 posts por ScoreOP
        print(f"\n  📈 TOP 10 POSTS POR SCOREOP:")
        top10 = df_consolidado.nlargest(10, 'ScoreOP')[
            ['plataforma', 'contenido_post', 'stance_post', 'num_comentarios', 'ScoreOP']
        ]
        for i, row in top10.iterrows():
            print(f"     {i+1}. [{row['plataforma']}] Score={row['ScoreOP']:.2f} | "
                  f"Stance={row['stance_post']:+d} | Coms={row['num_comentarios']} | "
                  f"{row['contenido_post'][:50]}...")
        
        # Guardar resumen en JSON
        resumen = {
            'total_posts': len(df_consolidado),
            'posts_por_plataforma': df_consolidado.groupby('plataforma').size().to_dict(),
            'scoreop_stats': {
                'media': float(df_consolidado['ScoreOP'].mean()),
                'mediana': float(df_consolidado['ScoreOP'].median()),
                'min': float(df_consolidado['ScoreOP'].min()),
                'max': float(df_consolidado['ScoreOP'].max()),
                'std': float(df_consolidado['ScoreOP'].std())
            },
            'top_10_posts': top10.to_dict('records')
        }
        
        resumen_path = Path(data_folder) / "scoreop_resumen.json"
        with open(resumen_path, 'w', encoding='utf-8') as f:
            json.dump(resumen, f, ensure_ascii=False, indent=2)
        
        print(f"  📋 Resumen JSON: {resumen_path.name}")
    
    return resultados


# =====================================================
# INTEGRACIÓN CON LOGICA.PY
# =====================================================

def ejecutar_scoreop_desde_logica(u_conf):
    """
    Función para llamar desde logica.py después del análisis de sentimiento.
    
    Args:
        u_conf: Objeto de configuración con u_conf.general["output_folder"]
    """
    try:
        output_folder = u_conf.general["output_folder"]
        
        # Detectar qué plataformas tienen datos
        folder = Path(output_folder)
        plataformas_disponibles = []
        
        for plat in ['reddit', 'youtube', 'bluesky']:
            archivos = list(folder.glob(f"{plat}*_analizado.csv"))
            if archivos:
                plataformas_disponibles.append(plat)
        
        if not plataformas_disponibles:
            print("⚠️ No se encontraron datasets analizados para calcular ScoreOP")
            return None
        
        # Calcular ScoreOP
        resultados = calcular_scoreop_completo(
            output_folder,
            plataformas_disponibles
        )
        
        return resultados
        
    except Exception as e:
        print(f"❌ Error calculando ScoreOP: {e}")
        import traceback
        traceback.print_exc()
        return None


# =====================================================
# TESTING
# =====================================================

if __name__ == "__main__":
    from types import SimpleNamespace
    
    # Test con datos de prueba
    test_config = SimpleNamespace(
        general={
            "output_folder": "/home/rrss/proyecto_web/RRSS_version_stance/project_web/Web_Proyecto/datos/admin/ROSALIA"
        }
    )
    
    # Crear datos de prueba
    folder = Path(test_config.general["output_folder"])
    folder.mkdir(exist_ok=True)
    
    # Reddit de prueba
    # df_reddit_test = pd.DataFrame({
    #     'tipo': ['Post', 'Comentario', 'Comentario', 'Post'],
    #     'id_raiz': ['post1', 'post1', 'post1', 'post2'],
    #     'id_propio': ['post1', 'com1', 'com2', 'post2'],
    #     'contenido': ['Post sobre transporte', 'Comentario positivo', 'Comentario negativo', 'Otro post'],
    #     'sentimiento': [1, 1, -1, 0],
    #     'topic': ['mejora servicio', 'eficiencia', 'coste alto', 'informativo'],
    #     'likes': [10, 5, 3, 8],
    #     'comments': [2, 0, 0, 1],
    #     'usuario': ['user1', 'user2', 'user3', 'user4'],
    #     'id_anonimo': ['hash1', 'hash2', 'hash3', 'hash4'],
    #     'fecha': ['2026-04-01'] * 4
    # })
    
    # df_reddit_test.to_csv(folder / 'reddit_global_dataset_analizado.csv', index=False, sep=';')
    
    # Ejecutar
    print("🧪 EJECUTANDO TEST DE SCOREOP\n")
    resultados = calcular_scoreop_completo(str(folder))
    
    if 'reddit' in resultados:
        print("\n📊 RESULTADOS REDDIT:")
        print(resultados['reddit'])