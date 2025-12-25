"""
노드 패키지
LangGraph 그래프의 노드 함수들을 정의합니다.

구조:
- 전처리 노드: load, crop, enhancement, filter, metrics, packaging
- 전문가 노드: experts/ 폴더에 정의
  - 각 전문가의 로직: {expert}_expert.py
  - 각 전문가의 서브그래프 노드: {expert}_expert_graph.py
- Arbiter 노드: experts/arbiter.py
"""

# 전처리 노드들
from src.nodes.load import load_node
from src.nodes.crop import crop_node
# enhancement_node는 지연 로딩 (basicsr 의존성 문제 방지)
# from src.nodes.enhancement import enhancement_node
from src.nodes.filter import filter_node
from src.nodes.metrics import metrics_node
from src.nodes.packaging import packaging_node

# enhancement_node 지연 로딩 함수
def get_enhancement_node():
    """enhancement_node를 지연 로딩"""
    from src.nodes.enhancement import enhancement_node
    return enhancement_node

# Arbiter 노드
from src.nodes.experts.arbiter import node_arbiter

__all__ = [
    # 전처리 노드
    "load_node",
    "crop_node",
    "enhancement_node",
    "filter_node",
    "metrics_node",
    "packaging_node",
    # Arbiter 노드
    "node_arbiter",
]
