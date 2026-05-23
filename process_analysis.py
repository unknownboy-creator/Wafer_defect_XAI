"""
process_analysis.py
패턴/zone 분포를 받아 공정 원인, 레시피 인사이트, 결론을 생성한다.

도메인 지식은 코드가 아닌 데이터(dict)로 표현하여
새 시나리오 추가가 코드 변경 없이 가능하도록 설계했다.
"""

# 패턴 -> 원인 후보: (name, base_weight, hint)
PATTERN_CAUSES = {
    "Donut": [
        ("Gas flow imbalance",            0.78,
         "중앙·외곽 대비 중간 반경의 막 두께가 어긋남"),
        ("Plasma density variation",      0.65,
         "환형 플라즈마 분포로 중간 zone의 증착/에칭률 편차"),
        ("Chuck temperature instability", 0.52,
         "척의 중간 반경 온도 링이 막 형성 균일도에 영향"),
        ("Wafer rotation issue",          0.40,
         "회전 비대칭이 환형 패턴으로 누적"),
    ],
    "Edge-Ring": [
        ("Edge bead removal failure",     0.80,
         "EBR 노즐 또는 용제 압력 이상으로 외곽 잔류물"),
        ("Chuck edge contact",            0.62,
         "외곽 핀/링 오염 또는 접촉 결함"),
        ("Edge gas curtain weak",         0.50,
         "에지부 가스 커튼 약화로 외곽 오염 유입"),
    ],
    "Center": [
        ("Showerhead center clog",        0.74,
         "샤워헤드 중앙 노즐 막힘 가능성"),
        ("Focus/illumination drift",      0.55,
         "광학 정렬 또는 조명 균일도 편차"),
        ("Center pressure spike",         0.48,
         "중앙부 압력 분포 이상"),
    ],
    "Scratch Line": [
        ("Transport arm scratch",         0.82,
         "이송 암 접촉 또는 긁힘"),
        ("Polish pad groove",             0.50,
         "CMP 패드 그루브 또는 패드 결함"),
    ],
    "Random": [
        ("Particle contamination",        0.70,
         "공기 중 파티클 또는 필터 점검 필요"),
        ("Coolant/solvent droplet",       0.45,
         "냉각수/용제 미세 비산 가능성"),
    ],
    "Normal": [],
}


# 레시피 파라미터 인사이트 (항상 표시)
RECIPE_INSIGHT = [
    ("Gas flow",    "thickness distribution",
     "유량 편차는 반경 방향 두께 프로파일에 직결됨"),
    ("Temperature", "film uniformity",
     "척 온도 링 편차는 결정성 및 두께 균일도에 영향"),
    ("Rotation",    "angular symmetry",
     "회전 안정성 부족은 비대칭/환형 패턴을 유발"),
    ("Plasma",      "etch/deposition rate",
     "플라즈마 밀도 분포가 zone별 반응속도를 결정"),
    ("Pressure",    "step coverage",
     "공정 압력은 step coverage와 입자 응집에 영향"),
]


CONCLUSIONS = {
    "Donut": (
        "증착(CVD/PVD) 공정의 막 두께 불균일로 인해 "
        "{zone} zone에 도넛형 stain 패턴이 집중되었습니다."
    ),
    "Edge-Ring": (
        "웨이퍼 외곽 처리 단계(EBR/edge handling)에서 결함이 누적되어 "
        "{zone} zone에 링 형태 분포가 관찰됩니다."
    ),
    "Center": (
        "중앙부 공정 조건(샤워헤드/광학)의 편차로 "
        "{zone} zone에 defect가 우세합니다."
    ),
    "Scratch Line": (
        "기계적 접촉(이송/CMP)으로 인한 선형 스크래치가 "
        "특정 행/열에 집중되어 있습니다."
    ),
    "Random": (
        "특정 패턴이 약하며 파티클 오염성 결함 가능성이 높습니다. "
        "필터/클린룸 환경 점검을 권장합니다."
    ),
    "Normal": "검출된 결함이 없어 공정은 정상 범위로 판단됩니다.",
}


