"""
화재조사 AI 멀티 에이전트 시스템 메인 실행 파일
Updated Workflow: Sequential Multi-Agent ReAct Architecture
"""
import sys
import json
import argparse
import warnings
import time
from pathlib import Path
import config

# torchvision 경고 억제
warnings.filterwarnings('ignore', category=UserWarning, module='torchvision.transforms.functional_tensor')

# 핵심 분석 함수 임포트
from src.agent import analyze_fire_evidence
from src.utils import find_data_directory

def select_image_file():
    """
    data 디렉토리에서 이미지 파일 목록을 보여주고 사용자가 선택할 수 있게 합니다.
    """
    try:
        data_dir = find_data_directory()
    except ValueError as e:
        print(f"오류: {e}")
        return None
    
    image_extensions = ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG", "*.heic", "*.HEIC"]
    image_files = []
    for ext in image_extensions:
        image_files.extend(Path(data_dir).glob(ext))
    
    image_files = sorted(set(image_files))
    
    if not image_files:
        print(f"오류: {data_dir} 디렉토리에 이미지 파일이 없습니다.")
        return None
    
    print("\n" + "=" * 60)
    print("사용 가능한 이미지 파일:")
    print("=" * 60)
    for idx, img_file in enumerate(image_files, 1):
        file_size = img_file.stat().st_size / 1024  # KB
        print(f"  [{idx}] {img_file.name} ({file_size:.1f} KB)")
    print("=" * 60)
    
    while True:
        try:
            choice = input(f"\n이미지 번호를 선택하세요 (1-{len(image_files)}): ").strip()
            
            if choice.lower() in ['q', 'quit']:
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

def create_payload_from_image(image_path: str) -> list:
    """
    이미지 경로에서 직접 Gemini Vertex AI 형식의 payload 생성
    """
    import base64
    
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        ext = Path(image_path).suffix.lower()
        mime_type = 'image/png' if ext == '.png' else 'image/jpeg'
        
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        payload = [
            {
                "text": "이미지를 분석하고 화재 원인을 조사하세요. (분석 단계별 지침을 따르세요)"
            },
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": image_base64
                }
            }
        ]
        return payload
    except Exception as e:
        raise

