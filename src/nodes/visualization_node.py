"""
Visualization Node
분석 결과를 원본 이미지에 오버레이하여 시각적 보고서를 생성합니다.
"""
import cv2
import numpy as np
import os
from typing import Dict, Any, List

from src.state import InvestigationState
from src.utils import load_image_safe, save_image_safe

def draw_annotation_node(state: InvestigationState) -> Dict[str, Any]:
    """
    모든 전문가의 분석 결과를 취합하여 원본 이미지에 시각화(Bbox, Label)합니다.
    """
    print("\n🎨 [Visualization] 시각적 보고서 생성 중...")
    
    # 1. 이미지 로드 ([Memory Optimization] image_path 우선 사용)
    image_path = state.get("image_path")
    
    if image_path and os.path.exists(image_path):
        # 파일 경로에서 직접 로드
        img = load_image_safe(image_path)
        if img is None:
            print(f"⚠️ [Visualization] 이미지 로드 실패: {image_path}")
            return {}
    else:
        # Fallback: payload에서 추출 (레거시 지원)
        from src.tools.experts.expert_utils import extract_image_from_payload
        image_data = extract_image_from_payload(state.get("payload", []))
        if image_data is None:
            print("⚠️ [Visualization] image_path도 없고 payload에서도 이미지를 찾을 수 없어 건너뜁니다.")
            return {}
        
        # 메모리 상에서 이미지 디코딩
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            print("⚠️ [Visualization] 이미지 디코딩 실패.")
            return {}
         
    # 2. 결과 순회 및 그리기
    expert_results = state.get("expert_analysis_results", {})
    
    # Color Palette (BGR)
    COLORS = {
        "contact": (0, 0, 255),    # Red
        "aging": (255, 0, 0),      # Blue
        "deform": (0, 255, 0),     # Green
        "necking": (0, 255, 255),  # Yellow
        "tracking": (255, 0, 255)  # Magenta
    }
    
    annotated_count = 0
    
    for expert_name, result_data in expert_results.items():
        # 각 전문가별 결과 구조가 다를 수 있음. 
        # 공통적으로 'multi_hotspot_results' 리스트를 가짐.
        hotspot_results = result_data.get("multi_hotspot_results", [])
        color = COLORS.get(expert_name, (255, 255, 255))
        
        for res in hotspot_results:
            hotspot = res.get("hotspot_info", {})
            box_2d = hotspot.get("box_2d") # [ymin, xmin, ymax, xmax] (0~1000)
            
            if not box_2d:
                continue
                
            # 좌표 변환
            h, w = img.shape[:2]
            ymin, xmin, ymax, xmax = box_2d
            x1 = int(xmin / 1000 * w)
            y1 = int(ymin / 1000 * h)
            x2 = int(xmax / 1000 * w)
            y2 = int(ymax / 1000 * h)
            
            # Box 그리기
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            
            # Label 구성
            damage_type = hotspot.get("damage_type", "Unknown")
            verdict = res.get("verdict", "")
            # 전문가 Verdict가 있으면 우선 표기, 없으면 초기 탐지명 표기
            label = f"[{expert_name.upper()}] {verdict}" if verdict and verdict != "N/A" else f"[{expert_name.upper()}] {damage_type}"
            
            # Text Background
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(img, (x1, y1 - 20), (x1 + tw, y1), color, -1)
            
            # Text
            cv2.putText(img, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            annotated_count += 1

    if annotated_count == 0:
        print("⚠️ [Visualization] 시각화할 Hotspot이 없습니다.")
        return {}

    # 3. 결과 저장
    # Output Dir: ./outputs/visual_reports/
    output_dir = os.path.join(os.getcwd(), "outputs", "visual_reports")
    os.makedirs(output_dir, exist_ok=True)
    
    import uuid
    filename = f"report_{uuid.uuid4().hex[:8]}.jpg"
    save_path = os.path.join(output_dir, filename)
    
    save_image_safe(img, save_path)
    print(f"✅ [Visualization] 리포트 저장 완료: {save_path}")
    
    # State에 경로 추가 (Optional, 만약 다운로드 링크 등을 제공하려면)
    return {"visual_report_path": save_path}