def _dominant_zone(zone_summary):
    return max(zone_summary, key=zone_summary.get) if zone_summary else None


def estimate_causes(pattern, zone_summary, total):
    """패턴 + zone 분포 -> 원인 후보 (confidence 내림차순)."""
    base = PATTERN_CAUSES.get(pattern, [])
    if not base or total == 0:
        return []

    middle = zone_summary.get("middle", 0) / total
    edge   = zone_summary.get("edge", 0) / total
    center = zone_summary.get("center", 0) / total

    results = []
    for name, weight, hint in base:
        adj = weight

        # 패턴별 zone 신호로 가중치 미세 조정
        if pattern == "Donut" and "Gas" in name:
            adj += (middle - 0.5) * 0.3
        elif pattern == "Edge-Ring" and "Edge" in name:
            adj += (edge - 0.5) * 0.3
        elif pattern == "Center" and "center" in name.lower():
            adj += (center - 0.5) * 0.3

        adj = max(0.0, min(1.0, adj))
        results.append({
            "cause": name,
            "confidence": round(adj, 2),
            "hint": hint,
        })

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results


def recipe_insight():
    return [
        {"param": p, "affects": a, "note": n}
        for p, a, n in RECIPE_INSIGHT
    ]


def conclusion(pattern, zone_summary, total):
    if total == 0:
        return CONCLUSIONS["Normal"]

    template = CONCLUSIONS.get(pattern)
    if template is None:
        return f"패턴 '{pattern}'에 대한 해석 규칙이 등록되어 있지 않습니다."

    zone = _dominant_zone(zone_summary) or "unknown"
    return template.format(zone=zone)


def dominant_defect_type(wafer_snapshot):
    """count_map 기반으로 가장 많이 검출된 결함 타입을 반환."""
    totals = {
        "particle": sum(sum(r) for r in wafer_snapshot.get("particle_map", [])),
        "scratch":  sum(sum(r) for r in wafer_snapshot.get("scratch_map", [])),
        "stain":    sum(sum(r) for r in wafer_snapshot.get("stain_map", [])),
    }
    if all(v == 0 for v in totals.values()):
        return None
    return max(totals, key=totals.get)


# die status 분류 임계값
DIE_HEAVY_THRESHOLD = 3       # 이 개수 이상이면 heavy
# die 중심이 wafer 반경의 이 비율 안이면 active.
# 9x9 grid 기준 0.73: 행별 [3,5,7,9,9,9,7,5,3] = 57 active die (실제 wafer step 패턴)
DIE_ACTIVE_RADIUS_RATIO = 0.73


def _classify_zone(dist_ratio):
    if dist_ratio < 0.33:
        return "center"
    if dist_ratio < 0.66:
        return "middle"
    return "edge"


def _classify_die_status(active, defect_count):
    if not active:
        return "outside"
    if defect_count == 0:
        return "normal"
    if defect_count < DIE_HEAVY_THRESHOLD:
        return "defective_light"
    return "defective_heavy"


def build_die_grid(wafer_snapshot):
    """
    각 die의 상세 정보를 평탄한 리스트로 반환한다.
    UI는 이 리스트를 받아 die-grid 캔버스를 그린다.
    """
    rows = wafer_snapshot["rows"]
    cols = wafer_snapshot["cols"]

    cy = (rows - 1) / 2
    cx = (cols - 1) / 2
    rmax = (cy ** 2 + cx ** 2) ** 0.5 or 1.0

    type_maps = {
        "particle": wafer_snapshot.get("particle_map", []),
        "scratch":  wafer_snapshot.get("scratch_map", []),
        "stain":    wafer_snapshot.get("stain_map", []),
    }

    dies = []
    for r in range(rows):
        for c in range(cols):
            dist_ratio = ((r - cy) ** 2 + (c - cx) ** 2) ** 0.5 / rmax
            active = dist_ratio <= DIE_ACTIVE_RADIUS_RATIO

            counts = {k: m[r][c] for k, m in type_maps.items()}
            defect_count = sum(counts.values())
            defect_type = (
                max(counts, key=counts.get) if defect_count > 0 else None
            )

            dies.append({
                "die_id": r * cols + c,
                "row": r,
                "col": c,
                "zone": _classify_zone(dist_ratio),
                "defect_type": defect_type,
                "defect_count": defect_count,
                "status": _classify_die_status(active, defect_count),
                "active": active,
            })

    return dies


