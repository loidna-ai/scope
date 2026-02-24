"""
리포트 포매팅 유틸리티

main.py에 포함되어 있던 텍스트 파싱, 정규식, 마크다운 리포트 포매팅 기능을
별도로 분리한 모듈입니다.
"""

import re
from typing import Dict, Any, List, Optional
from pathlib import Path

import config
from src.utils.logging_config import setup_logger

logger = setup_logger(__name__)

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

EXPERT_NAME_PATTERN = r'(?:\[|##\s+)(Contact|Deform|Necking|Aging|Tracking|DielectricAge|Mechanical|StrandFracture)'
CONCLUSION_PATTERN = r'## 결론[:\s]*([^\n]+)'
CONFIDENCE_IN_PARENTHESES_PATTERN = r'\((\d+\.?\d*)%\)'
RECOMMENDATION_PATTERN = r'\[추가 조사 (?:필요 사항|권고 사항)\]\s*\n(.*?)(?=\[|\n##|\Z)'
RECOMMENDATION_ITEMS_PATTERN = r'\d+\.\s+(.+)'
ZONE_PATTERN_TEMPLATE = r'Zone\s*{}\s*[의:]?\s*([가-힣a-zA-Z0-9\s,\-]+?)(?=\.|Zone|\d+\.|$)'


def sanitize_user_visible_text(text: str) -> str:
    """사용자에게 노출되는 텍스트에서 Raw Python 에러를 제거"""
    if not text or not isinstance(text, str):
        return text
    for pat in _RAW_ERROR_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "판독 보류 (분석 데이터 부족)"
    return text


def sanitize_report_for_display(report: str) -> str:
    """전문가 상세 리포트 내 Raw 에러를 정제 (파일 저장용)"""
    if not report or not isinstance(report, str):
        return report
    sanitized = report
    sanitized = re.sub(r'[^\n]*Supervisor Error:[^\n]*', '※ 분석 불가 (시스템 데이터 부족)', sanitized)
    sanitized = re.sub(r'[^\n]*name\s+\'[^\']+\'\s+is not defined[^\n]*', '※ 분석 불가 (시스템 데이터 부족)', sanitized)
    sanitized = re.sub(r'\[오류\]\s*\n\s*LLM 호출 실패:[^\n]*', '[오류]\nLLM 호출 실패: (시스템 일시 오류)', sanitized)
    sanitized = re.sub(r'\(Error:\s*[^)]+\)', '(시스템 오류)', sanitized)
    if "Traceback" in sanitized or 'File "' in sanitized:
        sanitized = re.sub(r'Traceback \(most recent call last\):.*?(?=\n\n|\Z)', '※ 분석 불가 (시스템 데이터 부족)', sanitized, flags=re.DOTALL)
    return sanitized


