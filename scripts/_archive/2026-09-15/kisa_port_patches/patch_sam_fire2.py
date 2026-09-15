# -*- coding: utf-8 -*-
"""화재 클립의 SAM 모드: 객체는 불(1)·연기(2) 두 개로 고정. 숫자키 1/2 만, 추가·삭제 없음.
SAM 박스의 클래스 = 객체 번호-1 (DINO 모드의 불 0 / 연기 1 과 동일). 전파 결과도 같은 규칙으로 클래스 부여."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "FIRE_OBJ" not in s, "이미 적용됨"
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, ("앵커 수 불일치", s.count(old), old[:120])
    s = s.replace(old, new)

rep('''const samCol = o => SAM_COLORS[(o - 1) % SAM_COLORS.length];''',
'''const FIRE_OBJ = { 1: ["불", "#f85149"], 2: ["연기", "#a371f7"] };        // 화재 클립: 객체 = 클래스(불·연기) 고정
const samCol = o => LB.mode === "fire" ? (FIRE_OBJ[o] || FIRE_OBJ[2])[1] : SAM_COLORS[(o - 1) % SAM_COLORS.length];
const samName = o => LB.mode === "fire" ? (FIRE_OBJ[o] || FIRE_OBJ[2])[0] : `객체 ${o}`;
const samCls = o => LB.mode === "fire" ? Math.max(0, Math.min(1, o - 1)) : 0;   // SAM 박스의 클래스''')

# 전파 결과 → 박스 클래스
rep('''  return Object.values(o).map(b => [0, b[0], b[1], b[2], b[3]]);''',
    '''  return Object.entries(o).map(([k, b]) => [samCls(+k), b[0], b[1], b[2], b[3]]);''')

# 화재면 객체 두 개 고정
rep('''  const SM = samState(f.clip);                        // SAM 작업 상태''',
'''  const SM = samState(f.clip);                        // SAM 작업 상태
  if (LB.mode === "fire") { SM.objs = [1, 2]; if (!FIRE_OBJ[SM.cur]) SM.cur = 1; }   // 화재: 불·연기 두 객체 고정''')

# SAM 박스 클래스
rep('''const nb = [curCls, r.box[0], r.box[1], r.box[2], r.box[3]];''',
    '''const nb = [samCls(SM.cur), r.box[0], r.box[1], r.box[2], r.box[3]];''', 2)

# 객체 줄 이름 · 삭제 버튼
rep('''      const tag = el("button", null, `객체 ${o}`);''',
    '''      const tag = el("button", null, samName(o));''')
rep('''      if (SM.objs.length > 1) { const del = el("span", null, "객체 삭제");''',
    '''      if (SM.objs.length > 1 && LB.mode !== "fire") { const del = el("span", null, "객체 삭제");''')

# 숫자키: 화재는 1/2 만
rep('''    if (LAB === "sam" && /^[1-8]$/.test(ev.key)) { const n = +ev.key; if (!SM.objs.includes(n)) { SM.objs.push(n); SM.objs.sort((a, b) => a - b); } SM.cur = n; loadSam(); return; }''',
'''    if (LAB === "sam" && /^[1-8]$/.test(ev.key)) {
      const n = +ev.key;
      if (LB.mode === "fire") { if (n <= 2) { SM.cur = n; loadSam(); } return; }   // 화재: 불(1)·연기(2) 만
      if (!SM.objs.includes(n)) { SM.objs.push(n); SM.objs.sort((a, b) => a - b); } SM.cur = n; loadSam(); return;
    }''')
# 객체 줄 → 미리보기 아래
rep('''  pane.insertBefore(rowAct, wrap); pane.insertBefore(rowObj, rowAct);   // 순서: 객체 → ↶↷ 전파 검수 → 화면 → 프레임바 → 미리보기
  rowObj.style.marginTop = "0"; rowAct.style.margin = "0 0 10px";''',
'''  pane.insertBefore(rowAct, wrap); pane.appendChild(rowObj);   // 순서: ↶↷ 전파 검수 → 화면 → 프레임바 → 미리보기 → 객체
  rowObj.style.marginTop = "10px"; rowAct.style.margin = "0 0 10px";''')
io.open(p, "w", encoding="utf-8").write(s)
print("fire objs ok")
