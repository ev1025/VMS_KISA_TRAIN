# -*- coding: utf-8 -*-
"""프레임 바(슬라이더·프레임번호 입력)를 쓴 뒤 포커스가 입력칸에 남아 숫자키가 객체 전환이 아니라 입력으로 먹히던 것 → 값 확정 후 포커스 해제."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:90]
    s = s.replace(old, new, 1)
rep("""  num.onchange = () => openFrameAt(f.clip, _undisp(+num.value));   // 사람은 정수 프레임번호 입력 → 초로 환산""",
    """  num.onchange = () => { num.blur(); openFrameAt(f.clip, _undisp(+num.value)); };   // 사람은 정수 프레임번호 입력 → 초로 환산. 포커스를 풀어 숫자키가 객체 전환으로 가게""")
rep("""  sl.onchange = () => openFrameAt(f.clip, _undisp(+sl.value));    // 놓을 때 그 프레임을 뽑는다""",
    """  sl.onchange = () => { sl.blur(); openFrameAt(f.clip, _undisp(+sl.value)); };    // 놓을 때 그 프레임을 뽑는다. 포커스 해제""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
