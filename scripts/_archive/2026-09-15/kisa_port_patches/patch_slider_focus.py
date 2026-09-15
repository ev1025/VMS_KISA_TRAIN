# -*- coding: utf-8 -*-
"""프레임바 슬라이더를 클릭만 해도(값 변화 없이) 포커스가 슬라이더에 남아 숫자키가 먹히던 것:
 1) 슬라이더는 마우스를 떼면 바로 포커스 해제  2) 그래도 슬라이더에 포커스가 있으면 숫자키를 단축키로 넘긴다(입력칸은 예전처럼 입력)."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:100])
    s = s.replace(old, new, 1)
rep("""    if (ev.target && /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName)) return;   // 프레임번호 입력 중엔""",
    """    if (ev.target && ev.target.tagName === "INPUT" && ev.target.type === "range") { ev.preventDefault(); ev.target.blur(); }   // 슬라이더에 포커스가 남아도 단축키로
    else if (ev.target && /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName)) return;   // 프레임번호 입력 중엔""")
rep("""  sl.oninput = () => { num.value = sl.value; };          // 끄는 동안은 숫자만 따라간다""",
    """  sl.oninput = () => { num.value = sl.value; };          // 끄는 동안은 숫자만 따라간다
  sl.addEventListener("pointerup", () => setTimeout(() => sl.blur(), 0));   // 놓으면 포커스 해제(숫자키가 객체 전환으로 가게)""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
