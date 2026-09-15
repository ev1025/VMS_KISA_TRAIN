# -*- coding: utf-8 -*-
"""탭 뒤 마스크 응답이 오기 전에 Ctrl+Z 를 누르면: 되돌리기는 점만 지우고, 늦게 온 응답이 박스를 다시 넣던 것.
→ 되돌리기/다시하기가 일어나면 진행 중인 탭 요청 결과를 버린다(세대 번호)."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "_tapGen" not in s
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:100])
    s = s.replace(old, new)
rep("""  const restore = (from, to) => {
    if (!from.length) return;
    const e = from.pop();""",
    """  let _tapGen = 0;                                   // 되돌리기마다 +1 → 그 전에 보낸 탭 요청 결과는 버린다
  const restore = (from, to) => {
    if (!from.length) return;
    _tapGen++;
    const e = from.pop();""")
# samPoint: 요청 전 세대 기록, 응답 후 비교
rep("""    const r = await fetch("/api/sam2_mask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(r => r.json()).catch(() => ({}));
    if (f.t !== t) return;
    if (!r.box) { SMASK = null; draw(); return; }
    SMASK = { box: r.box, poly: r.poly };
    const nb = [samCls(SM.cur), r.box[0], r.box[1], r.box[2], r.box[3]];
    const sd0 = SM.seeds.find(q => Math.abs(q.t - t) < 0.01 && q.obj === SM.cur);
    let idx = (sd0 && sd0.i != null && LB.boxes[sd0.i]) ? sd0.i : ((hit && hit.i >= 0) ? hit.i : -1);""",
    """    const gen = _tapGen;
    const r = await fetch("/api/sam2_mask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(r => r.json()).catch(() => ({}));
    if (f.t !== t || gen !== _tapGen) return;         // 다른 프레임으로 갔거나 그사이 되돌리기 → 결과 버림
    if (!r.box) { SMASK = null; draw(); return; }
    SMASK = { box: r.box, poly: r.poly };
    const nb = [samCls(SM.cur), r.box[0], r.box[1], r.box[2], r.box[3]];
    const sd0 = SM.seeds.find(q => Math.abs(q.t - t) < 0.01 && q.obj === SM.cur);
    let idx = (sd0 && sd0.i != null && LB.boxes[sd0.i]) ? sd0.i : ((hit && hit.i >= 0) ? hit.i : -1);""")
# samRecompute 도 같은 가드
rep("""    draw();
    const r = await fetch("/api/sam2_mask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, t, pts: SP }) }).then(r => r.json()).catch(() => ({}));
    if (f.t !== t) return;""",
    """    draw();
    const gen = _tapGen;
    const r = await fetch("/api/sam2_mask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, t, pts: SP }) }).then(r => r.json()).catch(() => ({}));
    if (f.t !== t || gen !== _tapGen) return;""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
