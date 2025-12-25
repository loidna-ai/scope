"""
화재조사 AI 멀티 에이전트 시스템 메인 실행 파일
전체 파이프라인을 오케스트레이션합니다.
"""
import sys
import json
import argparse
import warnings
# torchvision 경고 메시지 억제 (basicsr/realesrgan에서 사용)
warnings.filterwarnings('ignore', category=UserWarning, module='torchvision.transforms.functional_tensor')
from pathlib import Path
from src.agent import build_investigation_graph_with_react, analyze_fire_evidence
from src.utils import find_data_directory
from src.nodes.packaging import to_gemini_vertex_ai_format
import config


def select_image_file():
    """
    data 디렉토리에서 이미지 파일 목록을 보여주고 사용자가 선택할 수 있게 합니다.
    
    Returns:
        선택된 이미지 파일 경로
    """
    try:
        # data 디렉토리 찾기
        data_dir = find_data_directory()
    except ValueError as e:
        print(f"오류: {e}")
        return None
    
    # 이미지 파일 목록 가져오기 (여러 형식 지원)
    image_extensions = ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG", "*.heic", "*.HEIC"]
    image_files = []
    for ext in image_extensions:
        image_files.extend(Path(data_dir).glob(ext))
    
    # 중복 제거 및 정렬
    image_files = sorted(set(image_files))
    
    if not image_files:
        print(f"오류: {data_dir} 디렉토리에 이미지 파일이 없습니다.")
        return None
    
    # 이미지 파일 목록 출력
    print("\n" + "=" * 60)
    print("사용 가능한 이미지 파일:")
    print("=" * 60)
    for idx, img_file in enumerate(image_files, 1):
        file_size = img_file.stat().st_size / 1024  # KB
        print(f"  [{idx}] {img_file.name} ({file_size:.1f} KB)")
    print("=" * 60)
    
    # 사용자 입력 받기
    while True:
        try:
            choice = input(f"\n이미지 번호를 선택하세요 (1-{len(image_files)}): ").strip()
            
            if choice.lower() == 'q' or choice.lower() == 'quit':
                print("실행을 취소했습니다.")
                return None
            
            choice_num = int(choice)
            
            if 1 <= choice_num <= len(image_files):
                selected_file = image_files[choice_num - 1]
                print(f"\n선택된 이미지: {selected_file.name}")
                return str(selected_file)
            else:
                print(f"오류: 1부터 {len(image_files)} 사이의 숫자를 입력해주세요.")
        except ValueError:
            print("오류: 숫자를 입력해주세요. (종료하려면 'q' 입력)")
        except KeyboardInterrupt:
            print("\n\n실행을 취소했습니다.")
            return None


