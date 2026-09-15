# -*- coding: utf-8 -*-
"""객체 줄의 참조샷 프레임 번호를 누르면 그 프레임으로 이동(그 객체 선택). × 는 그대로 참조샷 취소."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
old = """        chip.innerHTML = `<b style="color:${samCol(o)}">${_disp(sd.t)}</b>`;"""
new = """        chip.innerHTML = `<b style="color:${samCol(o)};cursor:pointer" title="이 프레임으로 이동">${_disp(sd.t)}</b>`;
        chip.querySelector("b").onclick = () => { SM.cur = o; openFrameAt(f.clip, sd.t, LB.mode); };   // 번호 클릭 = 이동"""
assert s.count(old) == 1
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
