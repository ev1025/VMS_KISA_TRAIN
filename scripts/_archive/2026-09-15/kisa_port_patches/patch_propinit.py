# -*- coding: utf-8 -*-
"""전파 토글 상태를 저장소에서 복원: 클립을 열 때 SAM 저장소에 프레임이 있으면 [전파]가 켜진 상태(파란색)로 보이고,
누르면 그 클립의 SAM 결과를 전부 지운다. (새로고침 뒤에도 해제 가능)"""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
old = """  if (LB.mode === "fire") { SM.objs = [1, 2]; if (!FIRE_OBJ[SM.cur]) SM.cur = 1; }   // 화재: 불·연기 두 객체 고정"""
new = old + """
  if (!(SM.propFrames && SM.propFrames.length) && (SAMFR[f.stem] || []).length) SM.propFrames = SAMFR[f.stem].map(t => Number(t).toFixed(1));   // 저장소에 SAM 결과가 있으면 전파 토글 켜진 상태로 복원"""
assert s.count(old) == 1
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
