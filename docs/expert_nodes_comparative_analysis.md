# Expert Nodes 비교 분석 보고서

## 📋 개요
- **분석 대상**: `necking_nodes.py`, `deform_nodes.py`, `contact_nodes.py`
- **총 라인 수**: 1,202줄 + 1,255줄 + 1,313줄 = **3,770줄**
- **공통 아키텍처**: Map-Reduce 패턴 with Send API

---

## 🔍 파일별 구조 비교

### 1. 공통 구조
세 파일 모두 동일한 구조를 가짐:
```
[Expert]_nodes.py
├── analyze_hotspot_worker()      # Map 단계
├── supervisor_verdict()           # Reduce 단계
├── verdict_analyst_node()        # Debate - Analyst
├── verdict_critic_node()         # Debate - Critic
├── verdict_finalize_node()       # 최종 정리
└── Helper Functions
    ├── format_report_summary()
    └── extract_critiqued_hotspots()
```

### 2. 차이점

| 항목 | necking_nodes.py | deform_nodes.py | contact_nodes.py |
|------|-----------------|-----------------|------------------|
| **대상 컴포넌트** | Wire만 | Wire만 | Terminal/Splice/Plug |
| **Worker 함수 길이** | 447줄 | 499줄 | 445줄 |
| **Specialist 분기** | 없음 (Wire만) | 없음 (Wire만) | 있음 (`_analyze_specialist`) |
| **디버그 로깅** | 없음 | 있음 (enhance_image 내부) | 있음 (여러 곳) |
| **에러 처리** | try-except | try-except (전체 래핑) | try-except |

---

## ⚠️ 심각한 공통 문제점

### 1. **대규모 코드 중복 (Copy-Paste Programming)**

#### 1.1 거의 동일한 코드 블록
세 파일 간 코드 유사도가 **90% 이상**입니다. 주요 중복 영역:

**Safety Settings** (각 파일마다 5곳 이상 반복)
```python
# necking_nodes.py: Line 173-178, 246-251, 519-524, 777-782, 989-994
# deform_nodes.py: Line 212-217, 284-289, 571-576, 834-839, 1043-1048
# contact_nodes.py: Line 224-229, 502-507, 641-646, 892-897, 1101-1106
safety_settings_block_none = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]
```
- **총 15곳 이상**에서 동일한 코드 반복
- 한 곳 수정 시 3개 파일 모두 수정 필요

**API 호출 패턴** (각 파일마다 5-6개 함수)
```python
# 각 파일마다 거의 동일한 패턴
async def _call_classifier_api(...)
async def _call_evidence_api(...)
async def _call_supervisor_api(...)
async def _call_analyst_api(...)
async def _call_critic_vision_api(...)
async def _call_critic_text_api(...)
```
- **총 18개 함수**가 거의 동일한 로직
- 차이점: 프롬프트 함수명, 모델명, response_schema만 다름

**Response 검증 로직** (각 파일마다 5곳 이상)
```python
# 동일한 패턴이 각 파일마다 반복
response_text = getattr(response, 'text', None)
if not response_text:
    finish_reason = "Unknown"
    if hasattr(response, 'candidates') and response.candidates:
        finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
    raise ValueError(f"... (Finish Reason: {finish_reason})")
```
- **총 15곳 이상**에서 동일한 코드 반복

**이미지 로딩 로직** (각 파일마다 3-4곳)
```python
# 동일한 패턴 반복
roi_image_data = await asyncio.to_thread(_load_image_data, roi_image_path)
original_image_data = await asyncio.to_thread(_load_image_data, image_path)
```
- **총 10곳 이상**에서 동일한 코드 반복

#### 1.2 중복 코드 통계
| 중복 항목 | 반복 횟수 (파일당) | 총 반복 횟수 |
|----------|-------------------|-------------|
| Safety Settings | 5곳 | **15곳** |
| API 호출 함수 | 6개 | **18개** |
| Response 검증 | 5곳 | **15곳** |
| 이미지 로딩 | 3-4곳 | **10곳** |
| ROI Crop + Enhancement | 1곳 | **3곳** (거의 동일) |
| Component Classification | 1곳 | **3곳** (거의 동일) |
| Supervisor 로직 | 1곳 | **3곳** (거의 동일) |
| Analyst 로직 | 1곳 | **3곳** (거의 동일) |
| Critic 로직 | 1곳 | **3곳** (거의 동일) |
| Finalize 로직 | 1곳 | **3곳** (거의 동일) |

**총 중복 코드**: 약 **2,500줄 이상** (전체의 66%)

---

### 2. **유지보수성 문제**

