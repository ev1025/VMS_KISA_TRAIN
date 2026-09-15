# -*- coding: utf-8 -*-
"""SAM 모드: [손라벨 참조] 버튼. 이 클립의 손라벨 프레임(전파 구간 안)을 전부 참조샷으로 등록한다.
객체 번호: 화재 = 클래스(불 1·연기 2). 사람 = 프레임 순서대로 박스 중심이 가장 가까운 이전 객체를 이어받고, 없으면 새 객체."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "손라벨 참조" not in s, "이미 적용됨"
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:100]
    s = s.replace(old, new, 1)

rep('''  const pstat = el("span", "now", ""); pstat.style.whiteSpace = "nowrap";
  rowAct.appendChild(bUndo); rowAct.appendChild(bRedo); if (LAB === "sam") { rowAct.appendChild(bGo); rowAct.appendChild(bRev); } rowAct.appendChild(pstat);   // DINO 모드는 ↶↷ 만''',
'''  const pstat = el("span", "now", ""); pstat.style.whiteSpace = "nowrap";
  const bHand = mkBtn("손라벨 참조", "이 클립의 손라벨 프레임(전파 구간 안)을 전부 참조샷으로 등록");
  rowAct.appendChild(bUndo); rowAct.appendChild(bRedo); if (LAB === "sam") { rowAct.appendChild(bHand); rowAct.appendChild(bGo); rowAct.appendChild(bRev); } rowAct.appendChild(pstat);   // DINO 모드는 ↶↷ 만''')

rep('''  const loadSam = () => {''',
'''  bHand.onclick = () => {                            // 손라벨 → 참조샷(구간 안 전부)
    const frames = shotSecs(f.stem).map(([t]) => t).filter(t => (SM.a == null || t >= SM.a) && (SM.b == null || t <= SM.b));
    let prev = [], prevT = null, nextObj = SM.seeds.length ? Math.max.apply(null, SM.objs) : 0;
    frames.forEach(t => {
      const boxes = existingBoxes(f.stem, t) || [];
      if (!boxes.length) return;
      const used = new Set(), cur = [];
      boxes.forEach((b, i) => {
        const cx = b[1] + b[3] / 2, cy = b[2] + b[4] / 2;
        let obj;
        if (LB.mode === "fire") obj = b[0] === 1 ? 2 : 1;               // 화재: 클래스가 곧 객체
        else {
          let best = null, bd = Math.min(0.5, 0.15 + 0.05 * (prevT == null ? 0 : t - prevT));   // 프레임 간격이 멀수록 허용 거리 확대
          prev.forEach(q => { if (used.has(q.obj)) return; const d = Math.hypot(q.cx - cx, q.cy - cy); if (d < bd) { bd = d; best = q.obj; } });
          obj = best != null ? best : ++nextObj;
        }
        if (!SM.objs.includes(obj)) SM.objs.push(obj);
        used.add(obj); cur.push({ obj, cx, cy });
        SM.seeds = SM.seeds.filter(q => !(Math.abs(q.t - t) < 0.01 && q.obj === obj));
        SM.seeds.push({ t, obj, box: [b[1], b[2], b[3], b[4]], poly: [], pts: [], i });
      });
      prev = cur; prevT = t;
    });
    SM.objs.sort((a, b) => a - b); SM.seeds.sort((a, b) => a.t - b.t || a.obj - b.obj);
    if (!SM.objs.includes(SM.cur)) SM.cur = SM.objs[0];
    loadSam(); fillShots();
  };
  const loadSam = () => {''')
io.open(p, "w", encoding="utf-8").write(s)
print("hand seeds ok")
