// dashboard.js
// /api/analysis 데이터를 가져와 wafer canvas + 패널 + 차트 + 테이블을 갱신한다.

const TYPE_COLOR = {
  particle: "#27ae60",
  scratch:  "#e74c3c",
  stain:    "#f39c12",
};

// die-level 시각화에서 status별 색상
const DIE_STATUS_COLOR = {
  normal:           "#dfe4ea",  // gray
  defective_light:  "#ffd166",  // light yellow/orange
  defective_heavy:  "#e76f51",  // dark orange
  outside:          "#eef0f2",  // 거의 안 보이는 회색 (wafer 원 밖)
};

let zoneChart = null;
let typeChart = null;

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(url + " " + r.status);
  return r.json();
}

async function refresh() {
  try {
    const data = await fetchJSON("/api/analysis");
    drawWafer(data);
    fillPanel(data);
    drawZoneChart(data.zone_summary);
    drawTypeChart(data);
    fillRisk(data.process.risk);
    fillYield(data.process.yield);
    fillCauses(data.process.causes);
    fillRecipe(data.process.recipe);
    fillConclusion(data);
    fillSource().catch(err => console.error("source fetch:", err));
  } catch (e) {
    console.error(e);
  }
}

// 최근 fetch한 source 응답 (toggle 시 재그리기 위해 저장)
let _lastSource = null;

async function fillSource() {
  const src = await fetchJSON("/api/source");
  _lastSource = src;
  const img = document.getElementById("source-img");
  const empty = document.getElementById("source-empty");

  if (src.exists && src.url) {
    img.src = src.url + "?t=" + Date.now();
    img.style.display = "block";
    empty.style.display = "none";
  } else {
    img.style.display = "none";
    empty.style.display = "block";
  }

  document.getElementById("src-scenario").textContent = src.scenario || "";
  document.getElementById("src-file").textContent     = src.file || "-";
  document.getElementById("src-model").textContent    = src.model || "-";
  document.getElementById("src-infer").textContent    =
    src.inference_ms != null ? `${src.inference_ms} ms (mock)` : "-";
  document.getElementById("src-exp-type").textContent = src.expected_defect || "-";
  document.getElementById("src-exp-pat").textContent  = src.expected_pattern || "-";
  document.getElementById("src-exp-zone").textContent = src.expected_zone || "-";
  document.getElementById("src-note").textContent     = src.note || "";

  // wafer spec 한 줄
  if (src.wafer_spec) {
    const s = src.wafer_spec;
    document.getElementById("src-spec").textContent =
      `Ø ${s.diameter_mm} mm  ·  ${s.die_count} dies  ·  ${s.die_size_mm}×${s.die_size_mm} mm/die  ·  pitch ${s.pitch_mm} mm`;
  }

  // stain region analysis
  const stainDet = (src.detections || []).find(
    d => d.type === "stain" && d.stain_metrics
  );
  fillStainAnalysis(stainDet);

  if (src.captured_at) {
    const d = new Date(src.captured_at);
    document.getElementById("src-time").textContent =
      d.toLocaleString("ko-KR", { hour12: false });
  }

  // detection 개수 라벨 + overlay 그리기
  const cnt = src.detection_count || 0;
  document.getElementById("source-detection-count").textContent =
    cnt > 0 ? `${cnt} regions` : "no detection";

  redrawDetections();
}

function redrawDetections() {
  if (!_lastSource) return;
  const img    = document.getElementById("source-img");
  const canvas = document.getElementById("source-overlay");
  const show   = document.getElementById("show-detections").checked;
  const detections = _lastSource.detections || [];
  const imageSize  = _lastSource.image_size || 620;

  // canvas resolution은 image의 natural size에 맞춰서 좌표 정확하게
  canvas.width  = imageSize;
  canvas.height = imageSize;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, imageSize, imageSize);

  if (!show || detections.length === 0) return;

  // 이미지 로드 끝나지 않았으면 onload 후 재시도
  if (!img.complete || img.naturalWidth === 0) {
    img.addEventListener("load", redrawDetections, { once: true });
    return;
  }

  detections.forEach(d => {
    if (d.shape === "polygon") {
      drawDetectionPolygon(ctx, d);
    } else {
      drawDetectionBox(ctx, d);
    }
  });

  // 좌하단 요약 박스
  drawDetectionSummary(ctx, imageSize, detections);
}