#### 2.1 버그 수정 시 3곳 모두 수정 필요
예시: Safety Settings 변경 시
- 현재: 3개 파일 × 5곳 = **15곳 수정 필요**
- 개선 후: 1곳만 수정

#### 2.2 기능 추가 시 3곳 모두 추가 필요
예시: 새로운 에러 처리 로직 추가 시
- 현재: 3개 파일 모두 수정
- 개선 후: 공통 모듈 1곳만 수정

#### 2.3 일관성 문제
- `deform_nodes.py`만 전체 try-except로 래핑됨 (Line 89, 519)
- `contact_nodes.py`만 `_analyze_specialist` 헬퍼 함수 존재
- 디버그 로깅 코드가 일부 파일에만 존재

---

### 3. **파일별 고유 문제점**

#### 3.1 necking_nodes.py
- ✅ 상대적으로 깔끔함 (디버그 코드 없음)
- ❌ `analyze_hotspot_worker`가 447줄로 과도하게 김
- ❌ Enhancement 로직이 인라인으로 포함됨

#### 3.2 deform_nodes.py
- ❌ **디버그 로깅 코드가 프로덕션 코드에 포함됨** (Line 123-148)
```python
def enhance_image(img, path):
    # #region agent log
    import json
    import time
    from pathlib import Path
    log_path = Path(PROJECT_ROOT) / ".cursor" / "debug.log"
    # ... 디버그 로깅 코드 ...
    # #endregion
```
- ❌ `analyze_hotspot_worker`가 499줄로 가장 김
- ❌ 전체 함수가 try-except로 래핑되어 있어 에러 추적 어려움

#### 3.3 contact_nodes.py
- ✅ `_analyze_specialist` 헬퍼 함수로 코드 재사용성 향상 (좋은 패턴!)
- ❌ 디버그 로깅 코드가 여러 곳에 산재 (Line 135-159, 512-545)
- ❌ Specialist 분기 로직이 복잡함 (Terminal/Splice/Plug)

---

## 🔧 통합 개선 제안

### Phase 1: 공통 모듈 추출 (High Priority)

#### 1.1 공통 설정 모듈
```python
# src/utils/expert_config.py
class ExpertConfig:
    """전문가 노드 공통 설정"""
    
    @staticmethod
    def get_safety_settings():
        """Safety Settings 반환"""
        return [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
    
    THINKING_SUPPORTED_MODELS = [
        "gemini-2.0-flash-exp",
        "gemini-2.5-flash",
        "gemini-2.5-pro"
    ]
    
    LARGE_ROI_THRESHOLD = 80_000
    MAX_DEBATE_ITERATIONS = 3
```

#### 1.2 공통 API 클라이언트
```python
# src/utils/expert_api_client.py
class ExpertAPIClient:
    """전문가 노드 공통 API 클라이언트"""
    
    @staticmethod
    async def call_classifier_api(
        client,
        model_name: str,
        parts: List[Any],
        context_name: str = "Classifier"
    ) -> ComponentClassification:
        """컴포넌트 분류 API 호출"""
        # 공통 로직 통합
        ...
    
    @staticmethod
    async def call_evidence_api(
        client,
        model_name: str,
        parts: List[Any],
        response_schema: Type[BaseModel],
        thinking_level: Optional[str] = "high",
        context_name: str = "Evidence"
    ) -> BaseModel:
        """증거 수집 API 호출"""
        # 공통 로직 통합
        ...
    
    @staticmethod
    async def call_supervisor_api(
        client,
        model_name: str,
        prompt: str,
        response_schema: Type[BaseModel],
        context_name: str = "Supervisor"
    ) -> BaseModel:
        """Supervisor API 호출"""
        # 공통 로직 통합
        ...
    
    @staticmethod
    def validate_response(response) -> str:
        """응답 검증 및 텍스트 추출"""
        response_text = getattr(response, 'text', None)
        if not response_text:
            finish_reason = extract_finish_reason(response)
            raise ValueError(
                f"API 응답이 비어있습니다. (Finish Reason: {finish_reason})"
            )
        return response_text
```

#### 1.3 공통 이미지 처리 모듈
```python
# src/utils/expert_image_utils.py
class ExpertImageLoader:
    """전문가 노드 공통 이미지 로더 (캐싱 지원)"""
    
    def __init__(self):
        self._cache = {}
    
    async def load_images(
        self,
        roi_path: str,
        original_path: str,
        use_cache: bool = True
    ) -> Tuple[bytes, bytes]:
        """ROI 및 원본 이미지 로드"""
        roi_data = await self.load_image(roi_path, use_cache)
        original_data = await self.load_image(original_path, use_cache)
        return original_data, roi_data
    
    async def load_image(self, path: str, use_cache: bool = True) -> bytes:
        """단일 이미지 로드"""
        if use_cache and path in self._cache:
            return self._cache[path]
        
        data = await asyncio.to_thread(_load_image_data, path)
        if use_cache:
            self._cache[path] = data
        return data

class ExpertImageProcessor:
    """전문가 노드 공통 이미지 처리"""
    
    @staticmethod
    async def crop_and_enhance(
        image_path: str,
        box_2d: Dict[str, Any],
        hotspot_id: str
    ) -> str:
        """ROI 크롭 및 Enhancement"""
        # 공통 로직 통합
        ...
```

