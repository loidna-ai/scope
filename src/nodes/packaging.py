"""
패키징 노드
LLM 분석을 위한 데이터를 준비하고 JSON 형식으로 변환합니다.
"""
from typing import Dict, Any
import json
import base64
import cv2
import numpy as np
from datetime import datetime
from src.state import GraphState


def encode_image_base64(img: np.ndarray, format: str = 'PNG') -> str:
    """
    이미지를 base64 문자열로 인코딩합니다.
    
    Args:
        img: 인코딩할 이미지 (numpy.ndarray)
        format: 이미지 형식 ('PNG' 또는 'JPEG')
    
    Returns:
        base64 인코딩된 문자열
    """
    if format == 'PNG':
        _, buffer = cv2.imencode('.png', img)
    else:
        _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    
    return base64.b64encode(buffer).decode('utf-8')


def encode_image_bytes(img: np.ndarray, format: str = 'PNG') -> bytes:
    """
    이미지를 바이트 데이터로 인코딩합니다 (Base64 없이).
    화질 손실을 방지하기 위해 최고 품질 설정을 사용합니다.
    
    Args:
        img: 인코딩할 이미지 (numpy.ndarray)
        format: 이미지 형식 ('PNG' 또는 'JPEG')
    
    Returns:
        바이트 데이터 (Binary Blob)
    """
    if format == 'PNG':
        # PNG: 무손실 압축
        _, buffer = cv2.imencode('.png', img, [cv2.IMWRITE_PNG_COMPRESSION, 0])
    else:
        # JPEG: 품질 100 (화질 손실 방지, 미세한 구멍(Void) 보존)
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 100]
        _, buffer = cv2.imencode('.jpg', img, encode_param)
    
    return buffer.tobytes()


def create_data_description(analysis_data: dict) -> str:
    """
    순수 데이터 설명을 생성합니다 (지시문 없음).
    "증거물 패키지" 형식으로 데이터만 제공합니다.
    
    Args:
        analysis_data: 분석 데이터 딕셔너리
    
    Returns:
        지시문이 제거된 순수 데이터 설명 문자열
    """
    # 메트릭스 JSON 생성
    metrics_json = json.dumps({
        "circularity": analysis_data['metrics']['morphology']['circularity'],
        "solidity": analysis_data['metrics']['morphology']['solidity'],
        "area": analysis_data['metrics']['morphology']['area'],
        "area_ratio": analysis_data['metrics']['morphology']['area_ratio']
    }, ensure_ascii=False)
    
    # 비교 분석 데이터 JSON 생성
    comparison_json = json.dumps({
        "brightness_change": analysis_data['comparison']['enhancer_to_filter']['brightness_change'],
        "pixel_difference_mean": analysis_data['comparison']['enhancer_to_filter']['pixel_difference_mean'],
        "pixel_difference_max": analysis_data['comparison']['enhancer_to_filter']['pixel_difference_max']
    }, ensure_ascii=False)
    
    # 순수 데이터 설명 생성 (지시문 없음)
    description = f"""단락흔 이미지 처리 파이프라인 분석 데이터

[처리 단계]
1. Enhancer: Real-ESRGAN 4x 초해상도 확대
2. Filter: CLAHE 텍스처 강조 필터
3. Metrics: 형태학적 분석

[형태학적 메트릭스]
{metrics_json}

[비교 분석 데이터]
{comparison_json}

[이미지 매핑]
- 첫 번째 이미지: Enhancer 결과 (Real-ESRGAN 4x 확대)
- 두 번째 이미지: Filter 결과 (CLAHE 텍스처 강조)
- 세 번째 이미지: Analysis Mask (형태학적 분석 이진 마스크)"""
    
    return description


def get_image_stats(img: np.ndarray) -> Dict[str, Any]:
    """
    이미지 통계 정보를 추출합니다.
    
    Args:
        img: 분석할 이미지
    
    Returns:
        통계 정보 딕셔너리
    """
    # 그레이스케일 변환
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    
    return {
        'width': int(img.shape[1]),
        'height': int(img.shape[0]),
        'channels': int(img.shape[2]) if len(img.shape) == 3 else 1,
        'total_pixels': int(img.shape[0] * img.shape[1]),
        'pixel_range': {
            'min': int(img.min()),
            'max': int(img.max())
        },
        'brightness': {
            'mean': float(gray.mean()),
            'std': float(gray.std()),
            'median': float(np.median(gray))
        }
    }