function drawDetectionBox(ctx, det) {
  const [x, y, w, h] = det.bbox;
  const color = TYPE_COLOR[det.type] || "#e74c3c";
  const heavy = det.severity === "heavy";

  // box
  ctx.strokeStyle = color;
  ctx.lineWidth = heavy ? 3 : 2;
  ctx.strokeRect(x, y, w, h);

  // 헤드 라벨
  const label = `${det.label} ${Math.round(det.confidence * 100)}%`;
  ctx.font = "bold 13px sans-serif";
  const tw = ctx.measureText(label).width;
  const labelH = 18;
  const pad = 4;

  // 라벨이 박스 위 공간 부족하면 박스 안 상단
  const labelY = y >= labelH + 2 ? y - labelH : y + 1;

  ctx.fillStyle = color;
  ctx.fillRect(x, labelY, tw + pad * 2, labelH);

  ctx.fillStyle = "#ffffff";
  ctx.textBaseline = "top";
  ctx.fillText(label, x + pad, labelY + 3);
}

function drawDetectionPolygon(ctx, det) {
  if (!det.polygons || det.polygons.length === 0) return;
  const color = TYPE_COLOR[det.type] || "#e74c3c";

  // outer + hole 모두 한 path에, even-odd 규칙으로 hole이 fill에서 빠지게
  ctx.beginPath();
  det.polygons.forEach(poly => {
    const pts = poly.points;
    if (pts.length < 3) return;
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i][0], pts[i][1]);
    }
    ctx.closePath();
  });

  // 반투명 fill
  ctx.fillStyle = color + "33";
  ctx.fill("evenodd");

  // 선
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.stroke();

  // 라벨: 가장 큰 outer polygon의 centroid에 (donut이면 ring 가운데 hole 부근)
  const outers = det.polygons.filter(p => !p.is_hole);
  if (outers.length === 0) return;
  const biggest = outers.reduce((a, b) =>
    _polyArea(a.points) > _polyArea(b.points) ? a : b
  );
  const c = _polyCentroid(biggest.points);

  const title = `${det.label}   ${Math.round(det.confidence * 100)}%`;
  const sub = `severity: ${det.severity}  ·  coverage: ${det.coverage_pct}% (${det.die_count} dies)`;

  ctx.font = "bold 16px sans-serif";
  const tw1 = ctx.measureText(title).width;
  ctx.font = "12.5px sans-serif";
  const tw2 = ctx.measureText(sub).width;
  const tw = Math.max(tw1, tw2);
  const labelW = tw + 24;
  const labelH = 48;
  const lx = c.x - labelW / 2;
  const ly = c.y - labelH / 2;

  // 배경 박스 (둥근 모서리)
  _roundRect(ctx, lx, ly, labelW, labelH, 8);
  ctx.fillStyle = color;
  ctx.fill();

  // 텍스트
  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = "bold 16px sans-serif";
  ctx.fillText(title, c.x, c.y - 9);
  ctx.font = "12.5px sans-serif";
  ctx.fillText(sub, c.x, c.y + 10);
  ctx.textAlign = "left";
}

function _polyArea(pts) {
  let a = 0;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    a += (pts[j][0] + pts[i][0]) * (pts[j][1] - pts[i][1]);
  }
  return Math.abs(a / 2);
}

function _polyCentroid(pts) {
  let x = 0, y = 0;
  pts.forEach(p => { x += p[0]; y += p[1]; });
  return { x: x / pts.length, y: y / pts.length };
}

function _roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function drawDetectionSummary(ctx, imageSize, detections) {
  // type별 정보: polygon이면 "1 region (N dies)", bbox면 그냥 N개
  const summary = {};
  detections.forEach(d => {
    if (!summary[d.type]) summary[d.type] = { regions: 0, instances: 0, dies: 0 };
    if (d.shape === "polygon") {
      summary[d.type].regions += 1;
      summary[d.type].dies    += (d.die_count || 0);
    } else {
      summary[d.type].instances += 1;
    }
  });

  const parts = Object.entries(summary).map(([type, info]) => {
    if (info.regions > 0) {
      return `${type}: ${info.regions} region (${info.dies} dies)`;
    }
    return `${type}: ${info.instances}`;
  });
  const text = `AI Detection  ·  ${parts.join("  |  ")}`;

  ctx.font = "bold 14px sans-serif";
  const tw = ctx.measureText(text).width;
  const padX = 12, h = 28;
  const x = 12, y = imageSize - h - 12;

  ctx.fillStyle = "rgba(20, 20, 30, 0.82)";
  ctx.fillRect(x, y, tw + padX * 2, h);

  ctx.fillStyle = "#ffffff";
  ctx.textBaseline = "middle";
  ctx.textAlign = "left";
  ctx.fillText(text, x + padX, y + h / 2);
}

