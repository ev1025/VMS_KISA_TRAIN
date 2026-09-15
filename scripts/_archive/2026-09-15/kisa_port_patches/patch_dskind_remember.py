# -*- coding: utf-8 -*-
"""원본 데이터 ↔ 학습 데이터 를 오갈 때 각 쪽에서 마지막으로 고른 항목을 기억한다(첫 항목으로 튀지 않게)."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/data.js"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:90]
    s = s.replace(old, new, 1)
rep("""let DSMETA = null, DS_CUR = null, DS_ONLY_LABELED = false, DS_SEL = null, DS_KIND = "raw", DS_EDIT = false;   // raw=원본, ds=학습""",
    """let DSMETA = null, DS_CUR = null, DS_ONLY_LABELED = false, DS_SEL = null, DS_KIND = "raw", DS_EDIT = false;   // raw=원본, ds=학습
const DS_SEL_BY = { raw: null, ds: null };   // 원본/학습 각각 마지막에 고른 항목""")
rep("""    b.onclick = () => { if (DS_KIND === k) return; DS_KIND = k; DS_SEL = null; buildDatasetSrc(); };""",
    """    b.onclick = () => { if (DS_KIND === k) return; DS_SEL_BY[DS_KIND] = DS_SEL; DS_KIND = k; DS_SEL = DS_SEL_BY[k]; buildDatasetSrc(); };""")
rep("""  sel.value = DS_SEL;
  sel.onchange = () => pickDataSrc(sel.value);""",
    """  sel.value = DS_SEL; DS_SEL_BY[DS_KIND] = DS_SEL;
  sel.onchange = () => { DS_SEL_BY[DS_KIND] = sel.value; pickDataSrc(sel.value); };""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
