# -*- coding: utf-8 -*-
"""DINO 탭 제거 → SAM 한 모드. 드래그 = 박스(빈 곳=새 박스, 박스 안=이동), 클릭 = SAM 점(기존), 우클릭 = 제외점(기존).
그린/옮긴 박스는 현재 객체의 참조샷이 된다(크기 조절과 같은 규칙)."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "sd = { p, u:" not in s
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:90])
    s = s.replace(old, new, 1)
# 1) 탭 제거: LAB 는 항상 sam
rep("""let LAB = "sam"; try { LAB = localStorage.getItem("kisa_lab_tab") === "dino" ? "dino" : "sam"; } catch (e) {}""",
    """const LAB = "sam";                   // 편집 모드는 SAM 하나. 드래그=박스, 클릭=점, 우클릭=제외점""")
i0 = s.index("function labTabs(f, cur) {"); i1 = s.index("function renderEditor(f) {")
s = s[:i0] + s[i1:]
rep("""  top.appendChild(labTabs(f, LAB));                  // [SAM] [DINO]\n""", "")
# 2) 마우스: 누른 자리를 기억해 두고, 끌기 시작하면 박스(새로/이동), 안 끌면 onclick 이 점으로 처리
rep("""    if (LAB === "sam") return;                        // SAM: 그리기/이동 없음. 클릭은 onclick 에서 점으로""",
    """    if (ev.button !== 0) return;                      // 우클릭 = 제외점(oncontextmenu)
    sd = { p, u: ev.shiftKey ? null : boxUnder(p) }; return;   // 누른 자리 기억. 끌면 박스(빈 곳=새 박스 · 박스 안=이동), 안 끌면 onclick 에서 점""")
rep("""  let lastP = null;                                  // 마지막 마우스 위치(이미지 좌표) → Del 대상 박스 판단""",
    """  let lastP = null, sd = null;                       // 마지막 마우스 위치(이미지 좌표) → Del 대상 박스 판단 · sd = 누른 자리(드래그 판정)""")
rep("""    if (rz) { resizeTo(p); draw(); return; }
    if (mv) { moveTo(p); draw(); return; }""",
    """    if (sd) {                                        // 3px 넘게 끌면 드래그 시작(클릭=점 과 구분)
      if (Math.hypot(p.x - sd.p.x, p.y - sd.p.y) < 3) return;
      if (sd.u !== null) { const b = LB.boxes[sd.u]; snap(); mv = { i: sd.u, ox: sd.p.x - b[1] * f.W, oy: sd.p.y - b[2] * f.H }; sel = sd.u; }
      else { curCls = LB.mode === "person" ? 0 : samCls(SM.cur); st = sd.p; }   // 화재: 현재 객체(1=불 2=연기)가 클래스
      sd = null; _resized = true;                     // 드래그 뒤의 click 은 점으로 안 찍는다
    }
    if (rz) { resizeTo(p); draw(); return; }
    if (mv) { moveTo(p); draw(); return; }""")
rep("""    if (mv) { mv = null; draw(); saveNow(); return; }      // 이동 끝 → 그 자리에서 저장
    if (!st) return; const p = toImg(ev);""",
    """    if (mv) { const i = mv.i; mv = null; seedFromBox(i); sel = null; draw(); saveNow(); return; }   // 이동 끝 → 참조샷 따라가고 저장
    sd = null;
    if (!st) return; const p = toImg(ev);""")
rep("""    if (w > 4 && h > 4) { snap(); LB.boxes.push([curCls, x / f.W, y / f.H, w / f.W, h / f.H]); draw(); saveNow(); }""",
    """    if (w > 4 && h > 4) { snap(); LB.boxes.push([curCls, x / f.W, y / f.H, w / f.W, h / f.H]); seedFromBox(LB.boxes.length - 1); draw(); saveNow(); }   // 그린 박스 = 현재 객체 참조샷""")
rep("""    if (!h && u !== null && LAB !== "sam") ov.style.cursor = "move";""",
    """    if (!h && u !== null) ov.style.cursor = "move";""")
# 3) DINO 전용 단축키 제거
rep("""    if (LAB !== "sam" && (ev.key === "1" || ev.key === "2") && LB.mode !== "person" && sel !== null && LB.boxes[sel]) {   // DINO 모드: 1=불 2=연기 (선택 박스)
      snap(); LB.boxes[sel][0] = ev.key === "1" ? 0 : 1; draw(); saveNow(); return;
    }
""", "")
io.open(p, "w", encoding="utf-8").write(s)
print("ok", s.count("LAB !== \"sam\""), "dead LAB!==sam branches left")
