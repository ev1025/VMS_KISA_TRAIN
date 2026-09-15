# -*- coding: utf-8 -*-
"""SAM 모드 탭 저장: 프레임에 DINO 프리필이 떠 있던 경우, 참조샷(객체)이 잡은 박스만 손라벨로 남기고 나머지 프리필은 뺀다.
(탭 한 번에 다른 사람의 DINO 박스까지 손라벨로 들어가던 것 방지) DINO 후보는 점선으로 계속 보인다."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "dropUnownedPrefill" not in s
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:90])
    s = s.replace(old, new)
rep("""  const seedFromBox = i => {                       // 박스 크기 조절 → 그 박스를 쓰는 객체의 참조샷만 갱신(현재 객체와 무관)""",
"""  const dropUnownedPrefill = () => {               // DINO 프리필 프레임에서 탭했으면 객체가 잡은 박스만 남긴다(나머지 프리필은 손라벨로 안 넘김)
    if (LB.src !== "dino") return;
    const own = SM.seeds.filter(q => Math.abs(q.t - f.t) < 0.01 && q.i != null);
    const keep = new Set(own.map(q => q.i));
    const map = {}; let k = 0;
    LB.boxes = LB.boxes.filter((b, i) => { if (keep.has(i)) { map[i] = k++; return true; } return false; });
    own.forEach(q => { q.i = map[q.i]; });
    LB.src = "hand";
  };
  const seedFromBox = i => {                       // 박스 크기 조절 → 그 박스를 쓰는 객체의 참조샷만 갱신(현재 객체와 무관)""")
# samPoint · samRecompute 의 저장 직전
rep("""    seedSet(r.box, r.poly, SP, idx);
    draw(); saveNow();                                 // 탭한 프레임 → 손라벨""",
"""    seedSet(r.box, r.poly, SP, idx); dropUnownedPrefill();
    draw(); saveNow();                                 // 탭한 프레임 → 손라벨(객체가 잡은 박스만)""")
rep("""    seedSet(r.box, r.poly, SP, idx); draw(); saveNow();""",
"""    seedSet(r.box, r.poly, SP, idx); dropUnownedPrefill(); draw(); saveNow();""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