def _die_grid_summary(dies):
    active = [d for d in dies if d["active"]]
    return {
        "total_die": len(dies),
        "active_die": len(active),
        "normal_die": sum(1 for d in active if d["status"] == "normal"),
        "defective_light_die": sum(
            1 for d in active if d["status"] == "defective_light"
        ),
        "defective_heavy_die": sum(
            1 for d in active if d["status"] == "defective_heavy"
        ),
    }


def wafer_yield(die_summary):
    """예측 수율 = 정상 die / active die × 100.
    반도체 업계 표준 yield 메트릭."""
    active = die_summary["active_die"] or 1
    good   = die_summary["normal_die"]
    light  = die_summary["defective_light_die"]
    heavy  = die_summary["defective_heavy_die"]
    defective = light + heavy

    pct = round(good / active * 100, 1)

    if pct >= 90:
        level = "Excellent"
    elif pct >= 75:
        level = "Good"
    elif pct >= 50:
        level = "Marginal"
    else:
        level = "Poor"

    return {
        "yield_pct": pct,
        "good_die": good,
        "light_die": light,
        "heavy_die": heavy,
        "defective_die": defective,
        "active_die": active,
        "level": level,
    }


def risk_score(die_summary, pattern):
    """0-100 위험도 점수.
    결함 die 비율(가장 큰 가중치) + heavy die 가산 + 패턴 명확성으로 산정한다.
    """
    active = die_summary["active_die"] or 1
    heavy = die_summary["defective_heavy_die"]
    light = die_summary["defective_light_die"]

    defective_ratio = (heavy + light) / active

    score = defective_ratio * 60        # 결함 die 비율 (0~60)
    score += min(heavy * 1.5, 25)        # heavy 가산 (최대 25)
    if pattern not in ("Normal", "Random"):
        score += 15                      # 패턴이 명확하면 +15

    score = max(0.0, min(100.0, score))

    if score < 30:
        level = "Low"
    elif score < 60:
        level = "Medium"
    elif score < 80:
        level = "High"
    else:
        level = "Critical"

    # 조치 권고 한 줄
    advice = {
        "Low":      "현재 공정은 정상 범위로 보입니다. 정기 모니터링만 유지.",
        "Medium":   "이상 징후가 감지됩니다. 해당 zone 공정 조건을 점검하세요.",
        "High":     "결함 집중이 확인됩니다. 즉시 공정 점검을 권고합니다.",
        "Critical": "광범위한 결함이 감지되었습니다. 즉시 라인 중단 및 조사 필요.",
    }[level]

    return {
        "score": round(score, 1),
        "level": level,
        "advice": advice,
    }


def analyze(wafer_snapshot):
    """WaferMap.to_json() 결과를 받아 공정 분석 결과를 추가한다."""
    total = wafer_snapshot.get("total_defects", 0)
    pattern = wafer_snapshot.get("pattern", "Normal")
    zones = wafer_snapshot.get(
        "zone_summary", {"center": 0, "middle": 0, "edge": 0}
    )

    die_grid = build_die_grid(wafer_snapshot)
    die_summary = _die_grid_summary(die_grid)

    return {
        "pattern": pattern,
        "dominant_zone": _dominant_zone(zones) if total else None,
        "dominant_type": dominant_defect_type(wafer_snapshot),
        "causes": estimate_causes(pattern, zones, total),
        "recipe": recipe_insight(),
        "conclusion": conclusion(pattern, zones, total),
        "die_grid": die_grid,
        "die_summary": die_summary,
        "risk": risk_score(die_summary, pattern),
        "yield": wafer_yield(die_summary),
    }
