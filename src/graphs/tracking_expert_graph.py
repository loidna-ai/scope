"""
Tracking 전문가 서브그래프 빌더
순수 ReAct 패턴 (LangGraph 공식 권장 방식)

LangGraph 공식 패턴:
- create_react_agent 또는 ToolNode + tools_condition 사용
- LLM이 자유롭게 Step 도구와 이미지 편집 도구를 선택
- agent → tools → agent 루프 구조
"""
from typing import Dict, Any, Optional, List
import json
import os
import contextlib
from langgraph.graph import StateGraph, START, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from src.state import InvestigationState
from src.nodes.experts.tracking_expert import (
    step1_dendritic_pattern,
    step2_luster_detection,
    step3_surface_erosion,
    calculate_confidence_score,
    collect_evidence,
    generate_report
)
from src.nodes.experts.expert_utils import extract_image_from_payload, save_bytes_to_temp_file
from src.agents.gemini_chatmodel import GeminiChatModel
from src.tools.registry import ToolRegistry


# 상수 정의
STEP_TOOLS = [
    "analyze_dendritic_pattern",
    "analyze_luster",
    "analyze_erosion"
]

IMAGE_EDITING_TOOLS = [
    "enhance_image",
    "apply_clahe_filter",
    "crop_image"
]

TOOL_TO_STEP_KEY = {
    "analyze_dendritic_pattern": "tracking_step1_result",
    "analyze_luster_detection": "tracking_step2_result",
    "analyze_surface_erosion": "tracking_step3_result"
}


def _load_image_data(image_path: str) -> bytes:
    """이미지 파일을 바이트로 로드"""
    try:
        with open(image_path, "rb") as f:
            return f.read()
    except Exception as e:
        raise IOError(f"이미지 로드 실패: {str(e)}")


def create_step_tools():
    """
    Step 도구 생성
    
    LangGraph 표준 패턴에 따라 도구는 image_path를 인자로 받습니다.
    """
    @tool
    def analyze_dendritic_pattern(image_path: str) -> Dict[str, Any]:
        """수지상 도전로 패턴을 분석하여 트래킹 현상 여부를 판단합니다."""
        try:
            image_data = _load_image_data(image_path)
            return step1_dendritic_pattern(image_data, verbose=False)
        except Exception as e:
            return {"error": str(e)}
    
    @tool
    def analyze_luster_detection(image_path: str) -> Dict[str, Any]:
        """탄화 흔적의 광택을 분석하여 흑연화 여부를 확인합니다."""
        try:
            image_data = _load_image_data(image_path)
            return step2_luster_detection(image_data, verbose=False)
        except Exception as e:
            return {"error": str(e)}
    
    @tool
    def analyze_surface_erosion(image_path: str) -> Dict[str, Any]:
        """탄화 경로를 따른 표면 침식을 분석하여 트래킹 여부를 판단합니다."""
        try:
            image_data = _load_image_data(image_path)
            return step3_surface_erosion(image_data, verbose=False)
        except Exception as e:
            return {"error": str(e)}
    
    return [
        analyze_dendritic_pattern,
        analyze_luster_detection,
        analyze_surface_erosion
    ]


class TrackingExpertState(MessagesState):
    """
    Tracking Expert ReAct State
    
    MessagesState를 상속받아 messages 필드가 자동으로 포함됩니다.
    """
    tracking_step1_result: Optional[Dict[str, Any]]
    tracking_step2_result: Optional[Dict[str, Any]]
    tracking_step3_result: Optional[Dict[str, Any]]
    image_path: Optional[str]  # 현재 사용 중인 이미지 파일 경로 (표준 패턴)


