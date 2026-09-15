# -*- coding: utf-8 -*-
"""클립을 열 때 SAM 저장소를 새로 읽어(캐시 무효화) 전파 토글·라벨 검수·훈련 데이터 문구·배지를 맞춘다.
(다른 클립에 가 있는 동안 서버 큐가 전파를 끝낸 경우 돌아오면 바로 반영)"""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "syncSam" not in s
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:90])
    s = s.replace(old, new)
rep("""  LB.mode = mode || LB.mode || "fire";
  if (LB.mode === "person" && !PLABELS)""",
"""  LB.mode = mode || LB.mode || "fire";
  if (!ED || ED.clip !== clip) delete SAML[clip];          // 클립을 새로 열면 SAM 저장소를 다시 읽는다(서버 큐가 그사이 저장했을 수 있다)
  if (LB.mode === "person" && !PLABELS)""")
rep("""    if (!wantPseudo) { Promise.all([samLabels(clip), autoLabels(clip)]).then(([sam, dino]) => { SAMMAP[clip] = sam; DINOMAP[clip] = dino; if (ED && ED.clip === clip) { if (ED.fillShots) ED.fillShots(); if (ED.loadSam) ED.loadSam(); } }); return; }""",
"""    if (!wantPseudo) { Promise.all([samLabels(clip), autoLabels(clip)]).then(([sam, dino]) => { SAMMAP[clip] = sam; DINOMAP[clip] = dino; if (ED && ED.clip === clip) { if (ED.syncSam) ED.syncSam(); if (ED.fillShots) ED.fillShots(); if (ED.loadSam) ED.loadSam(); } }); return; }""")
rep("""      if (bx.length) ED.setPseudo(sec, bx, src);
      if (ED.fillShots) ED.fillShots(); if (ED.loadSam) ED.loadSam();""",
"""      if (bx.length) ED.setPseudo(sec, bx, src);
      if (ED.syncSam) ED.syncSam(); if (ED.fillShots) ED.fillShots(); if (ED.loadSam) ED.loadSam();""")
rep("""    loadSam,
    applyFrame: (sec, url, saved) => {""",
"""    loadSam,
    syncSam: () => {                                   // 저장소 기준으로 전파 토글·검수 버튼·문구·배지 맞춤
      SAMFR[f.stem] = samFramesOf(f.clip); SM.propFrames = SAMFR[f.stem].map(t => Number(t).toFixed(1));
      styleGo(); updateTStat(); if (typeof updateRawBadge === "function") updateRawBadge(f.stem);
    },
    applyFrame: (sec, url, saved) => {""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
