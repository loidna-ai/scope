"""
화재조사 AI 멀티 에이전트 시스템 메인 실행 파일
전체 파이프라인을 오케스트레이션합니다.
"""
import sys
import json
import argparse
import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')  # GUI 백엔드 없이 사용
import matplotlib.pyplot as plt
from pathlib import Path
from src.graph_builder import build_graph, analyze_fire_evidence
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
    
    # 이미지 파일 목록 가져오기
    image_files = sorted(Path(data_dir).glob("*.png"))
    
    if not image_files:
        print(f"오류: {data_dir} 디렉토리에 PNG 이미지 파일이 없습니다.")
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


def run_preprocessing_pipeline(input_image_path: str):
    """
    이미지 전처리 파이프라인 실행
    
    Args:
        input_image_path: 입력 이미지 경로
    
    Returns:
        전처리 결과 딕셔너리 (result, analysis_data)
    """
    print("\n" + "=" * 60)
    print("화재조사 AI 멀티 에이전트 시스템")
    print("=" * 60)
    print(f"입력 이미지: {input_image_path}")
    print("\n[1단계] 이미지 전처리 파이프라인 실행 중...")
    
    # 그래프 빌드 및 실행
    graph = build_graph()
    
    initial_state = {
        "input_image_path": input_image_path,
        "errors": []
    }
    
    result = graph.invoke(initial_state)
    
    # 에러 확인
    if result.get("errors"):
        print(f"\n경고: {len(result['errors'])}개의 오류가 발생했습니다:")
        for error in result["errors"]:
            print(f"  - {error}")
    
    # analysis_data 확인
    if not result.get("analysis_data"):
        raise ValueError("이미지 전처리 파이프라인에서 analysis_data를 생성하지 못했습니다.")
    
    analysis_data = result["analysis_data"]
    print("✓ 이미지 전처리 완료")
    
    return result, analysis_data


def save_preprocessing_results(result: dict, output_dir: Path):
    """
    전처리 결과 저장 (JSON, 이미지 시각화 등)
    
    Args:
        result: 그래프 실행 결과
        output_dir: 출력 디렉토리 경로
    """
    print(f"\n결과 저장 중... (저장 위치: {output_dir})")
    
    # JSON 데이터 저장 (Format 2만 사용)
    if result.get("analysis_data"):
        analysis_data = result["analysis_data"]
        
        # Format 2: Vertex AI Gemini 형식 (텍스트와 이미지 분리)
        gemini_format = to_gemini_vertex_ai_format(analysis_data)
        gemini_format_path = output_dir / "llm_gemini_format.json"
        with open(gemini_format_path, 'w', encoding='utf-8') as f:
            json.dump(gemini_format, f, indent=2, ensure_ascii=False)
        print(f"  ✅ Gemini 형식 저장 (Format 2): {gemini_format_path}")
        
        # 메트릭스 출력
        if result.get("metrics"):
            print(f"\n📊 형태학적 메트릭스:")
            print(f"  - Circularity (원형도): {result['metrics']['circularity']}")
            print(f"  - Solidity (고형도): {result['metrics']['solidity']}")
            print(f"  - Area (면적): {result['metrics']['area']:,} 픽셀")
    
    # 전체 파이프라인 시각화 (1x5 레이아웃)
    if (result.get("original_image") is not None and 
        result.get("cropped_image") is not None and
        result.get("enhanced_image") is not None and
        result.get("filtered_image") is not None and
        result.get("binary_mask") is not None and
        result.get("metrics") is not None):
        
        print("\n전체 파이프라인 이미지 생성 중...")
        
        # 1x5 레이아웃으로 순차 처리 구조 시각화
        fig, axes = plt.subplots(1, 5, figsize=(30, 6))
        
        # 원본 이미지
        axes[0].imshow(cv2.cvtColor(result["original_image"], cv2.COLOR_BGR2RGB))
        axes[0].set_title(
            f'1. 원본 이미지\n크기: {result["original_image"].shape[1]}x{result["original_image"].shape[0]}',
            fontsize=10, fontweight='bold'
        )
        axes[0].axis('off')
        
        # 크롭된 이미지
        axes[1].imshow(cv2.cvtColor(result["cropped_image"], cv2.COLOR_BGR2RGB))
        axes[1].set_title(
            f'2. 크롭된 이미지\n크기: {result["cropped_image"].shape[1]}x{result["cropped_image"].shape[0]}',
            fontsize=10, fontweight='bold'
        )
        axes[1].axis('off')
        
        # Enhancer 결과
        axes[2].imshow(cv2.cvtColor(result["enhanced_image"], cv2.COLOR_BGR2RGB))
        axes[2].set_title(
            f'3. Enhancer (4x 확대)\n크기: {result["enhanced_image"].shape[1]}x{result["enhanced_image"].shape[0]}',
            fontsize=10, fontweight='bold'
        )
        axes[2].axis('off')
        
        # Filter 결과
        axes[3].imshow(cv2.cvtColor(result["filtered_image"], cv2.COLOR_BGR2RGB))
        axes[3].set_title(
            f'4. Filter (CLAHE)\n크기: {result["filtered_image"].shape[1]}x{result["filtered_image"].shape[0]}',
            fontsize=10, fontweight='bold'
        )
        axes[3].axis('off')
        
        # Metrics 분석 결과 (마스크 오버레이)
        overlay = result["enhanced_image"].copy()
        overlay[result["binary_mask"] == 255] = [0, 0, 255]  # BGR에서 빨간색
        metrics_overlay = cv2.addWeighted(result["enhanced_image"], 0.7, overlay, 0.3, 0)
        
        axes[4].imshow(cv2.cvtColor(metrics_overlay, cv2.COLOR_BGR2RGB))
        metrics = result["metrics"]
        axes[4].set_title(
            f'5. Metrics 분석\nCircularity: {metrics["circularity"]}\nSolidity: {metrics["solidity"]}\nArea: {metrics["area"]:,}px',
            fontsize=10, fontweight='bold'
        )
        axes[4].axis('off')
        
        plt.tight_layout()
        pipeline_path = output_dir / "full_pipeline.png"
        plt.savefig(str(pipeline_path), dpi=150, bbox_inches='tight')
        plt.close()  # 메모리 해제
        
        print(f"  ✅ 전체 파이프라인 이미지 저장: {pipeline_path}")


