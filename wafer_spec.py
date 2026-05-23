"""
wafer_spec.py
시연 시나리오에서 가정하는 실제 wafer 규격과 픽셀↔실측(mm) 변환 헬퍼.

데모용 입력 이미지(620×620)는 300mm wafer를 가정하므로
모든 면적/길이 메트릭은 이 비율로 환산한다.
"""

# ====== 시나리오 wafer 규격 ======
WAFER_SPEC = {
    "diameter_mm":   300,
    "radius_mm":     150,
    "die_count":     57,
    "die_size_mm":   28,         # 가로 = 세로
    "die_area_mm2":  28 * 28,    # 784
    "pitch_mm":      30,
}


def px_per_mm(image_size_px, diameter_mm=None):
    diameter_mm = diameter_mm or WAFER_SPEC["diameter_mm"]
    return image_size_px / diameter_mm


def px_to_mm(length_px, image_size_px, diameter_mm=None):
    return length_px / px_per_mm(image_size_px, diameter_mm)


def area_px_to_mm2(area_px, image_size_px, diameter_mm=None):
    r = 1.0 / px_per_mm(image_size_px, diameter_mm)
    return area_px * (r ** 2)


def image_to_wafer_mm(x_px, y_px, image_size_px, diameter_mm=None):
    """이미지 좌표(좌상단 원점) → wafer center 기준 mm 좌표(우측+, 상측+)."""
    cx = image_size_px / 2
    cy = image_size_px / 2
    scale = 1.0 / px_per_mm(image_size_px, diameter_mm)
    return ((x_px - cx) * scale, (cy - y_px) * scale)