def create_agent_node(all_tools: List[Any]):
    """ReAct 에이전트 노드 생성"""
    def agent_node(state: TrackingExpertState) -> Dict[str, Any]:
        """ReAct 에이전트 노드 - LLM이 상황을 판단하고 필요한 도구를 선택합니다."""
        messages = state.get("messages", [])
        image_path = state.get("image_path")
        
        # 이미지 편집 도구 실행 결과 확인 및 image_path 업데이트
        updated_image_path = None
        # 역순으로 탐색하여 가장 최근의 편집된 이미지 경로를 찾음
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage) and msg.name in IMAGE_EDITING_TOOLS:
                try:
                    # 문자열인 경우에만 파싱 시도
                    content = msg.content
                    if isinstance(content, str):
                        # JSON 파싱 시도 (단순 텍스트 에러일 경우 대비)
                        with contextlib.suppress(json.JSONDecodeError, TypeError):
                            data = json.loads(content)
                            if isinstance(data, dict) and "image_path" in data:
                                updated_image_path = data["image_path"]
                                break
                    elif isinstance(content, dict) and "image_path" in content:
                        updated_image_path = content["image_path"]
                        break
                except Exception:
                    continue  # 파싱 실패 시 무시하고 계속 탐색
        
        llm = GeminiChatModel()
        llm_with_tools = llm.bind_tools(all_tools)
        
        # 현재 유효한 이미지 경로 결정
        current_image_path = updated_image_path or image_path
        
        if current_image_path is None:
            # 이미지 경로가 없다면 에러를 발생시키는 대신 에이전트에게 알려줌 (Graceful handling)
            return {"messages": [SystemMessage(content="시스템 오류: 분석할 이미지 경로를 찾을 수 없습니다.")]}
        
        sys_msg = SystemMessage(content=f"""
당신은 전기화재 감식 전문가 'Tracking Expert'입니다.
현재 분석 대상 이미지 파일 경로: "{current_image_path}"

[필수 수행 규칙]
1. 도구 호출 시 'image_path' 인자에 반드시 위 경로("{current_image_path}")를 그대로 넣으세요.
2. 상황에 따라 필요한 도구를 자유롭게 선택하여 사용하세요. 사용 가능한 분석 도구:
   - analyze_dendritic_pattern: 수지상 도전로 패턴 분석 (트래킹 현상 여부 판단)
   - analyze_luster_detection: 탄화 흔적의 광택 분석 (흑연화 여부 확인)
   - analyze_surface_erosion: 탄화 경로를 따른 표면 침식 분석 (트래킹 여부 판단)
3. 각 분석 결과(JSON)를 확인하고, 신뢰도가 낮으면 이미지 개선 도구를 사용 후 재시도하세요.

[종료 조건]
모든 분석이 완료되었거나 결론을 내릴 충분한 근거가 있다면, 도구 사용을 멈추고 최종 답변을 하세요.
최종 답변은 반드시 "**Final Answer:**" 로 시작해야 합니다.
""")
        
        response = llm_with_tools.invoke([sys_msg] + messages)
        result = {"messages": [response]}
        if updated_image_path:
            result["image_path"] = updated_image_path
        return result
    
    return agent_node


def build_tracking_expert_graph():
    """
    Tracking 전문가 서브그래프 빌드
    
    그래프 구조: START → agent → [조건부: tools_condition → tools 또는 종료] ← tools ───┘
    """
    builder = StateGraph(TrackingExpertState)
    
    step_tools = create_step_tools()
    registry = ToolRegistry()
    image_editing_tools = registry.get_tools_by_category("image")
    all_tools = step_tools + image_editing_tools
    
    agent_node_func = create_agent_node(all_tools)
    builder.add_node("agent", agent_node_func)
    builder.add_node("tools", ToolNode(all_tools))
    
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    
    return builder.compile()


def _extract_report_text(final_message: Any) -> str:
    """최종 메시지에서 리포트 텍스트 추출"""
    if not final_message or not hasattr(final_message, "content"):
        return ""
    
    content = final_message.content
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item.get("text", "")
    return ""


