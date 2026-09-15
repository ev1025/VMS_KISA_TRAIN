# -*- coding: utf-8 -*-
"""기존 편집기(editor.js)에 SAM 모드를 넣는다. iframe 탭 제거. 모든 편집 모드 공통.
 - [SAM][DINO] 토글: 같은 화면·같은 도구. DINO = 박스 직접 편집(기존). SAM = 탭 → 마스크·참조샷 → 전파.
 - 노출·수정 우선순위: 손라벨 → SAM → DINO (색: 파랑/주황/초록). 어느 저장소도 지우지 않는다.
 - 참조샷(탭한 프레임) → 손라벨 저장 · 전파 결과 → 자동라벨/sam2 자동 저장.
 - 재생바(기존): 왼쪽에 시작/종료, 눈금에 SAM 프레임(주황)·전파 구간 띠. 파란 긴 줄 없음.
 - 아래: ↶ ↷ [전파] 라벨검수 · 객체 줄(SAM) · 참조 샷 줄(손라벨 파랑 + SAM 주황)."""
import io

p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "function samState(" not in s, "이미 적용됨"

def rep(old, new, must=True):
    global s
    if old not in s:
        if must: raise AssertionError("앵커를 못 찾음:\n" + old[:160])
        return
    s = s.replace(old, new, 1)

# ---------------------------------------------------------------- A. 탭 → 모드 토글(iframe 제거)
i = s.find("// 라벨편집 탭: 디노박스 = 이 편집기(DINO 프리필 + 손라벨) · 삼박스 = SAM2 페이지를 같은 클립으로 임베드")
j = s.find("function renderEditor(f) {")
assert 0 < i < j
s = s[:i] + r'''// 편집 모드 [SAM][DINO]: 같은 화면·같은 도구. SAM = 탭→마스크·참조샷→전파, DINO = 박스 직접 편집.
let LAB = "sam"; try { LAB = localStorage.getItem("kisa_lab_tab") === "dino" ? "dino" : "sam"; } catch (e) {}
const SAMST = {};                    // clip → SAM 작업 상태(참조샷·객체·전파 결과·구간). 클립 단위로 유지
function samState(clip) { return SAMST[clip] || (SAMST[clip] = { seeds: [], objs: [1], cur: 1, result: {}, a: null, b: null }); }
const SAM_COLORS = ["#e8913a", "#58a6ff", "#d2a8ff", "#3fb950", "#f778ba", "#79c0ff", "#ffa657", "#56d364"];
const samCol = o => SAM_COLORS[(o - 1) % SAM_COLORS.length];
const SRC_COLOR = { hand: "#58a6ff", sam: "#e8913a", dino: "#3fb950", none: "#3fb950" };
const SAMMAP = {}, DINOMAP = {};      // clip → 프레임맵(동기 조회용 캐시; 눈금·참조샷 줄에서 쓴다)
function samFramesOf(clip) { const m = SAMMAP[clip] || {}; return Object.keys(m).filter(k => Object.keys(m[k] || {}).length).map(Number).sort((a, b) => a - b); }
function labTabs(f, cur) {
  const bar = el("div"); bar.style.cssText = `display:flex;gap:4px;padding:8px 8px 0;max-width:min(${f.W}px, calc((100vh - 400px) * 16 / 9));margin:0 auto;width:100%`;
  [["sam", "SAM"], ["dino", "DINO"]].forEach(([k, label]) => {
    const b = el("button", null, label);
    b.style.cssText = "width:auto;padding:5px 14px;font-size:12px;font-weight:800;border-radius:6px;cursor:pointer;" +
      (k === cur ? "background:var(--blue);color:#06090f;border:1px solid var(--blue)" : "background:var(--panel);color:var(--mut);border:1px solid var(--line)");
    b.onclick = () => { if (k === cur) return; LAB = k; try { localStorage.setItem("kisa_lab_tab", k); } catch (e) {} ED = null; openFrameAt(f.clip, f.t, LB.mode); };
    bar.appendChild(b);
  });
  return bar;
}

''' + s[j:]

rep('''  let _lastTab = "sam"; try { _lastTab = localStorage.getItem("kisa_lab_tab") || "sam"; } catch (e) {}   // 기본 = SAM
  if (_lastTab === "sam" && LB.mode === "person") { showSamTab(f); return; }   // 마지막에 SAM 으로 작업했으면 SAM 으로 이어간다
  const c = $("#center"); c.innerHTML = "";''',
'''  const c = $("#center"); c.innerHTML = "";''')
rep('''  top.appendChild(labTabs(f, "dino"));               // [SAM] [DINO]''',
'''  top.appendChild(labTabs(f, LAB));                  // [SAM] [DINO]
  const SM = samState(f.clip);                        // SAM 작업 상태
  let SP = [], SMASK = null;                          // 현재 프레임·현재 객체의 점, 마스크
  if (!LB.src) LB.src = f.saved ? "hand" : "none";''')

