# -*- coding: utf-8 -*-
"""화면 순서: SAM/DINO → 객체 → ↶↷ 전파 검수 → 화면 → 프레임바 → 미리보기(학습데이터, 프레임번호만).
DINO 모드 = 전부 초록 실선. SAM 모드 = 손 파랑 · SAM 주황 · DINO 초록 점선."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "pane.insertBefore(rowAct, wrap)" not in s, "이미 적용됨"
def rep(old, new):
    global s
    assert old in s, "앵커 없음:\n" + old[:140]
    s = s.replace(old, new, 1)

rep('''  const shots = el("div");
  pane.appendChild(shots);
  bRev.onclick = () => openAutoReview(f, null);''',
'''  const shots = el("div");
  pane.appendChild(shots);
  pane.insertBefore(rowAct, wrap); pane.insertBefore(rowObj, rowAct);   // 순서: 객체 → ↶↷ 전파 검수 → 화면 → 프레임바 → 미리보기
  rowObj.style.marginTop = "0"; rowAct.style.margin = "0 0 10px";
  bRev.onclick = () => openAutoReview(f, null);''')

rep('''    const col = (LB.mode === "person") ? SRC_COLOR[LB.src || "none"] : null;   // 사람: 손라벨 파랑 · SAM 주황 · DINO 초록
    LB.boxes.forEach((b, i) => { s += rectSvg(b[1] * f.W, b[2] * f.H, b[3] * f.W, b[4] * f.H, b[0], LB.src === "dino" && LAB === "dino", false, col); });
    if (LAB === "sam") {
      const dm = DINOMAP[f.clip] || {};
      autoBoxesAt(dm, f.t).forEach(b => { s += rectSvg(b[1] * f.W, b[2] * f.H, b[3] * f.W, b[4] * f.H, 0, true, false, "#3fb950"); });   // DINO 후보(점선)''',
'''    const col = (LB.mode === "person" && LAB === "sam") ? SRC_COLOR[LB.src || "none"] : null;   // SAM: 손 파랑 · SAM 주황 · DINO 초록 / DINO 모드: 전부 초록 실선
    LB.boxes.forEach((b, i) => { s += rectSvg(b[1] * f.W, b[2] * f.H, b[3] * f.W, b[4] * f.H, b[0], LAB === "sam" && LB.src === "dino", false, col); });
    if (LAB === "sam") {
      const dm = DINOMAP[f.clip] || {};
      if (LB.src !== "dino") autoBoxesAt(dm, f.t).forEach(b => { s += rectSvg(b[1] * f.W, b[2] * f.H, b[3] * f.W, b[4] * f.H, 0, true, false, "#3fb950"); });   // DINO 후보(점선)''')

# 미리보기 = 학습데이터(손·SAM). 캡션은 프레임 번호만
rep('''    b.title = `${s}초 · 박스 ${n}개 · ${src === "hand" ? "손라벨" : "SAM"}`;''',
    '''    b.title = _disp(s);''')
rep('''    const cap = el("span", null, `${_disp(s)}<span style="opacity:.7;font-weight:600"> ${n}</span>`);
    cap.style.cssText = `position:absolute;left:0;bottom:0;background:#0b0e13cc;color:${src === "sam" ? "#e8913a" : "var(--tx)"};font-size:10px;font-weight:700;padding:1px 5px;border-top-right-radius:5px;line-height:1.4`;''',
'''    const cap = el("span", null, _disp(s));
    cap.style.cssText = "position:absolute;left:0;bottom:0;background:#0b0e13cc;color:var(--tx);font-size:10px;font-weight:700;padding:1px 5px;border-top-right-radius:5px;line-height:1.4";''')
io.open(p, "w", encoding="utf-8").write(s)
print("layout ok")
