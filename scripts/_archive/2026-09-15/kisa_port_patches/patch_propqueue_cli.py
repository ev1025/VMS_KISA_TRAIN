# -*- coding: utf-8 -*-
"""편집기: 전파는 서버 큐에 넣고 떠나도 된다. 클립을 열면 그 클립의 전파 작업 상태(대기/진행 %)를 이어서 보여주고,
끝나면 저장소를 다시 읽어 화면·배지를 갱신한다. 토글 해제 = /api/sam2_clear 한 번."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "watchJob" not in s, "이미 적용됨"
i = s.find("  bGo.onclick = async () => {")
j = s.find("  ov.onmouseup = finish;", i)
assert 0 < i < j
new = r'''  const refreshSam = async () => {                    // 저장소를 다시 읽어 화면·배지·토글 상태를 맞춘다
    delete SAML[f.clip]; const sam = await samLabels(f.clip); SAMMAP[f.clip] = sam;
    SAMFR[f.stem] = samFramesOf(f.clip); SM.propFrames = SAMFR[f.stem].map(t => Number(t).toFixed(1));
    renderClipList(); if (typeof updateRawBadge === "function") updateRawBadge(f.stem);
    if (!(ED && ED.clip === f.clip)) return;
    styleGo(); fillShots();
    if (LB.src === "sam" || (!f.saved && !LB.boxes.length)) { const bx = samBoxesAt(sam, f.t); LB.boxes = bx; LB.src = bx.length ? "sam" : "none"; }
    draw();
  };
  let _watching = false;
  const watchJob = async () => {                      // 이 클립의 전파 작업을 끝날 때까지 지켜본다(다른 클립에 가 있어도 계속)
    if (_watching) return; _watching = true;
    let seen = null;
    while (true) {
      const jobs = await fetch(`/api/sam2_jobs?clip=${encodeURIComponent(f.clip)}`).then(r => r.json()).catch(() => []);
      const act = jobs.find(jb => jb.state === "running" || jb.state === "queued");
      if (!act) { if (seen) seen = jobs.find(jb => jb.id === seen.id) || seen; break; }
      seen = act;
      if (ED && ED.clip === f.clip) { bGo.disabled = true; pstat.innerHTML = act.state === "queued" ? `<span style="color:var(--mut)">대기 ${act.pos}</span>` : spin(act.total ? Math.min(99, Math.round(act.done / act.total * 100)) : 0); }
      await new Promise(r => setTimeout(r, 800));
    }
    _watching = false;
    if (!seen) return;                                // 작업이 없었다 → 아무것도 안 바꾼다
    if (ED && ED.clip === f.clip) { bGo.disabled = false; pstat.innerHTML = seen.err ? '<b style="color:#f85149">실패</b>' : ""; }
    if (!seen.err) { SM.seeds = []; SM.handRef = false; SM.objs = LB.mode === "fire" ? [1, 2] : [1]; SM.cur = 1; if (ED && ED.clip === f.clip) { SP = []; SMASK = null; styleHand(); drawObjs(); } }   // 참조샷은 전파에 쓰였으니 정리
    await refreshSam();
  };
  bGo.onclick = async () => {
    if (SM.propFrames && SM.propFrames.length) {      // 토글 해제: 이 클립의 SAM 결과를 저장소에서 전부 뺀다
      bGo.disabled = true; pstat.innerHTML = spin(0);
      await fetch("/api/sam2_clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip }) }).catch(() => {});
      bGo.disabled = false; pstat.innerHTML = "";
      await refreshSam(); return;
    }
    if (!SM.seeds.length) return;
    if (SM.a == null || SM.b == null) {               // 구간을 안 정했으면 확인
      const ts0 = SM.seeds.map(q => q.t), lo0 = Math.min.apply(null, ts0), hi0 = Math.max.apply(null, ts0);
      const a0 = SM.a == null ? Math.max(0, lo0 - 5) : SM.a, b0 = SM.b == null ? Math.min(f.last, hi0 + 10) : SM.b;
      if (!confirm(`시작/종료를 정하지 않았습니다.\n참조샷 기준 ${_disp(a0)} ~ ${_disp(b0)} 구간으로 전파할까요?`)) return;
    }
    bGo.disabled = true; pstat.innerHTML = spin(0);
    const ts = SM.seeds.map(q => q.t), lo = Math.min.apply(null, ts), hi = Math.max.apply(null, ts);
    const a = SM.a == null ? lo - 5 : Math.min(SM.a, lo), b = SM.b == null ? hi + 10 : Math.max(SM.b, hi);
    const start = await fetch("/api/sam2_propagate_start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, seeds: SM.seeds.map(q => ({ t: q.t, box: q.box, obj: q.obj })), back: Math.max(0, lo - Math.max(0, a)), fwd: Math.max(0, Math.min(f.last, b) - hi), step: _step() }) }).then(r => r.json()).catch(() => ({ err: "x" }));
    if (start.err) { bGo.disabled = false; pstat.innerHTML = '<b style="color:#f85149">실패</b>'; return; }
    watchJob();                                       // 서버 큐가 처리·저장한다. 다른 클립에 가도 된다
  };
  watchJob();                                         // 이 클립에 진행 중인 전파가 있으면 이어서 보여준다
'''
s = s[:i] + new + s[j:]
# 라벨 검수: SAM 결과가 없으면 회색 비활성. 전파 토글 색과 같은 자리에서 맞춘다
old = """  const styleGo = () => { const on = !!(SM.propFrames && SM.propFrames.length); bGo.style.background = on ? "var(--blue)" : "var(--panel)"; bGo.style.color = on ? "#06090f" : "var(--blue)"; };"""
new2 = """  const styleGo = () => { const on = !!(SM.propFrames && SM.propFrames.length); bGo.style.background = on ? "var(--blue)" : "var(--panel)"; bGo.style.color = on ? "#06090f" : "var(--blue)"; bRev.disabled = !on; bRev.style.opacity = on ? "1" : "0.4"; bRev.style.cursor = on ? "pointer" : "default"; bRev.title = on ? "SAM 전파 결과를 격자로 검수" : "검수할 SAM 결과가 없습니다"; };"""
assert s.count(old) == 1
s = s.replace(old, new2, 1)
# 라벨 검수 오른쪽: 훈련 데이터 N건 (손라벨 a · 영상전파 b · DINO c). N = 손라벨 ∪ 영상전파. DINO 는 수정 전엔 훈련에 안 들어가 참고용
old = """  rowAct.appendChild(bUndo); rowAct.appendChild(bRedo); if (LAB === "sam") { rowAct.appendChild(bHand); rowAct.appendChild(bGo); rowAct.appendChild(bRev); } rowAct.appendChild(pstat);   // DINO 모드는 ↶↷ 만"""
new3 = """  const tstat = el("span", "now", ""); tstat.style.cssText = "color:var(--mut);font-size:12px;white-space:nowrap";
  rowAct.appendChild(bUndo); rowAct.appendChild(bRedo); if (LAB === "sam") { rowAct.appendChild(bHand); rowAct.appendChild(bGo); rowAct.appendChild(bRev); } rowAct.appendChild(tstat); rowAct.appendChild(pstat);   // DINO 모드는 ↶↷ 만
  const updateTStat = () => {
    const hs = shotSecs(f.stem), hset = new Set(hs.map(([t]) => t));
    const sam = samFramesOf(f.clip).filter(t => !hset.has(t)).length;
    const dm = DINOMAP[f.clip] || {}; const dino = Object.keys(dm).filter(k => (dm[k] || []).length).length;
    tstat.textContent = `훈련 데이터 ${hs.length + sam}건 (손라벨 ${hs.length} · 영상전파 ${sam} · DINO ${dino})`;
  };"""
assert s.count(old) == 1
s = s.replace(old, new3, 1)
old = """  const fillShots = () => (drawTrack(bar.tk, f), renderShotRow(shots, f, {"""
new4 = """  const fillShots = () => (drawTrack(bar.tk, f), updateTStat(), renderShotRow(shots, f, {"""
assert s.count(old) == 1
s = s.replace(old, new4, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("editor.js: 전파 큐 감시·서버 저장")