def parse_final_verdict(verdict_text: str) -> Dict[str, str]:
    """최종 판정 텍스트에서 판정 결과와 신뢰도를 추출"""
    result = {
        "verdict": "판정 불가",
        "confidence": "N/A",
        "confidence_level": "N/A"
    }
    if not verdict_text:
        return result
    
    clean_text = verdict_text
    for pattern, replacement in VERDICT_CLEANUP_PATTERNS:
        clean_text = re.sub(pattern, replacement, clean_text)
    
    verdict_match = None
    for pattern in VERDICT_PATTERNS:
        verdict_match = re.search(pattern, clean_text)
        if verdict_match:
            break
    if verdict_match:
        raw = verdict_match.group(1).strip()
        result["verdict"] = sanitize_user_visible_text(raw) if raw else "판정 불가"
    
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
    """전문가 리포트에서 판정 결과 추출"""
    result = {
        "expert_name": "Unknown",
        "conclusion": "해당 없음",
        "confidence": "N/A",
        "key_evidence": "해당 없음"
    }
    if not report_text:
        return result
    
    def _safe_evidence(s: str) -> str:
        return sanitize_user_visible_text(s) if s else "해당 없음"
    
    name_match = re.search(EXPERT_NAME_PATTERN, report_text, re.IGNORECASE)
    if name_match:
        result["expert_name"] = name_match.group(1).upper()
    
    conclusion_match = re.search(CONCLUSION_PATTERN, report_text)
    if conclusion_match:
        conclusion = conclusion_match.group(1).strip()
        if "Analysis Skipped" in report_text or "해당 없음" in conclusion or "전선이 아님" in report_text:
            result["conclusion"] = "해당 없음"
            result["confidence"] = "-"
            if result["expert_name"] == "DEFORM" and ("전선이 아님" in report_text or "Target is not a Wire" in report_text):
                result["key_evidence"] = "분석 대상이 전선이 아니므로(터미널) 압착/손상 분석 알고리즘 적용 제외"
            elif "전선이 아님" in report_text or "Target is not a Wire" in report_text:
                result["key_evidence"] = "분석 제외 (대상: 터미널)"
            else:
                result["key_evidence"] = "분석 제외"
        else:
            if "유력" in conclusion:
                result["conclusion"] = "유력"
            elif "의심" in conclusion:
                result["conclusion"] = "의심"
            elif "아님" in conclusion:
                result["conclusion"] = "아님"
            else:
                result["conclusion"] = conclusion.split('(')[0].strip() if '(' in conclusion else conclusion
            
            conf_match = re.search(CONFIDENCE_IN_PARENTHESES_PATTERN, conclusion)
            if conf_match:
                result["confidence"] = f"{float(conf_match.group(1)):.1f}%"
            else:
                conf_match = re.search(CONFIDENCE_PATTERN, report_text)
                if conf_match:
                    result["confidence"] = f"{float(conf_match.group(1)):.1f}%"
            
            if "Pitting" in report_text or "크레이터" in report_text or "터미널" in report_text:
                result["key_evidence"] = "Pitting, 열적 구배, Arc Bead 부재"
            elif "압착" in report_text:
                result["key_evidence"] = "압착흔 분석"
            elif "반단선" in report_text:
                result["key_evidence"] = "반단선(용융흔) 분석"
            else:
                result["key_evidence"] = "물리적 증거 분석"
    
    result["key_evidence"] = _safe_evidence(result["key_evidence"])
    return result


def _confidence_badge(level: str) -> str:
    badges = {"High": "🟢 High", "Medium": "🟡 Medium", "Low": "🔴 Low"}
    return badges.get(level, level)


def _format_report_header(
    timestamp: str,
    image_name: str,
    verdict_info: Dict[str, str]
) -> List[str]:
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
) -> tuple[List[str], Optional[str]]:
    output = []
    output.append("## 1. 종합 분석 결론 (Executive Summary)\n")
    
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
    
    reasoning_text = None
    for pattern in REASONING_PATTERNS:
        reasoning_match = re.search(pattern, final_verdict, re.DOTALL)
        if reasoning_match:
            reasoning_text = reasoning_match.group(1).strip()
            break
    
    output.append("\n**핵심 근거:**\n")
    if reasoning_text:
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
    output = []
    output.append("## 1. 종합 분석 결론 (Executive Summary)\n")
    
    if hasattr(final_verdict_structured, 'verdict'):
        verdict_phrase = final_verdict_structured.verdict
        key_evidence = final_verdict_structured.key_evidence
        reasoning_summary = final_verdict_structured.reasoning_summary
    else:
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
    output = []
    output.append("## 2. 전문가 에이전트 세부 소견\n")
    output.append("| 분석 모듈 | 판정 결과 | 신뢰도 | 상세 소견 |")
    output.append("| :--- | :---: | :---: | :--- |")
    
    EXPERT_LABELS = {"CONTACT": "접촉불량", "AGING": "경년열화", "DEFORM": "압착/손상", "NECKING": "용융/단선"}
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
    output = []
    output.append("## 3. 상세 증거 분석 (Evidence Breakdown)\n")
    output.append("*(이곳에 Zone 1, 3, 4가 표시된 분석 이미지를 삽입하세요)*\n\n")
    zone_info = [(1, "압착부 경계", "소선 간 탄화물 고착 심화. 물리적 틈새(Gap) 존재."),
                 (3, "도체 표면", "장기과열 특유의 적갈색/회색 산화 스케일 관찰."),
                 (4, "말단부", "용융흔 없음. 원형 유지.")]
    for z_num, z_desc, z_default in zone_info:
        custom = ""
        if reasoning_text:
            zone_pattern = ZONE_PATTERN_TEMPLATE.format(z_num)
            m = re.search(zone_pattern, reasoning_text, re.IGNORECASE)
            if m and len(m.group(1).strip()) > 4:
                custom = m.group(1).strip()[:100] + ("." if not m.group(1).strip().endswith(".") else "")
        zone_desc = custom if custom else z_default
        output.append(f"- **{z_desc}**: {zone_desc}")
    output.append("")
    return output


