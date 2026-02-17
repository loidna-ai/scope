"""
중앙 Gemini/Vertex AI Client 생성 유틸
Google AI Studio 또는 Vertex AI 중 config에 따라 적절한 Client 반환
"""
import os
from google import genai
import config


def get_genai_client():
    """
    config.USE_VERTEX_AI에 따라 Google AI Studio 또는 Vertex AI Client 반환

    Returns:
        genai.Client: 인증된 Gemini API 클라이언트

    Raises:
        ValueError: Vertex AI 모드에서 프로젝트 미설정, 또는 AI Studio 모드에서 API 키 미설정 시
    """
    if config.USE_VERTEX_AI:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", config.GOOGLE_CLOUD_PROJECT)
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", config.GOOGLE_CLOUD_LOCATION)
        if not project:
            raise ValueError(
                "Vertex AI 모드: GOOGLE_CLOUD_PROJECT가 설정되지 않았습니다. "
                "config.py 또는 환경 변수 GOOGLE_CLOUD_PROJECT를 설정하세요."
            )
        return genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "Google AI Studio 모드: GEMINI_API_KEY가 설정되지 않았습니다. "
                "환경 변수 GEMINI_API_KEY를 설정하세요."
            )
        return genai.Client(api_key=api_key)
