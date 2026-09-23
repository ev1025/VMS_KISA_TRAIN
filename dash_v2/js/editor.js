// dash_v2/js/editor.js — 라벨 편집기(SAM 탭·박스·저장·전파·검수). 로드 순서: core → review → data → editor → main (dashboard.html)
// 세 저장소: 손라벨(person_labels/fire_labels.json) > SAM 전파(자동라벨/sam2) > 정답 복사본(정답라벨). 표시·학습 우선순위도 이 순서. (DINO 초안은 2026-09-11 걷어냈다)
// 프레임 단위: 사람 클립 0.5초(2FPS), 화재 클립 1초. 화재 SAM 객체는 1=불(cls 0)·2=연기(cls 1) 고정(FIRE).
// 데이터확인 탭의 영상 조건 필터(야간·눈·비·안개)가 쓰는 상태. data.js 가 채우고 passFilter 로 거른다.
let CONDS = {}, CLIPFILTER = "";
// 클립이 지금 필터에 걸리나. 조건은 XML 의 TimeOfDay/Snow/Rain/Fog.
function passFilter(stem) {
  if (!CLIPFILTER) return true;
  const c = CONDS[stem]; if (!c) return false;
  const yes = v => /^(yes|y|true|1)$/i.test(String(v || "")) || /(light|heavy|weak|strong)/i.test(String(v || ""));
  if (CLIPFILTER === "night") return /night/i.test(c.tod);
  if (CLIPFILTER === "day") return /day/i.test(c.tod);
  if (CLIPFILTER === "snow") return yes(c.snow);
  if (CLIPFILTER === "rain") return yes(c.rain);
  if (CLIPFILTER === "fog") return yes(c.fog);
  if (CLIPFILTER === "hard") return /night/i.test(c.tod) || yes(c.snow) || yes(c.rain) || yes(c.fog);
  return true;
}
// 편집기 전역 상태. src = 지금 화면 박스의 출처(hand 손라벨 · sam 전파 결과 · gt 정답 · none 없음)
let LB = { cat: null, clip: null, sec: 0, boxes: [], src: "none", mode: null, img: null };   // img = 정지 이미지 편집 중이면 그 상대경로
const stemOf = pathStr => String(pathStr).split("/").pop();   // 라벨은 파일 이름(stem)으로 묶인다

// ---------- 프레임 단위(사람 0.5초 · 화재 1초): 양자화·표시 변환은 전부 여기서 ----------
let _AUTO = null;                       // 자동 넘기기 타이머(전역: 클립을 바꿀 때 밖에서도 멈춰야 한다)
const AUTO_MS = 500;                    // 1초에 두 프레임
function autoStop() { if (_AUTO) { clearTimeout(_AUTO); _AUTO = null; } }
function _step() { return LB.mode === "person" ? 0.5 : 1; }
function quant(sec) { const q = 1 / _step(); return Math.round(sec * q) / q; }          // 시각을 프레임 격자에 맞춘다
const GRID = 0.5;                                                                          // 모드와 무관한 공통 격자(사람 0.5 · 화재 1.0 의 공배수). 목록 배지처럼 모드 밖에서 셀 때 쓴다
const gridKey = t => Math.round(t / GRID) * GRID;
function tkey(sec) { return Number(sec).toFixed(1); }                                     // 저장소 키("190.5")
function _disp(sec) { return LB.mode === "person" ? Math.round(sec * 2) : sec; }         // 사람: 화면엔 정수 프레임번호(초×2)
function _undisp(v) { return LB.mode === "person" ? v / 2 : v; }
const near = (a, b) => Math.abs(a - b) < 0.01;                                            // 같은 프레임 판정

// 현재 편집 모드의 손라벨 저장소(person 이면 PLABELS, 아니면 LABELS)
function _labelStore() { return LB.img ? IMGLABELS : ((LB.mode === "person") ? PLABELS : LABELS); }
// 그 프레임의 손라벨 상태. null = 기록 없음(프리필 대상) · [] = 검토완료(빈 라벨 마커, 초안 안 깔림) · 박스 목록 = 손라벨
function existingBoxes(clip, t) {
  const S = _labelStore(); if (!S) return null;
  const rs = S.filter(r => r.clip === clip && Math.abs(Number(r.t) - t) < 0.25);
  if (!rs.length) return null;
  return rs.filter(r => r.cls >= 0).map(r => r.obj != null ? [r.cls, r.x, r.y, r.w, r.h, +r.obj] : [r.cls, r.x, r.y, r.w, r.h]);   // 6번째 = 객체 번호(있을 때)
}
const hasHand = s => !!(s && s.length);                                                   // 손라벨 박스로 확정된 프레임인가
// 그 클립에서 손라벨 박스가 있는 초 목록 [[초, 박스수], ...]
function shotSecs(clip) {
  const S = _labelStore(); if (!S) return [];
  const by = {};
  S.filter(r => r.clip === clip && r.cls >= 0).forEach(r => { const s = quant(r.t); by[s] = (by[s] || 0) + 1; });
  return Object.keys(by).map(Number).sort((a, b) => a - b).map(s => [s, by[s]]);
}
// 초별 손라벨 종류: "box"=박스 있음 · "empty"=검토완료(박스 0, cls -1 마커)
function shotKinds(clip) {
  const S = _labelStore(); const by = {};
  if (S) S.filter(r => r.clip === clip).forEach(r => { const k = gridKey(r.t); by[k] = (by[k] === "box" || r.cls >= 0) ? "box" : "empty"; });
  return by;
}
let SAMFR = {};    // stem → SAM 전파 프레임 시각 목록(/api/sam2frames). 목록 배지 = 손라벨 ∪ SAM = 학습데이터 수
function labeledCount(clip, mode) {   // mode 를 주면 그 모드 손라벨만 센다(방화 클립은 불·연기, 사람 클립은 사람)
  if (clip.startsWith("img:")) return (IMGLABELS || []).some(r => r.clip === clip && r.cls >= 0) ? 1 : 0;   // 이미지 = 프레임 하나
  const by = {};
  const stores = mode ? (mode === "fire" ? [LABELS] : mode === "person" ? [PLABELS] : []) : [LABELS, PLABELS];
  for (const S of stores) { if (S) S.filter(r => r.clip === clip && r.cls >= 0).forEach(r => { by[gridKey(r.t)] = 1; }); }
  (SAMFR[clip] || []).forEach(t => { by[gridKey(t)] = 1; });
  return Object.keys(by).length;
}

// 대시보드 스타일 대화상자(크롬 기본 confirm/alert 대신). Enter=확인, Esc=취소
function uiDialog(msg, { ok = "확인", cancel = "취소", danger = false } = {}) {
  return new Promise(resolve => {
    const old = document.getElementById("uiDlg"); if (old) old.remove();
    const wrap = el("div"); wrap.id = "uiDlg";
    wrap.style.cssText = "position:fixed;inset:0;z-index:200;background:#000a;display:flex;align-items:center;justify-content:center";
    const box = el("div");
    box.style.cssText = "background:var(--panel);border:1px solid var(--line);border-radius:12px;min-width:320px;max-width:480px;box-shadow:0 12px 40px #000c;padding:18px 20px 14px";
    const body = el("div"); body.style.cssText = "color:var(--tx);font-size:13px;line-height:1.6;white-space:pre-line"; body.textContent = msg;
    const row = el("div"); row.style.cssText = "display:flex;justify-content:flex-end;gap:8px;margin-top:16px";
    const mk = (t, primary) => { const b = el("button", null, t); b.style.cssText = "width:auto;padding:6px 14px;border-radius:6px;font-weight:700;cursor:pointer;" +
      (primary ? (danger ? "background:#f85149;color:#fff;border:1px solid #f85149" : "background:var(--blue);color:#06090f;border:1px solid var(--blue)") : "background:var(--panel2);color:var(--tx);border:1px solid var(--line)"); return b; };
    const done = v => { wrap.remove(); document.removeEventListener("keydown", onKey, true); resolve(v); };
    const onKey = ev => { if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); done(false); } else if (ev.key === "Enter") { ev.preventDefault(); ev.stopPropagation(); done(true); } else { ev.stopPropagation(); } };
    if (cancel !== null) { const bc = mk(cancel, false); bc.onclick = () => done(false); row.appendChild(bc); }
    const bo = mk(ok, true); bo.onclick = () => done(true); row.appendChild(bo);
    box.appendChild(body); box.appendChild(row); wrap.appendChild(box);
    wrap.onclick = ev => { if (ev.target === wrap && cancel !== null) done(false); };
    document.body.appendChild(wrap); document.addEventListener("keydown", onKey, true); bo.focus();
  });
}
const uiConfirm = (msg, opt) => uiDialog(msg, Object.assign({ ok: "확인", cancel: "취소" }, opt || {}));
const uiAlert = msg => uiDialog(msg, { ok: "닫기", cancel: null });
const SESSKEY = "kisa_last_view";
// 새로고침해도 보던 자리로 돌아가게 마지막 위치를 남긴다(브라우저에만 저장).
function saveSession(extra) {
  try {
    const cur = JSON.parse(localStorage.getItem(SESSKEY) || "{}");
    const v = Object.assign(cur, { mode: CUR.mode, cat: LB.cat, clip: LB.clip, sec: LB.sec, lmode: LB.mode }, extra || {});
    localStorage.setItem(SESSKEY, JSON.stringify(v));
  } catch (e) {}
}
function loadSession() {
  try { return JSON.parse(localStorage.getItem(SESSKEY) || "{}"); } catch (e) { return {}; }
}
const postJSON = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(r => r.json());

// ---------- 정답라벨(데이터셋 제공) 캐시 ----------
const GTL = {}, GTMAP = {};    // 클립 → Promise / 동기 캐시 {frames, points}
function gtLabels(clip) {
  if (!GTL[clip]) GTL[clip] = fetch("/api/gtlabel?clip=" + encodeURIComponent(clip)).then(r => r.json()).then(j => { GTMAP[clip] = j || {}; return GTMAP[clip]; }).catch(() => (GTMAP[clip] = {}));
  return GTL[clip];
}
function gtBoxesAt(gt, sec) { const o = gt && gt.frames && gt.frames[tkey(sec)]; return o ? Object.entries(o).map(([k, b]) => [0, b[0], b[1], b[2], b[3], +k]) : []; }
function gtPointsAt(gt, sec) { const o = gt && gt.points && gt.points[tkey(sec)]; return o ? Object.entries(o).map(([k, p]) => ({ obj: +k, x: p[0], y: p[1] })) : []; }
function gtFramesOf(clip) { const g = GTMAP[clip] || {}; return Object.keys(g.frames || {}).filter(k => Object.keys(g.frames[k] || {}).length).map(Number).sort((a, b) => a - b); }

// ---------- SAM 전파 저장소 캐시(클립 단위). 프레임맵 SAMMAP · 윤곽선 SAMPOLY · 저장소 참조샷 SAMSEEDS ----------
const SAML = {};                      // clip → Promise(프레임맵). 한 번만 받고, 바뀌면 samInvalidate 로 다시 받는다
const SAMMAP = {}, SAMPOLY = {}, SAMSEEDS = {};
function samLabels(clip) {
  if (!SAML[clip]) SAML[clip] = fetch("/api/sam2label?clip=" + encodeURIComponent(clip)).then(r => r.json())
    .then(j => { SAMPOLY[clip] = j.polys || {}; SAMSEEDS[clip] = j.seeds || []; return (SAMMAP[clip] = j.frames || {}); })
    .catch(() => (SAMMAP[clip] = SAMMAP[clip] || {}));
  return SAML[clip];
}
function samInvalidate(clip) { delete SAML[clip]; }                     // 다음 samLabels 가 서버를 다시 읽는다
function samForget(clip, t) {                                            // 한 프레임의 SAM 결과를 캐시에서 뺀다(서버는 따로 뺀다)
  const k = tkey(t);
  if (SAMMAP[clip]) delete SAMMAP[clip][k];
  if (SAMPOLY[clip]) delete SAMPOLY[clip][k];
  SAML[clip] = Promise.resolve(SAMMAP[clip] || {});
  SAMFR[stemOf(clip)] = samFramesOf(clip);
  if (typeof updateRawBadge === "function") updateRawBadge(stemOf(clip));
}
async function dropSam(clip, t) {                                        // 서버 저장소 + 캐시에서 그 프레임 제거
  await postJSON("/api/sam2_drop", { clip, t }).catch(() => {});
  samForget(clip, t);
}
function samFramesOf(clip) { const m = SAMMAP[clip] || {}; return Object.keys(m).filter(k => Object.keys(m[k] || {}).length).map(Number).sort((a, b) => a - b); }
// SAM 저장소의 그 초 박스 → [cls,x,y,w,h] 목록(객체별 박스를 펼친다)
function samBoxesAt(frames, sec) {
  const o = frames[tkey(sec)];
  if (!o) return [];
  return Object.entries(o).map(([k, b]) => [samCls(+k), b[0], b[1], b[2], b[3], +k]);   // 6번째 = 객체 번호(화면 색·번호용, 저장 땐 뗀다)
}
function samPolysAt(clip, sec) { const o = (SAMPOLY[clip] || {})[tkey(sec)]; return o ? Object.entries(o).map(([k, p]) => ({ obj: +k, poly: p })) : []; }

let _ZOOM = 1, _TX = 0, _TY = 0, _ZCLIP = null;   // 확대 배율·위치는 같은 클립 안에서만 이어받고, 클립이 바뀌면 푼다
const _HIST = {};                    // clip → {undo:[{t,boxes,sam}], redo:[...]}  되돌리기 이력은 이 하나만 쓴다
let _PENDING = null;                 // 다른 프레임으로 이동해 적용할 되돌리기 항목 {clip,t,boxes,sam,ts}. 10초 안에 그 프레임이 열리지 않으면 버린다
let ED = null;        // 지금 열려 있는 편집기(같은 클립이면 재사용해 깜빡임을 없앤다)
let loadSeq = 0;      // 프레임 요청 순번. 늦게 도착한 그림은 버린다
const CLIPINFO = {};
async function clipInfo(clip) {
  if (CLIPINFO[clip]) return CLIPINFO[clip];
  const r = await fetch("/api/clipinfo?clip=" + encodeURIComponent(clip));
  if (!r.ok) throw new Error("clipinfo " + r.status);
  CLIPINFO[clip] = await r.json();
  return CLIPINFO[clip];
}

// 그 초의 프레임을 편집기에 띄운다. sec 는 프레임 격자(quant)에 맞춘다.
async function openFrameAt(clip, sec, mode) {
  if (LB.img) { LB.img = null; ED = null; }                 // 이미지 편집에서 영상으로 넘어오면 편집기를 새로 그린다
  if (sec != null && !isFinite(Number(sec))) sec = null;   // NaN 시각 방어(빈 입력·계산 오류) → 시작 프레임 자동 선택
  LB.mode = mode || LB.mode || clipMode(LB.src || ("data/원본데이터/" + clip + ".mp4"));   // 폴더로 가른다(배포 검증영상은 한 카테고리에 네 항목이 섞여 있다)
  if (ED && ED.clip === clip && ED.mode !== LB.mode) { ED = null; delete SAMST[clip]; }   // 라벨 모드(사람↔불연기)가 바뀌면 편집기를 새로 그린다: 객체 규약·버튼이 모드에 묶여 있다
  if (!ED || ED.clip !== clip) samInvalidate(clip);         // 클립을 새로 열면 SAM 저장소를 다시 읽는다(서버 큐가 그사이 저장했을 수 있다)
  if (LB.mode === "person" && !PLABELS) { try { PLABELS = await (await fetch("/api/labels?kind=person")).json(); } catch (e) { PLABELS = []; } }
  let ci;
  try { ci = await clipInfo(clip); }
  catch (e) { $("#center").innerHTML = '<div class="empty">이 영상 정보를 못 읽었습니다</div>'; return; }
  const last = Math.max(Math.floor(ci.dur), 0);
  if (sec == null) sec = (ci.fire && ci.fire.length) ? ci.fire[0].start : 0;   // 초를 안 주면: 정답 시각 → 없으면 0초
  sec = Math.min(Math.max(quant(sec), 0), last);
  LB.clip = clip; LB.sec = sec;
  saveSession();                      // 새로고침 후 이 자리로 돌아오게
  const saved = existingBoxes(stemOf(clip), sec);
  const url = `/frameat?clip=${encodeURIComponent(clip)}&t=${sec}`;
  // 화면에 얹을 초안: 손라벨 박스가 없을 때만. 순서 SAM → 정답(기록이 전혀 없는 프레임만)
  const afterShow = () => {
    Promise.all([samLabels(clip), gtLabels(clip)]).then(([sam, gt]) => {
      if (!ED || ED.clip !== clip || LB.sec !== sec) return;                  // 그사이 다른 클립·프레임으로 갔다
      if (!hasHand(saved)) {
        let bx = samBoxesAt(sam, sec), src = "sam";
        if (!bx.length && saved === null) { bx = gtBoxesAt(gt, sec).map(b => b.slice(0, 5)); src = "gt"; }        // 데이터셋 정답 박스 = 편집 가능한 라벨
        if (bx.length) ED.setPseudo(sec, bx, src);
      }
      ED.syncSam(); ED.fillShots(); ED.loadSam();
    });
  };
  if (ED && ED.clip === clip) {
    if (ED.keydown) { document.onkeydown = ED.keydown; document.onkeyup = ED.keyup; }   // 같은 클립 재클릭 시 showRawVideo 가 지운 단축키 복구
    // 화면을 지우지 않는다. 새 그림을 다 받은 뒤 바꿔 끼우면 사라졌다 나타나는 깜빡임이 없다.
    const n = ++loadSeq;
    const pre = new Image();
    pre.onload = pre.onerror = () => { if (n !== loadSeq) return; ED.applyFrame(sec, url, existingBoxes(stemOf(clip), sec)); afterShow(); preloadNear(clip, sec, last); };   // 손라벨은 그림을 받은 뒤 다시 읽는다(그사이 저장됐을 수 있다)
    pre.src = url;
    return;
  }
  loadSeq++;
  setTimeout(afterShow, 0);            // 편집기를 새로 만든 경우
  renderEditor({ clip, stem: stemOf(clip), src: clip + ".mp4", t: sec, last, W: ci.W, H: ci.H, url, saved });
  preloadNear(clip, sec, last);
}