def prepare_llm_analysis_data(
    enhanced_img: np.ndarray,
    filtered_img: np.ndarray,
    metrics: dict,
    binary_mask: np.ndarray
) -> Dict[str, Any]:
    """
    LLM 분석을 위한 표준 형식 데이터를 준비합니다.
    
    Args:
        enhanced_img: 향상된 이미지
        filtered_img: 필터 적용 이미지
        metrics: 형태학적 메트릭스
        binary_mask: 이진 마스크
    
    Returns:
        분석 데이터 딕셔너리
    """
    # 데이터 구조화
    analysis_data = {
        # 메타데이터
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'pipeline': 'arc_bead_analysis',
            'stages': ['enhancer', 'filter', 'metrics']
        },
        
        # 이미지 데이터 (base64 인코딩)
        'images': {
            'enhanced': {
                'data': encode_image_base64(enhanced_img, 'PNG'),
                'data_bytes': base64.b64encode(encode_image_bytes(enhanced_img, 'PNG')).decode('utf-8'),  # 바이트 데이터 (선택적, 호환성)
                'format': 'PNG',
                'encoding': 'base64',
                'statistics': get_image_stats(enhanced_img),
                'description': 'Real-ESRGAN 4x super-resolution enhanced image'
            },
            'filtered': {
                'data': encode_image_base64(filtered_img, 'PNG'),
                'data_bytes': base64.b64encode(encode_image_bytes(filtered_img, 'PNG')).decode('utf-8'),  # 바이트 데이터 (선택적, 호환성)
                'format': 'PNG',
                'encoding': 'base64',
                'statistics': get_image_stats(filtered_img),
                'description': 'CLAHE filtered image for texture enhancement',
                'filter_type': 'CLAHE',
                'filter_params': {
                    'clipLimit': 4.0,
                    'tileGridSize': [8, 8]
                }
            },
            'analysis_mask': {
                'data': encode_image_base64(binary_mask, 'PNG'),
                'data_bytes': base64.b64encode(encode_image_bytes(binary_mask, 'PNG')).decode('utf-8'),  # 바이트 데이터 (선택적, 호환성)
                'format': 'PNG',
                'encoding': 'base64',
                'description': 'Binary mask from morphological analysis'
            }
        },
        
        # 분석 메트릭스 (숫자 데이터)
        'metrics': {
            'morphology': {
                'circularity': float(metrics['circularity']),
                'solidity': float(metrics['solidity']),
                'area': int(metrics['area']),
                'area_ratio': float(
                    (metrics['area'] / (filtered_img.shape[0] * filtered_img.shape[1])) * 100
                )
            }
        },
        
        # 비교 분석 데이터
        'comparison': {
            'enhancer_to_filter': {
                'brightness_change': float(
                    cv2.cvtColor(filtered_img, cv2.COLOR_BGR2GRAY).mean() - 
                    cv2.cvtColor(enhanced_img, cv2.COLOR_BGR2GRAY).mean()
                ),
                'pixel_difference_mean': float(
                    np.abs(filtered_img.astype(float) - enhanced_img.astype(float)).mean()
                ),
                'pixel_difference_max': float(
                    np.abs(filtered_img.astype(float) - enhanced_img.astype(float)).max()
                )
            },
            'filter_to_metrics': {
                'analyzed_area_coverage': float(
                    (metrics['area'] / (enhanced_img.shape[0] * enhanced_img.shape[1])) * 100
                ),
                'morphology_characteristics': {
                    'shape_regularity': metrics['circularity'],
                    'internal_density': metrics['solidity']
                }
            }
        }
    }
    
    return analysis_data


