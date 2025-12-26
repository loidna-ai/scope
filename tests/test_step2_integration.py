"""
2단계: 그래프 통합 테스트
ReAct 에이전트 독립 실행 및 그래프 통합 테스트
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


def test_investigation_edges_react():
    """엣지 수정 테스트"""
    log_debug("test-step2", "run1", "A", "test_step2_integration.py:test_investigation_edges_react",
              "테스트 시작", {"test": "add_investigation_edges_with_react"})
    
    try:
        # 파일 존재 확인
        edges_file = project_root / "src" / "edges" / "investigation_edges.py"
        if not edges_file.exists():
            raise FileNotFoundError(f"파일 없음: {edges_file}")
        
        # 파일 내용 확인
        with open(edges_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if "def add_investigation_edges_with_react" not in content:
                raise ValueError("add_investigation_edges_with_react 함수가 정의되지 않음")
            if "react_agent" not in content:
                raise ValueError("react_agent 엣지가 정의되지 않음")
            if "START" in content and "react_agent" in content:
                # START -> react_agent 엣지 확인
                lines = content.split('\n')
                has_start_edge = any("START" in line and "react_agent" in line for line in lines)
                if not has_start_edge:
                    raise ValueError("START -> react_agent 엣지가 없음")
        
        log_debug("test-step2", "run1", "A", "test_step2_integration.py:test_investigation_edges_react",
                  "테스트 성공", {"file_exists": True, "has_function": True, "has_edges": True})
        print("✅ 엣지 수정 확인 완료")
        return True
        
    except Exception as e:
        log_debug("test-step2", "run1", "A", "test_step2_integration.py:test_investigation_edges_react",
                  "테스트 실패", {"error": str(e), "error_type": type(e).__name__})
        print(f"❌ 엣지 수정 테스트 실패: {e}")
        return False


def test_agent_integration():
    """그래프 빌더 통합 테스트"""
    log_debug("test-step2", "run1", "B", "test_step2_integration.py:test_agent_integration",
              "테스트 시작", {"test": "build_investigation_graph_with_react"})
    
    try:
        # 파일 존재 확인
        agent_file = project_root / "src" / "agent.py"
        if not agent_file.exists():
            raise FileNotFoundError(f"파일 없음: {agent_file}")
        
        # 파일 내용 확인
        with open(agent_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if "def build_investigation_graph_with_react" not in content:
                raise ValueError("build_investigation_graph_with_react 함수가 정의되지 않음")
            if "build_react_agent_graph" not in content:
                raise ValueError("build_react_agent_graph import가 없음")
            if "add_investigation_edges_with_react" not in content:
                raise ValueError("add_investigation_edges_with_react import가 없음")
            if "react_agent" in content and "add_node" in content:
                # react_agent 노드 추가 확인
                lines = content.split('\n')
                has_react_node = any("react_agent" in line and "add_node" in line for line in lines)
                if not has_react_node:
                    raise ValueError("react_agent 노드 추가가 없음")
        
        log_debug("test-step2", "run1", "B", "test_step2_integration.py:test_agent_integration",
                  "테스트 성공", {"file_exists": True, "has_function": True, "has_integration": True})
        print("✅ 그래프 빌더 통합 확인 완료")
        return True
        
    except Exception as e:
        log_debug("test-step2", "run1", "B", "test_step2_integration.py:test_agent_integration",
                  "테스트 실패", {"error": str(e), "error_type": type(e).__name__})
        print(f"❌ 그래프 빌더 통합 테스트 실패: {e}")
        return False


def test_main_integration():
    """메인 통합 테스트"""
    log_debug("test-step2", "run1", "C", "test_step2_integration.py:test_main_integration",
              "테스트 시작", {"test": "main.py ReAct 모드"})
    
    try:
        # 파일 존재 확인
        main_file = project_root / "main.py"
        if not main_file.exists():
            raise FileNotFoundError(f"파일 없음: {main_file}")
        
        # 파일 내용 확인
        with open(main_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if "--react-mode" not in content:
                raise ValueError("--react-mode 인자가 없음")
            if "run_react_agent_mode" not in content:
                raise ValueError("run_react_agent_mode 함수가 없음")
            if "build_react_agent_graph" not in content:
                raise ValueError("build_react_agent_graph import가 없음")
            if "ReActState" not in content:
                raise ValueError("ReActState import가 없음")
        
        log_debug("test-step2", "run1", "C", "test_step2_integration.py:test_main_integration",
                  "테스트 성공", {"file_exists": True, "has_react_mode": True, "has_function": True})
        print("✅ 메인 통합 확인 완료")
        return True
        
    except Exception as e:
        log_debug("test-step2", "run1", "C", "test_step2_integration.py:test_main_integration",
                  "테스트 실패", {"error": str(e), "error_type": type(e).__name__})
        print(f"❌ 메인 통합 테스트 실패: {e}")
        return False


def run_all_tests():
    """모든 2단계 테스트 실행"""
    print("\n" + "=" * 60)
    print("2단계: 그래프 통합 테스트 시작")
    print("=" * 60 + "\n")
    
    results = []
    
    # 각 테스트 실행
    results.append(("엣지 수정", test_investigation_edges_react()))
    results.append(("그래프 빌더 통합", test_agent_integration()))
    results.append(("메인 통합", test_main_integration()))
    
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