def _cleanup_temp_files(temp_image_path: Optional[str], final_state: Optional[Dict[str, Any]]):
    """임시 파일 정리"""
    if temp_image_path and os.path.exists(temp_image_path):
        try:
            os.remove(temp_image_path)
        except Exception as e:
            print(f"⚠️ 임시 파일 정리 실패: {e}")
    
    if final_state:
        final_image_path = final_state.get("image_path")
        if final_image_path and final_image_path != temp_image_path and os.path.exists(final_image_path):
            try:
                os.remove(final_image_path)
            except Exception:
                pass


def tracking_expert_wrapper_node(state: InvestigationState) -> Dict[str, Any]:
    """
    InvestigationState를 TrackingExpertState로 변환하여 ReAct 그래프를 실행하고,
    결과를 InvestigationState 형식으로 반환합니다.
    
    표준 패턴을 사용하여 image_data를 임시 파일로 저장하고 image_path를 사용합니다.
    """
    temp_image_path = None
    final_state = None
    try:
        image_data = extract_image_from_payload(state.get("payload", []))
        
        if image_data is None:
            return {
                "errors": ["Tracking 전문가: 이미지를 추출할 수 없습니다."],
                "expert_reports": [],
                "expert_analysis_results": {},
                "expert_confidence_scores": {},
                "expert_evidence": {}
            }
        
        temp_image_path = save_bytes_to_temp_file(image_data)
        
        initial_state: TrackingExpertState = {
            "messages": [
                HumanMessage(content=f"이미지를 분석하고 트래킹 현상 여부를 판단하세요. 이미지 경로: {temp_image_path}")
            ],
            "image_path": temp_image_path,
            "tracking_step1_result": None,
            "tracking_step2_result": None,
            "tracking_step3_result": None
        }
        
        graph = build_tracking_expert_graph()
        final_state = graph.invoke(initial_state, config={"recursion_limit": 100})
        
        messages = final_state.get("messages", [])
        step_results = {
            "tracking_step1_result": {},
            "tracking_step2_result": {},
            "tracking_step3_result": {}
        }
        
        final_message = messages[-1] if messages else None
        report_text = _extract_report_text(final_message)
        
        # 메시지를 순서대로 순회하며 결과를 덮어씌움 (재시도 시 마지막 결과가 반영되도록)
        for msg in messages:
            if isinstance(msg, ToolMessage) and msg.name in TOOL_TO_STEP_KEY:
                step_key = TOOL_TO_STEP_KEY[msg.name]
                try:
                    content = msg.content
                    if isinstance(content, str):
                        # JSON 파싱 시도
                        with contextlib.suppress(json.JSONDecodeError):
                            parsed = json.loads(content)
                            if isinstance(parsed, dict):
                                step_results[step_key] = parsed
                            else:
                                step_results[step_key] = {"result": content}
                    elif isinstance(content, dict):
                        step_results[step_key] = content
                except Exception:
                    # 파싱 실패 시 원본 텍스트 저장
                    step_results[step_key] = {"raw_content": str(msg.content)}
        
        # None 체크를 위에서 초기값 {}로 처리했으므로 바로 할당
        step1_result = step_results["tracking_step1_result"]
        step2_result = step_results["tracking_step2_result"]
        step3_result = step_results["tracking_step3_result"]
        
        confidence_score = calculate_confidence_score(
            step1_result, step2_result, step3_result
        )
        evidence = collect_evidence(step1_result, step2_result, step3_result)
        
        if report_text and ("Final Answer" in report_text or len(report_text) > 100):
            report = report_text
        else:
            report = generate_report(
                step1_result, step2_result, step3_result,
                confidence_score, evidence
            )
        return {
            "expert_reports": [report],
            "expert_analysis_results": {
                "tracking": {
                    "step1": step1_result,
                    "step2": step2_result,
                    "step3": step3_result
                }
            },
            "expert_confidence_scores": {"tracking": confidence_score},
            "expert_evidence": {"tracking": evidence},
            **step_results
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "errors": [f"Tracking 전문가 ReAct 에이전트 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }
    finally:
        _cleanup_temp_files(temp_image_path, final_state)
