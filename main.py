"""
화재조사 AI 멀티 에이전트 시스템 메인 실행 파일
Updated Workflow: Fan-In/Fan-Out Multi-Agent Parallel Architecture
"""
import sys
import logging
import argparse
import warnings
import time
import base64
import traceback
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

# [Optimization] Heavy imports moved to main() to ensure early logging setup
from src.utils.logging_config import setup_logger


# 구조화된 데이터 타입 (순환 참조 방지)
try:
    from src.models.verdict_models import FinalVerdictResult
except ImportError:
    FinalVerdictResult = Any  # Fallback (타입 체크용)

# torchvision 경고 억제
warnings.filterwarnings(
    'ignore', category=UserWarning, module='torchvision.transforms.functional_tensor'
)

class StreamToLogger:
    """
    stdout/stderr 포트를 로거로 리다이렉션하면서 동시에 터미널에도 직접 출력하는 클래스
    """
    def __init__(self, logger, original_stream, log_level=logging.INFO):
        self.logger = logger
        self.original_stream = original_stream
        self.log_level = log_level

    def write(self, buf):
        # 1. 터미널(원본 스트림)에 그대로 출력 (기존과 동일한 외관 유지)
        self.original_stream.write(buf)
        
        # 2. 로거를 통해 파일에 기록 (상세 정보 포함 저장)
        # 빈 줄이나 단순 개행은 제외하고 기록
        content = buf.strip()
        if content:
            self.logger.log(self.log_level, content)

    def flush(self):
        self.original_stream.flush()

# --- Logging Setup (Entry Point only) ---
if __name__ == "__main__":
    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = debug_dir / f"debug_{timestamp}.log"
    
    # Save original streams
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    logger = setup_logger(__name__, log_file=str(log_file))
    
    # Redirect stdout/stderr
    sys.stdout = StreamToLogger(logger, original_stdout, logging.INFO)
    sys.stderr = StreamToLogger(logger, original_stderr, logging.ERROR)
else:
    # Module import: use standard logger
    logger = setup_logger(__name__)

# --- Analytical Imports ---
import config
from src.agent import analyze_fire_evidence
from src.utils import find_data_directory
from src.utils.io_utils import (
    validate_image_path,
    validate_result_structure,
    select_image_file,
    create_payload_from_image,
    save_expert_reports,
    save_arbiter_report,
    save_investigation_result
)


# Regex patterns and formatting functions were moved to src.utils.report_formatter
# I/O handling functions were moved to src.utils.io_utils