function currentWaferMode() {
  const el = document.querySelector('input[name="wafer-mode"]:checked');
  return el ? el.value : "status";
}

function drawWafer(data) {
  const cv = document.getElementById("wafer-canvas");
  const ctx = cv.getContext("2d");
  const W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);

  const cx = W / 2, cy = H / 2;
  const R = Math.min(W, H) / 2 - 14;
  const mode = currentWaferMode();

  // zone overlay (center / middle / edge)
  if (document.getElementById("zone-toggle").checked) {
    drawZoneRings(ctx, cx, cy, R);
  }

  // die-grid 좌표 계산: 정사각형 grid가 wafer 원 내부에 살짝 여유를 두고 들어가도록
  const rows = data.rows, cols = data.cols;
  const dies = (data.process && data.process.die_grid) || [];

  const gridSpan = 2 * R * 0.95;
  const cell = gridSpan / Math.max(rows, cols);
  const offsetX = cx - (cols * cell) / 2;
  const offsetY = cy - (rows * cell) / 2;

  // heatmap 모드를 위한 max count
  const maxCount = Math.max(
    1,
    ...dies.filter(d => d.active).map(d => d.defect_count)
  );

  // die cells
  dies.forEach(d => {
    const x = offsetX + d.col * cell;
    const y = offsetY + d.row * cell;
    if (mode === "heatmap") {
      drawDieHeatmap(ctx, x, y, cell, d, maxCount);
    } else if (mode === "type") {
      drawDieType(ctx, x, y, cell, d);
    } else {
      drawDie(ctx, x, y, cell, d);
    }
  });

  // wafer outline + notch (die 위에 그려서 wafer 경계가 또렷하게)
  drawWaferOutline(ctx, cx, cy, R);

  // legend는 HTML로 분리되어 canvas와 겹치지 않음
  setLegendForMode(mode, maxCount);
}

function setLegendForMode(mode, maxCount) {
  const statusLeg  = document.getElementById("wafer-legend-status");
  const typeLeg    = document.getElementById("wafer-legend-type");
  const heatmapLeg = document.getElementById("wafer-legend-heatmap");

  // 모두 숨김 후 한 개만 표시
  statusLeg.style.display  = "none";
  typeLeg.style.display    = "none";
  heatmapLeg.style.display = "none";

  if (mode === "heatmap") {
    heatmapLeg.style.display = "flex";
    document.getElementById("heatmap-max").textContent = maxCount;
  } else if (mode === "type") {
    typeLeg.style.display = "flex";
  } else {
    statusLeg.style.display = "flex";
  }
}

// stain은 면적 결함이라 개수 표기가 부적절. 숫자 숨김 여부 판단.
function _shouldShowCount(die) {
  return die.defect_count > 0 && die.defect_type !== "stain";
}

function drawDie(ctx, x, y, size, die) {
  const fill = DIE_STATUS_COLOR[die.status] || "#dfe4ea";

  ctx.globalAlpha = die.status === "outside" ? 0.35 : 1.0;
  ctx.fillStyle = fill;
  ctx.fillRect(x, y, size, size);

  ctx.strokeStyle = die.status === "outside" ? "#dde1e4" : "#9aa3ad";
  ctx.lineWidth = 0.8;
  ctx.strokeRect(x + 0.5, y + 0.5, size - 1, size - 1);

  if (_shouldShowCount(die)) {
    ctx.fillStyle = die.status === "defective_heavy" ? "#ffffff" : "#2c3e50";
    ctx.font = `bold ${Math.max(10, Math.floor(size * 0.32))}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(die.defect_count, x + size / 2, y + size / 2);
  }

  ctx.globalAlpha = 1.0;
}

function drawDieType(ctx, x, y, size, die) {
  // outside는 옅게
  if (die.status === "outside") {
    ctx.globalAlpha = 0.35;
    ctx.fillStyle = "#eef0f2";
    ctx.fillRect(x, y, size, size);
    ctx.strokeStyle = "#dde1e4";
    ctx.lineWidth = 0.6;
    ctx.strokeRect(x + 0.5, y + 0.5, size - 1, size - 1);
    ctx.globalAlpha = 1.0;
    return;
  }

  // normal die는 회색
  if (die.defect_count === 0) {
    ctx.fillStyle = DIE_STATUS_COLOR.normal;
    ctx.fillRect(x, y, size, size);
    ctx.strokeStyle = "#9aa3ad";
    ctx.lineWidth = 0.8;
    ctx.strokeRect(x + 0.5, y + 0.5, size - 1, size - 1);
    return;
  }

  // 결함 die: type 색상 + 강도(alpha)
  const color = TYPE_COLOR[die.defect_type] || "#7f8c8d";
  const heavy = die.status === "defective_heavy";
  ctx.globalAlpha = heavy ? 1.0 : 0.55;
  ctx.fillStyle = color;
  ctx.fillRect(x, y, size, size);
  ctx.globalAlpha = 1.0;

  ctx.strokeStyle = "#9aa3ad";
  ctx.lineWidth = 0.8;
  ctx.strokeRect(x + 0.5, y + 0.5, size - 1, size - 1);

  // 개수 (stain은 면적 결함이라 숫자 생략)
  if (_shouldShowCount(die)) {
    ctx.fillStyle = heavy ? "#ffffff" : "#2c3e50";
    ctx.font = `bold ${Math.max(10, Math.floor(size * 0.32))}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(die.defect_count, x + size / 2, y + size / 2);
  }
}

