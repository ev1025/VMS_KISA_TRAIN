# -*- coding: utf-8 -*-
"""1) 원본 데이터 목록의 조건필터 줄을 스크롤 상단에 고정
2) SAM 객체 줄: 참조샷이 하나도 없으면 비움(탭했거나 객체가 있을 때만 '객체 1' 표시)
3) SAM 탭 저장: DINO 뿐 아니라 SAM 저장소 프리필도 객체가 잡은 박스만 손라벨로
4) SAM2 실험실 제거: 헤더 링크·/sam2 라우트 (편집기의 SAM API 는 그대로)"""
import io, re
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/"
def patch(name, pairs):
    p = V + name; s = io.open(p, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, (name, s.count(old), old[:90])
        s = s.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8").write(s); print(name, "ok")

# 1) 필터 줄 고정 (.list 는 overflow-y:auto, padding 6px)
patch("js/data.js", [
    ("""        cf.innerHTML = ""; cf.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;margin:0 0 6px";""",
     """        cf.innerHTML = ""; cf.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;position:sticky;top:-6px;z-index:2;background:var(--bg,#0d1117);margin:-6px -6px 6px;padding:8px 6px 6px;border-bottom:1px solid var(--line)";   // 목록 스크롤 상단에 고정"""),
])

patch("js/editor.js", [
    # 2) 참조샷 없으면 객체 줄 비움
    ("""  function drawObjs() {
    rowObj.innerHTML = "";
    if (LAB !== "sam") return;""",
     """  function drawObjs() {
    rowObj.innerHTML = "";
    if (LAB !== "sam") return;
    if (!SM.seeds.length) { bGo.disabled = !(SM.propFrames && SM.propFrames.length); return; }   // 탭하기 전엔 객체 줄을 비워 둔다"""),
    # 3) 프리필(DINO·SAM) 은 객체가 잡은 박스만 손라벨로
    ("""  const dropUnownedPrefill = () => {               // DINO 프리필 프레임에서 탭했으면 객체가 잡은 박스만 남긴다(나머지 프리필은 손라벨로 안 넘김)
    if (LB.src !== "dino") return;""",
     """  const dropUnownedPrefill = () => {               // 프리필(DINO·SAM 저장소) 프레임에서 탭했으면 객체가 잡은 박스만 남긴다(나머지는 손라벨로 안 넘김)
    if (LB.src !== "dino" && LB.src !== "sam") return;"""),
    ("""    if (LAB === "sam" && LB.src === "dino") dropUnownedPrefill();   // SAM: DINO 프리필은 손라벨로 안 넘김(객체가 잡은 박스만)""",
     """    if (LAB === "sam" && (LB.src === "dino" || LB.src === "sam")) dropUnownedPrefill();   // SAM: 프리필은 손라벨로 안 넘김(객체가 잡은 박스만)"""),
])

# 4) SAM2 실험실 제거
patch("dashboard.html", [
    (""" <a href="/sam2" style="margin-left:10px;color:#58a6ff;font-size:12px;text-decoration:none;font-weight:700">SAM2 실험실</a>""", ""),
])
p = V + "serve_kisa.py"; s = io.open(p, encoding="utf-8").read()
m = re.search(r'        if p in \("/sam2", "/sam2\.html"\):.*?\n(?=        if p == )', s, re.S)
assert m, "/sam2 라우트 못 찾음"
s = s[:m.start()] + s[m.end():]
io.open(p, "w", encoding="utf-8").write(s); print("serve_kisa.py: /sam2 라우트 제거")
