"""
화재조사 AI 멀티 에이전트 시스템 메인 실행 파일
Updated Workflow: Fan-In/Fan-Out Multi-Agent Parallel Architecture
"""
import sys
import json
import argparse
import warnings
import time
import re
from pathlib import Path
import config

# torchvision 경고 억제
warnings.filterwarnings('ignore', category=UserWarning, module='torchvision.transforms.functional_tensor')

# 핵심 분석 함수 임포트
from src.agent import analyze_fire_evidence
from src.utils import find_data_directory

def parse_final_verdict(verdict_text: str) -> dict:
    """최종 판정 텍스트에서 판정 결과와 신뢰도를 추출"""
    result = {
        "verdict": "판정 불가",
        "confidence": "N/A",
        "confidence_level": "N/A"
    }
    
    # 최종 판정 추출 - 여러 패턴 시도
    verdict_match = re.search(r'\*\*최종 판정\*\*\s*\n\s*\*\*([^*]+)\*\*', verdict_text)
    if not verdict_match:
        verdict_match = re.search(r'\*\*최종 판정\*\*\s*\n\s*([^\n]+)', verdict_text)
    if not verdict_match:
        verdict_match = re.search(r'최종 판정[:\s]*([^\n]+)', verdict_text)
    if not verdict_match:
        # "접촉불량(Poor Contact) 유력" 같은 패턴
        verdict_match = re.search(r'([가-힣]+\([^)]+\)\s*[가-힣]+)', verdict_text)
    if verdict_match:
        result["verdict"] = verdict_match.group(1).strip()
    
    # 신뢰도 추출 (예: 85.0%, 85%, High 등)
    # 전문가 리포트에서 신뢰도 찾기
    confidence_match = re.search(r'(\d+\.?\d*)%', verdict_text)
    if confidence_match:
        conf_value = float(confidence_match.group(1))
        result["confidence"] = f"{conf_value:.1f}%"
        if conf_value >= 80:
            result["confidence_level"] = "High"
        elif conf_value >= 60:
            result["confidence_level"] = "Medium"
        else:
            result["confidence_level"] = "Low"
    else:
        # High/Medium/Low 텍스트 추출
        level_match = re.search(r'(High|Medium|Low)', verdict_text, re.IGNORECASE)
        if level_match:
            result["confidence_level"] = level_match.group(1)
            result["confidence"] = "N/A"
    
    return result

def parse_expert_report(report_text: str) -> dict:
    """전문가 리포트에서 판정 결과 추출"""
    result = {
        "expert_name": "Unknown",
        "conclusion": "해당 없음",
        "confidence": "N/A",
        "key_evidence": "해당 없음"
    }
    
    # 전문가 이름 추출
    name_match = re.search(r'\[(Contact|Deform|Necking|Aging|Tracking|DielectricAge|Mechanical|StrandFracture)', report_text, re.IGNORECASE)
    if name_match:
        result["expert_name"] = name_match.group(1).upper()
    
    # 결론 추출
    conclusion_match = re.search(r'## 결론[:\s]*([^\n]+)', report_text)
    if conclusion_match:
        conclusion = conclusion_match.group(1).strip()
        # Analysis Skipped 확인
        if "Analysis Skipped" in report_text or "아님" in conclusion or "해당 없음" in conclusion or "전선이 아님" in report_text:
            result["conclusion"] = "해당 없음"
            result["confidence"] = "100%"
            # 분석 제외 이유 추출
            if "전선이 아님" in report_text or "Target is not a Wire" in report_text:
                result["key_evidence"] = "분석 제외 (대상: 터미널)"
            else:
                result["key_evidence"] = "분석 제외"
        else:
            # 결론에서 핵심만 추출
            if "유력" in conclusion:
                result["conclusion"] = "유력"
            elif "의심" in conclusion:
                result["conclusion"] = "의심"
            elif "아님" in conclusion:
                result["conclusion"] = "아님"
            else:
                result["conclusion"] = conclusion.split('(')[0].strip() if '(' in conclusion else conclusion
            
            # 신뢰도 추출
            conf_match = re.search(r'\((\d+\.?\d*)%\)', conclusion)
            if conf_match:
                result["confidence"] = f"{float(conf_match.group(1)):.1f}%"
            else:
                conf_match = re.search(r'(\d+\.?\d*)%', report_text)
                if conf_match:
                    result["confidence"] = f"{float(conf_match.group(1)):.1f}%"
            
            # 핵심 근거 추출
            if "Pitting" in report_text or "크레이터" in report_text or "터미널" in report_text:
                result["key_evidence"] = "Pitting, 열적 구배, 단락 비드 부재"
            elif "압착" in report_text:
                result["key_evidence"] = "압착흔 분석"
            elif "반단선" in report_text:
                result["key_evidence"] = "반단선 분석"
            else:
                result["key_evidence"] = "물리적 증거 분석"
    
    return result

