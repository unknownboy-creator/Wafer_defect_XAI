"""
mock_detector.py
die_grid를 받아서 "AI가 검출한 것처럼 보이는" detection 리스트를 만든다.
type별로 표현 방식이 다르다:
  - stain    : 연속된 면적 결함이므로 모든 die의 union을 하나의 polygon으로
               (donut 같은 ring 형태는 outer+inner contour로 hole까지 표현)
  - particle : 셀 수 있는 입자 → die별 작은 bbox
  - scratch  : 선형 결함 → die별 bbox (향후 line 표현으로 확장 가능)

좌표 체계는 wafer_renderer.py의 generate_donut_wafer_image와 정확히 일치한다.
"""

import random
import numpy as np
import cv2

from wafer_spec import WAFER_SPEC, area_px_to_mm2, image_to_wafer_mm


# wafer_renderer.py와 일치해야 함
DEFAULT_IMAGE_SIZE = 620
DEFAULT_GRID_SPAN_RATIO = 0.88
DEFAULT_PADDING = 22


def _grid_layout(rows, cols, image_size=DEFAULT_IMAGE_SIZE):
    cx, cy = image_size // 2, image_size // 2
    R = image_size // 2 - DEFAULT_PADDING
    grid_span = int(2 * R * DEFAULT_GRID_SPAN_RATIO)
    cell = grid_span // max(rows, cols)
    offset_x = cx - (cols * cell) // 2
    offset_y = cy - (rows * cell) // 2
    return offset_x, offset_y, cell


def generate(die_grid, rows=9, cols=9, image_size=DEFAULT_IMAGE_SIZE, seed=42):
    """type별로 분기한 detection 리스트.
    stain은 하나의 polygon, 나머지는 die별 bbox."""
    by_type = {"stain": [], "particle": [], "scratch": [], "other": []}
    for die in die_grid:
        if not die.get("active") or die["defect_count"] == 0:
            continue
        t = die.get("defect_type")
        (by_type[t] if t in by_type else by_type["other"]).append(die)

    detections = []

    if by_type["stain"]:
        detections.extend(_stain_region(
            by_type["stain"], rows, cols, image_size
        ))

    for t in ("particle", "scratch", "other"):
        if by_type[t]:
            detections.extend(_bbox_per_die(
                by_type[t], rows, cols, image_size, seed=seed,
            ))

    # id 재부여
    for i, det in enumerate(detections):
        det["id"] = i
    return detections


def _classify_location(dist_ratio):
    if dist_ratio < 0.33:
        return "center"
    if dist_ratio < 0.66:
        return "middle"
    return "edge"


def _classify_distribution(region_count, has_hole, location):
    """region 수 + hole 유무 + centroid 위치로 stain 분포 패턴 분류."""
    if region_count == 1:
        if has_hole:
            return "Ring (Donut)"
        if location == "center":
            return "Center Cluster"
        if location == "edge":
            return "Edge Cluster"
        return "Local Cluster"
    if region_count == 2:
        return "Dual Cluster"
    if region_count <= 4:
        return "Multi-cluster"
    return "Scattered"