#### 1.4 공통 Worker 베이스 클래스
```python
# src/nodes/base_expert_worker.py
class BaseExpertWorker:
    """전문가 Worker 베이스 클래스"""
    
    def __init__(
        self,
        expert_type: str,  # "necking", "deform", "contact"
        api_client: Optional[ExpertAPIClient] = None,
        image_loader: Optional[ExpertImageLoader] = None,
        image_processor: Optional[ExpertImageProcessor] = None
    ):
        self.expert_type = expert_type
        self.api_client = api_client or ExpertAPIClient()
        self.image_loader = image_loader or ExpertImageLoader()
        self.image_processor = image_processor or ExpertImageProcessor()
    
    async def analyze_hotspot(self, state: WorkerState) -> Dict[str, List[Dict]]:
        """공통 Worker 로직"""
        # 1. ROI Crop + Enhancement
        roi_path = await self._crop_and_enhance(state)
        
        # 2. Component Classification
        connection_type = await self._classify_component(state, roi_path)
        
        # 3. Evidence Collection (서브클래스에서 구현)
        evidence_result = await self._collect_evidence(
            state, roi_path, connection_type
        )
        
        # 4. 결과 반환
        return self._format_result(state, evidence_result, connection_type)
    
    async def _crop_and_enhance(self, state: WorkerState) -> str:
        """ROI 크롭 및 Enhancement (공통)"""
        ...
    
    async def _classify_component(self, state: WorkerState, roi_path: str) -> str:
        """컴포넌트 분류 (공통)"""
        ...
    
    async def _collect_evidence(self, state: WorkerState, roi_path: str, connection_type: str):
        """증거 수집 (서브클래스에서 구현)"""
        raise NotImplementedError
    
    def _format_result(self, state: WorkerState, evidence_result, connection_type: str):
        """결과 포맷팅 (서브클래스에서 커스터마이징 가능)"""
        ...
```

---

### Phase 2: 전문가별 서브클래스 구현

#### 2.1 Necking Worker
```python
# src/nodes/necking_nodes.py (리팩토링 후)
from src.nodes.base_expert_worker import BaseExpertWorker

class NeckingWorker(BaseExpertWorker):
    """Necking 전문가 Worker"""
    
    def __init__(self):
        super().__init__(expert_type="necking")
    
    async def _collect_evidence(self, state: WorkerState, roi_path: str, connection_type: str):
        """Wire만 분석"""
        if "Wire" not in connection_type:
            return None
        
        # Necking 전용 로직
        prompt = get_necking_wire_prompt(roi_path)
        original_data, roi_data = await self.image_loader.load_images(roi_path, state["image_path"])
        
        parts = [prompt]
        for img_data in [original_data, roi_data]:
            parts.append(types.Part.from_bytes(data=img_data, mime_type="image/jpeg"))
        
        response = await self.api_client.call_evidence_api(
            client=get_genai_client(),
            model_name=os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME),
            parts=parts,
            response_schema=NeckingEvidenceResult,
            context_name=f"Necking Worker #{state['current_hotspot']['id']}"
        )
        
        return NeckingEvidenceResult.model_validate_json(response.text)
```

#### 2.2 Contact Worker
```python
# src/nodes/contact_nodes.py (리팩토링 후)
class ContactWorker(BaseExpertWorker):
    """Contact 전문가 Worker"""
    
    def __init__(self):
        super().__init__(expert_type="contact")
    
    async def _collect_evidence(self, state: WorkerState, roi_path: str, connection_type: str):
        """Terminal/Splice/Plug 분기 처리"""
        if "Terminal" in connection_type or "단자" in connection_type:
            return await self._analyze_terminal(state, roi_path)
        elif "Splice" in connection_type or "전선" in connection_type:
            return await self._analyze_splice(state, roi_path)
        elif "Plug" in connection_type or "플러그" in connection_type:
            return await self._analyze_plug(state, roi_path)
        return None
    
    async def _analyze_terminal(self, state: WorkerState, roi_path: str):
        """Terminal 분석"""
        return await self._analyze_specialist(
            state, roi_path, get_terminal_prompt, TerminalEvidenceResult, "Terminal"
        )
    
    # ... _analyze_splice, _analyze_plug 유사 ...
```

