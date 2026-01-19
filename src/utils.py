"""
유틸리티 함수 모음
한글 경로 지원 이미지 I/O 및 경로 탐색 함수를 제공합니다.
"""
import os
import cv2
import numpy as np
from pathlib import Path
from typing import Optional
import config

def find_data_directory(data_dir: Optional[str] = None) -> str:
    """
    data 폴더를 탐색하여 실제 경로를 반환합니다.
    
    현재 위치, 상위 위치 등을 탐색하여 data 폴더를 찾습니다.
    
    Args:
        data_dir: 찾을 디렉토리 이름 (기본값: config.DATA_DIR)
    
    Returns:
        찾은 data 폴더의 절대 경로
    
    Raises:
        ValueError: data 폴더를 찾을 수 없을 때
    """
    if data_dir is None:
        data_dir = config.DATA_DIR
    
    # 여러 가능한 경로 시도
    possible_paths = [
        data_dir,  # 현재 디렉토리
        os.path.join("..", data_dir),  # 상위 디렉토리
        os.path.join(os.path.dirname(os.getcwd()), data_dir),  # 절대 경로
    ]
    
    # 실제 존재하는 경로 찾기
    actual_path = None
    for path in possible_paths:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path) and os.path.isdir(abs_path):
            actual_path = abs_path
            break
    
    if actual_path is None:
        # 현재 작업 디렉토리 확인
        cwd = os.getcwd()
        # 프로젝트 루트 찾기 시도
        if "notebook" in cwd:
            # notebook 폴더에서 실행 중이면 상위로 이동
            project_root = os.path.dirname(cwd) if os.path.basename(cwd) == "notebook" else cwd
            actual_path = os.path.abspath(os.path.join(project_root, data_dir))
        else:
            actual_path = os.path.abspath(data_dir)
    
    if not os.path.exists(actual_path):
        raise ValueError(f"data 폴더를 찾을 수 없습니다. 시도한 경로: {actual_path}")
    
    return actual_path

def load_image_safe(image_path: str) -> np.ndarray:
    """
    한글 경로 및 특수 문자가 포함된 이미지를 안전하게 로드합니다.
    
    cv2.imread는 한글 경로를 제대로 처리하지 못하므로,
    np.fromfile + cv2.imdecode 패턴을 사용합니다.
    
    Args:
        image_path: 이미지 파일 경로
    
    Returns:
        로드된 이미지 (BGR 형식, numpy.ndarray)
    
    Raises:
        ValueError: 이미지를 로드할 수 없을 때
    """
    import json
    import time
    import os
    
    
    
    # 경로를 Path 객체로 변환하여 정규화
    path = Path(image_path)
    
    if not path.exists():
        raise ValueError(f"이미지 파일을 찾을 수 없습니다: {image_path}")
    
    
    
    # np.fromfile로 바이너리 데이터 읽기 (한글 경로 지원)
    img_array = np.fromfile(str(path), np.uint8)
    
    
    
    
    
    # cv2.imdecode로 이미지 디코딩
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    
    
    
    if img is None:
        raise ValueError(f"이미지를 디코딩할 수 없습니다: {image_path}")
    
    return img

def save_image_safe(image: np.ndarray, output_path: str, quality: int = 95) -> None:
    """
    한글 경로 및 특수 문자가 포함된 경로에 이미지를 안전하게 저장합니다.
    
    cv2.imwrite는 한글 경로를 제대로 처리하지 못하므로,
    cv2.imencode + 파일 쓰기 패턴을 사용합니다.
    
    Args:
        image: 저장할 이미지 (numpy.ndarray)
        output_path: 저장할 파일 경로
        quality: JPEG 품질 (0-100, 기본값: 95). PNG 파일인 경우 무시됨
    
    Raises:
        ValueError: 이미지를 저장할 수 없을 때
    """
    # 출력 디렉토리 생성
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # 파일 확장자에 따라 인코딩 방식 결정
    ext = os.path.splitext(output_path)[1].lower()
    
    if ext in ['.jpg', '.jpeg']:
        # JPEG 저장 시 품질 지정
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        success, encoded_img = cv2.imencode(ext, image, encode_params)
    elif ext == '.png':
        # PNG 저장 시 압축 레벨 지정 (0-9, 기본값: 3)
        encode_params = [cv2.IMWRITE_PNG_COMPRESSION, 3]
        success, encoded_img = cv2.imencode(ext, image, encode_params)
    else:
        # 기타 형식은 기본 인코딩
        success, encoded_img = cv2.imencode(ext, image)
    
    if not success:
        raise ValueError(f"이미지 인코딩에 실패했습니다: {output_path}")
    
    # 인코딩된 이미지를 파일로 저장 (한글 경로 지원)
    encoded_img.tofile(output_path)

