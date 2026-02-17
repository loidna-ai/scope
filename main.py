"""
화재조사 AI 멀티 에이전트 시스템 메인 실행 파일
Updated Workflow: Fan-In/Fan-Out Multi-Agent Parallel Architecture
"""
import sys
import argparse
import warnings
import time
import re
import base64
import traceback
from pathlib import Path
from typing import List, Dict, Any, Optional
import config
from src.agent import analyze_fire_evidence
from src.utils import find_data_directory
from src.utils.report_generator import generate_report_llm
from src.utils.logging_config import setup_logger

# 구조화된 데이터 타입 (순환 참조 방지)
try:
    from src.models.verdict_models import FinalVerdictResult
except ImportError:
    FinalVerdictResult = Any  # Fallback (타입 체크용)

# 로거 초기화
logger = setup_logger(__name__)

# torchvision 경고 억제
warnings.filterwarnings(
    'ignore', category=UserWarning, module='torchvision.transforms.functional_tensor'
)

# Raw 에러 패턴 (사용자 노출 금지)
_RAW_ERROR_PATTERNS = (
    r"name '[^']+' is not defined",
    r"Supervisor Error:",
    r"Traceback \(most recent",
    r"File \"",
    r"ValueError:",
    r"KeyError:",
    r"ImportError:",
    r"ModuleNotFoundError:",
    r"config\.",
)

# 최종 판정 추출 패턴
VERDICT_PATTERNS = [
    r'\*\*최종 판정\*\*\s*[\|\s]*\*\*([^*\]]+)\*\*',
    r'\*\*최종 판정\*\*\s*\n\s*\*\*([^*\]]+)\*\*',
    r'\*\*최종 판정\*\*\s*\n\s*([^\n\]]+)',
    r'최종 판정[:\s\|]*([^\n\]]+)',
    r'([가-힣]+\([^)]+\)\s*[가-힣]+)',
]

# 판정 근거 추출 패턴
REASONING_PATTERNS = [
    r'\[판정 근거\]\s*\n(.*?)(?=\[|$)',
    r'\*\*\[판정 근거\]\*\*\s*\n(.*?)(?=\*\*\[|$)',
    r'\[종합 분석\]\s*\n(.*?)(?=\[|$)',
]

# 신뢰도 추출 패턴
CONFIDENCE_PATTERN = r'(\d+\.?\d*)%'
CONFIDENCE_LEVEL_PATTERN = r'(High|Medium|Low)'

# 기타 정규식 패턴
VERDICT_CLEANUP_PATTERNS = [
    (r'\*\*\s*\]\s*\*\*', ''),
    (r'\*\*\]\s*', ''),
]

VERDICT_PHRASE_PATTERNS = [
    r'\[최종 판정\]\s*\n(.*?)(?=\[|\n\n|\Z)',
    r'\*\*화재 원인[:\s]*\*\*(.*?)(?=\n\n|\Z)',
]

BULLET_PATTERNS = [
    r'\d+\.\s+\*\*([^*]+)\*\*[:\s]*([^\n]+)',
    r'\d+\.\s+([^:]+):\s*([^\n]+)',
]

EXPERT_NAME_PATTERN = r'\[(Contact|Deform|Necking|Aging|Tracking|DielectricAge|Mechanical|StrandFracture)'
CONCLUSION_PATTERN = r'## 결론[:\s]*([^\n]+)'
CONFIDENCE_IN_PARENTHESES_PATTERN = r'\((\d+\.?\d*)%\)'
RECOMMENDATION_PATTERN = r'\[추가 조사 (?:필요 사항|권고 사항)\]\s*\n(.*?)(?=\[|\n##|\Z)'
RECOMMENDATION_ITEMS_PATTERN = r'\d+\.\s+(.+)'
ZONE_PATTERN_TEMPLATE = r'Zone\s*{}\s*[의:]?\s*([가-힣a-zA-Z0-9\s,\-]+?)(?=\.|Zone|\d+\.|$)'


def _sanitize_user_visible_text(text: str) -> str:
    """사용자에게 노출되는 텍스트에서 Raw Python 에러를 제거
    
    Args:
        text: 정제할 텍스트
        
    Returns:
        정제된 텍스트
    """
    if not text or not isinstance(text, str):
        return text
    for pat in _RAW_ERROR_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "판독 보류 (분석 데이터 부족)"
    return text


def _sanitize_report_for_display(report: str) -> str:
    """전문가 상세 리포트 내 Raw 에러를 정제 (파일 저장용)
    
    Args:
        report: 정제할 리포트 텍스트
        
    Returns:
        정제된 리포트 텍스트
    """
    if not report or not isinstance(report, str):
        return report
    sanitized = report
    # Raw Python/시스템 에러가 포함된 줄을 정제
    sanitized = re.sub(r'[^\n]*Supervisor Error:[^\n]*', '※ 분석 불가 (시스템 데이터 부족)', sanitized)
    sanitized = re.sub(r'[^\n]*name\s+\'[^\']+\'\s+is not defined[^\n]*', '※ 분석 불가 (시스템 데이터 부족)', sanitized)
    sanitized = re.sub(r'\[오류\]\s*\n\s*LLM 호출 실패:[^\n]*', '[오류]\nLLM 호출 실패: (시스템 일시 오류)', sanitized)
    sanitized = re.sub(r'\(Error:\s*[^)]+\)', '(시스템 오류)', sanitized)
    if "Traceback" in sanitized or 'File "' in sanitized:
        sanitized = re.sub(r'Traceback \(most recent call last\):.*?(?=\n\n|\Z)', '※ 분석 불가 (시스템 데이터 부족)', sanitized, flags=re.DOTALL)
    return sanitized


