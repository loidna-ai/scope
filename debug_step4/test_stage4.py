
import os
import sys
import logging
from pathlib import Path
import cv2
import json

# 프로젝트 루트를 패스에 추가하여 src 모듈 임포트 가능하게 설정
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.image_processing import map_hotspots_to_global, get_image_size
from src.utils import find_data_directory
import config

# --- Setup Logging ---
debug_folder = Path(__file__).parent
log_file = debug_folder / "test_stage4.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def run_stage4_test():
    logger.info("=== Stage 4 Debugging Test Started ===")
    
    # 1. 테스트용 탐지 결과 로드 (Stage 3 결과물)
    api_response_file = Path("debug_step3/api_response_raw.json")
    if not api_response_file.exists():
        logger.error("Stage 3 API response not found. Please run Stage 3 first.")
        return
    
    with open(api_response_file, "r", encoding="utf-8") as f:
        hotspots = json.load(f)

    # 2. 패치 메타데이터 복원 (Stage 2 지식 기반)
    # Stage 3에서 사용한 [ImgIdx:1]은 patch_0_0.jpg였음.
    # Stage 2에서 IMG_1634.JPG (4032x3024)가 2048x1536으로 스케일링됨(0.5079).
    # patch_0_0.jpg의 Local Offset=(0, 0), Local Size=(1024, 1024)
    # Original Offset = (0, 0) / 0.5079 = (0, 0)
    # Original Size = (1024, 1024) / 0.5079 = (2016, 2016)
    
    scale_factor = 2048 / 4032.0 # 0.5079365...
    # patch_0_0: offset(0,0), size(1024, 1024)
    # patch_0_1: offset(824,0), size(1024, 1024) -> 824는 stride
    
    image_path = Path("data/IMG_1634.JPG")
    full_image_size = (4032, 3024) # (W, H)
    
    # map_hotspots_to_global()은 batch_results를 인자로 받는데, 
    # batch_results는 [(patches_chunk, patch_hotspots)] 구조임.
    
    # Mocking patches_chunk
    patches_chunk = [
        {
            'source_image_path': str(image_path),
            'original_offset': (0, 0),
            'original_size': (2016, 2016)
        },
        {
            'source_image_path': str(image_path),
            'original_offset': (int(824/scale_factor), 0),
            'original_size': (2016, 2016)
        }
    ]
    
    batch_results = [(patches_chunk, hotspots)]
    image_sizes = {str(image_path): full_image_size}

    # 3. 좌표 매핑 실행
    logger.info("Calling map_hotspots_to_global...")
    global_hotspots = map_hotspots_to_global(batch_results, image_sizes)
    
    # 4. 결과 시각화 및 검증
    img = cv2.imread(str(image_path))
    if img is None:
        logger.error(f"Image not found at {image_path}")
        return

    for i, h in enumerate(global_hotspots):
        box = h['box_2d']
        idx = h['image_index']
        logger.info(f"Detection {i+1} (ImgIdx {idx}):")
        logger.info(f"  - Original Patch offset: {patches_chunk[idx-1]['original_offset']}")
        logger.info(f"  - Global Normalized Box: {box}")
        
        # normalized box (0-1000) -> pixel box
        W, H = full_image_size
        ymin = int(box['ymin'] * H / 1000)
        xmin = int(box['xmin'] * W / 1000)
        ymax = int(box['ymax'] * H / 1000)
        xmax = int(box['xmax'] * W / 1000)
        
        logger.info(f"  - Global Pixel Box: [{ymin}, {xmin}, {ymax}, {xmax}]")
        
        # 상자 그리기
        cv2.rectangle(img, (xmin, ymin), (xmax, ymax), (0, 255, 0), 5)
        cv2.putText(img, f"#{i+1}", (xmin + 10, ymin + 50), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)

    output_path = debug_folder / "global_mapping_test.jpg"
    cv2.imwrite(str(output_path), img)
    logger.info(f"Global mapping visualization saved to: {output_path}")

    # 요약 리포트
    summary_file = debug_folder / "summary.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write("=== Stage 4 Coordinate Transformation Debug Summary ===\n")
        f.write(f"Source Image: {image_path.name} ({full_image_size})\n")
        f.write(f"Scale Factor used: {scale_factor:.4f}\n")
        f.write("Detections:\n")
        for i, h in enumerate(global_hotspots):
            f.write(f"  #{i+1} [ImgIdx:{h.get('image_index')}] NormBox:{h['box_2d']}\n")
    
    logger.info("=== Stage 4 Debugging Test Completed ===")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_stage4_test())
