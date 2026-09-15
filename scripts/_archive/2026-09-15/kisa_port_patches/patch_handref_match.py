# -*- coding: utf-8 -*-
"""손라벨 참조의 객체 번호 배정: 직전 프레임만 보던 것을 '각 객체의 마지막 위치'와 비교하도록.
(한 프레임이라도 빠지면 새 객체가 생겨 20개까지 불어나던 문제)"""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:90]
    s = s.replace(old, new, 1)
rep("""    let prev = [], prevT = null, nextObj = SM.seeds.length ? Math.max.apply(null, SM.objs) : 0;""",
    """    let nextObj = SM.seeds.length ? Math.max.apply(null, SM.objs) : 0;
    const last = {};                                  // 객체 → 마지막 위치 {cx,cy,t}. 이미 찍은 참조샷으로 초기화
    SM.seeds.slice().sort((a, b) => a.t - b.t).forEach(q => { last[q.obj] = { cx: q.box[0] + q.box[2] / 2, cy: q.box[1] + q.box[3] / 2, t: q.t }; });""")
rep("""          let best = null, bd = Math.min(0.5, 0.15 + 0.05 * (prevT == null ? 0 : t - prevT));   // 프레임 간격이 멀수록 허용 거리 확대
          prev.forEach(q => { if (used.has(q.obj)) return; const d = Math.hypot(q.cx - cx, q.cy - cy); if (d < bd) { bd = d; best = q.obj; } });
          obj = best != null ? best : ++nextObj;""",
    """          let best = null, bestScore = Infinity;      // 모든 객체의 마지막 위치와 비교. 오래 안 보인 객체는 허용 거리를 넉넉히
          Object.keys(last).forEach(k => { const q = last[k], o = +k; if (used.has(o)) return; const tol = Math.min(0.5, 0.15 + 0.05 * Math.max(0, t - q.t)); const d = Math.hypot(q.cx - cx, q.cy - cy); if (d < tol && d / tol < bestScore) { bestScore = d / tol; best = o; } });
          obj = best != null ? best : ++nextObj;""")
rep("""        if (!SM.objs.includes(obj)) SM.objs.push(obj);
        used.add(obj); cur.push({ obj, cx, cy });""",
    """        if (!SM.objs.includes(obj)) SM.objs.push(obj);
        used.add(obj); last[obj] = { cx, cy, t };""")
rep("""      prev = cur; prevT = t;
    });""",
    """    });""")
# 더 이상 안 쓰는 cur 선언 정리
rep("""      const used = new Set(), cur = [], taken = [];""", """      const used = new Set(), taken = [];""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