def parse_final_verdict(verdict_text: str) -> Dict[str, str]:
    """최종 판정 텍스트에서 판정 결과와 신뢰도를 추출
    
    Args:
        verdict_text: 최종 판정 텍스트
        
    Returns:
        판정 정보 딕셔너리:
        - verdict: 판정 결과 문자열
        - confidence: 신뢰도 퍼센트 문자열
        - confidence_level: 신뢰도 레벨 (High/Medium/Low)
    """
    result = {
        "verdict": "판정 불가",
        "confidence": "N/A",
        "confidence_level": "N/A"
    }
    if not verdict_text:
        return result
    
    # 파싱 오류 방지: stray ] 제거 (예: **최종 판정** | **]**)
    clean_text = verdict_text
    for pattern, replacement in VERDICT_CLEANUP_PATTERNS:
        clean_text = re.sub(pattern, replacement, clean_text)
    
    # 최종 판정 추출 - 여러 패턴 시도
    verdict_match = None
    for pattern in VERDICT_PATTERNS:
        verdict_match = re.search(pattern, clean_text)
        if verdict_match:
            break
    if verdict_match:
        raw = verdict_match.group(1).strip()
        result["verdict"] = _sanitize_user_visible_text(raw) if raw else "판정 불가"
    
    # 신뢰도 추출
    confidence_match = re.search(CONFIDENCE_PATTERN, clean_text)
    if confidence_match:
        conf_value = float(confidence_match.group(1))
        result["confidence"] = f"{conf_value:.1f}%"
        if conf_value >= config.CONFIDENCE_HIGH_THRESHOLD:
            result["confidence_level"] = "High"
        elif conf_value >= config.CONFIDENCE_MEDIUM_THRESHOLD:
            result["confidence_level"] = "Medium"
        else:
            result["confidence_level"] = "Low"
    else:
        level_match = re.search(CONFIDENCE_LEVEL_PATTERN, clean_text, re.IGNORECASE)
        if level_match:
            result["confidence_level"] = level_match.group(1)
            result["confidence"] = "N/A"
    
    return result


def parse_expert_report(report_text: str) -> Dict[str, str]:
    """전문가 리포트에서 판정 결과 추출 (Raw 에러 메시지는 정제)
    
    Args:
        report_text: 전문가 리포트 텍스트
        
    Returns:
        전문가 정보 딕셔너리:
        - expert_name: 전문가 이름
        - conclusion: 결론 (유력/의심/아님/해당 없음)
        - confidence: 신뢰도 퍼센트 문자열
        - key_evidence: 핵심 근거 문자열
    """
    result = {
        "expert_name": "Unknown",
        "conclusion": "해당 없음",
        "confidence": "N/A",
        "key_evidence": "해당 없음"
    }
    if not report_text:
        return result
    
    # Raw 에러 포함 시 key_evidence만 정제 (결론은 유지)
    def _safe_evidence(s: str) -> str:
        return _sanitize_user_visible_text(s) if s else "해당 없음"
    
    # 전문가 이름 추출
    name_match = re.search(EXPERT_NAME_PATTERN, report_text, re.IGNORECASE)
    if name_match:
        result["expert_name"] = name_match.group(1).upper()
    
    # 결론 추출
    conclusion_match = re.search(CONCLUSION_PATTERN, report_text)
    if conclusion_match:
        conclusion = conclusion_match.group(1).strip()
        # Analysis Skipped 확인 (해당 없음: 분석 미적용 vs 아님: 분석 후 음성 판정)
        if "Analysis Skipped" in report_text or "해당 없음" in conclusion or "전선이 아님" in report_text:
            result["conclusion"] = "해당 없음"
            result["confidence"] = "-"
            # DEFORM: 분석 대상이 전선이 아닌 경우 상세 설명
            if result["expert_name"] == "DEFORM" and ("전선이 아님" in report_text or "Target is not a Wire" in report_text):
                result["key_evidence"] = "분석 대상이 전선이 아니므로(터미널) 압착/손상 분석 알고리즘 적용 제외"
            elif "전선이 아님" in report_text or "Target is not a Wire" in report_text:
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
            conf_match = re.search(CONFIDENCE_IN_PARENTHESES_PATTERN, conclusion)
            if conf_match:
                result["confidence"] = f"{float(conf_match.group(1)):.1f}%"
            else:
                conf_match = re.search(CONFIDENCE_PATTERN, report_text)
                if conf_match:
                    result["confidence"] = f"{float(conf_match.group(1)):.1f}%"
            
            # 핵심 근거 추출 (표준 용어: Arc Bead, 용융흔)
            if "Pitting" in report_text or "크레이터" in report_text or "터미널" in report_text:
                result["key_evidence"] = "Pitting, 열적 구배, Arc Bead 부재"
            elif "압착" in report_text:
                result["key_evidence"] = "압착흔 분석"
            elif "반단선" in report_text:
                result["key_evidence"] = "반단선(용융흔) 분석"
            else:
                result["key_evidence"] = "물리적 증거 분석"
    
    # 최종 key_evidence 정제 (Raw 에러 은닉)
    result["key_evidence"] = _safe_evidence(result["key_evidence"])
    return result


def _confidence_badge(level: str) -> str:
    """신뢰도 레벨에 따른 시각적 표시 (텍스트 리포트용)"""
    badges = {"High": "🟢 High", "Medium": "🟡 Medium", "Low": "🔴 Low"}
    return badges.get(level, level)


def _format_report_header(
    timestamp: str,
    image_name: str,
    verdict_info: Dict[str, str]
) -> List[str]:
    """리포트 헤더 섹션 생성
    
    Args:
        timestamp: 분석 일시
        image_name: 이미지 파일명
        verdict_info: 판정 정보 딕셔너리
        
    Returns:
        헤더 라인 리스트
    """
    output = []
    conf_badge = _confidence_badge(verdict_info.get("confidence_level", "N/A"))
    output.append("# 🔥 AI 화재증거물 정밀 분석 보고서\n")
    output.append(f"| 분석 일시 | {timestamp} | 대상 이미지 | {image_name} |")
    output.append("| :--- | :--- | :--- | :--- |")
    verdict_display = verdict_info.get("verdict", "판정 불가")
    confidence_display = verdict_info.get("confidence", "N/A")
    output.append(f"| **최종 판정** | **{verdict_display}** | **AI 신뢰도** | **{confidence_display} ({conf_badge})** |\n")
    return output