def run_analysis_pipeline(input_image_path: str, output_dir: Path, user_query: str = ""):
    """
    통합 분석 파이프라인 실행
    1. Payload 생성
    2. analyze_fire_evidence 호출 (멀티 에이전트 그래프 실행)
    3. 결과 저장
    """
    print("\n" + "=" * 60)
    print("화재 조사 멀티 에이전트 시스템 가동")
    print("=" * 60)
    print(f"분석 대상: {Path(input_image_path).name}")
    
    # 1. Payload 생성
    try:
        print("\n[1단계] 입력 데이터 처리 중...")
        payload = create_payload_from_image(input_image_path)
        print(f"✓ Payload 생성 완료 ({len(payload)} parts)")
    except Exception as e:
        print(f"❌ 오류: Payload 생성 실패 - {e}")
        import traceback
        traceback.print_exc()
        return

    # 2. 분석 실행
    print("\n[2단계] 멀티 에이전트 협업 분석 시작")
    print("  - 5인의 전문가 에이전트가 각자의 영역을 분석합니다.")
    print("    (Contact, Dielectric, Mechanical, StrandFracture, Tracking)")
    print("  - 각 에이전트는 ReAct 패턴을 사용하여 도구를 능동적으로 활용합니다.")
    print("  - 수석 조사관(Arbiter)이 모든 분석을 종합하여 최종 결론을 내립니다.")
    
    try:
        # 핵심 로직 호출
        start_time = time.time()
        result = analyze_fire_evidence(payload)
        duration = time.time() - start_time
        
        print(f"✓ 분석 완료 (소요 시간: {duration:.1f}초)")
        
    except Exception as e:
        print(f"❌ 오류: 분석 실행 중 예외 발생 - {e}")
        import traceback
        traceback.print_exc()
        return

    # 3. 결과 처리
    final_verdict = result.get("final_verdict", "분석 실패")
    expert_reports = result.get("expert_reports", [])
    errors = result.get("errors", [])
    
    if errors:
        print(f"\n⚠️ 분석 중 {len(errors)}개의 경고가 발생했습니다:")
        for err in errors:
            print(f"  - {err}")

    # 콘솔 출력 (최종 결과)
    print("\n" + "=" * 60)
    print("최종 분석 결과 (Final Verdict)")
    print("=" * 60)
    print(final_verdict)
    print("=" * 60)

    # 결과 파일 저장
    output_file = output_dir / "investigation_result.txt"
    try:
        # 1. 통합 결과 파일 저장
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("화재조사 AI 멀티 에이전트 시스템 분석 결과\n")
            f.write(f"일시: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n")
            f.write(f"입력 이미지: {input_image_path}\n")
            if user_query:
                f.write(f"사용자 질문: {user_query}\n")
            f.write("=" * 60 + "\n\n")
            
            # 최종 결론
            f.write("[최종 분석 결론]\n")
            f.write(final_verdict)
            f.write("\n\n" + "-" * 60 + "\n\n")
            
            # 전문가 리포트 (통합 파일에도 포함)
            if expert_reports:
                f.write("[전문가 상세 리포트]\n")
                for i, report in enumerate(expert_reports, 1):
                    f.write(f"\n--- Expert Report {i} ---\n")
                    f.write(report)
                    f.write("\n")
            
            # 오류 로그
            if errors:
                f.write("\n" + "=" * 60 + "\n")
                f.write("[System Errors & Warnings]\n")
                for err in errors:
                    f.write(f"- {err}\n")

        print(f"\n✅ 전체 결과가 저장되었습니다: {output_file}")

        # 2. 각 전문가별 별도 리포트 파일 저장
        if expert_reports:
            print("\n[개별 리포트 저장]")
            for report in expert_reports:
                # 리포트 헤더에서 전문가 이름 추출
                filename = "Unknown_Expert_Report.txt"
                if "[Contact 전문가 리포트]" in report:
                    filename = "Contact_Expert_Report.txt"
                elif "[DielectricAge 전문가 리포트]" in report:
                    filename = "Dielectric_Expert_Report.txt"
                elif "[Mechanical 전문가 리포트]" in report:
                    filename = "Mechanical_Expert_Report.txt"
                elif "[StrandFracture 전문가 리포트]" in report:
                    filename = "StrandFracture_Expert_Report.txt"
                elif "[Tracking 전문가 리포트]" in report:
                    filename = "Tracking_Expert_Report.txt"
                
                expert_file = output_dir / filename
                with open(expert_file, 'w', encoding='utf-8') as f:
                    f.write(report)
                print(f"  - {filename} 저장 완료")
        
        # 3. Arbiter(최종 결론) 리포트 별도 저장
        if final_verdict:
            arbiter_file = output_dir / "Arbiter_Report.txt"
            with open(arbiter_file, 'w', encoding='utf-8') as f:
                f.write("[Arbiter (Chief Investigator) Report]\n\n")
                f.write(final_verdict)
            print(f"  - Arbiter_Report.txt 저장 완료")
        
    except Exception as e:
        print(f"❌ 결과 파일 저장 실패: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="화재조사 AI 멀티 에이전트 시스템 (Sequential Multi-Agent ReAct)"
    )
    parser.add_argument("image_path", nargs="?", help="분석할 이미지 파일 경로")
    parser.add_argument("--query", type=str, default="", help="사용자 질문 (현재 미사용)")
    parser.add_argument("--test", action="store_true", help="검증 모드로 실행")
    
    args = parser.parse_args()
    

    # 1. 검증 모드
    if args.test:
        print("\n[검증 모드] 기본 테스트 이미지를 사용하여 파이프라인을 점검합니다.")
        try:
            data_dir = find_data_directory()
            test_image_path = None
            
            # 우선순위 목록
            candidates = ["Primary_Arc_Bead_1.png", "Primary_Arc_Bead_1.jpg"]
            for name in candidates:
                p = Path(data_dir) / name
                if p.exists():
                    test_image_path = p
                    break
            
            # 없으면 아무 이미지나
            if test_image_path is None:
                for ext in ["*.png", "*.jpg", "*.jpeg"]:
                    found = list(Path(data_dir).glob(ext))
                    if found:
                        test_image_path = found[0]
                        break
            
            if test_image_path is None:
                print("❌ 오류: 테스트용 이미지를 찾을 수 없습니다.")
                sys.exit(1)
                
            input_image_path = str(test_image_path)
            print(f"테스트 이미지 선택됨: {test_image_path.name}")
            
        except Exception as e:
            print(f"❌ 오류: {e}")
            sys.exit(1)

    # 2. 일반 실행 모드
    elif args.image_path:
        input_image_path = args.image_path
    else:
        # 대화형 선택
        input_image_path = select_image_file()
        if input_image_path is None:
            sys.exit(0)

    # 경로 검증
    image_path = Path(input_image_path)
    if not image_path.exists():
        # 혹시 data 폴더 안에 있는지 확인
        try:
            data_dir = find_data_directory()
            alt_path = Path(data_dir) / image_path.name
            if alt_path.exists():
                image_path = alt_path
                input_image_path = str(image_path)
                print(f"알림: 이미지를 data 폴더에서 찾았습니다: {image_path}")
            else:
                print(f"❌ 오류: 이미지 파일을 찾을 수 없습니다: {input_image_path}")
                sys.exit(1)
        except:
            print(f"❌ 오류: 이미지 파일을 찾을 수 없습니다: {input_image_path}")
            sys.exit(1)

    # 출력 디렉토리 준비
    input_filename = image_path.stem
    output_base_dir = Path(config.OUTPUT_DIR)
    output_dir = output_base_dir / input_filename
    output_dir.mkdir(parents=True, exist_ok=True)

    # 파이프라인 실행
    run_analysis_pipeline(input_image_path, output_dir, args.query)

if __name__ == "__main__":
    main()
