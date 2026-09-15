# -*- coding: utf-8 -*-
"""SAM 모드의 모든 저장 경로(탭·크기조절·Del·되돌리기)에서 DINO 프리필 박스는 손라벨로 넘기지 않는다.
saveNow 진입 시 LB.src === "dino" 면 객체(참조샷)가 잡은 박스만 남긴다. DINO 모드는 설계대로(수정하면 프레임 전체 승격) 유지."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
old = """  const saveNow = async () => {
    try {
      const res = await postLabel(f.stem, f.t, f.W, f.H, LB.boxes, f.src);"""
new = """  const saveNow = async () => {
    if (LAB === "sam" && LB.src === "dino") dropUnownedPrefill();   // SAM: DINO 프리필은 손라벨로 안 넘김(객체가 잡은 박스만)
    try {
      const res = await postLabel(f.stem, f.t, f.W, f.H, LB.boxes, f.src);"""
assert s.count(old) == 1, "saveNow 앵커 없음"
s = s.replace(old, new, 1)
# 크기조절 끝: 참조샷 갱신을 저장보다 먼저(그 박스가 '객체가 잡은 박스'가 되게)
old2 = """    if (rz) { const i = rz.i; rz = null; _resized = true; draw(); saveNow(); if (LAB === "sam") seedFromBox(i); return; }      // 크기조절 끝 → 저장(SAM: 참조샷도 갱신)"""
new2 = """    if (rz) { const i = rz.i; rz = null; _resized = true; if (LAB === "sam") seedFromBox(i); draw(); saveNow(); return; }      // 크기조절 끝 → (SAM: 참조샷 갱신 후) 저장"""
assert s.count(old2) == 1, "finish 앵커 없음"
s = s.replace(old2, new2, 1)
# 전파 진행 중: 객체 줄(참조샷·객체 삭제)과 손라벨 참조를 잠근다
old3 = """      if (ED && ED.clip === f.clip) { bGo.disabled = true; pstat.innerHTML = act.state === "queued" ?"""
new3 = """      if (ED && ED.clip === f.clip) { rowObj.style.pointerEvents = "none"; rowObj.style.opacity = "0.5"; bHand.disabled = true; bHand.style.opacity = "0.4"; bGo.disabled = true; pstat.innerHTML = act.state === "queued" ?"""
assert s.count(old3) == 1, "watch 진행 앵커 없음"
s = s.replace(old3, new3, 1)
old4 = """    if (ED && ED.clip === f.clip) { bGo.disabled = false; pstat.innerHTML = seen.err ? '<b style="color:#f85149">실패</b>' : ""; }"""
new4 = """    if (ED && ED.clip === f.clip) { rowObj.style.pointerEvents = ""; rowObj.style.opacity = ""; bHand.disabled = false; bHand.style.opacity = ""; bGo.disabled = false; pstat.innerHTML = seen.err ? '<b style="color:#f85149">실패</b>' : ""; }"""
assert s.count(old4) == 1, "watch 종료 앵커 없음"
s = s.replace(old4, new4, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
