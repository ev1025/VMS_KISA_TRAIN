# -*- coding: utf-8 -*-
"""프레임바 왼쪽에 전파 구간 입력칸: 시작 [   ] 종료 [   ] (프레임 번호 직접 입력, 비우면 자동=미리보기 첫/끝).
값을 바꾸면 SM.a/SM.b 갱신 → 띠 표시. 전파가 구간을 자동으로 찍으면 칸에도 채워진다."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "rangeIn" not in s
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:100])
    s = s.replace(old, new, 1)
rep("""  bar.appendChild(btn("◀◀10", -10, "10칸 뒤로"));""",
    """  {                                                   // 전파 구간 입력칸(비우면 자동 = 미리보기 첫/끝 프레임)
    const SMb = samState(f.clip);
    const mkIn = (label, key) => {
      const lab = el("span", "now", label); lab.style.cssText = "color:var(--mut);font-size:11px;margin-left:2px";
      const inp = el("input"); inp.type = "text"; inp.inputMode = "numeric"; inp.placeholder = "자동";
      inp.style.cssText = "width:48px;align-self:stretch;box-sizing:border-box;background:var(--panel);color:var(--tx);border:1px solid var(--line);border-radius:6px;text-align:center;font:700 12px ui-monospace,Menlo,monospace;padding:0 4px";
      inp.value = SMb[key] == null ? "" : _disp(SMb[key]);
      inp.onchange = () => { const v = inp.value.trim(); SMb[key] = v === "" ? null : _undisp(+v); if (SMb.a != null && SMb.b != null && SMb.a > SMb.b) { const t = SMb.a; SMb.a = SMb.b; SMb.b = t; } inp.blur(); if (ED && ED.fillShots) ED.fillShots(); };
      inp.onkeydown = ev => { if (ev.key === "Enter") { ev.preventDefault(); inp.onchange(); } ev.stopPropagation(); };
      bar.appendChild(lab); bar.appendChild(inp); return inp;
    };
    bar.rangeIn = { a: mkIn("시작", "a"), b: mkIn("종료", "b") };
    bar.rangeIn.b.style.marginRight = "6px";
  }
  bar.appendChild(btn("◀◀10", -10, "10칸 뒤로"));""")
# drawTrack: 입력칸 값 동기화(포커스 중이면 건드리지 않음)
rep("""  const tkr = track.parentElement && track.parentElement.parentElement;   // 시작/종료 표시 갱신
  if (tkr && tkr.rangeA) { tkr.rangeA.textContent = SMt.a == null ? "—" : _disp(SMt.a); tkr.rangeB.textContent = SMt.b == null ? "—" : _disp(SMt.b); }""",
    """  const tkr = track.parentElement && track.parentElement.parentElement;   // 시작/종료 입력칸 동기화
  if (tkr && tkr.rangeIn) { ["a", "b"].forEach(k => { const inp = tkr.rangeIn[k]; if (document.activeElement !== inp) inp.value = SMt[k] == null ? "" : _disp(SMt[k]); }); }""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
