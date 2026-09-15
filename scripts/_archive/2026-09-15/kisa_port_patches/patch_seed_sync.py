# -*- coding: utf-8 -*-
"""참조샷과 손라벨 불일치 정리: 그 프레임에 손라벨 박스가 없는데(지웠거나 초기화) 참조샷만 남아 번호 글자만 떠 있던 것.
편집기를 그릴 때·프레임을 바꿀 때, 손라벨 박스와 겹치지 않는 참조샷은 버린다(화재 클립 포함)."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "pruneSeeds" not in s
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:100])
    s = s.replace(old, new, 1)
rep("""  const loadSam = () => {""",
    """  const pruneSeeds = () => {                         // 손라벨 박스가 없는 참조샷 제거(전 프레임)
    const iouq = (a, b) => { const x1 = Math.max(a[0], b[0]), y1 = Math.max(a[1], b[1]), x2 = Math.min(a[0] + a[2], b[0] + b[2]), y2 = Math.min(a[1] + a[3], b[1] + b[3]); const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1); return inter / (a[2] * a[3] + b[2] * b[3] - inter || 1); };
    const n0 = SM.seeds.length;
    SM.seeds = SM.seeds.filter(q => { if (q.fromGT) return true; const hb = existingBoxes(f.stem, q.t); return hb && hb.some(b => iouq([b[1], b[2], b[3], b[4]], q.box) > 0.3); });   // 정답 참조는 손라벨 없이도 유지
    if (SM.seeds.length !== n0) persistSam(f.clip);
  };
  const loadSam = () => {
    pruneSeeds();""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
