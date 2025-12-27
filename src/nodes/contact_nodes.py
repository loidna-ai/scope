"""
Contact 전문가 노드 및 ReAct 에이전트 정의
"""
from typing import Dict, Any, Optional, List
import json
import os
import re

from langgraph.graph import MessagesState
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langchain_core.tools import tool

from src.agents.gemini_chatmodel import GeminiChatModel
from src.tools.registry import ToolRegistry
from src.tools.experts.contact_tools import (
    step1_location_context,
    step2_spectral_analysis,
    step3_thermal_gradient,
    step4_surface_analysis
)
from src.prompts.contact_expert_prompts import (
    get_step1_react_prompt,
    get_step2_react_prompt,
    get_step3_react_prompt,
    get_step4_react_prompt
)

def print_agent_process(messages):
    """에이전트의 추론 및 도구 사용 과정을 출력"""
    print("\n" + "="*20 + " Agent Reasoning & Tool Execution " + "="*20)
    for msg in messages:
        if isinstance(msg, HumanMessage):
            continue
        if isinstance(msg, AIMessage):
            if msg.content:
                print(f"\n🧠 [Thought]:\n{msg.content}\n")
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    print(f"🛠️ [Tool Call]: {tool_call['name']} (Args: {tool_call['args']})")
        elif isinstance(msg, ToolMessage):
             content = str(msg.content)
             display_content = content[:300] + "..." if len(content) > 300 else content
             print(f"   └─ 📊 [Tool Output]: {display_content}")
    print("="*76 + "\n")


class ContactExpertState(MessagesState):
    """
    Contact Expert ReAct State
    """
    contact_step1_result: Optional[Dict[str, Any]]
    contact_step2_result: Optional[Dict[str, Any]]
    contact_step3_result: Optional[Dict[str, Any]]
    contact_step4_result: Optional[Dict[str, Any]]
    image_path: Optional[str]

def _load_image_data(image_path: str) -> bytes:
    """이미지 파일을 바이트로 로드"""
    try:
        with open(image_path, "rb") as f:
            return f.read()
    except Exception as e:
        raise IOError(f"이미지 로드 실패: {str(e)}")

def _update_image_path_from_messages(messages: List[Any], current_path: str) -> str:
    """메시지 히스토리에서 이미지 편집 도구의 결과를 찾아 이미지 경로 업데이트"""
    updated_path = current_path
    image_tool_names = ["enhance_image", "apply_clahe_filter", "crop_image"]
    
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "")
            content = str(msg.content)
            
            try:
                data = json.loads(content)
                if isinstance(data, dict) and "image_path" in data:
                    potential_path = data["image_path"]
                    if os.path.exists(potential_path):
                        return potential_path
            except:
                pass
            
            if tool_name in image_tool_names:
                match = re.search(r'완료[:\\s]+([^\\n]+)', content)
                if match:
                    potential_path = match.group(1).strip()
                    if os.path.exists(potential_path):
                        return potential_path
                        
    return updated_path

# --------------------------------------------------------------------------------
# Step별 ReAct 에이전트 빌더
# --------------------------------------------------------------------------------

def build_step1_react_agent(image_path: str):
    llm = GeminiChatModel()
    registry = ToolRegistry()
    image_editing_tools = registry.get_tools_by_category("image")
    
    @tool
    def analyze_location_context_internal(image_path: str) -> str:
        """이미지의 위치적 맥락(접속점 여부, 전선 끝단 등)을 식별합니다. 이미지 보정이 필요하면 먼저 보정 도구를 사용하세요."""
        try:
            image_data = _load_image_data(image_path)
            result = step1_location_context(image_data, verbose=False)
            return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    all_tools = [analyze_location_context_internal] + image_editing_tools
    react_prompt = get_step1_react_prompt(image_path)
    return create_react_agent(model=llm, tools=all_tools, prompt=react_prompt)

def build_step2_react_agent(image_path: str):
    llm = GeminiChatModel()
    registry = ToolRegistry()
    image_editing_tools = registry.get_tools_by_category("image")
    
    @tool
    def analyze_spectral_analysis_internal(image_path: str) -> str:
        """아산화동(Cu2O) 증식 여부를 판단하기 위해 붉은색/적갈색 패턴을 분석합니다. 이미지 보정이 필요하면 먼저 보정 도구를 사용하세요."""
        try:
            image_data = _load_image_data(image_path)
            result = step2_spectral_analysis(image_data, verbose=False)
            return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    all_tools = [analyze_spectral_analysis_internal] + image_editing_tools
    react_prompt = get_step2_react_prompt(image_path)
    return create_react_agent(model=llm, tools=all_tools, prompt=react_prompt)

