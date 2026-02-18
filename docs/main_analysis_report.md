# main.py 구조 및 워크플로우 분석 리포트

## 📋 목차
1. [전체 구조 개요](#전체-구조-개요)
2. [워크플로우 분석](#워크플로우-분석)
3. [주요 문제점](#주요-문제점)
4. [개선사항 제안](#개선사항-제안)
5. [우선순위별 개선 계획](#우선순위별-개선-계획)

---

## 전체 구조 개요

### 파일 크기 및 복잡도
- **총 라인 수**: 1,189줄
- **함수 개수**: 약 20개 이상
- **정규식 패턴**: 20개 이상의 패턴 정의
- **책임 영역**: 다중 책임 (파싱, 포맷팅, 검증, 저장, 실행)

### 코드 구조 분류

```
main.py 구조:
├── 상수 및 패턴 정의 (28-82줄)
│   ├── 에러 패턴 (_RAW_ERROR_PATTERNS)
│   ├── 판정 추출 패턴 (VERDICT_PATTERNS)
│   └── 기타 정규식 패턴들
│
├── 텍스트 처리 함수들 (85-122줄)
│   ├── _sanitize_user_visible_text()
│   └── _sanitize_report_for_display()
│
├── 파싱 함수들 (124-258줄)
│   ├── parse_final_verdict()
│   └── parse_expert_report()
│
├── 리포트 포맷팅 함수들 (260-555줄)
│   ├── _format_report_header()
│   ├── _format_executive_summary()
│   ├── _format_expert_reports_section()
│   ├── _format_evidence_breakdown()
│   ├── _format_recommendations()
│   ├── format_investigation_result()
│   └── _format_audit_trail_section()
│
├── 검증 함수들 (557-637줄)
│   ├── validate_image_path()
│   └── validate_result_structure()
│
├── 이미지 처리 함수들 (639-785줄)
│   ├── select_image_file()
│   └── create_payload_from_image()
│
├── 리포트 저장 함수들 (788-860줄)
│   ├── _get_expert_filename()
│   ├── _save_expert_reports()
│   ├── _save_arbiter_report()
│   └── _save_investigation_result()
│
├── 메인 파이프라인 (932-1092줄)
│   └── run_analysis_pipeline()
│
└── 진입점 (1095-1188줄)
    └── main()
```

---

## 워크플로우 분석

### 실행 흐름도

```
[main()]
    │
    ├─→ [검증 모드] args.test == True
    │       └─→ 테스트 이미지 자동 선택
    │
    ├─→ [일반 모드] args.image_path 제공
    │       └─→ 제공된 경로 사용
    │
    └─→ [대화형 모드] 경로 미제공
            └─→ select_image_file() 호출
                    └─→ 사용자 선택 대기

    ↓
[이미지 경로 검증]
    validate_image_path()
    ├─→ 파일 존재 확인
    ├─→ 파일 크기 검증
    └─→ 확장자 검증

    ↓
[출력 디렉토리 준비]
    output_dir = outputs/{image_name}/

    ↓
[run_analysis_pipeline()]
    │
    ├─→ [1단계] Payload 생성
    │   create_payload_from_image()
    │   ├─→ 이미지 파일 읽기
    │   ├─→ Base64 인코딩
    │   └─→ Gemini 형식으로 변환
    │
    ├─→ [2단계] 멀티 에이전트 분석
    │   analyze_fire_evidence(payload)
    │   ├─→ Hotspot Detector 실행
    │   ├─→ 3개 전문가 병렬 분석 (Fan-Out)
    │   │   ├─→ Contact Expert
    │   │   ├─→ Deform Expert
    │   │   └─→ Necking Expert
    │   ├─→ 결과 수집 (Fan-In)
    │   └─→ Arbiter 최종 판정
    │
    ├─→ [3단계] 결과 검증
    │   validate_result_structure()
    │   ├─→ 필수 키 확인
    │   └─→ 타입 검증
    │
    └─→ [4단계] 결과 저장
        _save_investigation_result()
        ├─→ LLM 리포트 생성 (선택적)
        ├─→ 정규식 기반 리포트 생성 (Fallback)
        ├─→ 전문가 리포트 저장
        └─→ Arbiter 리포트 저장
```

### 데이터 흐름

```
입력 이미지
    ↓
[Base64 인코딩]
    ↓
Payload (Gemini 형식)
    ↓
analyze_fire_evidence()
    ↓
State Graph 실행
    ↓
결과 딕셔너리
{
    "final_verdict": str,
    "expert_reports": List[str],
    "arbiter_debate_messages": List[Dict],
    "errors": List[str]
}
    ↓
파싱 및 포맷팅
    ↓
Markdown 리포트
    ↓
파일 저장
```

---

## 주요 문제점

### 🔴 심각한 문제점 (Critical)

#### 1. **단일 책임 원칙 위반 (SRP Violation)**
- **문제**: 하나의 파일에 너무 많은 책임이 집중됨
  - 텍스트 파싱 (정규식 기반)
  - 리포트 포맷팅
  - 파일 I/O
  - 검증 로직
  - 비즈니스 로직
- **영향**: 유지보수 어려움, 테스트 복잡도 증가, 코드 재사용성 저하

#### 2. **과도한 정규식 의존성**
- **문제**: 20개 이상의 복잡한 정규식 패턴으로 텍스트 파싱
- **위험**:
  - 패턴 변경 시 취약성 증가
  - LLM 출력 형식 변경 시 파싱 실패 가능성 높음
  - 디버깅 어려움

**구체적인 위치 및 예시**:

**① 최종 판정 추출 (라인 42-48, 149-157)**
```python
VERDICT_PATTERNS = [
    r'\*\*최종 판정\*\*\s*[\|\s]*\*\*([^*\]]+)\*\*',  # 패턴 1
    r'\*\*최종 판정\*\*\s*\n\s*\*\*([^*\]]+)\*\*',    # 패턴 2
    r'\*\*최종 판정\*\*\s*\n\s*([^\n\]]+)',            # 패턴 3
    r'최종 판정[:\s\|]*([^\n\]]+)',                    # 패턴 4
    r'([가-힣]+\([^)]+\)\s*[가-힣]+)',                 # 패턴 5
]
# 5개의 패턴을 순차적으로 시도하여 첫 번째 매칭되는 것을 사용
for pattern in VERDICT_PATTERNS:
    verdict_match = re.search(pattern, clean_text)
    if verdict_match:
        break
```
**문제점**: LLM이 "최종 판정: 접촉불량(유력)" 형식으로 출력하면 패턴 4가 매칭되지만, 
"**최종 판정** | **접촉불량**" 형식으로 출력하면 패턴 1이 매칭됨. 
형식이 조금만 달라져도 파싱 실패 가능.

**② 판정 근거 추출 (라인 51-55, 323-327)**
```python
REASONING_PATTERNS = [
    r'\[판정 근거\]\s*\n(.*?)(?=\[|$)',              # 패턴 1
    r'\*\*\[판정 근거\]\*\*\s*\n(.*?)(?=\*\*\[|$)',  # 패턴 2
    r'\[종합 분석\]\s*\n(.*?)(?=\[|$)',              # 패턴 3
]
# 여러 패턴 시도
for pattern in REASONING_PATTERNS:
    reasoning_match = re.search(pattern, final_verdict, re.DOTALL)
    if reasoning_match:
        reasoning_text = reasoning_match.group(1).strip()
        break
```
**문제점**: LLM이 "판정 근거:" (콜론 사용) 또는 "판정 근거" (대괄호 없음)로 출력하면 
모든 패턴이 실패하여 `reasoning_text = None`이 됨.

**③ 전문가 리포트 파싱 (라인 179-257)**
```python
# 전문가 이름 추출 (라인 206)
name_match = re.search(EXPERT_NAME_PATTERN, report_text, re.IGNORECASE)
# EXPERT_NAME_PATTERN = r'\[(Contact|Deform|Necking|...)'

# 결론 추출 (라인 211)
conclusion_match = re.search(CONCLUSION_PATTERN, report_text)
# CONCLUSION_PATTERN = r'## 결론[:\s]*([^\n]+)'

# 신뢰도 추출 (라인 237, 241)
conf_match = re.search(CONFIDENCE_IN_PARENTHESES_PATTERN, conclusion)
# CONFIDENCE_IN_PARENTHESES_PATTERN = r'\((\d+\.?\d*)%\)'
# 또는
conf_match = re.search(CONFIDENCE_PATTERN, report_text)
# CONFIDENCE_PATTERN = r'(\d+\.?\d*)%'
```
**문제점**: 
- 전문가 이름이 "[Contact Expert]" 형식이 아닌 "Contact 전문가"로 출력되면 파싱 실패
- 결론이 "## 결론" 대신 "결론:" 또는 "Conclusion:"로 출력되면 파싱 실패
- 신뢰도가 "(85%)" 대신 "85%" 또는 "신뢰도: 85%"로 출력되면 파싱 실패

**④ Bullet 포인트 추출 (라인 72-75, 333-336)**
```python
BULLET_PATTERNS = [
    r'\d+\.\s+\*\*([^*]+)\*\*[:\s]*([^\n]+)',  # "1. **제목**: 내용"
    r'\d+\.\s+([^:]+):\s*([^\n]+)',            # "1. 제목: 내용"
]
for pattern in BULLET_PATTERNS:
    bullets = re.findall(pattern, reasoning_text)
    if bullets:
        break
```
**문제점**: LLM이 "- 제목: 내용" (하이픈 사용) 또는 "• 제목 - 내용" 형식으로 출력하면 파싱 실패.

**⑤ Zone 정보 추출 (라인 82, 415-418)**
```python
ZONE_PATTERN_TEMPLATE = r'Zone\s*{}\s*[의:]?\s*([가-힣a-zA-Z0-9\s,\-]+?)(?=\.|Zone|\d+\.|$)'
zone_pattern = ZONE_PATTERN_TEMPLATE.format(z_num)
m = re.search(zone_pattern, reasoning_text, re.IGNORECASE)
```
**문제점**: "Zone 1" 대신 "영역 1" 또는 "Zone1" (공백 없음)로 출력되면 파싱 실패.

**⑥ 에러 메시지 정제 (라인 115-120)**
```python
sanitized = re.sub(r'[^\n]*Supervisor Error:[^\n]*', '※ 분석 불가', sanitized)
sanitized = re.sub(r'[^\n]*name\s+\'[^\']+\'\s+is not defined[^\n]*', '※ 분석 불가', sanitized)
sanitized = re.sub(r'\[오류\]\s*\n\s*LLM 호출 실패:[^\n]*', '[오류]\nLLM 호출 실패: (시스템 일시 오류)', sanitized)
sanitized = re.sub(r'\(Error:\s*[^)]+\)', '(시스템 오류)', sanitized)
sanitized = re.sub(r'Traceback \(most recent call last\):.*?(?=\n\n|\Z)', '※ 분석 불가', sanitized, flags=re.DOTALL)
```
**문제점**: 에러 메시지 형식이 조금만 달라져도 정제되지 않아 사용자에게 노출될 수 있음.

**총 정규식 사용 통계**:
- 정의된 패턴: 20개 이상
- `re.search()` 호출: 15회 이상
- `re.sub()` 호출: 6회 이상
- `re.findall()` 호출: 2회 이상
- **총 정규식 사용: 23회 이상**

#### 3. **에러 처리 일관성 부족**
- **문제**: 
  - 일부 함수는 `None` 반환
  - 일부는 `(bool, str)` 튜플 반환
  - 일부는 예외 발생
- **예시**:
  ```python
  # 일관성 없는 반환 타입
  validate_image_path() -> tuple[bool, Optional[str]]
  select_image_file() -> Optional[str]
  create_payload_from_image() -> List[Dict]  # 예외 발생 가능
  ```

#### 4. **하드코딩된 값들**
- **문제**: 매직 넘버와 문자열이 코드에 직접 포함
- **예시**:
  ```python
  # 라인 262: 하드코딩된 배지
  badges = {"High": "🟢 High", "Medium": "🟡 Medium", "Low": "🔴 Low"}
  
  # 라인 365: 하드코딩된 라벨
  EXPERT_LABELS = {"CONTACT": "접촉불량", "DEFORM": "압착/손상", "NECKING": "용융/단선"}
  ```

### 🟡 중간 문제점 (Major)

#### 5. **긴 함수들 (Long Functions)**
- **문제**: 일부 함수가 100줄 이상
- **예시**:
  - `parse_expert_report()`: 79줄
  - `select_image_file()`: 76줄
  - `run_analysis_pipeline()`: 161줄
- **영향**: 가독성 저하, 테스트 어려움

#### 6. **타입 힌트 불일치**
- **문제**: 
  - 일부는 `tuple[bool, Optional[str]]` (Python 3.9+)
  - 일부는 `Dict[str, Any]` (타입 명시)
  - 일부는 타입 힌트 없음
- **예시**:
  ```python
  # 라인 557: 최신 문법
  def validate_image_path(image_path: str) -> tuple[bool, Optional[str]]:
  
  # 라인 124: 구식 문법
  def parse_final_verdict(verdict_text: str) -> Dict[str, str]:
  ```

#### 7. **중복된 검증 로직**
- **문제**: 
  - `validate_result_structure()`에서 타입 검증 후
  - `run_analysis_pipeline()`에서 다시 타입 검증 수행
- **예시** (라인 1020-1040):
  ```python
  is_valid, error_msg = validate_result_structure(result)
  # ... 이후 다시 타입 체크
  if not isinstance(expert_reports, list):
      expert_reports = []
  ```

#### 8. **에러 메시지 정제 로직 분산**
- **문제**: 
  - `_sanitize_user_visible_text()`: 사용자 노출용
  - `_sanitize_report_for_display()`: 파일 저장용
  - 로직이 중복되고 일관성 부족

### 🟢 경미한 문제점 (Minor)

#### 9. **문서화 부족**
- **문제**: 일부 함수에 docstring이 없거나 불완전
- **예시**: `_confidence_badge()` 함수에 docstring 없음

#### 10. **사용하지 않는 매개변수**
- **문제**: `_user_query` 매개변수가 정의되었지만 사용되지 않음
- **예시** (라인 935):
  ```python
  def run_analysis_pipeline(
      input_image_path: str, 
      output_dir: Path, 
      _user_query: str = ""  # 현재 미사용, 향후 확장용
  )
  ```

#### 11. **중복된 경로 검증**
- **문제**: `validate_image_path()`와 `create_payload_from_image()`에서 경로 검증 중복
- **예시**: 라인 1153-1173과 라인 732-738

#### 12. **하드코딩된 파일명 매핑**
- **문제**: `_get_expert_filename()` 함수에 if-elif 체인이 길고 확장성 부족
- **예시** (라인 788-811): 7개의 if-elif 분기

---

## 개선사항 제안

### 🎯 우선순위 1: 모듈 분리 (Refactoring)

#### 1.1 텍스트 파싱 모듈 분리
```python
# 제안: src/utils/text_parser.py
class VerdictParser:
    """최종 판정 텍스트 파싱"""
    PATTERNS = [...]
    
    @staticmethod
    def parse(verdict_text: str) -> Dict[str, str]:
        ...

class ExpertReportParser:
    """전문가 리포트 파싱"""
    @staticmethod
    def parse(report_text: str) -> Dict[str, str]:
        ...
```

**장점**:
- 단일 책임 원칙 준수
- 테스트 용이성 향상
- 재사용성 증가

#### 1.2 리포트 포맷팅 모듈 분리
```python
# 제안: src/utils/report_formatter.py
class ReportFormatter:
    """리포트 포맷팅 전담 클래스"""
    
    def format_header(self, ...) -> List[str]:
        ...
    
    def format_summary(self, ...) -> List[str]:
        ...
    
    def format_expert_section(self, ...) -> List[str]:
        ...
```

**장점**:
- 포맷팅 로직 집중화
- 다양한 출력 형식 지원 가능 (HTML, PDF 등)

#### 1.3 검증 모듈 통합
```python
# 제안: src/utils/validators.py
class ImageValidator:
    """이미지 파일 검증"""
    
    @staticmethod
    def validate_path(path: str) -> ValidationResult:
        ...
    
    @staticmethod
    def validate_size(path: str) -> ValidationResult:
        ...

class ResultValidator:
    """분석 결과 검증"""
    
    @staticmethod
    def validate_structure(result: Any) -> ValidationResult:
        ...
```

**장점**:
- 일관된 검증 인터페이스
- 에러 처리 통일

### 🎯 우선순위 2: 설정 외부화 (Configuration)

#### 2.1 정규식 패턴을 config.py로 이동
```python
# config.py에 추가
VERDICT_PATTERNS = [
    r'\*\*최종 판정\*\*\s*[\|\s]*\*\*([^*\]]+)\*\*',
    # ...
]

EXPERT_LABELS = {
    "CONTACT": "접촉불량",
    "DEFORM": "압착/손상",
    "NECKING": "용융/단선"
}
```

**장점**:
- 설정 변경 시 코드 수정 불필요
- 패턴 관리 용이

#### 2.2 하드코딩된 값들을 상수로 추출
```python
# config.py에 추가
CONFIDENCE_BADGES = {
    "High": "🟢 High",
    "Medium": "🟡 Medium",
    "Low": "🔴 Low"
}

EXPERT_FILE_MAPPING = {
    "Contact": "Contact_Expert_Report.txt",
    "Deform": "Deform_Expert_Report.txt",
    # ...
}
```

### 🎯 우선순위 3: 에러 처리 개선 (Error Handling)

#### 3.1 커스텀 예외 클래스 도입
```python
# src/utils/exceptions.py
class ImageValidationError(Exception):
    """이미지 검증 오류"""
    pass

class ResultValidationError(Exception):
    """결과 검증 오류"""
    pass

class ReportGenerationError(Exception):
    """리포트 생성 오류"""
    pass
```

**장점**:
- 명확한 에러 타입 구분
- 에러 핸들링 용이

#### 3.2 Result 타입 도입 (Python 3.10+)
```python
from typing import Union

class ValidationResult:
    """검증 결과를 나타내는 클래스"""
    def __init__(self, is_valid: bool, error_msg: Optional[str] = None):
        self.is_valid = is_valid
        self.error_msg = error_msg
    
    @classmethod
    def success(cls):
        return cls(True)
    
    @classmethod
    def failure(cls, msg: str):
        return cls(False, msg)
```

### 🎯 우선순위 4: 코드 품질 개선 (Code Quality)

#### 4.1 함수 분해 (Function Decomposition)
```python
# 현재: run_analysis_pipeline()이 161줄
# 개선: 작은 함수로 분해

def run_analysis_pipeline(...):
    payload = _create_payload(input_image_path)
    result = _execute_analysis(payload)
    _validate_and_save_result(result, output_dir, input_image_path)
    return result

def _create_payload(image_path: str) -> List[Dict]:
    """Payload 생성 전담"""
    ...

def _execute_analysis(payload: List[Dict]) -> Dict:
    """분석 실행 전담"""
    ...

def _validate_and_save_result(...):
    """결과 검증 및 저장 전담"""
    ...
```

#### 4.2 타입 힌트 통일
```python
# Python 3.9+ 스타일로 통일
from typing import Dict, List, Optional, Tuple

def validate_image_path(image_path: str) -> Tuple[bool, Optional[str]]:
    # 또는
    def validate_image_path(image_path: str) -> ValidationResult:
        ...
```

#### 4.3 매직 넘버 제거
```python
# 현재
if len(content_lines) > 8:  # 라인 544

# 개선
MAX_CONTENT_LINES = config.CONTENT_LINES_TRUNCATE_THRESHOLD
if len(content_lines) > MAX_CONTENT_LINES:
```

### 🎯 우선순위 5: 테스트 가능성 향상 (Testability)

#### 5.1 의존성 주입 (Dependency Injection)
```python
# 현재: 직접 import
from src.agent import analyze_fire_evidence

# 개선: 의존성 주입
def run_analysis_pipeline(
    input_image_path: str,
    output_dir: Path,
    analyzer: Callable = analyze_fire_evidence,  # 기본값 제공
    ...
):
    result = analyzer(payload)
```

**장점**:
- 테스트 시 Mock 객체 주입 가능
- 유연성 증가

#### 5.2 순수 함수 분리
```python
# 현재: I/O와 로직이 혼재
def parse_expert_report(report_text: str) -> Dict[str, str]:
    # 파일 읽기 + 파싱 로직

# 개선: 순수 함수로 분리
def parse_expert_report(report_text: str) -> Dict[str, str]:
    """순수 파싱 함수 (부작용 없음)"""
    ...

def load_and_parse_expert_report(file_path: str) -> Dict[str, str]:
    """I/O와 파싱 결합"""
    with open(file_path) as f:
        return parse_expert_report(f.read())
```

---

## 우선순위별 개선 계획

### Phase 1: 긴급 개선 (1-2주)
1. ✅ **모듈 분리**
   - 텍스트 파싱 모듈 분리 (`src/utils/text_parser.py`)
   - 리포트 포맷팅 모듈 분리 (`src/utils/report_formatter.py`)
   - 검증 모듈 통합 (`src/utils/validators.py`)

2. ✅ **에러 처리 개선**
   - 커스텀 예외 클래스 도입
   - 일관된 에러 처리 패턴 적용

### Phase 2: 중기 개선 (2-4주)
3. ✅ **설정 외부화**
   - 정규식 패턴을 config.py로 이동
   - 하드코딩된 값들을 상수로 추출

4. ✅ **함수 분해**
   - 긴 함수들을 작은 함수로 분해
   - 단일 책임 원칙 적용

### Phase 3: 장기 개선 (1-2개월)
5. ✅ **테스트 추가**
   - 단위 테스트 작성
   - 통합 테스트 작성

6. ✅ **문서화**
   - API 문서 작성
   - 사용자 가이드 작성

---

## 결론

`main.py`는 현재 **1,189줄의 거대한 모놀리식 파일**로, 여러 책임이 혼재되어 있습니다. 

**주요 개선 포인트**:
1. **모듈 분리**: 텍스트 파싱, 리포트 포맷팅, 검증 로직을 별도 모듈로 분리
2. **설정 외부화**: 정규식 패턴과 하드코딩된 값들을 config.py로 이동
3. **에러 처리 통일**: 커스텀 예외와 일관된 에러 처리 패턴 도입
4. **함수 분해**: 긴 함수들을 작은 단위로 분해하여 가독성과 테스트 용이성 향상

이러한 개선을 통해 **유지보수성**, **테스트 가능성**, **확장성**을 크게 향상시킬 수 있습니다.
