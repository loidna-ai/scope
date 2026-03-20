
import os
import sys
import logging
from pathlib import Path
import cv2
import numpy as np
import io
from PIL import Image

# 프로젝트 루트를 패스에 추가하여 src 모듈 임포트 가능하게 설정
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.image_processing import slice_image, get_image_size
from src.utils import find_data_directory
import config

# --- Setup Logging ---
debug_folder = Path(__file__).parent
patch_folder = debug_folder / "patches"
patch_folder.mkdir(exist_ok=True)

log_file = debug_folder / "test_stage2.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def visualize_slicing_debug(image_path, patches_info, output_path):
    """Slicing 결과를 그리드로 시각화합니다."""
    img = cv2.imread(str(image_path))
    if img is None:
        logger.error(f"Failed to load image for visualization: {image_path}")
        return

    h, w = img.shape[:2]
    # Resize image if it was resized during slicing
    # Note: slice_image internal implementation handles resizing.
    # We should match the scale_factor if any patch has it.
    scale_factor = 1.0
    if patches_info:
        scale_factor = patches_info[0].get('scale_factor', 1.0)
    
    if scale_factor != 1.0:
        new_w = int(w * scale_factor)
        new_h = int(h * scale_factor)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    overlay = img.copy()
    
    for patch in patches_info:
        x, y = patch['offset']
        pw, ph = patch['size']
        status = patch['status']
        metrics = patch.get('debug_metrics', {})
        
        # Color: Green for PASS, Red for FILTERED
        color = (0, 255, 0) if status == "PASS" else (0, 0, 255)
        thickness = 2 if status == "PASS" else 1
        
        cv2.rectangle(img, (x, y), (x + pw, y + ph), color, thickness)
        
        # Text info
        r, c = patch['index']
        label = f"({r},{c}) V:{metrics.get('variance',0):.0f} E:{metrics.get('edge',0):.1f}"
        cv2.putText(img, label, (x + 5, y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)

    # Blend original and grid
    alpha = 0.3
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
    
    cv2.imwrite(str(output_path), img)
    logger.info(f"Saved slicing grid visualization to: {output_path}")

def run_stage2_test():
    logger.info("=== Stage 2 Debugging Test Started ===")
    
    # 1. 테스트 이미지 선정
    try:
        data_dir = find_data_directory()
        test_image_path = Path(data_dir) / "IMG_1634.JPG"
        if not test_image_path.exists():
            jpgs = list(Path(data_dir).glob("*.jpg"))
            if jpgs: test_image_path = jpgs[0]
            else:
                logger.error("No test image found.")
                return
    except Exception as e:
        logger.error(f"Error finding data directory: {e}")
        return

    logger.info(f"Target Test Image: {test_image_path.name}")
    
    # config 값 로드
    patch_size = getattr(config, 'HOTSPOT_PATCH_SIZE', 1024)
    overlap = getattr(config, 'HOTSPOT_OVERLAP', 200)
    max_dim = getattr(config, 'HOTSPOT_MAX_IMAGE_DIMENSION', 2048)
    blur_th = getattr(config, 'HOTSPOT_BLUR_THRESHOLD', 50.0)
    edge_th = getattr(config, 'HOTSPOT_EDGE_THRESHOLD', 15)
    
    logger.info(f"Config: Size={patch_size}, Overlap={overlap}, MaxDim={max_dim}, BlurTH={blur_th}, EdgeTH={edge_th}")

    # 2. Slicing 수행 및 모든 패치 정보 수집 (Filtering 내역 포함)
    # slice_image는 Generator이므로 실행하면서 정보를 수집합니다.
    # 하지만 PASS한 것만 yield하므로, 내부 로직을 모방하여 모든 정보를 수집하는 "Debug Slicer"를 구현합니다.
    
    all_patches_for_debug = []
    
    # Original slice_image implementation details
    img_array = cv2.imread(str(test_image_path))
    h_orig, w_orig = img_array.shape[:2]
    
    scale_factor = 1.0
    if max(w_orig, h_orig) > max_dim:
        scale_factor = max_dim / float(max(w_orig, h_orig))
        new_w, new_h = int(w_orig * scale_factor), int(h_orig * scale_factor)
        img_array = cv2.resize(img_array, (new_w, new_h), interpolation=cv2.INTER_AREA)

    h, w = img_array.shape[:2]
    stride = patch_size - overlap
    
    def get_starts(total_length, window, stride):
        starts = []
        curr = 0
        while curr + window < total_length:
            starts.append(curr)
            curr += stride
        starts.append(max(0, total_length - window))
        return sorted(list(set(starts)))

    x_coords = get_starts(w, patch_size, stride)
    y_coords = get_starts(h, patch_size, stride)
    
    pass_count = 0
    fail_count = 0

    for r_idx, y in enumerate(y_coords):
        for c_idx, x in enumerate(x_coords):
            x_end = min(x + patch_size, w)
            y_end = min(y + patch_size, h)
            pw, ph = x_end - x, y_end - y
            
            patch_bgr = img_array[y:y_end, x:x_end]
            gray = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.mean(edges)
            
            status = "PASS"
            if laplacian_var < blur_th or edge_density < edge_th:
                status = "FILTERED"
                fail_count += 1
            else:
                pass_count += 1
                
            patch_data = {
                "status": status,
                "offset": (x, y),
                "size": (pw, ph),
                "index": (r_idx, c_idx),
                "scale_factor": scale_factor,
                "debug_metrics": {"variance": laplacian_var, "edge": edge_density}
            }
            all_patches_for_debug.append(patch_data)
            
            # 패치 이미지 저장 (PASS한 것만 또는 모두 가능)
            if status == "PASS":
                patch_filename = f"patch_{r_idx}_{c_idx}.jpg"
                cv2.imwrite(str(patch_folder / patch_filename), patch_bgr)

    logger.info(f"Slicing Result: Total={len(all_patches_for_debug)}, PASS={pass_count}, FILTERED={fail_count}")

    # 3. 시각화 그리드 생성
    viz_path = debug_folder / "slicing_debug_grid.jpg"
    visualize_slicing_debug(test_image_path, all_patches_for_debug, viz_path)

    # 4. 요약 리포트 작성
    summary_file = debug_folder / "summary.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write("=== Stage 2 Slicing Debug Summary ===\n")
        f.write(f"Image: {test_image_path.name} ({w_orig}x{h_orig})\n")
        f.write(f"Scale Factor: {scale_factor:.4f} -> ({w}x{h})\n")
        f.write(f"Config: Size={patch_size}, Overlap={overlap}, Stride={stride}\n")
        f.write(f"Thresholds: Blur={blur_th}, Edge={edge_th}\n")
        f.write(f"Total Patches Generated: {len(all_patches_for_debug)}\n")
        f.write(f"  - PASS: {pass_count}\n")
        f.write(f"  - FILTERED: {fail_count}\n\n")
        f.write("Patch Details:\n")
        for p in all_patches_for_debug:
            idx = p['index']
            m = p['debug_metrics']
            f.write(f"[{idx[0]},{idx[1]}] Status: {p['status']}, Var: {m['variance']:.1f}, Edge: {m['edge']:.2f}, Offset: {p['offset']}\n")

    logger.info("=== Stage 2 Debugging Test Completed ===")

if __name__ == "__main__":
    run_stage2_test()
