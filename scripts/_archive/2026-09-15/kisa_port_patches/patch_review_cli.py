# -*- coding: utf-8 -*-
"""리뷰 결함 수정(클라이언트)
1) SAM 모드에서 리사이즈 뒤 sel 이 남아 1/2 키가 객체 전환 대신 클래스 변경으로 새는 것
2) 검수 확대창의 박스 클릭이 SAM 프레임인데 DINO API 를 부르는 것 → SAM 프레임 삭제로
3) 재렌더 뒤 옛 watchJob/refreshSam 클로저가 새 화면을 덮는 것 → 인스턴스 토큰으로 가드
4) 되돌리기로 빈 라벨을 복원한 직후 비동기 프리필이 덮는 것 → LB.src==="hand" 면 프리필 안 얹음
5) mouseleave 로 리사이즈가 끝나면 _resized 가 남아 다음 클릭을 먹는 것 → mousedown 에서 초기화"""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "ED._tok" not in s, "이미 적용됨"
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:100])
    s = s.replace(old, new)

# 1) 1/2 클래스 변경은 DINO 모드에서만. 리사이즈 끝나면 sel 해제(SAM)
rep("""    if ((ev.key === "1" || ev.key === "2") && LB.mode !== "person" && sel !== null && LB.boxes[sel]) {   // 1=불 2=연기 (선택 박스)""",
    """    if (LAB !== "sam" && (ev.key === "1" || ev.key === "2") && LB.mode !== "person" && sel !== null && LB.boxes[sel]) {   // DINO 모드: 1=불 2=연기 (선택 박스)""")
rep("""    if (rz) { const i = rz.i; rz = null; _resized = true; if (LAB === "sam") seedFromBox(i); draw(); saveNow(); return; }""",
    """    if (rz) { const i = rz.i; rz = null; _resized = true; if (LAB === "sam") { seedFromBox(i); sel = null; } draw(); saveNow(); return; }""")

# 5) mousedown 시작 시 _resized 초기화
rep("""  ov.onmousedown = ev => {
    ev.preventDefault();
    if (_space) { pan = { sx: ev.clientX, sy: ev.clientY, tx0: _tx, ty0: _ty }; ov.style.cursor = "grabbing"; return; }   // 스페이스+드래그 = 확대이미지 이동""",
    """  ov.onmousedown = ev => {
    ev.preventDefault(); _resized = false;
    if (_space) { pan = { sx: ev.clientX, sy: ev.clientY, tx0: _tx, ty0: _ty }; ov.style.cursor = "grabbing"; return; }   // 스페이스+드래그 = 확대이미지 이동""")

# 4) 프리필 가드
rep("""      if (LB.sec !== sec || LB.boxes.length || f.saved) return;
      LB.boxes = boxes.map(b => b.slice()); LB.src = src || "dino"; draw();""",
    """      if (LB.sec !== sec || LB.boxes.length || f.saved || LB.src === "hand") return;   // 손라벨(빈 라벨 포함)로 확정된 프레임엔 안 얹는다
      LB.boxes = boxes.map(b => b.slice()); LB.src = src || "dino"; draw();""")

# 3) 인스턴스 토큰
rep("""function renderEditor(f) {
  LB.file = f.file;""",
    """function renderEditor(f) {
  const MY = {};                                      // 이 편집기 인스턴스 표식(재렌더 뒤 옛 클로저가 화면을 건드리지 않게)
  LB.file = f.file;""")
rep("""    loadSam,
    syncSam: () => {""",
    """    loadSam, _tok: MY,
    syncSam: () => {""")
rep("""    if (!(ED && ED.clip === f.clip)) return;
    styleGo(); fillShots();""",
    """    if (!(ED && ED._tok === MY)) return;              // 다른 인스턴스가 화면을 맡고 있으면 여기서 끝(저장소·배지는 위에서 이미 갱신)
    styleGo(); fillShots();""")
