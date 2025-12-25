"""
1단계: 핵심 인프라 구축 테스트
각 컴포넌트별 단위 테스트
"""
import json
import time
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 로그 파일 경로
LOG_PATH = Path(__file__).parent.parent / ".cursor" / "debug.log"


def log_debug(session_id: str, run_id: str, hypothesis_id: str, location: str, 
              message: str, data: dict = None):
    """디버그 로그 기록"""
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            log_entry = {
                "sessionId": session_id,
                "runId": run_id,
                "hypothesisId": hypothesis_id,
                "location": location,
                "message": message,
                "data": data or {},
                "timestamp": int(time.time() * 1000)
            }
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    except Exception as e:
        print(f"로그 기록 실패: {e}")


def test_react_state():
    """ReActState 정의 테스트"""
    log_debug("test-step1", "run1", "A", "test_step1_infrastructure.py:test_react_state", 
              "테스트 시작", {"test": "ReActState"})
    
    try:
        # 파일 존재 확인
        state_file = project_root / "src" / "state.py"
        if not state_file.exists():
            raise FileNotFoundError(f"파일 없음: {state_file}")
        
        # 파일 내용 확인
        with open(state_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if "class ReActState" not in content:
                raise ValueError("ReActState 클래스가 정의되지 않음")
            if "MessagesState" not in content:
                raise ValueError("MessagesState 상속이 없음")
            if "task: Optional[str]" not in content:
                raise ValueError("task 필드가 정의되지 않음")
            if "context: Optional[Dict" not in content:
                raise ValueError("context 필드가 정의되지 않음")
        
        log_debug("test-step1", "run1", "A", "test_step1_infrastructure.py:test_react_state",
                  "테스트 성공", {"file_exists": True, "has_class": True, "has_fields": True})
        print("✅ ReActState 정의 확인 완료")
        return True
        
    except Exception as e:
        log_debug("test-step1", "run1", "A", "test_step1_infrastructure.py:test_react_state",
                  "테스트 실패", {"error": str(e), "error_type": type(e).__name__})
        print(f"❌ ReActState 테스트 실패: {e}")
        return False


def test_gemini_chatmodel():
    """Gemini ChatModel 래퍼 테스트"""
    log_debug("test-step1", "run1", "B", "test_step1_infrastructure.py:test_gemini_chatmodel",
              "테스트 시작", {"test": "GeminiChatModel"})
    
    try:
        # 파일 존재 확인
        chatmodel_file = project_root / "src" / "agents" / "gemini_chatmodel.py"
        if not chatmodel_file.exists():
            raise FileNotFoundError(f"파일 없음: {chatmodel_file}")
        
        # 파일 내용 확인
        with open(chatmodel_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if "class GeminiChatModel" not in content:
                raise ValueError("GeminiChatModel 클래스가 정의되지 않음")
            if "BaseChatModel" not in content:
                raise ValueError("BaseChatModel 상속이 없음")
            if "_generate" not in content:
                raise ValueError("_generate 메서드가 없음")
            if "_convert_messages" not in content:
                raise ValueError("_convert_messages 메서드가 없음")
        
        log_debug("test-step1", "run1", "B", "test_step1_infrastructure.py:test_gemini_chatmodel",
                  "테스트 성공", {"file_exists": True, "has_class": True, "has_methods": True})
        print("✅ GeminiChatModel 정의 확인 완료")
        return True
        
    except Exception as e:
        log_debug("test-step1", "run1", "B", "test_step1_infrastructure.py:test_gemini_chatmodel",
                  "테스트 실패", {"error": str(e), "error_type": type(e).__name__})
        print(f"❌ GeminiChatModel 테스트 실패: {e}")
        return False


def test_tool_registry():
    """도구 레지스트리 테스트"""
    log_debug("test-step1", "run1", "C", "test_step1_infrastructure.py:test_tool_registry",
              "테스트 시작", {"test": "ToolRegistry"})
    
    try:
        # 파일 존재 확인
        registry_file = project_root / "src" / "tools" / "registry.py"
        if not registry_file.exists():
            raise FileNotFoundError(f"파일 없음: {registry_file}")
        
        # 파일 내용 확인
        with open(registry_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if "class ToolRegistry" not in content:
                raise ValueError("ToolRegistry 클래스가 정의되지 않음")
            if "_initialize_tools" not in content:
                raise ValueError("_initialize_tools 메서드가 없음")
            if "get_tools" not in content:
                raise ValueError("get_tools 메서드가 없음")
            if "ImageAnalyzerTool" not in content:
                raise ValueError("ImageAnalyzerTool import가 없음")
            if "RunPreprocessingPipelineTool" not in content:
                raise ValueError("RunPreprocessingPipelineTool import가 없음")
        
        log_debug("test-step1", "run1", "C", "test_step1_infrastructure.py:test_tool_registry",
                  "테스트 성공", {"file_exists": True, "has_class": True, "has_methods": True})
        print("✅ ToolRegistry 정의 확인 완료")
        return True
        
    except Exception as e:
        log_debug("test-step1", "run1", "C", "test_step1_infrastructure.py:test_tool_registry",
                  "테스트 실패", {"error": str(e), "error_type": type(e).__name__})
        print(f"❌ ToolRegistry 테스트 실패: {e}")
        return False


def test_react_agent_builder():
    """ReAct 에이전트 빌더 테스트"""
    log_debug("test-step1", "run1", "D", "test_step1_infrastructure.py:test_react_agent_builder",
              "테스트 시작", {"test": "build_react_agent_graph"})
    
    try:
        # 파일 존재 확인
        react_agent_file = project_root / "src" / "agents" / "react_agent.py"
        if not react_agent_file.exists():
            raise FileNotFoundError(f"파일 없음: {react_agent_file}")
        
        # 파일 내용 확인
        with open(react_agent_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if "def build_react_agent_graph" not in content:
                raise ValueError("build_react_agent_graph 함수가 정의되지 않음")
            if "create_react_agent" not in content:
                raise ValueError("create_react_agent import가 없음")
            if "GeminiChatModel" not in content:
                raise ValueError("GeminiChatModel import가 없음")
            if "ToolRegistry" not in content:
                raise ValueError("ToolRegistry import가 없음")
        
        log_debug("test-step1", "run1", "D", "test_step1_infrastructure.py:test_react_agent_builder",
                  "테스트 성공", {"file_exists": True, "has_function": True, "has_imports": True})
        print("✅ ReAct 에이전트 빌더 정의 확인 완료")
        return True
        
    except Exception as e:
        log_debug("test-step1", "run1", "D", "test_step1_infrastructure.py:test_react_agent_builder",
                  "테스트 실패", {"error": str(e), "error_type": type(e).__name__})
        print(f"❌ ReAct 에이전트 빌더 테스트 실패: {e}")
        return False


def test_tools():
    """개별 도구 테스트"""
    log_debug("test-step1", "run1", "E", "test_step1_infrastructure.py:test_tools",
              "테스트 시작", {"test": "Individual Tools"})
    
    try:
        # 이미지 도구 파일 확인
        image_tools_file = project_root / "src" / "tools" / "tools" / "image_tools.py"
        if not image_tools_file.exists():
            raise FileNotFoundError(f"파일 없음: {image_tools_file}")
        
        with open(image_tools_file, 'r', encoding='utf-8') as f:
            content = f.read()
            required_classes = [
                "ImageAnalyzerTool", "ImageEnhancerTool",
                "ImageCropperTool", "ImageFilterTool"
            ]
            for cls_name in required_classes:
                if f"class {cls_name}" not in content:
                    raise ValueError(f"{cls_name} 클래스가 정의되지 않음")
            if "args_schema" not in content:
                raise ValueError("args_schema가 정의되지 않음")
            if "BaseModel" not in content:
                raise ValueError("Pydantic BaseModel import가 없음")
        
        # 파이프라인 도구 파일 확인
        pipeline_tools_file = project_root / "src" / "tools" / "tools" / "pipeline_tools.py"
        if not pipeline_tools_file.exists():
            raise FileNotFoundError(f"파일 없음: {pipeline_tools_file}")
        
        with open(pipeline_tools_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if "RunPreprocessingPipelineTool" not in content:
                raise ValueError("RunPreprocessingPipelineTool 클래스가 정의되지 않음")
            if "RunInvestigationPipelineTool" not in content:
                raise ValueError("RunInvestigationPipelineTool 클래스가 정의되지 않음")
        
        log_debug("test-step1", "run1", "E", "test_step1_infrastructure.py:test_tools",
                  "테스트 성공", {
                      "image_tools_file_exists": True,
                      "pipeline_tools_file_exists": True,
                      "has_all_classes": True
                  })
        print("✅ 도구 정의 확인 완료 (6개 도구)")
        return True
        
    except Exception as e:
        log_debug("test-step1", "run1", "E", "test_step1_infrastructure.py:test_tools",
                  "테스트 실패", {"error": str(e), "error_type": type(e).__name__})
        print(f"❌ 도구 테스트 실패: {e}")
        return False


def run_all_tests():
    """모든 1단계 테스트 실행"""
    print("\n" + "=" * 60)
    print("1단계: 핵심 인프라 구축 테스트 시작")
    print("=" * 60 + "\n")
    
    results = []
    
    # 각 테스트 실행
    results.append(("ReActState", test_react_state()))
    results.append(("GeminiChatModel", test_gemini_chatmodel()))
    results.append(("ToolRegistry", test_tool_registry()))
    results.append(("Tools", test_tools()))
    results.append(("ReAct Agent Builder", test_react_agent_builder()))
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 통과" if result else "❌ 실패"
        print(f"{name}: {status}")
    
    print(f"\n총 {passed}/{total} 테스트 통과")
    print("=" * 60 + "\n")
    
    return all(result for _, result in results)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

