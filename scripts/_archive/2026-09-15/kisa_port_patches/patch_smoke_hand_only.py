# -*- coding: utf-8 -*-
"""화재 클립: SAM 객체는 불(1) 하나. 연기는 참조샷·전파 없이 손라벨 박스로만.
 우클릭 드래그 = 연기 박스(손라벨), 좌클릭 드래그 = 불 박스(참조샷). 우클릭(끌지 않음) = 제외점 그대로."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "연기는 참조샷으로 안 넣는다" not in s
def rep(old, new, n=1):
    global s
    assert s.count(old) == n, (s.count(old), old[:90])
    s = s.replace(old, new)
# 화재 SAM 객체 = 불 하나
rep("""  if (LB.mode === "fire") { SM.objs = [1, 2]; if (!FIRE_OBJ[SM.cur]) SM.cur = 1; }   // 화재: 불·연기 두 객체 고정""",
    """  if (LB.mode === "fire") { SM.objs = [1]; SM.cur = 1; }   // 화재: SAM 객체는 불 하나(연기는 손라벨 박스만)""")
rep("""SM.objs = LB.mode === "fire" ? [1, 2] : [1];""", """SM.objs = [1];""", 2)
rep("""      SM.objs = LB.mode === "fire" ? [1, 2] : SM.objs.filter(o => used.has(o) || o === 1);""",
    """      SM.objs = LB.mode === "fire" ? [1] : SM.objs.filter(o => used.has(o) || o === 1);""")
rep("""      if (LB.mode === "fire") cand.forEach(c => { c.obj = c.b[0] === 1 ? 2 : 1; });   // 화재: 클래스가 곧 객체""",
    """      if (LB.mode === "fire") { for (let k = cand.length - 1; k >= 0; k--) { if (cand[k].b[0] === 1) cand.splice(k, 1); else cand[k].obj = 1; } }   // 화재: 불 박스만 객체 1 참조샷. 연기는 참조샷으로 안 넣는다""")
rep("""      if (LB.mode === "fire") { if (n <= 2) { SM.cur = n; loadSam(); } return; }   // 화재: 불(1)·연기(2) 만""",
    """      if (LB.mode === "fire") return;                  // 화재: 객체는 불 하나""")
# 연기 박스는 참조샷이 되지 않는다(그리기·이동·크기조절 모두 이 함수를 거친다)
rep("""  const seedFromBox = i => {                       // 박스 크기 조절 → 그 박스를 쓰는 객체의 참조샷만 갱신(현재 객체와 무관)
    const b = LB.boxes[i]; if (!b) return;""",
    """  const seedFromBox = i => {                       // 박스 크기 조절 → 그 박스를 쓰는 객체의 참조샷만 갱신(현재 객체와 무관)
    const b = LB.boxes[i]; if (!b) return;
    if (LB.mode === "fire" && b[0] === 1) return;   // 연기는 참조샷으로 안 넣는다(손라벨로만)""")
# 우클릭 드래그 = 연기 박스(화재), 우클릭 = 제외점
rep("""    if (ev.button !== 0) return;                      // 우클릭 = 제외점(oncontextmenu)
    sd = { p, u: ev.shiftKey ? null : boxUnder(p) }; return;""",
    """    if (ev.button === 2) { if (LB.mode === "fire") sd = { p, u: null, cls: 1 }; return; }   // 화재: 우클릭 끌기 = 연기 박스. 안 끌면 제외점(oncontextmenu)
    if (ev.button !== 0) return;
    sd = { p, u: ev.shiftKey ? null : boxUnder(p), cls: 0 }; return;""")
rep("""      else { curCls = LB.mode === "person" ? 0 : samCls(SM.cur); st = sd.p; }   // 화재: 현재 객체(1=불 2=연기)가 클래스""",
    """      else { curCls = sd.cls; st = sd.p; }            // 좌클릭 끌기 = 불/사람(0) · 우클릭 끌기 = 연기(1)""")
rep("""  ov.oncontextmenu = ev => { ev.preventDefault(); if (LAB === "sam" && !_space && !rz && !mv) {""",
    """  ov.oncontextmenu = ev => { ev.preventDefault(); if (_resized) { _resized = false; return; } if (LAB === "sam" && !_space && !rz && !mv) {""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