# ---------------------------------------------------------------- B. 재생바 뒤 조작 줄 + 객체 줄
rep('''  const bar = buildFrameBar(f, status);
  pane.appendChild(bar);
  const shots = el("div");
  pane.appendChild(shots);''',
'''  const bar = buildFrameBar(f, status);
  pane.appendChild(bar);
  // ↶ ↷ [전파] 라벨검수  (전파는 SAM 모드에서만)
  const rowAct = el("div"); rowAct.style.cssText = "display:flex;align-items:center;gap:8px;margin-top:10px;flex-wrap:wrap";
  const mkBtn = (txt, title) => { const b = el("button", null, txt); b.title = title; b.style.cssText = "width:auto;padding:0 9px;height:28px;background:var(--panel);color:var(--tx);border:1px solid var(--line);border-radius:6px;font-weight:700;cursor:pointer"; return b; };
  const bUndo = mkBtn("↶", "되돌리기 (Ctrl+Z)"), bRedo = mkBtn("↷", "다시하기 (Ctrl+Shift+Z)"), bRev = mkBtn("라벨 검수", "이 클립의 라벨(손·SAM·DINO)을 격자로 검수");
  const bGo = mkBtn("전파", "참조샷으로 전파 → SAM 저장소 자동 저장"); bGo.style.cssText += ";background:var(--blue);color:#06090f;border-color:var(--blue);font-weight:800;padding:0 12px";
  const pstat = el("span", "now", ""); pstat.style.whiteSpace = "nowrap";
  rowAct.appendChild(bUndo); rowAct.appendChild(bRedo); if (LAB === "sam") rowAct.appendChild(bGo); rowAct.appendChild(bRev); rowAct.appendChild(pstat);
  pane.appendChild(rowAct);
  const rowObj = el("div"); rowObj.style.cssText = "display:flex;flex-direction:column;gap:6px;margin-top:8px"; if (LAB !== "sam") rowObj.style.display = "none";
  pane.appendChild(rowObj);
  const shots = el("div");
  pane.appendChild(shots);
  bRev.onclick = () => openAutoReview(f, null);''')

# ---------------------------------------------------------------- C. 그리기: 출처 색 + SAM 오버레이
rep('''  const draw = (drag, dcls) => {
    let s = `<svg viewBox="0 0 ${f.W} ${f.H}" style="position:absolute;inset:0;width:100%;height:100%">`;
    LB.boxes.forEach((b, i) => { s += rectSvg(b[1] * f.W, b[2] * f.H, b[3] * f.W, b[4] * f.H, b[0], false, false); });
    if (drag) s += rectSvg(drag.x, drag.y, drag.w, drag.h, dcls, true);
    ov.innerHTML = s + "</svg>";''',
'''  const draw = (drag, dcls) => {
    let s = `<svg viewBox="0 0 ${f.W} ${f.H}" style="position:absolute;inset:0;width:100%;height:100%">`;
    const col = (LB.mode === "person") ? SRC_COLOR[LB.src || "none"] : null;   // 사람: 손라벨 파랑 · SAM 주황 · DINO 초록
    LB.boxes.forEach((b, i) => { s += rectSvg(b[1] * f.W, b[2] * f.H, b[3] * f.W, b[4] * f.H, b[0], LB.src === "dino" && LAB === "dino", false, col); });
    if (LAB === "sam") {
      const dm = DINOMAP[f.clip] || {};
      autoBoxesAt(dm, f.t).forEach(b => { s += rectSvg(b[1] * f.W, b[2] * f.H, b[3] * f.W, b[4] * f.H, 0, true, false, "#3fb950"); });   // DINO 후보(점선)
      SM.seeds.filter(sd => sd.t === f.t && !(sd.obj === SM.cur && SMASK)).forEach(sd => {
        const cc = samCol(sd.obj);
        if (sd.poly && sd.poly.length) s += `<polygon points="${sd.poly.map(p => `${p[0] * f.W},${p[1] * f.H}`).join(" ")}" fill="${cc}44" stroke="${cc}" stroke-width="2"/>`;
        s += `<text x="${sd.box[0] * f.W + 4}" y="${sd.box[1] * f.H + 16}" fill="${cc}" font-size="16" font-weight="800">${sd.obj}</text>`;
        (sd.pts || []).forEach(p => { s += `<circle cx="${p[0] * f.W}" cy="${p[1] * f.H}" r="4" fill="${p[2] ? "#58a6ff" : "#f85149"}" stroke="${cc}" stroke-width="1.5"/>`; });
      });
      if (SMASK) {
        const cc = samCol(SM.cur);
        if (SMASK.poly && SMASK.poly.length) s += `<polygon points="${SMASK.poly.map(p => `${p[0] * f.W},${p[1] * f.H}`).join(" ")}" fill="${cc}55" stroke="${cc}" stroke-width="2"/>`;
        if (SMASK.box) s += `<text x="${SMASK.box[0] * f.W + 4}" y="${SMASK.box[1] * f.H + 16}" fill="${cc}" font-size="16" font-weight="800">${SM.cur}</text>`;
      }
      SP.forEach(p => { s += `<circle cx="${p[0] * f.W}" cy="${p[1] * f.H}" r="4" fill="${p[2] ? "#58a6ff" : "#f85149"}" stroke="#fff" stroke-width="1.5"/>`; });
    }
    if (drag) s += rectSvg(drag.x, drag.y, drag.w, drag.h, dcls, true);
    ov.innerHTML = s + "</svg>";''')
rep('''function rectSvg(x, y, w, h, cls, dash, on) {
  const stroke = (LB.mode === "person") ? "#3fb950" : (cls ? "#a371f7" : "#f85149");''',
'''function rectSvg(x, y, w, h, cls, dash, on, color) {
  const stroke = color || ((LB.mode === "person") ? "#3fb950" : (cls ? "#a371f7" : "#f85149"));''')

# 저장하면 손라벨 출처
rep('''      const res = await postLabel(f.stem, f.t, f.W, f.H, LB.boxes, f.src);
      f.saved = LB.boxes.map(b => b.slice());''',
'''      const res = await postLabel(f.stem, f.t, f.W, f.H, LB.boxes, f.src);
      f.saved = LB.boxes.map(b => b.slice()); LB.src = "hand";''')