def run_investigation_pipeline(analysis_data: dict, input_image_path: str, output_dir: Path, payload_parts: list = None):
    """
    멀티 에이전트 분석 파이프라인 실행
    
    Args:
        analysis_data: 전처리된 분석 데이터
        input_image_path: 입력 이미지 경로
        output_dir: 출력 디렉토리 경로
        payload_parts: 이미 변환된 payload (선택사항, 있으면 재사용)
    """
    # #region agent log
    import json
    import time
    import sys
    try:
        with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"workflow-debug","runId":"run1","hypothesisId":"A","location":"main.py:run_investigation_pipeline","message":"Investigation pipeline start","data":{"analysis_data_keys":list(analysis_data.keys()) if analysis_data else None,"has_images":bool(analysis_data.get("images")) if analysis_data else False,"has_payload_parts":payload_parts is not None},"timestamp":int(time.time()*1000)})+'\n')
    except: pass
    # #endregion
    # Format 2 형식으로 변환 (payload 생성) - 이미 있으면 재사용
    if payload_parts is None:
        print("\n[2단계] LLM 입력 데이터 변환 중...")
        try:
            # #region agent log
            try:
                import psutil
                mem_before = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            except:
                mem_before = None
            # #endregion
            payload_parts = to_gemini_vertex_ai_format(analysis_data)
            # #region agent log
            try:
                mem_after = psutil.Process().memory_info().rss / 1024 / 1024 if 'psutil' in sys.modules else None
                with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"workflow-debug","runId":"run1","hypothesisId":"C","location":"main.py:run_investigation_pipeline","message":"Payload conversion complete","data":{"payload_parts_count":len(payload_parts),"mem_before_mb":mem_before,"mem_after_mb":mem_after,"mem_diff_mb":mem_after-mem_before if mem_before and mem_after else None,"payload_types":[type(p).__name__ for p in payload_parts]},"timestamp":int(time.time()*1000)})+'\n')
            except: pass
            # #endregion
            print(f"✓ Payload 생성 완료 ({len(payload_parts)} parts)")
        except Exception as e:
            # #region agent log
            try:
                with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"workflow-debug","runId":"run1","hypothesisId":"B","location":"main.py:run_investigation_pipeline","message":"Payload conversion error","data":{"error":str(e),"error_type":type(e).__name__},"timestamp":int(time.time()*1000)})+'\n')
            except: pass
            # #endregion
            raise Exception(f"Payload 변환 중 오류 발생: {e}")
    else:
        print("\n[3단계] 멀티 에이전트 분석 실행 중... (이미 변환된 payload 재사용)")
    
    # 멀티 에이전트 분석 실행
    if payload_parts is None:
        print("\n[3단계] 멀티 에이전트 분석 실행 중...")
    print("  - 5명의 전문가가 병렬로 분석 중...")
    print("  - 수석 조사관이 리포트를 종합 중...")
    
    try:
        # #region agent log
        try:
            mem_before_inv = psutil.Process().memory_info().rss / 1024 / 1024 if 'psutil' in sys.modules else None
        except:
            mem_before_inv = None
        # #endregion
        investigation_result = analyze_fire_evidence(payload_parts)
        # #region agent log
        try:
            mem_after_inv = psutil.Process().memory_info().rss / 1024 / 1024 if 'psutil' in sys.modules else None
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"workflow-debug","runId":"run1","hypothesisId":"E","location":"main.py:run_investigation_pipeline","message":"Investigation complete","data":{"has_final_verdict":bool(investigation_result.get("final_verdict")),"expert_reports_count":len(investigation_result.get("expert_reports",[])),"errors_count":len(investigation_result.get("errors",[])),"mem_before_mb":mem_before_inv,"mem_after_mb":mem_after_inv,"mem_diff_mb":mem_after_inv-mem_before_inv if mem_before_inv and mem_after_inv else None},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        print("✓ 멀티 에이전트 분석 완료")
    except Exception as e:
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"workflow-debug","runId":"run1","hypothesisId":"D","location":"main.py:run_investigation_pipeline","message":"Investigation error","data":{"error":str(e),"error_type":type(e).__name__},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        raise Exception(f"멀티 에이전트 분석 중 오류 발생: {e}")
    
    # 에러 확인
    if investigation_result.get("errors"):
        print(f"\n경고: {len(investigation_result['errors'])}개의 오류가 발생했습니다:")
        for error in investigation_result["errors"]:
            print(f"  - {error}")
    
    # 전문가 리포트 출력
    expert_reports = investigation_result.get("expert_reports", [])
    if expert_reports:
        print("\n" + "=" * 60)
        print("전문가 리포트")
        print("=" * 60)
        for i, report in enumerate(expert_reports, 1):
            print(f"\n[전문가 {i}]")
            print(report)
            print("-" * 60)
    
    # 최종 분석 결과 출력
    final_verdict = investigation_result.get("final_verdict", "분석 실패")
    print("\n" + "=" * 60)
    print("최종 분석 결과")
    print("=" * 60)
    print(final_verdict)
    print("=" * 60)
    
    # 결과를 파일로 저장 (전문가 리포트 + 최종 리포트 취합)
    output_file = output_dir / "investigation_result.txt"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("화재조사 AI 멀티 에이전트 시스템 분석 결과\n")
            f.write("=" * 60 + "\n")
            f.write(f"입력 이미지: {input_image_path}\n")
            f.write("=" * 60 + "\n\n")
            
            # 전문가 리포트 저장
            if expert_reports:
                f.write("=" * 60 + "\n")
                f.write("전문가 리포트\n")
                f.write("=" * 60 + "\n\n")
                for i, report in enumerate(expert_reports, 1):
                    f.write(f"[전문가 {i}]\n")
                    f.write(report)
                    f.write("\n" + "-" * 60 + "\n\n")
            
            # 최종 분석 결과 저장
            f.write("=" * 60 + "\n")
            f.write("최종 분석 결과\n")
            f.write("=" * 60 + "\n\n")
            f.write(final_verdict)
            f.write("\n")
            
            # 에러 정보 저장 (있는 경우)
            if investigation_result.get("errors"):
                f.write("\n" + "=" * 60 + "\n")
                f.write("오류 정보\n")
                f.write("=" * 60 + "\n")
                for error in investigation_result["errors"]:
                    f.write(f"- {error}\n")
        
        print(f"  ✅ 조사 결과 저장: {output_file}")
    except Exception as e:
        print(f"\n경고: 결과 파일 저장 실패: {e}")


