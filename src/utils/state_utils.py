from typing import Dict, Any, List

def validate_state_keys(
    state: Dict[str, Any], 
    required_keys: List[str],
    context: str = "State"
) -> None:
    """
    State에 필수 키가 있는지 검증 (LangGraph Best Practice)
    
    노드 경계에서 inbound/outbound state를 검증하여
    명확한 에러 메시지를 제공하고 디버깅을 용이하게 합니다.
    
    Args:
        state: 검증할 state dictionary
        required_keys: 필수 키 리스트
        context: 에러 메시지용 컨텍스트
    
    Raises:
        ValueError: 필수 키가 없을 경우
    """
    missing = [key for key in required_keys if not state.get(key)]
    if missing:
        raise ValueError(
            f"{context} validation failed: Missing required keys {missing}"
        )
