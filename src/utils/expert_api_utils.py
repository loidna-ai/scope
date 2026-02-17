"""
전문가 노드 공통 API 유틸리티
Response 검증 및 공통 API 호출 함수를 제공합니다.
"""
from typing import Any, List, Optional, Type, Dict
from google.genai import types
from pydantic import BaseModel

from src.utils.expert_config import THINKING_SUPPORTED_MODELS, get_safety_settings


def extract_finish_reason(response: Any) -> str:
    """
    Gemini API 응답에서 finish_reason 추출
    
    Args:
        response: Gemini API 응답 객체
        
    Returns:
        finish_reason 문자열 (없으면 "Unknown")
    """
    finish_reason = "Unknown"
    if hasattr(response, 'candidates') and response.candidates:
        finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
    return finish_reason


def validate_gemini_response(response: Any, context_name: str = "API") -> str:
    """
    Gemini API 응답 검증 및 텍스트 추출
    
    응답이 비어있거나 유효하지 않은 경우 ValueError를 발생시킵니다.
    
    Args:
        response: Gemini API 응답 객체
        context_name: 에러 메시지에 포함할 컨텍스트 이름
        
    Returns:
        응답 텍스트 문자열
        
    Raises:
        ValueError: 응답이 비어있거나 유효하지 않은 경우
    """
    response_text = getattr(response, 'text', None)
    if not response_text:
        finish_reason = extract_finish_reason(response)
        raise ValueError(
            f"{context_name} 응답이 비어있습니다. (Finish Reason: {finish_reason})"
        )
    return response_text


async def call_classifier_api(
    client: Any,
    model_name: str,
    parts: List[Any],
    response_schema: Type[BaseModel],
    context_name: str = "Classifier"
) -> Any:
    """
    컴포넌트 분류 API 호출 공통 함수
    
    Args:
        client: Gemini API 클라이언트
        model_name: 모델 이름
        parts: API 호출용 parts 리스트 (프롬프트 + 이미지)
        response_schema: Pydantic 모델 클래스
        context_name: 컨텍스트 이름 (에러 메시지용)
        
    Returns:
        Gemini API 응답 객체
    """
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=parts,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": response_schema.model_json_schema(),
            "safety_settings": get_safety_settings(),
        }
    )
    validate_gemini_response(response, context_name=context_name)
    return response


async def call_evidence_api(
    client: Any,
    model_name: str,
    parts: List[Any],
    response_schema: Type[BaseModel],
    thinking_level: str = "high",
    temperature: float = 1.0,
    context_name: str = "Evidence"
) -> Any:
    """
    증거 수집 API 호출 공통 함수
    
    Args:
        client: Gemini API 클라이언트
        model_name: 모델 이름
        parts: API 호출용 parts 리스트 (프롬프트 + 이미지)
        response_schema: Pydantic 모델 클래스
        thinking_level: Thinking level ("high", "medium", "low")
        temperature: Temperature 파라미터
        context_name: 컨텍스트 이름 (에러 메시지용)
        
    Returns:
        Gemini API 응답 객체
    """
    api_config: Dict[str, Any] = {
        "temperature": temperature,
        "response_mime_type": "application/json",
        "response_json_schema": response_schema.model_json_schema(),
        "safety_settings": get_safety_settings()
    }
    
    # thinking level 지원 모델에만 추가
    if any(m in model_name for m in THINKING_SUPPORTED_MODELS):
        api_config["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)
    
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=parts,
        config=api_config
    )
    validate_gemini_response(response, context_name=context_name)
    return response


async def call_supervisor_api(
    client: Any,
    model_name: str,
    prompt: str,
    response_schema: Type[BaseModel],
    temperature: float = 0.0,
    context_name: str = "Supervisor"
) -> Any:
    """
    Supervisor API 호출 공통 함수
    
    Args:
        client: Gemini API 클라이언트
        model_name: 모델 이름
        prompt: 프롬프트 텍스트
        response_schema: Pydantic 모델 클래스
        temperature: Temperature 파라미터
        context_name: 컨텍스트 이름 (에러 메시지용)
        
    Returns:
        Gemini API 응답 객체
    """
    api_config = {
        "temperature": temperature,
        "response_mime_type": "application/json",
        "response_json_schema": response_schema.model_json_schema(),
        "safety_settings": get_safety_settings(),
    }
    
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=prompt,
        config=api_config
    )
    validate_gemini_response(response, context_name=context_name)
    return response


