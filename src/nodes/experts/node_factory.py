"""
전문가 노드 팩토리
공통 패턴을 사용하여 step 노드 함수를 생성합니다.

중복 코드 제거:
- 모든 step 노드 함수가 동일한 패턴을 사용하므로 팩토리 함수로 생성
- 이미지 추출 로직 통합
- 에러 처리 통합

위치: nodes/experts/ 폴더
- 노드를 생성하는 팩토리이므로 노드 폴더에 위치하는 것이 논리적
- 그래프 빌더(graphs/)에서 import하여 사용
"""
from typing import Dict, Any, Callable, Optional
from src.state import InvestigationState
from src.nodes.experts.expert_utils import extract_image_from_payload


def create_step_node(
    expert_name: str,
    step_number: int,
    step_function: Callable,
    result_key: str,
    image_cache_key: str = None  # None이면 expert_name 기반으로 자동 생성
) -> Callable[[InvestigationState], Dict[str, Any]]:
    """
    Step 노드 함수를 생성하는 팩토리 함수
    
    Args:
        expert_name: 전문가 이름 (예: "contact", "dielectric")
        step_number: Step 번호 (1, 2, 3, ...)
        step_function: 실제 step 분석 함수 (예: step1_location_context)
        result_key: 상태에 저장할 결과 키 (예: "contact_step1_result")
        image_cache_key: 캐시된 이미지 데이터의 상태 키 (None이면 expert_name 기반으로 자동 생성)
    
    Returns:
        Step 노드 함수
    """
    # image_cache_key가 None이면 expert_name 기반으로 자동 생성
    if image_cache_key is None:
        image_cache_key = f"{expert_name}_cached_image_data"
    
    def node_function(state: InvestigationState) -> Dict[str, Any]:
        """
        생성된 Step 노드 함수
        
        이미지 캐싱:
        - 첫 번째 step에서 이미지를 추출하여 state에 저장
        - 이후 step에서는 캐시된 이미지를 재사용
        - 첫 번째 step만 캐시를 반환하여 불필요한 reducer 호출 방지
        """
        try:
            # 이미지 캐싱: 이미 state에 캐시된 이미지가 있으면 재사용
            image_data = state.get(image_cache_key)
            
            if image_data is None:
                # 첫 번째 step이거나 캐시가 없는 경우 이미지 추출
                image_data = extract_image_from_payload(state["payload"])
                
                if image_data is None:
                    return {
                        "errors": [f"{expert_name.capitalize()} 전문가 Step {step_number}: 이미지를 추출할 수 없습니다."],
                        result_key: {"error": "이미지 추출 실패"}
                    }
            
            # Step 함수 실행
            result = step_function(image_data, verbose=False)
            
            # 결과 반환
            # 최적화: 첫 번째 step만 캐시를 반환하여 불필요한 reducer 호출 방지
            return_value = {
                result_key: result
            }
            
            # 첫 번째 step이거나 캐시가 없는 경우에만 캐시 반환
            if step_number == 1 or state.get(image_cache_key) is None:
                return_value[image_cache_key] = image_data
            
            # #region agent log
            try:
                import json
                import time
                with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    return_keys = list(return_value.keys())
                    f.write(json.dumps({"sessionId":"react-parallel","runId":"run1","hypothesisId":"C","location":"node_factory.py:node_function","message":"Step 노드 반환값","data":{"expert_name":expert_name,"step_number":step_number,"return_keys":return_keys,"has_context":"context" in return_keys},"timestamp":int(time.time()*1000)})+'\n')
            except: pass
            # #endregion
            
            return return_value
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "errors": [f"{expert_name.capitalize()} 전문가 Step {step_number} 오류: {str(e)}"],
                result_key: {"error": str(e)}
            }
    
    return node_function