def run_investigation_pipeline(analysis_data: dict, input_image_path: str, output_dir: Path):
    """
    멀티 에이전트 분석 파이프라인 실행
    
    Args:
        analysis_data: 전처리된 분석 데이터
        input_image_path: 입력 이미지 경로
        output_dir: 출력 디렉토리 경로
    """
    # Format 2 형식으로 변환 (payload 생성)
    print("\n[2단계] LLM 입력 데이터 변환 중...")
    try:
        payload_parts = to_gemini_vertex_ai_format(analysis_data)
        print(f"✓ Payload 생성 완료 ({len(payload_parts)} parts)")
    except Exception as e:
        raise Exception(f"Payload 변환 중 오류 발생: {e}")
    
    # 멀티 에이전트 분석 실행
    print("\n[3단계] 멀티 에이전트 분석 실행 중...")
    print("  - 5명의 전문가가 병렬로 분석 중...")
    print("  - 수석 조사관이 리포트를 종합 중...")
    
    try:
        investigation_result = analyze_fire_evidence(payload_parts)
        print("✓ 멀티 에이전트 분석 완료")
    except Exception as e:
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
        "--preprocess-only",
        action="store_true",
        help="이미지 전처리만 실행하고 멀티 에이전트 분석은 건너뜁니다"
    )
    
    args = parser.parse_args()
    
    # 입력 이미지 경로 확인
    if args.image_path:
        input_image_path = args.image_path
    else:
        # 명령줄 인자가 없으면 대화형 선택 모드
        print("\n이미지 파일이 지정되지 않았습니다.")
        input_image_path = select_image_file()
        
        if input_image_path is None:
            sys.exit(0)
    
    # 파일 존재 확인
    if not Path(input_image_path).exists():
        print(f"오류: 이미지 파일을 찾을 수 없습니다: {input_image_path}")
        sys.exit(1)
    
    # 출력 디렉토리 생성
    input_filename = Path(input_image_path).stem  # 확장자 제거
    output_base_dir = Path(config.OUTPUT_DIR)
    output_base_dir.mkdir(exist_ok=True)
    
    # 입력 파일명으로 폴더 생성
    output_dir = output_base_dir / input_filename
    output_dir.mkdir(exist_ok=True)
    
    try:
        # 1. 이미지 전처리 파이프라인 실행
        result, analysis_data = run_preprocessing_pipeline(input_image_path)
        
        # 2. 전처리 결과 저장
        save_preprocessing_results(result, output_dir)
        
        # 3. 멀티 에이전트 분석 실행 (옵션)
        if not args.preprocess_only:
            run_investigation_pipeline(analysis_data, input_image_path, output_dir)
        
        print(f"\n모든 결과가 {output_dir} 디렉토리에 저장되었습니다.")
        
    except Exception as e:
        print(f"\n오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