def build_step3_react_agent(image_path: str):
    llm = GeminiChatModel()
    registry = ToolRegistry()
    image_editing_tools = registry.get_tools_by_category("image")
    
    @tool
    def analyze_thermal_gradient_internal(image_path: str) -> str:
        """전선의 탄화 패턴을 통해 열적 구배(Thermal Gradient)를 시각화합니다. 이미지 보정이 필요하면 먼저 보정 도구를 사용하세요."""
        try:
            image_data = _load_image_data(image_path)
            result = step3_thermal_gradient(image_data, verbose=False)
            return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    all_tools = [analyze_thermal_gradient_internal] + image_editing_tools
    react_prompt = get_step3_react_prompt(image_path)
    return create_react_agent(model=llm, tools=all_tools, prompt=react_prompt)

def build_step4_react_agent(image_path: str):
    llm = GeminiChatModel()
    registry = ToolRegistry()
    image_editing_tools = registry.get_tools_by_category("image")
    
    @tool
    def analyze_surface_analysis_internal(image_path: str) -> str:
        """금속 표면의 곰보 자국(Pitting)이나 전기적 부식 흔적을 정밀 분석합니다. 이미지 보정이 필요하면 먼저 보정 도구를 사용하세요."""
        try:
            image_data = _load_image_data(image_path)
            result = step4_surface_analysis(image_data, verbose=False)
            return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    all_tools = [analyze_surface_analysis_internal] + image_editing_tools
    react_prompt = get_step4_react_prompt(image_path)
    return create_react_agent(model=llm, tools=all_tools, prompt=react_prompt)

# --------------------------------------------------------------------------------
# Step Node 정의
# --------------------------------------------------------------------------------

def step1_node(state: ContactExpertState):
    import json
    import time
    current_image_path = state.get("image_path")
    
    agent = build_step1_react_agent(current_image_path)
    input_msg = HumanMessage(content=f"이미지를 분석하여 용융흔이 발생한 위치를 식별하세요. 이미지 경로: {current_image_path}")
    
    result = agent.invoke({"messages": [input_msg]})
    
    step_messages = result.get("messages", [])
    print_agent_process(step_messages)
    updated_image_path = _update_image_path_from_messages(step_messages, current_image_path)
    
    step_result = None
    if step_messages:
        last_msg = step_messages[-1]
        if isinstance(last_msg.content, str):
            try:
                content = last_msg.content
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    step_result = json.loads(json_match.group(0))
                else:
                    step_result = {"result_text": content}
            except:
                step_result = {"result_text": last_msg.content}

    for msg in reversed(step_messages):
        if isinstance(msg, ToolMessage) and msg.name == "analyze_location_context_internal":
            try:
                step_result = json.loads(msg.content)
                break
            except:
                pass

    return {
        "messages": step_messages,
        "contact_step1_result": step_result,
        "image_path": updated_image_path
    }

def step2_node(state: ContactExpertState):
    current_image_path = state.get("image_path")
    agent = build_step2_react_agent(current_image_path)
    input_msg = HumanMessage(content=f"이미지에서 아산화동(Cu₂O)을 의심할 수 있는 색상 패턴을 관찰하세요. 이미지 경로: {current_image_path}")
    result = agent.invoke({"messages": [input_msg]})
    step_messages = result.get("messages", [])
    print_agent_process(step_messages)
    updated_image_path = _update_image_path_from_messages(step_messages, current_image_path)
    
    step_result = None
    for msg in reversed(step_messages):
        if isinstance(msg, ToolMessage) and msg.name == "analyze_spectral_analysis_internal":
            try:
                step_result = json.loads(msg.content)
                break
            except:
                pass
    if step_result is None and step_messages:
        step_result = {"result_text": step_messages[-1].content}

    return {
        "messages": step_messages,
        "contact_step2_result": step_result,
        "image_path": updated_image_path
    }

