"""
simulator.py
데모용 결함 분포 mock 생성기.
WaferMap.add_defects()에 그대로 전달 가능한 dict 리스트를 반환한다.
결정적이므로 슬라이드/시연에 안정적이다.
"""


def _radius_ratio(i, j, rows, cols):
    cy, cx = (rows - 1) / 2, (cols - 1) / 2
    rmax = (cy ** 2 + cx ** 2) ** 0.5 or 1.0
    return ((i - cy) ** 2 + (j - cx) ** 2) ** 0.5 / rmax


def _make(i, j, dtype, count, conf=0.85):
    out = []
    for k in range(count):
        out.append({
            "die": [int(i), int(j)],
            "type": dtype,
            "bbox": [10 + k * 6, 10 + k * 6, 8, 8],
            "confidence": conf,
        })
    return out


def generate_donut(rows, cols):
    """중간 반경(0.35~0.70)에 stain 환형 분포."""
    defects = []
    for i in range(rows):
        for j in range(cols):
            r = _radius_ratio(i, j, rows, cols)
            if 0.35 <= r <= 0.70:
                count = 3 if 0.45 <= r <= 0.60 else 1
                defects += _make(i, j, "stain", count)
    return defects


def generate_edge_ring(rows, cols):
    """외곽(0.70~1.0)에 particle/stain 혼합."""
    defects = []
    for i in range(rows):
        for j in range(cols):
            r = _radius_ratio(i, j, rows, cols)
            if r >= 0.70:
                count = 2 if r >= 0.85 else 1
                defects += _make(i, j, "particle", count)
    return defects


def generate_center(rows, cols):
    """중심부(<0.30)에 stain 집중."""
    defects = []
    for i in range(rows):
        for j in range(cols):
            r = _radius_ratio(i, j, rows, cols)
            if r < 0.30:
                defects += _make(i, j, "stain", 3)
    return defects


def generate_scratch_line(rows, cols):
    """특정 행에 scratch 집중."""
    defects = []
    target_row = rows // 2
    for j in range(cols):
        defects += _make(target_row, j, "scratch", 2)
    return defects


GENERATORS = {
    "donut": generate_donut,
    "edge": generate_edge_ring,
    "center": generate_center,
    "scratch": generate_scratch_line,
}
