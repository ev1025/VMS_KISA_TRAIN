# -*- coding: utf-8 -*-
"""손라벨 참조 번호 배정: 박스 순서대로 잡던 것을 '프레임 안의 모든 (객체, 박스) 쌍을 거리순으로' 배정.
(왼쪽에서 새로 들어온 사람이 기존 객체 번호를 가로채 두 사람의 참조샷이 한 번호에 섞이던 것 → SAM 이 두 사람을 오락가락)"""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:90])
    s = s.replace(old, new, 1)
old_block_start = s.index("      const used = new Set(), taken = [];")
old_block_end = s.index("    SM.objs.sort((a, b) => a - b); SM.seeds.sort((a, b) => a.t - b.t || a.obj - b.obj);")
new_block = """      const iou = (a, b) => { const x1 = Math.max(a[1], b[1]), y1 = Math.max(a[2], b[2]), x2 = Math.min(a[1] + a[3], b[1] + b[3]), y2 = Math.min(a[2] + a[4], b[2] + b[4]); const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1); return inter / (a[3] * a[4] + b[3] * b[4] - inter || 1); };
      const taken = [], cand = [];
      boxes.forEach((b, i) => { if (taken.some(q => iou(q, b) > 0.7)) return; taken.push(b); cand.push({ b, i, cx: b[1] + b[3] / 2, cy: b[2] + b[4] / 2, obj: null }); });   // 겹치는 중복 박스는 하나만
      if (LB.mode === "fire") cand.forEach(c => { c.obj = c.b[0] === 1 ? 2 : 1; });
      else {
        const pairs = [];                              // 모든 (기존 객체, 박스) 쌍을 거리/허용거리 순으로 → 가까운 것부터 확정
        cand.forEach((c, ci) => Object.keys(last).forEach(k => { const q = last[k]; const tol = Math.min(0.5, 0.15 + 0.05 * Math.max(0, t - q.t)); const d = Math.hypot(q.cx - c.cx, q.cy - c.cy); if (d < tol) pairs.push({ ci, obj: +k, score: d / tol }); }));
        pairs.sort((x, y) => x.score - y.score);
        const usedObj = new Set();
        pairs.forEach(pr => { const c = cand[pr.ci]; if (c.obj != null || usedObj.has(pr.obj)) return; c.obj = pr.obj; usedObj.add(pr.obj); });
        cand.forEach(c => { if (c.obj == null) c.obj = ++nextObj; });   // 어느 객체와도 안 맞으면 새 객체
      }
      cand.forEach(c => {
        const obj = c.obj, b = c.b, i = c.i;
        if (!SM.objs.includes(obj)) SM.objs.push(obj);
        last[obj] = { cx: c.cx, cy: c.cy, t };
        SM.seeds = SM.seeds.filter(q => !(Math.abs(q.t - t) < 0.01 && q.obj === obj));
        SM.seeds.push({ t, obj, box: [b[1], b[2], b[3], b[4]], poly: [], pts: [], i, fromHand: true });
      });
    });
"""
s = s[:old_block_start] + new_block + s[old_block_end:]
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
