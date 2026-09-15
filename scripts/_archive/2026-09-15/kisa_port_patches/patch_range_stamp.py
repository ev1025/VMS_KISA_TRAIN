# -*- coding: utf-8 -*-
"""전파를 누를 때 시작/종료가 비어 있으면 미리보기 첫/끝 프레임으로 '찍어' 넣는다(값이 프레임바에 그대로 남음). 확인창 대신."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:100])
    s = s.replace(old, new, 1)
rep("""    if (SM.a == null || SM.b == null) {               // 구간을 안 정했으면 확인
      const ts0 = SM.seeds.map(q => q.t), lo0 = Math.min.apply(null, ts0), hi0 = Math.max.apply(null, ts0);
      const a0 = SM.a != null ? SM.a : (pvA != null ? Math.min(pvA, lo0) : Math.max(0, lo0 - 5)), b0 = SM.b != null ? SM.b : (pvB != null ? Math.max(pvB, hi0) : Math.min(f.last, hi0 + 10));
      if (!confirm(`시작/종료를 정하지 않았습니다.\\n참조샷 기준 ${_disp(a0)} ~ ${_disp(b0)} 구간으로 전파할까요?`)) return;
    }""",
    """    {                                                 // 시작/종료가 비어 있으면 미리보기 첫/끝 프레임으로 찍어 넣는다(프레임바에 값이 남음)
      const ts0 = SM.seeds.map(q => q.t), lo0 = Math.min.apply(null, ts0), hi0 = Math.max.apply(null, ts0);
      if (SM.a == null) SM.a = pvA != null ? Math.min(pvA, lo0) : Math.max(0, lo0 - 5);
      if (SM.b == null) SM.b = pvB != null ? Math.max(pvB, hi0) : Math.min(f.last, hi0 + 10);
      fillShots();
    }""")
rep("""    const a = SM.a != null ? Math.min(SM.a, lo) : (pvA != null ? Math.min(pvA, lo) : lo - 5), b = SM.b != null ? Math.max(SM.b, hi) : (pvB != null ? Math.max(pvB, hi) : hi + 10);""",
    """    const a = Math.min(SM.a, lo), b = Math.max(SM.b, hi);""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
