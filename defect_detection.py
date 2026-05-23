import cv2
import numpy as np


def detect_defects(die_img):
    results = []

    if die_img is None or die_img.size == 0:
        return results

    gray = cv2.cvtColor(die_img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    _, th = cv2.threshold(
        blur, 0, 255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    kernel = np.ones((3, 3), np.uint8)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(
        th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    h, w = gray.shape

    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        area = bw * bh

        if area < 10:
            continue

        aspect = max(bw, bh) / max(min(bw, bh), 1)

        if area < 200 and aspect < 2:
            dtype = "particle"
            conf = 0.60

        elif aspect > 5:
            dtype = "scratch"
            conf = 0.70

        elif area > w * h * 0.05:
            dtype = "stain"
            conf = 0.65

        else:
            continue

        results.append({
            "type": dtype,
            "bbox": [int(x), int(y), int(bw), int(bh)],
            "confidence": float(conf)
        })

    return results


def draw_defects_on_frame(frame, defects, rows, cols):
    vis = frame.copy()
    h, w = vis.shape[:2]

    rows = max(1, int(rows))
    cols = max(1, int(cols))

    cell_h = h // rows
    cell_w = w // cols

    for d in defects:
        i, j = d["die"]
        x, y, bw, bh = d["bbox"]

        global_x = j * cell_w + x
        global_y = i * cell_h + y

        dtype = d["type"]

        if dtype == "particle":
            color = (0, 180, 0)
        elif dtype == "scratch":
            color = (0, 0, 255)
        else:
            color = (255, 120, 0)

        cv2.rectangle(
            vis,
            (global_x, global_y),
            (global_x + bw, global_y + bh),
            color,
            2
        )

        cv2.putText(
            vis,
            dtype,
            (global_x, max(global_y - 5, 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA
        )

    return vis