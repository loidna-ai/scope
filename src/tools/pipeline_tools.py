"""
파이프라인 도구
기존 파이프라인을 ReAct 에이전트 도구로 래핑합니다.
"""
from typing import List, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from src.state import GraphState
from src.nodes.packaging import to_gemini_vertex_ai_format


class RunPreprocessingPipelineInput(BaseModel):
    """전처리 파이프라인 도구 입력 스키마"""
    image_path: str = Field(description="전처리할 이미지 파일 경로")


class RunPreprocessingPipelineTool(BaseTool):
    """
    기존 전처리 파이프라인을 ReAct 도구로 제공
    
    이미지 전처리 파이프라인을 실행합니다 (load → crop → enhance → filter/metrics → packaging).
    """
    
    name: str = "run_preprocessing_pipeline"
    description: str = (
        "이미지 전처리 파이프라인을 실행합니다. "
        "단계: 이미지 로드 → 크롭 → 향상 → 필터/메트릭스 → 패키징. "
        "입력: 이미지 파일 경로. "
        "출력: 전처리 완료 메시지 및 분석 데이터 요약."
    )
    args_schema: type[BaseModel] = RunPreprocessingPipelineInput
    
    def _run(
        self,
        image_path: str,
        run_manager: Optional[Any] = None,
    ) -> str:
        """
        전처리 파이프라인 실행
        
        Args:
            image_path: 입력 이미지 파일 경로
            run_manager: 실행 매니저 (선택적)
        
        Returns:
            전처리 결과 문자열
        """
        try:
            # 지연 import로 순환 import 방지
            from src.agent import build_graph
            # 그래프 빌드 및 실행
            graph = build_graph()
            
            initial_state: GraphState = {
                "input_image_path": image_path,
                "original_image": None,
                "cropped_image": None,
                "enhanced_image": None,
                "filtered_image": None,
                "binary_mask": None,
                "metrics": None,
                "analysis_data": None,
                "errors": []
            }
            
            result = graph.invoke(initial_state)
            
            # 에러 확인
            errors = result.get("errors", [])
            if errors:
                return f"전처리 중 오류 발생: {', '.join(errors)}"
            
            # 결과 요약
            analysis_data = result.get("analysis_data", {})
            metrics = result.get("metrics", {})
            
            summary = "전처리 완료:\n"
            if metrics:
                summary += f"- 원형도: {metrics.get('circularity', 'N/A')}\n"
                summary += f"- 고형도: {metrics.get('solidity', 'N/A')}\n"
                summary += f"- 면적: {metrics.get('area', 'N/A')} 픽셀\n"
            
            if analysis_data:
                summary += f"- 분석 데이터 생성 완료 (키: {list(analysis_data.keys())})"
            
            return summary
            
        except Exception as e:
            return f"전처리 파이프라인 실행 오류: {str(e)}"
    
    async def _arun(
        self,
        image_path: str,
        run_manager: Optional[Any] = None,
    ) -> str:
        """비동기 실행 (동기 실행으로 위임)"""
        return self._run(image_path, run_manager)


class RunInvestigationPipelineInput(BaseModel):
    """조사 파이프라인 도구 입력 스키마"""
    image_path: str = Field(description="분석할 이미지 파일 경로 (전처리 파이프라인을 먼저 실행한 후 조사 파이프라인 실행)")


class RunInvestigationPipelineTool(BaseTool):
    """
    기존 조사 파이프라인을 ReAct 도구로 제공
    
    화재조사 멀티 에이전트 분석 파이프라인을 실행합니다.
    """
    
    name: str = "run_investigation_pipeline"
    description: str = (
        "화재조사 멀티 에이전트 분석 파이프라인을 실행합니다. "
        "이미지 경로를 받아 전처리 파이프라인을 먼저 실행한 후, "
        "여러 전문가(접촉불량, 유전체, 기계적, 추적, 소선파단)가 병렬로 분석하고 "
        "수석 조사관이 최종 결론을 도출합니다. "
        "입력: image_path (이미지 파일 경로). "
        "출력: 조사 완료 메시지 및 최종 결론 요약."
    )
    args_schema: type[BaseModel] = RunInvestigationPipelineInput
    
    def _run(
        self,
        image_path: str,
        run_manager: Optional[Any] = None,
    ) -> str:
        """
        조사 파이프라인 실행
        
        Args:
            image_path: 분석할 이미지 파일 경로
            run_manager: 실행 매니저 (선택적)
        
        Returns:
            조사 결과 문자열
        """
        try:
            # 지연 import로 순환 import 방지
            from src.agent import build_graph, analyze_fire_evidence
            # 1. 전처리 파이프라인 실행
            graph = build_graph()
            initial_state: GraphState = {
                "input_image_path": image_path,
                "original_image": None,
                "cropped_image": None,
                "enhanced_image": None,
                "filtered_image": None,
                "binary_mask": None,
                "metrics": None,
                "analysis_data": None,
                "errors": []
            }
            preprocessing_result = graph.invoke(initial_state)
            
            # 전처리 에러 확인
            preprocessing_errors = preprocessing_result.get("errors", [])
            if preprocessing_errors:
                return f"전처리 중 오류 발생: {', '.join(preprocessing_errors)}"
            
            analysis_data = preprocessing_result.get("analysis_data")
            if not analysis_data:
                return "전처리 파이프라인에서 analysis_data를 생성하지 못했습니다."
            
            # 2. payload_data 변환
            payload_data = to_gemini_vertex_ai_format(analysis_data)
            
            # 3. 조사 파이프라인 실행
            result = analyze_fire_evidence(payload_data)
            
            # 에러 확인 및 결과 요약
            errors = result.get("errors", [])
            final_verdict = result.get("final_verdict", "분석 실패")
            expert_reports = result.get("expert_reports", [])
            
            # final_verdict가 있으면 조사가 완료된 것으로 간주 (에러가 있어도 최종 결론이 있으면 성공)
            if final_verdict and final_verdict != "분석 실패":
                summary = f"조사 완료:\n"
                summary += f"- 전문가 리포트 수: {len(expert_reports)}\n"
                if errors:
                    summary += f"- 경고: {len(errors)}개의 오류가 발생했지만 최종 결론을 도출했습니다.\n"
                summary += f"- 최종 결론: {final_verdict}\n\n"
                summary += "이 조사 결과를 바탕으로 사용자에게 최종 답변을 제공하세요. "
                summary += "더 이상 도구를 호출할 필요가 없습니다. "
                summary += "'Final Answer:'로 시작하여 최종 답변을 작성하세요."
                return summary
            
            # final_verdict가 없거나 분석 실패인 경우에만 에러로 처리
            if errors:
                error_msg = f"조사 중 오류 발생: {', '.join(errors)}"
                return f"{error_msg}\n\n조사가 실패했습니다. 다른 방법을 시도하거나 사용자에게 결과를 보고하세요."
            
            # 에러도 없고 final_verdict도 없는 경우
            return "조사 파이프라인이 실행되었지만 최종 결론을 생성하지 못했습니다."
            
        except Exception as e:
            return f"조사 파이프라인 실행 오류: {str(e)}"
    
    async def _arun(
        self,
        image_path: str,
        run_manager: Optional[Any] = None,
    ) -> str:
        """비동기 실행 (동기 실행으로 위임)"""
        return self._run(image_path, run_manager)

