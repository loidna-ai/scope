"""
전문가 노드 공통 설정 모듈
Safety Settings, 상수, 임계값 등을 중앙에서 관리합니다.
"""
from typing import List, Dict, Any


def get_safety_settings() -> List[Dict[str, str]]:
    """
    Gemini API Safety Settings 반환
    
    모든 전문가 노드에서 사용하는 공통 Safety Settings입니다.
    BLOCK_NONE으로 설정하여 이미지 분석 시 차단되지 않도록 합니다.
    
    Returns:
        Safety Settings 리스트
    """
    return [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]


# Thinking Level 지원 모델 목록
THINKING_SUPPORTED_MODELS = [
    "gemini-2.0-flash-exp",
    "gemini-2.5-flash",
    "gemini-2.5-pro"
]


# ROI 크기 임계값 (픽셀)
LARGE_ROI_THRESHOLD = 80_000  # 80,000 픽셀 이상이면 대형 ROI로 간주


# Debate 최대 반복 횟수
MAX_DEBATE_ITERATIONS = 3
