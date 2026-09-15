# -*- coding: utf-8 -*-
"""손라벨 참조 번호 배정에 이동 예측을 넣는다: 객체의 마지막 위치가 아니라 (마지막 위치 + 속도×경과시간) 과 비교.
C049100_005 에서 걷던 사람의 라벨이 몇 프레임 빠진 사이 왼쫙에서 새로 들어온 사람이 그 번호를 가로챈 것이 전파 뒤섞임의 원인."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:90])
    s = s.replace(old, new, 1)
rep("""        cand.forEach((c, ci) => Object.keys(last).forEach(k => { const q = last[k]; const tol = Math.min(0.5, 0.15 + 0.05 * Math.max(0, t - q.t)); const d = Math.hypot(q.cx - c.cx, q.cy - c.cy); if (d < tol) pairs.push({ ci, obj: +k, score: d / tol }); }));""",
    """        cand.forEach((c, ci) => Object.keys(last).forEach(k => {
          const q = last[k], dt = Math.max(0, t - q.t), dtp = Math.min(dt, 2);          // 예측 위치 = 마지막 위치 + 속도×경과(최대 2초까지만 외삽)
          const px = q.cx + (q.vx || 0) * dtp, py = q.cy + (q.vy || 0) * dtp;
          const tol = Math.min(0.4, 0.08 + 0.05 * dt);                                 // 오래 안 보였으면 허용 거리 확대
          const d = Math.hypot(px - c.cx, py - c.cy);
          if (d < tol) pairs.push({ ci, obj: +k, score: d / tol });
        }));""")
rep("""        last[obj] = { cx: c.cx, cy: c.cy, t };""",
    """        const q0 = last[obj], dt0 = q0 ? t - q0.t : 0;
        last[obj] = { cx: c.cx, cy: c.cy, t, vx: q0 && dt0 > 0 ? (c.cx - q0.cx) / dt0 : 0, vy: q0 && dt0 > 0 ? (c.cy - q0.cy) / dt0 : 0 };""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
