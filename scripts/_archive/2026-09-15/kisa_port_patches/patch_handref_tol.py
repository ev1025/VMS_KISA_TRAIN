# -*- coding: utf-8 -*-
"""손라벨 참조 매칭 허용거리 조정: 6초 넘게 안 보인 객체는 이어붙이지 않고 새 객체(재등장 신원은 위치로 알 수 없다), 허용거리 증가폭 축소."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
old = """          const q = last[k], dt = Math.max(0, t - q.t), dtp = Math.min(dt, 2);          // 예측 위치 = 마지막 위치 + 속도×경과(최대 2초까지만 외삽)
          const px = q.cx + (q.vx || 0) * dtp, py = q.cy + (q.vy || 0) * dtp;
          const tol = Math.min(0.4, 0.08 + 0.05 * dt);                                 // 오래 안 보였으면 허용 거리 확대"""
new = """          const q = last[k], dt = Math.max(0, t - q.t), dtp = Math.min(dt, 2);          // 예측 위치 = 마지막 위치 + 속도×경과(최대 2초까지만 외삽)
          if (dt > 6) return;                                                           // 6초 넘게 안 보였으면 같은 사람이라 단정 못 함 → 새 객체
          const px = q.cx + (q.vx || 0) * dtp, py = q.cy + (q.vy || 0) * dtp;
          const tol = Math.min(0.3, 0.08 + 0.03 * dt);                                 // 안 보인 시간만큼 허용 거리 조금 확대"""
assert s.count(old) == 1
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