async def run_analysis_pipeline(
    input_image_path: str, 
    output_dir: Path, 
    _user_query: str = ""  # 현재 미사용, 향후 확장용
) -> Optional[Dict[str, Any]]:
    """
    통합 분석 파이프라인 실행
    1. Payload 생성
    2. analyze_fire_evidence 호출 (멀티 에이전트 그래프 실행)
    3. 결과 저장
    
    Args:
        input_image_path: 분석할 이미지 파일 경로
        output_dir: 결과 저장 디렉토리
        _user_query: 사용자 질문 (현재 미사용)
        
    Returns:
        분석 결과 딕셔너리 또는 None (실패 시)
    """
    logger.info(f"화재 조사 멀티 에이전트 시스템 가동 - 분석 대상: {Path(input_image_path).name}")
    print("\n" + "=" * 60)
    print("화재 조사 멀티 에이전트 시스템 가동")
    print("=" * 60)
    print(f"분석 대상: {Path(input_image_path).name}")
    
    # 1. Payload 생성
    try:
        print("\n[1단계] 입력 데이터 처리 중...")
        payload = create_payload_from_image(input_image_path)
        logger.info(f"Payload 생성 완료 ({len(payload)} parts)")
        print(f"OK: Payload 생성 완료 ({len(payload)} parts)")
    except FileNotFoundError as e:
        logger.error(f"파일을 찾을 수 없음: {e}")
        print(f"Error: 오류: {e}")
        return None
    except PermissionError as e:
        logger.error(f"파일 읽기 권한 없음: {e}")
        print(f"Error: 오류: {e}")
        return None
    except (UnicodeDecodeError, base64.binascii.Error) as e:
        logger.error(f"데이터 인코딩/디코딩 오류: {e}", exc_info=True)
        print(f"Error: 오류: 데이터 인코딩/디코딩 오류 발생 - {e}")
        traceback.print_exc()
        return None
    except OSError as e:
        logger.error(f"파일 시스템 오류: {e}", exc_info=True)
        print(f"Error: 오류: 파일 시스템 오류 발생 - {e}")
        traceback.print_exc()
        return None
    except ValueError as e:
        logger.error(f"값 오류: {e}")
        print(f"Error: 오류: {e}")
        return None

    # 2. 분석 실행
    # 캐시 정리 (7일 이상 된 enhancement 캐시, 1일 이상 된 visual_reports 고아 파일 삭제)
    from src.nodes.enhancement_cache import clear_enhancement_cache, clear_visual_reports
    clear_enhancement_cache(max_age_days=getattr(config, "CACHE_MAX_AGE_DAYS", 7))
    clear_visual_reports(max_age_days=1)

    print("\n[2단계] 멀티 에이전트 병렬 분석 시작")
    print("  - Hotspot Detector가 관심 영역을 탐지합니다.")
    print("  - 3인의 전문가 에이전트가 병렬로 동시에 분석합니다. (Fan-Out)")
    print("    (Contact, Deform, Necking - Map-Reduce Pattern)")
    print("  - 각 전문가는 독립적인 서브그래프로 동작하며 Map-Reduce 패턴을 사용합니다.")
    print("  - 모든 분석 결과를 수집합니다. (Fan-In)")
    print("  - 수석 조사관(Arbiter)이 종합하여 최종 결론을 도출합니다.")
    
    try:
        start_time = time.time()
        result = await analyze_fire_evidence(payload, output_dir=str(output_dir))
        duration = time.time() - start_time
        logger.info(f"분석 완료 (소요 시간: {duration:.1f}초)")
        print(f"OK: 분석 완료 (소요 시간: {duration:.1f}초)")
    except Exception as e:
        logger.exception(f"분석 실행 중 예외 발생: {e}")
        print(f"Error: 오류: 분석 실행 중 예외 발생 - {e}")
        traceback.print_exc()
        # 에러 정보를 포함한 딕셔너리 반환
        error_result = {
            "final_verdict": "분석 실패",
            "expert_reports": [],
            "arbiter_debate_messages": [],
            "errors": [f"분석 실행 중 예외 발생: {str(e)}"],
            "output_file": None,
        }
        return error_result

    # 3. 결과 검증 및 처리
    is_valid, error_msg = validate_result_structure(result)
    if not is_valid:
        logger.error(f"결과 구조 검증 실패: {error_msg}")
        print(f"Error: 오류: {error_msg}")
        return None
    
    final_verdict = result.get("final_verdict", "분석 실패")
    expert_reports = result.get("expert_reports", [])
    arbiter_debate_messages = result.get("arbiter_debate_messages", [])
    errors = result.get("errors", [])
    
    # 타입 안전성 보장 (validate_result_structure에서 이미 검증했지만, 방어적 프로그래밍)
    if not isinstance(expert_reports, list):
        logger.warning("expert_reports가 리스트가 아님, 빈 리스트로 초기화")
        expert_reports = []
    if not isinstance(arbiter_debate_messages, list):
        logger.warning("arbiter_debate_messages가 리스트가 아님, 빈 리스트로 초기화")
        arbiter_debate_messages = []
    if not isinstance(errors, list):
        logger.warning("errors가 리스트가 아님, 빈 리스트로 초기화")
        errors = []
    
    if errors:
        logger.warning(f"분석 중 {len(errors)}개의 경고 발생")
        print(f"\nWarning: 분석 중 {len(errors)}개의 경고가 발생했습니다:")
        for err in errors:
            logger.debug(f"경고: {err}")
            print(f"  - {err}")

    # 콘솔 출력 (최종 결과)
    logger.info("최종 분석 결과 출력")
    print("\n" + "=" * 60)
    print("최종 분석 결과 (Final Verdict)")
    print("=" * 60)
    print(final_verdict)
    print("=" * 60)

    # 결과 파일 저장
    if not isinstance(output_dir, Path):
        output_dir = Path(output_dir)
    
    output_file = output_dir / "investigation_result.txt"
    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        final_verdict_structured = result.get("final_verdict_structured")
        
        save_investigation_result(
            final_verdict=final_verdict,
            expert_reports=expert_reports,
            arbiter_debate_messages=arbiter_debate_messages,
            errors=errors,
            input_image_path=input_image_path,
            output_file=output_file,
            final_verdict_structured=final_verdict_structured,
            visual_report_path=result.get("visual_report_path")
        )
        logger.info(f"전체 결과 저장 완료: {output_file}")
        docx_file = output_dir / "investigation_result.docx"
        if docx_file.exists():
            print(f"\nOK: 전체 결과가 저장되었습니다: {output_file}")
            print(f"   Word 문서: {docx_file}")
        else:
            print(f"\nOK: 전체 결과가 저장되었습니다: {output_file}")
        
        # 개별 리포트 저장
        save_expert_reports(expert_reports, output_dir)
        save_arbiter_report(final_verdict, output_dir)
        
    except (OSError, UnicodeEncodeError) as e:
        logger.error(f"결과 파일 저장 실패: {e}", exc_info=True)
        print(f"Error: 결과 파일 저장 실패: {e}")
        traceback.print_exc()
        return None
    
    # 성공적으로 완료된 결과 반환
    return {
        "final_verdict": final_verdict,
        "final_verdict_structured": result.get("final_verdict_structured"),  # 구조화된 데이터 포함
        "expert_reports": expert_reports,
        "arbiter_debate_messages": arbiter_debate_messages,
        "errors": errors,
        "output_file": str(output_file)
    }


