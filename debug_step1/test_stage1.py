
import os
import sys
import base64
import logging
from pathlib import Path
import cv2
import shutil

# 프로젝트 루트를 패스에 추가하여 src 모듈 임포트 가능하게 설정
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.io_utils import create_payload_from_image, process_payload_images
from src.utils import find_data_directory
import config

# --- Setup Logging ---
debug_folder = Path(__file__).parent
output_folder = debug_folder / "outputs"
output_folder.mkdir(exist_ok=True)

log_file = debug_folder / "test_stage1.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def get_image_info(image_path):
    """이미지의 해상도와 파일 크기 정보를 반환합니다."""
    img = cv2.imread(str(image_path))
    if img is None:
        return None, 0
    height, width = img.shape[:2]
    file_size = os.path.getsize(image_path) / 1024 # KB
    return (width, height), file_size

async def run_stage1_test():
    logger.info("=== Stage 1 Debugging Test Started ===")
    summary = []
    
    # 1. 테스트 이미지 선정
    try:
        data_dir = find_data_directory()
        test_image_path = Path(data_dir) / "Poor_Contact_001.jpg"
        if not test_image_path.exists():
            # 대안 이미지 찾기
            jpgs = list(Path(data_dir).glob("*.jpg"))
            if jpgs:
                test_image_path = jpgs[0]
            else:
                logger.error("No test image found in data directory.")
                return
    except Exception as e:
        logger.error(f"Error finding data directory: {e}")
        return

    logger.info(f"Target Test Image: {test_image_path.name}")
    orig_res, orig_size = get_image_info(test_image_path)
    logger.info(f"Original Properties: Res={orig_res}, Size={orig_size:.2f} KB")
    summary.append(f"Original Image: {test_image_path.name}")
    summary.append(f"  - Resolution: {orig_res}")
    summary.append(f"  - File Size: {orig_size:.2f} KB")

    # 2. Payload 생성 테스트 (create_payload_from_image)
    logger.info("Testing create_payload_from_image...")
    try:
        payload = create_payload_from_image(str(test_image_path))
        
        # 검증
        if not isinstance(payload, list) or len(payload) < 2:
            logger.error("Payload structure is invalid (expected list of >= 2 items).")
            return
        
        inline_data = payload[1].get("inline_data")
        if not inline_data:
            logger.error("Payload missing 'inline_data'.")
            return
        
        mime_type = inline_data.get("mime_type")
        encoded_data = inline_data.get("data")
        
        logger.info(f"Payload MIME Type: {mime_type}")
        logger.info(f"Base64 Data Length: {len(encoded_data)} chars")
        
        # 확장자 체크
        expected_mime = "image/jpeg" if test_image_path.suffix.lower() in [".jpg", ".jpeg"] else "image/png"
        if mime_type != expected_mime:
            logger.warning(f"MIME type mismatch: Expected {expected_mime}, got {mime_type}")
        
        summary.append(f"Payload Creation: OK (MIME: {mime_type}, Base64 Length: {len(encoded_data)})")
    except Exception as e:
        logger.error(f"Error in create_payload_from_image: {e}", exc_info=True)
        return

    # 3. 이미지 복원 및 리사이즈 테스트 (process_payload_images)
    logger.info("Testing process_payload_images...")
    try:
        # config 설정 확인 (리사이즈 여부 등)
        pre_resize_enabled = getattr(config, 'PRE_RESIZE_ENABLED', True)
        pre_resize_max = getattr(config, 'PRE_RESIZE_MAX_DIMENSION', 2048)
        logger.info(f"Config - PRE_RESIZE_ENABLED: {pre_resize_enabled}, MAX_DIM: {pre_resize_max}")

        temp_paths = process_payload_images(payload)
        
        if not temp_paths:
            logger.error("process_payload_images returned empty list.")
            return
        
        restored_path = Path(temp_paths[0])
        logger.info(f"Restored Temp Image: {restored_path}")
        
        # 복원된 이미지 정보 확인
        rest_res, rest_size = get_image_info(restored_path)
        logger.info(f"Restored Properties: Res={rest_res}, Size={rest_size:.2f} KB")
        
        summary.append(f"Image Restoration: OK")
        summary.append(f"  - Restored Resolution: {rest_res}")
        summary.append(f"  - Restored File Size: {rest_size:.2f} KB")

        # 리사이즈 로직 검증
        if pre_resize_enabled:
            max_orig = max(orig_res) if orig_res else 0
            if max_orig > pre_resize_max:
                if max(rest_res) != pre_resize_max:
                   logger.warning(f"Resize target mismatch. Expected max {pre_resize_max}, got {max(rest_res)}")
                else:
                    logger.info("Resize was applied correctly.")
            else:
                logger.info("Image was within max dimension, no downscaling expected (unless quality setting changed).")

        # 결과물 보관
        artifact_path = output_folder / f"restored_{test_image_path.name}"
        shutil.copy2(restored_path, artifact_path)
        logger.info(f"Saved restored image to: {artifact_path}")
        
        # 임시 파일은 process_payload_images가 생성한 것이므로 테스트 종료 후에 지워짐 (또는 여기서 수동 정리 가능)
        # 하지만 디버깅을 위해 일단 둠. (cleanup_temporary_resources는 원래 agent.py가 호출함)
        
    except Exception as e:
        logger.error(f"Error in process_payload_images: {e}", exc_info=True)
        return

    # 4. 요약 리포트 저장
    summary_file = output_folder / "summary.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write("\n".join(summary))
    
    logger.info("=== Stage 1 Debugging Test Completed ===")
    logger.info(f"Summary saved to: {summary_file}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_stage1_test())