const _PRE = new Map();               // 미리 받아 둔 프레임 그림(url → Image). 최근 60장만
function preloadNear(clip, sec, last) {   // 편집기에서 앞뒤 2칸을 미리 받아 두면 화살표 이동이 검수 확대창처럼 바로 바뀐다
  [1, -1, 2, -2].forEach(k => {
    const t = quant(sec + k * _step()); if (t < 0 || t > last) return;
    const u = `/frameat?clip=${encodeURIComponent(clip)}&t=${t}`;
    if (_PRE.has(u)) return;
    const g = new Image(); g.src = u; _PRE.set(u, g);
    if (_PRE.size > 60) _PRE.delete(_PRE.keys().next().value);
  });
}
function rectSvg(x, y, w, h, color, dash, fill) {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill ? color + fill : 'none'}" stroke="${color}" stroke-width="3" ${dash ? 'stroke-dasharray="8 5"' : ''}/>`;
}
const polySvg = (poly, W, H, color, fill) => (poly && poly.length) ? `<polygon points="${poly.map(p => `${p[0] * W},${p[1] * H}`).join(" ")}" fill="${fill ? color + fill : 'none'}" stroke="${color}" stroke-width="1.5"/>` : "";

// ---------- 화재 클립의 SAM 객체 규약(한 곳): 객체 1 = 불(cls 0) · 객체 2 = 연기(cls 1). 사람 클립은 객체 = 사람 번호, cls 0 ----------
const FIRE = { objs: [1, 2], name: { 1: "불", 2: "연기(수동)" }, color: { 1: "#f85149", 2: "#a371f7" }, cls: o => Math.max(0, Math.min(1, o - 1)), obj: c => (c === 1 ? 2 : 1) };
// 전파 대상 객체인가. 화재는 불(1)만 전파한다 — 연기는 마스크가 기둥의 진한 중심만 잡아 손 박스와 4배까지 벌어진다(IoU 0.2).
// 연기는 드래그로 그린 손라벨만 학습에 쓴다.
const PROP_OBJ = o => !isFire() || o === 1;
const SAM_COLORS = ["#e8913a", "#2ee6c5", "#d2a8ff", "#f778ba", "#ffd33d",
                    "#b5e853", "#f85149", "#c9d1d9", "#4d9de0", "#ff9ecd"];
// 객체 1~10 색. 서로 · 손라벨(#58a6ff)·정답(#79c0ff)·없음(#3fb950) 과 색차 ΔE 32 이상(2026-09-18 실측).
// 옛 팔레트는 1번과 5번이 ΔE 8.8 로 거의 같았다. 9·10번은 2026-09-22 에 추가(사람이 10명까지 나오는 편이 있다).
const isFire = () => LB.mode === "fire";
const objsFor = () => isFire() ? FIRE.objs.slice() : [1];                                   // 모드별 기본 객체 목록
const samCol = o => isFire() ? (FIRE.color[o] || FIRE.color[2]) : SAM_COLORS[(o - 1) % SAM_COLORS.length];
const samName = o => isFire() ? `객체 ${o} · ${FIRE.name[o] || FIRE.name[2]}` : `객체 ${o}`;
const samCls = o => isFire() ? FIRE.cls(o) : 0;                                             // 객체 → 박스 클래스
const objOfCls = c => isFire() ? FIRE.obj(c) : null;                                          // 박스 클래스 → 객체(화재만 정해진다)
const clsColorFor = (mode, c) => mode === "fire" ? (FIRE.color[FIRE.obj(+c)] || FIRE.color[2]) : SAM_COLORS[(+c) % SAM_COLORS.length];   // 모드별 클래스 색(편집기 밖에서도 같은 규약)
const SRC_COLOR = { hand: "#58a6ff", sam: "#e8913a", gt: "#79c0ff", none: "#3fb950" };   // 출처별 박스 색
const MASK_FILL = () => isFire() ? "2e" : "";                                                // 화재: 불·연기 마스크를 반투명 층으로 겹쳐 보인다(사람은 윤곽선만)
// 전파 방식은 실측 비교(화재 8클립) 결과 '객체별 분리 전파'가 가장 좋아 서버 기본값으로 고정했다. 화면에서 고르지 않는다.

const SAMST = {};                    // clip → SAM 작업 상태(참조샷·객체·구간). 클립 단위로 유지, 브라우저에 저장
function samState(clip) {
  if (SAMST[clip]) return SAMST[clip];
  let st = null;
  try { const raw = localStorage.getItem("kisa_sam_" + clip.split("/").pop()); if (raw) st = JSON.parse(raw); } catch (e) { st = null; }   // 브라우저에 남긴 참조샷 복원
  st = Object.assign({ seeds: [], objs: [1], cur: 1, a: null, b: null }, st || {});
  delete st.result; st.propFrames = [];               // propFrames 는 저장소 기준으로 다시 맞춘다(syncSam)
  SAMST[clip] = st; pullRange(clip); return st;      // 이 브라우저에 없던 구간은 서버 값으로 채운다
}
function pushRange(clip) {                            // 전파 구간을 서버에 적는다(브라우저에만 있으면 Thor 로 안 간다)
  const st = SAMST[clip]; if (!st) return;
  const stem = clip.split("/").pop().replace(/\.mp4$/, "");
  if (typeof saveClipState === "function") saveClipState(stem, { a: st.a == null ? null : st.a, b: st.b == null ? null : st.b });
}
function pullRange(clip) {                            // 이 브라우저에 구간이 없으면 서버 값을 가져온다(다른 장비에서 잡아 둔 것)
  const st = SAMST[clip]; if (!st) return;
  const stem = clip.split("/").pop().replace(/\.mp4$/, "");
  const sv = (typeof CLIPST !== "undefined" && CLIPST[stem]) || null; if (!sv) return;
  if (st.a == null && sv.a != null) st.a = sv.a;
  if (st.b == null && sv.b != null) st.b = sv.b;
}
const _PERSIST_T = {};
function persistSam(clip) {                           // 참조샷·객체·구간·손라벨참조 토글만 남긴다(결과는 서버 저장소에 있다). 300ms 디바운스
  clearTimeout(_PERSIST_T[clip]);
  _PERSIST_T[clip] = setTimeout(() => {
    const st = SAMST[clip]; if (!st) return;
    const seeds = st.seeds.map(q => ({ t: q.t, obj: q.obj, box: q.box, pts: q.pts || [], fromHand: !!q.fromHand, fromGT: !!q.fromGT }));   // 폴리곤·박스 인덱스는 다시 계산되니 제외
    try { localStorage.setItem("kisa_sam_" + clip.split("/").pop(), JSON.stringify({ seeds, objs: st.objs, cur: st.cur, a: st.a, b: st.b })); } catch (e) {}
    pushRange(clip);                                  // 구간은 서버에도 적는다(다른 장비·Thor 와 맞추려고)
  }, 300);
}
const iou4 = (a, b) => { const x1 = Math.max(a[0], b[0]), y1 = Math.max(a[1], b[1]), x2 = Math.min(a[0] + a[2], b[0] + b[2]), y2 = Math.min(a[1] + a[3], b[1] + b[3]); const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1); return inter / (a[2] * a[3] + b[2] * b[3] - inter || 1); };   // [x,y,w,h] 두 박스의 IoU
const box4 = b => [b[1], b[2], b[3], b[4]];                                                   // [cls,x,y,w,h] → [x,y,w,h]