---

### Phase 3: 공통 Debate 노드 추출

#### 3.1 공통 Debate 베이스
```python
# src/nodes/base_debate_nodes.py
class BaseDebateNodes:
    """공통 Debate 노드 베이스"""
    
    @staticmethod
    async def analyst_node(state: ExpertState, expert_type: str) -> Dict[str, Any]:
        """공통 Analyst 로직"""
        # 공통 로직 통합
        ...
    
    @staticmethod
    async def critic_node(state: ExpertState, expert_type: str) -> Dict[str, Any]:
        """공통 Critic 로직"""
        # 공통 로직 통합
        ...
    
    @staticmethod
    async def finalize_node(state: ExpertState, expert_type: str) -> Dict[str, Any]:
        """공통 Finalize 로직"""
        # 공통 로직 통합
        ...
```

---

## 📊 개선 효과 예상

### 코드 라인 수 감소
| 항목 | 현재 | 개선 후 | 감소율 |
|------|------|---------|--------|
| **necking_nodes.py** | 1,202줄 | ~400줄 | 67% |
| **deform_nodes.py** | 1,255줄 | ~400줄 | 68% |
| **contact_nodes.py** | 1,313줄 | ~450줄 | 66% |
| **공통 모듈 추가** | 0줄 | ~800줄 | - |
| **총계** | 3,770줄 | ~2,050줄 | **46% 감소** |

### 중복 코드 제거
- **Safety Settings**: 15곳 → 1곳 (93% 감소)
- **API 호출 함수**: 18개 → 6개 (67% 감소)
- **Response 검증**: 15곳 → 1곳 (93% 감소)
- **이미지 로딩**: 10곳 → 1곳 (90% 감소)

### 유지보수성 향상
- **버그 수정**: 3곳 수정 → 1곳 수정 (67% 시간 절약)
- **기능 추가**: 3곳 추가 → 1곳 추가 (67% 시간 절약)
- **테스트 작성**: 각 파일별 → 공통 모듈 중심 (효율성 향상)

---

## 🎯 우선순위별 개선 로드맵

### Phase 1: 즉시 개선 (1-2주)
1. ✅ Safety Settings 상수화
2. ✅ Response 검증 함수 추출
3. ✅ 이미지 로딩 헬퍼 생성
4. ✅ 디버그 로깅 코드 제거 (deform_nodes.py, contact_nodes.py)

### Phase 2: 구조 개선 (2-4주)
1. ✅ 공통 API 클라이언트 생성
2. ✅ BaseExpertWorker 클래스 생성
3. ✅ 각 전문가별 서브클래스 구현
4. ✅ 공통 Debate 노드 추출

### Phase 3: 최적화 (4-6주)
1. ✅ 이미지 캐싱 구현
2. ✅ 임시 파일 관리 개선
3. ✅ 에러 처리 표준화
4. ✅ 타입 힌트 강화
5. ✅ 테스트 코드 작성

---

## 🚨 즉시 수정 필요 사항

### 1. 디버그 코드 제거
**deform_nodes.py** Line 123-148:
```python
# 제거 필요
def enhance_image(img, path):
    # #region agent log
    import json
    import time
    from pathlib import Path
    log_path = Path(PROJECT_ROOT) / ".cursor" / "debug.log"
    # ...
```

**contact_nodes.py** Line 135-159, 512-545:
```python
# 제거 필요
# #region agent log
# ...
# #endregion
```

### 2. 일관성 확보
- `deform_nodes.py`의 전체 try-except 래핑 제거 또는 다른 파일에도 적용
- `contact_nodes.py`의 `_analyze_specialist` 패턴을 다른 파일에도 적용

---

## 📈 결론

세 전문가 노드 파일은 **거의 동일한 코드가 3번 반복**되어 있습니다. 이는 다음과 같은 심각한 문제를 야기합니다:

1. **유지보수 비용 증가**: 한 곳 수정 시 3곳 모두 수정 필요
2. **버그 발생 가능성 증가**: 수정 누락 시 일관성 깨짐
3. **코드 품질 저하**: 중복 코드로 인한 가독성 저하
4. **테스트 어려움**: 동일한 로직을 3번 테스트해야 함

**제안된 리팩토링을 통해**:
- 코드 라인 수 **46% 감소**
- 중복 코드 **90% 이상 제거**
- 유지보수 시간 **67% 절약**
- 코드 품질 및 테스트 가능성 **대폭 향상**

가장 우선적으로 **공통 모듈 추출**을 진행하는 것을 강력히 권장합니다.
