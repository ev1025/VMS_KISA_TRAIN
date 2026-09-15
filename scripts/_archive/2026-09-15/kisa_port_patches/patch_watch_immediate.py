# -*- coding: utf-8 -*-
"""편집기를 그린 직후 전파 버튼을 잠깐 잠그고, 진행 중 작업 조회가 끝난 뒤에 상태를 정한다(돌아와서 첫 폴링 전 0.8초 동안 눌러 중복 작업이 생기던 것)."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:90]
    s = s.replace(old, new, 1)
rep("""    _watching = false;
    if (!seen) return;                                // 작업이 없었다 → 아무것도 안 바꾼다""",
    """    _watching = false;
    if (!seen) { if (ED && ED._tok === MY) drawObjs(); return; }   // 작업이 없었다 → 버튼 상태만 원래대로""")
rep("""  watchJob();                                         // 이 클립에 진행 중인 전파가 있으면 이어서 보여준다""",
    """  bGo.disabled = true;                                // 진행 중 작업 조회가 끝날 때까지 잠깐 잠금(중복 전파 방지)
  watchJob();                                         // 이 클립에 진행 중인 전파가 있으면 이어서 보여준다""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
