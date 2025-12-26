"""
Gemini ChatModel 래퍼
Google Gemini를 LangChain ChatModel 인터페이스로 래핑하여 LangGraph와 통합합니다.
"""
from typing import List, Optional, Dict, Any, Iterator
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun
from pydantic import ConfigDict
from google import genai
from google.genai import types
from src.nodes.experts.expert_utils import client, generation_config, MODEL_NAME


class GeminiChatModel(BaseChatModel):
    """
    Google Gemini를 LangChain ChatModel로 래핑
    
    LangGraph의 create_react_agent와 호환되도록 구현합니다.
    """
    
    # Pydantic v2 설정: 추가 필드 허용
    model_config = ConfigDict(extra="allow")
    
    def __init__(self, **kwargs):
        """Gemini ChatModel 초기화"""
        # #region agent log
        import json
        import time
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:__init__","message":"GeminiChatModel 초기화 시작","data":{},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        super().__init__(**kwargs)
        # 현재 프로젝트의 설정 사용
        object.__setattr__(self, "client", client)
        object.__setattr__(self, "config", generation_config)
        object.__setattr__(self, "model_name", MODEL_NAME)
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:__init__","message":"GeminiChatModel 초기화 완료","data":{"has_client":self.client is not None,"model_name":self.model_name},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
    
    @property
    def _llm_type(self) -> str:
        """LLM 타입 반환"""
        return "gemini"
    
    def bind_tools(self, tools: List[Any], **kwargs: Any) -> "GeminiChatModel":
        """
        도구를 모델에 바인딩
        
        Args:
            tools: 바인딩할 도구 리스트
            **kwargs: 추가 인자
        
        Returns:
            도구가 바인딩된 새로운 GeminiChatModel 인스턴스
        """
        # #region agent log
        import json
        import time
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:bind_tools","message":"bind_tools 호출","data":{"tools_count":len(tools) if tools else 0},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # 새로운 인스턴스 생성 (도구 바인딩)
        bound_model = GeminiChatModel()
        # 원본 인스턴스의 속성 복사
        object.__setattr__(bound_model, "client", self.client)
        object.__setattr__(bound_model, "config", self.config)
        object.__setattr__(bound_model, "model_name", self.model_name)
        # 도구를 인스턴스에 저장
        object.__setattr__(bound_model, "bound_tools", tools)
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:bind_tools","message":"bind_tools 완료","data":{"has_bound_tools":hasattr(bound_model,'bound_tools')},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        return bound_model
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        동기 생성 메서드
        
        Args:
            messages: LangChain 메시지 리스트
            stop: 중지 시퀀스 (선택적)
            run_manager: 콜백 매니저 (선택적)
            **kwargs: 추가 인자
        
        Returns:
            ChatResult 객체
        """
        # #region agent log
        import json
        import time
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:_generate","message":"_generate 호출 시작","data":{"messages_count":len(messages),"has_tools":"tools" in kwargs,"tools_count":len(kwargs.get("tools",[]))},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        if self.client is None:
            raise ValueError("Gemini client가 초기화되지 않았습니다.")
        
        # LangChain 메시지를 Gemini 형식으로 변환
        contents = self._convert_messages(messages)
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:_generate","message":"메시지 변환 완료","data":{"contents_count":len(contents),"contents_types":[type(c).__name__ for c in contents]},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # Function calling 지원을 위한 설정
        # ReAct 에이전트용 시스템 인스트럭션 추가
        react_system_instruction = (
            "당신은 ReAct 패턴을 따르는 AI 에이전트입니다. "
            "도구 실행 결과를 받은 후 최종 답변을 제공할 때는 반드시 'Final Answer:'로 시작하세요. "
            "예시: 'Final Answer: [여기에 최종 답변 내용]'"
        )
        config = types.GenerateContentConfig(
            temperature=self.config.temperature if self.config else 0.7,
            system_instruction=react_system_instruction,
        )
        
        # 도구가 있으면 추가 (kwargs의 tools 우선, 없으면 bound_tools 사용)
        tools = kwargs.get("tools", []) or getattr(self, "bound_tools", [])
        if tools:
            function_declarations = self._create_function_declarations(tools)
            config.tools = [types.Tool(function_declarations=function_declarations)]
            # #region agent log
            try:
                with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"D","location":"gemini_chatmodel.py:_generate","message":"도구 선언 생성 완료","data":{"function_declarations_count":len(function_declarations),"function_names":[fd.get("name","") for fd in function_declarations]},"timestamp":int(time.time()*1000)})+'\n')
            except: pass
            # #endregion
        
        try:
            # #region agent log
            try:
                with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:_generate","message":"Gemini API 호출 시작","data":{"model_name":self.model_name},"timestamp":int(time.time()*1000)})+'\n')
            except: pass
            # #endregion
            
            # Gemini API 호출
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )
            
            # #region agent log
            try:
                with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    # 경고 방지: response.text 접근 대신 candidates 확인
                    has_candidates = hasattr(response, "candidates") and response.candidates
                    has_parts = False
                    text_parts_count = 0
                    function_call_count = 0
                    if has_candidates and response.candidates:
                        candidate = response.candidates[0]
                        if hasattr(candidate, "content") and candidate.content:
                            if hasattr(candidate.content, "parts"):
                                parts = candidate.content.parts
                                has_parts = True
                                text_parts_count = sum(1 for p in parts if hasattr(p, "text") and p.text)
                                function_call_count = sum(1 for p in parts if hasattr(p, "function_call") and p.function_call)
                    f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:_generate","message":"Gemini API 호출 완료","data":{"has_candidates":has_candidates,"has_parts":has_parts,"text_parts_count":text_parts_count,"function_call_count":function_call_count},"timestamp":int(time.time()*1000)})+'\n')
            except: pass
            # #endregion
            
            # Gemini 응답을 AIMessage로 변환
            ai_message = self._convert_response_to_message(response)
            
            # #region agent log
            try:
                with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    has_tool_calls = hasattr(ai_message, "tool_calls") and ai_message.tool_calls
                    f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:_generate","message":"AIMessage 변환 완료","data":{"has_content":bool(ai_message.content),"has_tool_calls":has_tool_calls,"tool_calls_count":len(ai_message.tool_calls) if has_tool_calls else 0},"timestamp":int(time.time()*1000)})+'\n')
            except: pass
            # #endregion
            
            # ChatResult 생성
            generation = ChatGeneration(message=ai_message)
            return ChatResult(generations=[generation])
            
        except Exception as e:
            # #region agent log
            try:
                with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"ERROR","location":"gemini_chatmodel.py:_generate","message":"Gemini API 호출 실패","data":{"error":str(e),"error_type":type(e).__name__},"timestamp":int(time.time()*1000)})+'\n')
            except: pass
            # #endregion
            raise ValueError(f"Gemini API 호출 실패: {e}")
    
    def _convert_messages(self, messages: List[BaseMessage]) -> List[Any]:
        """
        LangChain 메시지를 Gemini 형식으로 변환
        
        기존 프로젝트의 expert_utils.py 방식을 참고하여 구현합니다.
        Gemini API는 contents에 문자열이나 types.Part 객체를 받습니다.
        
        Args:
            messages: LangChain 메시지 리스트
        
        Returns:
            Gemini 형식의 contents 리스트 (문자열 또는 types.Part 객체)
        """
        # #region agent log
        import json
        import time
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                message_types = [type(m).__name__ for m in messages]
                f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:_convert_messages","message":"메시지 변환 시작","data":{"messages_count":len(messages),"message_types":message_types},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        contents = []
        
        for message in messages:
            if isinstance(message, SystemMessage):
                # 시스템 메시지는 config에 포함되므로 건너뜀
                continue
            elif isinstance(message, HumanMessage):
                # 텍스트 메시지 - 문자열로 변환
                if isinstance(message.content, str):
                    contents.append(message.content)
                elif isinstance(message.content, list):
                    # 멀티모달 메시지 처리
                    for part in message.content:
                        if isinstance(part, dict):
                            if "type" in part and part["type"] == "image_url":
                                # 이미지 URL 처리 (필요시 types.Part.from_uri 사용)
                                # 현재는 텍스트로만 처리
                                pass
                        elif isinstance(part, str):
                            contents.append(part)
                else:
                    contents.append(str(message.content))
            elif isinstance(message, AIMessage):
                # AI 응답 메시지 - 텍스트만 추출
                if message.content:
                    contents.append(str(message.content))
                # Tool calls는 Gemini API의 function_call 형식으로 변환 필요
                # 하지만 현재는 텍스트 응답만 처리
            elif isinstance(message, ToolMessage):
                # #region agent log
                try:
                    with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                        f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:_convert_messages","message":"ToolMessage 처리","data":{"tool_message_content":str(message.content)[:100]},"timestamp":int(time.time()*1000)})+'\n')
                except: pass
                # #endregion
                # 도구 실행 결과 메시지 - 텍스트로 변환
                contents.append(str(message.content))
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:_convert_messages","message":"메시지 변환 완료","data":{"contents_count":len(contents)},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        return contents
    
    def _convert_response_to_message(self, response: Any) -> AIMessage:
        """
        Gemini 응답을 AIMessage로 변환
        
        Args:
            response: Gemini API 응답 객체
        
        Returns:
            AIMessage 객체
        """
        # #region agent log
        try:
            import json
            import time
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:_convert_response_to_message","message":"함수 시작","data":{"has_response":response is not None},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # 응답 텍스트 및 tool_calls 추출
        text_parts = []
        tool_calls = []
        
        # candidates.content.parts를 직접 확인하여 텍스트와 function_call 분리 처리
        # 주의: text와 function_call은 같은 part에 동시에 있을 수 있으므로 elif가 아닌 독립적으로 처리
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "content") and candidate.content:
                if hasattr(candidate.content, "parts"):
                    for part in candidate.content.parts:
                        # 텍스트 파트 처리 (function_call과 독립적으로 처리)
                        if hasattr(part, "text") and part.text:
                            text_parts.append(part.text)
                        # function_call 파트 처리 (text와 독립적으로 처리)
                        if hasattr(part, "function_call") and part.function_call is not None:
                            # function_call.name이 존재하는지 확인
                            if hasattr(part.function_call, "name") and part.function_call.name:
                                tool_calls.append({
                                    "name": part.function_call.name,
                                    "args": dict(part.function_call.args) if hasattr(part.function_call, "args") and part.function_call.args else {},
                                    "id": f"call_{len(tool_calls)}"
                                })
        
        # 텍스트 결합
        text = " ".join(text_parts) if text_parts else ""
        
        # 경고 방지: response.text는 function_call이 있을 때 경고를 발생시킴
        # 따라서 parts에서 직접 추출한 텍스트만 사용
        # 텍스트가 없고 tool_calls도 없으면 빈 문자열 유지 (경고 방지)
        
        # #region agent log
        try:
            import json
            import time
            # parts 상세 정보 로깅 (디버깅용)
            parts_info = []
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "content") and candidate.content:
                    if hasattr(candidate.content, "parts"):
                        for i, part in enumerate(candidate.content.parts):
                            part_info = {"index": i}
                            if hasattr(part, "text") and part.text:
                                part_info["has_text"] = True
                                part_info["text_len"] = len(part.text)
                                part_info["text_preview"] = part.text[:100]
                            if hasattr(part, "function_call") and part.function_call:
                                part_info["has_function_call"] = True
                                if hasattr(part.function_call, "name"):
                                    part_info["function_name"] = part.function_call.name
                            parts_info.append(part_info)
            
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:_convert_response_to_message","message":"AIMessage 생성 직전","data":{"text_len":len(text),"has_text":bool(text),"tool_calls_count":len(tool_calls),"text_preview":text[:200] if text else "","parts_info":parts_info},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # AIMessage 생성
        message_kwargs = {"content": text}
        if tool_calls:
            message_kwargs["tool_calls"] = tool_calls
        
        ai_message = AIMessage(**message_kwargs)
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"C","location":"gemini_chatmodel.py:_convert_response_to_message","message":"AIMessage 생성 완료","data":{"has_content":bool(ai_message.content),"content_preview":str(ai_message.content)[:200] if ai_message.content else ""},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        return ai_message
    
    def _create_function_declarations(self, tools: List[Any]) -> List[Dict[str, Any]]:
        """
        LangChain Tool을 Gemini Function Declaration로 변환
        
        Args:
            tools: LangChain Tool 리스트
        
        Returns:
            Gemini Function Declaration 리스트
        """
        function_declarations = []
        
        for tool in tools:
            # Tool의 스키마 추출
            if hasattr(tool, "name") and hasattr(tool, "description"):
                function_decl = {
                    "name": tool.name,
                    "description": tool.description,
                }
                
                # 파라미터 스키마 추출
                if hasattr(tool, "args_schema"):
                    schema = tool.args_schema
                    if schema:
                        properties = {}
                        required = []
                        
                        if hasattr(schema, "schema"):
                            json_schema = schema.schema()
                            if "properties" in json_schema:
                                properties = json_schema["properties"]
                            if "required" in json_schema:
                                required = json_schema["required"]
                        
                        function_decl["parameters"] = {
                            "type": "object",
                            "properties": properties,
                            "required": required
                        }
                
                function_declarations.append(function_decl)
        
        return function_declarations
    
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGeneration]:
        """
        스트리밍 생성 메서드 (선택적 구현)
        
        Args:
            messages: LangChain 메시지 리스트
            stop: 중지 시퀀스 (선택적)
            run_manager: 콜백 매니저 (선택적)
            **kwargs: 추가 인자
        
        Yields:
            ChatGeneration 객체
        """
        # 스트리밍은 현재 구현하지 않음 (필요시 추가)
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        yield result.generations[0]

