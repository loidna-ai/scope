"""
ReAct 에이전트 래퍼 노드
InvestigationState를 ReActState로 변환하여 ReAct 에이전트를 실행하고,
결과를 다시 InvestigationState 형식으로 변환합니다.

Step별로 필요한 이미지 편집 도구를 결정하여 프롬프트에 포함합니다.
"""
from typing import Dict, Any, Optional, Tuple
from langchain_core.messages import HumanMessage
from src.state import InvestigationState, ReActState
from src.agents.react_agent import build_react_agent_graph


def _determine_current_step_and_expert(state: InvestigationState) -> Tuple[Optional[str], Optional[str]]:
    """
    State를 분석하여 현재 실행 중인 Step과 Expert를 추론합니다.
    
    Returns:
        (expert_name, step_number): 예) ("contact", 1), ("dielectric", 2) 등
    """
    experts = ["contact", "dielectric", "mechanical", "tracking", "strand_fracture"]
    step_patterns = {
        "contact": ["step1", "step2", "step3", "step4"],
        "dielectric": ["step1", "step2", "step3"],
        "mechanical": ["step1", "step2", "step3"],
        "tracking": ["step1", "step2", "step3"],
        "strand_fracture": ["step1", "step2", "step3"]
    }
    
    for expert in experts:
        for i, step_pattern in enumerate(step_patterns[expert], 1):
            step_key = f"{expert}_{step_pattern}_result"
            next_step_key = None
            
            # 다음 Step이 있는지 확인
            if i < len(step_patterns[expert]):
                next_step_pattern = step_patterns[expert][i]
                next_step_key = f"{expert}_{next_step_pattern}_result"
            
            # 현재 Step 결과는 있지만 다음 Step 결과는 없으면 현재 Step에서 호출됨
            if step_key in state and state.get(step_key) is not None:
                if next_step_key is None or state.get(next_step_key) is None:
                    return (expert, i)
    
    return (None, None)