# ---------------------------------------------------------------- D. 마우스: SAM 모드 분기
rep('''  ov.oncontextmenu = ev => ev.preventDefault();   // 우클릭 메뉴 차단(연기 그리기용)
  ov.onmousedown = ev => {
    ev.preventDefault();
    if (_space) { pan = { sx: ev.clientX, sy: ev.clientY, tx0: _tx, ty0: _ty }; ov.style.cursor = "grabbing"; return; }   // 스페이스+드래그 = 확대이미지 이동
    const p = toImg(ev);
    const h = ev.button === 2 || ev.shiftKey ? null : hitTest(p);   // 우클릭·Shift 는 언제나 새 박스
    if (h) { snap(); rz = h; sel = h.i; return; }''',
'''  ov.oncontextmenu = ev => { ev.preventDefault(); if (LAB === "sam" && !_space && !rz && !mv) { const p = toImg(ev); samPoint(p.x / f.W, p.y / f.H, 0); } };   // SAM: 우클릭 = 제외점
  let _resized = false;
  ov.onmousedown = ev => {
    ev.preventDefault();
    if (_space) { pan = { sx: ev.clientX, sy: ev.clientY, tx0: _tx, ty0: _ty }; ov.style.cursor = "grabbing"; return; }   // 스페이스+드래그 = 확대이미지 이동
    const p = toImg(ev);
    const h = ev.button === 2 || ev.shiftKey ? null : hitTest(p);   // 우클릭·Shift 는 언제나 새 박스
    if (h) { snap(); rz = h; sel = h.i; return; }
    if (LAB === "sam") return;                        // SAM: 그리기/이동 없음. 클릭은 onclick 에서 점으로''')
rep('''  const finish = ev => {
    if (pan) { pan = null; ov.style.cursor = _space ? "grab" : "crosshair"; return; }   // 이동 끝
    if (rz) { rz = null; draw(); saveNow(); return; }      // 크기조절 끝 → 그 자리에서 저장''',
'''  const finish = ev => {
    if (pan) { pan = null; ov.style.cursor = _space ? "grab" : "crosshair"; return; }   // 이동 끝
    if (rz) { const i = rz.i; rz = null; _resized = true; draw(); saveNow(); if (LAB === "sam") seedFromBox(i); return; }      // 크기조절 끝 → 저장(SAM: 참조샷도 갱신)''')
