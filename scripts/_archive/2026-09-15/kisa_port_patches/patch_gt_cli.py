# -*- coding: utf-8 -*-
"""편집기: 정답라벨 그룹(4번째 저장소, 읽기 전용 참고).
- 표시: 정답 박스 = 하늘색(#79c0ff) 점선, 정답 점 = 하늘색 마름모. 어느 모드에서나 보임(우선순위 손 > SAM > 정답 > DINO 로 프리필)
- SAM 모드 [정답 참조]: 정답 점 → SAM 탭(마스크·박스) → 그 객체 참조샷, 정답 박스 → 참조샷. 그다음 [전파]
- 훈련 데이터 문구에 '정답 n' 추가. 데이터 확인 카테고리 판정에 '이상행동·다각도' 추가(사람 편집 가능)."""
import io
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/"
def patch(name, pairs):
    p = V + name; s = io.open(p, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, (name, s.count(old), old[:90])
        s = s.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8").write(s); print(name, "ok")

patch("js/data.js", [
    ("""  if (/사람|침입|쓰러짐|배회|스토킹/.test(cat)) return "person";""",
     """  if (/사람|침입|쓰러짐|배회|스토킹|이상행동|다각도/.test(cat)) return "person";"""),
])

patch("js/editor.js", [
    # 저장소 캐시·헬퍼 (SAML 옆)
    ("""const SAML = {};               // 클립 → SAM 전파 결과 프레임맵 Promise""",
     """const GTL = {}, GTMAP = {};    // 클립 → 정답라벨(데이터셋 제공) Promise / 동기 캐시 {frames, points}
function gtLabels(clip) {
  if (!GTL[clip]) GTL[clip] = fetch("/api/gtlabel?clip=" + encodeURIComponent(clip)).then(r => r.json()).then(j => { GTMAP[clip] = j || {}; return GTMAP[clip]; }).catch(() => (GTMAP[clip] = {}));
  return GTL[clip];
}
function gtBoxesAt(gt, sec) { const o = gt && gt.frames && gt.frames[Number(sec).toFixed(1)]; return o ? Object.entries(o).map(([k, b]) => [0, b[0], b[1], b[2], b[3], +k]) : []; }
function gtPointsAt(gt, sec) { const o = gt && gt.points && gt.points[Number(sec).toFixed(1)]; return o ? Object.entries(o).map(([k, p]) => ({ obj: +k, x: p[0], y: p[1] })) : []; }
function gtFramesOf(clip) { const g = GTMAP[clip] || {}; return Object.keys(g.frames || {}).filter(k => Object.keys(g.frames[k] || {}).length).map(Number).sort((a, b) => a - b); }
const SAML = {};               // 클립 → SAM 전파 결과 프레임맵 Promise"""),
    # 프리필: 손 → SAM → 정답 → DINO
    ("""    Promise.all([samLabels(clip), autoLabels(clip)]).then(([sam, dino]) => {   // 손라벨 → SAM → DINO
      SAMMAP[clip] = sam; DINOMAP[clip] = dino;
      if (!ED || ED.clip !== clip) return;
      let bx = samBoxesAt(sam, sec), src = "sam";
      if (!bx.length) { bx = autoBoxesAt(dino, sec); src = "dino"; }""",
     """    Promise.all([samLabels(clip), autoLabels(clip), gtLabels(clip)]).then(([sam, dino, gt]) => {   // 손라벨 → SAM → 정답 → DINO
      SAMMAP[clip] = sam; DINOMAP[clip] = dino;
      if (!ED || ED.clip !== clip) return;
      let bx = samBoxesAt(sam, sec), src = "sam";
      if (!bx.length) { bx = gtBoxesAt(gt, sec).map(b => b.slice(0, 5)); src = "gt"; }
      if (!bx.length) { bx = autoBoxesAt(dino, sec); src = "dino"; }"""),
    ("""    if (!wantPseudo) { Promise.all([samLabels(clip), autoLabels(clip)]).then(([sam, dino]) => { SAMMAP[clip] = sam; DINOMAP[clip] = dino;""",
     """    if (!wantPseudo) { Promise.all([samLabels(clip), autoLabels(clip), gtLabels(clip)]).then(([sam, dino]) => { SAMMAP[clip] = sam; DINOMAP[clip] = dino;"""),
    # 색
    ("""const SRC_COLOR = { hand: "#58a6ff", sam: "#e8913a", dino: "#3fb950", none: "#3fb950" };""",
     """const SRC_COLOR = { hand: "#58a6ff", sam: "#e8913a", gt: "#79c0ff", dino: "#3fb950", none: "#3fb950" };"""),
    # 그리기: 정답 박스(점선)·점(마름모) — 두 모드 공통, 현재 박스가 정답 프리필이면 중복 안 그림
    ("""    if (LAB === "sam") {
      const dm = DINOMAP[f.clip] || {};""",
     """    {                                                 // 정답라벨(데이터셋 제공): 하늘색 점선 박스 + 마름모 점
      const gt = GTMAP[f.clip];
      if (gt && LB.src !== "gt") gtBoxesAt(gt, f.t).forEach(b => { s += rectSvg(b[1] * f.W, b[2] * f.H, b[3] * f.W, b[4] * f.H, 0, true, false, "#79c0ff"); });
      if (gt) gtPointsAt(gt, f.t).forEach(p => { const x = p.x * f.W, y = p.y * f.H; s += `<polygon points="${x},${y - 7} ${x + 7},${y} ${x},${y + 7} ${x - 7},${y}" fill="#79c0ff" stroke="#0b0e13" stroke-width="1.5"/><text x="${x + 9}" y="${y - 6}" fill="#79c0ff" font-size="13" font-weight="800">정답${p.obj}</text>`; });
    }
    if (LAB === "sam") {
      const dm = DINOMAP[f.clip] || {};"""),
    # 버튼: [정답 참조] (SAM 모드, 손라벨 참조 옆)
    ("""  const bHand = mkBtn("손라벨 참조", "이 클립의 손라벨 프레임(전파 구간 안)을 전부 참조샷으로 등록");""",
     """  const bHand = mkBtn("손라벨 참조", "이 클립의 손라벨 프레임(전파 구간 안)을 전부 참조샷으로 등록");
  const bGT = mkBtn("정답 참조", "데이터셋 정답(점·박스)을 참조샷으로: 점은 SAM 탭으로 박스를 만든다"); bGT.hidden = true;"""),
    ("""  rowAct.appendChild(bUndo); rowAct.appendChild(bRedo); if (LAB === "sam") { rowAct.appendChild(bHand); rowAct.appendChild(bGo); rowAct.appendChild(bRev); } rowAct.appendChild(tstat); rowAct.appendChild(pstat); rowAct.appendChild(bReset);   // DINO 모드는 ↶↷ 만""",
     """  rowAct.appendChild(bUndo); rowAct.appendChild(bRedo); if (LAB === "sam") { rowAct.appendChild(bHand); rowAct.appendChild(bGT); rowAct.appendChild(bGo); rowAct.appendChild(bRev); } rowAct.appendChild(tstat); rowAct.appendChild(pstat); rowAct.appendChild(bReset);   // DINO 모드는 ↶↷ 만
  gtLabels(f.clip).then(gt => { const has = (gt && ((gt.points && Object.keys(gt.points).length) || (gt.frames && Object.keys(gt.frames).length))); bGT.hidden = !has; if (ED && ED._tok === MY) { updateTStat(); draw(); } });
  bGT.onclick = async () => {                        // 정답 → 참조샷
    const gt = GTMAP[f.clip]; if (!gt) return;
    bGT.disabled = true; pstat.innerHTML = spin(0);
    const items = [];
    Object.keys(gt.frames || {}).forEach(k => Object.entries(gt.frames[k]).forEach(([o, b]) => items.push({ t: +k, obj: +o, box: b })));
    Object.keys(gt.points || {}).forEach(k => Object.entries(gt.points[k]).forEach(([o, p]) => items.push({ t: +k, obj: +o, pt: p })));
    let n = 0;
    for (const it of items) {
      let box = it.box, poly = [], pts = [];
      if (!box && it.pt) {                             // 점 → SAM 마스크 → 박스
        const r = await fetch("/api/sam2_mask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, t: it.t, pts: [[it.pt[0], it.pt[1], 1]] }) }).then(r => r.json()).catch(() => ({}));
        if (r.box) { box = r.box; poly = r.poly || []; pts = [[it.pt[0], it.pt[1], 1]]; }
      }
      n++; pstat.innerHTML = spin(Math.round(n / items.length * 100));
      if (!box) continue;
      if (!SM.objs.includes(it.obj)) SM.objs.push(it.obj);
      SM.seeds = SM.seeds.filter(q => !(Math.abs(q.t - it.t) < 0.01 && q.obj === it.obj));
      SM.seeds.push({ t: it.t, obj: it.obj, box, poly, pts, i: null, fromGT: true });
      if (Math.abs(it.t - f.t) < 0.01) { LB.boxes.push([samCls(it.obj), box[0], box[1], box[2], box[3]]); LB.src = "hand"; }
    }
    SM.objs.sort((a, b) => a - b); SM.seeds.sort((a, b) => a.t - b.t || a.obj - b.obj);
    if (!SM.objs.includes(SM.cur)) SM.cur = SM.objs[0];
    bGT.disabled = false; pstat.innerHTML = "";
    loadSam(); fillShots(); draw(); if (LB.boxes.length && LB.src === "hand") saveNow();
  };"""),
    # 정답 프리필도 탭 때 객체가 잡은 박스만 손라벨로
    ("""    if (LB.src !== "dino" && LB.src !== "sam") return;""",
     """    if (LB.src !== "dino" && LB.src !== "sam" && LB.src !== "gt") return;"""),
    ("""    if (LAB === "sam" && (LB.src === "dino" || LB.src === "sam")) dropUnownedPrefill();   // SAM: 프리필은 손라벨로 안 넘김(객체가 잡은 박스만)""",
     """    if (LAB === "sam" && (LB.src === "dino" || LB.src === "sam" || LB.src === "gt")) dropUnownedPrefill();   // SAM: 프리필은 손라벨로 안 넘김(객체가 잡은 박스만)"""),
    # 문구
    ("""    tstat.textContent = `훈련 데이터 ${hs.length + sam}건 (손라벨 ${hs.length} · 영상전파 ${sam} · DINO ${dino})`;""",
     """    const gt = GTMAP[f.clip]; const gtn = gt ? gtFramesOf(f.clip).length : 0, gtp = gt && gt.points ? Object.values(gt.points).reduce((a, o) => a + Object.keys(o).length, 0) : 0;
    tstat.textContent = `훈련 데이터 ${hs.length + sam}건 (손라벨 ${hs.length} · 영상전파 ${sam} · DINO ${dino}${gtn || gtp ? ` · 정답 ${gtn ? gtn + "박스프레임" : ""}${gtn && gtp ? " " : ""}${gtp ? gtp + "점" : ""}` : ""})`;"""),
])
