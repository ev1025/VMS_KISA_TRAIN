# -*- coding: utf-8 -*-
"""원본 데이터 조건필터가 목록보다 늦게 따로 뜨던 것: 조건을 먼저 받아(카테고리별 캐시) 목록과 함께 그린다."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/data.js"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:90])
    s = s.replace(old, new, 1)
rep("""const DS_SEL_BY = { raw: null, ds: null };   // 원본/학습 각각 마지막에 고른 항목""",
    """const DS_SEL_BY = { raw: null, ds: null };   // 원본/학습 각각 마지막에 고른 항목
const CONDS_BY = {};                          // 카테고리 → 촬영조건(한 번 받으면 재사용)""")
rep("""    fetch("/api/clipconds?src=" + encodeURIComponent(cat)).then(x => x.json()).then(cd => {
      CONDS = cd || {}; CLIPFILTER = "";""",
    """    let cd = CONDS_BY[cat];                       // 조건을 먼저 받아 목록과 같이 그린다(늦게 따로 뜨지 않게)
    if (!cd) { try { cd = await (await fetch("/api/clipconds?src=" + encodeURIComponent(cat))).json(); } catch (e) { cd = {}; } CONDS_BY[cat] = cd || {}; }
    {
      CONDS = cd || {}; CLIPFILTER = "";""")
rep("""      draw(); applyCondFilter(box);              // 새 카테고리 조건이 도착했으니 필터를 다시 적용(이전 카테고리 조건으로 숨겨진 항목 복구)
    }).catch(() => {});""",
    """      draw();
    }""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