def create_payload_from_image(image_path: str) -> list:
    """
    이미지 경로에서 직접 payload 생성 (전처리 없이)
    
    Args:
        image_path: 이미지 파일 경로
    
    Returns:
        Gemini Vertex AI 형식 payload 리스트
    """
    import base64
    from pathlib import Path
    
    # 이미지 파일 읽기
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    # MIME 타입 결정
    ext = Path(image_path).suffix.lower()
    if ext == '.png':
        mime_type = 'image/png'
    elif ext in ['.jpg', '.jpeg']:
        mime_type = 'image/jpeg'
    else:
        mime_type = 'image/jpeg'  # 기본값
    
    # Base64 인코딩
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    # Gemini Vertex AI 형식으로 변환
    payload = [
        {
            "text": "이미지를 분석하고 화재 원인을 조사하세요."
        },
        {
            "inline_data": {
                "mime_type": mime_type,
                "data": image_base64
            }
        }
    ]
    
    return payload


def run_react_agent_parallel_mode(
    input_image_path: str,
    output_dir: Path,
    user_query: str = "",
    payload_parts: list = None
):
    """
    병렬 모드 실행 (5명 전문가 병렬 실행)
    
    Args:
        input_image_path: 입력 이미지 경로
        output_dir: 출력 디렉토리 경로
        user_query: 사용자 질문 (선택적, 현재 미사용)
        payload_parts: 이미 변환된 payload (선택적)
    """
    print("\n" + "=" * 60)
    print("병렬 멀티 에이전트 모드 실행")
    print("=" * 60)
    print("  - 5명의 전문가가 병렬로 분석 중...")
    print("  - 수석 조사관이 리포트를 종합 중...")
    
    # Payload 생성 - 이미 있으면 재사용
    if payload_parts is None:
        print("\n[1단계] LLM 입력 데이터 생성 중...")
        try:
            payload_parts = create_payload_from_image(input_image_path)
            print(f"✓ Payload 생성 완료 ({len(payload_parts)} parts)")
        except Exception as e:
            raise Exception(f"Payload 생성 중 오류 발생: {e}")
    
    try:
        # #region agent log
        import json
        import time
        import sys
        try:
            import psutil
            mem_before = psutil.Process().memory_info().rss / 1024 / 1024
        except ImportError:
            mem_before = None
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-parallel","runId":"run1","hypothesisId":"A","location":"main.py:run_react_agent_parallel_mode","message":"병렬 그래프 빌드 시작","data":{"payload_parts_count":len(payload_parts) if payload_parts else 0},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # ReAct 에이전트를 포함한 병렬 그래프 빌드
        graph = build_investigation_graph_with_react()
        
        initial_state = {
            "payload": payload_parts,
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {},
            "final_verdict": None,
            "errors": [],
            # 각 서브그래프별 독립 캐시 초기화
            "contact_cached_image_data": None,
            "dielectric_cached_image_data": None,
            "mechanical_cached_image_data": None,
            "tracking_cached_image_data": None,
            "strand_fracture_cached_image_data": None
        }
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-parallel","runId":"run1","hypothesisId":"D","location":"main.py:run_react_agent_parallel_mode","message":"initial_state 생성","data":{"image_path":input_image_path,"payload_parts_count":len(payload_parts) if payload_parts else 0},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-parallel","runId":"run1","hypothesisId":"A","location":"main.py:run_react_agent_parallel_mode","message":"그래프 실행 시작","data":{},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        invoke_start_time = time.time()
        result = graph.invoke(initial_state)
        invoke_duration_ms = (time.time() - invoke_start_time) * 1000
        
        # #region agent log
        try:
            try:
                import psutil
                mem_after = psutil.Process().memory_info().rss / 1024 / 1024
            except ImportError:
                mem_after = None
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-parallel","runId":"run1","hypothesisId":"A","location":"main.py:run_react_agent_parallel_mode","message":"그래프 실행 완료","data":{"duration_ms":invoke_duration_ms,"expert_reports_count":len(result.get("expert_reports",[])),"errors_count":len(result.get("errors",[])),"has_final_verdict":bool(result.get("final_verdict")),"mem_before_mb":mem_before,"mem_after_mb":mem_after,"mem_diff_mb":mem_after-mem_before if mem_before and mem_after else None},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        print("✓ 병렬 멀티 에이전트 분석 완료")
        
    except Exception as e:
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-parallel","runId":"run1","hypothesisId":"ERROR","location":"main.py:run_react_agent_parallel_mode","message":"그래프 실행 오류","data":{"error":str(e),"error_type":type(e).__name__},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        raise Exception(f"병렬 멀티 에이전트 분석 중 오류 발생: {e}")
    
    # 에러 확인
    if result.get("errors"):
        print(f"\n경고: {len(result['errors'])}개의 오류가 발생했습니다:")
        for error in result["errors"]:
            print(f"  - {error}")
    
    # 전문가 리포트 출력
    expert_reports = result.get("expert_reports", [])
    if expert_reports:
        print("\n" + "=" * 60)
        print("전문가 리포트 (5명 전문가)")
        print("=" * 60)
        for i, report in enumerate(expert_reports, 1):
            print(f"\n[전문가 {i}]")
            print(report)
            print("-" * 60)
    
    # 최종 분석 결과 출력
    final_verdict = result.get("final_verdict", "분석 실패")
    print("\n" + "=" * 60)
    print("최종 분석 결과")
    print("=" * 60)
    print(final_verdict)
    print("=" * 60)
    
    # 결과를 파일로 저장
    output_file = output_dir / "react_parallel_result.txt"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("화재조사 AI 멀티 에이전트 시스템 분석 결과 (병렬 모드)\n")
            f.write("=" * 60 + "\n")
            f.write(f"입력 이미지: {input_image_path}\n")
            if user_query:
                f.write(f"사용자 질문: {user_query}\n")
            f.write("=" * 60 + "\n\n")
            
            # 전문가 리포트 저장
            if expert_reports:
                f.write("=" * 60 + "\n")
                f.write("전문가 리포트 (5명 전문가)\n")
                f.write("=" * 60 + "\n\n")
                for i, report in enumerate(expert_reports, 1):
                    f.write(f"[전문가 {i}]\n")
                    f.write(report)
                    f.write("\n" + "-" * 60 + "\n\n")
            
            # 최종 분석 결과 저장
            f.write("=" * 60 + "\n")
            f.write("최종 분석 결과\n")
            f.write("=" * 60 + "\n\n")
            f.write(final_verdict)
            f.write("\n")
            
            # 에러 정보 저장 (있는 경우)
            if result.get("errors"):
                f.write("\n" + "=" * 60 + "\n")
                f.write("오류 정보\n")
                f.write("=" * 60 + "\n")
                for error in result["errors"]:
                    f.write(f"- {error}\n")
        
        print(f"  ✅ 병렬 분석 결과 저장: {output_file}")
    except Exception as e:
        print(f"\n경고: 결과 파일 저장 실패: {e}")