def _format_executive_summary(
    final_verdict: str,
    verdict_info: Dict[str, str]
) -> List[str]:
    """종합 분석 결론 섹션 생성 (정규식 기반, Fallback용)
    
    Args:
        final_verdict: 최종 판정 텍스트
        verdict_info: 판정 정보 딕셔너리
        
    Returns:
        Executive Summary 라인 리스트, reasoning_text 튜플
    """
    output = []
    output.append("## 1. 종합 분석 결론 (Executive Summary)\n")
    
    # [최종 판정] 추출
    verdict_match = None
    for pattern in VERDICT_PHRASE_PATTERNS:
        verdict_match = re.search(pattern, final_verdict, re.DOTALL)
        if verdict_match:
            break
    default_verdict = verdict_info.get("verdict", "판정 불가")
    verdict_phrase = verdict_match.group(1).strip() if verdict_match else default_verdict
    verdict_phrase = re.sub(r'^\*\*|\*\*$', '', verdict_phrase).strip()
    
    output.append("**판정 요약:**\n")
    output.append(f"본 시스템은 3개의 전문 분석 에이전트(Contact, Deform, Necking)의 교차 검증을 통해, 해당 증거물의 발화 원인을 **'{verdict_phrase}'**로 최종 판정합니다.\n")
    
    # [판정 근거] → 핵심 근거 bullet 추출
    reasoning_text = None
    for pattern in REASONING_PATTERNS:
        reasoning_match = re.search(pattern, final_verdict, re.DOTALL)
        if reasoning_match:
            reasoning_text = reasoning_match.group(1).strip()
            break
    
    output.append("\n**핵심 근거:**\n")
    if reasoning_text:
        # 번호 목록(1. 2. 3.) 추출 → bullet 형태로
        bullets = None
        for pattern in BULLET_PATTERNS:
            bullets = re.findall(pattern, reasoning_text)
            if bullets:
                break
        if bullets:
            for title, content in bullets[:config.MAX_BULLET_POINTS]:
                output.append(f"- **{title.strip()}**: {content.strip()}.")
        else:
            truncate_len = config.REASONING_TEXT_TRUNCATE_LENGTH
            truncated = reasoning_text[:truncate_len] + ("..." if len(reasoning_text) > truncate_len else "")
            output.append(f"- {truncated}")
    else:
        output.append("- *판정 근거가 추출되지 않았습니다.*")
    output.append("")
    
    return output, reasoning_text


def _format_executive_summary_structured(final_verdict_structured: Any) -> List[str]:
    """종합 분석 결론 섹션 생성 (구조화된 데이터 기반)
    
    Args:
        final_verdict_structured: FinalVerdictResult 객체 또는 딕셔너리
        
    Returns:
        Executive Summary 라인 리스트
    """
    output = []
    output.append("## 1. 종합 분석 결론 (Executive Summary)\n")
    
    # Pydantic 모델인지 확인
    if hasattr(final_verdict_structured, 'verdict'):
        verdict_phrase = final_verdict_structured.verdict
        key_evidence = final_verdict_structured.key_evidence
        reasoning_summary = final_verdict_structured.reasoning_summary
    else:
        # 딕셔너리 형태
        verdict_phrase = final_verdict_structured.get("verdict", "판정 불가")
        key_evidence = final_verdict_structured.get("key_evidence", [])
        reasoning_summary = final_verdict_structured.get("reasoning_summary", "")
    
    output.append("**판정 요약:**\n")
    output.append(f"본 시스템은 3개의 전문 분석 에이전트(Contact, Deform, Necking)의 교차 검증을 통해, 해당 증거물의 발화 원인을 **'{verdict_phrase}'**로 최종 판정합니다.\n")
    
    output.append("\n**핵심 근거:**\n")
    if key_evidence:
        for evidence in key_evidence[:config.MAX_BULLET_POINTS]:
            output.append(f"- {evidence}")
    elif reasoning_summary:
        truncate_len = config.REASONING_TEXT_TRUNCATE_LENGTH
        truncated = reasoning_summary[:truncate_len] + ("..." if len(reasoning_summary) > truncate_len else "")
        output.append(f"- {truncated}")
    else:
        output.append("- *판정 근거가 추출되지 않았습니다.*")
    output.append("")
    
    return output


def _format_expert_reports_section(expert_reports: List[str]) -> List[str]:
    """전문가 에이전트 세부 소견 섹션 생성
    
    Args:
        expert_reports: 전문가 리포트 리스트
        
    Returns:
        전문가 리포트 테이블 라인 리스트
    """
    output = []
    output.append("## 2. 전문가 에이전트 세부 소견\n")
    output.append("| 분석 모듈 | 판정 결과 | 신뢰도 | 상세 소견 |")
    output.append("| :--- | :---: | :---: | :--- |")
    
    EXPERT_LABELS = {"CONTACT": "접촉불량", "DEFORM": "압착/손상", "NECKING": "용융/단선"}
    for report in expert_reports:
        if not isinstance(report, str):
            continue
        
        expert_info = parse_expert_report(report)
        if not isinstance(expert_info, dict):
            continue
        
        conclusion = expert_info.get("conclusion", "해당 없음")
        if conclusion == "해당 없음":
            conclusion_display = "**해당 없음 (N/A)**"
        elif conclusion == "유력":
            conclusion_display = "유력 (Positive)"
        elif conclusion == "판독 불가":
            conclusion_display = "판독 불가"
        else:
            conclusion_display = conclusion
        
        expert_name = expert_info.get("expert_name", "Unknown")
        label = EXPERT_LABELS.get(expert_name, "")
        module_col = f"**{expert_name}** ({label})" if label else f"**{expert_name}**"
        
        confidence = expert_info.get("confidence", "N/A")
        key_evidence = expert_info.get("key_evidence", "해당 없음")
        
        output.append(f"| {module_col} | {conclusion_display} | {confidence} | {key_evidence} |")
    
    output.append("")
    return output


