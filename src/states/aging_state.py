"""
Aging (절연열화/트래킹) 전문가 상태 정의
"""
from src.states.common_state import BaseExpertState

class AgingExpertState(BaseExpertState):
    """
    Aging Expert State (Map-Reduce Pattern)
    BaseExpertState를 상속받아 공통 필드 재사용 (hotspots, messages, analysis_results 등)
    """
    pass
