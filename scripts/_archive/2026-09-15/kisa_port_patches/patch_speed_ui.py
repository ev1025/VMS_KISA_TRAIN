# -*- coding: utf-8 -*-
"""SAM 모드 프레임 이동·라벨 검수 속도
1) persistSam: 마스크 폴리곤은 저장 안 함 + 300ms 디바운스 (프레임마다 수십 KB 를 localStorage 에 쓰던 것)
2) renderShotRow: 미리보기 구성(프레임 목록)이 같으면 썸네일을 다시 만들지 않고 강조·스크롤만 갱신 (프레임마다 100+ 썸네일 재생성)
3) 라벨 검수 격자: 처음 24장만 기다리고 나머지 프레임 캐시는 뒤에서 (격자가 뜨기까지 수십 초 걸리던 것)"""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:90])
    s = s.replace(old, new, 1)

# 1) persistSam 디바운스·폴리곤 제외
rep("""function persistSam(clip) {                           // 참조샷·객체·구간·손라벨참조 토글만 남긴다(결과는 서버 저장소에 있다)
  const st = SAMST[clip]; if (!st) return;
  try { localStorage.setItem("kisa_sam_" + clip.split("/").pop(), JSON.stringify({ seeds: st.seeds, objs: st.objs, cur: st.cur, a: st.a, b: st.b, handRef: !!st.handRef })); } catch (e) {}
}""",
"""const _PERSIST_T = {};
function persistSam(clip) {                           // 참조샷·객체·구간·손라벨참조 토글만 남긴다(결과는 서버 저장소에 있다). 300ms 디바운스
  clearTimeout(_PERSIST_T[clip]);
  _PERSIST_T[clip] = setTimeout(() => {
    const st = SAMST[clip]; if (!st) return;
    const seeds = st.seeds.map(q => ({ t: q.t, obj: q.obj, box: q.box, pts: q.pts || [], i: q.i, fromHand: !!q.fromHand }));   // 폴리곤은 크고 다시 계산되니 제외
    try { localStorage.setItem("kisa_sam_" + clip.split("/").pop(), JSON.stringify({ seeds, objs: st.objs, cur: st.cur, a: st.a, b: st.b, handRef: !!st.handRef })); } catch (e) {}
  }, 300);
}""")

# 2) renderShotRow: 구성이 같으면 강조만
rep("""function renderShotRow(row, f, hooks) {
  row.innerHTML = "";
  row.style.cssText = "display:flex;gap:8px;overflow-x:auto;padding:12px 2px;align-items:center;min-height:114px";   // 빈 상태도 높이 예약(박스 그릴 때 안 튀게)""",
"""function renderShotRow(row, f, hooks) {
  {                                                   // 구성(프레임 목록·출처)이 그대로면 썸네일을 다시 만들지 않고 강조·스크롤만 갱신
    const handS0 = shotSecs(f.stem), hset0 = new Set(handS0.map(([t]) => t));
    const key = f.clip + "|" + handS0.map(([t, n]) => t + ":" + n).join(",") + "|" + samFramesOf(f.clip).filter(t => !hset0.has(t)).join(",");
    if (row.dataset.key === key && row.children.length) {
      [...row.children].forEach(b => { const on = +b.dataset.t === f.t; b.style.outline = on ? "2px solid var(--blue)" : ""; b.style.border = on ? "0" : (b.dataset.src === "sam" ? "1px solid #e8913a88" : "1px solid var(--line)"); });
      const near = [...row.children].sort((a, b) => Math.abs(+a.dataset.t - f.t) - Math.abs(+b.dataset.t - f.t))[0];
      if (near) requestAnimationFrame(() => { row.scrollLeft = near.offsetLeft - row.offsetLeft - row.clientWidth / 2 + near.offsetWidth / 2; });
      return;
    }
    row.dataset.key = key;
  }
  row.innerHTML = "";
  row.style.cssText = "display:flex;gap:8px;overflow-x:auto;padding:12px 2px;align-items:center;min-height:114px";   // 빈 상태도 높이 예약(박스 그릴 때 안 튀게)""")
rep("""    b.appendChild(x);
    b.dataset.t = s;
    row.appendChild(b);""",
"""    b.appendChild(x);
    b.dataset.t = s; b.dataset.src = src;
    row.appendChild(b);""")

# 3) 검수 격자: 앞 24장만 기다림
rep("""  const tsAll = items.map(d => d.t).join(",");
  try { await fetch("/api/warmframes?w=320&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsAll); } catch (e) {}
  fetch("/api/warmframes?w=0&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsAll);""",
"""  const tsFirst = items.slice(0, 24).map(d => d.t).join(","), tsRest = items.slice(24).map(d => d.t).join(",");
  try { await fetch("/api/warmframes?w=320&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsFirst); } catch (e) {}   // 처음 보이는 장만 기다린다
  if (tsRest) fetch("/api/warmframes?w=320&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsRest).catch(() => {});   // 나머지는 뒤에서
  fetch("/api/warmframes?w=0&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsFirst).catch(() => {});""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