def _format_evidence_breakdown(reasoning_text: Optional[str]) -> List[str]:
    """상세 증거 분석 섹션 생성 (정규식 기반, Fallback용)
    
    Args:
        reasoning_text: 판정 근거 텍스트 (Zone 정보 추출용)
        
    Returns:
        증거 분석 라인 리스트
    """
    output = []
    output.append("## 3. 상세 증거 분석 (Evidence Breakdown)\n")
    output.append("*(이곳에 Zone 1, 3, 4가 표시된 분석 이미지를 삽입하세요)*\n\n")
    zone_info = [(1, "압착부 경계", "소선 간 탄화물 고착 심화. 물리적 틈새(Gap) 존재."),
                 (3, "도체 표면", "장기 과열 특유의 적갈색/회색 산화 스케일 관찰."),
                 (4, "말단부", "용융흔 없음. 원형 유지.")]
    for z_num, z_desc, z_default in zone_info:
        custom = ""
        if reasoning_text:
            zone_pattern = ZONE_PATTERN_TEMPLATE.format(z_num)
            m = re.search(zone_pattern, reasoning_text, re.IGNORECASE)
            if m and len(m.group(1).strip()) > 4:
                custom = m.group(1).strip()[:100] + ("." if not m.group(1).strip().endswith(".") else "")
        zone_desc = custom if custom else z_default
        output.append(f"- **Zone {z_num} ({z_desc})**: {zone_desc}")
    output.append("")
    return output


def _format_evidence_breakdown_structured(zones: List[Any]) -> List[str]:
    """상세 증거 분석 섹션 생성 (구조화된 데이터 기반)
    
    Args:
        zones: ZoneInfo 객체 리스트 또는 딕셔너리 리스트
        
    Returns:
        증거 분석 라인 리스트
    """
    output = []
    output.append("## 3. 상세 증거 분석 (Evidence Breakdown)\n")
    output.append("*(이곳에 Zone 1, 3, 4가 표시된 분석 이미지를 삽입하세요)*\n\n")
    
    if zones:
        for zone in zones:
            if hasattr(zone, 'zone_number'):
                # Pydantic 모델
                z_num = zone.zone_number
                z_desc = zone.description
                z_obs = zone.observation
            else:
                # 딕셔너리
                z_num = zone.get("zone_number", 0)
                z_desc = zone.get("description", "")
                z_obs = zone.get("observation", "")
            
            output.append(f"- **Zone {z_num} ({z_desc})**: {z_obs}")
    else:
        # 기본 Zone 정보 (Fallback)
        zone_info = [(1, "압착부 경계", "소선 간 탄화물 고착 심화. 물리적 틈새(Gap) 존재."),
                     (3, "도체 표면", "장기 과열 특유의 적갈색/회색 산화 스케일 관찰."),
                     (4, "말단부", "용융흔 없음. 원형 유지.")]
        for z_num, z_desc, z_default in zone_info:
            output.append(f"- **Zone {z_num} ({z_desc})**: {z_default}")
    
    output.append("")
    return output


def _format_recommendations(final_verdict: str) -> List[str]:
    """추가 조사 권고 사항 섹션 생성 (정규식 기반, Fallback용)
    
    Args:
        final_verdict: 최종 판정 텍스트
        
    Returns:
        권고 사항 라인 리스트
    """
    output = []
    rec_match = re.search(RECOMMENDATION_PATTERN, final_verdict, re.DOTALL)
    if rec_match:
        rec_text = rec_match.group(1).strip()
        output.append("## 4. 추가 조사 권고 사항 (Recommendation)\n")
        rec_items = re.findall(RECOMMENDATION_ITEMS_PATTERN, rec_text)
        for i, item in enumerate(rec_items, 1):
            output.append(f"{i}. {item.strip()}")
        output.append("")
    return output


def _format_recommendations_structured(recommendations: List[str]) -> List[str]:
    """추가 조사 권고 사항 섹션 생성 (구조화된 데이터 기반)
    
    Args:
        recommendations: 권고 사항 문자열 리스트
        
    Returns:
        권고 사항 라인 리스트
    """
    output = []
    if recommendations:
        output.append("## 4. 추가 조사 권고 사항 (Recommendation)\n")
        for i, rec in enumerate(recommendations, 1):
            output.append(f"{i}. {rec.strip()}")
        output.append("")
    return output


def format_investigation_result(
    final_verdict: str,
    expert_reports: List[str],
    arbiter_debate_messages: List[Dict[str, Any]],
    input_image_path: str,
    timestamp: str,
    final_verdict_structured: Optional[Any] = None  # FinalVerdictResult (구조화된 데이터)
) -> str:
    """분석 결과를 실무용 보고서 형식으로 포맷팅 (결론→근거→상세 순)
    
    Args:
        final_verdict: 최종 판정 텍스트 (하위 호환성)
        expert_reports: 전문가 리포트 리스트
        arbiter_debate_messages: Arbiter 토론 메시지 리스트
        input_image_path: 입력 이미지 경로
        timestamp: 분석 일시
        final_verdict_structured: 구조화된 최종 판정 데이터 (우선 사용)
        
    Returns:
        포맷팅된 리포트 문자열
    """
    output = []
    image_name = Path(input_image_path).name
    
    # 🔥 구조화된 데이터 우선 사용
    if final_verdict_structured:
        try:
            from src.models.verdict_models import FinalVerdictResult
            # Pydantic 모델인지 확인
            if isinstance(final_verdict_structured, FinalVerdictResult):
                verdict_info = {
                    "verdict": final_verdict_structured.verdict,
                    "confidence": f"{final_verdict_structured.confidence_score:.1f}%",
                    "confidence_level": final_verdict_structured.confidence_level
                }
                reasoning_text = final_verdict_structured.reasoning_summary
                zones = final_verdict_structured.zones
                recommendations = final_verdict_structured.recommendations
                use_structured = True
            else:
                # 딕셔너리 형태인 경우
                verdict_info = {
                    "verdict": final_verdict_structured.get("verdict", "판정 불가"),
                    "confidence": f"{final_verdict_structured.get('confidence_score', 0):.1f}%",
                    "confidence_level": final_verdict_structured.get("confidence_level", "N/A")
                }
                reasoning_text = final_verdict_structured.get("reasoning_summary")
                zones = final_verdict_structured.get("zones", [])
                recommendations = final_verdict_structured.get("recommendations", [])
                use_structured = True
        except Exception as e:
            logger.warning(f"구조화된 데이터 파싱 실패, 정규식 Fallback 사용: {e}")
            use_structured = False
    else:
        use_structured = False
    
    # Fallback: 기존 정규식 파싱 (하위 호환성)
    if not use_structured:
        verdict_info = parse_final_verdict(final_verdict)
        if not isinstance(verdict_info, dict):
            verdict_info = {
                "verdict": "판정 불가",
                "confidence": "N/A",
                "confidence_level": "N/A"
            }
        reasoning_text = None
        zones = []
        recommendations = []
    
    # 헤더 섹션
    output.extend(_format_report_header(timestamp, image_name, verdict_info))
    
    # Executive Summary 섹션
    if use_structured:
        summary_lines = _format_executive_summary_structured(final_verdict_structured)
        output.extend(summary_lines)
    else:
        summary_lines, reasoning_text = _format_executive_summary(final_verdict, verdict_info)
        output.extend(summary_lines)
    
    # 전문가 리포트 섹션
    output.extend(_format_expert_reports_section(expert_reports))
    
    # 증거 분석 섹션
    if use_structured and zones:
        output.extend(_format_evidence_breakdown_structured(zones))
    else:
        output.extend(_format_evidence_breakdown(reasoning_text))
    
    # 권고 사항 섹션
    if use_structured and recommendations:
        output.extend(_format_recommendations_structured(recommendations))
    else:
        output.extend(_format_recommendations(final_verdict))
    
    # AI 추론 로그 섹션
    output.append(_format_audit_trail_section(arbiter_debate_messages or []))
    
    return "\n".join(output)


