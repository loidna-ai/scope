"""
전문가 노드 공통 예외 클래스
에러 처리 표준화를 위한 커스텀 예외를 정의합니다.
"""


class ExpertAnalysisError(Exception):
    """전문가 분석 관련 기본 예외"""
    pass


class ComponentClassificationError(ExpertAnalysisError):
    """컴포넌트 분류 실패"""
    pass


class EvidenceCollectionError(ExpertAnalysisError):
    """증거 수집 실패"""
    pass


class SupervisorAggregationError(ExpertAnalysisError):
    """Supervisor 종합 판정 실패"""
    pass


class AnalystHypothesisError(ExpertAnalysisError):
    """Analyst 가설 수립 실패"""
    pass


class CriticVerificationError(ExpertAnalysisError):
    """Critic 검증 실패"""
    pass


class ImageProcessingError(ExpertAnalysisError):
    """이미지 처리 실패"""
    pass