def crop_roi_from_box(
    image_path: str, 
    box_2d: list, 
    output_path: Optional[str] = None,
    padding_ratio: float = 0.1
) -> str:
    """
    box_2d 좌표(0~1000 정규화)를 사용하여 ROI 크롭
    
    Args:
        image_path: 원본 이미지 경로
        box_2d: [ymin, xmin, ymax, xmax] (0~1000 정규화)
        output_path: 출력 경로 (None이면 임시 파일 생성)
        padding_ratio: 패딩 비율 (기본값: 0.1 = 10%)
    
    Returns:
        크롭된 이미지 경로
        
    Note:
        - box_2d가 [0,0,0,0]이거나 유효하지 않으면 원본 경로 반환
        - 좌표는 0~1000 범위로 정규화되어 있다고 가정
        - 변환 공식: x_pixel = xmin / 1000 * img_width
    """
    import tempfile
    
    # 유효하지 않은 box_2d 체크
    if not box_2d:
        return image_path
    
    # 1. Dictionary 형식 처리 (Pydantic model_dump 결과)
    if isinstance(box_2d, dict):
        ymin = box_2d.get('ymin', 0)
        xmin = box_2d.get('xmin', 0)
        ymax = box_2d.get('ymax', 0)
        xmax = box_2d.get('xmax', 0)
    # 2. List 형식 처리 (기존 방식)
    elif isinstance(box_2d, list) and len(box_2d) == 4:
        ymin, xmin, ymax, xmax = box_2d
    else:
        return image_path
    
    # [0,0,0,0] 체크 (None 케이스)
    if ymin == 0 and xmin == 0 and ymax == 0 and xmax == 0:
        return image_path
    
    # 좌표 유효성 체크 (정규화 좌표 0~1000)
    if xmin >= xmax or ymin >= ymax:
        return image_path

    
    # 이미지 로드
    img = load_image_safe(image_path)
    img_height, img_width = img.shape[:2]
    
    # 정규화된 좌표(0~1000)를 픽셀 좌표로 변환
    x1_pixel = int(xmin / 1000.0 * img_width)
    y1_pixel = int(ymin / 1000.0 * img_height)
    x2_pixel = int(xmax / 1000.0 * img_width)
    y2_pixel = int(ymax / 1000.0 * img_height)
    
    # 패딩 계산
    width = x2_pixel - x1_pixel
    height = y2_pixel - y1_pixel
    padding_x = int(width * padding_ratio)
    padding_y = int(height * padding_ratio)
    
    # 패딩 적용 (이미지 경계 내에서)
    x1_pixel = max(0, x1_pixel - padding_x)
    y1_pixel = max(0, y1_pixel - padding_y)
    x2_pixel = min(img_width, x2_pixel + padding_x)
    y2_pixel = min(img_height, y2_pixel + padding_y)
    
    # ROI 크롭
    cropped_img = img[y1_pixel:y2_pixel, x1_pixel:x2_pixel]
    
    # 출력 경로 설정
    if output_path is None:
        # 임시 파일 생성
        ext = Path(image_path).suffix
        fd, output_path = tempfile.mkstemp(suffix=ext, prefix="roi_crop_")
        os.close(fd)
    
    # 크롭된 이미지 저장
    save_image_safe(cropped_img, output_path)
    
    return output_path

