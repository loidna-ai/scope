"""
Mechanical 전문가 노드 및 ReAct 에이전트 정의
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
from src.tools.experts.mechanical_tools import (
    step1_mechanical_deformation,
    step2_strand_splaying,
    step3_bead_confinement
)
from src.prompts.mechanical_expert_prompts import (
    get_step1_react_prompt,
    get_step2_react_prompt,
    get_step3_react_prompt
)

class MechanicalExpertState(MessagesState):
    """
    Mechanical Expert ReAct State
    """
    mechanical_step1_result: Optional[Dict[str, Any]]
    mechanical_step2_result: Optional[Dict[str, Any]]
    mechanical_step3_result: Optional[Dict[str, Any]]
    image_path: Optional[str]

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
    def analyze_mechanical_deformation_internal(image_path: str) -> str:
        """이미지에서 기계적 변형 흔적(찍힘, 절단면 등)을 분석합니다. 이미지 보정이 필요하면 먼저 보정 도구를 사용하세요."""
        try:
            image_data = _load_image_data(image_path)
            result = step1_mechanical_deformation(image_data, verbose=False)
            return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    all_tools = [analyze_mechanical_deformation_internal] + image_editing_tools
    react_prompt = get_step1_react_prompt()
    return create_react_agent(model=llm, tools=all_tools, prompt=react_prompt)

def build_step2_react_agent(image_path: str):
    llm = GeminiChatModel()
    registry = ToolRegistry()
    image_editing_tools = registry.get_tools_by_category("image")
    
    @tool
    def analyze_strand_splaying_internal(image_path: str) -> str:
        """이미지에서 소선 배열의 흐트러짐을 분석합니다. 이미지 보정이 필요하면 먼저 보정 도구를 사용하세요."""
        try:
            image_data = _load_image_data(image_path)
            result = step2_strand_splaying(image_data, verbose=False)
            return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    all_tools = [analyze_strand_splaying_internal] + image_editing_tools
    react_prompt = get_step2_react_prompt()
    return create_react_agent(model=llm, tools=all_tools, prompt=react_prompt)

def build_step3_react_agent(image_path: str):
    llm = GeminiChatModel()
    registry = ToolRegistry()
    image_editing_tools = registry.get_tools_by_category("image")
    
    @tool
    def analyze_bead_confinement_internal(image_path: str) -> str:
        """이미지에서 단락흔(망울)의 위치와 기계적 구속 여부를 분석합니다. 이미지 보정이 필요하면 먼저 보정 도구를 사용하세요."""
        try:
            image_data = _load_image_data(image_path)
            result = step3_bead_confinement(image_data, verbose=False)
            return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    all_tools = [analyze_bead_confinement_internal] + image_editing_tools
    react_prompt = get_step3_react_prompt()
    return create_react_agent(model=llm, tools=all_tools, prompt=react_prompt)

# --------------------------------------------------------------------------------
# Step Node 정의
# --------------------------------------------------------------------------------

def step1_node(state: MechanicalExpertState):
    current_image_path = state.get("image_path")
    agent = build_step1_react_agent(current_image_path)
    input_msg = HumanMessage(content=f"이미지를 분석하여 기계적 변형 흔적을 식별하세요. 이미지 경로: {current_image_path}")
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
        if isinstance(msg, ToolMessage) and msg.name == "analyze_mechanical_deformation_internal":
            try:
                step_result = json.loads(msg.content)
                break
            except:
                pass

    return {
        "messages": step_messages,
        "mechanical_step1_result": step_result,
        "image_path": updated_image_path
    }

def step2_node(state: MechanicalExpertState):
    current_image_path = state.get("image_path")
    agent = build_step2_react_agent(current_image_path)
    input_msg = HumanMessage(content=f"이미지에서 소선 배열의 흐트러짐을 분석하세요. 이미지 경로: {current_image_path}")
    result = agent.invoke({"messages": [input_msg]})
    step_messages = result.get("messages", [])
    print_agent_process(step_messages)
    updated_image_path = _update_image_path_from_messages(step_messages, current_image_path)
    
    step_result = None
    for msg in reversed(step_messages):
        if isinstance(msg, ToolMessage) and msg.name == "analyze_strand_splaying_internal":
            try:
                step_result = json.loads(msg.content)
                break
            except:
                pass
    if step_result is None and step_messages:
        step_result = {"result_text": step_messages[-1].content}

    return {
        "messages": step_messages,
        "mechanical_step2_result": step_result,
        "image_path": updated_image_path
    }

def step3_node(state: MechanicalExpertState):
    current_image_path = state.get("image_path")
    agent = build_step3_react_agent(current_image_path)
    input_msg = HumanMessage(content=f"이미지에서 단락흔의 위치와 구속 여부를 분석하세요. 이미지 경로: {current_image_path}")
    result = agent.invoke({"messages": [input_msg]})
    step_messages = result.get("messages", [])
    print_agent_process(step_messages)
    updated_image_path = _update_image_path_from_messages(step_messages, current_image_path)
    
    step_result = None
    for msg in reversed(step_messages):
        if isinstance(msg, ToolMessage) and msg.name == "analyze_bead_confinement_internal":
            try:
                step_result = json.loads(msg.content)
                break
            except:
                pass
    if step_result is None and step_messages:
        step_result = {"result_text": step_messages[-1].content}

    return {
        "messages": step_messages,
        "mechanical_step3_result": step_result,
        "image_path": updated_image_path
    }