def export_existing_to_docx():
    """기존 investigation_result.txt/.md를 Word(.docx)로 변환"""
    from src.utils.io_utils import save_investigation_result_docx

    output_base = Path(config.OUTPUT_DIR)
    found = 0
    for txt_path in output_base.rglob("investigation_result.txt"):
        docx_path = txt_path.with_suffix(".docx")
        base_dir = txt_path.parent
        # 이미지: 같은 폴더(visual_report_*.jpg) 우선, 없으면 visual_reports/
        raw_visual = None
        local_jpgs = list(base_dir.glob("visual_report_*.jpg"))
        if local_jpgs:
            raw_visual = str(local_jpgs[0])
        else:
            visual_dir = output_base / "visual_reports"
            if visual_dir.exists():
                jpgs = list(visual_dir.glob("*.jpg"))
                raw_visual = str(jpgs[0]) if jpgs else None
        try:
            content = txt_path.read_text(encoding="utf-8")
            save_investigation_result_docx(content, docx_path, base_dir, raw_visual)
            print(f"  OK: {docx_path.relative_to(output_base)}")
            found += 1
        except Exception as e:
            print(f"  Error: {txt_path.relative_to(output_base)}: {e}")
    for md_path in output_base.rglob("investigation_result.md"):
        docx_path = md_path.with_suffix(".docx")
        if docx_path.exists():
            continue
        base_dir = md_path.parent
        raw_visual = None
        local_jpgs = list(base_dir.glob("visual_report_*.jpg"))
        if local_jpgs:
            raw_visual = str(local_jpgs[0])
        else:
            visual_dir = output_base / "visual_reports"
            if visual_dir.exists():
                jpgs = list(visual_dir.glob("*.jpg"))
                raw_visual = str(jpgs[0]) if jpgs else None
        try:
            content = md_path.read_text(encoding="utf-8")
            save_investigation_result_docx(content, docx_path, base_dir, raw_visual)
            print(f"  OK: {docx_path.relative_to(output_base)}")
            found += 1
        except Exception as e:
            print(f"  Error: {md_path.relative_to(output_base)}: {e}")
    return found


