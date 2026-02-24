import os
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
