# -*- coding: utf-8 -*-
"""손라벨 참조 배정: 라벨 빈틈이 2초를 넘고 박스 수가 최근(30초 안) 객체 수와 같으면 좌→우 순서로 짝지음(무리가 같이 움직인 경우).
C049200_005 에서 세 사람이 7초 뒤 함께 왼쪽으로 이동하자 '가장 가까운 위치' 규칙이 셋 다 옆 사람으로 바꿔 붙이던 것."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "순서 유지" not in s
old = """      else {
        const pairs = [];                              // 모든 (기존 객체, 박스) 쌍을 거리/허용거리 순으로 → 가까운 것부터 확정"""
new = """      else {
        // 라벨 빈틈이 2초 넘고 박스 수 = 최근 객체 수면 좌→우 순서로 짝지음(무리가 같이 움직이면 '가까운 위치' 는 옆 사람으로 붙는다)
        let done = false;
        const recentK = Object.keys(last).filter(k => t - last[k].t <= 30);
        const gap = recentK.length ? Math.min.apply(null, recentK.map(k => t - last[k].t)) : 0;
        if (recentK.length && gap > 2 && cand.length === recentK.length) {
          const cs = cand.slice().sort((a, b) => a.cx - b.cx), ks = recentK.slice().sort((a, b) => last[a].cx - last[b].cx);
          const ok = cs.every((c, n) => { const q = last[ks[n]]; return Math.hypot(q.cx - c.cx, q.cy - c.cy) < Math.min(0.3, 0.08 + 0.03 * (t - q.t)); });
          if (ok) { cs.forEach((c, n) => { c.obj = +ks[n]; }); done = true; }   // 순서 유지 배정
        }
        if (!done) {
        const pairs = [];                              // 모든 (기존 객체, 박스) 쌍을 거리/허용거리 순으로 → 가까운 것부터 확정"""
assert s.count(old) == 1
s = s.replace(old, new, 1)
old2 = """        cand.forEach(c => { if (c.obj == null) c.obj = ++nextObj; });   // 어느 객체와도 안 맞으면 새 객체
      }"""
new2 = """        }
        cand.forEach(c => { if (c.obj == null) c.obj = ++nextObj; });   // 어느 객체와도 안 맞으면 새 객체
      }"""
assert s.count(old2) == 1
s = s.replace(old2, new2, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