def _format_audit_trail_section(arbiter_debate_messages: List[Dict[str, Any]]) -> str:
    """AI 추론 로그(섹션 5)만 포맷팅. LLM 리포트에 붙일 때 사용.
    
    Args:
        arbiter_debate_messages: Arbiter 토론 메시지 리스트
        
    Returns:
        포맷팅된 Audit Trail 섹션 문자열
    """
    if not arbiter_debate_messages:
        return ""
    output = []
    output.append("## 5. [첨부] AI 추론 로그 (상세 토론 과정)\n")
    output.append("*최종 사용자용 요약 상단 배치 완료. 이하 상세 토론 내역.*\n")
    current_round = None
    current_stage = None
    for msg in arbiter_debate_messages:
        if not isinstance(msg, dict):
            continue
        
        speaker = msg.get("speaker", "unknown")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        stage = msg.get("stage", "")
        round_num = msg.get("round_num", 0)
        validated = msg.get("validated", None)
        if speaker == "judge":
            continue
        if round_num != current_round or stage != current_stage:
            if current_round is not None:
                output.append("")
            stage_kr = {"opening": "개회", "rebuttal": "반론", "judgment": "판정"}.get(stage, stage)
            output.append(f"### Round {round_num}: {stage_kr}\n")
            current_round = round_num
            current_stage = stage
        if speaker in ["contact", "deform", "necking"]:
            validation_status = " ✓ 통과" if validated else " ✗ 실패" if validated is False else ""
            output.append(f"**{speaker.upper()} 전문가{validation_status}**\n\n")
        elif speaker == "fact_checker":
            output.append("**Fact Checker**\n\n")
        elif speaker == "moderator":
            if "합의" in content or "도달" in content:
                output.append(f"*{content.strip()}*\n\n")
            continue
        if speaker in ["contact", "deform", "necking"]:
            content_lines = content.split('\n')
            if len(content_lines) > config.CONTENT_LINES_TRUNCATE_THRESHOLD:
                first_part = "\n".join(content_lines[:3])
                last_part = "\n".join([line for line in content_lines[-2:] if line.strip()])
                output.append(f"{first_part}\n\n*... (중략) ...*\n\n{last_part}\n")
            else:
                output.append(f"{content}\n")
        elif speaker == "fact_checker":
            if "통과" in content or "일관성" in content:
                output.append(f"*{content[:100]}...*\n")
        output.append("")
    return "\n".join(output)


def validate_image_path(image_path: str) -> tuple[bool, Optional[str]]:
    """이미지 파일 경로 유효성 검사
    
    Args:
        image_path: 검증할 이미지 파일 경로
        
    Returns:
        (유효성 여부, 오류 메시지) 튜플
        - 유효한 경우: (True, None)
        - 유효하지 않은 경우: (False, 오류 메시지)
    """
    image_file = Path(image_path)
    
    # 파일 존재 확인
    if not image_file.exists():
        # data 폴더에서도 확인
        try:
            data_dir = find_data_directory()
            alt_path = Path(data_dir) / image_file.name
            if alt_path.exists():
                return True, None
        except (OSError, ValueError):
            pass
        return False, f"이미지 파일을 찾을 수 없습니다: {image_path}"
    
    # 파일 크기 검증
    try:
        MAX_IMAGE_SIZE = config.MAX_IMAGE_SIZE_MB * 1024 * 1024
        file_size = image_file.stat().st_size
        if file_size > MAX_IMAGE_SIZE:
            return False, (
                f"이미지 파일이 너무 큽니다 ({file_size / 1024 / 1024:.1f}MB). "
                f"최대 {config.MAX_IMAGE_SIZE_MB}MB까지 지원합니다."
            )
    except OSError as e:
        return False, f"파일 크기 확인 실패: {e}"
    
    # 파일 확장자 검증
    ext = image_file.suffix.lower()
    valid_extensions = ['.png', '.jpg', '.jpeg', '.heic']
    if ext not in valid_extensions:
        return False, f"지원하지 않는 이미지 형식입니다: {ext}"
    
    return True, None


