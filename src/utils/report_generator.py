"""
LLM 기반 화재증거물 분석 보고서 생성기
모든 분석 데이터를 LLM에 전달하여 단일 통합 Markdown 보고서로 변환합니다.
(Inverted Pyramid: Executive Summary → Body → Appendix)
"""
from pathlib import Path
from typing import List, Optional

from src.prompts.report_generator_prompts import REPORT_SYSTEM_PROMPT
from src.tools.experts.expert_utils import call_gemini_text


def _build_raw_log(
    final_verdict: str,
    expert_reports: List[str],
    arbiter_debate_messages: List[dict],
    image_name: str,
    timestamp: str,
    errors: Optional[List[str]] = None,
) -> str:
    """분석 결과 전체를 LLM 입력용 Raw Log 문자열로 구성합니다."""
    lines = [
        "[System Log]",
        f"Date: {timestamp}",
        f"Image: {image_name}",
        "",
        "[Arbiter Final Verdict]",
        final_verdict or "(없음)",
        "",
        "[Expert Reports]",
    ]
    labels = ["Contact", "Deform", "Necking"]
    for i, report in enumerate(expert_reports or []):
        label = labels[i] if i < len(labels) else f"Expert_{i+1}"
        lines.append(f"--- {label} ---")
        lines.append(report or "(없음)")
        lines.append("")

    lines.append("[Debate Messages]")
    if arbiter_debate_messages:
        for msg in arbiter_debate_messages:
            speaker = msg.get("speaker", "unknown")
            content = (msg.get("content", "") or "")
            stage = msg.get("stage", "")
            round_num = msg.get("round_num", 0)
            validated = msg.get("validated", None)
            val_str = " ✓" if validated else " ✗" if validated is False else ""
            lines.append(f"[Round {round_num} / {stage} / {speaker}{val_str}]")
            lines.append(content)
            lines.append("")
    else:
        lines.append("(토론 기록 없음)")
        lines.append("")

    if errors:
        lines.append("[System Errors]")
        for err in errors:
            lines.append(f"- {err}")
        lines.append("")

    return "\n".join(lines)


def generate_report_llm(
    final_verdict: str,
    expert_reports: List[str],
    arbiter_debate_messages: List[dict],
    input_image_path: str,
    timestamp: str,
    errors: Optional[List[str]] = None,
) -> Optional[str]:
    """
    모든 분석 데이터를 LLM에 전달하여 단일 통합 Markdown 보고서를 생성합니다.

    Args:
        final_verdict: Arbiter 최종 판정 원문
        expert_reports: 전문가 리포트 원문 리스트 (Contact, Deform, Necking)
        arbiter_debate_messages: 토론 메시지 리스트 (전체)
        input_image_path: 입력 이미지 경로 (파일명 추출용)
        timestamp: 분석 일시 문자열
        errors: 시스템 경고/에러 리스트 (선택)

    Returns:
        생성된 Markdown 보고서 문자열. 실패 시 None.
    """
    image_name = Path(input_image_path).name
    raw_log = _build_raw_log(
        final_verdict=final_verdict,
        expert_reports=expert_reports or [],
        arbiter_debate_messages=arbiter_debate_messages or [],
        image_name=image_name,
        timestamp=timestamp,
        errors=errors,
    )
    user_prompt = f"""위 [System Prompt]의 지침에 따라, 아래 [Raw Log]를 전문 Markdown 보고서로 변환해주세요.
시스템 에러나 디버깅 메시지는 절대 그대로 출력하지 말고 정제된 표현으로 대체하세요.

[Raw Log]
---
{raw_log}
---
"""
    full_prompt = f"""{REPORT_SYSTEM_PROMPT}

---

{user_prompt}"""
    try:
        response_text, _ = call_gemini_text(
            prompt=full_prompt,
            step_name="report_generator",
            temperature=0.3,
        )
        if not response_text or response_text.startswith("Error:"):
            return None
        # 불필요한 앞뒤 --- 제거 (프롬프트 잔여물)
        return response_text.strip()
    except Exception:
        return None
