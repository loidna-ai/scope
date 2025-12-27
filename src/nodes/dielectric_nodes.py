"""
Dielectric 전문가 노드 및 ReAct 에이전트 정의
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
from src.tools.experts.dielectric_tools import (
    step1_carbonization_depth,
    step2_swelling_analysis,
    step3_global_aging
)
from src.prompts.dielectric_expert_prompts import (
    get_step1_react_prompt,
    get_step2_react_prompt,
    get_step3_react_prompt
)

class DielectricExpertState(MessagesState):
    """
    Dielectric Expert ReAct State
    """
    dielectric_step1_result: Optional[Dict[str, Any]]
    dielectric_step2_result: Optional[Dict[str, Any]]
    dielectric_step3_result: Optional[Dict[str, Any]]
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
    def analyze_carbonization_depth_internal(image_path: str) -> str:
        """이미지에서 절연체의 탄화 심도와 방향을 분석합니다. 이미지 보정이 필요하면 먼저 보정 도구를 사용하세요."""
        try:
            image_data = _load_image_data(image_path)
            result = step1_carbonization_depth(image_data, verbose=False)
            return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    all_tools = [analyze_carbonization_depth_internal] + image_editing_tools
    react_prompt = get_step1_react_prompt()
    return create_react_agent(model=llm, tools=all_tools, prompt=react_prompt)

def build_step2_react_agent(image_path: str):
    llm = GeminiChatModel()
    registry = ToolRegistry()
    image_editing_tools = registry.get_tools_by_category("image")
    
    @tool
    def analyze_swelling_internal(image_path: str) -> str:
        """이미지에서 절연체의 스펀지 현상, 흑연화, 단순 용융을 분석합니다. 이미지 보정이 필요하면 먼저 보정 도구를 사용하세요."""
        try:
            image_data = _load_image_data(image_path)
            result = step2_swelling_analysis(image_data, verbose=False)
            return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    all_tools = [analyze_swelling_internal] + image_editing_tools
    react_prompt = get_step2_react_prompt()
    return create_react_agent(model=llm, tools=all_tools, prompt=react_prompt)

def build_step3_react_agent(image_path: str):
    llm = GeminiChatModel()
    registry = ToolRegistry()
    image_editing_tools = registry.get_tools_by_category("image")
    
    @tool
    def analyze_global_aging_internal(image_path: str) -> str:
        """이미지에서 전선 전체의 광역적 노후화 징후(균열, 변색 등)를 분석합니다. 이미지 보정이 필요하면 먼저 보정 도구를 사용하세요."""
        try:
            image_data = _load_image_data(image_path)
            result = step3_global_aging(image_data, verbose=False)
            return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    all_tools = [analyze_global_aging_internal] + image_editing_tools
    react_prompt = get_step3_react_prompt()
    return create_react_agent(model=llm, tools=all_tools, prompt=react_prompt)

# --------------------------------------------------------------------------------
# Step Node 정의
# --------------------------------------------------------------------------------

def step1_node(state: DielectricExpertState):
    current_image_path = state.get("image_path")
    agent = build_step1_react_agent(current_image_path)
    input_msg = HumanMessage(content=f"이미지를 분석하여 절연체의 탄화 심도와 방향을 식별하세요. 이미지 경로: {current_image_path}")
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
        if isinstance(msg, ToolMessage) and msg.name == "analyze_carbonization_depth_internal":
            try:
                step_result = json.loads(msg.content)
                break
            except:
                pass

    return {
        "messages": step_messages,
        "dielectric_step1_result": step_result,
        "image_path": updated_image_path
    }

def step2_node(state: DielectricExpertState):
    current_image_path = state.get("image_path")
    agent = build_step2_react_agent(current_image_path)
    input_msg = HumanMessage(content=f"이미지에서 절연체의 스펀지 현상, 흑연화, 단순 용융을 분석하세요. 이미지 경로: {current_image_path}")
    result = agent.invoke({"messages": [input_msg]})
    step_messages = result.get("messages", [])
    print_agent_process(step_messages)
    updated_image_path = _update_image_path_from_messages(step_messages, current_image_path)
    
    step_result = None
    for msg in reversed(step_messages):
        if isinstance(msg, ToolMessage) and msg.name == "analyze_swelling_internal":
            try:
                step_result = json.loads(msg.content)
                break
            except:
                pass
    if step_result is None and step_messages:
        step_result = {"result_text": step_messages[-1].content}

    return {
        "messages": step_messages,
        "dielectric_step2_result": step_result,
        "image_path": updated_image_path
    }

def step3_node(state: DielectricExpertState):
    current_image_path = state.get("image_path")
    agent = build_step3_react_agent(current_image_path)
    input_msg = HumanMessage(content=f"이미지에서 광역적 노후화 징후를 분석하세요. 이미지 경로: {current_image_path}")
    result = agent.invoke({"messages": [input_msg]})
    step_messages = result.get("messages", [])
    print_agent_process(step_messages)
    updated_image_path = _update_image_path_from_messages(step_messages, current_image_path)
    
    step_result = None
    for msg in reversed(step_messages):
        if isinstance(msg, ToolMessage) and msg.name == "analyze_global_aging_internal":
            try:
                step_result = json.loads(msg.content)
                break
            except:
                pass
    if step_result is None and step_messages:
        step_result = {"result_text": step_messages[-1].content}

    return {
        "messages": step_messages,
        "dielectric_step3_result": step_result,
        "image_path": updated_image_path
    }