def validate_result_structure(result: Any) -> tuple[bool, Optional[str]]:
    """분석 결과 딕셔너리 구조 검증
    
    Args:
        result: 검증할 결과 객체
        
    Returns:
        (유효성 여부, 오류 메시지) 튜플
        - 유효한 경우: (True, None)
        - 유효하지 않은 경우: (False, 오류 메시지)
    """
    if result is None:
        return False, "분석 결과를 받지 못했습니다."
    
    if not isinstance(result, dict):
        return False, f"예상치 못한 결과 타입: {type(result)}"
    
    # 필수 키 확인
    required_keys = ["final_verdict", "expert_reports", "arbiter_debate_messages", "errors"]
    for key in required_keys:
        if key not in result:
            return False, f"필수 키가 누락되었습니다: {key}"
    
    # 타입 검증
    if not isinstance(result.get("expert_reports"), list):
        return False, "expert_reports가 리스트가 아닙니다."
    
    if not isinstance(result.get("arbiter_debate_messages"), list):
        return False, "arbiter_debate_messages가 리스트가 아닙니다."
    
    if not isinstance(result.get("errors"), list):
        return False, "errors가 리스트가 아닙니다."
    
    return True, None


def select_image_file() -> Optional[str]:
    """data 디렉토리에서 이미지 파일 목록을 보여주고 사용자가 선택할 수 있게 합니다.
    
    Returns:
        선택된 이미지 파일 경로 또는 None (취소/오류 시)
    """
    try:
        data_dir = find_data_directory()
    except ValueError as e:
        logger.error(f"데이터 디렉토리 찾기 실패: {e}")
        print(f"오류: {e}")
        return None
    except Exception as e:
        logger.exception(f"예상치 못한 오류 발생: {e}")
        print(f"오류: {e}")
        return None
    
    try:
        image_extensions = config.IMAGE_EXTENSIONS
        image_files = []
        for ext in image_extensions:
            try:
                image_files.extend(Path(data_dir).glob(ext))
            except OSError as e:
                logger.warning(f"이미지 파일 검색 중 오류 (확장자: {ext}): {e}")
                continue
        
        image_files = sorted(set(image_files))
        
        if not image_files:
            logger.warning(f"이미지 파일 없음: {data_dir}")
            print(f"오류: {data_dir} 디렉토리에 이미지 파일이 없습니다.")
            return None
        
        print("\n" + "=" * 60)
        print("사용 가능한 이미지 파일:")
        print("=" * 60)
        for idx, img_file in enumerate(image_files, 1):
            try:
                file_size = img_file.stat().st_size / 1024  # KB
                print(f"  [{idx}] {img_file.name} ({file_size:.1f} KB)")
            except OSError as e:
                logger.warning(f"파일 정보 읽기 실패: {img_file.name}, 오류: {e}")
                print(f"  [{idx}] {img_file.name} (크기 확인 불가)")
        print("=" * 60)
        
        while True:
            try:
                choice = input(f"\n이미지 번호를 선택하세요 (1-{len(image_files)}): ").strip()
                
                if choice.lower() in ['q', 'quit']:
                    logger.info("사용자가 선택 취소")
                    print("실행을 취소했습니다.")
                    return None
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(image_files):
                    selected_file = image_files[choice_num - 1]
                    logger.info(f"이미지 선택됨: {selected_file.name}")
                    print(f"\n선택된 이미지: {selected_file.name}")
                    return str(selected_file)
                else:
                    print(f"오류: 1부터 {len(image_files)} 사이의 숫자를 입력해주세요.")
            except ValueError:
                print("오류: 숫자를 입력해주세요. (종료하려면 'q' 입력)")
            except KeyboardInterrupt:
                logger.info("사용자가 키보드 인터럽트로 취소")
                print("\n\n실행을 취소했습니다.")
                return None
            except Exception as e:
                logger.exception(f"이미지 선택 중 예상치 못한 오류: {e}")
                print(f"오류: 예상치 못한 문제가 발생했습니다. 다시 시도해주세요.")
    except Exception as e:
        logger.exception(f"이미지 파일 목록 생성 중 오류: {e}")
        print(f"오류: 이미지 파일 목록을 생성하는 중 오류가 발생했습니다: {e}")
        return None


def create_payload_from_image(image_path: str) -> List[Dict[str, Any]]:
    """
    이미지 경로에서 직접 Gemini Vertex AI 형식의 payload 생성
    
    Args:
        image_path: 이미지 파일 경로
        
    Returns:
        Gemini Vertex AI 형식의 payload 리스트
        
    Raises:
        FileNotFoundError: 이미지 파일을 찾을 수 없을 때
        PermissionError: 파일 읽기 권한이 없을 때
        ValueError: 이미지 처리 중 오류 발생 시
    """
    # 이미지 파일 유효성 검사
    is_valid, error_msg = validate_image_path(image_path)
    if not is_valid:
        if "찾을 수 없습니다" in error_msg:
            raise FileNotFoundError(error_msg)
        else:
            raise ValueError(error_msg)
    
    image_file = Path(image_path)
    
    # 이미지 데이터 읽기
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
    except PermissionError as exc:
        logger.error(f"파일 읽기 권한 없음: {image_path}")
        raise PermissionError(f"이미지 파일 읽기 권한이 없습니다: {image_path}") from exc
    except OSError as e:
        logger.error(f"파일 읽기 오류: {image_path}, 오류: {e}")
        raise ValueError(f"이미지 파일 읽기 중 오류 발생: {e}") from e
    except Exception as e:
        logger.exception(f"예상치 못한 오류 발생: {image_path}, 오류: {e}")
        raise ValueError(f"이미지 파일 처리 중 예상치 못한 오류 발생: {e}") from e
    
    # MIME 타입 결정
    ext = image_file.suffix.lower()
    if ext == '.png':
        mime_type = 'image/png'
    elif ext in ['.jpg', '.jpeg']:
        mime_type = 'image/jpeg'
    elif ext in ['.heic']:
        mime_type = 'image/heic'
    else:
        # 기본값으로 jpeg 사용
        mime_type = 'image/jpeg'
    
    try:
        image_base64 = base64.b64encode(image_data).decode('utf-8')
    except Exception as e:
        logger.error(f"base64 인코딩 실패: {image_path}, 오류: {e}")
        raise ValueError(f"이미지 base64 인코딩 중 오류 발생: {e}") from e
    
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


