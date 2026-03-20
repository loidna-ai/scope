"""
LLM 기반 화재증거물 분석 보고서 생성기
모든 분석 데이터를 LLM에 전달하여 단일 통합 Markdown 보고서로 변환합니다.
(Inverted Pyramid: Executive Summary → Body → Appendix)
"""
from pathlib import Path
from typing import Any, List, Optional

import asyncio
import os

import config
from src.prompts.report_generator_prompts import REPORT_SYSTEM_PROMPT
from src.tools.experts.expert_utils import call_gemini_text
from src.utils import async_retry_with_backoff


def _detect_expert_label(report: str, fallback_index: int) -> str:
    """전문가 리포트 내용에서 전문가 유형을 식별합니다. (io_utils._get_expert_filename과 동일 패턴)"""
    if not report:
        return f"Expert_{fallback_index + 1}"
    r = report[:500]  # 앞부분만 검사
    if "[Contact 전문가" in r or "## Contact 전문가" in r:
        return "Contact"
    if "[Aging 전문가" in r or "## Aging 전문가" in r:
        return "Aging"
    if "[Deform 전문가" in r or "## Deform 전문가" in r:
        return "Deform"
    if "[Necking 전문가" in r or "## Necking 전문가" in r:
        return "Necking"
    if "[Tracking 전문가" in r or "## Tracking 전문가" in r:
        return "Tracking"
    return f"Expert_{fallback_index + 1}"


def _build_raw_log(
    final_verdict: str,
    expert_reports: List[str],
    arbiter_debate_messages: List[dict],
    image_name: str,
    timestamp: str,
    errors: Optional[List[str]] = None,
    final_verdict_structured: Optional[Any] = None,
) -> str:
    """분석 결과 전체를 LLM 입력용 Raw Log 문자열로 구성합니다."""
    lines = [
        "[System Log]",
        f"Date: {timestamp}",
        f"Image: {image_name}",
        "",
    ]

    # 구조화된 데이터가 있으면 우선 포함 (LLM이 더 정확한 리포트 생성에 활용)
    if final_verdict_structured:
        try:
            if hasattr(final_verdict_structured, "verdict"):
                v = final_verdict_structured
                lines.append("[Structured Verdict Data]")
                lines.append(f"Verdict: {v.verdict}")
                lines.append(f"Confidence: {v.confidence_score:.1f}% ({v.confidence_level})")
                lines.append(f"Reasoning: {v.reasoning_summary or '(없음)'}")
                if getattr(v, "key_evidence", None):
                    lines.append("Key Evidence:")
                    for ev in v.key_evidence[:5]:
                        lines.append(f"  - {ev}")
                if getattr(v, "zones", None) and v.zones:
                    lines.append("Zones:")
                    for z in v.zones:
                        lines.append(f"  - {z.description}: {z.observation}")
                if getattr(v, "recommendations", None) and v.recommendations:
                    lines.append("Recommendations:")
                    for r in v.recommendations:
                        lines.append(f"  - {r}")
                lines.append("")
            elif isinstance(final_verdict_structured, dict):
                v = final_verdict_structured
                lines.append("[Structured Verdict Data]")
                lines.append(f"Verdict: {v.get('verdict', '(없음)')}")
                lines.append(f"Confidence: {v.get('confidence_score', 0):.1f}%")
                if v.get("key_evidence"):
                    lines.append("Key Evidence:")
                    for ev in (v["key_evidence"] or [])[:5]:
                        lines.append(f"  - {ev}")
                if v.get("zones"):
                    lines.append("Zones:")
                    for z in v["zones"]:
                        desc = z.get("description", "") if isinstance(z, dict) else getattr(z, "description", "")
                        obs = z.get("observation", "") if isinstance(z, dict) else getattr(z, "observation", "")
                        lines.append(f"  - {desc}: {obs}")
                if v.get("recommendations"):
                    lines.append("Recommendations:")
                    for r in v["recommendations"]:
                        lines.append(f"  - {r}")
                lines.append("")
        except Exception:
            pass

    lines.extend([
        "[Arbiter Final Verdict]",
        final_verdict or "(없음)",
        "",
        "[Expert Reports]",
    ])
    # 콘텐츠 기반 라벨링: 전문가 리포트 순서가 병렬 실행으로 비결정적이므로, 리포트 내용으로 전문가 유형 식별
    for i, report in enumerate(expert_reports or []):
        label = _detect_expert_label(report, i)
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
    final_verdict_structured: Optional[Any] = None,
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
        final_verdict_structured: 구조화된 최종 판정 데이터 (FinalVerdictResult 또는 dict)

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
        final_verdict_structured=final_verdict_structured,
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
        # Rate Limiter 적용을 위해 async_retry_with_backoff 사용
        async def _call_report_api():
            def run_sync_call():
                return call_gemini_text(
                    prompt=full_prompt,
                    step_name="report_generator",
                    temperature=0.3,
                    model_name=os.environ.get("GEMINI_PRO_MODEL_NAME", config.GEMINI_PRO_MODEL_NAME),
                )
            return await async_retry_with_backoff(
                lambda: asyncio.to_thread(run_sync_call),
                max_retries=5,
                context_name="report_generator",
                model_type="pro",
            )
        
        # 동기 함수에서 비동기 함수 호출
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 이미 실행 중인 루프가 있으면 새 태스크 생성
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _call_report_api())
                    response_text, _ = future.result()
            else:
                response_text, _ = asyncio.run(_call_report_api())
        except RuntimeError:
            # 이벤트 루프가 없으면 새로 생성
            response_text, _ = asyncio.run(_call_report_api())
        
        if not response_text or response_text.startswith("Error:"):
            return None
        # 불필요한 앞뒤 --- 제거 (프롬프트 잔여물)
        return response_text.strip()
    except Exception:
        return None
