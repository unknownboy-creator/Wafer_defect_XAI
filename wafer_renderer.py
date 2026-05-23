"""
wafer_renderer.py
시나리오 시연용 mock wafer 사진 생성기.

실제 deep learning 입력 이미지가 없으므로 OpenCV로
"실사처럼 보이는" wafer 사진을 합성한다.

- 9x9 die grid (active radius 0.73 → 57 active dies)
- 시나리오: middle 반경에 어두운 stain ring (Donut)
- 사용 예:
    python wafer_renderer.py            # 기본 경로에 donut 이미지 생성
"""

import os
import numpy as np
import cv2


# 기본 출력 위치
DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "static", "img", "wafer_donut_input.jpg",
)


def _add_rainbow_edge(img, cx, cy, R):
    """wafer 외곽에 무지개 광택 효과를 더한다."""
    overlay = img.copy()
    # 외곽 굵은 링을 다중 색으로 stroke
    bands = [
        (R + 2,  (200, 120, 180), 6),   # magenta tint
        (R + 0,  (120, 200, 200), 4),   # cyan
        (R - 4,  (180, 200, 130), 3),   # green-ish
    ]
    for radius, color, thick in bands:
        cv2.circle(overlay, (cx, cy), radius, color, thick, cv2.LINE_AA)
    return cv2.addWeighted(img, 0.75, overlay, 0.25, 0)


def _draw_die_grid(img, cx, cy, R, rows=9, cols=9, active_ratio=0.73):
    """die grid를 그린다.
    반환: die 좌표 리스트 [(r, c, x, y, cell_size)]"""
    grid_span = int(2 * R * 0.88)
    cell = grid_span // max(rows, cols)
    offset_x = cx - (cols * cell) // 2
    offset_y = cy - (rows * cell) // 2

    cy_idx = (rows - 1) / 2
    cx_idx = (cols - 1) / 2
    rmax = (cy_idx ** 2 + cx_idx ** 2) ** 0.5 or 1.0

    dies = []

    for r in range(rows):
        for c in range(cols):
            dr = (((r - cy_idx) ** 2 + (c - cx_idx) ** 2) ** 0.5) / rmax
            if dr > active_ratio:
                continue
            x = offset_x + c * cell
            y = offset_y + r * cell

            # die 본체 (다소 거친 회색 톤, 약간의 노이즈)
            base = np.full((cell - 3, cell - 3, 3), 165, dtype=np.uint8)
            noise = np.random.randint(-12, 13, base.shape, dtype=np.int16)
            base = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            img[y + 1:y + cell - 2, x + 1:x + cell - 2] = base

            # die 경계 (얇은 어두운 선)
            cv2.rectangle(
                img,
                (x, y), (x + cell - 2, y + cell - 2),
                (95, 95, 100), 1, cv2.LINE_AA,
            )
            dies.append((r, c, x, y, cell))

    return dies


def _overlay_donut_stain(img, cx, cy, R, intensity=0.55):
    """middle 반경에 부드러운 donut 형태의 어두운 stain을 합성한다."""
    H, W = img.shape[:2]
    mask = np.zeros((H, W), dtype=np.float32)

    # 중간 반경 ring (R * 0.4 ~ R * 0.72)
    inner = int(R * 0.40)
    outer = int(R * 0.72)
    # 그라데이션 ring: 안/밖으로 갈수록 옅게
    for rr in range(inner, outer + 1):
        t = 1.0 - abs(rr - (inner + outer) / 2) / ((outer - inner) / 2)
        t = max(0.0, min(1.0, t))
        cv2.circle(mask, (cx, cy), rr, t, 1, cv2.LINE_AA)

    # 블러로 부드러운 ring으로
    mask = cv2.GaussianBlur(mask, (61, 61), 0)
    mask = np.clip(mask / (mask.max() or 1.0), 0, 1)

    # 어두운 갈색 톤으로 합성
    stain_color = np.array([55, 70, 95], dtype=np.float32)  # BGR (살짝 brown)
    img_f = img.astype(np.float32)
    for ch in range(3):
        img_f[:, :, ch] = (
            img_f[:, :, ch] * (1 - mask * intensity) +
            stain_color[ch] * (mask * intensity)
        )
    return np.clip(img_f, 0, 255).astype(np.uint8)


def generate_donut_wafer_image(out_path=DEFAULT_OUT, size=620, seed=42):
    """Donut 시나리오용 mock wafer 사진을 합성하고 저장한다."""
    np.random.seed(seed)

    H = W = size
    # 옅은 배경 (실사 사진의 흰 배경 느낌)
    img = np.full((H, W, 3), 235, dtype=np.uint8)
    # 약한 노이즈
    noise = np.random.randint(-6, 7, img.shape, dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    cx, cy = W // 2, H // 2
    R = size // 2 - 22

    # wafer 원반 (어두운 실리콘 톤)
    wafer = np.full((H, W, 3), 100, dtype=np.uint8)
    wnoise = np.random.randint(-8, 9, wafer.shape, dtype=np.int16)
    wafer = np.clip(wafer.astype(np.int16) + wnoise, 0, 255).astype(np.uint8)

    mask = np.zeros((H, W), dtype=np.uint8)
    cv2.circle(mask, (cx, cy), R, 255, -1, cv2.LINE_AA)
    img[mask > 0] = wafer[mask > 0]

    # 무지개 외곽 광택
    img = _add_rainbow_edge(img, cx, cy, R)

    # die grid
    _draw_die_grid(img, cx, cy, R, rows=9, cols=9, active_ratio=0.73)

    # donut stain overlay
    img = _overlay_donut_stain(img, cx, cy, R, intensity=0.6)

    # 외곽 wafer outline (검은 테두리)
    cv2.circle(img, (cx, cy), R, (40, 40, 45), 2, cv2.LINE_AA)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    return out_path


if __name__ == "__main__":
    path = generate_donut_wafer_image()
    print(f"Generated: {path}")