def _get_expert_filename(report: str) -> str:
    """전문가 리포트에서 파일명 추출
    
    Args:
        report: 전문가 리포트 텍스트
        
    Returns:
        파일명 문자열
    """
    if "[Contact 전문가" in report:
        return "Contact_Expert_Report.txt"
    elif "[Deform 전문가" in report:
        return "Deform_Expert_Report.txt"
    elif "[Necking 전문가" in report:
        return "Necking_Expert_Report.txt"
    elif "[DielectricAge 전문가" in report:
        return "Dielectric_Expert_Report.txt"
    elif "[Mechanical 전문가" in report:
        return "Mechanical_Expert_Report.txt"
    elif "[StrandFracture 전문가" in report:
        return "StrandFracture_Expert_Report.txt"
    elif "[Tracking 전문가" in report:
        return "Tracking_Expert_Report.txt"
    return "Unknown_Expert_Report.txt"


def _save_expert_reports(expert_reports: List[str], output_dir: Path) -> None:
    """각 전문가별 별도 리포트 파일 저장
    
    Args:
        expert_reports: 전문가 리포트 리스트
        output_dir: 출력 디렉토리 경로
    """
    if not expert_reports:
        return
    
    logger.info("개별 리포트 저장 시작")
    for report in expert_reports:
        filename = _get_expert_filename(report)
        expert_file = output_dir / filename
        try:
            expert_file.parent.mkdir(parents=True, exist_ok=True)
            with open(expert_file, 'w', encoding='utf-8') as f:
                f.write(_sanitize_report_for_display(report))
            logger.debug(f"전문가 리포트 저장 완료: {filename}")
            print(f"  - {filename} 저장 완료")
        except (OSError, UnicodeEncodeError) as e:
            logger.error(f"전문가 리포트 저장 실패: {filename}, 오류: {e}")
            print(f"  - {filename} 저장 실패: {e}")


def _save_arbiter_report(final_verdict: str, output_dir: Path) -> None:
    """Arbiter(최종 결론) 리포트 별도 저장
    
    Args:
        final_verdict: 최종 판정 텍스트
        output_dir: 출력 디렉토리 경로
    """
    if not final_verdict:
        return
    
    arbiter_file = output_dir / "Arbiter_Report.txt"
    try:
        arbiter_file.parent.mkdir(parents=True, exist_ok=True)
        with open(arbiter_file, 'w', encoding='utf-8') as f:
            f.write("[Arbiter (Chief Investigator) Report]\n\n")
            f.write(final_verdict)
        logger.debug("Arbiter 리포트 저장 완료")
        print("  - Arbiter_Report.txt 저장 완료")
    except (OSError, UnicodeEncodeError) as e:
        logger.error(f"Arbiter 리포트 저장 실패: {e}")
        print(f"  - Arbiter_Report.txt 저장 실패: {e}")


def _save_investigation_result(
    final_verdict: str,
    expert_reports: List[str],
    arbiter_debate_messages: List[Dict[str, Any]],
    errors: List[str],
    input_image_path: str,
    output_file: Path,
    final_verdict_structured: Optional[Any] = None  # FinalVerdictResult (구조화된 데이터)
) -> None:
    """통합 분석 결과 파일 저장"""
    timestamp_str = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # 리포트 생성: LLM 기반 또는 정규식 기반
    if config.USE_LLM_REPORT_GENERATOR:
        llm_report = generate_report_llm(
            final_verdict=final_verdict,
            expert_reports=expert_reports or [],
            arbiter_debate_messages=arbiter_debate_messages or [],
            input_image_path=input_image_path,
            timestamp=timestamp_str,
        )
        if llm_report:
            audit_section = _format_audit_trail_section(arbiter_debate_messages or [])
            formatted_result = llm_report + ("\n\n" + audit_section if audit_section else "")
            logger.info("LLM 기반 리포트 생성 완료")
            print("  [리포트] LLM 기반 생성 완료")
        else:
            formatted_result = format_investigation_result(
                final_verdict=final_verdict,
                expert_reports=expert_reports or [],
                arbiter_debate_messages=arbiter_debate_messages or [],
                input_image_path=input_image_path,
                timestamp=timestamp_str,
                final_verdict_structured=final_verdict_structured,
            )
            logger.warning("LLM 리포트 생성 실패, 구조화된 데이터 또는 정규식 Fallback 사용")
            print("  [리포트] LLM 실패 → 구조화된 데이터 또는 정규식 Fallback 사용")
    else:
        formatted_result = format_investigation_result(
            final_verdict=final_verdict,
            expert_reports=expert_reports or [],
            arbiter_debate_messages=arbiter_debate_messages or [],
            input_image_path=input_image_path,
            timestamp=timestamp_str,
            final_verdict_structured=final_verdict_structured,
        )
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(formatted_result)
        
        # 추가 정보 (원본 데이터 보존용, Raw 에러 정제)
        f.write("\n\n---\n\n")
        f.write("## 상세 분석 내용 (원본 데이터)\n\n")
        f.write("### 최종 판정 상세\n")
        f.write(_sanitize_report_for_display(final_verdict))
        f.write("\n\n")
        
        # 전문가 상세 리포트 (Raw 에러 정제)
        if expert_reports:
            f.write("### 전문가 상세 리포트\n\n")
            for i, report in enumerate(expert_reports, 1):
                f.write(f"#### Expert Report {i}\n\n")
                f.write(_sanitize_report_for_display(report))
                f.write("\n\n")
        
        # 오류 로그 (사용자 노출용 정제)
        if errors:
            f.write("\n---\n\n")
            f.write("## 5. System Errors & Warnings\n\n")
            for err in errors:
                f.write(f"- {_sanitize_user_visible_text(err)}\n")