def _get_step_specific_prompt(expert_name: Optional[str], step_number: Optional[int]) -> str:
    """
    Step별 컨텍스트를 제공하되, 도구 선택은 LLM에게 맡깁니다.
    
    ReAct 패턴에 맞게:
    - LLM이 상황을 판단하고 필요할 때만 도구를 선택
    - 필요한 도구를 명시하지 않고 컨텍스트만 제공
    
    Args:
        expert_name: 전문가 이름
        step_number: Step 번호
    
    Returns:
        Step별 컨텍스트가 포함된 프롬프트 (도구 선택은 LLM에게 위임)
    """
    base_prompt = (
        "당신은 ReAct 패턴을 따르는 AI 에이전트입니다. "
        "사용자의 작업을 수행하기 위해 필요한 도구를 사용하세요.\n\n"
        "중요 지침:\n"
        "- 당신은 이미지 편집 및 분석 도구를 사용할 수 있습니다.\n"
        "- 현재 상황을 분석하고, 필요하다고 판단될 때만 도구를 사용하세요.\n"
        "- 도구를 사용하지 않고도 답변할 수 있다면 도구를 사용하지 마세요.\n"
        "- 도구 호출 시 반드시 사용자 메시지에서 제공된 정확한 이미지 경로를 사용하세요.\n"
        "- 같은 도구를 같은 인자로 두 번 이상 연속으로 호출하지 마세요.\n"
        "- 도구가 에러를 반환하면 다른 방법을 시도하거나 사용자에게 결과를 보고하세요.\n"
        "- **반드시** 최종 답변을 제공할 때는 반드시 'Final Answer:'로 시작해야 합니다.\n\n"
    )
    
    # Step별 컨텍스트만 제공 (도구 선택은 LLM에게 맡김)
    step_contexts = {
        ("contact", 1): (
            "현재 작업: Contact Expert Step1 (위치적 맥락 확인)\n"
            "목적: 접속점 위치를 식별합니다.\n"
            "상황: 이미지 품질이 낮거나 해상도가 부족하다고 판단되면 이미지 향상 도구를 사용할 수 있습니다.\n"
        ),
        ("contact", 2): (
            "현재 작업: Contact Expert Step2 (색상 패턴 분석)\n"
            "목적: 아산화동 의심 색상 패턴을 관찰합니다.\n"
            "상황: 색상 구분이 어렵거나 대비가 부족하다고 판단되면 대비 향상 도구를 사용할 수 있습니다.\n"
        ),
        ("contact", 3): (
            "현재 작업: Contact Expert Step3 (열적 구배 분석)\n"
            "목적: 탄화 패턴과 열 전파 방향을 분석합니다.\n"
            "상황: 관심 영역이 불명확하거나 해상도가 부족하다고 판단되면 크롭 또는 향상 도구를 사용할 수 있습니다.\n"
        ),
        ("contact", 4): (
            "현재 작업: Contact Expert Step4 (표면 분석)\n"
            "목적: 미세 기공과 곰보 자국을 식별합니다.\n"
            "상황: 표면 특징이 불명확하거나 해상도가 부족하다고 판단되면 향상 또는 필터 도구를 사용할 수 있습니다.\n"
        ),
        ("dielectric", 1): (
            "현재 작업: Dielectric Expert Step1 (탄화 깊이 분석)\n"
            "목적: 단면을 확인하고 내부/외부를 구분합니다.\n"
            "상황: 단면이 불명확하거나 해상도가 부족하다고 판단되면 향상 또는 크롭 도구를 사용할 수 있습니다.\n"
        ),
        ("dielectric", 2): (
            "현재 작업: Dielectric Expert Step2 (부풀림 분석)\n"
            "목적: 스펀지형 질감을 분석합니다.\n"
            "상황: 질감이 불명확하거나 텍스처가 보이지 않는다고 판단되면 텍스처 강조 도구를 사용할 수 있습니다.\n"
        ),
        ("dielectric", 3): (
            "현재 작업: Dielectric Expert Step3 (전역 노화 분석)\n"
            "목적: 전체 패턴을 분석합니다.\n"
            "상황: 관심 영역이 불명확하다고 판단되면 크롭 도구를 사용할 수 있습니다.\n"
        ),
        ("mechanical", 1): (
            "현재 작업: Mechanical Expert Step1 (변형 분석)\n"
            "목적: 도구 흔적과 찍힘 자국을 식별합니다.\n"
            "상황: 미세 흔적이 불명확하거나 해상도가 부족하다고 판단되면 향상 도구를 사용할 수 있습니다.\n"
        ),
        ("mechanical", 2): (
            "현재 작업: Mechanical Expert Step2 (소선 배열 분석)\n"
            "목적: 소선 분산과 절단 흔적을 분석합니다.\n"
            "상황: 미세 구조가 불명확하거나 해상도가 부족하다고 판단되면 향상 도구를 사용할 수 있습니다.\n"
        ),
        ("mechanical", 3): (
            "현재 작업: Mechanical Expert Step3 (구속 분석)\n"
            "목적: 망울 형태를 분석합니다.\n"
            "상황: 형태학적 분석이 필요하다고 판단되면 형태학적 분석 도구를 사용할 수 있습니다.\n"
        ),
        ("tracking", 1): (
            "현재 작업: Tracking Expert Step1 (수지상 패턴 분석)\n"
            "목적: 수지상 도전로 패턴을 분석합니다.\n"
            "상황: 패턴이 불명확하거나 해상도가 부족하다고 판단되면 크롭 또는 향상 도구를 사용할 수 있습니다.\n"
        ),
        ("tracking", 2): (
            "현재 작업: Tracking Expert Step2 (광택 탐지)\n"
            "목적: 흑연 광택을 구분합니다.\n"
            "상황: 광택이 불명확하거나 대비가 부족하다고 판단되면 대비 향상 도구를 사용할 수 있습니다.\n"
        ),
        ("tracking", 3): (
            "현재 작업: Tracking Expert Step3 (침식 분석)\n"
            "목적: 표면 침식을 분석합니다.\n"
            "상황: 표면 특징이 불명확하거나 해상도가 부족하다고 판단되면 향상 또는 필터 도구를 사용할 수 있습니다.\n"
        ),
        ("strand_fracture", 1): (
            "현재 작업: StrandFracture Expert Step1 (끝단 형태 분석)\n"
            "목적: 네킹 현상과 미세 망울을 식별합니다.\n"
            "상황: 미세 특징이 불명확하거나 해상도가 부족하다고 판단되면 향상 도구를 사용할 수 있습니다.\n"
        ),
        ("strand_fracture", 2): (
            "현재 작업: StrandFracture Expert Step2 (망울 분포 분석)\n"
            "목적: 미세 망울 크기와 분포를 분석합니다.\n"
            "상황: 미세 망울이 불명확하거나 해상도가 부족하다고 판단되면 향상 도구를 사용할 수 있습니다.\n"
        ),
        ("strand_fracture", 3): (
            "현재 작업: StrandFracture Expert Step3 (피로 분석)\n"
            "목적: 형태학적 메트릭스를 분석합니다.\n"
            "상황: 형태학적 분석이 필요하다고 판단되면 형태학적 분석 도구를 사용할 수 있습니다.\n"
        ),
    }
    
    step_context = step_contexts.get((expert_name, step_number), "")
    
    # 사용 가능한 도구 목록
    tools_list = (
        "사용 가능한 이미지 편집 도구:\n"
        "  * `enhance_image`: Real-ESRGAN을 사용하여 이미지를 4배 초해상도로 향상\n"
        "  * `apply_clahe_filter`: CLAHE 필터를 적용하여 대비 향상\n"
        "  * `crop_image`: 단락흔 영역을 탐지하고 크롭\n"
        "  * `analyze_image_morphology`: 이미지의 형태학적 특성 분석 (원형도, 고형도, 면적)\n"
    )
    
    if step_context:
        return base_prompt + step_context + "\n" + tools_list
    else:
        return base_prompt + tools_list


