"""
이미지 로드 노드
입력 이미지 경로에서 이미지를 로드하여 상태에 저장합니다.
"""
from typing import Dict, Any
from src.state import GraphState
from src.utils import load_image_safe

def load_node(state: GraphState) -> Dict[str, Any]:
    """
    이미지 로드 노드
    
    Args:
        state: 그래프 상태
    
    Returns:
        업데이트할 상태 필드 (Partial State)
    """
    input_path = state["input_image_path"]
    
    try:
        # 한글 경로 지원 이미지 로드
        image = load_image_safe(input_path)
        
        return {
            "original_image": image
        }
    except Exception as e:
        error_msg = f"이미지 로드 실패 ({input_path}): {str(e)}"
        return {
            "errors": [error_msg]
        }