def step3_node(state: ContactExpertState):
    import json
    import time
    print("\n[DEBUG] step3_node 시작")
    current_image_path = state.get("image_path")
    
    agent = build_step3_react_agent(current_image_path)
    input_msg = HumanMessage(content=f"이미지에서 열적 구배(Thermal Gradient) 패턴을 분석하세요. 이미지 경로: {current_image_path}")
    
    print("\n[DEBUG] step3_node agent.invoke 호출 시작")
    result = agent.invoke({"messages": [input_msg]})
    print("\n[DEBUG] step3_node agent.invoke 호출 완료")
    
    step_messages = result.get("messages", [])
    print_agent_process(step_messages)
    updated_image_path = _update_image_path_from_messages(step_messages, current_image_path)
    
    step3_result = None
    # ToolMessage에서 결과 추출 (Step 1, 2, 4와 동일한 방식)
    for msg in reversed(step_messages):
        if isinstance(msg, ToolMessage) and msg.name == "analyze_thermal_gradient_internal":
            try:
                # 툴 메시지 내용이 단순 문자열일 수 있으므로 처리
                content = str(msg.content)
                # JSON 파싱 시도
                step3_result = json.loads(content)
                break
            except Exception as e:
                print(f"[DEBUG] Step3 파싱 에러: {e}")
                pass
    
    # 여전히 결과가 없으면 마지막 메시지 내용 사용
    if step3_result is None and step_messages:
        last_msg = step_messages[-1]
        try:
            content = str(last_msg.content).strip()
            # 코드 블록 마커 제거
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            step3_result = json.loads(content.strip())
        except:
            step3_result = {"result_text": str(last_msg.content)}
    
    print("\n[DEBUG] step3_node 종료")
    return {
        "messages": step_messages,
        "contact_step3_result": step3_result,
        "image_path": updated_image_path
    }

def step4_node(state: ContactExpertState):
    import json
    import threading
    
    print("\n[DEBUG] step4_node 시작")
    current_image_path = state.get("image_path")
    
    agent = build_step4_react_agent(current_image_path)
    input_msg = HumanMessage(content=f"이미지에서 금속 표면의 전기적 부식 흔적을 분석하세요. 이미지 경로: {current_image_path}")
    
    result_container = {"result": None, "error": None}
    
    def agent_runner():
        try:
            # Recursion Limit을 10으로 제한하여 무한 루프 방지
            result_container["result"] = agent.invoke(
                {"messages": [input_msg]}, 
                config={"recursion_limit": 10}
            )
        except Exception as e:
            result_container["error"] = e

    # 데몬 스레드로 실행 (메인 스레드 종료 시 함께 종료됨)
    thread = threading.Thread(target=agent_runner)
    thread.daemon = True
    thread.start()
    
    # 300초(5분) 대기
    thread.join(timeout=300.0)
    
    if thread.is_alive():
        print("\n[ERROR] step4_node 타임아웃 (300초 초과)")
        # 타임아웃 발생 시 가짜 결과 생성
        error_json = json.dumps({"error": "타임아웃: Step4 분석이 5분을 초과하여 중단되었습니다."})
        result = {
            "messages": [
                input_msg,
                ToolMessage(
                    content=error_json,
                    tool_call_id="timeout_fallback",
                    name="analyze_surface_analysis_internal" 
                )
            ]
        }
    elif result_container["error"]:
        print(f"\n[ERROR] step4_node 실행 중 오류: {result_container['error']}")
        error_json = json.dumps({"error": f"분석 중 오류 발생: {str(result_container['error'])}"})
        result = {
            "messages": [
                input_msg,
                ToolMessage(
                    content=error_json,
                    tool_call_id="error_fallback",
                    name="analyze_surface_analysis_internal"
                )
            ]
        }
    else:
        result = result_container["result"]

    # 방어 코드: result가 None인 경우 (예: 스레드 오류 등)
    if result is None:
        print(f"\n[ERROR] step4_node 결과 누락. result_container: {result_container}")
        error_json = json.dumps({"error": "내부 오류: 에이전트 결과가 None입니다."})
        result = {
            "messages": [
                input_msg,
                ToolMessage(
                    content=error_json,
                    tool_call_id="null_result_fallback",
                    name="analyze_surface_analysis_internal"
                )
            ]
        }
    
    step_messages = result.get("messages", [])
    
    # 과정 출력
    print_agent_process(step_messages)

    updated_image_path = _update_image_path_from_messages(step_messages, current_image_path)
    
    step_result = None
    for msg in reversed(step_messages):
        if isinstance(msg, ToolMessage) and msg.name == "analyze_surface_analysis_internal":
            try:
                step_result = json.loads(msg.content)
                break
            except:
                pass
    if step_result is None and step_messages:
        last_content = step_messages[-1].content
        step_result = {"result_text": str(last_content)}

    return {
        "messages": step_messages,
        "contact_step4_result": step_result,
        "image_path": updated_image_path
    }
