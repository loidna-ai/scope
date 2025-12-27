"""
도구 레지스트리
싱글톤 패턴으로 모든 도구를 중앙에서 관리합니다.
"""
from typing import List
import threading
from langchain_core.tools import BaseTool
# 지연 로딩을 위해 import를 함수 내부로 이동

class ToolRegistry:
    """
    도구 레지스트리 싱글톤
    
    모든 도구를 중앙에서 관리하고 ReAct 에이전트에 제공합니다.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """싱글톤 패턴 구현"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ToolRegistry, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """도구 레지스트리 초기화"""
        if self._initialized:
            return
        
        with self._lock:
            if self._initialized:
                return
            
            self._tools: List[BaseTool] = []
            self._tools_by_category: dict[str, List[BaseTool]] = {}
            self._initialize_tools()
            self._initialized = True
    
    def _initialize_tools(self):
        """
        모든 도구 초기화
        
        기본 도구와 파이프라인 도구를 등록합니다.
        """
        
        
        try:
            
            
            # 지연 로딩: import를 함수 내부로 이동
            try:
                from src.tools.image_tools import (
                    ImageAnalyzerTool,
                    ImageEnhancerTool,
                    ImageCropperTool,
                    ImageFilterTool,
                )
            except ImportError as e:
                
                # 이미지 도구를 사용할 수 없으면 빈 리스트로 시작
                image_tools = []
            else:
                
                # 이미지 분석 도구 (torch 의존성 있는 도구는 선택적)
                image_tools = []
                try:
                    image_tools.append(ImageAnalyzerTool())
                except Exception as e:
                    
                    pass
                
                try:
                    image_tools.append(ImageEnhancerTool())
                except Exception as e:
                    
                    pass
                
                try:
                    image_tools.append(ImageCropperTool())
                except Exception as e:
                    
                    pass
                
                try:
                    image_tools.append(ImageFilterTool())
                except Exception as e:
                    
                    pass
            
            
            
            
            
            # 지연 로딩: 파이프라인 도구 import
            # ReAct 모드에서는 run_investigation_pipeline 도구를 제거하여 중복 실행 방지
            # 각 전문가는 서브그래프로 직접 실행되므로 파이프라인 도구가 필요 없음
            try:
                from src.tools.pipeline_tools import RunPreprocessingPipelineTool
                
                # 파이프라인 도구 (전처리만, 조사 파이프라인은 제외)
                # RunInvestigationPipelineTool은 제거: 각 전문가가 서브그래프로 직접 실행되므로 중복 실행 방지
                pipeline_tools = [
                    RunPreprocessingPipelineTool(),
                    # RunInvestigationPipelineTool() 제거됨 - 중복 실행 방지
                ]
            except ImportError as e:
                
                pipeline_tools = []
            
            
            
            # 모든 도구 등록
            self._tools.extend(image_tools)
            self._tools.extend(pipeline_tools)
            
            # 카테고리별 분류
            self._tools_by_category["image"] = image_tools
            self._tools_by_category["pipeline"] = pipeline_tools
            
            
            
        except Exception as e:
            
            raise
    
    def get_tools(self) -> List[BaseTool]:
        """
        모든 도구 반환
        
        Returns:
            등록된 모든 도구 리스트
        """
        return self._tools.copy()
    
    def get_tools_by_category(self, category: str) -> List[BaseTool]:
        """
        카테고리별 도구 반환
        
        Args:
            category: 도구 카테고리 ('image', 'pipeline' 등)
        
        Returns:
            해당 카테고리의 도구 리스트
        """
        return self._tools_by_category.get(category, []).copy()
    
    def add_tool(self, tool: BaseTool, category: str = "custom"):
        """
        새 도구 추가
        
        Args:
            tool: 추가할 도구
            category: 도구 카테고리 (기본값: 'custom')
        """
        with self._lock:
            self._tools.append(tool)
            if category not in self._tools_by_category:
                self._tools_by_category[category] = []
            self._tools_by_category[category].append(tool)

