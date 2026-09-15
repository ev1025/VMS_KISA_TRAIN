# -*- coding: utf-8 -*-
"""목록 배지 = 손라벨 ∪ SAM 전파 프레임(학습데이터 수). 전파 완료 후 참조샷·점·마스크 정리(전파 토글은 유지)."""
import io, re
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/"

def patch(name, pairs):
    p = V + name
    s = io.open(p, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, (name, old[:90])
        s = s.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8").write(s)
    print(name, "ok")

# editor.js : labeledCount 함수 전체를 정규식으로 바꾼다(주석 문구에 의존하지 않게)
p = V + "editor.js"
s = io.open(p, encoding="utf-8").read()
assert "SAMFR" not in s, "이미 적용됨"
m = re.search(r"function labeledCount\(clip\) \{\n(?:.*\n)*?\}\n", s)
assert m, "labeledCount 를 못 찾음"
body = m.group(0)
assert "return Object.keys(by).length;" in body
new_body = body.replace("  return Object.keys(by).length;",
                        "  (SAMFR[clip] || []).forEach(t => { by[Math.round(t * 2) / 2] = 1; });   // SAM 전파 프레임도 학습데이터\n  return Object.keys(by).length;")
s = s.replace(body, "let SAMFR = {};    // stem → SAM 전파 프레임 시각 목록(/api/sam2frames). 목록 배지 = 손라벨 ∪ SAM = 학습데이터 수\n" + new_body, 1)
io.open(p, "w", encoding="utf-8").write(s)

patch("editor.js", [
    ("""    SM.propFrames = Object.keys(frames); styleGo();""",
     """    SM.propFrames = Object.keys(frames); styleGo();
    SAMFR[f.stem] = samFramesOf(f.clip); renderClipList(); if (typeof updateRawBadge === "function") updateRawBadge(f.stem);
    SM.seeds = []; SM.handRef = false; SM.objs = LB.mode === "fire" ? [1, 2] : [1]; SM.cur = 1; SP = []; SMASK = null; styleHand(); drawObjs();   // 참조샷은 전파에 쓰였으니 정리"""),
    ("""      SM.propFrames = []; SM.result = {}; styleGo(); bGo.disabled = false; pstat.innerHTML = "";""",
     """      SM.propFrames = []; SM.result = {}; styleGo(); bGo.disabled = false; pstat.innerHTML = "";
      SAMFR[f.stem] = samFramesOf(f.clip); renderClipList(); if (typeof updateRawBadge === "function") updateRawBadge(f.stem);"""),
])
patch("main.js", [
    ("""  try { PLABELS = await (await fetch("/api/labels?kind=person")).json(); } catch (e) { PLABELS = null; }""",
     """  try { PLABELS = await (await fetch("/api/labels?kind=person")).json(); } catch (e) { PLABELS = null; }
  try { SAMFR = await (await fetch("/api/sam2frames")).json(); } catch (e) { SAMFR = {}; }   // SAM 전파 프레임(목록 배지 합산용)"""),
])
patch("data.js", [
    ("""// 좌측 영상 클릭: 편집 중이면 그 영상 편집 유지, 아니면 재생""",
     r"""// 목록 배지(학습데이터 프레임 수) 한 항목만 다시 그린다 — 전파·삭제 직후
function updateRawBadge(stem) {
  document.querySelectorAll("#list .item").forEach(it => {
    if (!it.dataset.rel || it.dataset.rel.split("/").pop().replace(/\.mp4$/, "") !== stem) return;
    const old = it.querySelector(":scope > span:not(.nm)"); if (old) old.remove();
    const n = labeledCount(stem);
    if (n) { const b = el("span", null, String(n)); b.style.cssText = "flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;min-width:26px;height:18px;padding:0 6px;border-radius:6px;font:700 11px/1 ui-monospace,Menlo,monospace;color:#cfe4ff;background:#58a6ff22;border:1px solid #58a6ff55;margin-right:6px"; it.insertBefore(b, it.firstChild); }
  });
}
// 좌측 영상 클릭: 편집 중이면 그 영상 편집 유지, 아니면 재생"""),
])
