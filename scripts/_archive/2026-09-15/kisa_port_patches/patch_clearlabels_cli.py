# -*- coding: utf-8 -*-
"""[학습프레임 초기화] 버튼: 이 클립의 손라벨·SAM 전파 결과·참조샷을 전부 비운다(확인창). 라벨 검수 오른쪽, 훈련 데이터 문구 앞."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "학습프레임 초기화" not in s
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:90])
    s = s.replace(old, new, 1)
rep("""  rowAct.appendChild(bUndo); rowAct.appendChild(bRedo); if (LAB === "sam") { rowAct.appendChild(bHand); rowAct.appendChild(bGo); rowAct.appendChild(bRev); } rowAct.appendChild(tstat); rowAct.appendChild(pstat);   // DINO 모드는 ↶↷ 만""",
    """  const bReset = mkBtn("학습프레임 초기화", "이 클립의 손라벨·전파 결과·참조샷을 전부 지운다(손라벨은 백업됨)"); bReset.style.cssText += ";color:#f85149;border-color:#f8514966;margin-left:auto";
  rowAct.appendChild(bUndo); rowAct.appendChild(bRedo); if (LAB === "sam") { rowAct.appendChild(bHand); rowAct.appendChild(bGo); rowAct.appendChild(bRev); } rowAct.appendChild(tstat); rowAct.appendChild(pstat); rowAct.appendChild(bReset);   // DINO 모드는 ↶↷ 만
  bReset.onclick = async () => {
    const hs = shotSecs(f.stem).length, hset = new Set(shotSecs(f.stem).map(([t]) => t)), sm = samFramesOf(f.clip).filter(t => !hset.has(t)).length;
    if (!confirm(`이 클립의 학습 프레임을 초기화합니다.\\n손라벨 ${hs}프레임 · 영상전파 ${sm}프레임 · 참조샷 ${SM.seeds.length}개가 지워집니다(손라벨은 백업됨). 계속할까요?`)) return;
    bReset.disabled = true;
    try {
      const r = await fetch("/api/clearlabels", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, kind: LB.mode === "person" ? "person" : "fire" }) }).then(r => r.json());
      if (!r.ok) throw new Error(r.err || "실패");
      if (LB.mode === "person") { try { PLABELS = await (await fetch("/api/labels?kind=person")).json(); } catch (e) {} }
      else { try { LABELS = await (await fetch("/api/labels")).json(); } catch (e) {} }
      SM.seeds = []; SM.objs = LB.mode === "fire" ? [1, 2] : [1]; SM.cur = 1; SM.handRef = false; SM.a = null; SM.b = null; SP = []; SMASK = null;
      _HIST[f.clip] = { undo: [], redo: [] };
      LB.boxes = []; LB.src = "none"; f.saved = null;
      styleHand(); drawObjs(); await refreshSam(); renderClipList(); if (typeof updateRawBadge === "function") updateRawBadge(f.stem);
    } catch (e) { alert("초기화 실패: " + e.message); }
    bReset.disabled = false;
  };""")
io.open(p, "w", encoding="utf-8").write(s)
print("client ok")
