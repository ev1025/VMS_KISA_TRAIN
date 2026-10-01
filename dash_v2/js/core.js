// dash_v2/js/core.js — 전역 상태·DOM 헬퍼. app.js 에서 분리(2026-09-09). 로드 순서: core → review → data → editor → main (dashboard.html)
"use strict";
const $ = s => document.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const fmt = s => s == null ? "-" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const BEFORE = 2, AFTER = 10;

let META = null, LABELS = null, PLABELS = null, IMGLABELS = null;   // 화재 영상 · 사람 영상 · 정지 이미지 손라벨
let CUR = { item: "fire", name: null, mode: "data" };   // 첫 화면 = 데이터 확인
let FILT = "all", VID = null;

// 검수 탭의 예측 알람 · 판정은 서버가 채점과 같은 판정 모듈로 미리 계산해 준다(scripts/review_cache.py, 2026-09-28).
// 여기 있던 JS 판정 함수(방화·침입·배회·쓰러짐)는 옛 규칙 상수라 채점과 달라 지웠다.
const vClass = v => ({ "정검": "ok", "오검": "bad", "오탐": "bad", "미검": "miss", "정상": "none", "라벨": "ok", "빈프레임": "none" }[v] || "none");


// 전역 항목 필터(계약 v2, 2026-10-01): 영상 검수 · 결과(비교 묶음) · 히스토리 탭에 적용. 데이터 확인 탭 · 점수 카드 · 큐는 늘 전부. 계층마다 항목 이름이 달라 여기 한 곳에서 묶는다
//   meta = results meta.item · history item, review = 검수 API item
const GF_DEF = {
  all: { label: "전체" },
  fire: { label: "화재", meta: "방화", review: ["fire"] },
  person: { label: "사람", meta: "사람", review: ["intrusion", "loiter"] },   // 침입 · 배회(10-01 사용자: 이름은 '사람')
  fall: { label: "쓰러짐", meta: "쓰러짐", review: ["fall"] },
};
let GF = "all";
try { const v = localStorage.getItem("kisa_gf"); if (GF_DEF[v]) GF = v; } catch (e) {}
const gf = () => GF_DEF[GF];
const gfMeta = v => GF === "all" || v === gf().meta || (GF === "person" && (v === "침입" || v === "배회"));   // 옛 실험은 meta.item 이 침입 · 배회
