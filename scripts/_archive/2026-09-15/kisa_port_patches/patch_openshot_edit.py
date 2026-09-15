# -*- coding: utf-8 -*-
"""라벨 검수 확대창을 편집 가능하게: 박스 변 드래그=크기, 안쪽 드래그=이동, Del=마우스 아래 박스 삭제, [프레임 삭제] 버튼.
고친 프레임은 손라벨로 승격(전 박스 저장) 후 SAM 저장소에서 빼서 중복을 없앤다. ←/→ 이동, Esc 닫기, 우클릭 = 그 프레임 편집기로."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
i = s.index("function openShot(f, items, idx) {")
j = s.index("// ---------- 라벨 검수(한 화면)")
assert 0 < i < j
new = r'''function openShot(f, items, idx) {
  const old = document.getElementById("shotView"); if (old) old.remove();
  const v = el("div"); v.id = "shotView";
  v.style.cssText = "position:fixed;inset:0;z-index:90;background:#000d;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px";
  const holder = el("div");
  holder.style.cssText = "position:relative;max-width:94vw;max-height:80vh;line-height:0";
  const im = el("img");
  im.style.cssText = "display:block;max-width:94vw;max-height:80vh;width:auto;height:auto;-webkit-user-drag:none;user-select:none";
  const ovl = el("div"); ovl.style.cssText = "position:absolute;inset:0;cursor:default";
  holder.appendChild(im); holder.appendChild(ovl);
  const cap = el("div"); cap.style.cssText = "color:var(--tx);font-size:12px;font-weight:700";
  const row = el("div"); row.style.cssText = "display:flex;gap:8px;align-items:center";
  const mk = (t, danger) => { const b = el("button", null, t); b.style.cssText = "width:auto;padding:5px 12px;border-radius:6px;font-weight:700;cursor:pointer;background:var(--panel2);color:" + (danger ? "#f85149" : "var(--tx)") + ";border:1px solid " + (danger ? "#f8514966" : "var(--line)"); return b; };
  const bDel = mk("프레임 삭제", true), bClose = mk("닫기", false);
  const hint = el("span", null, "박스 변 드래그 = 크기 · 안쪽 드래그 = 이동 · Del = 박스 삭제 · ←/→ 이동 · 우클릭 = 편집기로"); hint.style.cssText = "color:var(--mut);font-size:11px;margin-left:8px";
  row.appendChild(bDel); row.appendChild(bClose); row.appendChild(hint);
  let boxes = [], busy = false, lastP = null;
  const cur = () => items[idx];
  const norm = ev => { const rc = im.getBoundingClientRect(); return { x: (ev.clientX - rc.left) / rc.width, y: (ev.clientY - rc.top) / rc.height, tx: 8 / rc.width, ty: 8 / rc.height }; };
  const render = () => {
    const d = cur();
    const col = SRC_COLOR[d.src] || "#3fb950";
    ovl.innerHTML = "<svg viewBox=\"0 0 " + f.W + " " + f.H + "\" preserveAspectRatio=\"none\" style=\"position:absolute;inset:0;width:100%;height:100%\">" +
      boxes.map(b => "<rect x=\"" + (b[1] * f.W) + "\" y=\"" + (b[2] * f.H) + "\" width=\"" + (b[3] * f.W) + "\" height=\"" + (b[4] * f.H) + "\" fill=\"none\" stroke=\"" + col + "\" stroke-width=\"2\"/>").join("") + "</svg>";
    cap.innerHTML = `${_disp(d.t)} · ${boxes.length}개 <span style="color:${col}">${d.src === "hand" ? "손라벨" : (d.src || "").toUpperCase()}</span>`;
  };
  const show = i => {
    idx = Math.min(Math.max(i, 0), items.length - 1);
    const d = cur();
    im.src = "/frameat?clip=" + encodeURIComponent(f.clip) + "&t=" + d.t;
    boxes = (d.boxes || []).map(b => b.slice());
    render();
  };
  // 고친 프레임 = 손라벨로 승격(전 박스 저장), SAM 저장소에서는 뺀다(중복 방지)
  const save = async () => {
    const d = cur(); if (busy) return; busy = true; cap.textContent = "저장 중…";
    try {
      await postLabel(f.stem, d.t, f.W, f.H, boxes, f.src);
      if (d.src === "sam") {
        await fetch("/api/sam2_drop", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, t: d.t }) }).catch(() => {});
        if (SAMMAP[f.clip]) delete SAMMAP[f.clip][d.t.toFixed(1)]; SAML[f.clip] = Promise.resolve(SAMMAP[f.clip] || {});
      }
      d.src = "hand"; d.boxes = boxes.map(b => b.slice());
      SAMFR[f.stem] = samFramesOf(f.clip); if (typeof updateRawBadge === "function") updateRawBadge(f.stem);
      if (typeof refillGrid === "function") refillGrid();
      if (ED && ED.clip === f.clip) { if (LB.sec === d.t) { LB.boxes = boxes.map(b => b.slice()); LB.src = "hand"; } if (ED.syncSam) ED.syncSam(); if (ED.fillShots) ED.fillShots(); if (ED.loadSam) ED.loadSam(); }
    } catch (e) {}
    busy = false; render();
  };
  const dropFrame = async () => {
    const d = cur(); if (busy) return;
    if (!await uiConfirm(`${_disp(d.t)} 프레임의 라벨을 지웁니다. 계속할까요?`, { ok: "삭제", danger: true })) return;
    busy = true; cap.textContent = "제거 중…";
    try {
      if (d.src === "sam") {
        await fetch("/api/sam2_drop", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip, t: d.t }) });
        if (SAMMAP[f.clip]) delete SAMMAP[f.clip][d.t.toFixed(1)]; SAML[f.clip] = Promise.resolve(SAMMAP[f.clip] || {});
      } else {
        await postLabel(f.stem, d.t, f.W, f.H, [], f.src);   // 손라벨: 빈 라벨(검토 완료) 로
      }
      SAMFR[f.stem] = samFramesOf(f.clip); if (typeof updateRawBadge === "function") updateRawBadge(f.stem);
      items.splice(idx, 1);
      if (typeof refillGrid === "function") refillGrid();
      if (ED && ED.clip === f.clip) { if (LB.sec === d.t) { LB.boxes = []; LB.src = "none"; } if (ED.syncSam) ED.syncSam(); if (ED.fillShots) ED.fillShots(); if (ED.loadSam) ED.loadSam(); }
      busy = false;
      if (!items.length) { done(); return; }
      show(Math.min(idx, items.length - 1));
    } catch (e) { busy = false; cap.textContent = "제거 실패"; }
  };
  bDel.onclick = dropFrame;
  // ---- 박스 편집(변 드래그 = 크기, 안쪽 드래그 = 이동)
  const hit = p => {                                   // 변/모서리 잡기
    for (let i = boxes.length - 1; i >= 0; i--) {
      const b = boxes[i], L = b[1], T = b[2], R = b[1] + b[3], B = b[2] + b[4];
      const nx = Math.abs(p.x - L) < p.tx, px_ = Math.abs(p.x - R) < p.tx, ny = Math.abs(p.y - T) < p.ty, py_ = Math.abs(p.y - B) < p.ty;
      const inX = p.x > L - p.tx && p.x < R + p.tx, inY = p.y > T - p.ty && p.y < B + p.ty;
      if ((nx || px_) && inY) return { i, l: nx, r: px_, t: ny && inX, b: py_ && inX };
      if ((ny || py_) && inX) return { i, l: false, r: false, t: ny, b: py_ };
    }
    return null;
  };
  const under = p => { for (let i = boxes.length - 1; i >= 0; i--) { const b = boxes[i]; if (p.x >= b[1] && p.x <= b[1] + b[3] && p.y >= b[2] && p.y <= b[2] + b[4]) return i; } return null; };
  let drag = null;
  ovl.onmousemove = ev => {
    const p = norm(ev); lastP = p;
    if (drag) {
      const b = boxes[drag.i];
      if (drag.type === "mv") { b[1] = Math.min(Math.max(p.x - drag.dx, 0), 1 - b[3]); b[2] = Math.min(Math.max(p.y - drag.dy, 0), 1 - b[4]); }
      else {
        let L = b[1], T = b[2], R = b[1] + b[3], B = b[2] + b[4];
        if (drag.l) L = Math.min(Math.max(p.x, 0), R - 0.005); if (drag.r) R = Math.max(Math.min(p.x, 1), L + 0.005);
        if (drag.t) T = Math.min(Math.max(p.y, 0), B - 0.005); if (drag.b) B = Math.max(Math.min(p.y, 1), T + 0.005);
        b[1] = L; b[2] = T; b[3] = R - L; b[4] = B - T;
      }
      render(); return;
    }
    const h = hit(p);
    ovl.style.cursor = h ? ((h.l || h.r) && (h.t || h.b) ? "nwse-resize" : (h.l || h.r) ? "ew-resize" : "ns-resize") : (under(p) !== null ? "move" : "default");
  };
  ovl.onmousedown = ev => {
    if (ev.button !== 0 || busy) return;
    ev.preventDefault();
    const p = norm(ev); const h = hit(p);
    if (h) { drag = Object.assign({ type: "rz" }, h); return; }
    const u = under(p); if (u !== null) { const b = boxes[u]; drag = { type: "mv", i: u, dx: p.x - b[1], dy: p.y - b[2] }; }
  };
  const finish = () => { if (!drag) return; drag = null; boxes.forEach(b => { b[1] = +b[1].toFixed(5); b[2] = +b[2].toFixed(5); b[3] = +b[3].toFixed(5); b[4] = +b[4].toFixed(5); }); save(); };
  ovl.onmouseup = finish; ovl.onmouseleave = finish;
  show(idx);
  v.appendChild(holder); v.appendChild(cap); v.appendChild(row);
  const done = () => { v.remove(); document.onkeydown = _k0; };
  bClose.onclick = done;
  v.onclick = ev => { if (ev.target === v) done(); };
  v.oncontextmenu = ev => { ev.preventDefault(); const t = cur().t; done(); const g = document.getElementById("autoGrid"); if (g) g.remove(); openFrameAt(f.clip, t, LB.mode); };
  const _k0 = document.onkeydown;
  document.onkeydown = ev => {
    if (document.getElementById("uiDlg")) return;    // 대화상자가 떠 있으면 그쪽이 처리
    if (ev.key === "Escape") { ev.preventDefault(); done(); return; }
    if (ev.key === "ArrowLeft") { ev.preventDefault(); show(idx - 1); return; }
    if (ev.key === "ArrowRight") { ev.preventDefault(); show(idx + 1); return; }
    if (ev.key === "Delete" || ev.key === "Backspace") {   // 마우스 아래 박스 삭제(없으면 무시)
      ev.preventDefault(); if (!lastP || busy) return;
      const u = under(lastP); if (u === null) return;
      boxes.splice(u, 1); render(); save();
    }
  };
  document.body.appendChild(v);
}

'''
s = s[:i] + new + s[j:]
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