function renderEditor(f) {
  const MY = {};                                      // 이 편집기 인스턴스 표식(재렌더 뒤 옛 클로저가 화면을 건드리지 않게)
  const mine = () => ED && ED._tok === MY;
  const SM = samState(f.clip);                        // SAM 작업 상태
  if (isFire()) { SM.objs = objsFor(); if (!FIRE.objs.includes(SM.cur)) SM.cur = 1; }   // 화재: 불·연기 두 객체 고정
  if (!(SM.propFrames && SM.propFrames.length) && (SAMFR[f.stem] || []).length) SM.propFrames = SAMFR[f.stem].map(tkey);   // 저장소에 SAM 결과가 있으면 전파 켜진 상태로 복원
  LB.boxes = f.saved ? f.saved.map(b => b.slice()) : []; LB.src = hasHand(f.saved) ? "hand" : "none";
  if (f.prefill && f.prefill.length && !hasHand(f.saved)) { LB.boxes = f.prefill.map(b => b.slice()); LB.src = "gt"; }   // 데이터셋 정답 박스 = 우리 라벨과 같은 것. 고치면 손라벨로 저장된다
  let SP = [], SMASK = null;                          // 현재 프레임·현재 객체의 점, 마스크
  const c = $("#center"); c.innerHTML = "";
  const top = el("div"); top.style.cssText = "width:100%;align-self:flex-start";   // #center 가 세로 가운데 정렬이라 위로 붙인다
  c.appendChild(top);
  // 이미지 + 그리기 오버레이 (이미지 위에는 아무 글자도 얹지 않는다)
  const pane = el("div"); pane.style.cssText = `width:100%;max-width:min(${f.W}px, calc((100vh - 400px) * 16 / 9));margin:0 auto;padding:12px 8px 0`;
  top.appendChild(pane);
  const wrap = el("div"); wrap.style.cssText = "position:relative;overflow:hidden";
  const img = el("img"); img.src = f.url; img.style.cssText = "width:100%;display:block;border-radius:6px;-webkit-user-drag:none";
  const ov = el("div"); ov.style.cssText = "position:absolute;inset:0;cursor:crosshair";
  wrap.appendChild(img); wrap.appendChild(ov);
  img.addEventListener("load", () => { if (_zoom !== 1) _applyZoom(); }, { once: true });   // 이어받은 확대 반영(크기 확정 뒤)
  // 휠 = 프레임 확대/축소(1~8x). 커서 기준, 프레임 박스 안에서만 확대(주변 레이아웃 안 밀림).
  if (_ZCLIP !== f.clip) { _ZOOM = 1; _TX = 0; _TY = 0; _ZCLIP = f.clip; }   // 다른 클립 = 확대 해제
  let _zoom = _ZOOM, _tx = _TX, _ty = _TY;   // origin 0 0 고정 + translate 로 커서 밑 지점을 붙잡아 누적 확대해도 안 튄다
  const _applyZoom = () => {
    const rc = wrap.getBoundingClientRect();
    if (rc.width) {                                   // 클립마다 표시 크기가 달라 이어받은 위치가 밖으로 나갈 수 있다
      _tx = Math.min(0, Math.max(rc.width * (1 - _zoom), _tx));
      _ty = Math.min(0, Math.max(rc.height * (1 - _zoom), _ty));
    }
    _ZOOM = _zoom; _TX = _tx; _TY = _ty;              // 다음 클립이 이어받을 값
    const t = "translate(" + _tx + "px," + _ty + "px) scale(" + _zoom + ")";
    img.style.transformOrigin = "0 0"; img.style.transform = t;
    ov.style.transformOrigin = "0 0"; ov.style.transform = t;
  };
  ov.addEventListener("wheel", ev => {
    ev.preventDefault();
    const rc = wrap.getBoundingClientRect();
    const cx = ev.clientX - rc.left, cy = ev.clientY - rc.top, z0 = _zoom;
    _zoom = Math.min(Math.max(_zoom * (ev.deltaY < 0 ? 1.15 : 1 / 1.15), 1), 8);
    _tx = cx - (_zoom / z0) * (cx - _tx);   // 지금 커서 밑에 있는 지점이 확대 후에도 커서 아래 그대로
    _ty = cy - (_zoom / z0) * (cy - _ty);
    _tx = Math.min(0, Math.max(rc.width * (1 - _zoom), _tx));   // 박스 밖 빈공간 방지
    _ty = Math.min(0, Math.max(rc.height * (1 - _zoom), _ty));
    if (_zoom === 1) { _tx = 0; _ty = 0; }
    _applyZoom();
  }, { passive: false });

  // ---------- 도구 줄: ↶ ↷ 손라벨참조 정답참조 [전파] 전파지우기 라벨검수 · 상태 · 학습프레임 초기화 ----------
  const status = el("span", "now", "");            // 저장 상태(재생바 안)
  const bar = buildFrameBar(f, status);
  const rowAct = el("div"); rowAct.style.cssText = "display:flex;align-items:center;gap:8px;margin:0 0 10px;flex-wrap:wrap";
  const mkBtn = (txt, title) => { const b = el("button", null, txt); b.title = title; b.style.cssText = "width:auto;padding:0 9px;height:28px;background:var(--panel);color:var(--tx);border:1px solid var(--line);border-radius:6px;font-weight:700;cursor:pointer"; return b; };
  const bUndo = mkBtn("↶", "되돌리기 (Ctrl+Z)"), bRedo = mkBtn("↷", "다시하기 (Ctrl+Shift+Z)"), bRev = mkBtn("라벨 검수", "이 클립의 SAM 전파 결과를 격자로 검수");
  const bGo = mkBtn("전파", "참조샷으로 전파 → SAM 저장소 자동 저장. 결과가 있는 클립에서 지금 프레임에 참조샷이 있으면 '이어서 전파' = 그 프레임부터 종료까지 뒤로만"); bGo.style.cssText += ";color:var(--blue);border-color:var(--blue);font-weight:800;padding:0 12px";
  const bClr = mkBtn("전파 지우기", "이 클립의 SAM 전파 결과를 저장소에서 전부 뺀다(손라벨은 그대로)"); bClr.hidden = true;
  const pstat = el("span", "now", ""); pstat.style.whiteSpace = "nowrap";
  const tstat = el("span", "now", ""); tstat.style.cssText = "color:var(--mut);font-size:12px;white-space:nowrap";
  const bReset = mkBtn("학습프레임 초기화", "이 클립의 손라벨·전파 결과·참조샷을 전부 지운다(손라벨은 백업됨)"); bReset.style.cssText += ";color:#f85149;border-color:#f8514966;margin-left:auto";
  // 순서: 되돌리기 · 참조샷 만들기(손라벨) · 전파 · 검수 · 상태 · 초기화
  [bUndo, bRedo, bGo, bClr, bRev, tstat, pstat, bReset].forEach(b => rowAct.appendChild(b));
  const rowObj = el("div"); rowObj.style.cssText = "display:flex;flex-direction:column;gap:6px;margin-top:10px";
  const shots = el("div");
  const undoBar = el("div"); undoBar.style.cssText = "padding:2px 2px 8px";   // 삭제 직후 되돌리기 버튼이 잠깐 뜨는 자리
  [rowAct, wrap, bar, shots, rowObj, undoBar].forEach(x => pane.appendChild(x));   // 순서: 도구 → 화면 → 프레임바 → 미리보기 → 객체
  if (f.image) {                                      // 정지 이미지: 프레임·전파·미리보기가 없다. 정답이 있으면 '정답 가져오기'로 한 번에 손라벨로
    bar.style.display = "none"; shots.style.display = "none";
    [bGo, bClr, bRev, bReset].forEach(b => { b.hidden = true; });
    tstat.style.display = "none";
  }
  const spin = pct => `<span style="display:inline-block;width:12px;height:12px;border:2px solid #58a6ff55;border-top-color:#58a6ff;border-radius:50%;animation:ed_sp .8s linear infinite;vertical-align:-2px;margin-right:6px"></span>${pct}%`;
  if (!document.getElementById("ed_sp")) { const stl = document.createElement("style"); stl.id = "ed_sp"; stl.textContent = "@keyframes ed_sp{to{transform:rotate(360deg)}}"; document.head.appendChild(stl); }
  const flash = (html, ms) => { pstat.innerHTML = html; if (ms) setTimeout(() => { if (mine() && pstat.innerHTML === html) pstat.innerHTML = ""; }, ms); };

  const updateTStat = () => {
    const hs = shotSecs(f.stem), hset = new Set(hs.map(([t]) => t));
    const sam = samFramesOf(f.clip).filter(t => !hset.has(t)).length;
    const gt = GTMAP[f.clip]; const gtn = gt ? gtFramesOf(f.clip).length : 0, gtp = gt && gt.points ? Object.values(gt.points).reduce((a, o) => a + Object.keys(o).length, 0) : 0;
    tstat.textContent = `훈련 데이터 ${hs.length + sam}건 (손라벨 ${hs.length} · 영상전파 ${sam}${gtn || gtp ? ` · 정답 ${gtn ? gtn + "박스프레임" : ""}${gtn && gtp ? " " : ""}${gtp ? gtp + "점" : ""}` : ""})`;
  };
  let drawRef = () => {};      // 아래에서 draw 로 채운다(선언 순서 때문에 참조로 둔다)
  const fillShots = () => (persistSam(f.clip), drawTrack(bar.tk, f), updateTStat(), renderShotRow(shots, f, {
    onDeleted: (sec, prev) => {                       // 미리보기 × 로 프레임 라벨을 지움 → [규칙 1] 그 프레임의 참조샷도 전부 지운다. 이력에 남기고 되돌리기 버튼
      if (prev && prev.length) { hist.push({ t: sec, boxes: JSON.stringify(prev), sam: null }); redo.length = 0; }
      frameDeleted(sec); showUndo(sec, prev);
    },
  }));
  let undoTimer = null;
  const showUndo = (sec, prev) => {                   // 삭제 되돌리기: 지운 박스를 그대로 다시 써 넣는다. 6초 뒤 버튼은 사라진다
    clearTimeout(undoTimer); undoBar.innerHTML = "";
    if (!prev || !prev.length) return;
    const b = el("button", null, `↺ 되돌리기`);
    b.style.cssText = "background:var(--panel2);color:var(--tx);border:1px solid var(--blue);border-radius:6px;padding:4px 10px;font-size:11px;font-weight:700;cursor:pointer";
    b.onclick = async () => {
      b.textContent = "…";
      try {
        await postLabel(f.stem, sec, f.W, f.H, prev, f.src);
        if (sec === f.t) { LB.boxes = prev.map(q => q.slice()); f.saved = prev; LB.src = "hand"; }
        const k = hist.findIndex(e => e.t === sec && !e.sam); if (k >= 0) hist.splice(k, 1);
        fillShots(); drawRef(); undoBar.innerHTML = "";
      } catch (e) { b.textContent = "실패"; }
    };
    undoBar.appendChild(b);
    undoTimer = setTimeout(() => { undoBar.innerHTML = ""; }, 6000);
  };

  // ---------- 그리기: 손라벨 파랑 · SAM 주황 · 정답 하늘. 객체가 잡은 박스는 객체 색, 마스크는 객체별 층 ----------
  let saveState = "";
  const draw = (drag, dcls) => {
    let s = `<svg viewBox="0 0 ${f.W} ${f.H}" style="position:absolute;inset:0;width:100%;height:100%">`;
    const col = SRC_COLOR[LB.src] || SRC_COLOR.none;
    LB.boxes.forEach((b, i) => {                     // 박스의 객체: 참조샷 → 전파 결과의 번호 → 화재면 클래스(불=1 연기=2). 있으면 객체 색 + 번호
      const q = seedForBox(i);
      const obj = q ? q.obj : (b[5] != null ? +b[5] : (isFire() ? objOfCls(b[0]) : (f.image ? i + 1 : null)));   // 6번째(객체 번호)는 전파·손라벨 어디서 왔든 같은 뜻   // 사람 이미지: 박스 순서 = 객체 번호(전파가 없으니 번호는 표시용). 객체 줄 색과 맞춘다
      s += rectSvg(b[1] * f.W, b[2] * f.H, b[3] * f.W, b[4] * f.H, obj ? samCol(obj) : col);
      if (obj && !q) { const bx = b[1] * f.W + 2, by = b[2] * f.H; s += `<text x="${bx}" y="${by >= 18 ? by - 4 : (b[2] + b[4]) * f.H + 16}" fill="${samCol(obj)}" font-size="16" font-weight="800">${obj}</text>`; }
    });
    const gt = GTMAP[f.clip];                         // 정답라벨(데이터셋 제공): 하늘색 점선 박스 + 마름모 점
    if (gt && LB.src !== "gt" && !f.image) gtBoxesAt(gt, f.t).forEach(b => { s += rectSvg(b[1] * f.W, b[2] * f.H, b[3] * f.W, b[4] * f.H, SRC_COLOR.gt, true); });   // 이미지는 정답이 곧 편집 중인 박스라 겹그리지 않는다
    if (gt) gtPointsAt(gt, f.t).forEach(p => { const x = p.x * f.W, y = p.y * f.H; s += `<polygon points="${x},${y - 7} ${x + 7},${y} ${x},${y + 7} ${x - 7},${y}" fill="${SRC_COLOR.gt}" stroke="#0b0e13" stroke-width="1.5"/><text x="${x + 9}" y="${y - 6}" fill="${SRC_COLOR.gt}" font-size="13" font-weight="800">정답${p.obj}</text>`; });
    // 전파 결과 마스크 윤곽선은 그리지 않는다(박스 확인을 방해해서 뺐다). 학습에 쓰는 것은 박스라 사라져도 되돌리면 samPolysAt 한 줄이다
    const numAt = (box, cc, n) => { const bx = box[0] * f.W + 2, by = box[1] * f.H; return `<text x="${bx}" y="${by >= 18 ? by - 4 : (box[1] + box[3]) * f.H + 16}" fill="${cc}" font-size="16" font-weight="800">${n}</text>`; };
    SM.seeds.filter(sd => near(sd.t, f.t) && !(sd.obj === SM.cur && SMASK)).forEach(sd => {   // 이 프레임 참조샷: 윤곽선 + 번호 + 점
      const cc = samCol(sd.obj);
      s += numAt(sd.box, cc, sd.obj);   // 윤곽선은 안 그린다(박스 보기를 방해). 번호만 남긴다
      (sd.pts || []).forEach(p => { s += `<circle cx="${p[0] * f.W}" cy="${p[1] * f.H}" r="3" fill="${p[2] ? "#58a6ff" : "#f85149"}" stroke="${cc}" stroke-width="1"/>`; });
    });
    if (SMASK && SMASK.box) s += numAt(SMASK.box, samCol(SM.cur), SM.cur);   // 탭한 결과도 윤곽선 없이 번호만(박스는 LB.boxes 로 그려진다)
    SP.forEach(p => { s += `<circle cx="${p[0] * f.W}" cy="${p[1] * f.H}" r="3" fill="${p[2] ? "#58a6ff" : "#f85149"}" stroke="#fff" stroke-width="1"/>`; });
    if (drag) s += rectSvg(drag.x, drag.y, drag.w, drag.h, isFire() ? samCol(objOfCls(dcls)) : samCol(SM.cur), true);
    ov.innerHTML = s + "</svg>";
    status.innerHTML = saveState ? `<span style="color:#f85149">${saveState}</span>` : "";   // 성공은 표시하지 않는다
  };
  drawRef = draw;
  const saveNow = async () => {                       // 화면 박스 → 손라벨 저장(SAM 전파 결과·정답 초안은 보이는 그대로 손라벨로)
    LB.boxes.forEach((b, i) => { if (b[5] == null) { const q = seedForBox(i); const o = q ? q.obj : (isFire() ? objOfCls(b[0]) : null); if (o != null) b[5] = o; } });   // 객체 번호를 채워 저장(옛 박스도)
    try {
      await postLabel(f.stem, f.t, f.W, f.H, LB.boxes, f.src);
      f.saved = LB.boxes.map(b => b.slice()); LB.src = "hand";
      if ((SAMMAP[f.clip] || {})[tkey(f.t)]) { samForget(f.clip, f.t); SM.propFrames = SAMFR[f.stem].map(tkey); }   // 손라벨이 SAM 을 대신(서버 저장소는 savelabel 이 뺐다)
      fillShots(); saveState = ""; draw(); if (typeof updateRawBadge === "function") updateRawBadge(f.stem);   // 목록 배지(영상·이미지 공통)
    } catch (e) { saveState = "저장 실패"; draw(); }
  };

  // ---------- 되돌리기(클립 단위 이력 하나): 박스 + 이 프레임의 SAM 상태(점·마스크·참조샷) ----------
  const HS = _HIST[f.clip] || (_HIST[f.clip] = { undo: [], redo: [] });
  const hist = HS.undo, redo = HS.redo;                                    // 항목 = {t, boxes(JSON), sam(JSON|null)}
  const samSnap = t => JSON.stringify({ cur: SM.cur, SP: t === f.t ? SP : null, SMASK: t === f.t ? SMASK : null, seeds: SM.seeds.filter(q => near(q.t, t)) });
  const applySam = o => { SM.seeds = SM.seeds.filter(q => !near(q.t, f.t)).concat(o.seeds || []); SM.seeds.sort((a, b) => a.t - b.t || a.obj - b.obj); SM.cur = o.cur || SM.cur; if (o.SP) { SP = o.SP; SMASK = o.SMASK; drawObjs(); } else loadSam(); };
  const snap = () => { hist.push({ t: f.t, boxes: JSON.stringify(LB.boxes), src: LB.src, sam: samSnap(f.t) }); if (hist.length > 300) hist.shift(); redo.length = 0; };   // src 도 남긴다(초안 상태로 되돌리면 저장 대신 손라벨 기록을 지운다)
  let _tapGen = 0;                                   // 되돌리기마다 +1 → 그 전에 보낸 탭 요청 결과는 버린다
  const applyHist = e => {                           // 이력 항목을 지금 프레임에 적용. 초안(SAM·정답) 상태면 손라벨 기록을 지우고 초안으로 되돌린다
    LB.boxes = JSON.parse(e.boxes); sel = null; if (e.sam) applySam(JSON.parse(e.sam));
    if (e.src && e.src !== "hand") { LB.src = e.src; draw(); clearLabel(f.stem, f.t).then(() => { f.saved = null; fillShots(); }).catch(() => {}); }
    else { LB.src = "hand"; draw(); saveNow(); }
  };
  const restore = (from, to) => {
    if (!from.length) return;
    _tapGen++;
    const e = from.pop();
    const cur = (e.t === f.t) ? LB.boxes : (existingBoxes(f.stem, e.t) || []);   // 되돌리기 전 그 프레임의 현재 상태 → 반대편 이력
    to.push({ t: e.t, boxes: JSON.stringify(cur), src: (e.t === f.t) ? LB.src : (hasHand(cur) ? "hand" : "none"), sam: samSnap(e.t) });
    if (e.t !== f.t) { _PENDING = { clip: f.clip, t: e.t, boxes: e.boxes, src: e.src, sam: e.sam, ts: Date.now() }; openFrameAt(f.clip, e.t, LB.mode); return; }   // 다른 프레임 → 이동 후 적용
    applyHist(e);
  };

  // ---------- 마우스: 클릭 = SAM 점 · 드래그 = 현재 객체 박스(빈 곳=새 박스, 박스 안=이동, 변=크기) · 우클릭 = 제외점 · Space+드래그 = 화면 이동 ----------
  let st = null, curCls = 0, rz = null, mv = null, sel = null, pan = null, _space = false, sd = null, lastP = null, _resized = false;
  const HIT = 8;                       // 화면 기준 8px 안이면 그 변을 잡은 것으로 본다
  const CURSOR = { n: "ns-resize", s: "ns-resize", w: "ew-resize", e: "ew-resize", nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize" };
  const toImg = ev => { const rc = img.getBoundingClientRect(); return { x: (ev.clientX - rc.left) / rc.width * f.W, y: (ev.clientY - rc.top) / rc.height * f.H }; };
  const hitTest = p => {                             // 마우스가 어느 박스의 어느 변에 닿았나. 위에 그린 박스(뒤 항목)부터 본다
    const rc = img.getBoundingClientRect();
    const tol = HIT * (f.W / (rc.width || f.W));       // 화면 px → 원본 px
    for (let i = LB.boxes.length - 1; i >= 0; i--) {
      const b = LB.boxes[i];
      const x1 = b[1] * f.W, y1 = b[2] * f.H, x2 = x1 + b[3] * f.W, y2 = y1 + b[4] * f.H;
      if (p.x < x1 - tol || p.x > x2 + tol || p.y < y1 - tol || p.y > y2 + tol) continue;
      let tag = "";
      if (Math.abs(p.y - y1) <= tol) tag += "n"; else if (Math.abs(p.y - y2) <= tol) tag += "s";
      if (Math.abs(p.x - x1) <= tol) tag += "w"; else if (Math.abs(p.x - x2) <= tol) tag += "e";
      if (tag) return { i, tag };
    }
    return null;
  };
  const boxUnder = p => {                            // 커서가 얹힌 박스(안쪽 포함). 위에 그린 것부터 본다
    for (let i = LB.boxes.length - 1; i >= 0; i--) {
      const b = LB.boxes[i];
      const x1 = b[1] * f.W, y1 = b[2] * f.H, x2 = x1 + b[3] * f.W, y2 = y1 + b[4] * f.H;
      if (p.x >= x1 && p.x <= x2 && p.y >= y1 && p.y <= y2) return i;
    }
    return null;
  };
  const moveTo = p => {                              // 잡은 자리를 유지하며 옮긴다. 이미지 밖으로는 나가지 않는다
    const b = LB.boxes[mv.i]; if (!b) return;
    const w = b[3] * f.W, h = b[4] * f.H;
    b[1] = Math.min(Math.max(p.x - mv.ox, 0), f.W - w) / f.W;
    b[2] = Math.min(Math.max(p.y - mv.oy, 0), f.H - h) / f.H;
  };
  const resizeTo = p => {
    const b = LB.boxes[rz.i]; if (!b) return;
    let x1 = b[1] * f.W, y1 = b[2] * f.H, x2 = x1 + b[3] * f.W, y2 = y1 + b[4] * f.H;
    if (rz.tag.includes("n")) y1 = p.y;
    if (rz.tag.includes("s")) y2 = p.y;
    if (rz.tag.includes("w")) x1 = p.x;
    if (rz.tag.includes("e")) x2 = p.x;
    if (x2 < x1) { const t = x1; x1 = x2; x2 = t; }    // 반대편으로 넘겨 끌면 좌우가 뒤집힌다
    if (y2 < y1) { const t = y1; y1 = y2; y2 = t; }
    x1 = Math.max(x1, 0); y1 = Math.max(y1, 0); x2 = Math.min(x2, f.W); y2 = Math.min(y2, f.H);
    b[1] = x1 / f.W; b[2] = y1 / f.H;
    b[3] = Math.max(x2 - x1, 6) / f.W; b[4] = Math.max(y2 - y1, 6) / f.H;   // 6px 아래로는 안 줄인다
  };
  ov.oncontextmenu = ev => { ev.preventDefault(); if (_resized) { _resized = false; return; } if (!_space && !rz && !mv) { const p = toImg(ev); samPoint(p.x / f.W, p.y / f.H, 0); } };   // 우클릭 = 제외점
  ov.onmousedown = ev => {
    ev.preventDefault(); _resized = false;
    if (_space) { pan = { sx: ev.clientX, sy: ev.clientY, tx0: _tx, ty0: _ty }; ov.style.cursor = "grabbing"; return; }   // 스페이스+드래그 = 확대이미지 이동
    const p = toImg(ev);
    const h = ev.button === 2 || ev.shiftKey ? null : hitTest(p);   // 우클릭·Shift 는 변 잡기 없음
    if (h) { snap(); rz = h; rz.owner = seedForBox(h.i); sel = h.i; return; }   // 소유 참조샷은 움직이기 전에 잡아둔다(옮긴 뒤 IoU 로 찾으면 놓친다)
    if (ev.button !== 0) return;
    sd = { p, u: ev.shiftKey ? null : boxUnder(p) };   // 누른 자리 기억. 끌면 박스(빈 곳=새 박스 · 박스 안=이동), 안 끌면 onclick 에서 점
  };
  ov.onmousemove = ev => {
    lastP = toImg(ev);
    if (pan) {
      const rc = wrap.getBoundingClientRect();
      _tx = Math.min(0, Math.max(rc.width * (1 - _zoom), pan.tx0 + (ev.clientX - pan.sx)));
      _ty = Math.min(0, Math.max(rc.height * (1 - _zoom), pan.ty0 + (ev.clientY - pan.sy)));
      _applyZoom(); return;
    }
    const p = lastP;
    if (sd) {                                        // 3px 넘게 끌면 드래그 시작(클릭=점 과 구분)
      if (Math.hypot(p.x - sd.p.x, p.y - sd.p.y) < 3) return;
      if (sd.u !== null) { const b = LB.boxes[sd.u]; snap(); mv = { i: sd.u, ox: sd.p.x - b[1] * f.W, oy: sd.p.y - b[2] * f.H, owner: seedForBox(sd.u) }; sel = sd.u; }
      else { curCls = samCls(SM.cur); st = sd.p; }   // 새 박스 = 현재 객체(화재: 1 불 · 2 연기)
      sd = null; _resized = true;                     // 드래그 뒤의 click 은 점으로 안 찍는다
    }
    if (rz) { resizeTo(p); draw(); return; }
    if (mv) { moveTo(p); draw(); return; }
    if (st) { draw({ x: Math.min(st.x, p.x), y: Math.min(st.y, p.y), w: Math.abs(p.x - st.x), h: Math.abs(p.y - st.y) }, curCls); return; }
    const h = hitTest(p);
    ov.style.cursor = h ? (CURSOR[h.tag] || "crosshair") : (boxUnder(p) !== null ? "move" : "crosshair");
  };
  const finish = ev => {
    if (pan) { pan = null; ov.style.cursor = _space ? "grab" : "crosshair"; return; }   // 이동 끝
    if (rz) { const i = rz.i, ow = rz.owner; rz = null; _resized = true; seedFromBox(i, false, ow); sel = null; draw(); saveNow(); return; }   // 크기조절 끝 → (참조샷이 있으면) 따라가고 저장
    if (mv) { const i = mv.i, ow = mv.owner; mv = null; seedFromBox(i, false, ow); sel = null; draw(); saveNow(); return; }                    // 이동 끝 → (참조샷이 있으면) 따라가고 저장
    sd = null;
    if (!st) return; const p = toImg(ev);
    const x = Math.min(st.x, p.x), y = Math.min(st.y, p.y), w = Math.abs(p.x - st.x), h = Math.abs(p.y - st.y); st = null;
    if (w > 4 && h > 4) { snap(); LB.boxes.push([curCls, x / f.W, y / f.H, w / f.W, h / f.H, SM.cur]); seedFromBox(LB.boxes.length - 1, true); }   // 새로 그린 박스 = 현재 객체 참조샷
    draw(); saveNow();
  };
  ov.onmouseup = finish;
  ov.onmouseleave = finish;                          // sel 유지 → 박스 클릭 후 마우스 나가도 Del 됨
  ov.onclick = ev => {                               // 좌클릭(끌지 않음) = 후보/박스 탭 또는 포함점
    if (_resized) { _resized = false; return; }
    if (_space || pan || rz || mv) return;
    const p = toImg(ev); const x = p.x / f.W, y = p.y / f.H;
    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    samPoint(x, y, 1);
  };

  // ---------- SAM: 탭 → 마스크 → 참조샷(손라벨 저장) ----------
  const seedSet = (box, poly, pts, idx) => {          // 현재 객체·현재 프레임의 참조샷을 이걸로 바꾼다
    SM.seeds = SM.seeds.filter(q => !(near(q.t, f.t) && q.obj === SM.cur));
    SM.seeds.push({ t: f.t, obj: SM.cur, box, poly: poly || [], pts: (pts || []).slice(), i: idx }); SM.seeds.sort((a, b) => a.t - b.t || a.obj - b.obj);
    drawObjs();
  };
  const seedForBox = i => {                          // 이 프레임에서 LB.boxes[i] 의 참조샷. 박스의 객체 번호(6번째)가 곧 정체성 → 그 번호의 참조샷(거리 안 본다)
    const b = LB.boxes[i]; if (!b) return null;
    const here = SM.seeds.filter(q => near(q.t, f.t));
    if (b[5] != null) return here.find(q => q.obj === +b[5]) || null;
    let best = null, bi = 0.3;                         // 번호 없는 옛 박스만: 위치(IoU) → 인덱스. pinObjs 가 곧 번호를 박아 다음부턴 이 길로 안 온다
    here.forEach(q => { const v = iou4(q.box, box4(b)); if (v > bi) { bi = v; best = q; } });
    return best || here.find(q => q.i === i) || null;
  };
  const pinObjs = () => {                            // 번호 없는 박스에 객체 번호를 한 번 박는다(참조샷 → 화재는 클래스). 이후 편집은 번호만 따른다
    LB.boxes.forEach((b, i) => { if (b[5] == null) { const q = seedForBox(i); const o = q ? q.obj : (isFire() ? objOfCls(b[0]) : null); if (o != null) b[5] = o; } });
  };
  const clipPoly = (poly, box) => (poly || []).map(p => [Math.min(Math.max(p[0], box[0]), box[0] + box[2]), Math.min(Math.max(p[1], box[1]), box[1] + box[3])]);   // 마스크 윤곽선을 박스 안으로 자른다(박스를 줄이면 마스크도 그만큼 줄어 보인다)
  const seedFromBox = (i, create, ownerIn) => {   // ownerIn: 움직이기 전에 잡아둔 소유 참조샷(있으면 IoU 재탐색 대신 그걸 쓴다)               // 박스의 참조샷 동기화. create=true(새 박스 드래그)면 참조샷이 없을 때 현재 객체 것으로 만든다.
    const b = LB.boxes[i]; if (!b) return;             // 옮기기·크기조절(create=false)은 '고치기'라 참조샷을 새로 만들지 않는다(전파 결과를 다듬을 때 칩이 쌓이지 않게)
    if (isFire() && b[0] === 1) { SMASK = null; return; }   // 연기 박스는 참조샷을 만들지 않는다(전파 대상 아님)
    const box = box4(b);
    const owner0 = ownerIn !== undefined ? ownerIn : seedForBox(i);
    const owner = (create && owner0 && owner0.obj !== SM.cur) ? null : owner0;
    const objKeep = owner ? owner.obj : (b[5] != null ? +b[5] : (create ? SM.cur : (isFire() ? objOfCls(b[0]) : null)));
    if (objKeep != null) b[5] = objKeep;               // 객체 번호를 박스에 박아 저장까지 남긴다(참조샷을 잃어도 번호·색 유지)   // 새 박스 드래그는 현재 객체로만: 겹친 다른 객체 박스에 IoU 로 붙지 않게
    if (owner) { owner.poly = clipPoly(owner.poly, box); owner.box = box; owner.i = i; if (owner.obj === SM.cur) SMASK = { box, poly: owner.poly }; drawObjs(); }   // 박스를 옮기거나 줄이면 마스크도 박스 안으로 잘라 따라가게
    else if (create) { SMASK = { box, poly: [] }; seedSet(box, [], SP, i); }
    draw();
  };
  async function samPoint(x, y, label) {
    const t = f.t;
    const rc = img.getBoundingClientRect(); const tolX = 10 / rc.width, tolY = 10 / rc.height;
    const nearPt = SP.findIndex(q => Math.abs(q[0] - x) < tolX && Math.abs(q[1] - y) < tolY);
    snap();
    if (nearPt >= 0) { SP.splice(nearPt, 1); return samRecompute(); }   // 찍힌 점을 다시 탭 = 그 점 제거
    const claimed = new Set(LB.boxes.map((b, i) => i).filter(i => { const q = seedForBox(i); return q && q.obj !== SM.cur; }));   // 다른 객체의 박스
    // 화면 박스(손/SAM/정답) 안을 점 없이 좌클릭 → 그 박스로 프롬프트 (남의 객체 박스는 pool 에서 제외 → 뺏지 않는다)
    const pool = LB.boxes.map((b, i) => ({ b, i })).filter(o => !claimed.has(o.i));
    const hits = (label === 1 && !SP.length) ? pool.filter(o => x >= o.b[1] && x <= o.b[1] + o.b[3] && y >= o.b[2] && y <= o.b[2] + o.b[4]) : [];
    const hit = hits.sort((a, b) => a.b[3] * a.b[4] - b.b[3] * b.b[4])[0] || null;   // 겹치면 가장 작은 박스
    if (hit && isFire()) {                             // 화재: 탭한 박스의 클래스가 곧 객체. 다른 객체 박스를 탭하면 그 객체로 바꿔 잡는다(연기 박스가 불로 바뀌지 않게)
      const o = objOfCls(hit.b[0]);
      if (o !== SM.cur) { SM.cur = o; SP = []; SMASK = null; drawObjs(); }
      if (!PROP_OBJ(o)) { sel = hit.i; draw(); return; }   // 연기 박스 = 선택만(수동 편집). SAM 마스크로 바꾸지 않는다
    }
    SP.push([+x.toFixed(5), +y.toFixed(5), label]); draw();                       // 탭 점은 항상 남긴다(박스 프롬프트여도 표시·참조샷에 기록)
    if (!hit && !SP.some(q => q[2] === 1)) return;                                  // 제외점만 있으면 마스크·박스를 만들지 않는다(포함점이나 박스가 있어야 대상이 정해진다)
    const body = hit ? { clip: f.clip, t, pts: [], box: box4(hit.b) } : { clip: f.clip, t, pts: SP };
    await applyMask(t, body, hit);
  }
  async function samRecompute() {                    // 점이 바뀐 뒤 현재 객체 마스크 다시 계산
    const t = f.t; const sd0 = SM.seeds.find(q => near(q.t, t) && q.obj === SM.cur);
    if (!SP.some(q => q[2] === 1)) {                   // 포함점이 없음(다 지웠거나 제외점만) → 이 객체의 참조샷·박스 제거
      if (sd0 && sd0.i != null && LB.boxes[sd0.i]) { LB.boxes.splice(sd0.i, 1); SM.seeds.forEach(q => { if (near(q.t, t) && q.i != null && q.i > sd0.i) q.i -= 1; }); }
      SM.seeds = SM.seeds.filter(q => q !== sd0); SMASK = null; drawObjs(); draw(); saveNow(); return;
    }
    draw();
    await applyMask(t, { clip: f.clip, t, pts: SP }, null);
  }
  async function applyMask(t, body, hit) {           // 서버 SAM 마스크 → 현재 객체의 박스·참조샷 → 손라벨 저장
    const gen = _tapGen;
    const r = await postJSON("/api/sam2_mask", body).catch(() => ({}));
    if (f.t !== t || gen !== _tapGen) return;         // 다른 프레임으로 갔거나 그사이 되돌리기 → 결과 버림
    if (!r.box) { SMASK = null; draw(); return; }
    SMASK = { box: r.box, poly: r.poly };
    const nb = [samCls(SM.cur), r.box[0], r.box[1], r.box[2], r.box[3], SM.cur];   // 6번째 = 객체 번호
    const sd0 = SM.seeds.find(q => near(q.t, t) && q.obj === SM.cur);
    let idx = (sd0 && sd0.i != null && LB.boxes[sd0.i]) ? sd0.i : ((hit && hit.i >= 0) ? hit.i : -1);
    if (idx >= 0) LB.boxes[idx] = nb; else { LB.boxes.push(nb); idx = LB.boxes.length - 1; }
    if (PROP_OBJ(SM.cur)) seedSet(r.box, r.poly, SP, idx);   // 연기(화재 객체 2)는 박스만 남기고 참조샷은 안 만든다
    else { SP = []; SMASK = { box: r.box, poly: r.poly }; drawObjs(); }
    draw(); saveNow();                                 // 탭한 프레임 → 손라벨
  }
  // ---------- SAM: 객체 줄 ----------
  function drawObjs() {
    if (!isFire()) {                                 // 사람: 이 클립의 손라벨·전파·참조샷에 있는 객체 번호를 전부 목록에
      const S0 = _labelStore() || [], present = new Set([1, SM.cur, ...SM.seeds.map(q => q.obj), ...LB.boxes.map(b => b[5]).filter(v => v != null).map(Number),
        ...S0.filter(r => r.clip === f.stem && r.obj != null).map(r => +r.obj), ...Object.values(SAMMAP[f.clip] || {}).flatMap(v => Object.keys(v || {}).map(Number))]);
      SM.objs = [...present].filter(o => o >= 1).sort((a, b) => a - b);
    }
    SM.objs = SM.objs.filter(o => o === 1 || o === SM.cur || isFire() || SM.seeds.some(q => q.obj === o) || LB.boxes.some(b => +b[5] === o) || Object.values(SAMMAP[f.clip] || {}).some(v => v && v[String(o)]) || (_labelStore() || []).some(r => r.clip === f.stem && +r.obj === o));   // 어디에도 없는 번호만 정리
    if (f.image && !isFire()) { const n = Math.max(1, LB.boxes.length); SM.objs = Array.from({ length: n }, (_, i) => i + 1); if (SM.cur > n) SM.cur = 1; }   // 사람 이미지: 박스마다 객체 하나(화면 번호·색과 일치)
    if (!SM.objs.length) SM.objs = objsFor();
    persistSam(f.clip);
    rowObj.innerHTML = "";
    styleGo();
    if (!SM.seeds.length && !LB.boxes.length && !shotSecs(f.stem).length && !samFramesOf(f.clip).length) return;   // 화면 박스(정답 프리필 포함)·라벨(손·전파)·참조샷이 모두 없으면 객체 줄을 비워 둔다(처음·전부 삭제 뒤). 객체 선택은 숫자키(화재는 1 불 · 2 연기)
    SM.objs.forEach(o => {
      const row = el("div"); row.style.cssText = "display:flex;align-items:center;gap:6px;flex-wrap:wrap";
      const tag = el("button", null, samName(o)); tag.title = PROP_OBJ(o) ? "이 객체를 선택하고 탭·드래그" : "연기: 드래그로 직접 그린다. 전파하지 않는다(마스크가 연기 기둥을 못 따라감)"; tag.style.cssText = `width:auto;height:auto;padding:2px 9px;font-size:11px;border-radius:6px;border:2px solid ${samCol(o)};color:${o === SM.cur ? "#06090f" : samCol(o)};background:${o === SM.cur ? samCol(o) : "transparent"};cursor:pointer`;
      tag.onclick = () => { SM.cur = o; loadSam(); };
      row.appendChild(tag);
      if (f.image) {                                 // 이미지: 이 객체의 박스 수(정답 프리필 포함). 없으면 비워 둔다
        const n = LB.boxes.filter((b, i) => (b[5] != null ? +b[5] : (isFire() ? objOfCls(b[0]) : i + 1)) === o).length;
        if (n) { const c = el("span", null, `${n}박스`); c.style.cssText = "font-size:11px;color:var(--mut)"; row.appendChild(c); }
      }
      if (!f.image) {                                // 이 객체의 라벨 프레임을 칩으로(손라벨·전파 구분 없음). 참조샷 칩만 초록 점 + ×(참조샷 취소). 이미지엔 프레임이 없다
        const S = _labelStore() || [];
        const hand = S.filter(r => r.clip === f.stem && r.cls >= 0 && (r.obj != null ? +r.obj === o : (isFire() && r.cls === samCls(o)))).map(r => quant(r.t));   // 손라벨의 객체 번호(obj) 우선, 없으면 화재는 클래스로
        const sam = Object.entries(SAMMAP[f.clip] || {}).filter(([k, v]) => v && v[String(o)]).map(([k]) => +k);
        const seedAt = t => SM.seeds.find(sd => sd.obj === o && near(sd.t, t));
        const all = [...new Set([...hand, ...sam, ...SM.seeds.filter(sd => sd.obj === o).map(sd => sd.t)])].sort((x, y) => x - y);
        all.forEach(t => {
          const sd = seedAt(t);
          const chip = el("span"); chip.style.cssText = `display:inline-flex;align-items:center;gap:5px;background:var(--panel2);border:1px solid ${sd ? samCol(o) : "var(--line)"};border-radius:14px;padding:1px 6px 1px 8px;font-size:11px;font-weight:700${near(t, f.t) ? ";outline:2px solid var(--blue)" : ""}`;
          chip.innerHTML = (sd ? `<i style="width:7px;height:7px;border-radius:50%;background:#3fb950;display:inline-block" title="참조샷"></i>` : "") + `<b style="color:${samCol(o)};cursor:pointer" title="이 프레임으로 이동">${_disp(t)}</b>`;
          chip.querySelector("b").onclick = () => { SM.cur = o; openFrameAt(f.clip, t, LB.mode); };
          const x = el("span", null, "×"); x.style.cssText = "cursor:pointer;color:var(--mut);font-weight:800";   // 모든 칩에 × : 이 프레임에서 이 객체를 지운다(다른 객체 남으면 프레임 유지, 없으면 프레임 삭제)
          x.title = `${samName(o)} 삭제(이 프레임). 다른 객체가 남으면 프레임 유지, 없으면 프레임 삭제`;
          x.onclick = ev => { ev.stopPropagation(); deleteObjAt(o, t); };
          chip.appendChild(x);
          row.appendChild(chip);
        });
      }
      if (SM.objs.length > 1 && !isFire()) { const del = el("span", null, "객체 삭제"); del.style.cssText = "cursor:pointer;color:var(--mut);font-size:11px"; del.onclick = async () => {
        const mine0 = SM.seeds.filter(q => q.obj === o);
        const nProp = Object.values(SAMMAP[f.clip] || {}).filter(v => v && v[String(o)]).length;
        if (!await uiConfirm(`객체 ${o}를 지웁니다: 참조샷 ${mine0.length}개 · 그 박스 · 전파 결과 ${nProp}프레임.\n박스가 하나도 남지 않는 프레임은 프레임 기록도 지워지고, 다른 객체가 남는 프레임은 유지됩니다. 계속할까요?`, { ok: "삭제", danger: true })) return;
        snap();
        const cur = mine0.find(q => near(q.t, f.t));
        let touched = false;                            // 지금 프레임의 박스가 바뀌었나
        if (cur) { const i = LB.boxes.findIndex((b, k) => seedForBox(k) === cur); if (i >= 0) { LB.boxes.splice(i, 1); SM.seeds.forEach(q => { if (near(q.t, f.t) && q.i != null && q.i > i) q.i -= 1; }); touched = true; } SP = []; SMASK = null; }
        if (LB.src === "sam") { const n0 = LB.boxes.length; LB.boxes = LB.boxes.filter(b => b[5] !== o); touched = touched || LB.boxes.length !== n0; }   // 화면에 보이는 전파 박스도
        SM.objs = SM.objs.filter(q => q !== o); SM.seeds = SM.seeds.filter(q => q.obj !== o); if (SM.cur === o) SM.cur = SM.objs[0];
        for (const q of mine0) {                       // 다른 프레임의 손라벨: 그 박스만 뺀다. 안 남으면 프레임 기록째 지운다
          if (near(q.t, f.t)) continue;
          const hb = existingBoxes(f.stem, q.t); if (!hb || !hb.length) continue;
          const keep = hb.filter(b => iou4(box4(b), q.box) < 0.7);
          if (keep.length === hb.length) continue;
          try { if (keep.length) await postLabel(f.stem, q.t, f.W, f.H, keep, f.src); else await clearLabel(f.stem, q.t); } catch (e) {}
        }
        await postJSON("/api/sam2_drop_obj", { clip: f.clip, obj: o }).catch(() => {});   // 전파 결과(저장소)에서 이 객체를 뺀다
        if (touched) {                                  // 지금 프레임: 남은 박스 저장, 안 남으면 기록째 삭제
          if (LB.boxes.length) { LB.src = "hand"; await saveNow(); }
          else { try { await clearLabel(f.stem, f.t); } catch (e) {} f.saved = null; LB.src = "none"; }
        }
        await refreshSam(); loadSam(); draw();
      }; row.appendChild(del); }
      rowObj.appendChild(row);
    });
  }
  gtLabels(f.clip).then(() => { if (mine()) { updateTStat(); draw(); } });   // 정답이 늦게 오면 점선·마름모를 다시 그린다
  bReset.onclick = async () => {
    const hs = shotSecs(f.stem).length, hset = new Set(shotSecs(f.stem).map(([t]) => t)), sm = samFramesOf(f.clip).filter(t => !hset.has(t)).length;
    if (!await uiConfirm(`이 클립의 학습 프레임을 초기화합니다.\n손라벨 ${hs}프레임 · 영상전파 ${sm}프레임 · 참조샷 ${SM.seeds.length}개가 지워집니다(손라벨은 백업됨). 계속할까요?`, { ok: "초기화", danger: true })) return;
    bReset.disabled = true;
    try {
      const r = await postJSON("/api/clearlabels", { clip: f.clip, kind: LB.mode === "person" ? "person" : "fire" });
      if (!r.ok) throw new Error(r.err || "실패");
      if (LB.mode === "person") { try { PLABELS = await (await fetch("/api/labels?kind=person")).json(); } catch (e) {} }
      else { try { LABELS = await (await fetch("/api/labels")).json(); } catch (e) {} }
      SM.seeds = []; SM.objs = objsFor(); SM.cur = 1; SM.a = null; SM.b = null; SP = []; SMASK = null;
      hist.length = 0; redo.length = 0; _PENDING = null;   // 이력도 비운다(배열을 그대로 두고 비워야 Ctrl+Z 가 옛 배열을 안 본다)
      LB.boxes = []; LB.src = "none"; f.saved = null;
      drawObjs(); await refreshSam(); if (typeof updateRawBadge === "function") updateRawBadge(f.stem);
    } catch (e) { await uiAlert("초기화 실패: " + e.message); }
    bReset.disabled = false;
  };
  const pruneSeeds = () => {                         // 손라벨 박스가 없어진 참조샷 제거(전 프레임). 지금 프레임은 화면 박스 기준, 정답 참조는 유지
    const n0 = SM.seeds.length;
    SM.seeds = SM.seeds.filter(q => { if (q.fromGT) return true; const hb = near(q.t, f.t) ? LB.boxes : existingBoxes(f.stem, q.t); return !!hb && hb.some(b => iou4(box4(b), q.box) > 0.3); });
    if (SM.seeds.length !== n0) persistSam(f.clip);
  };
  const frameDeleted = t => {                        // [규칙 1] 프레임 라벨이 지워짐(어느 경로든): 그 프레임 참조샷 전부 제거, 보는 프레임이면 박스·점·마스크 비움
    SM.seeds = SM.seeds.filter(q => !near(q.t, t));
    if (near(f.t, t)) { LB.boxes = []; f.saved = []; LB.src = "none"; sel = null; }
    loadSam(); fillShots(); draw();
  };
  const loadSam = () => {
    pinObjs(); pruneSeeds(); const sd = SM.seeds.find(q => near(q.t, f.t) && q.obj === SM.cur); SP = sd && sd.pts ? sd.pts.slice() : []; SMASK = sd ? { box: sd.box, poly: sd.poly } : null; drawObjs(); draw(); };
  const deleteObjAt = async (o, t) => {              // 객체 o 를 프레임 t 에서 삭제(규칙 2·3). 참조샷·손라벨·전파 박스 모두
    const isCur = near(f.t, t);
    const objOf = b => (b[5] != null ? b[5] : (isFire() ? objOfCls(b[0]) : null));   // 박스의 객체: 전파 박스는 6번째, 화재 손라벨은 클래스로
    const boxes = (isCur ? LB.boxes : (existingBoxes(f.stem, t) || samBoxesAt(SAMMAP[f.clip] || {}, t) || [])).map(b => b.slice());
    const remain = boxes.filter(b => objOf(b) !== o);
    SM.seeds = SM.seeds.filter(q => !(q.obj === o && near(q.t, t)));   // 이 객체의 참조샷 제거
    snap();
    try {
      if (remain.length) { await postLabel(f.stem, t, f.W, f.H, remain, f.src); }   // 다른 객체 남음 → 손라벨로 유지(SAM 프레임이면 서버가 통째로 뺀다)
      else { await clearLabel(f.stem, t); await dropSam(f.clip, t); }                // 아무 객체도 없음 → 프레임 기록·전파 결과 삭제
    } catch (e) {}
    if (isCur) { LB.boxes = remain; LB.src = remain.length ? "hand" : "none"; f.saved = remain.length ? remain.map(b => b.slice()) : null; SP = []; SMASK = null; if (!remain.length) samForget(f.clip, t); }
    await refreshSam(); loadSam(); fillShots(); draw();
  };

  // ---------- SAM: 전파(서버 큐) → SAM 저장소 자동 저장. 결과가 있는 클립에서 참조샷을 더 찍으면 그 구간만 이어서 전파 ----------
  let _activeJob = null, _cancelling = false;
  const markProp = () => {                            // 목록 표시를 '전파' 로. 라디오·배지·칩 개수까지 같이 맞춘다
    const stem = f.clip.split("/").pop().replace(/\.mp4$/, "");
    if (typeof saveClipState !== "function") return;
    if (((CLIPST[stem] || {}).mark) === "hand") return;   // '완료' 는 사람이 확정한 값이라 전파가 덮지 않는다
    saveClipState(stem, { mark: "prop" });
    if (typeof updateListBadge === "function") updateListBadge(stem);
    if (typeof COND_REDRAW === "function" && COND_REDRAW) COND_REDRAW();
    const rb = document.querySelector(`input[type=radio][name="clipmark_${stem}"][value=prop]`);
    if (rb) rb.checked = true;                        // 오른쪽 영상정보의 라디오도 따라간다
  };
  const hasProp = () => !!(SM.propFrames && SM.propFrames.length);
  const seedHere = () => SM.seeds.some(q => near(q.t, f.t) && PROP_OBJ(q.obj));   // 지금 보고 있는 프레임에 전파 대상 참조샷이 있나(이어서 전파의 시작점)
  const styleGo = () => {
    const on = hasProp(), refine = on && seedHere(), dis = !_activeJob && !SM.seeds.length;
    bGo.style.background = on && !refine && !dis ? "var(--blue)" : "var(--panel)"; bGo.style.color = on && !refine && !dis ? "#06090f" : "var(--blue)";
    if (!_activeJob) { bGo.textContent = refine ? "이어서 전파" : "전파"; bGo.disabled = !SM.seeds.length; }
    bGo.style.opacity = bGo.disabled ? "0.5" : "1"; bGo.style.cursor = bGo.disabled ? "not-allowed" : "pointer";
    bGo.title = bGo.disabled ? "참조샷이 없습니다. 불을 탭하거나 박스를 그려 참조샷을 만든 뒤 전파하세요" : "참조샷으로 전파 → SAM 저장소 자동 저장. 이어서 전파 = 지금 프레임의 참조샷부터 종료 프레임까지 뒤로만(범위 안)";
    bClr.hidden = !on || !!_activeJob;
    const gt = GTMAP[f.clip] || {}, rv = on || shotSecs(f.stem).length > 0 || gtFramesOf(f.clip).length > 0 || Object.keys(gt.points || {}).length > 0;   // 검수 = 손라벨·SAM·정답 중 하나라도 있으면
    bRev.disabled = !rv; bRev.style.opacity = rv ? "1" : "0.4"; bRev.style.cursor = rv ? "pointer" : "default"; bRev.title = rv ? "학습 라벨(손·SAM)과 정답을 격자로 비교·검수" : "검수할 라벨이 없습니다";
  };
  const refreshSam = async () => {                    // 저장소를 다시 읽어 화면·배지·토글 상태를 맞춘다
    samInvalidate(f.clip); const sam = await samLabels(f.clip);
    SAMFR[f.stem] = samFramesOf(f.clip); SM.propFrames = SAMFR[f.stem].map(tkey);
    if (typeof updateRawBadge === "function") updateRawBadge(f.stem);
    if (!mine()) return;                              // 다른 인스턴스가 화면을 맡고 있으면 여기서 끝(저장소·배지는 위에서 이미 갱신)
    styleGo(); fillShots();
    if (LB.src === "sam" || (!hasHand(f.saved) && !LB.boxes.length)) { const bx = samBoxesAt(sam, f.t); LB.boxes = bx; LB.src = bx.length ? "sam" : "none"; }
    draw();
  };
  let _watching = false;
  const watchJob = async () => {                      // 이 클립의 전파 작업을 끝날 때까지 지켜본다(다른 클립에 가 있어도 계속)
    if (_watching) return; _watching = true;
    let seen = null;
    while (true) {
      if (ED && ED._tok !== MY) { _watching = false; return; }   // 편집기가 새로 그려졌으면 이 감시는 끝(새 편집기가 이어받는다)
      const jobs = await fetch(`/api/sam2_jobs?clip=${encodeURIComponent(f.clip)}`).then(r => r.json()).catch(() => []);
      const act = jobs.find(jb => jb.state === "running" || jb.state === "queued");
      if (!act) { _activeJob = null; if (seen) seen = jobs.find(jb => jb.id === seen.id) || seen; break; }
      seen = act; _activeJob = act;
      if (mine()) { rowObj.style.pointerEvents = "none"; rowObj.style.opacity = "0.5"; if (_cancelling) { bGo.disabled = true; bGo.textContent = "취소 중…"; } else { bGo.disabled = false; bGo.textContent = "전파 취소"; } bClr.hidden = true; pstat.innerHTML = act.state === "queued" ? `<span style="color:var(--mut)">대기 ${act.pos}</span>` : spin(act.total ? Math.min(99, Math.round(act.done / act.total * 100)) : 0); }
      await new Promise(r => setTimeout(r, 800));
    }
    _watching = false; _cancelling = false;   // 취소든 완료든 끝났으니 잠금 해제(styleGo 가 '전파'/'이어서 전파'로 되돌린다)
    if (!seen) { if (mine()) { styleGo(); drawObjs(); } return; }   // 작업이 없었다 → 버튼 상태만 원래대로
    if (mine()) {
      rowObj.style.pointerEvents = ""; rowObj.style.opacity = ""; bGo.disabled = false;
      const dr = seen.drops || {}, skipped = (dr.lost || 0) + (dr.empty || 0) + (dr.size || 0);   // 프레임이 빠진 사유: 놓침(가림·이탈) · 크기 제한(참조 대비 3배/1/3 밖)
      const why = skipped ? ` · 빠짐 ${skipped}` + (dr.lost + dr.empty ? ` (놓침 ${(dr.lost || 0) + (dr.empty || 0)}` : " (") + (dr.size ? `${dr.lost + dr.empty ? " · " : ""}크기제한 ${dr.size}` : "") + ")" : "";
      // 알림(warn)은 실패가 아니다. 결과는 저장돼 있고, 사람이 드나들어 많이 놓쳤다는 뜻이다(2026-09-23).
      pstat.innerHTML = seen.err === "cancelled" ? '<span style="color:var(--mut)">취소됨</span>'
        : seen.err ? `<b style="color:#f85149">실패</b> <span style="color:var(--mut)">${seen.err}</span>`
        : seen.warn ? `<b style="color:#d29922">${seen.nframes || 0}프레임 저장</b> <span style="color:var(--mut)">${seen.warn}</span>`
        : `<span style="color:var(--mut)">전파 ${seen.nframes || 0}프레임${why}</span>`;
      setTimeout(() => { if (mine()) pstat.innerHTML = ""; }, seen.err ? 4000 : seen.warn ? 20000 : 12000);
    }
    if (!seen.err) { if (mine()) loadSam(); }   // 참조샷은 그대로 둔다: 지우고 다시, 또는 이어서 전파할 수 있게. 참조 프레임은 손라벨이라 저장소에도 남는다
    await refreshSam();
  };
  bGo.onclick = async () => {
    if (_activeJob) {                                 // 진행·대기 중 → 취소(참조샷은 그대로 남아 취소가 끝나면 다시 전파)
      _cancelling = true; bGo.disabled = true; bGo.textContent = "취소 중…";
      await postJSON("/api/sam2_cancel", { clip: f.clip }).catch(() => {});
      return;
    }
    if (!SM.seeds.length) return;
    const refine = hasProp() && seedHere();          // 이어서 전파: 지금 프레임의 참조샷부터 종료까지(뒤로만). 없으면 전체 구간 다시
    let a, b;
    if (refine) {
      a = Math.max(f.t, SM.a == null ? 0 : SM.a); b = SM.b == null ? f.last : SM.b;   // 시작 = 지금 프레임(범위 시작보다 앞이면 범위 시작), 끝 = 종료 프레임
      if (b <= a) { flash('<b style="color:#f85149">지금 프레임이 종료 프레임 뒤입니다</b> <span style="color:var(--mut)">종료를 늘리거나 앞 프레임으로 가세요</span>', 3500); return; }
    }
    else {
      if (SM.a == null) SM.a = 0; if (SM.b == null) SM.b = f.last;   // 시작/종료가 비어 있으면 클립 처음~끝(프레임바에 값이 남음)
      const ts = SM.seeds.map(q => q.t);
      a = Math.min(SM.a, Math.min.apply(null, ts)); b = Math.max(SM.b, Math.max.apply(null, ts));
    }
    if (!refine && hasProp()) {                       // 결과가 있는데 지금 프레임에 참조샷이 없다 → 전체 범위를 다시 돌게 된다. 실수 방지
      const ok = await uiConfirm(`지금 프레임(${_disp(f.t)})에 참조샷이 없어 '이어서'가 아니라 전체 범위를 다시 전파합니다.
구간 ${_disp(a)}~${_disp(b)} · 참조샷 ${SM.seeds.map(q => _disp(q.t)).join(", ")}
이 프레임부터 이어서 하려면 취소 후 탭·박스·C 로 참조샷을 만드세요. 계속할까요?`, { ok: "전체 다시 전파", danger: true });
      if (!ok) return;
    }
    fillShots();
    bGo.disabled = true; pstat.innerHTML = spin(0);
    flash(`<span style="color:var(--mut)">전파 ${_disp(a)}~${_disp(b)} 시작</span>`, 3000);
    const seeds = SM.seeds.map(q => ({ t: q.t, box: q.box, obj: q.obj, pts: q.pts || [] }));
    const start = await postJSON("/api/sam2_propagate_start", { clip: f.clip, seeds, a, b, step: _step() }).catch(() => ({ err: "요청 실패" }));
    if (start.err) { bGo.disabled = false; flash(`<b style="color:#f85149">${start.err}</b>`, 3000); return; }
    markProp();                                       // 전파를 걸었으니 이 클립 표시를 '전파' 로
    watchJob();                                       // 서버 큐가 처리·저장한다. 다른 클립에 가도 된다
  };
  bClr.onclick = async () => {                       // 이 클립의 SAM 결과를 저장소에서 전부 뺀다
    if (!await uiConfirm(`이 클립의 전파 결과 ${samFramesOf(f.clip).length}프레임을 지웁니다. 손라벨은 그대로 둡니다. 계속할까요?`, { ok: "지우기", danger: true })) return;
    bClr.disabled = true; pstat.innerHTML = spin(0);
    await postJSON("/api/sam2_clear", { clip: f.clip }).catch(() => {});
    bClr.disabled = false; pstat.innerHTML = "";
    await refreshSam();
  };
  bRev.onclick = () => openAutoReview(f);

  // ---------- 키보드 ----------
  const _PEEK = on => { ov.style.opacity = on ? "0.23" : ""; };   // 라벨 흐리게: 그려진 것이 전부 ov 한 장이라 투명도만 낮추면 된다
  document.onkeyup = ev => { if (ev.code === "Space") { _space = false; if (!pan) ov.style.cursor = "crosshair"; } if (ev.key === "r" || ev.key === "R") _PEEK(false); };
  document.onkeydown = ev => {
    if (ev.target && ev.target.tagName === "INPUT" && ev.target.type === "range") { ev.preventDefault(); ev.target.blur(); }   // 슬라이더에 포커스가 남아도 단축키로
    else if (ev.target && /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName)) return;   // 프레임번호 입력 중엔 단축키 끔
    if (ev.code === "Space") { ev.preventDefault(); _space = true; if (!pan) ov.style.cursor = "grab"; return; }   // 스페이스=이동 모드(드래그로 확대이미지 이동)
    if ((ev.ctrlKey || ev.metaKey) && (ev.key === "z" || ev.key === "Z")) { ev.preventDefault(); ev.shiftKey ? restore(redo, hist) : restore(hist, redo); return; }   // Ctrl+Z 되돌리기 · Ctrl+Shift+Z 다시
    if ((ev.ctrlKey || ev.metaKey) && (ev.key === "y" || ev.key === "Y")) { ev.preventDefault(); restore(redo, hist); return; }
    if (ev.key === "c" || ev.key === "C") {                                              // C = 이전 프레임(저장된) 박스 복사. 불·쓰러진 사람은 제자리
      const pt = f.t - _step();
      const prev = existingBoxes(f.stem, pt) || samBoxesAt(SAMMAP[f.clip] || {}, pt);   // 손라벨 없으면 전파 결과에서 복사
      if (prev && prev.length) {
        snap();
        prev.forEach(b => {
          const nb = b.slice(); if (nb[5] == null) { const o = isFire() ? objOfCls(nb[0]) : SM.cur; if (o != null) nb[5] = o; }
          LB.boxes.push(nb); const i = LB.boxes.length - 1, o = nb[5];
          if (o != null && PROP_OBJ(o)) {              // 복사한 박스 = 그 객체의 이 프레임 참조샷(연기는 참조샷 안 만듦)
            SM.seeds = SM.seeds.filter(q => !(near(q.t, f.t) && q.obj === o));
            SM.seeds.push({ t: f.t, obj: o, box: box4(nb), poly: [], pts: [], i });
          }
        });
        SM.seeds.sort((a, b) => a.t - b.t || a.obj - b.obj);
        loadSam(); draw(); saveNow();
      }
      return;
    }
    if (ev.key === "?" || (ev.key === "/" && ev.shiftKey)) { toggleHelp(); return; }

    if (ev.key === "[") { ev.preventDefault(); SM.a = f.t; if (SM.b != null && SM.b < SM.a) SM.b = null; fillShots(); return; }
    if (ev.key === "]") { ev.preventDefault(); SM.b = f.t; if (SM.a != null && SM.a > SM.b) SM.a = null; fillShots(); return; }
    if (/^[0-9]$/.test(ev.key)) {                                 // 숫자 = 객체 선택. 0 은 10번(사람이 10명까지 나온다)
      const n = ev.key === "0" ? 10 : +ev.key;
      if (isFire()) { if (FIRE.objs.includes(n)) { SM.cur = n; loadSam(); } return; }
      if (!SM.objs.includes(n)) { SM.objs.push(n); SM.objs.sort((a, b) => a - b); } SM.cur = n; loadSam(); return;
    }
    if (ev.key === "Delete" || ev.key === "Backspace") {                                 // [규칙 3] 마우스 아래(또는 잡은) 박스 + 그 참조샷. 마지막 박스였으면 저장 시 '검토완료(객체 없음)' 마커. 박스가 없으면 현재 객체의 점·참조샷
      ev.preventDefault();
      const i = (sel !== null && LB.boxes[sel]) ? sel : (lastP ? boxUnder(lastP) : null);
      if (i !== null && i !== undefined && LB.boxes[i]) {
        snap();
        const owner = seedForBox(i);
        LB.boxes.splice(i, 1); sel = null;
        SM.seeds = SM.seeds.filter(q => q !== owner);
        SM.seeds.forEach(q => { if (near(q.t, f.t) && q.i != null && q.i > i) q.i -= 1; });
        if (owner && owner.obj === SM.cur) { SP = []; SMASK = null; }
        drawObjs(); draw(); saveNow(); return;
      }
      SP = []; samRecompute(); return;
    }
    if (f.image) return;                                                                 // 정지 이미지: 프레임 이동 없음
    if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") { ev.preventDefault(); openFrameAt(f.clip, f.t + (ev.key === "ArrowLeft" ? -1 : 1) * (ev.shiftKey ? 10 : _step()), LB.mode); return; }
    if (ev.key === "r" || ev.key === "R") { ev.preventDefault(); _PEEK(true); return; }   // R 을 누르고 있는 동안만 연하게. 떼면 keyup 이 되돌린다
    if (/^[weWE]$/.test(ev.key)) { ev.preventDefault(); openFrameAt(f.clip, f.t + (/^[eE]$/.test(ev.key) ? 1 : -1) * _step(), LB.mode); }   // W=이전 · E=다음 프레임
  };
  bUndo.onclick = () => restore(hist, redo); bRedo.onclick = () => restore(redo, hist);

  // ---------- 편집기 핸들: 같은 클립의 다른 초로 넘어갈 때는 applyFrame 만 부른다(DOM 을 다시 만들지 않는다) ----------
  ED = {
    clip: f.clip, mode: LB.mode, _tok: MY, loadSam, fillShots, frameDeleted, watch: () => watchJob(),
    keydown: document.onkeydown, keyup: document.onkeyup,   // 같은 클립 재진입(ED 재사용) 때 다시 걸기 위해 보관
    setPseudo: (sec, boxes, src) => {                 // 늦게 도착한 의사라벨을 얹는다. 이미 화면에 박스가 있거나 손라벨로 확정된 프레임이면 무시
      if (LB.sec !== sec || LB.boxes.length || hasHand(f.saved) || LB.src === "hand") return;
      LB.boxes = boxes.map(b => b.slice()); LB.src = src || "sam"; draw();   // 저장하지 않는다(사람이 손대야 손라벨)
    },
    syncSam: () => {                                   // 저장소 기준으로 전파 토글·검수 버튼·문구·배지 맞춤
      SAMFR[f.stem] = samFramesOf(f.clip); SM.propFrames = SAMFR[f.stem].map(tkey);
      styleGo(); updateTStat(); if (typeof updateRawBadge === "function") updateRawBadge(f.stem);
    },
    applyFrame: (sec, url, saved) => {
      f.t = sec; f.url = url; f.saved = saved; LB.sec = sec;
      LB.boxes = saved ? saved.map(b => b.slice()) : []; LB.src = hasHand(saved) ? "hand" : "none";
      sel = null; st = null; rz = null; mv = null; sd = null; pan = null; _resized = false;
      const pend = (_PENDING && _PENDING.clip === f.clip && near(_PENDING.t, sec) && Date.now() - _PENDING.ts < 10000) ? _PENDING : null; _PENDING = null;
      img.src = url;                     // 미리 받아둔 그림이라 즉시 바뀐다
      bar.sl.value = _disp(sec); bar.num.value = _disp(sec);
      if (pend) { applyHist(pend); if (!pend.sam) loadSam(); return; }   // 다른 프레임에서 넘어온 되돌리기 적용
      loadSam(); fillShots(); draw();
    },
  };
  fillShots(); loadSam();
  img.onload = () => draw(); if (img.complete) draw();
  bGo.disabled = true;                                // 진행 중 작업 조회가 끝날 때까지 잠깐 잠금(중복 전파 방지)
  setTimeout(() => { try { watchJob(); } catch (e) {} }, 0);   // 이 클립에 진행 중인 전파가 있으면 이어서 보여준다(ED 가 이 편집기로 바뀐 뒤에 시작)
}

