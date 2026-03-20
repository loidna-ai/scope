"""
전문가 노드 공통 설정 모듈
Safety Settings, 상수, 임계값 등을 중앙에서 관리합니다.

Thinking 설정: Vertex AI 공식 문서 기준
- Gemini 3 (gemini-3-flash, gemini-3.1-pro 등): thinking_level (minimal/low/medium/high)
- Gemini 2.5 (gemini-2.5-flash, gemini-2.5-pro 등): thinking_budget (토큰 수, -1=동적)
  - thinking_level 사용 시 400 INVALID_ARGUMENT 발생
  - 참고: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thinking
"""
from typing import List, Dict, Any, Optional

# ThinkingConfig 생성 시 types 필요
def _get_types():
    from google.genai import types
    return types


def get_thinking_config(
    model_name: str,
    level: str = "high"
) -> Optional[Any]:
    """
    모델 시리즈에 따라 적절한 ThinkingConfig 반환.
    
    - Gemini 3 (gemini-3-*): thinking_level 사용
    - Gemini 2.5 (gemini-2.5-*): thinking_budget 사용 (thinking_level 사용 시 400 에러)
    
    Args:
        model_name: 모델 ID (예: gemini-2.5-pro, gemini-3-flash-preview)
        level: "high" | "medium" | "low" | "minimal" (Gemini 3용)
        
    Returns:
        ThinkingConfig 또는 None (thinking 미지원 모델)
    """
    types = _get_types()
    model_lower = (model_name or "").lower()
    
    # Gemini 3 시리즈: thinking_level 사용
    if "gemini-3" in model_lower:
        level_map = {"high": "high", "medium": "medium", "low": "low", "minimal": "minimal"}
        thinking_level = level_map.get(level.lower(), "high")
        return types.ThinkingConfig(thinking_level=thinking_level)
    
    # Gemini 2.5 시리즈: thinking_budget 사용 (공식 문서)
    # - Pro: 128~32768, Flash: 1~24576, -1=동적
    if "gemini-2.5" in model_lower:
        budget_map = {"high": 8192, "medium": 4096, "low": 1024, "minimal": 128}
        budget = budget_map.get(level.lower(), 8192)
        return types.ThinkingConfig(thinking_budget=budget)
    
    # Gemini 2.0-flash-exp 등: thinking_budget (2.5와 동일 패턴)
    if "gemini-2.0-flash-exp" in model_lower:
        return types.ThinkingConfig(thinking_budget=8192)
    
    return None


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


# Thinking 지원 모델 (Gemini 2.5: thinking_budget, Gemini 3: thinking_level)
THINKING_SUPPORTED_MODELS = [
    "gemini-2.0-flash-exp",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
    "gemini-3-flash",
    "gemini-3.1-pro",
]


# ROI 크기 임계값 (픽셀)
LARGE_ROI_THRESHOLD = 80_000  # 80,000 픽셀 이상이면 대형 ROI로 간주


# Debate 최대 반복 횟수
MAX_DEBATE_ITERATIONS = 3
