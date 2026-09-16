// dash_v2/js/core.js — 전역 상태·DOM 헬퍼·KISA 판정 규칙(침입/배회/쓰러짐). app.js 에서 분리(2026-09-09). 로드 순서: core → review → data → editor → main (dashboard.html)
"use strict";
const $ = s => document.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const fmt = s => s == null ? "-" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const BEFORE = 2, AFTER = 10;

let META = null, LABELS = null, PLABELS = null, IMGLABELS = null;   // 화재 영상 · 사람 영상 · 정지 이미지 손라벨
let CUR = { item: "fire", name: null, mode: "data" };   // 첫 화면 = 데이터 확인
let FILT = "all", VID = null;

// ---------- 예측 알람 시각 (대시보드는 대표 규칙 하나로 표시) ----------
function fireAlarm(row) {
  const rows = row.signal || []; if (!rows.length) return null;
  const head = rows.filter(r => r[0] <= 60).map(r => r[2]).sort((a, b) => a - b);
  const base = head.length ? head[Math.min(Math.floor(head.length * 0.8), head.length - 1)] : 0;
  // 서버 실측 최적 (전수 88.9): 불임계 0.12, 창 20표본, 12회 충족, 연기 기준선+0.15
  const win = [], W = 20, HIT = 12, FTH = 0.12, RISE = 0.15;
  for (const [t, fire, smoke] of rows) {
    const hit = fire >= FTH || (smoke >= base + RISE && smoke >= 0.3);
    win.push([t, hit]); if (win.length > W) win.shift();
    if (win.filter(x => x[1]).length >= HIT) return win.find(x => x[1])[0] + 10;
  }
  return null;
}
// 점이 다각형 안인지 (구역 판정의 바탕)
function inPoly(x, y, poly) {
  if (!poly || poly.length < 3) return false;
  let on = false;
  for (let i = 0, n = poly.length; i < n; i++) {
    const [x1, y1] = poly[i], [x2, y2] = poly[(i + 1) % n];
    if ((y1 > y) !== (y2 > y) && x < x1 + (y - y1) * (x2 - x1) / (y2 - y1)) on = !on;
  }
  return on;
}
// 사람이 구역에 들어왔나. corners 0=발끝만(배회), 3=몸전체(침입)
function entered(box, poly, corners) {
  const [x1, y1, x2, y2] = box;
  if (!inPoly((x1 + x2) / 2, y2, poly)) return false;
  if (corners <= 0) return true;
  const c = [[x1, y1], [x2, y1], [x1, y2], [x2, y2]];
  return c.filter(([a, b]) => inPoly(a, b, poly)).length >= corners;
}
// 침입: 트랙별 몸전체 진입 → 마지막 사람 진입시각 (서버 실측 규칙)
function intrusionAlarm(row) {
  const poly = row.zone; if (!poly || !poly.length || !row.tracks) return null;
  const CONF = 0.45, CORNERS = 3, HOLD = 2, SETTLE = 24;
  const streak = {}, entry = {}; let latest = null, lastNew = null;
  for (const r of row.tracks) {
    const seen = new Set();
    for (const b of r.boxes) {
      if (b[1] < CONF || !entered(b.slice(2, 6), poly, CORNERS)) continue;
      seen.add(b[0]); streak[b[0]] = (streak[b[0]] || 0) + 1;
      if (streak[b[0]] === HOLD && !(b[0] in entry)) {
        entry[b[0]] = r.t; latest = latest == null ? r.t : Math.max(latest, r.t); lastNew = r.t;
      }
    }
    for (const k in streak) if (!seen.has(+k)) streak[k] = 0;
    if (latest != null && r.t - lastNew >= SETTLE) return latest;
  }
  return latest;
}
// 배회: 트랙별 체류 dwell초 → 마지막 배회자 진입 + delay
function loiterAlarm(row) {
  const poly = row.zone; if (!poly || !poly.length || !row.tracks) return null;
  const CONF = 0.4, CORNERS = 0, DWELL = 6, DELAY = 10, SETTLE = 5, GAP = 6, STEP = 0.5;
  const dwell = {}, miss = {}, entry = {}, loit = {}; let latest = null, lastNew = null;
  for (const r of row.tracks) {
    const seen = new Set();
    for (const b of r.boxes) {
      if (b[1] < CONF || !entered(b.slice(2, 6), poly, CORNERS)) continue;
      seen.add(b[0]);
      if (!(dwell[b[0]] > 0)) entry[b[0]] = r.t;
      dwell[b[0]] = (dwell[b[0]] || 0) + STEP; miss[b[0]] = 0;
      if (dwell[b[0]] >= DWELL && !(b[0] in loit)) {
        loit[b[0]] = entry[b[0]];
        latest = latest == null ? entry[b[0]] : Math.max(latest, entry[b[0]]); lastNew = r.t;
      }
    }
    for (const k in dwell) if (!seen.has(+k)) { miss[k] = (miss[k] || 0) + 1; if (miss[k] > GAP) dwell[k] = 0; }
    if (latest != null && r.t - lastNew >= SETTLE) return latest + DELAY;
  }
  return latest == null ? null : latest + DELAY;
}
function personAlarm(row, item) {
  return item === "loiter" ? loiterAlarm(row) : intrusionAlarm(row);
}
function fallAlarm(row) {
  // 서버 실측 최적 (전수 88.9): 로짓 임계 -1.0 = sigmoid 0.269, 연속 4창. 트랙별 최초 돌파 중 가장 이른 것 (처음 쓰러진 사람)
  const TH = 0.269, NEED = 4;
  let best = null;
  for (const c of (row.curves || [])) {
    let run = 0;
    for (let i = 0; i < c.length; i++) {
      run = c[i][1] >= TH ? run + 1 : 0;
      if (run >= NEED) { const t = c[i - NEED + 1][0]; best = best == null ? t : Math.min(best, t); break; }
    }
  }
  return best;
}
// 예측 알람은 서버가 제출 도구(_kisa_port/tools/kisa_items.py)의 규칙으로 계산해
// dash_meta 의 row.sa 로 실어 준다(dash_v2/dash_sa.py). 화면은 그 값을 쓴다.
//
// [주의] 아래 fireAlarm/personAlarm/fallAlarm 은 화면이 따로 구현해 둔 옛 규칙이다.
//        2026-09-16 에 네 항목 모두 상수가 낡아 화면의 정검/오검/미검이 실측과 달랐다.
//          방화   화면 불 0.12 · 20창 12회 · 연기 사용   |  제출 불 0.40 · 20창 3회 · 연기 미사용
//          쓰러짐 화면 th 0.269                          |  제출 th 0.755
//          배회   늦은 일행 조건 없음                     |  제출 20초/3명/방금 도착
//          침입   gap 없음                               |  제출 gap 2
//        row.sa 가 없을 때(옛 dash_meta)만 쓰는 대비책이다. 상수를 여기서 고치지 말 것.
function alarmOf(row, item) {
  if (row && row.sa !== undefined) return row.sa;      // 서버가 계산한 값
  if (item === "fire") return fireAlarm(row);
  if (item === "fall") return fallAlarm(row);
  return personAlarm(row, item);
}
function verdict(row, item) {
  if (item === "labelset") return row.box_count > 0 ? "라벨" : "빈프레임";  // 손라벨은 판정 대상 아님
  const gt = row.gt, sa = alarmOf(row, item);
  if (gt == null) return sa == null ? "정상" : "오탐";
  if (sa == null) return "미검";
  return (gt - BEFORE <= sa && sa <= gt + AFTER) ? "정검" : "오검";
}
const vClass = v => ({ "정검": "ok", "오검": "bad", "오탐": "bad", "미검": "miss", "정상": "none", "라벨": "ok", "빈프레임": "none" }[v] || "none");

