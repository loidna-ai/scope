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
from src.utils.logging_config import setup_logger

logger = setup_logger("visualization_node")

def draw_annotation_node(state: InvestigationState) -> Dict[str, Any]:
    """
    모든 전문가의 분석 결과를 취합하여 원본 이미지에 시각화(Bbox, Label)합니다.
    """
    print("\n[Visualization] 시각적 보고서 생성 중...")
    
    # 1. 이미지 로드 - image_paths[0] 우선 (Hotspot Detector가 사용한 분석 이미지와 동일)
    image_paths = state.get("image_paths") or []
    image_path = (image_paths[0] if image_paths else None) or state.get("image_path")
    
    if image_path and os.path.exists(image_path):
        # 파일 경로에서 직접 로드
        img = load_image_safe(image_path)
        if img is None:
            print(f"Warning: [Visualization] 이미지 로드 실패: {image_path}")
            return {}
    else:
        # Fallback: payload에서 추출 (레거시 지원)
        from src.tools.experts.expert_utils import extract_image_from_payload
        image_data = extract_image_from_payload(state.get("payload", []))
        if image_data is None:
            print("Warning: [Visualization] image_path도 없고 payload에서도 이미지를 찾을 수 없어 건너뜜")
            return {}
        
        # 메모리 상에서 이미지 디코딩
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            print("Warning: [Visualization] 이미지 디코딩 실패.")
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
    
    # [Fix] 핫스팟별로 한 번만 그리기: 동일 hotspot이 여러 전문가 결과에 있으면,
    # PENDING이 아닌 verdict를 가진 전문가를 우선 표시 (Contact가 CONTACT로 판정했으면 [CONTACT] 표시)
    # hotspot_id -> (expert_name, verdict, res, color)
    hotspot_to_draw: Dict[int, tuple] = {}
    for expert_name, result_data in expert_results.items():
        color = COLORS.get(expert_name, (255, 255, 255))
        hotspot_results = result_data.get("multi_hotspot_results", [])
        for res in hotspot_results:
            hotspot = res.get("hotspot_info", {})
            spec_result = res.get("specialist_result", {})
            # 우선순위: verdict(실제 결론) -> conclusion(상태) -> 기타
            verdict = res.get("verdict") or spec_result.get("verdict") or spec_result.get("conclusion") or ""
            if any(kw in verdict for kw in ["Skip", "Not Target", "분석 대상 아님", "Not Wire", "Not Contact"]):
                continue
            hid = hotspot.get("id")
            if hid is None:
                continue
            
            is_pending = not verdict or "보류" in verdict or verdict == "N/A"
            existing = hotspot_to_draw.get(hid)
            
            # [Expert Priority Logic] PENDING이 아닌 verdict를 가진 전문가를 우선 표시
            is_pending = not verdict or any(kw in verdict.upper() for kw in ["PENDING", "보류", "N/A"])
            existing = hotspot_to_draw.get(hid)
            
            if existing is None:
                hotspot_to_draw[hid] = (expert_name, verdict, res, color)
            else:
                existing_verdict = existing[1]
                is_existing_pending = not existing_verdict or any(kw in existing_verdict.upper() for kw in ["PENDING", "보류", "N/A"])
                # 기존이 보류(PENDING)이고 새로운 결과가 확정(Verdict)이면 교체
                if is_existing_pending and not is_pending:
                    hotspot_to_draw[hid] = (expert_name, verdict, res, color)
    
    annotated_count = 0
    for _hid, (expert_name, verdict, res, color) in hotspot_to_draw.items():
        hotspot = res.get("hotspot_info", {})
        box_2d = hotspot.get("box_2d")
        
        # [Fix v0.5.4] Wide/Deep 모드(UnifiedHotspot) 대응: 현재 이미지에 해당하는 Box 탐색
        if not box_2d:
            boxes = hotspot.get("boxes", {})
            if isinstance(boxes, dict) and boxes:
                # 1. 현재 메인 이미지 경로로 우선 확인 (상속된 경로)
                box_2d = boxes.get(image_path)
                if not box_2d and image_path:
                    target_name = os.path.basename(image_path)
                    for b_path, b_val in boxes.items():
                        if b_path and os.path.basename(b_path) == target_name:
                            box_2d = b_val
                            break
                if not box_2d:
                    first_path = next(iter(boxes))
                    box_2d = boxes[first_path]
        
        if not box_2d:
            continue
        
        # 좌표 추출
        h, w = img.shape[:2]
        if isinstance(box_2d, dict):
            ymin, xmin, ymax, xmax = box_2d.get("ymin", 0), box_2d.get("xmin", 0), box_2d.get("ymax", 0), box_2d.get("xmax", 0)
        elif hasattr(box_2d, 'ymin'):
            ymin, xmin, ymax, xmax = box_2d.ymin, box_2d.xmin, box_2d.ymax, box_2d.xmax
        elif isinstance(box_2d, list) and len(box_2d) == 4:
            ymin, xmin, ymax, xmax = box_2d
        else:
            continue
            
        # [Rich Aesthetics] 고해상도 대응 가변 스케일링
        base_scale = max(1.0, min(w, h) / 1500.0)
        thickness = max(2, int(3 * base_scale))
        font_scale = 0.5 * base_scale
        line_type = cv2.LINE_AA
        
        # 좌표 변환
        x1, y1 = int(xmin / 1000 * w), int(ymin / 1000 * h)
        x2, y2 = int(xmax / 1000 * w), int(ymax / 1000 * h)
        
        # [User Request] Label 구성: #ID 피해구분 (정확도) [RAW 좌표]
        # 예시: #1 Wire (80%) [100,200,300,400]
        hotspot_id = hotspot.get("id", "?")
        component = hotspot.get("component_name") or "Object"
        
        # 탐지 단계의 정확도 (Detection Confidence)
        confidence = hotspot.get("confidence_score") or 0.0
        conf_val = float(confidence)
        if conf_val <= 1.0: conf_val *= 100
        
        # [Debug] RAW 좌표 정보 (ymin, xmin, ymax, xmax)
        raw_coords = f"[{int(ymin)},{int(xmin)},{int(ymax)},{int(xmax)}]"
        
        # 최종 라벨 텍스트
        full_label = f"#{hotspot_id} {component} ({int(conf_val)}%) {raw_coords}"


        # 1. Box 그리기 (이중 외곽선으로 가독성 확보)
        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 255, 255), thickness + 2, line_type)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness, line_type)
        
        # 2. Text Background 및 Label 그리기
        (tw, th), baseline = cv2.getTextSize(full_label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness // 2)
        text_y = y1 if y1 - th - 10 > 0 else y2 + th + 10
        cv2.rectangle(img, (x1, text_y - th - 10), (x1 + tw + 10, text_y + baseline), color, -1)
        cv2.rectangle(img, (x1, text_y - th - 10), (x1 + tw + 10, text_y + baseline), (255, 255, 255), 1, line_type)
        cv2.putText(img, full_label, (x1 + 5, text_y - 5), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), (thickness // 2) + 1, line_type)
        cv2.putText(img, full_label, (x1 + 5, text_y - 5), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), max(1, thickness // 3), line_type)
        
        annotated_count += 1

    if annotated_count == 0:
        total_results = sum(len(rd.get("multi_hotspot_results", [])) for rd in expert_results.values())
        logger.warning(
            f"[Visualization] 시각화할 유효한 결과가 없습니다. (filtered from {total_results})"
        )
        print("Warning: [Visualization] 시각화할 유효한 분석 데이터가 없습니다.")
        return {}

    # 3. 결과 저장
    # output_dir가 있으면 해당 폴더에 저장, 없으면 outputs/visual_reports/ (레거시)
    output_dir_str = state.get("output_dir")
    if output_dir_str and os.path.isdir(output_dir_str):
        output_dir = output_dir_str
    else:
        output_dir = os.path.join(os.getcwd(), "outputs", "visual_reports")
    os.makedirs(output_dir, exist_ok=True)
    
    import uuid
    filename = f"visual_report_{uuid.uuid4().hex[:8]}.jpg"
    save_path = os.path.join(output_dir, filename)
    
    save_image_safe(img, save_path)
    print(f"OK: [Visualization] 리포트 저장 완료: {save_path}")
    
    # State에 경로 추가 (Optional, 만약 다운로드 링크 등을 제공하려면)
    return {"visual_report_path": save_path}
