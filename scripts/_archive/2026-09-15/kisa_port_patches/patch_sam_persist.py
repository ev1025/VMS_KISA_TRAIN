# -*- coding: utf-8 -*-
"""SAM 작업 상태(참조샷·객체·시작/종료·손라벨참조 토글)를 클립별로 브라우저(localStorage)에 남긴다.
새로고침·다른 화면 다녀와도 참조샷이 유지된다. 전파가 끝나면(설계대로) 비운 상태가 저장된다."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "persistSam" not in s
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:90]
    s = s.replace(old, new, 1)
rep("""function samState(clip) { return SAMST[clip] || (SAMST[clip] = { seeds: [], objs: [1], cur: 1, result: {}, a: null, b: null }); }""",
    """function samState(clip) {
  if (SAMST[clip]) return SAMST[clip];
  let st = null;
  try { const raw = localStorage.getItem("kisa_sam_" + clip.split("/").pop()); if (raw) st = JSON.parse(raw); } catch (e) { st = null; }   // 브라우저에 남긴 참조샷 복원
  st = Object.assign({ seeds: [], objs: [1], cur: 1, result: {}, a: null, b: null }, st || {});
  st.result = {}; st.propFrames = [];                 // 저장소 기준으로 다시 맞춘다(syncSam)
  return (SAMST[clip] = st);
}
function persistSam(clip) {                           // 참조샷·객체·구간·손라벨참조 토글만 남긴다(결과는 서버 저장소에 있다)
  const st = SAMST[clip]; if (!st) return;
  try { localStorage.setItem("kisa_sam_" + clip.split("/").pop(), JSON.stringify({ seeds: st.seeds, objs: st.objs, cur: st.cur, a: st.a, b: st.b, handRef: !!st.handRef })); } catch (e) {}
}""")
# 객체 줄 갱신 = 참조샷 변화 지점 → 저장. 시작/종료는 fillShots 에서.
rep("""  function drawObjs() {
    rowObj.innerHTML = "";""",
    """  function drawObjs() {
    persistSam(f.clip);
    rowObj.innerHTML = "";""")
rep("""  const fillShots = () => (drawTrack(bar.tk, f), updateTStat(), renderShotRow(shots, f, {""",
    """  const fillShots = () => (persistSam(f.clip), drawTrack(bar.tk, f), updateTStat(), renderShotRow(shots, f, {""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