def _stain_region(stain_dies, rows, cols, image_size):
    """stain die들의 union → contour polygon(s) + 4가지 분류 메트릭.
    ring 형태(donut)는 outer + inner(hole) 두 polygon으로 표현된다."""
    offset_x, offset_y, cell = _grid_layout(rows, cols, image_size)

    # 모든 stain die 픽셀 영역을 binary mask에 합침
    mask = np.zeros((image_size, image_size), dtype=np.uint8)
    for die in stain_dies:
        x = offset_x + die["col"] * cell
        y = offset_y + die["row"] * cell
        cv2.rectangle(mask, (x, y), (x + cell, y + cell), 255, -1)

    # 인접 die 사이를 자연스럽게 연결 + 경계 부드럽게
    mask = cv2.GaussianBlur(mask, (25, 25), 0)
    _, mask = cv2.threshold(mask, 100, 255, cv2.THRESH_BINARY)

    # outer + hole 모두 추출
    contours, hierarchy = cv2.findContours(
        mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE,
    )
    if not contours or hierarchy is None:
        return []

    polygons = []
    for i, cnt in enumerate(contours):
        if cv2.contourArea(cnt) < 80:
            continue
        eps = 0.003 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, eps, True)
        is_hole = hierarchy[0][i][3] != -1
        polygons.append({
            "is_hole": bool(is_hole),
            "points": [[int(p[0][0]), int(p[0][1])] for p in approx],
        })

    if not polygons:
        return []

    # severity / confidence / coverage 메타
    heavy = sum(1 for d in stain_dies if d["status"] == "defective_heavy")
    light = len(stain_dies) - heavy
    severity = (
        "heavy" if heavy > light * 2 else
        "light" if heavy == 0 else
        "mixed"
    )
    conf = round(0.80 + (heavy / max(len(stain_dies), 1)) * 0.15, 2)
    coverage_pct = round(len(stain_dies) / (rows * cols) * 100, 1)

    # ===== stain_metrics: 사용자 정의 4가지 분류 기준 =====
    # 1) 영역 개수
    region_count = sum(1 for p in polygons if not p["is_hole"])
    has_hole = any(p["is_hole"] for p in polygons)

    # 2) 면적: mask 픽셀 합 (hole은 자동 제외, mask 자체에 hole이 없음)
    area_px = int((mask > 0).sum())
    area_mm2 = round(area_px_to_mm2(area_px, image_size), 1)

    # 3) 위치: die 분포 기반 dominant zone (ring의 경우 결함이 외곽에 분포한 사실을 반영)
    #    centroid (mask 무게중심)는 sub 정보로 유지
    zone_count = {"center": 0, "middle": 0, "edge": 0}
    for d in stain_dies:
        zone_count[d.get("zone", "edge")] = zone_count.get(d.get("zone", "edge"), 0) + 1
    location = max(zone_count, key=zone_count.get)

    M = cv2.moments(mask)
    if M["m00"] > 0:
        cx_px = M["m10"] / M["m00"]
        cy_px = M["m01"] / M["m00"]
        cx_mm, cy_mm = image_to_wafer_mm(cx_px, cy_px, image_size)
        centroid_dist_mm = (cx_mm ** 2 + cy_mm ** 2) ** 0.5
    else:
        cx_mm, cy_mm, centroid_dist_mm = 0.0, 0.0, 0.0

    # 4) 분포 패턴
    distribution = _classify_distribution(region_count, has_hole, location)

    stain_metrics = {
        "region_count":  region_count,
        "has_hole":      has_hole,
        "area_mm2":      area_mm2,
        "area_px":       area_px,
        "centroid_mm":   {"x": round(cx_mm, 1), "y": round(cy_mm, 1)},
        "centroid_distance_mm": round(centroid_dist_mm, 1),
        "location":      location,
        "distribution":  distribution,
    }

    return [{
        "id": 0,
        "shape": "polygon",
        "type": "stain",
        "label": "stain region",
        "severity": severity,
        "confidence": conf,
        "polygons": polygons,
        "die_count": len(stain_dies),
        "heavy_die": heavy,
        "light_die": light,
        "coverage_pct": coverage_pct,
        "stain_metrics": stain_metrics,
    }]


def _bbox_per_die(dies, rows, cols, image_size, seed=42):
    """particle / scratch 등 셀 수 있는 결함은 die별 bbox로."""
    offset_x, offset_y, cell = _grid_layout(rows, cols, image_size)
    rng = random.Random(seed)

    detections = []
    for die in dies:
        die_x = offset_x + die["col"] * cell
        die_y = offset_y + die["row"] * cell
        heavy = die["status"] == "defective_heavy"

        scale = 0.85 if heavy else 0.55
        conf = round(rng.uniform(0.85, 0.97) if heavy
                     else rng.uniform(0.60, 0.82), 2)

        bw = int(cell * scale)
        bh = int(cell * scale)
        jx = rng.randint(-4, 4)
        jy = rng.randint(-4, 4)
        x = die_x + (cell - bw) // 2 + jx
        y = die_y + (cell - bh) // 2 + jy

        detections.append({
            "id": len(detections),
            "shape": "bbox",
            "type": die["defect_type"] or "defect",
            "label": die["defect_type"] or "defect",
            "confidence": conf,
            "bbox": [x, y, bw, bh],
            "die_ref": [die["row"], die["col"]],
            "severity": "heavy" if heavy else "light",
        })
    return detections