// ---------- 라벨 검수 격자: 학습에 들어갈 최종 라벨(손라벨 > SAM) 과 데이터셋 정답을 한 칸에서 비교한다 ----------
// 칸 = 손라벨·SAM·정답 중 하나라도 있는 프레임. 실선 = 우리 최종 라벨(파랑 손라벨 · 주황 SAM), 점선 하늘색 = 정답 박스, 마름모 = 정답 점.
// × = 보이는 출처만 뺀다(손라벨 → 빈 라벨 마커, SAM → 저장소에서 제거). 정답은 읽기만. 확대창에서 고치면 손라벨로 승격된다.
function reviewItems(f) {
  const sam = SAMMAP[f.clip] || {}, gt = GTMAP[f.clip] || {};
  const ts = new Set([...samFramesOf(f.clip), ...shotSecs(f.stem).map(([t]) => t), ...gtFramesOf(f.clip), ...Object.keys(gt.points || {}).map(Number)]);
  return [...ts].sort((a, b) => a - b).map(t => {
    const hand = existingBoxes(f.stem, t);
    const boxes = hasHand(hand) ? hand : samBoxesAt(sam, t);
    const src = hasHand(hand) ? "hand" : (boxes.length ? "sam" : "none");
    return { t, boxes, src, gt: gtBoxesAt(gt, t), gtp: gtPointsAt(gt, t) };
  }).filter(d => d.boxes.length || d.gt.length || d.gtp.length);
}
const gtSvg = (d, W, H) => d.gt.map(b => `<rect x="${b[1] * W}" y="${b[2] * H}" width="${b[3] * W}" height="${b[4] * H}" fill="none" stroke="${SRC_COLOR.gt}" stroke-width="2" stroke-dasharray="8 5"/>`).join("") +
  d.gtp.map(p => { const x = p.x * W, y = p.y * H; return `<polygon points="${x},${y - 9} ${x + 9},${y} ${x},${y + 9} ${x - 9},${y}" fill="${SRC_COLOR.gt}" stroke="#0b0e13" stroke-width="1.5"/>`; }).join("");