rep('''    if (!st) return; const p = toImg(ev);
    const x = Math.min(st.x, p.x), y = Math.min(st.y, p.y), w = Math.abs(p.x - st.x), h = Math.abs(p.y - st.y); st = null;
    if (w > 4 && h > 4) { snap(); LB.boxes.push([curCls, x / f.W, y / f.H, w / f.W, h / f.H]); draw(); saveNow(); }
    else { draw(); saveNow(); }   // 박스 안 쳐도 프레임 안쪽 클릭이면 현재 상태 저장(빈 라벨=검토완료)
  };
  ov.onmouseup = finish;''',
'''    if (!st) return; const p = toImg(ev);
    const x = Math.min(st.x, p.x), y = Math.min(st.y, p.y), w = Math.abs(p.x - st.x), h = Math.abs(p.y - st.y); st = null;
    if (w > 4 && h > 4) { snap(); LB.boxes.push([curCls, x / f.W, y / f.H, w / f.W, h / f.H]); draw(); saveNow(); }
    else { draw(); saveNow(); }   // 박스 안 쳐도 프레임 안쪽 클릭이면 현재 상태 저장(빈 라벨=검토완료)
  };
  ov.onclick = ev => {                                 // SAM: 좌클릭 = 후보/박스 탭 또는 포함점
    if (LAB !== "sam") return;
    if (_resized) { _resized = false; return; }
    if (_space || pan || rz || mv) return;
    const p = toImg(ev); const x = p.x / f.W, y = p.y / f.H;
    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    samPoint(x, y, 1);
  };
  // ---------- SAM: 탭 → 마스크 → 참조샷(손라벨 저장) ----------
  const seedSet = (box, poly, pts, idx) => {
    SM.seeds = SM.seeds.filter(q => !(Math.abs(q.t - f.t) < 0.01 && q.obj === SM.cur));
    SM.seeds.push({ t: f.t, obj: SM.cur, box, poly: poly || [], pts: (pts || []).slice(), i: idx }); SM.seeds.sort((a, b) => a.t - b.t || a.obj - b.obj);
    drawObjs();
  };
  const seedFromBox = i => { const b = LB.boxes[i]; if (!b) return; SMASK = { box: [b[1], b[2], b[3], b[4]], poly: [] }; seedSet(SMASK.box, [], SP, i); draw(); };
  async function samPoint(x, y, label) {
    const t = f.t;
    const rc = img.getBoundingClientRect(); const tolX = 10 / rc.width, tolY = 10 / rc.height;
    const near = SP.findIndex(q => Math.abs(q[0] - x) < tolX && Math.abs(q[1] - y) < tolY);
    snap();
    if (near >= 0) { SP.splice(near, 1); return samRecompute(); }
    // 후보(DINO)·화면 박스(손/SAM/DINO) 안을 점 없이 좌클릭 → 그 박스로 프롬프트
    const dm = DINOMAP[f.clip] || {};
    const pool = [...LB.boxes.map((b, i) => ({ b, i })), ...autoBoxesAt(dm, t).map(b => ({ b, i: -1 }))];
    const hit = (label === 1 && !SP.length) ? pool.find(o => x >= o.b[1] && x <= o.b[1] + o.b[3] && y >= o.b[2] && y <= o.b[2] + o.b[4]) : null;
    let body;
    if (hit) body = { clip: f.clip, t, pts: [], box: [hit.b[1], hit.b[2], hit.b[3], hit.b[4]] };
    else { SP.push([+x.toFixed(5), +y.toFixed(5), label]); draw(); body = { clip: f.clip, t, pts: SP }; }
    const r = await fetch("/api/sam2_mask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(r => r.json()).catch(() => ({}));
    if (f.t !== t) return;
    if (!r.box) { SMASK = null; draw(); return; }
    SMASK = { box: r.box, poly: r.poly };
    const nb = [0, r.box[0], r.box[1], r.box[2], r.box[3]];
    const sd0 = SM.seeds.find(q => Math.abs(q.t - t) < 0.01 && q.obj === SM.cur);
    let idx = (hit && hit.i >= 0) ? hit.i : (sd0 && sd0.i != null && LB.boxes[sd0.i] ? sd0.i : -1);
    if (idx >= 0) LB.boxes[idx] = nb; else { LB.boxes.push(nb); idx = LB.boxes.length - 1; }
    seedSet(r.box, r.poly, SP, idx);
    draw(); saveNow();                                 // 탭한 프레임 → 손라벨
  }
  async function samRecompute() {
    const t = f.t; const sd0 = SM.seeds.find(q => Math.abs(q.t - t) < 0.01 && q.obj === SM.cur);
    if (!SP.length) {                                  // 점을 다 지움 → 이 객체의 참조샷·박스 제거
      if (sd0 && sd0.i != null && LB.boxes[sd0.i]) LB.boxes.splice(sd0.i, 1);
      SM.seeds = SM.seeds.filter(q => q !== sd0); SMASK = null; drawObjs(); draw(); saveNow(); return;
    }
    draw();
    const r = await fetch("/api/sam2_mask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, t, pts: SP }) }).then(r => r.json()).catch(() => ({}));
    if (f.t !== t) return;
    if (!r.box) { SMASK = null; draw(); return; }
    SMASK = { box: r.box, poly: r.poly };
    const nb = [0, r.box[0], r.box[1], r.box[2], r.box[3]];
    let idx = (sd0 && sd0.i != null && LB.boxes[sd0.i]) ? sd0.i : -1;
    if (idx >= 0) LB.boxes[idx] = nb; else { LB.boxes.push(nb); idx = LB.boxes.length - 1; }
    seedSet(r.box, r.poly, SP, idx); draw(); saveNow();
  }
  // ---------- SAM: 객체 줄 ----------
  function drawObjs() {
    rowObj.innerHTML = "";
    if (LAB !== "sam") return;
    SM.objs.forEach(o => {
      const row = el("div"); row.style.cssText = "display:flex;align-items:center;gap:6px;flex-wrap:wrap";
      const tag = el("button", null, `객체 ${o}`); tag.style.cssText = `width:auto;height:auto;padding:2px 9px;font-size:11px;border-radius:6px;border:2px solid ${samCol(o)};color:${o === SM.cur ? "#06090f" : samCol(o)};background:${o === SM.cur ? samCol(o) : "transparent"};cursor:pointer`;
      tag.onclick = () => { SM.cur = o; loadSam(); };
      row.appendChild(tag);
      SM.seeds.filter(sd => sd.obj === o).forEach(sd => {
        const chip = el("span"); chip.style.cssText = `display:inline-flex;align-items:center;gap:6px;background:var(--panel2);border:1px solid ${samCol(o)};border-radius:14px;padding:2px 6px 2px 10px;font-size:11px;font-weight:700`;
        chip.innerHTML = `<b style="color:${samCol(o)}">${_disp(sd.t)}</b>`;
        const go = el("span", null, "↗"); go.style.cssText = "cursor:pointer;color:var(--mut)"; go.onclick = () => { SM.cur = o; openFrameAt(f.clip, sd.t, LB.mode); };
        const x = el("span", null, "×"); x.style.cssText = "cursor:pointer;color:var(--mut)"; x.title = "참조샷 취소(박스는 손라벨에 그대로)";
        x.onclick = () => { SM.seeds = SM.seeds.filter(q => q !== sd); if (sd.t === f.t && sd.obj === SM.cur) { SP = []; SMASK = null; } drawObjs(); draw(); };
        chip.appendChild(go); chip.appendChild(x); row.appendChild(chip);
      });
      if (SM.objs.length > 1) { const del = el("span", null, "객체 삭제"); del.style.cssText = "cursor:pointer;color:var(--mut);font-size:11px"; del.onclick = () => { SM.objs = SM.objs.filter(q => q !== o); SM.seeds = SM.seeds.filter(q => q.obj !== o); if (SM.cur === o) SM.cur = SM.objs[0]; loadSam(); }; row.appendChild(del); }
      rowObj.appendChild(row);
    });
    bGo.disabled = !SM.seeds.length;
  }
  const loadSam = () => { const sd = SM.seeds.find(q => q.t === f.t && q.obj === SM.cur); SP = sd && sd.pts ? sd.pts.slice() : []; SMASK = sd ? { box: sd.box, poly: sd.poly } : null; drawObjs(); draw(); };
  // ---------- SAM: 전파(비동기 진행률) → SAM 저장소 자동 저장 ----------
  const spin = pct => `<span style="display:inline-block;width:12px;height:12px;border:2px solid #58a6ff55;border-top-color:#58a6ff;border-radius:50%;animation:ed_sp .8s linear infinite;vertical-align:-2px;margin-right:6px"></span>${pct}%`;
  if (!document.getElementById("ed_sp")) { const stl = document.createElement("style"); stl.id = "ed_sp"; stl.textContent = "@keyframes ed_sp{to{transform:rotate(360deg)}}"; document.head.appendChild(stl); }
  bGo.onclick = async () => {
    if (!SM.seeds.length) return;
    bGo.disabled = true; pstat.innerHTML = spin(0);
    const ts = SM.seeds.map(q => q.t), lo = Math.min.apply(null, ts), hi = Math.max.apply(null, ts);
    const a = SM.a == null ? lo - 5 : Math.min(SM.a, lo), b = SM.b == null ? hi + 10 : Math.max(SM.b, hi);
    const start = await fetch("/api/sam2_propagate_start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, seeds: SM.seeds.map(q => ({ t: q.t, box: q.box, obj: q.obj })), back: Math.max(0, lo - Math.max(0, a)), fwd: Math.max(0, Math.min(f.last, b) - hi), step: _step() }) }).then(r => r.json()).catch(() => ({ err: "x" }));
    if (start.err) { bGo.disabled = false; pstat.innerHTML = '<b style="color:#f85149">실패</b>'; return; }
    let stt = {};
    while (true) { await new Promise(r => setTimeout(r, 500)); stt = await fetch(`/api/sam2_progress?id=${start.id}`).then(r => r.json()).catch(() => ({})); if (stt.total) pstat.innerHTML = spin(Math.min(99, Math.round(stt.done / stt.total * 100))); if (stt.running === false) break; }
    bGo.disabled = false; pstat.innerHTML = "";
    if (stt.err || !stt.result) { pstat.innerHTML = '<b style="color:#f85149">실패</b>'; return; }
    const frames = {}; Object.keys(stt.result).forEach(k => { const v = stt.result[k]; frames[Number(k).toFixed(1)] = Array.isArray(v) ? { "1": v } : v; });
    SM.result = frames;
    await fetch("/api/sam2_save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, frames, seeds: SM.seeds.map(q => ({ t: q.t, obj: q.obj, box: q.box })) }) }).catch(() => {});
    SAMMAP[f.clip] = Object.assign(SAMMAP[f.clip] || {}, frames); SAML[f.clip] = Promise.resolve(SAMMAP[f.clip]);
    fetch(`/api/warmframes?w=180&clip=${encodeURIComponent(f.clip)}&ts=${Object.keys(frames).join(",")}`).catch(() => {});
    fillShots();
    if (!f.saved && !LB.boxes.length) { const bx = samBoxesAt(SAMMAP[f.clip], f.t); if (bx.length) { LB.boxes = bx; LB.src = "sam"; } }   // 지금 프레임에 결과가 있으면 띄운다
    draw();
  };
  ov.onmouseup = finish;''')