def main():
    """메인 함수"""
    # argparse 설정
    parser = argparse.ArgumentParser(
        description="화재조사 AI 멀티 에이전트 시스템 - 전기적 특이점(단락흔) 분석"
    )
    parser.add_argument(
        "image_path",
        nargs="?",
        help="분석할 이미지 파일 경로 (지정하지 않으면 대화형 선택 모드)"
    )
    parser.add_argument(
        "--query",
        type=str,
        default="",
        help="사용자 질문 (예: '이미지를 분석하세요', 현재 미사용)"
    )
    
    args = parser.parse_args()
    
    # #region agent log
    import json
    import time
    try:
        with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"A","location":"main.py:main","message":"main 함수 시작","data":{"has_query":bool(args.query)},"timestamp":int(time.time()*1000)})+'\n')
    except: pass
    # #endregion
    
    # 입력 이미지 경로 확인
    if args.image_path:
        input_image_path = args.image_path
    else:
        # 명령줄 인자가 없으면 대화형 선택 모드
        print("\n이미지 파일이 지정되지 않았습니다.")
        input_image_path = select_image_file()
        
        if input_image_path is None:
            sys.exit(0)
    
    # 파일 존재 확인 및 경로 정규화
    image_path = Path(input_image_path)
    
    # 상대 경로인 경우 data 디렉토리에서 찾기 시도
    if not image_path.exists():
        # data 디렉토리에서 찾기 시도
        try:
            data_dir = find_data_directory()
            possible_path = Path(data_dir) / image_path.name
            if possible_path.exists():
                image_path = possible_path
                input_image_path = str(image_path)
        except ValueError:
            pass
    
    if not image_path.exists():
        print(f"오류: 이미지 파일을 찾을 수 없습니다: {input_image_path}")
        print(f"시도한 경로: {image_path.absolute()}")
        sys.exit(1)
    
    # 출력 디렉토리 생성
    input_filename = Path(input_image_path).stem  # 확장자 제거
    output_base_dir = Path(config.OUTPUT_DIR)
    output_base_dir.mkdir(exist_ok=True)
    
    # 입력 파일명으로 폴더 생성
    output_dir = output_base_dir / input_filename
    output_dir.mkdir(exist_ok=True)
    
    try:
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"A","location":"main.py:main","message":"멀티 에이전트 분석 시작","data":{"input_image_path":input_image_path},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        # 멀티 에이전트 분석 실행
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"A","location":"main.py:main","message":"병렬 모드 실행 시작","data":{"input_image_path":input_image_path,"query":args.query},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        run_react_agent_parallel_mode(input_image_path, output_dir, args.query)
        
        print(f"\n모든 결과가 {output_dir} 디렉토리에 저장되었습니다.")
        
    except Exception as e:
        # #region agent log
        try:
            with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
                import traceback
                tb_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                f.write(json.dumps({"sessionId":"react-execution","runId":"run1","hypothesisId":"ERROR","location":"main.py:main","message":"main 함수 예외 발생","data":{"error":str(e),"error_type":type(e).__name__,"traceback":tb_str[:500]},"timestamp":int(time.time()*1000)})+'\n')
        except: pass
        # #endregion
        
        print(f"\n오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