const boxCol = (d, b) => d.src === "hand" ? SRC_COLOR.hand : samCol(b[5] || (isFire() ? objOfCls(b[0]) : 1));   // 전파 결과는 객체 번호 색
const capOf = d => `${_disp(d.t)} · <span style="color:${d.src === "hand" ? SRC_COLOR.hand : d.src === "sam" ? SRC_COLOR.sam : "var(--mut)"};font-weight:700">${d.src === "hand" ? "손 " + d.boxes.length : d.src === "sam" ? "SAM " + d.boxes.length : "라벨 없음"}</span>` +
  ((d.gt.length || d.gtp.length) ? ` <span style="color:${SRC_COLOR.gt}">정답 ${d.gt.length ? d.gt.length + "박스" : ""}${d.gt.length && d.gtp.length ? " " : ""}${d.gtp.length ? d.gtp.length + "점" : ""}</span>` : "");
async function openAutoReview(f) {
  await Promise.all([samLabels(f.clip), gtLabels(f.clip)]);
  const items = reviewItems(f);
  if (!items.length) return;
  const tsFirst = items.slice(0, 24).map(d => d.t).join(","), tsRest = items.slice(24).map(d => d.t).join(",");
  try { await fetch("/api/warmframes?w=320&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsFirst); } catch (e) {}   // 처음 보이는 장만 기다린다
  if (tsRest) fetch("/api/warmframes?w=320&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsRest).catch(() => {});   // 나머지는 뒤에서
  fetch("/api/warmframes?w=0&clip=" + encodeURIComponent(f.clip) + "&ts=" + items.map(d => d.t).join(",")).catch(() => {});   // 확대창용 원본 크기도 전부 뒤에서 캐시
  const old = document.getElementById("autoGrid"); if (old) old.remove();
  const wrap = el("div"); wrap.id = "autoGrid";
  wrap.style.cssText = "position:fixed;inset:0;z-index:80;background:#000a;display:flex;align-items:center;justify-content:center";
  const box = el("div");
  box.style.cssText = "background:var(--panel);border:1px solid var(--line);border-radius:12px;width:min(1150px,95vw);max-height:90vh;display:flex;flex-direction:column;box-shadow:0 12px 40px #000c";
  const nHand = items.filter(d => d.src === "hand").length, nSam = items.filter(d => d.src === "sam").length, nGt = items.filter(d => d.gt.length || d.gtp.length).length;
  const head = el("div", null, `<b>라벨 검수</b> <span style="color:var(--mut);font-size:12px;margin-left:8px">손라벨 ${nHand} · SAM ${nSam}${nGt ? ` · 정답 있는 프레임 ${nGt}(점선·마름모)` : ""}</span>`); head.style.cssText = "padding:12px 16px;border-bottom:1px solid var(--line);font-size:14px";
  const grid = el("div"); grid.style.cssText = "padding:14px 16px;overflow:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px";
  const fill = () => {
    grid.innerHTML = "";
    items.forEach(d => {
      const col = d.src === "hand" ? SRC_COLOR.hand : d.src === "sam" ? SRC_COLOR.sam : SRC_COLOR.gt;
      const cell = el("div"); cell.style.cssText = "position:relative";
      const holder = el("div"); holder.style.cssText = `position:relative;border:1px solid ${col}88;border-radius:8px;overflow:hidden;background:#000;cursor:pointer`;
      holder.innerHTML = `<img loading="lazy" src="/frameat?clip=${encodeURIComponent(f.clip)}&t=${d.t}&w=320" style="display:block;width:100%;height:auto">` +
        `<svg viewBox="0 0 ${f.W} ${f.H}" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none">` + gtSvg(d, f.W, f.H) +
        d.boxes.map(b => `<rect x="${b[1] * f.W}" y="${b[2] * f.H}" width="${b[3] * f.W}" height="${b[4] * f.H}" fill="none" stroke="${boxCol(d, b)}" stroke-width="3"/>`).join("") + `</svg>`;
      holder.onclick = () => openShot(f, items, items.indexOf(d));
      holder.oncontextmenu = ev => { ev.preventDefault(); wrap.remove(); openFrameAt(f.clip, d.t, LB.mode); };
      const cap = el("div", null, capOf(d));
      cap.style.cssText = "font-size:11px;color:var(--tx);margin-top:5px";
      if (d.src !== "none") {
        const x = el("button", null, "×"); x.title = d.src === "hand" ? "이 프레임 손라벨 삭제(빈 라벨로 남음)" : "이 프레임의 SAM 결과 제외";
        x.style.cssText = "position:absolute;top:6px;right:6px;width:24px;height:24px;padding:0;border-radius:50%;border:none;background:#000b;color:#fff;font-size:15px;line-height:1;cursor:pointer";
        x.onclick = async ev => { ev.stopPropagation(); x.textContent = "…"; try { if (d.src === "hand") await postLabel(f.stem, d.t, f.W, f.H, [], f.src); else await dropSam(f.clip, d.t); d.boxes = []; d.src = "none"; cell.style.opacity = "0.35"; holder.style.filter = "grayscale(1)"; x.remove(); if (ED && ED.clip === f.clip && ED.frameDeleted) ED.frameDeleted(d.t); else if (ED && ED.fillShots) ED.fillShots(); } catch (e) { x.textContent = "×"; } };
        cell.appendChild(x);
      }
      cell.appendChild(holder); cell.appendChild(cap); grid.appendChild(cell);
    });
  };
  fill(); window.refillGrid = fill;
  const foot = el("div"); foot.style.cssText = "padding:10px 16px;border-top:1px solid var(--line);display:flex;justify-content:flex-end";
  const close = el("button", null, "닫기"); close.style.cssText = "width:auto;background:var(--panel2);color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:5px 14px;cursor:pointer"; close.onclick = () => wrap.remove();
  foot.appendChild(close); box.appendChild(head); box.appendChild(grid); box.appendChild(foot); wrap.appendChild(box);
  wrap.onclick = ev => { if (ev.target === wrap) wrap.remove(); };
  document.body.appendChild(wrap);
}

// 검수 격자에서 한 장을 크게 본다. 변 드래그 = 크기, 안쪽 드래그 = 이동, Del = 박스 삭제, ←/→ 앞뒤 프레임, Esc·클릭 = 닫기, 우클릭 = 편집기로
function openShot(f, items, idx) {
  const old = document.getElementById("shotView"); if (old) old.remove();
  const v = el("div"); v.id = "shotView";
  v.style.cssText = "position:fixed;inset:0;z-index:90;background:#000d;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px";
  const holder = el("div"); holder.style.cssText = "position:relative;max-width:94vw;max-height:80vh;line-height:0";
  const im = el("img"); im.style.cssText = "display:block;max-width:94vw;max-height:80vh;width:auto;height:auto;-webkit-user-drag:none;user-select:none";
  const ovl = el("div"); ovl.style.cssText = "position:absolute;inset:0;cursor:default";
  holder.appendChild(im); holder.appendChild(ovl);
  const cap = el("div"); cap.style.cssText = "color:var(--tx);font-size:12px;font-weight:700";
  const row = el("div"); row.style.cssText = "display:flex;gap:8px;align-items:center";
  const mk = (t, danger) => { const b = el("button", null, t); b.style.cssText = "width:auto;padding:5px 12px;border-radius:6px;font-weight:700;cursor:pointer;background:var(--panel2);color:" + (danger ? "#f85149" : "var(--tx)") + ";border:1px solid " + (danger ? "#f8514966" : "var(--line)"); return b; };
  const bGoto = mk("프레임 보기", false), bDel = mk("프레임 삭제", true), bClose = mk("닫기", false);
  bGoto.title = "이 프레임을 라벨 편집기에서 연다(같은 프레임 번호)";
  bGoto.style.cssText += ";color:var(--blue);border-color:var(--blue)";
  const hint = el("span", null, "박스 변 드래그 = 크기 · 안쪽 드래그 = 이동 · Del = 박스 삭제 · ←/→ 이동 · 우클릭 = 편집기로"); hint.style.cssText = "color:var(--mut);font-size:11px;margin-left:8px";
  row.appendChild(bGoto); row.appendChild(bDel); row.appendChild(bClose); row.appendChild(hint);
  let boxes = [], busy = false, lastP = null;
  const cur = () => items[idx];
  const norm = ev => { const rc = im.getBoundingClientRect(); return { x: (ev.clientX - rc.left) / rc.width, y: (ev.clientY - rc.top) / rc.height, tx: 8 / rc.width, ty: 8 / rc.height }; };
  const render = () => {                               // 실선 = 우리 라벨(손 파랑 · SAM 주황/객체색) · 점선 하늘색 = 정답 박스 · 마름모 = 정답 점
    const d = cur();
    ovl.innerHTML = "<svg viewBox=\"0 0 " + f.W + " " + f.H + "\" preserveAspectRatio=\"none\" style=\"position:absolute;inset:0;width:100%;height:100%\">" + gtSvg({ gt: d.gt || [], gtp: d.gtp || [] }, f.W, f.H) +
      boxes.map(b => "<rect x=\"" + (b[1] * f.W) + "\" y=\"" + (b[2] * f.H) + "\" width=\"" + (b[3] * f.W) + "\" height=\"" + (b[4] * f.H) + "\" fill=\"none\" stroke=\"" + boxCol(d, b) + "\" stroke-width=\"2\"/>").join("") + "</svg>";
    cap.innerHTML = capOf(Object.assign({}, d, { boxes }));
  };
  const srcOf = t => "/frameat?clip=" + encodeURIComponent(f.clip) + "&t=" + t;
  const _pre = {};                                     // 미리 받아둔 이미지
  const preload = t => { const u = srcOf(t); if (_pre[u]) return _pre[u]; const g = new Image(); g.src = u; _pre[u] = g; return g; };
  let showSeq = 0;
  const show = i => {
    idx = Math.min(Math.max(i, 0), items.length - 1);
    const d = cur(); const my = ++showSeq;
    const g = preload(d.t);
    const apply = () => { if (my !== showSeq) return; im.src = g.src; boxes = (d.boxes || []).map(b => b.slice()); render(); };
    if (g.complete && g.naturalWidth) apply(); else { g.onload = apply; g.onerror = apply; }   // 이미지가 준비된 뒤 박스와 함께 바꾼다
    [1, 2, -1, -2].forEach(k => { const q = items[idx + k]; if (q) preload(q.t); });        // 앞뒤 프레임 미리 받기
  };
  const syncEditor = (t, bx) => { if (ED && ED.clip === f.clip && !bx.length && ED.frameDeleted) { ED.frameDeleted(t); return; } if (ED && ED.clip === f.clip) { if (near(LB.sec, t)) { LB.boxes = bx.map(b => b.slice()); LB.src = bx.length ? "hand" : "none"; } ED.syncSam(); ED.fillShots(); ED.loadSam(); } };
  const save = async () => {                           // 고친 프레임 = 손라벨로 승격(전 박스 저장). SAM 저장소에서는 서버가 뺀다
    const d = cur(); if (busy) return; busy = true; cap.textContent = "저장 중…";
    try {
      await postLabel(f.stem, d.t, f.W, f.H, boxes, f.src);
      samForget(f.clip, d.t);
      d.src = "hand"; d.boxes = boxes.map(b => b.slice());
      if (typeof refillGrid === "function") refillGrid();
      syncEditor(d.t, boxes);
    } catch (e) {}
    busy = false; render();
  };
  const dropFrame = async () => {
    const d = cur(); if (busy) return;
    if (!await uiConfirm(`${_disp(d.t)} 프레임의 ${d.src === "hand" ? "손라벨을 지웁니다(빈 라벨로 남음)" : "SAM 결과를 뺍니다"}. 계속할까요?`, { ok: "삭제", danger: true })) return;
    busy = true; cap.textContent = "제거 중…";
    try {
      if (d.src === "hand") await postLabel(f.stem, d.t, f.W, f.H, [], f.src); else await dropSam(f.clip, d.t);
      items.splice(idx, 1);
      if (typeof refillGrid === "function") refillGrid();
      syncEditor(d.t, []);
      busy = false;
      if (!items.length) { done(); return; }
      show(Math.min(idx, items.length - 1));
    } catch (e) { busy = false; cap.textContent = "제거 실패"; }
  };
  bDel.onclick = dropFrame;
  const hit = p => {                                   // 변/모서리 잡기
    for (let i = boxes.length - 1; i >= 0; i--) {
      const b = boxes[i], L = b[1], T = b[2], R = b[1] + b[3], B = b[2] + b[4];
      const nx = Math.abs(p.x - L) < p.tx, px_ = Math.abs(p.x - R) < p.tx, ny = Math.abs(p.y - T) < p.ty, py_ = Math.abs(p.y - B) < p.ty;
      const inX = p.x > L - p.tx && p.x < R + p.tx, inY = p.y > T - p.ty && p.y < B + p.ty;
      if ((nx || px_) && inY) return { i, l: nx, r: px_, t: ny && inX, b: py_ && inX };
      if ((ny || py_) && inX) return { i, l: false, r: false, t: ny, b: py_ };
    }
    return null;
  };
  const under = p => { for (let i = boxes.length - 1; i >= 0; i--) { const b = boxes[i]; if (p.x >= b[1] && p.x <= b[1] + b[3] && p.y >= b[2] && p.y <= b[2] + b[4]) return i; } return null; };
  let drag = null;
  ovl.onmousemove = ev => {
    const p = norm(ev); lastP = p;
    if (drag) {
      const b = boxes[drag.i];
      if (drag.type === "mv") { b[1] = Math.min(Math.max(p.x - drag.dx, 0), 1 - b[3]); b[2] = Math.min(Math.max(p.y - drag.dy, 0), 1 - b[4]); }
      else {
        let L = b[1], T = b[2], R = b[1] + b[3], B = b[2] + b[4];
        if (drag.l) L = Math.min(Math.max(p.x, 0), R - 0.005); if (drag.r) R = Math.max(Math.min(p.x, 1), L + 0.005);
        if (drag.t) T = Math.min(Math.max(p.y, 0), B - 0.005); if (drag.b) B = Math.max(Math.min(p.y, 1), T + 0.005);
        b[1] = L; b[2] = T; b[3] = R - L; b[4] = B - T;
      }
      render(); return;
    }
    const h = hit(p);
    ovl.style.cursor = h ? ((h.l || h.r) && (h.t || h.b) ? "nwse-resize" : (h.l || h.r) ? "ew-resize" : "ns-resize") : (under(p) !== null ? "move" : "default");
  };
  ovl.onmousedown = ev => {
    if (ev.button !== 0 || busy) return;
    ev.preventDefault();
    const p = norm(ev); const h = hit(p);
    if (h) { drag = Object.assign({ type: "rz" }, h); return; }
    const u = under(p); if (u !== null) { const b = boxes[u]; drag = { type: "mv", i: u, dx: p.x - b[1], dy: p.y - b[2] }; }
  };
  const finish = () => { if (!drag) return; drag = null; boxes.forEach(b => { b[1] = +b[1].toFixed(5); b[2] = +b[2].toFixed(5); b[3] = +b[3].toFixed(5); b[4] = +b[4].toFixed(5); }); save(); };
  ovl.onmouseup = finish; ovl.onmouseleave = finish;
  show(idx);
  v.appendChild(holder); v.appendChild(cap); v.appendChild(row);
  const _k0 = document.onkeydown;
  const done = () => { v.remove(); document.onkeydown = _k0; };
  bClose.onclick = done;
  v.onclick = ev => { if (ev.target === v) done(); };
  const goEdit = () => { const t = cur().t; done(); const g = document.getElementById("autoGrid"); if (g) g.remove(); openFrameAt(f.clip, t, LB.mode); };   // 확대창·격자 닫고 편집기를 이 프레임(t)으로
  bGoto.onclick = goEdit;
  v.oncontextmenu = ev => { ev.preventDefault(); goEdit(); };
  document.onkeydown = ev => {
    if (document.getElementById("uiDlg")) return;    // 대화상자가 떠 있으면 그쪽이 처리
    if (ev.key === "Escape") { ev.preventDefault(); done(); return; }
    if (ev.key === "ArrowLeft") { ev.preventDefault(); show(idx - 1); return; }
    if (ev.key === "ArrowRight") { ev.preventDefault(); show(idx + 1); return; }
    if (ev.key === "Delete" || ev.key === "Backspace") {   // 마우스 아래 박스 삭제(없으면 무시)
      ev.preventDefault(); if (!lastP || busy) return;
      const u = under(lastP); if (u === null) return;
      boxes.splice(u, 1); render(); save();
    }
  };
  document.body.appendChild(v);
}

// 재생바: 전파 구간 입력 + 1칸·10칸 이동 + 슬라이더 + 프레임 직접 입력 + 저장 상태
function buildFrameBar(f, status) {
  const bar = el("div", "ctrl labbar");
  autoStop();                           // 다른 클립으로 넘어왔으면 돌던 자동 넘기기를 멈춘다
  bar.style.cssText = "margin-top:8px;border:1px solid var(--line);border-radius:8px";
  const btn = (txt, d, title) => {
    const b = el("button", null, txt);
    b.title = title; b.style.width = "auto"; b.style.padding = "0 9px";
    b.onclick = () => openFrameAt(f.clip, f.t + d * _step());   // 칸 단위(person 0.5초=1프레임, 화재 1초). 10▶▶ = 10칸
    return b;
  };
  {                                                   // 전파 구간 입력칸(비우면 자동 = 클립 처음~끝)
    const SMb = samState(f.clip);
    const mkIn = (label, key) => {
      const lab = el("button", null, label); lab.title = `지금 프레임을 ${label} 프레임으로`;   // 글자를 누르면 지금 프레임이 시작/종료가 된다
      lab.style.cssText = "width:auto;height:auto;padding:2px 6px;margin-left:2px;font-size:11px;font-weight:700;color:var(--mut);background:transparent;border:1px solid var(--line);border-radius:6px;cursor:pointer";
      lab.onclick = () => { SMb[key] = f.t; if (SMb.a != null && SMb.b != null && SMb.a > SMb.b) { const t = SMb.a; SMb.a = SMb.b; SMb.b = t; } if (ED && ED.fillShots) ED.fillShots(); };
      const inp = el("input"); inp.type = "text"; inp.inputMode = "numeric"; inp.placeholder = "자동";
      inp.style.cssText = "width:48px;align-self:stretch;box-sizing:border-box;background:var(--panel);color:var(--tx);border:1px solid var(--line);border-radius:6px;text-align:center;font:700 12px ui-monospace,Menlo,monospace;padding:0 4px";
      inp.value = SMb[key] == null ? "" : _disp(SMb[key]);
      inp.onchange = () => { const v = inp.value.trim(); SMb[key] = v === "" ? null : _undisp(+v); if (SMb.a != null && SMb.b != null && SMb.a > SMb.b) { const t = SMb.a; SMb.a = SMb.b; SMb.b = t; } inp.blur(); if (ED && ED.fillShots) ED.fillShots(); };
      inp.onkeydown = ev => { if (ev.key === "Enter") { ev.preventDefault(); inp.onchange(); } ev.stopPropagation(); };
      bar.appendChild(lab); bar.appendChild(inp); return inp;
    };
    bar.rangeIn = { a: mkIn("시작", "a"), b: mkIn("종료", "b") };
    const bAuto = el("button", null, "재생");     // 종료 칸 오른쪽: 자동 넘기기 / 도는 동안은 중단
    bAuto.style.cssText = "width:auto;height:auto;padding:3px 8px;margin:0 6px 0 4px;font-size:12px;font-weight:800;" +
      "border-radius:6px;cursor:pointer;background:var(--panel);color:var(--tx);border:1px solid var(--line)";
    const paintAuto = () => {
      const on = !!_AUTO;
      bAuto.textContent = on ? "중단" : "재생";
      bAuto.title = on ? "중단" : "자동 넘기기 (1초에 두 프레임)";
      bAuto.style.color = on ? "#f85149" : "var(--tx)";
      bAuto.style.borderColor = on ? "#f8514966" : "var(--line)";
    };
    bAuto.onclick = () => {
      if (_AUTO) { autoStop(); paintAuto(); return; }
      const tick = async () => {
        const t0 = Date.now();
        const nt = f.t + _step();
        if (nt > f.last) { autoStop(); paintAuto(); return; }   // 끝에 닿으면 스스로 멈춘다
        await openFrameAt(f.clip, nt, LB.mode);
        if (!_AUTO) { paintAuto(); return; }                     // 그 사이 사용자가 멈췄다
        _AUTO = setTimeout(tick, Math.max(0, AUTO_MS - (Date.now() - t0)));   // 한 장을 다 불러온 뒤에 다음을 예약(요청이 쌓이지 않게)
      };
      _AUTO = setTimeout(tick, 0);
      paintAuto();
    };
    bar.appendChild(bAuto);
    bar.paintAuto = paintAuto;
  }
  bar.appendChild(btn("◀◀10", -10, "10칸 뒤로"));
  bar.appendChild(btn("◀", -1, "1칸 뒤로"));
  const num = el("input");
  num.type = "text"; num.inputMode = "numeric"; num.value = _disp(f.t);   // type=number 는 브라우저가 위아래 화살표를 붙인다 → text + 숫자 키패드
  num.style.cssText = "width:56px;align-self:stretch;box-sizing:border-box;background:var(--panel);color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:15px;font-weight:400;line-height:1;font-variant-numeric:tabular-nums;text-align:center";
  num.onchange = () => { num.blur(); openFrameAt(f.clip, _undisp(+num.value)); };   // 사람은 정수 프레임번호 입력 → 초로 환산. 포커스를 풀어 숫자키가 객체 전환으로 가게
  const slWrap = el("div", "frbar");
  const tk = el("div", "tk");          // 정답 구간·라벨 눈금이 그려지는 슬라이더 트랙
  const sl = el("input");
  sl.type = "range"; sl.min = 0; sl.max = _disp(f.last); sl.step = 1; sl.value = _disp(f.t);
  sl.oninput = () => { num.value = sl.value; };          // 끄는 동안은 숫자만 따라간다
  sl.addEventListener("pointerup", () => setTimeout(() => sl.blur(), 0));   // 놓으면 포커스 해제(숫자키가 객체 전환으로 가게)
  sl.onchange = () => { sl.blur(); openFrameAt(f.clip, _undisp(+sl.value)); };    // 놓을 때 그 프레임을 뽑는다
  const fire = (CLIPINFO[f.clip] && CLIPINFO[f.clip].fire) || [];
  sl.title = fire.length ? `정답 화재 발생 ${fire.map(x => x.start + "s").join(", ")} · 경보 인정 ${fire[0].dur}초` : "정답 시각 없는 클립";
  slWrap.appendChild(tk); slWrap.appendChild(sl);
  bar.appendChild(slWrap);
  bar.appendChild(num);
  bar.appendChild(el("span", "now", `/ ${_disp(f.last)}`));
  bar.appendChild(btn("▶", 1, "1칸 앞으로"));
  bar.appendChild(btn("10▶▶", 10, "10칸 앞으로"));
  bar.appendChild(status);
  bar.sl = sl; bar.num = num; bar.tk = tk;   // 프레임만 바꿀 때 값·그림을 고쳐 쓰려고 들고 있는다
  return bar;
}

// 그 초의 박스를 서버에 쓴다. boxes 가 빈 배열이면 그 프레임은 '검토완료(빈 라벨)' 로 남는다. 서버가 같은 프레임의 SAM 결과를 뺀다.
async function postLabel(clip, t, W, H, boxes, src, clear) {
  const kind = LB.img ? "image" : ((LB.mode === "person") ? "person" : "fire");
  const _rel = LB.img || src || "", _parts = _rel.split("/");
  const _cat = _parts[0] === "data" ? (_parts[2] || "") : (_parts[0] || "");   // 이미지 rel = data/원본데이터/<카테고리>/… · 영상 src = <카테고리>/…/x.mp4
  const evalCat = (typeof isScoringCat === "function") && isScoringCat(_cat);   // 채점 전용 카테고리 → eval 표시(학습셋 빌더가 뺀다)
  const res = await postJSON("/api/savelabel", { clip, t, src, file: LB.img || `${clip}_${String(t).padStart(4, "0")}.png`, W, H, boxes: boxes.map(b => b.slice(0, 6)), kind, clear: !!clear, eval: !!evalCat });   // 6번째 = 객체 번호(전파 박스를 손으로 고쳐도 객체 유지)
  if (!res.ok) throw new Error(res.err || "저장 실패");
  if (kind === "image") IMGLABELS = res.labels || IMGLABELS; else if (kind === "person") PLABELS = res.labels || PLABELS; else LABELS = res.labels || LABELS;
  if (typeof updateRawBadge === "function") updateRawBadge(LB.img ? ("img:" + LB.img) : clip);   // 저장·삭제 어느 길로 와도 목록 숫자가 따라온다
  return res;
}

// ---------- 정지 이미지 한 장 편집: 같은 편집기를 프레임바·전파·미리보기 없이 연다 ----------
// rel = vms 기준 상대경로(data/원본데이터/.../x.jpg). 서버에는 'img:<rel>' 을 클립 이름으로 넘긴다.
async function openImageEdit(rel) {
  const key = "img:" + rel;
  LB.img = rel; LB.mode = catMode(rel); LB.clip = key; LB.sec = 0; ED = null;
  const url = "/dsimg/" + rel.split("/").map(encodeURIComponent).join("/");
  const im = await new Promise(res => { const g = new Image(); g.onload = () => res(g); g.onerror = () => res(null); g.src = url; });
  if (!im) { $("#center").innerHTML = '<div class="empty">이미지를 못 읽었습니다</div>'; return; }
  // 데이터셋 정답(YOLO txt)이 있으면 점선으로 보이게 GTMAP 에 넣는다(0.0초 한 프레임). 클래스는 imgcls 에 따로
  try {
    const txt = await (await fetch("/api/rawlabel?rel=" + encodeURIComponent(rel))).text();
    const bx = txt.trim().split("\n").filter(Boolean).map(l => l.split(/\s+/).map(Number)).filter(b => b.length >= 5);
    const fr = {}; bx.forEach((b, i) => { fr[String(i + 1)] = [b[1] - b[3] / 2, b[2] - b[4] / 2, b[3], b[4]]; });
    GTMAP[key] = { frames: bx.length ? { "0.0": fr } : {}, points: {}, imgcls: bx.map(b => b[0]) };
    GTL[key] = Promise.resolve(GTMAP[key]);
  } catch (e) { GTMAP[key] = { frames: {}, points: {} }; GTL[key] = Promise.resolve(GTMAP[key]); }
  SAML[key] = Promise.resolve(SAMMAP[key] = {});   // 이미지엔 전파 저장소가 없다
  saveSession({ img: rel, rel: null });
  const g = GTMAP[key], fr = (g.frames || {})["0.0"] || {}, cls = g.imgcls || [];
  const prefill = Object.keys(fr).map((k, i) => [isFire() ? (cls[i] === 1 ? 1 : 0) : 0, ...fr[k]]);   // 정답 클래스: 0 불 · 1 연기(화재) / 사람은 전부 0
  if (typeof imageRightPanel === "function") imageRightPanel(rel, true, prefill.length);
  renderEditor({ clip: key, stem: key, src: rel, t: 0, last: 0, W: im.naturalWidth, H: im.naturalHeight, url, saved: existingBoxes(key, 0), image: true, prefill });
}
// 그 프레임의 손라벨 기록을 마커 없이 지운다(되돌리기로 초안 상태로 돌아갈 때). 없던 것처럼 된다.
const clearLabel = (clip, t) => postLabel(clip, t, 0, 0, [], null, true);

// 타임라인: 초록 선/띠 = 정답 화재 발생·경보 인정 구간 · 주황 띠 = 전파 구간 · 주황 눈금 = SAM 결과 · 흰 눈금 = 손라벨 · 파랑 눈금 = 검토완료 · 노랑 선 = 지금 프레임
function drawTrack(track, f) {
  if (!track) return;
  const total = Math.max(f.last, 1), W = 1000, H = 20, px = t => t / total * W;
  const fire = (CLIPINFO[f.clip] && CLIPINFO[f.clip].fire) || [];
  let g = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%">`;
  fire.forEach(fs => {
    const x0 = px(Math.max(0, fs.start)), x1 = px(Math.min(total, fs.start + (fs.dur || 0)));
    g += `<rect x="${x0}" y="0" width="${Math.max(x1 - x0, 1)}" height="${H}" fill="#3fb95033"/>`;
    g += `<line x1="${px(fs.start)}" y1="0" x2="${px(fs.start)}" y2="${H}" stroke="#3fb950" stroke-width="2"/>`;
  });
  const SMt = samState(f.clip);
  if (SMt.a != null || SMt.b != null) {                         // 전파 구간 띠(주황)
    const a = SMt.a == null ? 0 : SMt.a, b = SMt.b == null ? total : SMt.b;
    g += `<rect x="${px(a)}" y="0" width="${Math.max(px(b) - px(a), 1)}" height="${H}" fill="#e8913a33"/>`;
    if (SMt.a != null) g += `<line x1="${px(SMt.a)}" y1="0" x2="${px(SMt.a)}" y2="${H}" stroke="#e8913a" stroke-width="2"/>`;
    if (SMt.b != null) g += `<line x1="${px(SMt.b)}" y1="0" x2="${px(SMt.b)}" y2="${H}" stroke="#e8913a" stroke-width="2"/>`;
  }
  const tkr = track.parentElement && track.parentElement.parentElement;   // 시작/종료 입력칸 동기화
  if (tkr && tkr.rangeIn) { ["a", "b"].forEach(k => { const inp = tkr.rangeIn[k]; if (document.activeElement !== inp) inp.value = SMt[k] == null ? "" : _disp(SMt[k]); }); }
  samFramesOf(f.clip).forEach(sec => { g += `<line x1="${px(sec)}" y1="${H - 12}" x2="${px(sec)}" y2="${H - 7}" stroke="#e8913a" stroke-width="1.4"/>`; });
  const kinds = shotKinds(f.stem);
  Object.keys(kinds).forEach(k => {
    const sec = +k, col = kinds[k] === "box" ? "#e6edf3cc" : "#58a6ff";
    g += `<line x1="${px(sec)}" y1="${H - 7}" x2="${px(sec)}" y2="${H}" stroke="${col}" stroke-width="1.4"/>`;
  });
  g += `<line x1="${px(f.t)}" y1="0" x2="${px(f.t)}" y2="${H}" stroke="#d29922" stroke-width="1.6"/>`;
  track.innerHTML = g + "</svg>";
}

// 미리보기 한 줄 = 학습 프레임(손라벨 ∪ SAM). 눌러서 그 프레임으로 넘어간다. × = 그 프레임의 라벨 삭제(보이는 출처만)
function renderShotRow(row, f, hooks) {
  if (f.image) { row.innerHTML = ""; row.style.display = "none"; return; }   // 정지 이미지: 프레임이 하나뿐이라 미리보기 줄이 없다(cssText 로 다시 켜지지 않게 여기서 막는다)
  const handS = shotSecs(f.stem), handSet = new Set(handS.map(([s]) => s));
  const smap = SAMMAP[f.clip] || {};
  const shots = [...handS.map(([s, n]) => [s, n, "hand"]), ...samFramesOf(f.clip).filter(s => !handSet.has(s)).map(s => [s, Object.keys(smap[tkey(s)] || {}).length, "sam"])].sort((a, b) => a[0] - b[0]);
  const key = f.clip + "|" + shots.map(([s, n, src]) => `${s}:${n}:${src}`).join(",");
  const center = () => { const nr = [...row.querySelectorAll("[data-t]")].sort((a, b) => Math.abs(+a.dataset.t - f.t) - Math.abs(+b.dataset.t - f.t))[0]; if (nr) requestAnimationFrame(() => { row.scrollLeft = nr.offsetLeft - row.offsetLeft - row.clientWidth / 2 + nr.offsetWidth / 2; }); };
  if (row.dataset.key === key && row.children.length) {   // 구성(프레임 목록·출처)이 그대로면 썸네일을 다시 만들지 않고 강조·스크롤만 갱신
    [...row.querySelectorAll("[data-t]")].forEach(b => { const on = +b.dataset.t === f.t; b.style.outline = on ? "2px solid var(--blue)" : ""; b.style.border = on ? "0" : (b.dataset.src === "sam" ? "1px solid #e8913a88" : "1px solid var(--line)"); });
    center(); return;
  }
  row.dataset.key = key;
  row.innerHTML = "";
  row.style.cssText = "display:flex;gap:8px;overflow-x:auto;padding:12px 2px;align-items:center;min-height:114px";   // 빈 상태도 높이 예약(박스 그릴 때 안 튀게)
  row.onwheel = ev => { if (ev.deltaY) { ev.preventDefault(); row.scrollLeft += ev.deltaY; } };   // 휠 상하 → 프레임줄 좌우 스크롤
  if (!shots.length) return;
  shots.forEach(([s, n, src]) => {
    const on = s === f.t;
    const b = el("button");
    b.title = _disp(s);
    b.style.cssText = "position:relative;flex:0 0 auto;padding:0;line-height:0;border-radius:6px;overflow:hidden;cursor:pointer;background:var(--panel);" +
      (on ? "outline:2px solid var(--blue);border:0" : `border:1px solid ${src === "sam" ? "#e8913a88" : "var(--line)"}`);
    const im = el("img");
    im.src = `/frameat?clip=${encodeURIComponent(f.clip)}&t=${s}&w=180`;   // 작게 줄여 받는다
    im.loading = "lazy";
    im.style.cssText = "width:160px;height:90px;object-fit:cover;display:block";
    const cap = el("span", null, _disp(s));
    cap.style.cssText = "position:absolute;left:0;bottom:0;background:#0b0e13cc;color:var(--tx);font-size:10px;font-weight:700;padding:1px 5px;border-top-right-radius:5px;line-height:1.4";
    b.appendChild(im); b.appendChild(cap);
    b.onclick = () => openFrameAt(f.clip, s);
    const x = el("span", null, "×");
    x.title = src === "hand" ? "이 프레임 손라벨 삭제" : "이 프레임 SAM 결과 삭제";
    x.style.cssText = "position:absolute;right:0;top:0;background:#0b0e13cc;color:var(--tx);font-size:12px;font-weight:800;line-height:1;padding:2px 5px;border-bottom-left-radius:5px;cursor:pointer";
    x.onclick = async ev => {
      ev.stopPropagation();                       // 썸네일 클릭(이동)과 겹치지 않게
      x.textContent = "…";
      try {
        if (src === "sam") { await dropSam(f.clip, s); if (hooks && hooks.onDeleted) hooks.onDeleted(s, null); }
        else {
          const prev = existingBoxes(f.stem, s);  // 지우기 전 박스 → 되돌리기에 쓴다
          await postLabel(f.stem, s, f.W, f.H, [], f.src);
          if (hooks && hooks.onDeleted) hooks.onDeleted(s, prev);
        }
      } catch (e) { x.textContent = "실패"; }
    };
    b.appendChild(x);
    b.dataset.t = s; b.dataset.src = src;
    row.appendChild(b);
  });
  const jump = dir => {                                  // << >> : 미리보기 줄의 첫 프레임 · 마지막 프레임으로 이동(썸네일을 누른 것과 같다)
    const nb = el("button", null, dir < 0 ? "\u00ab" : "\u00bb");
    nb.title = dir < 0 ? "첫 프레임" : "마지막 프레임";
    nb.style.cssText = "position:sticky;" + (dir < 0 ? "left:0;margin-right:-34px" : "right:0;margin-left:-34px") +   // 음수 여백(칸 26 + 사이 8) 으로 줄에서 자리를 안 차지한다 → 썸네일 위에 겹쳐 뜬다
      ";z-index:2;flex:0 0 auto;width:26px;padding:5px 0;line-height:1;text-align:center;cursor:pointer;" +
      "border:1px solid var(--line);border-radius:6px;background:#0b0e1399;color:var(--tx);font-size:17px;font-weight:800";   // 줄이 align-items:center 라 화살표 크기만 두면 세로 가운데에 놓인다
    nb.onclick = () => openFrameAt(f.clip, shots[dir < 0 ? 0 : shots.length - 1][0]);
    return nb;
  };
  row.insertBefore(jump(-1), row.firstChild);            // 줄이 좌우로 스크롤돼도 sticky 라 양 끝에 붙어 있는다
  row.appendChild(jump(1));
  center();
}

// 단축키 도움말 (? 로 토글)
function toggleHelp() {
  let h = document.getElementById("kbdHelp");
  if (h) { h.remove(); return; }
  h = document.createElement("div"); h.id = "kbdHelp";
  h.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:50;background:var(--panel);color:var(--tx);border:1px solid var(--line);border-radius:10px;padding:12px 16px;font-size:12px;line-height:1.9;box-shadow:0 8px 24px #0008;min-width:260px";
  h.innerHTML = '<div style="font-weight:800;margin-bottom:4px">단축키 <span style="color:var(--mut);font-weight:400">(? 닫기)</span></div>' +
    [["클릭", "SAM 점(현재 객체) · 박스 안이면 그 박스로 프롬프트"], ["우클릭", "제외점"], ["드래그", "현재 객체 박스(빈 곳=새로, 박스 안=이동, 변=크기)"],
     ["1 ~ 9, 0", "객체 선택 (0 = 객체 10 · 화재: 1 불 · 2 연기)"], ["Del", "마우스 아래 박스 삭제(+그 참조샷). 마지막 박스면 '검토완료·객체 없음'으로 남음"], ["C", "이전 프레임 박스 복사"],
     ["Ctrl+Z / Ctrl+Shift+Z", "되돌리기 / 다시"], ["W / E, ← / →", "이전 / 다음 프레임"], ["R (누르고 있기)", "라벨을 아주 연하게 — 원본 확인"], ["Shift+← / →", "10칸"], ["[ / ]", "전파 시작 / 종료 프레임"],
     ["휠", "확대·축소"], ["Space+드래그", "확대 화면 이동"],
     ["미리보기 ×", "프레임 라벨 삭제 = 박스 전부 + 그 프레임 참조샷 전부(검토완료로 남음)"], ["객체 삭제", "참조샷·박스·전파 결과 전부. 박스가 안 남는 프레임은 기록째 삭제, 다른 객체 남으면 유지"], ["객체 칩 ×", "이 프레임에서 그 객체 삭제. 다른 객체 남으면 프레임 유지, 없으면 프레임 삭제"]]
      .map(([k, v]) => `<div><kbd style="background:var(--panel2);border:1px solid var(--line);border-radius:4px;padding:0 6px;font-family:ui-monospace,Menlo,monospace">${k}</kbd> <span style="color:var(--mut)">${v}</span></div>`).join("");
  document.body.appendChild(h);
}
