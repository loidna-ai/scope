"""
Vertex AI gemini-2.5-flash 정상 작동 검증 스크립트
config.USE_VERTEX_AI=True 로 Vertex AI Client를 사용해 단순 텍스트 생성 테스트
"""
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

# Vertex AI 모드 강제
import config
config.USE_VERTEX_AI = True

def main():
    from src.utils.genai_client import get_genai_client
    
    print("=== Vertex AI gemini-2.5-flash 검증 ===\n")
    print(f"Project: {config.GOOGLE_CLOUD_PROJECT}")
    print(f"Location: {config.GOOGLE_CLOUD_LOCATION}")
    print(f"Model: gemini-2.5-flash\n")
    
    try:
        client = get_genai_client()
        print("[OK] Client 생성 성공\n")
        
        print("API 호출 중...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="한 줄로 'Vertex AI 연결 성공'이라고 답하세요.",
        )
        
        text = response.text if hasattr(response, "text") else str(response)
        print(f"\n[OK] 응답 수신:\n{text}\n")
        print("=== 검증 완료: Vertex AI gemini-2.5-flash 정상 작동 ===")
        return 0
        
    except Exception as e:
        print(f"\n[FAIL] 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