# 마우스 이동 중 커서: SAM 모드에서 박스 안은 move 커서 대신 기본
rep('''    const u = h ? h.i : boxUnder(p);
    if (!h && u !== null) ov.style.cursor = "move";''',
'''    const u = h ? h.i : boxUnder(p);
    if (!h && u !== null && LAB !== "sam") ov.style.cursor = "move";''')

# ---------------------------------------------------------------- E. ED.setPseudo 출처 · applyFrame 초기화
rep('''    setPseudo: (sec, boxes) => {
      if (LB.sec !== sec || LB.boxes.length || f.saved) return;
      LB.boxes = boxes.map(b => b.slice()); draw();          // 저장하지 않는다(사람이 손대야 손라벨)
    },''',
'''    setPseudo: (sec, boxes, src) => {
      if (LB.sec !== sec || LB.boxes.length || f.saved) return;
      LB.boxes = boxes.map(b => b.slice()); LB.src = src || "dino"; draw();   // 저장하지 않는다(사람이 손대야 손라벨)
    },
    loadSam,''')
rep('''      LB.boxes = saved ? saved.map(b => b.slice()) : [];
      sel = null; st = null; rz = null; mv = null; hist.length = 0; redo.length = 0;
      img.src = url;                     // 미리 받아둔 그림이라 즉시 바뀐다
      bar.sl.value = _disp(sec); bar.num.value = _disp(sec);
      fillShots(); draw();''',
'''      LB.boxes = saved ? saved.map(b => b.slice()) : []; LB.src = saved ? "hand" : "none";
      sel = null; st = null; rz = null; mv = null; hist.length = 0; redo.length = 0;
      img.src = url;                     // 미리 받아둔 그림이라 즉시 바뀐다
      bar.sl.value = _disp(sec); bar.num.value = _disp(sec);
      loadSam(); fillShots(); draw();''')

# openFrameAt 프리필: 출처 전달 + 동기 캐시 채움
rep('''    Promise.all([samLabels(clip), autoLabels(clip)]).then(([sam, dino]) => {   // 손라벨 → SAM → DINO
      if (!ED || ED.clip !== clip) return;
      let bx = samBoxesAt(sam, sec);
      if (!bx.length) bx = autoBoxesAt(dino, sec);
      if (bx.length) ED.setPseudo(sec, bx);
    });''',
'''    Promise.all([samLabels(clip), autoLabels(clip)]).then(([sam, dino]) => {   // 손라벨 → SAM → DINO
      SAMMAP[clip] = sam; DINOMAP[clip] = dino;
      if (!ED || ED.clip !== clip) return;
      let bx = samBoxesAt(sam, sec), src = "sam";
      if (!bx.length) { bx = autoBoxesAt(dino, sec); src = "dino"; }
      if (bx.length) ED.setPseudo(sec, bx, src);
      if (ED.fillShots) ED.fillShots(); if (ED.loadSam) ED.loadSam();
    });''')
rep('''  const afterShow = () => {
    if (!wantPseudo) return;                                  // 손라벨이 있으면 무조건 손라벨(이미 화면에 있음)''',
'''  const afterShow = () => {
    if (!wantPseudo) { Promise.all([samLabels(clip), autoLabels(clip)]).then(([sam, dino]) => { SAMMAP[clip] = sam; DINOMAP[clip] = dino; if (ED && ED.clip === clip) { if (ED.fillShots) ED.fillShots(); if (ED.loadSam) ED.loadSam(); } }); return; }   // 손라벨이 있으면 무조건 손라벨(이미 화면에 있음)''')

# ---------------------------------------------------------------- F. 단축키: SAM 추가
rep('''    if (ev.key === "?" || (ev.key === "/" && ev.shiftKey)) { toggleHelp(); return; }
    if (ev.key === "Delete" || ev.key === "Backspace") {
      ev.preventDefault();
      if (sel !== null && LB.boxes[sel]) { snap(); LB.boxes.splice(sel, 1); sel = null; draw(); saveNow(); }
      return;
    }''',
'''    if (ev.key === "?" || (ev.key === "/" && ev.shiftKey)) { toggleHelp(); return; }
    if (ev.key === "0") { _zoom = 1; _tx = 0; _ty = 0; _applyZoom(); return; }
    if (ev.key === "[") { ev.preventDefault(); SM.a = f.t; if (SM.b != null && SM.b < SM.a) SM.b = null; fillShots(); return; }
    if (ev.key === "]") { ev.preventDefault(); SM.b = f.t; if (SM.a != null && SM.a > SM.b) SM.a = null; fillShots(); return; }
    if (LAB === "sam" && /^[1-8]$/.test(ev.key)) { const n = +ev.key; if (!SM.objs.includes(n)) { SM.objs.push(n); SM.objs.sort((a, b) => a - b); } SM.cur = n; loadSam(); return; }
    if (ev.key === "Delete" || ev.key === "Backspace") {
      ev.preventDefault();
      if (LAB === "sam") { SP = []; samRecompute(); return; }    // SAM: 현재 객체의 이 프레임 점·참조샷·박스 제거
      if (sel !== null && LB.boxes[sel]) { snap(); LB.boxes.splice(sel, 1); sel = null; draw(); saveNow(); }
      return;
    }''')