async def call_analyst_api(
    client: Any,
    model_name: str,
    system_prompt: str,
    response_schema: Type[BaseModel],
    thinking_level: str = "high",
    temperature: float = 1.0,
    context_name: str = "Analyst"
) -> Any:
    """
    Analyst API 호출 공통 함수
    
    Args:
        client: Gemini API 클라이언트
        model_name: 모델 이름
        system_prompt: 시스템 프롬프트
        response_schema: Pydantic 모델 클래스
        thinking_level: Thinking level ("high", "medium", "low")
        temperature: Temperature 파라미터
        context_name: 컨텍스트 이름 (에러 메시지용)
        
    Returns:
        Gemini API 응답 객체
    """
    config_dict: Dict[str, Any] = {
        "temperature": temperature,
        "response_mime_type": "application/json",
        "response_json_schema": response_schema.model_json_schema(),
        "safety_settings": get_safety_settings()
    }
    
    # thinking level 지원 모델에만 추가
    if any(m in model_name for m in THINKING_SUPPORTED_MODELS):
        config_dict["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)
    
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=system_prompt,
        config=types.GenerateContentConfig(**config_dict)
    )
    # 응답 검증은 호출 측에서 수행 (Analyst 노드에서 validate_gemini_response 호출)
    return response


async def call_critic_vision_api(
    client: Any,
    model_name: str,
    parts: List[Any],
    response_schema: Type[BaseModel],
    thinking_level: str = "medium",
    temperature: float = 1.0,
    context_name: str = "Critic Vision"
) -> Any:
    """
    Critic Vision API 호출 공통 함수 (이미지 포함)
    
    Args:
        client: Gemini API 클라이언트
        model_name: 모델 이름
        parts: API 호출용 parts 리스트 (프롬프트 + 이미지)
        response_schema: Pydantic 모델 클래스
        thinking_level: Thinking level ("high", "medium", "low")
        temperature: Temperature 파라미터
        context_name: 컨텍스트 이름 (에러 메시지용)
        
    Returns:
        Gemini API 응답 객체
    """
    config_dict: Dict[str, Any] = {
        "temperature": temperature,
        "response_mime_type": "application/json",
        "response_json_schema": response_schema.model_json_schema(),
        "safety_settings": get_safety_settings()
    }
    
    # thinking level 지원 모델에만 추가
    if any(m in model_name for m in THINKING_SUPPORTED_MODELS):
        config_dict["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)
    
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=parts,
        config=types.GenerateContentConfig(**config_dict)
    )
    # 응답 검증은 호출 측에서 수행 (Critic 노드에서 validate_gemini_response 호출)
    return response


async def call_critic_text_api(
    client: Any,
    model_name: str,
    prompt: str,
    response_schema: Type[BaseModel],
    thinking_level: str = "high",
    temperature: float = 1.0,
    context_name: str = "Critic Text"
) -> Any:
    """
    Critic Text API 호출 공통 함수 (텍스트만)
    
    Args:
        client: Gemini API 클라이언트
        model_name: 모델 이름
        prompt: 프롬프트 텍스트
        response_schema: Pydantic 모델 클래스
        thinking_level: Thinking level ("high", "medium", "low")
        temperature: Temperature 파라미터
        context_name: 컨텍스트 이름 (에러 메시지용)
        
    Returns:
        Gemini API 응답 객체
    """
    config_dict: Dict[str, Any] = {
        "temperature": temperature,
        "response_mime_type": "application/json",
        "response_json_schema": response_schema.model_json_schema(),
        "safety_settings": get_safety_settings()
    }
    
    # thinking level 지원 모델에만 추가
    if any(m in model_name for m in THINKING_SUPPORTED_MODELS):
        config_dict["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)
    
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(**config_dict)
    )
    # 응답 검증은 호출 측에서 수행 (Critic 노드에서 validate_gemini_response 호출)
    return response