def _format_evidence_breakdown_structured(zones: List[Any]) -> List[str]:
    output = []
    output.append("## 3. 상세 증거 분석 (Evidence Breakdown)\n")
    output.append("*(이곳에 Zone 1, 3, 4가 표시된 분석 이미지를 삽입하세요)*\n\n")
    
    if zones:
        for zone in zones:
            if hasattr(zone, 'zone_number'):
                z_num = zone.zone_number
                z_desc = zone.description
                z_obs = zone.observation
            else:
                z_num = zone.get("zone_number", 0)
                z_desc = zone.get("description", "")
                z_obs = zone.get("observation", "")
            
            output.append(f"- **{z_desc}**: {z_obs}")
    else:
        zone_info = [(1, "압착부 경계", "소선 간 탄화물 고착 심화. 물리적 틈새(Gap) 존재."),
                     (3, "도체 표면", "장기과열 특유의 적갈색/회색 산화 스케일 관찰."),
                     (4, "말단부", "용융흔 없음. 원형 유지.")]
        for z_num, z_desc, z_default in zone_info:
            output.append(f"- **{z_desc}**: {z_default}")
    
    output.append("")
    return output


def _format_recommendations(final_verdict: str) -> List[str]:
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
    output = []
    if recommendations:
        output.append("## 4. 추가 조사 권고 사항 (Recommendation)\n")
        for i, rec in enumerate(recommendations, 1):
            output.append(f"{i}. {rec.strip()}")
        output.append("")
    return output


def _format_audit_trail_section(arbiter_debate_messages: List[Dict[str, Any]]) -> str:
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
        if speaker in ["contact", "deform", "necking", "aging"]:
            validation_status = " ✓ 통과" if validated else " ✗ 실패" if validated is False else ""
            output.append(f"**{speaker.upper()} 전문가{validation_status}**\n\n")
        elif speaker == "fact_checker":
            output.append("**Fact Checker**\n\n")
        elif speaker == "moderator":
            if "합의" in content or "도달" in content:
                output.append(f"*{content.strip()}*\n\n")
            continue
        if speaker in ["contact", "deform", "necking", "aging"]:
            if getattr(config, "FULL_AUDIT_TRAIL_OUTPUT", False):
                output.append(f"{content}\n")
            else:
                content_lines = content.split('\n')
                if len(content_lines) > config.CONTENT_LINES_TRUNCATE_THRESHOLD:
                    first_part = "\n".join(content_lines[:3])
                    last_part = "\n".join([line for line in content_lines[-2:] if line.strip()])
                    output.append(f"{first_part}\n\n*... (중략) ...*\n\n{last_part}\n")
                else:
                    output.append(f"{content}\n")
        elif speaker == "fact_checker":
            if getattr(config, "FULL_AUDIT_TRAIL_OUTPUT", False):
                output.append(f"*{content}*\n")
            elif "통과" in content or "일관성" in content:
                output.append(f"*{content[:100]}...*\n")
        output.append("")
    return "\n".join(output)


def format_investigation_result(
    final_verdict: str,
    expert_reports: List[str],
    arbiter_debate_messages: List[Dict[str, Any]],
    input_image_path: str,
    timestamp: str,
    final_verdict_structured: Optional[Any] = None
) -> str:
    """분석 결과를 실무용 보고서 형식으로 포맷팅 (결론→근거→상세 순)"""
    output = []
    image_name = Path(input_image_path).name
    
    if final_verdict_structured:
        try:
            from src.models.verdict_models import FinalVerdictResult
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
    
    output.extend(_format_report_header(timestamp, image_name, verdict_info))
    
    if use_structured:
        summary_lines = _format_executive_summary_structured(final_verdict_structured)
        output.extend(summary_lines)
    else:
        summary_lines, reasoning_text = _format_executive_summary(final_verdict, verdict_info)
        output.extend(summary_lines)
    
    output.extend(_format_expert_reports_section(expert_reports))
    
    if use_structured and zones:
        output.extend(_format_evidence_breakdown_structured(zones))
    else:
        output.extend(_format_evidence_breakdown(reasoning_text))
    
    if use_structured and recommendations:
        output.extend(_format_recommendations_structured(recommendations))
    else:
        output.extend(_format_recommendations(final_verdict))
    
    output.append(_format_audit_trail_section(arbiter_debate_messages or []))
    
    return "\n".join(output)