def format_investigation_result(
    final_verdict: str,
    expert_reports: list,
    arbiter_debate_messages: list,
    input_image_path: str,
    timestamp: str
) -> str:
    """분석 결과를 깔끔한 표 형식으로 포맷팅"""
    output = []
    
    # 헤더 정보 파싱
    image_name = Path(input_image_path).name
    
    # 최종 판정 파싱
    verdict_info = parse_final_verdict(final_verdict)
    
    # 헤더 테이블
    output.append("# 📑 AI 화재조사 분석 리포트\n")
    output.append("| 분석 일시 | {} | 대상 이미지 | {} |".format(timestamp, image_name))
    output.append("| :--- | :--- | :--- | :--- |")
    output.append("| **최종 판정** | **{}** | **신뢰도** | **{} ({})** |\n".format(
        verdict_info["verdict"],
        verdict_info["confidence"],
        verdict_info["confidence_level"]
    ))
    
    # 전문가 분석 요약
    output.append("## 1. 전문가 에이전트 분석 요약\n")
    output.append("| 전문가 (Agent) | 판정 결과 | 신뢰도 | 핵심 근거 |")
    output.append("| :--- | :---: | :---: | :--- |")
    
    expert_summaries = []
    for report in expert_reports:
        expert_info = parse_expert_report(report)
        expert_summaries.append(expert_info)
        
        conclusion_display = expert_info["conclusion"]
        if expert_info["conclusion"] == "해당 없음":
            conclusion_display = "**해당 없음**"
        
        output.append("| **{}** | {} | {} | {} |".format(
            expert_info["expert_name"],
            conclusion_display,
            expert_info["confidence"],
            expert_info["key_evidence"]
        ))
    
    output.append("")
    
    # Arbiter 최종 판정 논리
    output.append("## 2. Arbiter 최종 판정 논리\n")
    # 판정 근거 추출 - 여러 패턴 시도
    reasoning_text = None
    
    # 패턴 1: **[판정 근거]** 형식
    reasoning_match = re.search(r'\*\*\[판정 근거\]\*\*\s*\n(.*?)(?=\*\*\[|$)', final_verdict, re.DOTALL)
    if reasoning_match:
        reasoning_text = reasoning_match.group(1).strip()
    else:
        # 패턴 2: [판정 근거] 형식 (볼드 없음)
        reasoning_match = re.search(r'\[판정 근거\]\s*\n(.*?)(?=\[|$)', final_verdict, re.DOTALL)
        if reasoning_match:
            reasoning_text = reasoning_match.group(1).strip()
    
    if reasoning_text:
        # 번호 목록을 정리 - 여러 패턴 시도
        reasoning_lines = re.findall(r'\d+\.\s*\*\*([^*]+)\*\*[:\s]*([^\n]+)', reasoning_text)
        if not reasoning_lines:
            # 패턴 2: **제목:** 내용 형식
            reasoning_lines = re.findall(r'\d+\.\s+\*\*([^*]+)\*\*[:\s]+([^\n]+)', reasoning_text)
        if not reasoning_lines:
            # 패턴 3: 번호. 제목: 내용 (볼드 없음)
            reasoning_lines = re.findall(r'\d+\.\s+([^:]+):\s*([^\n]+)', reasoning_text)
        
        if reasoning_lines:
            for num, title, content in reasoning_lines:
                output.append(f"**{num}. {title.strip()}**")
                output.append(f"{content.strip()}\n")
        else:
            # 번호 목록이 없으면 전체 텍스트를 그대로 출력
            output.append(reasoning_text)
            output.append("")
    else:
        # 판정 근거가 없으면 종합 분석 추출
        summary_match = re.search(r'\*\*\[종합 분석\]\*\*\s*\n(.*?)(?=\*\*\[|$)', final_verdict, re.DOTALL)
        if not summary_match:
            summary_match = re.search(r'\[종합 분석\]\s*\n(.*?)(?=\[|$)', final_verdict, re.DOTALL)
        if summary_match:
            summary_text = summary_match.group(1).strip()
            # 너무 길면 요약
            if len(summary_text) > 500:
                output.append(summary_text[:500] + "...")
            else:
                output.append(summary_text)
            output.append("")
        else:
            # 아무것도 없으면 안내 메시지
            output.append("*판정 논리 정보를 추출할 수 없습니다.*\n")
    
    # 상세 토론 과정
    if arbiter_debate_messages:
        output.append("## 3. 상세 토론 과정\n")
        current_round = None
        current_stage = None
        
        for msg in arbiter_debate_messages:
            speaker = msg.get("speaker", "unknown")
            content = msg.get("content", "")
            stage = msg.get("stage", "")
            round_num = msg.get("round_num", 0)
            validated = msg.get("validated", None)
            
            # Judge는 최종 판정이므로 별도 섹션으로 처리하지 않음 (이미 위에 포함됨)
            if speaker == "judge":
                continue
            
            # Round/Stage 헤더
            if round_num != current_round or stage != current_stage:
                if current_round is not None:
                    output.append("")
                stage_kr = {"opening": "개회", "rebuttal": "반론", "judgment": "판정"}.get(stage, stage)
                output.append(f"### Round {round_num}: {stage_kr}\n")
                current_round = round_num
                current_stage = stage
            
            # 발언자별 포맷팅
            if speaker in ["contact", "deform", "necking"]:
                validation_status = " ✓ 통과" if validated else " ✗ 실패" if validated is False else ""
                output.append(f"**{speaker.upper()} 전문가{validation_status}**\n\n")
            elif speaker == "fact_checker":
                output.append("**Fact Checker**\n\n")
            elif speaker == "moderator":
                # Moderator 메시지는 간단히만 표시
                if "합의" in content or "도달" in content:
                    output.append(f"*{content.strip()}*\n\n")
                continue
            
            # 내용 (간결하게, 전문가 발언만 상세히)
            if speaker in ["contact", "deform", "necking"]:
                content_lines = content.split('\n')
                # 핵심 내용만 추출 (첫 3-5줄)
                if len(content_lines) > 8:
                    # 첫 문단과 마지막 문단만
                    first_part = "\n".join(content_lines[:3])
                    last_part = "\n".join([line for line in content_lines[-2:] if line.strip()])
                    output.append(f"{first_part}\n\n*... (중략) ...*\n\n{last_part}\n")
                else:
                    output.append(f"{content}\n")
            elif speaker == "fact_checker":
                # Fact Checker는 간단히만
                if "통과" in content or "일관성" in content:
                    output.append(f"*{content[:100]}...*\n")
            
            output.append("")
    
    return "\n".join(output)

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
    print("\n[2단계] 멀티 에이전트 병렬 분석 시작")
    print("  - Hotspot Detector가 관심 영역을 탐지합니다.")
    print("  - 3인의 전문가 에이전트가 병렬로 동시에 분석합니다. (Fan-Out)")
    print("    (Contact, Deform, Necking - Map-Reduce Pattern)")
    print("  - 각 전문가는 독립적인 서브그래프로 동작하며 Map-Reduce 패턴을 사용합니다.")
    print("  - 모든 분석 결과를 수집합니다. (Fan-In)")
    print("  - 수석 조사관(Arbiter)이 종합하여 최종 결론을 도출합니다.")
    
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
    arbiter_debate_messages = result.get("arbiter_debate_messages", [])
    errors = result.get("errors", [])
    
    # #region agent log
    import json as json_module
    import time as time_module
    from pathlib import Path as Path_module
    log_path = Path_module(__file__).parent / ".cursor" / "debug.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json_module.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"main.py:149","message":"Extracting arbiter_debate_messages","data":{"result_keys":list(result.keys()),"has_arbiter_debate_messages":"arbiter_debate_messages" in result,"arbiter_debate_messages_count":len(arbiter_debate_messages) if arbiter_debate_messages else 0,"arbiter_debate_messages_type":type(arbiter_debate_messages).__name__,"arbiter_debate_messages_is_none":arbiter_debate_messages is None},"timestamp":int(time_module.time()*1000)})+"\n")
    except: pass
    # #endregion
    
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
    # output_dir이 Path 객체인지 확인하고 변환
    from pathlib import Path as Path_module
    if not isinstance(output_dir, Path_module):
        output_dir = Path_module(output_dir)
    
    output_file = output_dir / "investigation_result.txt"
    # #region agent log
    import json
    import time as time_module
    log_path = Path_module(__file__).parent / ".cursor" / "debug.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"main.py:164","message":"File save entry","data":{"output_dir":str(output_dir),"output_file":str(output_file),"output_dir_type":type(output_dir).__name__,"output_dir_exists":output_dir.exists(),"output_dir_is_dir":output_dir.is_dir() if output_dir.exists() else False},"timestamp":int(time_module.time()*1000)})+"\n")
    except: pass
    # #endregion
    try:
        # 디렉토리 존재 확인 및 생성 (방어적 코드)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"main.py:178","message":"Directory ensured","data":{"output_dir":str(output_dir),"output_file_parent":str(output_file.parent),"parent_exists":output_file.parent.exists()},"timestamp":int(time_module.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"main.py:175","message":"Before file write","data":{"output_dir_exists":output_dir.exists(),"output_file":str(output_file),"output_file_parent":str(output_file.parent)},"timestamp":int(time_module.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # 1. 통합 결과 파일 저장 (개선된 포맷)
        timestamp_str = time.strftime('%Y-%m-%d %H:%M:%S')
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f_log:
                f_log.write(json_module.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"main.py:213","message":"Checking arbiter_debate_messages before write","data":{"arbiter_debate_messages_count":len(arbiter_debate_messages) if arbiter_debate_messages else 0,"arbiter_debate_messages_is_none":arbiter_debate_messages is None,"arbiter_debate_messages_bool":bool(arbiter_debate_messages)},"timestamp":int(time_module.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        with open(output_file, 'w', encoding='utf-8') as f:
            # 새로운 포맷으로 결과 작성
            formatted_result = format_investigation_result(
                final_verdict=final_verdict,
                expert_reports=expert_reports or [],
                arbiter_debate_messages=arbiter_debate_messages or [],
                input_image_path=input_image_path,
                timestamp=timestamp_str
            )
            f.write(formatted_result)
            
            # 추가 정보 (원본 데이터 보존용)
            f.write("\n\n---\n\n")
            f.write("## 4. 상세 분석 내용\n\n")
            f.write("### 최종 판정 상세\n")
            f.write(final_verdict)
            f.write("\n\n")
            
            # 전문가 상세 리포트
            if expert_reports:
                f.write("### 전문가 상세 리포트\n\n")
                for i, report in enumerate(expert_reports, 1):
                    f.write(f"#### Expert Report {i}\n\n")
                    f.write(report)
                    f.write("\n\n")
            
            # 오류 로그
            if errors:
                f.write("\n---\n\n")
                f.write("## 5. System Errors & Warnings\n\n")
                for err in errors:
                    f.write(f"- {err}\n")

        print(f"\n✅ 전체 결과가 저장되었습니다: {output_file}")
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"main.py:196","message":"Main file saved successfully","data":{"output_file":str(output_file),"file_exists":output_file.exists()},"timestamp":int(time_module.time()*1000)})+"\n")
        except: pass
        # #endregion

        # 2. 각 전문가별 별도 리포트 파일 저장
        if expert_reports:
            print("\n[개별 리포트 저장]")
            for report in expert_reports:
                # 리포트 헤더에서 전문가 이름 추출 (실제 리포트 헤더 형식에 맞춤)
                filename = "Unknown_Expert_Report.txt"
                if "[Contact 전문가" in report:
                    filename = "Contact_Expert_Report.txt"
                elif "[Deform 전문가" in report:
                    filename = "Deform_Expert_Report.txt"
                elif "[Necking 전문가" in report:
                    filename = "Necking_Expert_Report.txt"
                elif "[DielectricAge 전문가" in report:
                    filename = "Dielectric_Expert_Report.txt"
                elif "[Mechanical 전문가" in report:
                    filename = "Mechanical_Expert_Report.txt"
                elif "[StrandFracture 전문가" in report:
                    filename = "StrandFracture_Expert_Report.txt"
                elif "[Tracking 전문가" in report:
                    filename = "Tracking_Expert_Report.txt"
                
                expert_file = output_dir / filename
                # #region agent log
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"main.py:255","message":"Saving expert report","data":{"filename":filename,"expert_file":str(expert_file),"output_dir_exists":output_dir.exists(),"expert_file_parent":str(expert_file.parent),"parent_exists":expert_file.parent.exists()},"timestamp":int(time_module.time()*1000)})+"\n")
                except: pass
                # #endregion
                try:
                    # 디렉토리 존재 확인 및 생성 (방어적 코드)
                    expert_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(expert_file, 'w', encoding='utf-8') as f:
                        f.write(report)
                    # #region agent log
                    try:
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"main.py:264","message":"Expert report saved successfully","data":{"filename":filename,"expert_file":str(expert_file),"file_exists":expert_file.exists()},"timestamp":int(time_module.time()*1000)})+"\n")
                    except: pass
                    # #endregion
                    print(f"  - {filename} 저장 완료")
                except Exception as e:
                    # #region agent log
                    import traceback
                    try:
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"main.py:264","message":"Expert report save error","data":{"filename":filename,"expert_file":str(expert_file),"error":str(e),"error_type":type(e).__name__,"traceback":traceback.format_exc()},"timestamp":int(time_module.time()*1000)})+"\n")
                    except: pass
                    # #endregion
                    print(f"  - {filename} 저장 실패: {e}")
        
        # 3. Arbiter(최종 결론) 리포트 별도 저장
        if final_verdict:
            arbiter_file = output_dir / "Arbiter_Report.txt"
            # #region agent log
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"main.py:262","message":"Saving arbiter report","data":{"arbiter_file":str(arbiter_file),"output_dir_exists":output_dir.exists(),"arbiter_file_parent":str(arbiter_file.parent),"parent_exists":arbiter_file.parent.exists()},"timestamp":int(time_module.time()*1000)})+"\n")
            except: pass
            # #endregion
            try:
                # 디렉토리 존재 확인 및 생성 (방어적 코드)
                arbiter_file.parent.mkdir(parents=True, exist_ok=True)
                with open(arbiter_file, 'w', encoding='utf-8') as f:
                    f.write("[Arbiter (Chief Investigator) Report]\n\n")
                    f.write(final_verdict)
                # #region agent log
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"main.py:277","message":"Arbiter report saved successfully","data":{"arbiter_file":str(arbiter_file),"file_exists":arbiter_file.exists()},"timestamp":int(time_module.time()*1000)})+"\n")
                except: pass
                # #endregion
                print(f"  - Arbiter_Report.txt 저장 완료")
            except Exception as e:
                # #region agent log
                import traceback
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"main.py:277","message":"Arbiter report save error","data":{"arbiter_file":str(arbiter_file),"error":str(e),"error_type":type(e).__name__,"traceback":traceback.format_exc()},"timestamp":int(time_module.time()*1000)})+"\n")
                except: pass
                # #endregion
                print(f"  - Arbiter_Report.txt 저장 실패: {e}")
        
    except Exception as e:
        # #region agent log
        import traceback
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"main.py:233","message":"File save error","data":{"error":str(e),"error_type":type(e).__name__,"output_dir":str(output_dir),"output_file":str(output_file),"output_dir_exists":output_dir.exists() if output_dir else False,"traceback":traceback.format_exc()},"timestamp":int(time_module.time()*1000)})+"\n")
        except: pass
        # #endregion
        print(f"❌ 결과 파일 저장 실패: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="화재조사 AI 멀티 에이전트 시스템 (Fan-In/Fan-Out Parallel Multi-Agent)"
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
    # #region agent log
    import json
    import time as time_module
    from pathlib import Path as Path_module
    log_path = Path_module(__file__).parent / ".cursor" / "debug.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"main.py:311","message":"Creating output directory","data":{"output_base_dir":str(output_base_dir),"output_dir":str(output_dir),"input_filename":input_filename},"timestamp":int(time_module.time()*1000)})+"\n")
    except: pass
    # #endregion
    output_dir.mkdir(parents=True, exist_ok=True)
    # #region agent log
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"main.py:312","message":"Output directory created","data":{"output_dir":str(output_dir),"output_dir_exists":output_dir.exists(),"output_dir_is_dir":output_dir.is_dir() if output_dir.exists() else False},"timestamp":int(time_module.time()*1000)})+"\n")
    except: pass
    # #endregion

    # 파이프라인 실행
    run_analysis_pipeline(input_image_path, output_dir, args.query)

if __name__ == "__main__":
    main()