def main():
    parser = argparse.ArgumentParser(
        description="화재조사 AI 멀티 에이전트 시스템 (Fan-In/Fan-Out Parallel Multi-Agent)"
    )
    parser.add_argument("image_path", nargs="?", help="분석할 이미지 파일 경로")
    parser.add_argument("--query", type=str, default="", help="사용자 질문 (현재 미사용)")
    parser.add_argument("--test", action="store_true", help="검증 모드로 실행")
    parser.add_argument("--export-docx", action="store_true", help="기존 txt/md 결과를 Word(.docx)로 변환")
    parser.add_argument("--clean-cache", action="store_true", help="enhancement 캐시 및 visual_reports 정리")
    
    args = parser.parse_args()

    # 0a. 캐시 정리 (--clean-cache)
    if args.clean_cache:
        from src.nodes.enhancement_cache import clear_enhancement_cache, clear_visual_reports
        clear_enhancement_cache(max_age_days=0)
        clear_visual_reports(max_age_days=0)
        print("OK: 캐시 정리 완료 (.enhancement_cache, visual_reports)")
        sys.exit(0)

    # 0b. 기존 결과 docx 변환
    if args.export_docx:
        print("\n[기존 결과 → Word 변환]")
        n = export_existing_to_docx()
        print(f"\n완료: {n}개 파일 변환됨")
        sys.exit(0)

    # 1. 검증 모드
    if args.test:
        logger.info("[검증 모드] 기본 테스트 이미지를 사용하여 파이프라인을 점검합니다.")
        print("\n[검증 모드] 기본 테스트 이미지를 사용하여 파이프라인을 점검합니다.")
        try:
            data_dir = find_data_directory()
            test_image_path = None
            
            # 우선순위 목록
            candidates = config.TEST_IMAGE_CANDIDATES
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
                logger.error("테스트용 이미지를 찾을 수 없음")
                print("Error: 오류: 테스트용 이미지를 찾을 수 없습니다.")
                sys.exit(1)
                
            input_image_path = str(test_image_path)
            logger.info(f"테스트 이미지 선택됨: {test_image_path.name}")
            print(f"테스트 이미지 선택됨: {test_image_path.name}")
            
        except (OSError, ValueError) as e:
            logger.error(f"테스트 모드 오류: {e}")
            print(f"Error: 오류: {e}")
            sys.exit(1)

    # 2. 일반 실행 모드
    elif args.image_path:
        input_image_path = args.image_path
    else:
        # 대화형 선택
        input_image_path = select_image_file()
        if input_image_path is None:
            sys.exit(0)

    # 경로 검증 (validate_image_path가 data_dir fallback 포함)
    is_valid, error_msg, resolved = validate_image_path(input_image_path)
    if not is_valid:
        logger.error(f"이미지 파일 검증 실패: {error_msg}")
        print(f"Error: 오류: {error_msg}")
        sys.exit(1)
    if resolved:
        input_image_path = resolved
        logger.info(f"알림: 이미지를 data 폴더에서 찾았습니다: {resolved}")
        print(f"알림: 이미지를 data 폴더에서 찾았습니다: {resolved}")
    image_path = Path(input_image_path)

    # 출력 디렉토리 준비
    input_filename = image_path.stem
    output_base_dir = Path(config.OUTPUT_DIR)
    output_dir = output_base_dir / input_filename
    output_dir.mkdir(parents=True, exist_ok=True)

    # 파이프라인 실행
    asyncio.run(run_analysis_pipeline(input_image_path, output_dir, args.query))


if __name__ == "__main__":
    main()
