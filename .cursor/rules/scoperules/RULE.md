---
alwaysApply: true
---

Project Context & Persona

You are an expert Python developer specializing in Computer Vision and Workflow Automation.
Your goal is to build a robust image processing pipeline for electrical singularity (short circuit mark) photos using LangGraph.

CRITICAL INSTRUCTION: All LangGraph implementations must strictly adhere to the Official LangGraph Documentation Standards. Use standard patterns for StateGraph, node definition, and edge connections as outlined in the latest LangGraph guides.

Project Description

이 프로젝트는 전기적 특이점(단락흔)의 원본 사진을 입력받아 결함(균열 등)을 탐지하고, 고화질로 복원한 뒤, 분석 데이터를 추출하여 AI 모델(Gemini)이 분석 가능한 형태의 리포트를 생성하는 자동화 파이프라인입니다.

Key Features

Input: 전기적 특이점(단락흔) 원본 사진 (Raw Image) - 한글 경로 지원 필수

Process 1 (Enhancement):

Real-ESRGAN을 사용하여 초해상도(Super Resolution) 복원

Verification: 입력 대비 출력 크기(Scale) 검증 로직 포함

Process 2 (Branching):

Branch A: 기본 고화질 이미지 (Base)

Branch B: CLAHE 필터 적용 이미지 (Texture/Contrast Enhanced)

Branch C: Skimage를 활용한 원형도/광택 수치 추출 (Metrics)

Output: AI Model(Gemini)이 결과물을 비교 분석할 수 있는 파일 형태 (JSON)

Tech Stack & Libraries

Language: Python 3.10+

Orchestration: LangGraph, LangChain-Core (Latest Versions)

Computer Vision:

realesrgan or basicsr

opencv-python-headless (Image IO/Processing)

scikit-image (Metric Extraction)

Utilities: numpy, pillow, json, pathlib

Coding Standards & Conventions

General

Language: 변수명과 로직은 영어로 작성하되, 주석(Comments)과 Docstring은 반드시 "한국어"로 작성합니다.

Typing: src/state.py에 정의된 GraphState를 기준으로 엄격한 Type Hint를 적용합니다.

Configuration: 모든 상수(임계값, 모델 경로, 타겟 해상도 등)는 하드코딩하지 않고 config.py에서 가져와 사용합니다.

LangGraph Specific Rules (Standard Compliance)

Official Pattern: 반드시 LangGraph 공식 문서의 표준 패턴을 따릅니다.

MessageGraph가 아닌 **StateGraph**를 사용합니다.

그래프 정의는 src/graph_builder.py에서 수행하며, workflow.compile()을 호출하여 Runnable 객체를 생성합니다.

State Management:

src/state.py에 TypedDict를 상속받은 GraphState를 정의합니다.

상태 업데이트 시 Annotated와 operator.add (Reducer) 패턴을 적절히 활용합니다.

Node Architecture:

각 노드는 Functional Component 방식으로 구현합니다 (def node(state) -> dict).

노드의 반환값은 전체 State가 아닌 **업데이트할 필드만 포함하는 Dict(Partial State)**여야 합니다.

Edge Definition:

조건부 분기가 아닌 병렬 처리(Fan-out)는 add_edge를 여러 번 호출하는 표준 방식을 사용합니다.

흐름 제어에는 START, END 노드 상수를 사용합니다.

File I/O & Path Handling (Crucial)

Directory Search: 데이터 폴더(Data)는 src.utils.find_data_directory()를 사용하여 현재 위치, 상위 위치 등을 탐색해야 합니다.

Korean Path Support:

cv2.imread, cv2.imwrite를 절대 직접 사용하지 않습니다.

반드시 src.utils.load_image_safe()와 src.utils.save_image_safe()를 사용하여 한글 경로 및 특수 문자가 포함된 파일을 처리합니다.

(np.fromfile + cv2.imdecode 패턴 준수)

Computer Vision Logic Rules

Real-ESRGAN (Enhancement) - src/nodes/enhancement.py:

Verification: 추론 후 output_width == input_width * SR_SCALE 인지 확인하는 로직을 반드시 포함합니다.

크기 검증 실패 시 로그에 경고(Warning)를 남깁니다.

Analysis & Metrics - src/nodes/analysis.py:

Metric 추출 시 skimage 처리를 위해 그레이스케일 변환 및 이진화 전처리를 수행해야 합니다.

File & Directory Structure

project_root/
├── .cursorrules           # This file (Rules & Context)
├── requirements.txt       # Dependencies
├── config.py              # Central Configuration (Path, Thresholds, Constants)
├── main.py                # Entry point to run the graph
├── src/
│   ├── __init__.py
│   ├── state.py           # GraphState definition (TypedDict)
│   ├── utils.py           # Safe Image I/O, Path Finder
│   ├── graph_builder.py   # StateGraph assembly (Standard Pattern)
│   └── nodes/
│       ├── __init__.py
│       ├── enhancement.py # Real-ESRGAN Node (with Verification)
│       ├── analysis.py    # CLAHE, Metric, Save Base Nodes
│       └── packaging.py   # JSON Report Generation Node
└── models/                # Model weights storage