rep('''  ED.fillShots = fillShots;                                    // 격자 검수창에서 참조 샷 줄 갱신용''',
'''  ED.fillShots = fillShots;                                    // 격자 검수창에서 참조 샷 줄 갱신용
  bUndo.onclick = () => restore(hist, redo); bRedo.onclick = () => restore(redo, hist);
  loadSam();''')

# ---------------------------------------------------------------- G. 재생바: 검수 버튼 제거, 시작/종료 추가
rep('''  if (LB.mode === "person") {
    const rev = el("button", null, "검수");
    rev.title = "이 클립의 자동라벨(DINO)을 격자로 펼쳐 확인·제외한다. 손라벨은 바뀌지 않는다";
    rev.style.cssText = "width:auto;padding:0 9px;white-space:nowrap;flex:0 0 auto";
    rev.onclick = () => openAutoReview(f, null);
    bar.appendChild(rev);
  }
  bar.appendChild(status);''',
'''  bar.appendChild(status);''')
rep('''  bar.appendChild(btn("◀◀10", -10, "10초 뒤로"));
  bar.appendChild(btn("◀", -1, "1초 뒤로"));''',
'''  const SMb = samState(f.clip);                           // 전파 구간 시작/종료(재생바 왼쪽)
  const rangeA = el("span", "now", SMb.a == null ? "—" : _disp(SMb.a)), rangeB = el("span", "now", SMb.b == null ? "—" : _disp(SMb.b));
  rangeA.style.minWidth = rangeB.style.minWidth = "30px"; rangeB.style.marginRight = "6px";
  const bA = el("button", null, "시작"); bA.title = "현재 프레임을 전파 시작으로 ([)"; bA.style.cssText = "width:auto;padding:0 9px";
  const bB = el("button", null, "종료"); bB.title = "현재 프레임을 전파 끝으로 (])"; bB.style.cssText = "width:auto;padding:0 9px";
  bA.onclick = () => { SMb.a = f.t; if (SMb.b != null && SMb.b < SMb.a) SMb.b = null; if (ED && ED.fillShots) ED.fillShots(); };
  bB.onclick = () => { SMb.b = f.t; if (SMb.a != null && SMb.a > SMb.b) SMb.a = null; if (ED && ED.fillShots) ED.fillShots(); };
  bar.appendChild(bA); bar.appendChild(rangeA); bar.appendChild(bB); bar.appendChild(rangeB);
  bar.rangeA = rangeA; bar.rangeB = rangeB;
  bar.appendChild(btn("◀◀10", -10, "10초 뒤로"));
  bar.appendChild(btn("◀", -1, "1초 뒤로"));''')

# ---------------------------------------------------------------- H. 눈금: 전파 구간 띠 + SAM 프레임 주황
rep('''  const kinds = shotKinds(f.stem);   // 흰=손라벨 박스 · 파랑=검토완료(빈) · 노랑=지금 보는 프레임''',
'''  const SMt = samState(f.clip);
  if (SMt.a != null || SMt.b != null) {                         // 전파 구간 띠(주황)
    const a = SMt.a == null ? 0 : SMt.a, b = SMt.b == null ? total : SMt.b;
    g += `<rect x="${px(a)}" y="0" width="${Math.max(px(b) - px(a), 1)}" height="${H}" fill="#e8913a33"/>`;
    if (SMt.a != null) g += `<line x1="${px(SMt.a)}" y1="0" x2="${px(SMt.a)}" y2="${H}" stroke="#e8913a" stroke-width="2"/>`;
    if (SMt.b != null) g += `<line x1="${px(SMt.b)}" y1="0" x2="${px(SMt.b)}" y2="${H}" stroke="#e8913a" stroke-width="2"/>`;
  }
  const tkr = track.parentElement && track.parentElement.parentElement;   // 시작/종료 표시 갱신
  if (tkr && tkr.rangeA) { tkr.rangeA.textContent = SMt.a == null ? "—" : _disp(SMt.a); tkr.rangeB.textContent = SMt.b == null ? "—" : _disp(SMt.b); }
  samFramesOf(f.clip).forEach(sec => { g += `<line x1="${px(sec)}" y1="${H - 12}" x2="${px(sec)}" y2="${H - 7}" stroke="#e8913a" stroke-width="1.4"/>`; });   // 주황 = SAM 전파 결과
  const kinds = shotKinds(f.stem);   // 흰=손라벨 박스 · 파랑=검토완료(빈) · 노랑=지금 보는 프레임''')

