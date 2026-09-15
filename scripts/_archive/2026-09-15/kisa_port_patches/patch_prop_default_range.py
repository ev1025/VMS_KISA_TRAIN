# -*- coding: utf-8 -*-
"""전파 시작/종료 기본값 = 미리보기(손라벨 ∪ SAM 프레임)의 첫 프레임 ~ 마지막 프레임. 미리보기가 없으면 참조샷 -5s/+10s."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:90]
    s = s.replace(old, new, 1)
rep("""    if (!SM.seeds.length) return;
    if (SM.a == null || SM.b == null) {               // 구간을 안 정했으면 확인
      const ts0 = SM.seeds.map(q => q.t), lo0 = Math.min.apply(null, ts0), hi0 = Math.max.apply(null, ts0);
      const a0 = SM.a == null ? Math.max(0, lo0 - 5) : SM.a, b0 = SM.b == null ? Math.min(f.last, hi0 + 10) : SM.b;""",
    """    if (!SM.seeds.length) return;
    const pvT = Array.from(new Set([...shotSecs(f.stem).map(([t]) => t), ...samFramesOf(f.clip)])).sort((x, y) => x - y);   // 미리보기 프레임 = 기본 구간
    const pvA = pvT.length ? pvT[0] : null, pvB = pvT.length ? pvT[pvT.length - 1] : null;
    if (SM.a == null || SM.b == null) {               // 구간을 안 정했으면 확인
      const ts0 = SM.seeds.map(q => q.t), lo0 = Math.min.apply(null, ts0), hi0 = Math.max.apply(null, ts0);
      const a0 = SM.a != null ? SM.a : (pvA != null ? Math.min(pvA, lo0) : Math.max(0, lo0 - 5)), b0 = SM.b != null ? SM.b : (pvB != null ? Math.max(pvB, hi0) : Math.min(f.last, hi0 + 10));""")
rep("""    const a = SM.a == null ? lo - 5 : Math.min(SM.a, lo), b = SM.b == null ? hi + 10 : Math.max(SM.b, hi);""",
    """    const a = SM.a != null ? Math.min(SM.a, lo) : (pvA != null ? Math.min(pvA, lo) : lo - 5), b = SM.b != null ? Math.max(SM.b, hi) : (pvB != null ? Math.max(pvB, hi) : hi + 10);""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
