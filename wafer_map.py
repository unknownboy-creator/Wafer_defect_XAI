"""
wafer_map.py
Die별 defect 결과를 누적하고 wafer-level pattern을 해석하는 모듈
"""

import numpy as np


ZONE_CENTER = "center"
ZONE_MIDDLE = "middle"
ZONE_EDGE = "edge"


class WaferMap:
    def __init__(self, rows=5, cols=5):
        self.rows = rows
        self.cols = cols

        self.count_map = np.zeros((rows, cols), dtype=int)

        self.type_maps = {
            "particle": np.zeros((rows, cols), dtype=int),
            "scratch": np.zeros((rows, cols), dtype=int),
            "stain": np.zeros((rows, cols), dtype=int),
        }

    def reset(self):
        self.count_map[:, :] = 0
        for k in self.type_maps:
            self.type_maps[k][:, :] = 0

    def add_defects(self, defects):
        for d in defects:
            i, j = d["die"]
            dtype = d["type"]

            if 0 <= i < self.rows and 0 <= j < self.cols:
                self.count_map[i, j] += 1

                if dtype in self.type_maps:
                    self.type_maps[dtype][i, j] += 1

    def get_zone(self, i, j):
        center_i = (self.rows - 1) / 2
        center_j = (self.cols - 1) / 2

        dist = ((i - center_i) ** 2 + (j - center_j) ** 2) ** 0.5
        max_dist = (center_i ** 2 + center_j ** 2) ** 0.5

        ratio = dist / max_dist if max_dist > 0 else 0

        if ratio < 0.33:
            return ZONE_CENTER
        elif ratio < 0.66:
            return ZONE_MIDDLE
        else:
            return ZONE_EDGE

    def zone_summary(self):
        summary = {
            ZONE_CENTER: 0,
            ZONE_MIDDLE: 0,
            ZONE_EDGE: 0,
        }

        for i in range(self.rows):
            for j in range(self.cols):
                zone = self.get_zone(i, j)
                summary[zone] += int(self.count_map[i, j])

        return summary

    def classify_pattern(self):
        total = int(self.count_map.sum())

        if total == 0:
            return {
                "pattern": "Normal",
                "reason": "검출된 defect가 없습니다.",
                "feedback": "현재 프레임 기준 이상 징후가 약합니다."
            }

        zones = self.zone_summary()

        edge_ratio = zones[ZONE_EDGE] / total
        center_ratio = zones[ZONE_CENTER] / total
        middle_ratio = zones[ZONE_MIDDLE] / total

        # 선형 scratch 판단
        row_sum = self.count_map.sum(axis=1)
        col_sum = self.count_map.sum(axis=0)

        if row_sum.max() / total > 0.6 or col_sum.max() / total > 0.6:
            return {
                "pattern": "Scratch Line",
                "reason": "특정 행 또는 열에 defect가 집중되어 있습니다.",
                "feedback": "스캔 방향 또는 장비 이동축 관련 이상 가능성이 있습니다."
            }

        if edge_ratio > 0.55:
            return {
                "pattern": "Edge-Ring",
                "reason": f"Edge zone defect 비율이 {edge_ratio:.2f}로 높습니다.",
                "feedback": "웨이퍼 외곽 공정 조건 또는 edge handling 문제 가능성이 있습니다."
            }

        if center_ratio > 0.45:
            return {
                "pattern": "Center",
                "reason": f"Center zone defect 비율이 {center_ratio:.2f}로 높습니다.",
                "feedback": "중앙부 압력, 조명, 초점 또는 공정 균일도 문제 가능성이 있습니다."
            }

        if middle_ratio > 0.5:
            return {
                "pattern": "Donut",
                "reason": f"Middle zone defect 비율이 {middle_ratio:.2f}로 높습니다.",
                "feedback": "환형 분포 가능성이 있어 공정 균일도 확인이 필요합니다."
            }

        return {
            "pattern": "Random",
            "reason": "defect가 특정 zone에 강하게 집중되지 않습니다.",
            "feedback": "오염 입자 또는 랜덤성 결함 가능성이 있습니다."
        }

    def to_json(self):
        pattern_info = self.classify_pattern()

        return {
            "rows": self.rows,
            "cols": self.cols,
            "count_map": self.count_map.tolist(),
            "particle_map": self.type_maps["particle"].tolist(),
            "scratch_map": self.type_maps["scratch"].tolist(),
            "stain_map": self.type_maps["stain"].tolist(),
            "zone_summary": self.zone_summary(),
            "pattern": pattern_info["pattern"],
            "reason": pattern_info["reason"],
            "feedback": pattern_info["feedback"],
            "total_defects": int(self.count_map.sum()),
        }