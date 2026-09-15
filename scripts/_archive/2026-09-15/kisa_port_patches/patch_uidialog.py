# -*- coding: utf-8 -*-
"""크롬 기본 confirm/alert 대신 대시보드 스타일 대화상자(uiConfirm/uiAlert). 편집기의 모든 확인·알림에 적용."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "function uiConfirm" not in s
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:100])
    s = s.replace(old, new)

# 대화상자 헬퍼: 파일 맨 위 SESSKEY 선언 앞에
rep("""const SESSKEY = "kisa_last_view";""",
    r"""// 대시보드 스타일 대화상자(크롬 기본 confirm/alert 대신). Enter=확인, Esc=취소
function uiDialog(msg, { ok = "확인", cancel = "취소", danger = false } = {}) {
  return new Promise(resolve => {
    const old = document.getElementById("uiDlg"); if (old) old.remove();
    const wrap = el("div"); wrap.id = "uiDlg";
    wrap.style.cssText = "position:fixed;inset:0;z-index:200;background:#000a;display:flex;align-items:center;justify-content:center";
    const box = el("div");
    box.style.cssText = "background:var(--panel);border:1px solid var(--line);border-radius:12px;min-width:320px;max-width:480px;box-shadow:0 12px 40px #000c;padding:18px 20px 14px";
    const body = el("div"); body.style.cssText = "color:var(--tx);font-size:13px;line-height:1.6;white-space:pre-line"; body.textContent = msg;
    const row = el("div"); row.style.cssText = "display:flex;justify-content:flex-end;gap:8px;margin-top:16px";
    const mk = (t, primary) => { const b = el("button", null, t); b.style.cssText = "width:auto;padding:6px 14px;border-radius:6px;font-weight:700;cursor:pointer;" +
      (primary ? (danger ? "background:#f85149;color:#fff;border:1px solid #f85149" : "background:var(--blue);color:#06090f;border:1px solid var(--blue)") : "background:var(--panel2);color:var(--tx);border:1px solid var(--line)"); return b; };
    const done = v => { wrap.remove(); document.removeEventListener("keydown", onKey, true); resolve(v); };
    const onKey = ev => { if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); done(false); } else if (ev.key === "Enter") { ev.preventDefault(); ev.stopPropagation(); done(true); } else { ev.stopPropagation(); } };
    if (cancel !== null) { const bc = mk(cancel, false); bc.onclick = () => done(false); row.appendChild(bc); }
    const bo = mk(ok, true); bo.onclick = () => done(true); row.appendChild(bo);
    box.appendChild(body); box.appendChild(row); wrap.appendChild(box);
    wrap.onclick = ev => { if (ev.target === wrap && cancel !== null) done(false); };
    document.body.appendChild(wrap); document.addEventListener("keydown", onKey, true); bo.focus();
  });
}
const uiConfirm = (msg, opt) => uiDialog(msg, Object.assign({ ok: "확인", cancel: "취소" }, opt || {}));
const uiAlert = msg => uiDialog(msg, { ok: "닫기", cancel: null });
const SESSKEY = "kisa_last_view";""")

rep("""    if (!confirm(`이 클립의 학습 프레임을 초기화합니다.""",
    """    if (!await uiConfirm(`이 클립의 학습 프레임을 초기화합니다.""")
rep("""참조샷 ${SM.seeds.length}개가 지워집니다(손라벨은 백업됨). 계속할까요?`)) return;""",
    """참조샷 ${SM.seeds.length}개가 지워집니다(손라벨은 백업됨). 계속할까요?`, { ok: "초기화", danger: true })) return;""")
rep("""    } catch (e) { alert("초기화 실패: " + e.message); }""",
    """    } catch (e) { await uiAlert("초기화 실패: " + e.message); }""")
rep("""        if (!confirm(`객체 ${o}의 참조샷 ${mine.length}개와 그 박스를 지웁니다. 계속할까요?`)) return;""",
    """        if (!await uiConfirm(`객체 ${o}의 참조샷 ${mine.length}개와 그 박스를 지웁니다. 계속할까요?`, { ok: "삭제", danger: true })) return;""")
rep("""      if (!confirm(`${_disp(d.t)} 프레임의 SAM 결과를 지웁니다. 계속할까요?`)) return;""",
    """      if (!await uiConfirm(`${_disp(d.t)} 프레임의 SAM 결과를 지웁니다. 계속할까요?`, { ok: "삭제", danger: true })) return;""")
rep("""    if (!confirm("이 객체를 클립 전체에서 뺍니다(같은 자리에 겹치는 박스 전부). 계속할까요?")) return;""",
    """    if (!await uiConfirm("이 객체를 클립 전체에서 뺍니다(같은 자리에 겹치는 박스 전부). 계속할까요?", { ok: "제거", danger: true })) return;""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