function drawDieHeatmap(ctx, x, y, size, die, maxCount) {
  // outside die는 매우 옅게
  if (die.status === "outside") {
    ctx.globalAlpha = 0.25;
    ctx.fillStyle = "#eef0f2";
    ctx.fillRect(x, y, size, size);
    ctx.strokeStyle = "#dde1e4";
    ctx.lineWidth = 0.6;
    ctx.strokeRect(x + 0.5, y + 0.5, size - 1, size - 1);
    ctx.globalAlpha = 1.0;
    return;
  }

  // 결함 밀도 → 색상: 0 = cream, max = deep red
  const intensity = Math.max(0, Math.min(1, die.defect_count / maxCount));
  const r = 255;
  const g = Math.round(243 - intensity * 200);
  const b = Math.round(206 - intensity * 206);
  ctx.fillStyle = `rgb(${r}, ${Math.max(0, g)}, ${Math.max(0, b)})`;
  ctx.fillRect(x, y, size, size);

  ctx.strokeStyle = "#b8babd";
  ctx.lineWidth = 0.6;
  ctx.strokeRect(x + 0.5, y + 0.5, size - 1, size - 1);

  if (_shouldShowCount(die)) {
    ctx.fillStyle = intensity > 0.55 ? "#ffffff" : "#5a4a1a";
    ctx.font = `bold ${Math.max(10, Math.floor(size * 0.32))}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(die.defect_count, x + size / 2, y + size / 2);
  }
}


function drawZoneRings(ctx, cx, cy, R) {
  const rings = [
    { r: R * 1.00, color: "rgba(231, 76, 60, 0.10)" },  // edge
    { r: R * 0.66, color: "rgba(243, 156, 18, 0.13)" }, // middle
    { r: R * 0.33, color: "rgba(47, 128, 237, 0.15)" }, // center
  ];
  rings.forEach(({ r, color }) => {
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  });
}

function drawWaferOutline(ctx, cx, cy, R) {
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.strokeStyle = "#34495e";
  ctx.lineWidth = 2;
  ctx.stroke();

  // notch (아래쪽 wafer 정렬용 V자 홈)
  ctx.beginPath();
  ctx.moveTo(cx - 8, cy + R);
  ctx.lineTo(cx + 8, cy + R);
  ctx.lineTo(cx, cy + R - 10);
  ctx.closePath();
  ctx.fillStyle = "#fff";
  ctx.fill();
  ctx.strokeStyle = "#34495e";
  ctx.lineWidth = 1.5;
  ctx.stroke();
}


function fillPanel(data) {
  const p = data.process;
  document.getElementById("d-type").textContent    = p.dominant_type ?? "-";
  document.getElementById("d-pattern").textContent = data.pattern ?? "-";
  document.getElementById("d-zone").textContent    = p.dominant_zone ?? "-";
  document.getElementById("d-conf").textContent    =
    p.causes.length ? p.causes[0].confidence.toFixed(2) : "-";
  document.getElementById("d-total").textContent   = data.total_defects ?? 0;

  const s = p.die_summary;
  if (s) {
    const defective = s.defective_light_die + s.defective_heavy_die;
    document.getElementById("d-die").textContent =
      `${defective} / ${s.active_die}`;
  }
}

function drawZoneChart(zones) {
  const ctx = document.getElementById("zone-chart");
  const labels = ["Center", "Middle", "Edge"];
  const values = [zones.center, zones.middle, zones.edge];

  if (zoneChart) {
    zoneChart.data.datasets[0].data = values;
    zoneChart.update();
    return;
  }

  zoneChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Defects",
        data: values,
        backgroundColor: [
          "rgba(47, 128, 237, 0.7)",
          "rgba(243, 156, 18, 0.7)",
          "rgba(231, 76, 60, 0.7)",
        ],
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
    },
  });
}

function sum2D(matrix) {
  if (!matrix) return 0;
  return matrix.reduce(
    (s, row) => s + row.reduce((a, b) => a + b, 0),
    0
  );
}

function drawTypeChart(data) {
  const cv = document.getElementById("type-chart");
  const particle = sum2D(data.particle_map);
  const scratch  = sum2D(data.scratch_map);
  const stain    = sum2D(data.stain_map);
  const total    = particle + scratch + stain;

  const values = [particle, scratch, stain];
  const chartData = {
    labels: ["Particle", "Scratch", "Stain"],
    datasets: [{
      data: values,
      backgroundColor: [
        "rgba(39, 174, 96, 0.85)",
        "rgba(231, 76, 60, 0.85)",
        "rgba(243, 156, 18, 0.85)",
      ],
      borderColor: "#fff",
      borderWidth: 2,
    }],
  };

  if (typeChart) {
    typeChart.data = chartData;
    typeChart.options.plugins.tooltip.callbacks.label =
      makeTypeTooltip(total);
    typeChart.update();
    return;
  }

  typeChart = new Chart(cv, {
    type: "doughnut",
    data: chartData,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "60%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { boxWidth: 12, padding: 10 },
        },
        tooltip: {
          callbacks: { label: makeTypeTooltip(total) },
        },
      },
    },
  });
}

function makeTypeTooltip(total) {
  return (ctx) => {
    const v = ctx.parsed;
    const pct = total > 0 ? ((v / total) * 100).toFixed(1) : "0.0";
    return `${ctx.label}: ${v} (${pct}%)`;
  };
}

function fillRisk(risk) {
  if (!risk) return;
  document.getElementById("risk-number").textContent = risk.score;
  document.getElementById("risk-fill").style.width = risk.score + "%";

  const lvlEl = document.getElementById("risk-level");
  lvlEl.textContent = risk.level.toUpperCase();
  lvlEl.className = "risk-level " + risk.level.toLowerCase();

  document.getElementById("risk-advice").textContent = risk.advice;
}

function fillStainAnalysis(stainDet) {
  const card = document.getElementById("stain-analysis-card");
  if (!stainDet || !stainDet.stain_metrics) {
    card.style.display = "none";
    return;
  }
  card.style.display = "block";

  const m = stainDet.stain_metrics;

  // 1) Region count
  document.getElementById("stain-region-count").textContent = m.region_count;
  document.getElementById("stain-region-sub").textContent =
    m.has_hole ? "ring 형태 (hole 검출)" : "단일 영역";

  // 2) Area
  document.getElementById("stain-area").textContent =
    m.area_mm2.toLocaleString();
  document.getElementById("stain-area-sub").textContent =
    `mm² (${stainDet.die_count} dies, ${stainDet.coverage_pct}% wafer)`;

  // 3) Location
  document.getElementById("stain-location").textContent = m.location;
  const cm = m.centroid_mm;
  document.getElementById("stain-location-sub").textContent =
    `centroid (${cm.x}, ${cm.y}) mm  ·  dist ${m.centroid_distance_mm} mm`;

  // 4) Distribution
  document.getElementById("stain-distribution").textContent = m.distribution;
  document.getElementById("stain-distribution-sub").textContent =
    `severity: ${stainDet.severity}  ·  conf ${(stainDet.confidence*100).toFixed(0)}%`;
}

function fillYield(y) {
  if (!y) return;
  document.getElementById("yield-pct").textContent = y.yield_pct;
  document.getElementById("yield-fill").style.width = y.yield_pct + "%";

  const lvl = document.getElementById("yield-level");
  lvl.textContent = y.level.toUpperCase();
  lvl.className = "yield-level " + y.level.toLowerCase();

  document.getElementById("yield-good").textContent  = y.good_die;
  document.getElementById("yield-light").textContent = y.light_die;
  document.getElementById("yield-heavy").textContent = y.heavy_die;
  document.getElementById("yield-total").textContent = y.active_die;
}

function fillCauses(causes) {
  const top = document.getElementById("cause-top");
  const grid = document.getElementById("cause-grid");

  if (!causes || causes.length === 0) {
    top.style.display = "none";
    grid.innerHTML = '<div class="empty" style="padding:14px">no data</div>';
    return;
  }

  // top cause 강조
  const c0 = causes[0];
  top.style.display = "flex";
  document.getElementById("cause-top-name").textContent = c0.cause;
  document.getElementById("cause-top-hint").textContent = c0.hint;
  document.getElementById("cause-top-conf").textContent =
    Math.round(c0.confidence * 100) + "%";

  // 보조 원인 카드들
  grid.innerHTML = causes.slice(1).map((c, i) => {
    const pct = Math.round(c.confidence * 100);
    return `
      <div class="cause-card">
        <div class="cause-card-head">
          <span class="cause-card-name">#${i + 2} ${escapeHtml(c.cause)}</span>
          <span class="cause-card-conf">${pct}%</span>
        </div>
        <div class="cause-card-bar"><div style="width:${pct}%"></div></div>
        <div class="cause-card-hint">${escapeHtml(c.hint)}</div>
      </div>
    `;
  }).join("");
}

function fillRecipe(rows) {
  const grid = document.getElementById("recipe-grid");
  grid.innerHTML = rows.map(r => `
    <div class="recipe-card" data-param="${escapeHtml(r.param)}">
      <div class="recipe-card-name">${escapeHtml(r.param)}</div>
      <div class="recipe-card-affects">${escapeHtml(r.affects)}</div>
      <div class="recipe-card-note">${escapeHtml(r.note)}</div>
    </div>
  `).join("");
}

function fillConclusion(data) {
  document.getElementById("conclusion").textContent =
    data.process.conclusion;

  const chips = document.getElementById("conclusion-chips");
  const items = [];

  if (data.pattern && data.pattern !== "Normal") {
    items.push(chipHtml("pattern", "Pattern", data.pattern));
  }
  if (data.process.dominant_zone) {
    items.push(chipHtml("zone", "Zone", data.process.dominant_zone));
  }
  if (data.process.dominant_type) {
    items.push(chipHtml("type", "Type", data.process.dominant_type));
  }
  if (data.process.risk) {
    const lvl = data.process.risk.level.toLowerCase();
    const text = `${data.process.risk.level} (${data.process.risk.score})`;
    items.push(`
      <span class="conclusion-chip chip-risk-${lvl}">
        <span class="chip-label">Risk</span> ${escapeHtml(text)}
      </span>`);
  }

  chips.innerHTML = items.join("");
}

function chipHtml(cls, label, value) {
  return `
    <span class="conclusion-chip chip-${cls}">
      <span class="chip-label">${label}</span> ${escapeHtml(value)}
    </span>`;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

// --- mock loaders ---
async function loadMockDonut() {
  await fetchJSON("/api/simulate/donut", { method: "POST" });
  await refresh();
}

// 첫 진입 시: wafer가 비어 있으면 Donut mock을 자동 주입한다.
// 라이브 검출 데이터가 이미 누적되어 있으면 그대로 표시한다.
async function init() {
  try {
    const data = await fetchJSON("/api/analysis");
    if (!data.total_defects) {
      await loadMockDonut();
    } else {
      drawWafer(data);
      fillPanel(data);
      drawZoneChart(data.zone_summary);
      drawTypeChart(data);
      fillRisk(data.process.risk);
      fillCauses(data.process.causes);
      fillRecipe(data.process.recipe);
      fillConclusion(data);
      fillSource().catch(err => console.error("source fetch:", err));
    }
  } catch (e) {
    console.error("init failed:", e);
    // fallback: 어쨌든 화면을 그려본다
    refresh().catch(() => {});
  }
}

// event bindings
document.querySelectorAll("[data-sim]").forEach(btn => {
  btn.addEventListener("click", async () => {
    await fetchJSON("/api/simulate/" + btn.dataset.sim, { method: "POST" });
    refresh();
  });
});

document.getElementById("reset").addEventListener("click", async () => {
  await fetchJSON("/reset_wafer_map", { method: "POST" });
  refresh();
});

document.getElementById("zone-toggle").addEventListener("change", refresh);

document.querySelectorAll('input[name="wafer-mode"]').forEach(el => {
  el.addEventListener("change", refresh);
});

// AI detection 토글 (API 재호출 없이 캔버스만 재그리기)
document.getElementById("show-detections")
  .addEventListener("change", redrawDetections);

init();