def react_agent_wrapper_node(state: InvestigationState) -> Dict[str, Any]:
    """
    ReAct 에이전트 래퍼 노드
    
    InvestigationState를 ReActState로 변환하여 ReAct 에이전트를 실행하고,
    결과를 InvestigationState 형식으로 반환합니다.
    
    Args:
        state: InvestigationState
        
    Returns:
        Partial State: InvestigationState 형식의 결과
    """
    try:
        # #region agent log
        import json
        import time
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-parallel","runId":"run1","hypothesisId":"A","location":"react_agent_wrapper.py:react_agent_wrapper_node","message":"ReAct 래퍼 노드 시작","data":{"has_payload":bool(state.get("payload")),"payload_count":len(state.get("payload",[]))},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # payload에서 이미지 경로 추출 시도
        payload = state.get("payload", [])
        
        # task에서 이미지 경로 추출 (main.py에서 task에 포함시킴)
        task = state.get("task", "")
        image_path = None
        if task and "이미지 경로:" in task:
            # task에서 이미지 경로 추출
            lines = task.split("\n")
            for line in lines:
                if "이미지 경로:" in line:
                    image_path = line.split("이미지 경로:")[-1].strip()
                    break
        
        # context에서 이미지 경로 가져오기 (fallback)
        if not image_path:
            context = state.get("context", {})
            image_path = context.get("image_path") if isinstance(context, dict) else None
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-parallel","runId":"run1","hypothesisId":"E","location":"react_agent_wrapper.py:react_agent_wrapper_node","message":"이미지 경로 추출","data":{"task":task,"has_image_path_in_task":"이미지 경로:" in task if task else False,"image_path":image_path,"context_type":type(context).__name__ if not image_path else None},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # 현재 Step과 Expert 추론
        expert_name, step_number = _determine_current_step_and_expert(state)
        
        # Step별 프롬프트 생성
        step_prompt = _get_step_specific_prompt(expert_name, step_number)
        
        # 기본 질문 생성 (task에서 질문 부분만 추출)
        if task and "\n" in task:
            user_query = task.split("\n")[0].strip()
        else:
            user_query = task if task else "이미지를 분석하고 화재 원인을 조사하세요."
        
        # Step 정보를 포함한 사용자 메시지 생성
        step_info = ""
        if expert_name and step_number:
            step_info = f"\n\n[현재 작업: {expert_name.capitalize()} Expert Step {step_number}]\n"
        
        # 이미지 경로가 있으면 메시지에 포함
        if image_path:
            user_message_content = f"{user_query}{step_info}\n이미지 경로: {image_path}\n이미지 데이터가 payload에 포함되어 있습니다.\n\n{step_prompt}"
        else:
            user_message_content = f"{user_query}{step_info}\n이미지 데이터가 payload에 포함되어 있습니다.\n\n{step_prompt}"
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-parallel","runId":"run1","hypothesisId":"E","location":"react_agent_wrapper.py:react_agent_wrapper_node","message":"사용자 메시지 생성","data":{"user_message_content":user_message_content,"has_image_path_in_message":"이미지 경로:" in user_message_content},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # ReActState로 변환
        react_state: ReActState = {
            "messages": [
                HumanMessage(
                    content=user_message_content
                )
            ],
            "task": user_query,
            "context": {
                "payload": payload,
                "image_path": image_path,  # 이미지 경로를 context에 명시적으로 포함
                "expert_reports": state.get("expert_reports", []),
                "expert_analysis_results": state.get("expert_analysis_results", {})
            }
        }
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-parallel","runId":"run1","hypothesisId":"A","location":"react_agent_wrapper.py:react_agent_wrapper_node","message":"ReAct 그래프 실행 시작","data":{"messages_count":len(react_state.get("messages",[]))},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # ReAct 에이전트 그래프 실행
        react_graph = build_react_agent_graph()
        result = react_graph.invoke(
            react_state,
            config={"recursion_limit": 50}
        )
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                messages = result.get("messages", []) if result else []
                f.write(json.dumps({"sessionId":"react-parallel","runId":"run1","hypothesisId":"A","location":"react_agent_wrapper.py:react_agent_wrapper_node","message":"ReAct 그래프 실행 완료","data":{"messages_count":len(messages)},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # 결과 추출
        messages = result.get("messages", [])
        final_message = messages[-1] if messages else None
        
        # 메시지 히스토리를 딕셔너리 리스트로 변환 (JSON 직렬화 가능하도록)
        messages_history = []
        for msg in messages:
            msg_dict = {
                "type": type(msg).__name__,
                "content": msg.content if hasattr(msg, "content") else str(msg),
            }
            # Tool call 정보 추가
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {}),
                        "id": tc.get("id", "")
                    }
                    for tc in msg.tool_calls
                ]
            # Tool message인 경우 tool_call_id 추가
            if hasattr(msg, "tool_call_id"):
                msg_dict["tool_call_id"] = msg.tool_call_id
            messages_history.append(msg_dict)
        
        if final_message:
            response_text = final_message.content if hasattr(final_message, "content") else str(final_message)
            
            # InvestigationState 형식으로 변환
            # ReAct 에이전트의 응답을 전문가 리포트로 추가
            # context는 react_agent_wrapper_node에서만 설정 (병렬 실행 충돌 방지)
            return_dict = {
                "expert_reports": [f"[ReAct 에이전트]\n{response_text}"],
                "expert_analysis_results": {
                    "react_agent": {
                        "response": response_text,
                        "messages_count": len(messages)
                    }
                },
                "expert_confidence_scores": {"react_agent": 75.0},  # 기본 신뢰도
                "expert_evidence": {"react_agent": []},
                "react_agent_messages": messages_history,  # 메시지 히스토리 저장
                "context": {  # react_agent_wrapper_node에서만 context 설정
                    "image_path": image_path,
                    "payload": payload
                } if image_path else None
            }
            # #region agent log
            try:
                with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    return_keys = list(return_dict.keys())
                    f.write(json.dumps({"sessionId":"react-parallel","runId":"run1","hypothesisId":"B","location":"react_agent_wrapper.py:react_agent_wrapper_node","message":"반환값 생성","data":{"return_keys":return_keys,"has_context":"context" in return_keys,"context_is_none":return_dict.get("context") is None},"timestamp":int(time.time()*1000)})+'\n')
            except: pass
            # #endregion
            return return_dict
        else:
            return {
                "errors": ["ReAct 에이전트: 응답이 없습니다."],
                "expert_reports": [],
                "expert_analysis_results": {},
                "expert_confidence_scores": {},
                "expert_evidence": {}
            }
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "errors": [f"ReAct 에이전트 래퍼 노드 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }

