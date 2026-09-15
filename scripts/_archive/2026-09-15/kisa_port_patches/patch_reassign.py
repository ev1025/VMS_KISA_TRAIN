# -*- coding: utf-8 -*-
"""1) 객체 N 을 선택한 채 다른 객체 M 의 박스를 탭하면 → 그 참조샷을 N 으로 옮긴다(번호 바꾸기). SAM 재계산 없음.
2) 참조샷이 하나도 없는 객체 번호는 객체 줄에서 사라진다(현재 선택 객체·1번·화재 객체는 유지)."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "번호 바꾸기" not in s
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:100])
    s = s.replace(old, new, 1)
rep("""    const claimed = new Set(LB.boxes.map((b, i) => i).filter(i => { const q = seedForBox(i); return q && q.obj !== SM.cur; }));   // 다른 객체의 박스""",
    """    const claimed = new Set(LB.boxes.map((b, i) => i).filter(i => { const q = seedForBox(i); return q && q.obj !== SM.cur; }));   // 다른 객체의 박스
    if (label === 1 && !SP.length) {                   // 번호 바꾸기: 다른 객체의 박스를 점 없이 탭 → 그 참조샷을 현재 객체로
      const oi = LB.boxes.findIndex((b, i) => claimed.has(i) && x >= b[1] && x <= b[1] + b[3] && y >= b[2] && y <= b[2] + b[4]);
      if (oi >= 0) {
        const q = seedForBox(oi);
        if (q) {
          SM.seeds = SM.seeds.filter(s2 => !(Math.abs(s2.t - t) < 0.01 && s2.obj === SM.cur));   // 현재 객체가 이 프레임에 갖고 있던 참조샷은 버린다
          q.obj = SM.cur; q.i = oi; SP = (q.pts || []).slice(); SMASK = { box: q.box, poly: q.poly || [] };
          LB.boxes[oi][0] = samCls(SM.cur);
          drawObjs(); draw(); saveNow(); return;
        }
      }
    }""")
rep("""  function drawObjs() {
    persistSam(f.clip);
    rowObj.innerHTML = "";""",
    """  function drawObjs() {
    SM.objs = SM.objs.filter(o => o === 1 || o === SM.cur || LB.mode === "fire" || SM.seeds.some(q => q.obj === o));   // 참조샷 없는 번호는 정리
    if (!SM.objs.length) SM.objs = [1];
    persistSam(f.clip);
    rowObj.innerHTML = "";""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