# ---------------------------------------------------------------- I. 참조 샷 줄: SAM 프레임(주황) 포함
rep('''  const shots = shotSecs(f.stem);
  if (!shots.length) return;
  shots.forEach(([s, n]) => {
    const on = s === f.t;
    const b = el("button");
    b.title = `${s}초 · 박스 ${n}개`;   // 사람 모드는 화면 표기가 프레임번호(초×2)
    b.style.cssText = "position:relative;flex:0 0 auto;padding:0;line-height:0;border-radius:6px;overflow:hidden;cursor:pointer;background:var(--panel);" +
      (on ? "outline:2px solid var(--blue);border:0" : "border:1px solid var(--line)");''',
'''  const handS = shotSecs(f.stem);
  const handSet = new Set(handS.map(([s]) => s));
  const smap = SAMMAP[f.clip] || {};
  const shots = [...handS.map(([s, n]) => [s, n, "hand"]), ...samFramesOf(f.clip).filter(s => !handSet.has(s)).map(s => [s, Object.keys(smap[s.toFixed(1)] || {}).length, "sam"])].sort((a, b) => a[0] - b[0]);
  if (!shots.length) return;
  shots.forEach(([s, n, src]) => {
    const on = s === f.t;
    const b = el("button");
    b.title = `${s}초 · 박스 ${n}개 · ${src === "hand" ? "손라벨" : "SAM"}`;
    b.style.cssText = "position:relative;flex:0 0 auto;padding:0;line-height:0;border-radius:6px;overflow:hidden;cursor:pointer;background:var(--panel);" +
      (on ? "outline:2px solid var(--blue);border:0" : `border:1px solid ${src === "sam" ? "#e8913a88" : "var(--line)"}`);''')
rep('''    const cap = el("span", null, `${_disp(s)}<span style="opacity:.7;font-weight:600"> ${n}</span>`);
    cap.style.cssText = "position:absolute;left:0;bottom:0;background:#0b0e13cc;color:var(--tx);font-size:10px;font-weight:700;padding:1px 5px;border-top-right-radius:5px;line-height:1.4";''',
'''    const cap = el("span", null, `${_disp(s)}<span style="opacity:.7;font-weight:600"> ${n}</span>`);
    cap.style.cssText = `position:absolute;left:0;bottom:0;background:#0b0e13cc;color:${src === "sam" ? "#e8913a" : "var(--tx)"};font-size:10px;font-weight:700;padding:1px 5px;border-top-right-radius:5px;line-height:1.4`;''')
rep('''    x.title = "이 초 라벨 삭제";
    x.style.cssText = "position:absolute;right:0;top:0;background:#0b0e13cc;color:var(--tx);font-size:12px;font-weight:800;line-height:1;padding:2px 5px;border-bottom-left-radius:5px;cursor:pointer";
    x.onclick = async ev => {
      ev.stopPropagation();                       // 썸네일 클릭(이동)과 겹치지 않게
      x.textContent = "…";
      const prev = existingBoxes(f.stem, s);      // 지우기 전 박스 → 되돌리기에 쓴다
      try {
        await postLabel(f.stem, s, f.W, f.H, [], f.src);
        if (hooks && hooks.onDeleted) hooks.onDeleted(s, prev);
      } catch (e) { x.textContent = "실패"; }
    };''',
'''    x.title = src === "hand" ? "이 초 손라벨 삭제" : "이 초 SAM 결과 삭제";
    x.style.cssText = "position:absolute;right:0;top:0;background:#0b0e13cc;color:var(--tx);font-size:12px;font-weight:800;line-height:1;padding:2px 5px;border-bottom-left-radius:5px;cursor:pointer";
    x.onclick = async ev => {
      ev.stopPropagation();                       // 썸네일 클릭(이동)과 겹치지 않게
      x.textContent = "…";
      try {
        if (src === "sam") {
          await fetch("/api/sam2_drop", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, t: s }) });
          if (SAMMAP[f.clip]) delete SAMMAP[f.clip][s.toFixed(1)]; SAML[f.clip] = Promise.resolve(SAMMAP[f.clip] || {});
          if (hooks && hooks.onDeleted) hooks.onDeleted(s, null);
        } else {
          const prev = existingBoxes(f.stem, s);  // 지우기 전 박스 → 되돌리기에 쓴다
          await postLabel(f.stem, s, f.W, f.H, [], f.src);
          if (hooks && hooks.onDeleted) hooks.onDeleted(s, prev);
        }
      } catch (e) { x.textContent = "실패"; }
    };''')

