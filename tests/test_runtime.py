"""
런타임 테스트
실제 ReAct 에이전트 실행 테스트
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


def test_build_react_agent_graph():
    """ReAct 에이전트 그래프 빌드 런타임 테스트"""
    log_debug("runtime-test", "run1", "A", "test_runtime.py:test_build_react_agent_graph",
              "테스트 시작", {"test": "build_react_agent_graph runtime"})
    
    try:
        from src.agents.react_agent import build_react_agent_graph
        
        log_debug("runtime-test", "run1", "A", "test_runtime.py:test_build_react_agent_graph",
                  "함수 호출 전", {"import_success": True})
        
        # 실제 그래프 빌드 시도
        graph = build_react_agent_graph()
        
        log_debug("runtime-test", "run1", "A", "test_runtime.py:test_build_react_agent_graph",
                  "그래프 빌드 완료", {
                      "graph_is_none": graph is None,
                      "has_invoke": hasattr(graph, 'invoke'),
                      "graph_type": type(graph).__name__
                  })
        
        assert graph is not None, "그래프가 None입니다"
        assert hasattr(graph, 'invoke'), "invoke 메서드가 없습니다"
        
        print("✅ ReAct 에이전트 그래프 빌드 성공")
        return True
        
    except ImportError as e:
        log_debug("runtime-test", "run1", "A", "test_runtime.py:test_build_react_agent_graph",
                  "Import 에러", {"error": str(e), "error_type": "ImportError"})
        print(f"⚠️ Import 에러 (의존성 미설치 가능): {e}")
        return False
        
    except Exception as e:
        log_debug("runtime-test", "run1", "A", "test_runtime.py:test_build_react_agent_graph",
                  "테스트 실패", {"error": str(e), "error_type": type(e).__name__})
        print(f"❌ ReAct 에이전트 그래프 빌드 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tool_registry_runtime():
    """도구 레지스트리 런타임 테스트"""
    log_debug("runtime-test", "run1", "B", "test_runtime.py:test_tool_registry_runtime",
              "테스트 시작", {"test": "ToolRegistry runtime"})
    
    try:
        from src.tools.registry import ToolRegistry
        
        registry = ToolRegistry()
        tools = registry.get_tools()
        
        log_debug("runtime-test", "run1", "B", "test_runtime.py:test_tool_registry_runtime",
                  "도구 로드 완료", {
                      "tools_count": len(tools),
                      "tool_names": [t.name for t in tools],
                      "has_args_schema": all(hasattr(t, 'args_schema') for t in tools)
                  })
        
        # 도구가 없어도 레지스트리는 정상 작동해야 함 (의존성 문제로 일부 도구가 없을 수 있음)
        if len(tools) > 0:
            assert all(hasattr(t, 'name') for t in tools), "일부 도구에 name이 없습니다"
            assert all(hasattr(t, 'args_schema') for t in tools), "일부 도구에 args_schema가 없습니다"
            print(f"✅ 도구 레지스트리 런타임 테스트 통과 (도구 수: {len(tools)})")
        else:
            print("⚠️ 도구 레지스트리 생성 성공 (도구 없음 - 의존성 미설치 가능)")
        return True
        
    except ImportError as e:
        log_debug("runtime-test", "run1", "B", "test_runtime.py:test_tool_registry_runtime",
                  "Import 에러", {"error": str(e), "error_type": "ImportError"})
        print(f"⚠️ Import 에러 (의존성 미설치 가능): {e}")
        return False
        
    except Exception as e:
        log_debug("runtime-test", "run1", "B", "test_runtime.py:test_tool_registry_runtime",
                  "테스트 실패", {"error": str(e), "error_type": type(e).__name__})
        print(f"❌ 도구 레지스트리 런타임 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_gemini_chatmodel_runtime():
    """Gemini ChatModel 런타임 테스트"""
    log_debug("runtime-test", "run1", "C", "test_runtime.py:test_gemini_chatmodel_runtime",
              "테스트 시작", {"test": "GeminiChatModel runtime"})
    
    try:
        from src.agents.gemini_chatmodel import GeminiChatModel
        
        llm = GeminiChatModel()
        
        log_debug("runtime-test", "run1", "C", "test_runtime.py:test_gemini_chatmodel_runtime",
                  "ChatModel 생성 완료", {
                      "has_client": llm.client is not None,
                      "model_name": llm.model_name,
                      "llm_type": llm._llm_type
                  })
        
        assert llm is not None, "ChatModel이 None입니다"
        assert hasattr(llm, 'client'), "client 속성이 없습니다"
        assert llm._llm_type == "gemini", f"잘못된 LLM 타입: {llm._llm_type}"
        
        print("✅ Gemini ChatModel 런타임 테스트 통과")
        return True
        
    except ImportError as e:
        log_debug("runtime-test", "run1", "C", "test_runtime.py:test_gemini_chatmodel_runtime",
                  "Import 에러", {"error": str(e), "error_type": "ImportError"})
        print(f"⚠️ Import 에러 (의존성 미설치 가능): {e}")
        return False
        
    except Exception as e:
        log_debug("runtime-test", "run1", "C", "test_runtime.py:test_gemini_chatmodel_runtime",
                  "테스트 실패", {"error": str(e), "error_type": type(e).__name__})
        print(f"❌ Gemini ChatModel 런타임 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """모든 런타임 테스트 실행"""
    print("\n" + "=" * 60)
    print("런타임 테스트 시작")
    print("=" * 60 + "\n")
    
    results = []
    
    # 각 테스트 실행
    results.append(("Gemini ChatModel", test_gemini_chatmodel_runtime()))
    results.append(("ToolRegistry", test_tool_registry_runtime()))
    results.append(("ReAct Agent Graph", test_build_react_agent_graph()))
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("런타임 테스트 결과 요약")
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

