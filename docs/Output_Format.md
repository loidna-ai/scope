# 프로젝트 최종 출력 형식

## 1. 출력 구조 개요

프로젝트 실행 후 다음과 같은 형식으로 결과가 출력됩니다:

### 1.1 콘솔 출력

```
============================================================
최종 분석 결과 (Final Verdict)
============================================================
[Arbiter의 최종 판정 내용이 여기에 출력됨]
============================================================

✅ 전체 결과가 저장되었습니다: outputs/{이미지명}/investigation_result.txt

[개별 리포트 저장]
  - {전문가명}_Expert_Report.txt 저장 완료
  - Arbiter_Report.txt 저장 완료
```

### 1.2 파일 출력 구조

```
outputs/
└── {이미지명}/                    # 예: Poor_Contact_001/
    ├── investigation_result.txt    # 통합 결과 파일 (모든 정보 포함)
    ├── Arbiter_Report.txt          # Arbiter 최종 판정만 별도 저장
    └── {전문가명}_Expert_Report.txt # 각 전문가별 리포트 (선택적)
```

## 2. 출력 파일 상세 내용

### 2.1 `investigation_result.txt` (통합 결과 파일)

**구조:**
```
화재조사 AI 멀티 에이전트 시스템 분석 결과
일시: YYYY-MM-DD HH:MM:SS
============================================================
입력 이미지: {이미지 경로}
============================================================

[최종 분석 결론]
{Arbiter의 최종 판정 내용}

------------------------------------------------------------

[전문가 상세 리포트]

--- Expert Report 1 ---
{Contact 전문가 리포트}

--- Expert Report 2 ---
{Deform 전문가 리포트}

--- Expert Report 3 ---
{Necking 전문가 리포트}

============================================================
[System Errors & Warnings]
- {오류 메시지 1}
- {오류 메시지 2}
```

**특징:**
- 모든 정보를 하나의 파일에 통합
- 최종 결론과 각 전문가 리포트를 모두 포함
- 시스템 오류 및 경고도 함께 기록

### 2.2 `Arbiter_Report.txt` (Arbiter 최종 판정)

**구조:**
```
[Arbiter (Chief Investigator) Report]

## 화재조사 최종 결론 (Arbiter Agent)

### [종합 분석]
{각 전문가의 의견을 종합한 분석}

### [최종 판정]
**최종 결론: {결론}**
(신뢰도: {신뢰도}%)

### [판정 근거]
{상세한 판정 근거}

### [추가 조사 필요 사항]
{필요한 경우 추가 조사 항목}
```

**특징:**
- Arbiter의 최종 판정만 별도로 저장
- 논쟁 과정을 거쳐 도출된 최종 결론
- 판정 근거와 추가 조사 사항 포함

### 2.3 `{전문가명}_Expert_Report.txt` (전문가별 리포트)

**구조 (예: Contact 전문가):**
```
[Contact 전문가 최종 판정 - Analyst-Critic 토론]

## 결론: {결론} ({신뢰도}%)

## 최종 합의 가설
{가설 내용}

## 종합 소견
Analyst-Critic {턴 수}턴 토론 후 합의 도출.
{합의 상태}

## 토론 기록
{토론 내용}
```

**특징:**
- 각 전문가의 독립적인 분석 결과
- Analyst-Critic 토론 과정 포함
- 전문가별로 다른 형식일 수 있음

## 3. 출력 예시

### 3.1 콘솔 출력 예시

```
============================================================
최종 분석 결과 (Final Verdict)
============================================================
## 화재조사 최종 결론 (Arbiter Agent)

### [종합 분석]
본 사건은 전선 접속부에서 발생한 화재의 원인을 규명하는 것으로...

### [최종 판정]
**최종 결론: 접촉불량 (Contact Failure)**
(신뢰도: 95.0%)

### [판정 근거]
1. 특이적 화학 반응의 존재: ...
2. 배타적 증거 분석: ...
...

============================================================

✅ 전체 결과가 저장되었습니다: outputs/Poor_Contact_001/investigation_result.txt

[개별 리포트 저장]
  - Unknown_Expert_Report.txt 저장 완료
  - Arbiter_Report.txt 저장 완료
```

### 3.2 파일 출력 예시

**investigation_result.txt:**
```
화재조사 AI 멀티 에이전트 시스템 분석 결과
일시: 2026-02-06 21:43:46
============================================================
입력 이미지: C:\Users\loidn\Documents\Projects\P_04_Scope\data\Poor_Contact_001.jpg
============================================================

[최종 분석 결론]
## 화재조사 최종 결론 (Arbiter Agent)
...

------------------------------------------------------------

[전문가 상세 리포트]

--- Expert Report 1 ---
[Contact 전문가 최종 판정 - Analyst-Critic 토론]
...

--- Expert Report 2 ---
[Deform 전문가 최종 판정 - Analyst-Critic 토론]
...

============================================================
[System Errors & Warnings]
- Necking 전문가 오류: 'NoneType' object has no attribute 'get'
```

## 4. 출력 생성 프로세스

### 4.1 출력 생성 흐름

```
main.py
  └── run_analysis_pipeline()
      ├── analyze_fire_evidence() 실행
      │   └── InvestigationGraph 실행
      │       ├── Contact Expert 분석
      │       ├── Deform Expert 분석
      │       ├── Necking Expert 분석
      │       └── Arbiter 논쟁 및 최종 판정
      │
      └── 결과 저장
          ├── investigation_result.txt 생성
          ├── Arbiter_Report.txt 생성
          └── {전문가명}_Expert_Report.txt 생성
```

### 4.2 출력 위치

- **기본 경로**: `outputs/{이미지명}/`
- **설정**: `config.OUTPUT_DIR`에서 지정 가능
- **이미지명**: 입력 이미지 파일명에서 확장자 제거 (예: `Poor_Contact_001.jpg` → `Poor_Contact_001`)

## 5. 출력 파일 활용

### 5.1 통합 결과 파일 (`investigation_result.txt`)
- 전체 분석 과정과 결과를 한눈에 확인
- 리포트 작성 및 문서화에 활용
- 분석 이력 관리

### 5.2 Arbiter 리포트 (`Arbiter_Report.txt`)
- 최종 판정만 빠르게 확인
- 의사결정에 활용
- 보고서 작성 시 핵심 내용으로 활용

### 5.3 전문가 리포트 (`{전문가명}_Expert_Report.txt`)
- 각 전문가의 상세 분석 내용 확인
- 전문가별 의견 비교 분석
- 특정 전문가의 분석 과정 검토

## 6. 주의사항

1. **파일명 매핑**: 전문가 리포트 파일명은 리포트 내용에서 전문가 이름을 추출하여 결정됩니다. 현재는 다음 패턴을 인식합니다:
   - `[Contact 전문가 리포트]` → `Contact_Expert_Report.txt`
   - `[Deform 전문가 리포트]` → `Deform_Expert_Report.txt`
   - `[Necking 전문가 리포트]` → `Necking_Expert_Report.txt`
   - 매칭되지 않으면 `Unknown_Expert_Report.txt`로 저장됩니다.

2. **오류 처리**: 분석 중 발생한 오류는 `investigation_result.txt`의 `[System Errors & Warnings]` 섹션에 기록됩니다.

3. **인코딩**: 모든 출력 파일은 UTF-8 인코딩으로 저장됩니다.

4. **기존 파일 덮어쓰기**: 같은 이미지로 다시 실행하면 기존 출력 파일이 덮어씌워집니다.