# ---------------------------------------------------------------- J. 검수 격자: 손·SAM·DINO 통합(우선순위·출처 색·출처별 삭제)
i = s.find("// ---------- 자동라벨(DINO) 검수 화면 ----------")
j = s.find("// 재생바: 1초 · 10초 단위 이동 + 슬라이더 + 초 직접 입력 + 저장 상태")
assert 0 < i < j, "검수 함수 범위를 못 찾음"
s = s[:i] + r'''// ---------- 라벨 검수(한 화면): 손라벨·SAM·DINO 프레임 전부, 프레임마다 우선순위(손 → SAM → DINO)로 하나만 보인다 ----------
// × 는 그 프레임에 보이는 출처에서만 뺀다(손라벨은 빈 마커, SAM/DINO 는 저장소에서 제거). 다른 저장소는 건드리지 않는다.
async function openAutoReview(f, note) {
  const [sam, dino] = await Promise.all([samLabels(f.clip), autoLabels(f.clip)]);
  SAMMAP[f.clip] = sam; DINOMAP[f.clip] = dino;
  const pick = t => { const h = existingBoxes(f.stem, t); if (h !== null) return { boxes: h, src: "hand" }; const sb = samBoxesAt(sam, t); if (sb.length) return { boxes: sb, src: "sam" }; return { boxes: autoBoxesAt(dino, t), src: "dino" }; };
  const keys = Array.from(new Set([...shotSecs(f.stem).map(([s]) => s), ...samFramesOf(f.clip), ...Object.keys(dino).filter(k => (dino[k] || []).length).map(Number)])).sort((a, b) => a - b);
  const items = keys.map(t => Object.assign({ t }, pick(t))).filter(d => d.boxes.length);
  if (!items.length) return;
  const tsAll = items.map(d => d.t).join(",");
  try { await fetch("/api/warmframes?w=320&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsAll); } catch (e) {}
  fetch("/api/warmframes?w=0&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsAll);
  const old = document.getElementById("autoGrid"); if (old) old.remove();
  const wrap = el("div"); wrap.id = "autoGrid";
  wrap.style.cssText = "position:fixed;inset:0;z-index:80;background:#000a;display:flex;align-items:center;justify-content:center";
  const box = el("div");
  box.style.cssText = "background:var(--panel);border:1px solid var(--line);border-radius:12px;width:min(1150px,95vw);max-height:90vh;display:flex;flex-direction:column;box-shadow:0 12px 40px #000c";
  const head = el("div", null, "<b>라벨 검수</b>"); head.style.cssText = "padding:12px 16px;border-bottom:1px solid var(--line);font-size:14px";
  const grid = el("div"); grid.style.cssText = "padding:14px 16px;overflow:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px";
  const dropFrame = async d => {
    if (d.src === "hand") await postLabel(f.stem, d.t, f.W, f.H, [], f.src);
    else if (d.src === "sam") { await fetch("/api/sam2_drop", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, t: d.t }) }); delete sam[d.t.toFixed(1)]; SAML[f.clip] = Promise.resolve(sam); }
    else { await fetch("/api/autolabel_drop", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, t: d.t }) }); dino[d.t.toFixed(1)] = []; AUTOL[f.clip] = Promise.resolve(dino); }
    renderClipList(); fillShotsGlobal2();
  };
  let shown = items;
  const fill = () => {
    grid.innerHTML = "";
    shown.forEach(d => {
      const col = SRC_COLOR[d.src];
      const cell = el("div"); cell.style.cssText = "position:relative";
      const holder = el("div"); holder.style.cssText = `position:relative;border:1px solid ${col}88;border-radius:8px;overflow:hidden;background:#000;cursor:pointer`;
      holder.innerHTML = `<img loading="lazy" src="/frameat?clip=${encodeURIComponent(f.clip)}&t=${d.t}&w=320" style="display:block;width:100%;height:auto">` +
        `<svg viewBox="0 0 ${f.W} ${f.H}" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none">` +
        d.boxes.map(b => `<rect x="${b[1] * f.W}" y="${b[2] * f.H}" width="${b[3] * f.W}" height="${b[4] * f.H}" fill="none" stroke="${col}" stroke-width="3"/>`).join("") + `</svg>`;
      holder.onclick = () => openShot(f, shown, shown.indexOf(d));
      holder.oncontextmenu = ev => { ev.preventDefault(); wrap.remove(); openFrameAt(f.clip, d.t, LB.mode); };
      const cap = el("div", null, `${_disp(d.t)} · ${d.boxes.length}개 <span style="color:${col};font-weight:700">${d.src === "hand" ? "손" : d.src.toUpperCase()}</span>`);
      cap.style.cssText = "font-size:11px;color:var(--tx);margin-top:5px";
      const x = el("button", null, "×"); x.title = "이 프레임 라벨 제외(보이는 출처만)";
      x.style.cssText = "position:absolute;top:6px;right:6px;width:24px;height:24px;padding:0;border-radius:50%;border:none;background:#000b;color:#fff;font-size:15px;line-height:1;cursor:pointer";
      x.onclick = async ev => { ev.stopPropagation(); x.textContent = "…"; try { await dropFrame(d); d.boxes = []; cell.style.opacity = "0.35"; holder.style.filter = "grayscale(1)"; x.remove(); } catch (e) { x.textContent = "×"; } };
      cell.appendChild(holder); cell.appendChild(cap); cell.appendChild(x); grid.appendChild(cell);
    });
  };
  fill(); window.refillGrid = fill;
  const foot = el("div"); foot.style.cssText = "padding:10px 16px;border-top:1px solid var(--line);display:flex;justify-content:flex-end";
  const close = el("button", null, "닫기"); close.style.cssText = "width:auto;background:var(--panel2);color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:5px 14px;cursor:pointer"; close.onclick = () => wrap.remove();
  foot.appendChild(close); box.appendChild(head); box.appendChild(grid); box.appendChild(foot); wrap.appendChild(box);
  wrap.onclick = ev => { if (ev.target === wrap) wrap.remove(); };
  document.body.appendChild(wrap);
}

''' + s[j:]
# openShot 색: 출처별
rep('''fill=\\"none\\" stroke=\\"" + (d.hand ? "#58a6ff" : "#3fb950") + "\\" stroke-width=\\"2\\"/>";''',
    '''fill=\\"none\\" stroke=\\"" + (SRC_COLOR[d.src] || (d.hand ? "#58a6ff" : "#3fb950")) + "\\" stroke-width=\\"2\\"/>";''')
rep('''    cap.innerHTML = `${f.stem} · ${_disp(d.t)} · ${d.boxes.length}개` + (d.hand ? ' <span style="color:#58a6ff">손라벨</span>' : "") +
      ' <span style="color:var(--mut);font-weight:400">· 박스 클릭 = 그 객체를 클립 전체에서 제거 · ←/→ 이동 · 우클릭 이 프레임 편집 · Esc 닫기</span>';''',
'''    cap.innerHTML = `${_disp(d.t)} · ${d.boxes.length}개`;''')
rep('''  v.oncontextmenu = ev => { ev.preventDefault(); const t = items[idx].t; done(); const g = document.getElementById("autoGrid"); if (g) g.remove(); openFrameAt(f.clip, t, "person"); };''',
    '''  v.oncontextmenu = ev => { ev.preventDefault(); const t = items[idx].t; done(); const g = document.getElementById("autoGrid"); if (g) g.remove(); openFrameAt(f.clip, t, LB.mode); };''')

# 미사용 LB.src 초기값
rep('''let CLIPS = null, SOURCES = null, CONDS = {}, CLIPFILTER = "";''', '''let CLIPS = null, SOURCES = null, CONDS = {}, CLIPFILTER = "";
LB.src = "none";   // 현재 프레임 박스의 출처 hand/sam/dino/none''')

io.open(p, "w", encoding="utf-8").write(s)
print("editor.js: SAM 모드 통합 완료")
