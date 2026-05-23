from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple
import cv2
import numpy as np

MODE_GRID = "grid"
MODE_CONTOUR = "contour"

COLOR_BOX = (0, 229, 255)
COLOR_LABEL = (255, 107, 53)
COLOR_GRID = (0, 180, 200)
COLOR_DOT = (57, 255, 20)

FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.38
FONT_THICK = 1
BOX_THICK = 1


@dataclass
class DieResult:
    die_images: List[np.ndarray]
    die_coords: List[Tuple[int, int]]
    vis_frame: np.ndarray
    die_count: int = field(init=False)

    def __post_init__(self):
        self.die_count = len(self.die_images)


def segment_die(
    frame: np.ndarray,
    mode: str = MODE_GRID,
    rows: int = 5,
    cols: int = 5,
) -> DieResult:
    if frame is None:
        raise ValueError("frame is None")

    rows = max(1, int(rows))
    cols = max(1, int(cols))

    if mode == MODE_GRID:
        return _segment_grid(frame, rows, cols)

    if mode == MODE_CONTOUR:
        return _segment_contour(frame)

    raise ValueError(f"Unknown mode: {mode}")


def draw_grid(
    frame: np.ndarray,
    rows: int = 5,
    cols: int = 5,
) -> np.ndarray:
    if frame is None:
        raise ValueError("frame is None")

    rows = max(1, int(rows))
    cols = max(1, int(cols))

    vis = frame.copy()
    h, w = vis.shape[:2]

    cell_h = h // rows
    cell_w = w // cols

    for r in range(1, rows):
        y = r * cell_h
        cv2.line(vis, (0, y), (w, y), COLOR_GRID, 1, cv2.LINE_AA)

    for c in range(1, cols):
        x = c * cell_w
        cv2.line(vis, (x, 0), (x, h), COLOR_GRID, 1, cv2.LINE_AA)

    for r in range(rows):
        for c in range(cols):
            x0 = c * cell_w
            y0 = r * cell_h
            label = f"({r},{c})"

            (_, th), _ = cv2.getTextSize(label, FONT, FONT_SCALE, FONT_THICK)
            tx = x0 + 4
            ty = y0 + th + 4

            cv2.putText(vis, label, (tx + 1, ty + 1),
                        FONT, FONT_SCALE, (0, 0, 0),
                        FONT_THICK + 1, cv2.LINE_AA)

            cv2.putText(vis, label, (tx, ty),
                        FONT, FONT_SCALE, COLOR_LABEL,
                        FONT_THICK, cv2.LINE_AA)

    return vis


def _segment_grid(frame: np.ndarray, rows: int, cols: int) -> DieResult:
    h, w = frame.shape[:2]

    cell_h = h // rows
    cell_w = w // cols

    die_images = []
    die_coords = []

    for r in range(rows):
        for c in range(cols):
            y0 = r * cell_h
            y1 = (r + 1) * cell_h if r < rows - 1 else h
            x0 = c * cell_w
            x1 = (c + 1) * cell_w if c < cols - 1 else w

            crop = frame[y0:y1, x0:x1].copy()
            die_images.append(crop)
            die_coords.append((r, c))

    vis = _draw_grid_overlay(frame, rows, cols, cell_h, cell_w)

    return DieResult(
        die_images=die_images,
        die_coords=die_coords,
        vis_frame=vis,
    )


def _draw_grid_overlay(
    frame: np.ndarray,
    rows: int,
    cols: int,
    cell_h: int,
    cell_w: int,
) -> np.ndarray:
    h, w = frame.shape[:2]
    vis = frame.copy()

    for r in range(rows):
        for c in range(cols):
            x0 = c * cell_w
            y0 = r * cell_h
            x1 = (c + 1) * cell_w if c < cols - 1 else w
            y1 = (r + 1) * cell_h if r < rows - 1 else h

            cv2.rectangle(vis, (x0, y0), (x1 - 1, y1 - 1), COLOR_BOX, BOX_THICK)
            _draw_corner_mark(vis, x0, y0)

            label = f"({r},{c})"
            (_, th), _ = cv2.getTextSize(label, FONT, FONT_SCALE, FONT_THICK)
            tx = x0 + 4
            ty = y0 + th + 4

            cv2.putText(vis, label, (tx + 1, ty + 1),
                        FONT, FONT_SCALE, (0, 0, 0),
                        FONT_THICK + 1, cv2.LINE_AA)

            cv2.putText(vis, label, (tx, ty),
                        FONT, FONT_SCALE, COLOR_LABEL,
                        FONT_THICK, cv2.LINE_AA)

    return vis


def _segment_contour(frame: np.ndarray) -> DieResult:
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    scale = 0.5
    small = cv2.resize(gray, (0, 0), fx=scale, fy=scale)

    blurred = cv2.GaussianBlur(small, (5, 5), 0)

    _, thresh = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(
        closed,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    min_area = h * w * 0.001
    max_area = h * w * 0.25
    max_aspect = 5.0

    bboxes = []

    for cnt in contours:
        cnt_full = (cnt / scale).astype(np.int32)
        x, y, bw, bh = cv2.boundingRect(cnt_full)

        area = bw * bh
        aspect = max(bw, bh) / max(min(bw, bh), 1)

        if min_area <= area <= max_area and aspect <= max_aspect:
            bboxes.append((x, y, bw, bh))

    bboxes.sort(key=lambda b: (b[1], b[0]))

    die_images = []
    die_coords = []
    vis = frame.copy()

    for idx, (x, y, bw, bh) in enumerate(bboxes):
        x0 = max(x, 0)
        y0 = max(y, 0)
        x1 = min(x + bw, w)
        y1 = min(y + bh, h)

        crop = frame[y0:y1, x0:x1].copy()
        die_images.append(crop)

        # contour는 임시 좌표. wafer map 메인은 grid 사용 권장.
        die_coords.append((idx, 0))

        cv2.rectangle(vis, (x0, y0), (x1, y1), COLOR_BOX, BOX_THICK)
        _draw_corner_mark(vis, x0, y0)

        label = f"({idx},0)"
        (_, th), _ = cv2.getTextSize(label, FONT, FONT_SCALE, FONT_THICK)

        tx = x0 + 4
        ty = y0 + th + 4

        cv2.putText(vis, label, (tx + 1, ty + 1),
                    FONT, FONT_SCALE, (0, 0, 0),
                    FONT_THICK + 1, cv2.LINE_AA)

        cv2.putText(vis, label, (tx, ty),
                    FONT, FONT_SCALE, COLOR_LABEL,
                    FONT_THICK, cv2.LINE_AA)

    return DieResult(
        die_images=die_images,
        die_coords=die_coords,
        vis_frame=vis,
    )


def _draw_corner_mark(img: np.ndarray, x: int, y: int, size: int = 5) -> None:
    cv2.line(img, (x - size, y), (x + size, y), COLOR_DOT, 1, cv2.LINE_AA)
    cv2.line(img, (x, y - size), (x, y + size), COLOR_DOT, 1, cv2.LINE_AA)