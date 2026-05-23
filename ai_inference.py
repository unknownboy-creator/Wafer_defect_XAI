import cv2
import numpy as np
import time

COLORS = {
    "scratch": (231, 76, 60),
}

_last_detections = []
_last_time = 0


def run_ai_detection(frame):
    global _last_detections, _last_time

    if frame is None:
        return [], None

    now = time.time()

    if now - _last_time > 0.25:
        _last_detections = _detect_scratch_only(frame)
        _last_time = now

    overlay = draw_ai_overlay(frame, _last_detections)
    return _last_detections, overlay


def _wafer_mask(frame):
    h, w = frame.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    cx, cy = w // 2, h // 2
    radius = int(min(w, h) * 0.44)

    cv2.circle(mask, (cx, cy), radius, 255, -1)
    return mask


def _detect_scratch_only(frame):
    detections = []

    h, w = frame.shape[:2]

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = _wafer_mask(frame)

    gray = cv2.bitwise_and(gray, gray, mask=mask)

    # 🔥 대비 강화
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    blur = cv2.GaussianBlur(gray, (3, 3), 0)

    edges = cv2.Canny(blur, 80, 180)
    edges = cv2.bitwise_and(edges, edges, mask=mask)

    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=90,
        minLineLength=120,
        maxLineGap=20
    )

    if lines is None:
        return detections

    for line in lines:
        x1, y1, x2, y2 = line[0]

        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

        # 🔥 짧은 선 제거 (핵심)
        if length < 120:
            continue

        dx = abs(x2 - x1)
        dy = abs(y2 - y1)

        # 🔥 수직/수평 (die grid) 제거
        if dx < 25 or dy < 25:
            continue

        angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))

        # 🔥 거의 수평/수직 제거
        if angle < 15 or angle > 75:
            continue

        x = min(x1, x2)
        y = min(y1, y2)
        bw = max(dx, 12)
        bh = max(dy, 12)

        detections.append({
            "label": "scratch",
            "type": "scratch",
            "bbox": [int(x), int(y), int(bw), int(bh)],
            "confidence": 0.92,
        })

    return _merge_similar_scratches(detections)[:6]


def _merge_similar_scratches(detections):
    merged = []

    for d in detections:
        x, y, w, h = d["bbox"]
        keep = True

        for m in merged:
            mx, my, mw, mh = m["bbox"]

            if (
                abs(x - mx) < 50 and
                abs(y - my) < 50 and
                abs(w - mw) < 100 and
                abs(h - mh) < 100
            ):
                keep = False
                break

        if keep:
            merged.append(d)

    return merged


def draw_ai_overlay(frame, detections):
    vis = frame.copy()
    h, w = vis.shape[:2]

    cv2.circle(
        vis,
        (w // 2, h // 2),
        int(min(w, h) * 0.44),
        (47, 128, 237),
        2
    )

    cv2.rectangle(vis, (0, 0), (w, 44), (255, 255, 255), -1)

    cv2.putText(
        vis,
        "SCRATCH DEFECT AI DETECTION",
        (12, 29),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (47, 128, 237),
        2,
        cv2.LINE_AA,
    )

    cv2.putText(
        vis,
        f"SCRATCHES: {len(detections)}",
        (w - 190, 29),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (60, 60, 60),
        2,
        cv2.LINE_AA,
    )

    for d in detections:
        x, y, bw, bh = d["bbox"]
        conf = d["confidence"]
        color = COLORS["scratch"]

        cv2.rectangle(vis, (x, y), (x + bw, y + bh), color, 3)

        text = f"scratch {int(conf * 100)}%"
        (tw, th), _ = cv2.getTextSize(
            text,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            1
        )

        y_text = max(y - th - 12, 45)

        cv2.rectangle(
            vis,
            (x, y_text),
            (x + tw + 10, y_text + th + 12),
            color,
            -1
        )

        cv2.putText(
            vis,
            text,
            (x + 5, y_text + th + 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    return vis