def to_gemini_vertex_ai_format(analysis_data: dict) -> list:
    """
    Vertex AI Gemini API 형식으로 변환합니다.
    Format 2 방식: 텍스트와 이미지를 분리하여 리스트로 전송 (가장 효율적).
    바이트 데이터(Binary Blob)를 사용하여 Vision Encoder로 직행합니다.
    
    Args:
        analysis_data: 분석 데이터 딕셔너리
    
    Returns:
        Gemini Part 구조 리스트 (JSON 저장용 Base64 문자열 포함)
    
    Note:
        JSON 저장 시에는 Base64 문자열을 사용하지만, 실제 SDK 사용 시에는
        바이트 데이터로 변환하여 사용할 수 있습니다.
    """
    # #region agent log
    import json
    import time
    import sys
    try:
        import psutil
        mem_before = psutil.Process().memory_info().rss / 1024 / 1024  # MB
    except:
        mem_before = None
    try:
        with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"workflow-debug","runId":"run1","hypothesisId":"C","location":"packaging.py:to_gemini_vertex_ai_format","message":"Format conversion start","data":{"has_images":bool(analysis_data.get("images")),"image_keys":list(analysis_data.get("images",{}).keys()) if analysis_data.get("images") else None,"mem_before_mb":mem_before},"timestamp":int(time.time()*1000)})+'\n')
    except: pass
    # #endregion
    # 지시문 제거된 순수 데이터 설명 생성
    data_description = create_data_description(analysis_data)
    
    # Base64 문자열을 디코딩하여 바이트로 변환한 후, 품질 100으로 재인코딩
    # (화질 손실 방지: 미세한 구멍(Void) 보존)
    enhanced_base64_str = analysis_data['images']['enhanced']['data']
    filtered_base64_str = analysis_data['images']['filtered']['data']
    mask_base64_str = analysis_data['images']['analysis_mask']['data']
    
    # #region agent log
    try:
        with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"workflow-debug","runId":"run1","hypothesisId":"C","location":"packaging.py:to_gemini_vertex_ai_format","message":"Base64 decode start","data":{"enhanced_base64_len":len(enhanced_base64_str),"filtered_base64_len":len(filtered_base64_str),"mask_base64_len":len(mask_base64_str)},"timestamp":int(time.time()*1000)})+'\n')
    except: pass
    # #endregion
    
    # Base64 디코딩 → numpy 배열로 변환 → 바이트로 재인코딩 (품질 100)
    enhanced_bytes = base64.b64decode(enhanced_base64_str)
    enhanced_img = cv2.imdecode(np.frombuffer(enhanced_bytes, np.uint8), cv2.IMREAD_COLOR)
    enhanced_bytes_high_quality = encode_image_bytes(enhanced_img, 'PNG')
    
    filtered_bytes = base64.b64decode(filtered_base64_str)
    filtered_img = cv2.imdecode(np.frombuffer(filtered_bytes, np.uint8), cv2.IMREAD_COLOR)
    filtered_bytes_high_quality = encode_image_bytes(filtered_img, 'PNG')
    
    mask_bytes = base64.b64decode(mask_base64_str)
    mask_img = cv2.imdecode(np.frombuffer(mask_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    mask_bytes_high_quality = encode_image_bytes(mask_img, 'PNG')
    
    # #region agent log
    try:
        mem_after_decode = psutil.Process().memory_info().rss / 1024 / 1024 if 'psutil' in sys.modules and mem_before else None
        with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"workflow-debug","runId":"run1","hypothesisId":"C","location":"packaging.py:to_gemini_vertex_ai_format","message":"Image decode complete","data":{"enhanced_bytes_len":len(enhanced_bytes_high_quality),"filtered_bytes_len":len(filtered_bytes_high_quality),"mask_bytes_len":len(mask_bytes_high_quality),"mem_after_decode_mb":mem_after_decode,"mem_diff_mb":mem_after_decode-mem_before if mem_before and mem_after_decode else None},"timestamp":int(time.time()*1000)})+'\n')
    except: pass
    # #endregion
    
    # Base64로 변환 (JSON 직렬화를 위해)
    enhanced_base64 = base64.b64encode(enhanced_bytes_high_quality).decode('utf-8')
    filtered_base64 = base64.b64encode(filtered_bytes_high_quality).decode('utf-8')
    mask_base64 = base64.b64encode(mask_bytes_high_quality).decode('utf-8')
    
    # #region agent log
    try:
        mem_final = psutil.Process().memory_info().rss / 1024 / 1024 if 'psutil' in sys.modules and mem_before else None
        with open(r'c:\Users\user\Documents\Project\P_04_Scope\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"workflow-debug","runId":"run1","hypothesisId":"C","location":"packaging.py:to_gemini_vertex_ai_format","message":"Format conversion complete","data":{"enhanced_base64_final_len":len(enhanced_base64),"filtered_base64_final_len":len(filtered_base64),"mask_base64_final_len":len(mask_base64),"mem_final_mb":mem_final,"total_mem_diff_mb":mem_final-mem_before if mem_before and mem_final else None},"timestamp":int(time.time()*1000)})+'\n')
    except: pass
    # #endregion
    
    # Gemini Part 구조 생성 (Format 2: 텍스트와 이미지 분리)
    contents = [
        data_description,  # Part 1: 텍스트 (순수 데이터만, 지시문 없음)
        {
            "inline_data": {
                "mime_type": "image/png",
                "data": enhanced_base64  # Base64 문자열 (JSON 저장용, 품질 100)
            }
        },
        {
            "inline_data": {
                "mime_type": "image/png",
                "data": filtered_base64  # Base64 문자열 (JSON 저장용, 품질 100)
            }
        },
        {
            "inline_data": {
                "mime_type": "image/png",
                "data": mask_base64  # Base64 문자열 (JSON 저장용, 품질 100)
            }
        }
    ]
    
    return contents


def packaging_node(state: GraphState) -> Dict[str, Any]:
    """
    패키징 노드
    
    Args:
        state: 그래프 상태
    
    Returns:
        업데이트할 상태 필드 (Partial State)
    """
    # 필수 데이터 확인
    required_fields = ['enhanced_image', 'filtered_image', 'metrics', 'binary_mask']
    missing_fields = [field for field in required_fields if state.get(field) is None]
    
    if missing_fields:
        return {
            "errors": [f"패키징 실패: 필수 데이터가 없습니다: {', '.join(missing_fields)}"]
        }
    
    try:
        # LLM 분석 데이터 준비
        analysis_data = prepare_llm_analysis_data(
            state["enhanced_image"],
            state["filtered_image"],
            state["metrics"],
            state["binary_mask"]
        )
        
        return {
            "analysis_data": analysis_data
        }
    except Exception as e:
        error_msg = f"패키징 실패: {str(e)}"
        return {
            "errors": [error_msg]
        }

