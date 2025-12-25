"""
ReAct 에이전트 서브그래프 빌더
LangGraph의 create_react_agent를 사용하여 ReAct 에이전트를 생성합니다.
"""
import threading
from typing import Optional
from langgraph.prebuilt import create_react_agent
from langgraph.graph.state import CompiledStateGraph
from src.agents.gemini_chatmodel import GeminiChatModel
from src.tools.registry import ToolRegistry


# 싱글톤 패턴으로 그래프 재사용
_react_agent_graph: Optional[CompiledStateGraph] = None
_graph_lock = threading.Lock()


def build_react_agent_graph() -> CompiledStateGraph:
    """
    ReAct 에이전트 서브그래프 빌드 (통합)
    
    LangGraph 공식 권장 방식:
    - create_react_agent는 MessagesState를 기본으로 사용
    - 반환 타입은 CompiledGraph (StateGraph가 아님)
    - 기존 파이프라인 도구를 사용하여 기존 전문가 서브그래프를 간접적으로 호출 가능
    
    Returns:
        컴파일된 ReAct 에이전트 그래프
    """
    # #region agent log
    import json
    import time
    try:
        with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"A","location":"react_agent.py:build_react_agent_graph","message":"함수 시작","data":{},"timestamp":int(time.time()*1000)})+'\n')
    except: pass
    # #endregion
    
    try:
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"A","location":"react_agent.py:build_react_agent_graph","message":"GeminiChatModel 생성 시작","data":{},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        llm = GeminiChatModel()
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"A","location":"react_agent.py:build_react_agent_graph","message":"GeminiChatModel 생성 완료","data":{"has_client":llm.client is not None,"model_name":llm.model_name},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"B","location":"react_agent.py:build_react_agent_graph","message":"ToolRegistry 생성 시작","data":{},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        registry = ToolRegistry()
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                tools = registry.get_tools()
                f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"B","location":"react_agent.py:build_react_agent_graph","message":"ToolRegistry 생성 완료","data":{"tools_count":len(tools),"tool_names":[t.name for t in tools]},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        tools = registry.get_tools()  # 모든 도구 (기본: image_tools, pipeline_tools)
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"C","location":"react_agent.py:build_react_agent_graph","message":"create_react_agent 호출 시작","data":{"tools_count":len(tools)},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # LangGraph 공식 권장: create_react_agent 사용
        try:
            # #region agent log
            try:
                with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"C","location":"react_agent.py:build_react_agent_graph","message":"create_react_agent 호출 직전","data":{"llm_type":type(llm).__name__,"llm_has_stream":hasattr(llm,'_stream'),"tools_count":len(tools)},"timestamp":int(time.time()*1000)})+'\n')
            except: pass
            # #endregion
            
            agent = create_react_agent(
                model=llm,
                tools=tools,
                prompt=(
                    "당신은 ReAct 패턴을 따르는 AI 에이전트입니다. "
                    "사용자의 작업을 수행하기 위해 필요한 도구를 사용하세요.\n\n"
                    "중요 지침:\n"
                    "- 당신은 이미지 편집 및 분석 도구만 사용할 수 있습니다. "
                    "각 전문가(접촉불량, 절연열화, 기계적, 추적, 소선파단)는 이미 병렬로 실행되고 있습니다.\n"
                    "- 사용 가능한 이미지 편집 도구:\n"
                    "  * `enhance_image`: Real-ESRGAN을 사용하여 이미지를 4배 초해상도로 향상\n"
                    "  * `apply_clahe_filter`: CLAHE 필터를 적용하여 대비 향상\n"
                    "  * `crop_image`: 단락흔 영역을 탐지하고 크롭\n"
                    "  * `analyze_image_morphology`: 이미지의 형태학적 특성 분석 (원형도, 고형도, 면적)\n"
                    "  * `run_preprocessing_pipeline`: 이미지 전처리 파이프라인 실행\n"
                    "- 이미지 품질이 낮거나 분석이 어려운 경우, 적절한 이미지 편집 도구를 사용하여 이미지를 개선하세요.\n"
                    "- 각 전문가는 이미지 품질이 낮을 때 자동으로 이미지를 향상시키지만, "
                    "추가적인 이미지 편집이 필요하다고 판단되면 도구를 사용하세요.\n"
                    "- 도구 호출 시 반드시 사용자 메시지에서 제공된 정확한 이미지 경로를 사용하세요. "
                    "임의로 경로를 추측하거나 변경하지 마세요.\n"
                    "- 같은 도구를 같은 인자로 두 번 이상 연속으로 호출하지 마세요. "
                    "도구가 에러를 반환하면 다른 방법을 시도하거나 사용자에게 결과를 보고하세요.\n"
                    "- **반드시** 최종 답변을 제공할 때는 반드시 'Final Answer:'로 시작해야 합니다. "
                    "이것은 에이전트가 작업을 완료했음을 나타내는 신호입니다.\n"
                    "- 예시: 'Final Answer: [여기에 최종 답변 내용]'"
                )
            )
            
            # #region agent log
            try:
                with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"C","location":"react_agent.py:build_react_agent_graph","message":"create_react_agent 호출 완료","data":{"has_agent":agent is not None,"has_invoke":hasattr(agent,'invoke')},"timestamp":int(time.time()*1000)})+'\n')
            except: pass
            # #endregion
        except Exception as create_error:
            # #region agent log
            try:
                import traceback
                tb_str = ''.join(traceback.format_exception(type(create_error), create_error, create_error.__traceback__))
                with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"ERROR","location":"react_agent.py:build_react_agent_graph","message":"create_react_agent 호출 중 예외","data":{"error":str(create_error),"error_type":type(create_error).__name__,"traceback":tb_str[:1000]},"timestamp":int(time.time()*1000)})+'\n')
            except: pass
            # #endregion
            raise
        
        # create_react_agent는 이미 컴파일된 그래프를 반환
        return agent
        
    except Exception as e:
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"ERROR","location":"react_agent.py:build_react_agent_graph","message":"에러 발생","data":{"error":str(e),"error_type":type(e).__name__},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        raise


def _get_react_agent_graph() -> CompiledStateGraph:
    """
    ReAct 에이전트 서브그래프를 싱글톤으로 반환 (Thread-safe)
    
    Returns:
        컴파일된 ReAct 에이전트 그래프
    """
    global _react_agent_graph
    if _react_agent_graph is None:
        with _graph_lock:
            if _react_agent_graph is None:
                _react_agent_graph = build_react_agent_graph()
    return _react_agent_graph