rep("""    while (true) {
      const jobs = await fetch(`/api/sam2_jobs?clip=${encodeURIComponent(f.clip)}`).then(r => r.json()).catch(() => []);""",
    """    while (true) {
      if (ED && ED._tok !== MY) { _watching = false; return; }   // 편집기가 새로 그려졌으면 이 감시는 끝(새 편집기가 이어받는다)
      const jobs = await fetch(`/api/sam2_jobs?clip=${encodeURIComponent(f.clip)}`).then(r => r.json()).catch(() => []);""")
rep("""      if (ED && ED.clip === f.clip) { rowObj.style.pointerEvents = "none";""",
    """      if (ED && ED._tok === MY) { rowObj.style.pointerEvents = "none";""")
rep("""    if (ED && ED.clip === f.clip) { rowObj.style.pointerEvents = ""; rowObj.style.opacity = ""; bHand.disabled = false;""",
    """    if (ED && ED._tok === MY) { rowObj.style.pointerEvents = ""; rowObj.style.opacity = ""; bHand.disabled = false;""")
rep("""    if (!seen.err) { SM.seeds = []; SM.handRef = false; SM.objs = LB.mode === "fire" ? [1, 2] : [1]; SM.cur = 1; if (ED && ED.clip === f.clip) { SP = []; SMASK = null; styleHand(); drawObjs(); } }""",
    """    if (!seen.err) { SM.seeds = []; SM.handRef = false; SM.objs = LB.mode === "fire" ? [1, 2] : [1]; SM.cur = 1; if (ED && ED._tok === MY) { SP = []; SMASK = null; styleHand(); drawObjs(); } }""")

# 2) 검수 확대창: SAM 프레임은 박스 클릭 = 그 프레임 SAM 결과 삭제
rep("""  holder.onclick = async ev => {
    const d = items[idx];
    if (!d || !d.boxes.length) return;          // 손라벨이어도 지울 수 있다(사용자가 직접 누른 것)
    const rc = im.getBoundingClientRect();
    const px = (ev.clientX - rc.left) / rc.width, py = (ev.clientY - rc.top) / rc.height;
    const b = d.boxes.find(q => px >= q[1] && px <= q[1] + q[3] && py >= q[2] && py <= q[2] + q[4]);
    if (!b) return;
    if (!confirm(""",
    """  holder.onclick = async ev => {
    const d = items[idx];
    if (!d || !d.boxes.length) return;          // 손라벨이어도 지울 수 있다(사용자가 직접 누른 것)
    const rc = im.getBoundingClientRect();
    const px = (ev.clientX - rc.left) / rc.width, py = (ev.clientY - rc.top) / rc.height;
    const b = d.boxes.find(q => px >= q[1] && px <= q[1] + q[3] && py >= q[2] && py <= q[2] + q[4]);
    if (!b) return;
    if (d.src === "sam") {                      // SAM 결과: 이 프레임의 SAM 박스를 저장소에서 뺀다(격자 × 와 같은 동작)
      if (!confirm(`${_disp(d.t)} 프레임의 SAM 결과를 지웁니다. 계속할까요?`)) return;
      cap.textContent = "제거 중…";
      try {
        await fetch("/api/sam2_drop", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, t: d.t }) });
        if (SAMMAP[f.clip]) delete SAMMAP[f.clip][d.t.toFixed(1)]; SAML[f.clip] = Promise.resolve(SAMMAP[f.clip] || {});
        SAMFR[f.stem] = samFramesOf(f.clip); if (typeof updateRawBadge === "function") updateRawBadge(f.stem);
        items.splice(idx, 1);
        if (typeof refillGrid === "function") refillGrid();
        if (ED && ED.syncSam) ED.syncSam(); if (ED && ED.fillShots) ED.fillShots();
        if (!items.length) { done(); return; }
        show(Math.min(idx, items.length - 1));
      } catch (e) { cap.textContent = "제거 실패"; }
      return;
    }
    if (!confirm(""")
io.open(p, "w", encoding="utf-8").write(s)
print("editor.js: 리뷰 수정 5건")