def run_analysis_pipeline(
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
    logger.info("=" * 60)
    logger.info("화재 조사 멀티 에이전트 시스템 가동")
    logger.info("=" * 60)
    logger.info(f"분석 대상: {Path(input_image_path).name}")
    print("\n" + "=" * 60)
    print("화재 조사 멀티 에이전트 시스템 가동")
    print("=" * 60)
    print(f"분석 대상: {Path(input_image_path).name}")
    
    # 1. Payload 생성
    try:
        logger.info("[1단계] 입력 데이터 처리 시작")
        print("\n[1단계] 입력 데이터 처리 중...")
        payload = create_payload_from_image(input_image_path)
        logger.info(f"Payload 생성 완료 ({len(payload)} parts)")
        print(f"✓ Payload 생성 완료 ({len(payload)} parts)")
    except FileNotFoundError as e:
        logger.error(f"파일을 찾을 수 없음: {e}")
        print(f"❌ 오류: {e}")
        return None
    except PermissionError as e:
        logger.error(f"파일 읽기 권한 없음: {e}")
        print(f"❌ 오류: {e}")
        return None
    except (UnicodeDecodeError, base64.binascii.Error) as e:
        logger.error(f"데이터 인코딩/디코딩 오류: {e}", exc_info=True)
        print(f"❌ 오류: 데이터 인코딩/디코딩 오류 발생 - {e}")
        traceback.print_exc()
        return None
    except OSError as e:
        logger.error(f"파일 시스템 오류: {e}", exc_info=True)
        print(f"❌ 오류: 파일 시스템 오류 발생 - {e}")
        traceback.print_exc()
        return None
    except ValueError as e:
        logger.error(f"값 오류: {e}")
        print(f"❌ 오류: {e}")
        return None

    # 2. 분석 실행
    logger.info("[2단계] 멀티 에이전트 병렬 분석 시작")
    print("\n[2단계] 멀티 에이전트 병렬 분석 시작")
    print("  - Hotspot Detector가 관심 영역을 탐지합니다.")
    print("  - 3인의 전문가 에이전트가 병렬로 동시에 분석합니다. (Fan-Out)")
    print("    (Contact, Deform, Necking - Map-Reduce Pattern)")
    print("  - 각 전문가는 독립적인 서브그래프로 동작하며 Map-Reduce 패턴을 사용합니다.")
    print("  - 모든 분석 결과를 수집합니다. (Fan-In)")
    print("  - 수석 조사관(Arbiter)이 종합하여 최종 결론을 도출합니다.")
    
    try:
        start_time = time.time()
        result = analyze_fire_evidence(payload)
        duration = time.time() - start_time
        logger.info(f"분석 완료 (소요 시간: {duration:.1f}초)")
        print(f"✓ 분석 완료 (소요 시간: {duration:.1f}초)")
    except Exception as e:
        logger.exception(f"분석 실행 중 예외 발생: {e}")
        print(f"❌ 오류: 분석 실행 중 예외 발생 - {e}")
        traceback.print_exc()
        # 에러 정보를 포함한 딕셔너리 반환
        error_result = {
            "final_verdict": "분석 실패",
            "expert_reports": [],
            "arbiter_debate_messages": [],
            "errors": [f"분석 실행 중 예외 발생: {str(e)}"]
        }
        return error_result

    # 3. 결과 검증 및 처리
    is_valid, error_msg = validate_result_structure(result)
    if not is_valid:
        logger.error(f"결과 구조 검증 실패: {error_msg}")
        print(f"❌ 오류: {error_msg}")
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
        print(f"\n⚠️ 분석 중 {len(errors)}개의 경고가 발생했습니다:")
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
        
        _save_investigation_result(
            final_verdict=final_verdict,
            expert_reports=expert_reports,
            arbiter_debate_messages=arbiter_debate_messages,
            errors=errors,
            input_image_path=input_image_path,
            output_file=output_file,
            final_verdict_structured=final_verdict_structured
        )
        logger.info(f"전체 결과 저장 완료: {output_file}")
        print(f"\n✅ 전체 결과가 저장되었습니다: {output_file}")
        
        # 개별 리포트 저장
        _save_expert_reports(expert_reports, output_dir)
        _save_arbiter_report(final_verdict, output_dir)
        
    except (OSError, UnicodeEncodeError) as e:
        logger.error(f"결과 파일 저장 실패: {e}", exc_info=True)
        print(f"❌ 결과 파일 저장 실패: {e}")
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
                print("❌ 오류: 테스트용 이미지를 찾을 수 없습니다.")
                sys.exit(1)
                
            input_image_path = str(test_image_path)
            logger.info(f"테스트 이미지 선택됨: {test_image_path.name}")
            print(f"테스트 이미지 선택됨: {test_image_path.name}")
            
        except (OSError, ValueError) as e:
            logger.error(f"테스트 모드 오류: {e}")
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
    # 경로 검증
    is_valid, error_msg = validate_image_path(input_image_path)
    if not is_valid:
        # data 폴더에서 재시도
        try:
            data_dir = find_data_directory()
            alt_path = Path(data_dir) / Path(input_image_path).name
            if alt_path.exists():
                input_image_path = str(alt_path)
                image_path = alt_path
                logger.info(f"알림: 이미지를 data 폴더에서 찾았습니다: {alt_path}")
                print(f"알림: 이미지를 data 폴더에서 찾았습니다: {alt_path}")
            else:
                logger.error(f"이미지 파일 검증 실패: {error_msg}")
                print(f"❌ 오류: {error_msg}")
                sys.exit(1)
        except (OSError, ValueError) as e:
            logger.error(f"이미지 파일 찾기 실패: {input_image_path}, 상세: {e}")
            print(f"❌ 오류: 이미지 파일을 찾을 수 없습니다: {input_image_path}")
            print(f"   상세: {e}")
            sys.exit(1)
    else:
        image_path = Path(input_image_path)

    # 출력 디렉토리 준비
    input_filename = image_path.stem
    output_base_dir = Path(config.OUTPUT_DIR)
    output_dir = output_base_dir / input_filename
    output_dir.mkdir(parents=True, exist_ok=True)

    # 파이프라인 실행
    run_analysis_pipeline(input_image_path, output_dir, args.query)


if __name__ == "__main__":
    main()
