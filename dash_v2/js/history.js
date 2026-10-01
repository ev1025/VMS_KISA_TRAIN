// ---------- 히스토리 탭(2026-09-30): 모델 개선 기록. 원본 = configs/history.yaml(GET/POST /api/history)
// 상태(일이 끝났나) = 아이디어 · 할 일 · 진행 · 완료, 판정(결과를 쓸 건가, 완료만) = 채택 · 기각 · 보류. 사용자가 여기서 고치고 Claude 는 연구일지를 쓸 때 고친다
// 2026-10-01 계약 v2: 상태 아이디어 + 맨 위 Quick Add + item · phase 배지 + 전역 항목 필터(core.js GF). 칸반 보기는 넣었다가 같은 날 뺐다(사용자), 날짜별 보기 하나
const HS_ST = ["아이디어", "할 일", "진행", "완료"], HS_DEC = ["채택", "기각", "보류"], HS_ITEM = ["방화", "사람", "쓰러짐", "공통"];
const HS_LBL = { "아이디어": "아이디어", "할 일": "할 일", "진행": "진행 중", "완료": "완료" };
const hsCls = s => ({ "아이디어": "idea", "할 일": "todo", "진행": "run" }[s] || "ok");
const HS = { doc: null, f: null, df: null, edit: null, open: new Set() };        // 문서 · 상태 필터 · 판정 필터 · 고치는 항목 id · 펼친 날짜
const hsEsc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const HS_WD = "일월화수목금토";
const hsDay = d => { const t = new Date(d + "T00:00:00+09:00"); return `${d.slice(5)} (${HS_WD[t.getDay()]})`; };
const hsToday = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
const hsGf = it => GF === "all" || !it.item || it.item === "공통" || it.item === gf().meta;   // 전역 필터: 같은 항목 + 공통(item 없음 = 공통)
const HS_ALERT = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f0883e" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';

async function buildHistory() {
  const c = $("#center");
  c.innerHTML = '<div class="empty">불러오는 중…</div>';
  try { HS.doc = await (await fetch("/api/history")).json(); } catch (e) { c.innerHTML = '<div class="empty">히스토리를 못 읽었습니다</div>'; return; }
  if (CUR.mode !== "history") return;
  if (HS.doc.error) { c.innerHTML = `<div class="empty">${hsEsc(HS.doc.error)}</div>`; return; }
  if (!HS.open.size) (HS.doc.days || []).slice(0, 2).forEach(d => HS.open.add(d.date));   // 처음엔 최근 이틀 펼침
  hsRender();
}
async function hsSave(msg) {                          // 문서 통째로 저장. 그 사이 다른 곳에서 고쳤으면(시각이 다르면) 저장하지 않고 새로 읽는다
  let r;
  try {
    r = await (await fetch("/api/history", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base: HS.doc.updated_at, by: "사용자", doc: { days: HS.doc.days } }) })).json();
  } catch (e) { alert("저장 못 함: " + e); return false; }
  if (!r.ok) {
    alert(r.conflict ? "다른 곳에서 먼저 고쳤습니다. 새로 불러옵니다(방금 고친 것은 다시 입력해 주세요)" : "저장 못 함: " + (r.err || ""));
    HS.edit = null; await buildHistory(); return false;
  }
  HS.doc = r.doc; HS.edit = null; hsRender(); return true;
}
function hsItem(id) {
  for (const d of HS.doc.days) { const i = d.items.findIndex(x => x.id === id); if (i >= 0) return [d, i]; }
  return [null, -1];
}
function hsNewId(date) {
  const base = "h" + date.slice(5).replace("-", ""), used = new Set(HS.doc.days.flatMap(d => d.items.map(x => x.id)));
  for (let k = 0; k < 999; k++) { const id = base + "_" + k.toString(36); if (!used.has(id)) return id; }
  return base + "_" + Date.now();
}
function hsForm(it) {                                // 항목 고치기 칸(그 자리)
  const opt = (arr, v, blank) => (blank ? `<option value="">${blank}</option>` : "") + arr.map(x => `<option${x === v ? " selected" : ""}>${x}</option>`).join("");
  const ph = Object.entries(HS.doc.phases || {}).map(([k, v]) => `<option value="${hsEsc(k)}"${k === it.phase ? " selected" : ""}>${hsEsc(v)}</option>`).join("");
  return `<div class="hs-form" data-id="${hsEsc(it.id)}">
    <div class="hs-frow"><label>상태<select name="s">${opt(HS_ST, it.s)}</select></label>
      <label>판정<select name="dec">${opt(HS_DEC, it.dec || "", "(없음)")}</select></label>
      <label>인증 항목<select name="item">${opt(HS_ITEM, it.item || "공통")}</select></label>
      <label class="hs-grow">단계<select name="phase"><option value="">(없음)</option>${ph}</select></label></div>
    <label>항목<input name="t" value="${hsEsc(it.t)}" placeholder="무엇을 했나 / 할 것인가"></label>
    <label>판정 이유<textarea name="why" rows="2" placeholder="채택 · 기각 · 보류의 이유. 보류면 무엇이 결정하는지">${hsEsc(it.why)}</textarea></label>
    <label>결과 수치<textarea name="sub" rows="2" placeholder="근거 수치">${hsEsc(it.sub)}</textarea></label>
    <div class="hs-frow"><label class="hs-grow">선행 조건(할 일)<input name="cond" value="${hsEsc(it.cond)}" placeholder="예: 1단계 판정이 끝난 뒤"></label>
      <label>넘어감<input name="carry" value="${hsEsc(it.carry)}" placeholder="→ 09-30"></label></div>
    <label>기록 위치<input name="ref" value="${hsEsc(it.ref)}" placeholder="커밋 · 결과 파일"></label>
    <div class="hs-fbtn"><button class="hs-save">저장</button><button class="hs-cancel">취소</button><button class="hs-del">삭제</button></div></div>`;
}
function hsRow(it) {
  if (HS.edit === it.id && !HS.doc.readonly) return hsForm(it);
  const phl = (HS.doc.phases || {})[it.phase];
  const bdg = `<span class="hs-bdg">${hsEsc(it.item || "공통")}</span>` + (phl ? `<span class="hs-bdg ph">${hsEsc(phl)}</span>` : "");   // 단계 이름표는 phases 값 그대로, 없으면 표시 안 함
  const tags = [...(it.carry ? [`<span class="hs-tag hs-tag-carry">${hsEsc(it.carry)}</span>`] : []),     // 기록 위치 · 넘어감 = 본문 아래 태그(오른쪽 끝에 두면 시선이 흩어지고 제목 줄이 깨졌다)
    ...String(it.ref || "").split(" · ").filter(Boolean).map(r => `<span class="hs-tag">${hsEsc(r)}</span>`)];
  return `<div class="hs-it"><span class="hs-pill hs-p-${hsCls(it.s)}">${HS_LBL[it.s] || hsEsc(it.s)}</span>
    <div class="hs-body"><div class="hs-bdgs">${bdg}</div><div class="hs-ttl">${hsEsc(it.t)}</div>
      ${it.dec ? `<div class="hs-why"><span class="hs-dec hs-d-${it.dec}">${it.dec}</span>${hsEsc(it.why)}</div>` : ""}
      ${it.cond ? `<div class="hs-cond">선행 조건: ${hsEsc(it.cond)}</div>` : ""}
      ${it.sub ? `<div class="hs-sub" title="눌러서 펼치기 · 접기">${hsEsc(it.sub)}</div>` : ""}
      ${tags.length ? `<div class="hs-tags">${tags.join("")}</div>` : ""}</div>
    ${HS.doc.readonly ? "<span></span>" : `<button class="hs-pen" data-id="${hsEsc(it.id)}" title="고치기" aria-label="고치기">✎</button>`}</div>`;
}
function hsDays(D, all) {
  const keep = it => hsGf(it) && (!HS.f || it.s === HS.f) && (!HS.df || it.dec === HS.df) || HS.edit === it.id;
  // 할 일 · 보류를 누르면 날짜 상관없이 오래된 것부터 모아 위에(결정할 것 · 해야 할 것)
  const pool = HS.f === "할 일" ? all.filter(i => i.s === "할 일") : HS.df === "보류" ? all.filter(i => i.dec === "보류") : null;
  const dateOf = it => (D.days.find(d => d.items.includes(it)) || {}).date || "";
  const open = !pool ? "" : `<div class="hs-open"><h3>${HS.f === "할 일" ? "할 일 모아 보기" : "결정 남은 것(보류) 모아 보기"} (오래된 것 먼저)</h3><ol>` +
    pool.slice().sort((a, b) => dateOf(a) < dateOf(b) ? -1 : 1).map(i => `<li>${hsEsc(i.t)}<span class="hs-from">${dateOf(i).slice(5)}${i.cond ? " · 선행 조건: " + hsEsc(i.cond) : ""}${i.why && HS.df === "보류" ? " · " + hsEsc(i.why) : ""}</span></li>`).join("") + "</ol></div>";
  const days = D.days.map(d => {
    const mine = d.items.filter(hsGf), it = d.items.filter(keep), cnt = HS_ST.map(s => [s, mine.filter(i => i.s === s).length]).filter(x => x[1]);
    const pct = mine.length ? Math.round(100 * mine.filter(i => i.s === "완료").length / mine.length) : 0;
    const isOpen = HS.open.has(d.date) || HS.f || HS.df;
    return `<details class="hs-day${d.date === hsToday() ? " today" : ""}" data-date="${d.date}"${isOpen ? " open" : ""}>
      <summary class="hs-dh"><span class="d">${hsDay(d.date)}</span>${d.note ? `<span class="t">${hsEsc(d.note)}</span>` : ""}
        <span class="hs-cnt">${cnt.map(([s, n]) => `<span class="hs-c-${hsCls(s)}">${HS_LBL[s]} ${n}</span>`).join("")}</span>
        <span class="hs-prog"><i style="width:${pct}%"></i></span></summary>
      ${(d.milestones || []).map((m, j) => `<div class="hs-ms">${HS_ALERT}<div class="hs-grow"><b>${hsEsc(m.at)}</b>${hsEsc(m.text)}</div>${D.readonly ? "" : `<button class="hs-msdel" data-date="${d.date}" data-j="${j}" title="이정표 지우기" aria-label="이정표 지우기">×</button>`}</div>`).join("")}
      <div class="hs-items">${it.length ? it.map(x => hsRow(x)).join("") : '<div class="hs-empty">이 조건인 항목 없음</div>'}</div>
      ${D.readonly ? "" : `<div class="hs-dayact"><button class="hs-add" data-date="${d.date}">+ 항목</button><button class="hs-msadd" data-date="${d.date}">+ 이정표</button></div>`}</details>`;
  }).join("");
  return `${open}<div class="hs-tl">${days}</div>`;
}
function hsRender() {
  const c = $("#center"), D = HS.doc, all = D.days.flatMap(d => d.items).filter(hsGf), y = c.scrollTop;
  const cards = '<div class="hs-cards">' + `<button class="hs-card${HS.f ? "" : " on"}" data-s="" aria-pressed="${!HS.f}"><div class="k">전체</div><div class="v">${all.length}</div></button>` + HS_ST.map(s => `<button class="hs-card hs-c-${hsCls(s)}${HS.f === s ? " on" : ""}" data-s="${s}" aria-pressed="${HS.f === s}">
      <div class="k">${HS_LBL[s]}</div><div class="v">${all.filter(i => i.s === s).length}</div></button>`).join("") + "</div>";
  const decf = HS_DEC.map(x => `<button class="hs-dfb hs-d-${x}${HS.df === x ? " on" : ""}" data-d="${x}" aria-pressed="${HS.df === x}">${x} ${all.filter(i => i.dec === x).length}</button>`).join("");
  const qa = D.readonly ? "" : `<form class="hs-qa"><input name="t" placeholder="모델 개선 아이디어${GF === "all" ? "" : " · " + gf().label}" aria-label="아이디어 빠른 추가" autocomplete="off"><button>+ 아이디어</button></form>`;   // Quick Add: {id, s: 아이디어, t}(+ 전역 필터 항목)만
  c.innerHTML = `<div class="hs"><div class="hs-top">${qa}${cards}
      <div class="hs-meta"><div class="hs-decf">${decf}</div>${D.readonly ? '<span class="hs-ro">보기 전용(고치기는 서버 B 대시보드)</span>' : '<button class="hs-dayadd">+ 날짜</button>'}
      <span class="sp">마지막 수정 ${hsEsc(D.updated_at)}${D.updated_by ? " · " + hsEsc(D.updated_by) : ""}</span></div></div>${hsDays(D, all)}</div>`;
  c.scrollTop = y;
  const q = c.querySelector(".hs-qa");
  if (q) q.onsubmit = async e => {
    e.preventDefault();
    const t = q.t.value.trim(), date = hsToday(); if (!t) return;
    let d = HS.doc.days.find(x => x.date === date);
    if (!d) { d = { date, items: [] }; HS.doc.days.unshift(d); HS.doc.days.sort((a, b) => a.date < b.date ? 1 : -1); }
    d.items.unshift(Object.assign({ id: hsNewId(date), s: "아이디어", t }, GF === "all" ? {} : { item: gf().meta }));
    await hsSave();
  };
  c.querySelectorAll(".hs-card").forEach(b => b.onclick = () => { HS.f = HS.f === b.dataset.s ? null : (b.dataset.s || null); hsRender(); });
  c.querySelectorAll(".hs-dfb").forEach(b => b.onclick = () => { HS.df = HS.df === b.dataset.d ? null : b.dataset.d; hsRender(); });
  c.querySelectorAll(".hs-day").forEach(e => e.ontoggle = () => { if (!HS.f && !HS.df) { e.open ? HS.open.add(e.dataset.date) : HS.open.delete(e.dataset.date); } });
  c.querySelectorAll(".hs-pen").forEach(b => b.onclick = () => { HS.edit = b.dataset.id; hsRender(); });
  c.querySelectorAll(".hs-sub").forEach(e => e.onclick = () => e.classList.toggle("open"));   // 세부 수치는 한 줄만, 누르면 펼침
  c.querySelectorAll(".hs-add").forEach(b => b.onclick = () => {
    const d = HS.doc.days.find(x => x.date === b.dataset.date), id = hsNewId(d.date);
    d.items.unshift({ id, s: "할 일", t: "" }); HS.edit = id; HS.open.add(d.date); hsRender();
  });
  c.querySelectorAll(".hs-msadd").forEach(b => b.onclick = async () => {
    const at = prompt("이정표 시각 · 이름(예: 10:00, 사전시험)"); if (!at) return;
    const text = prompt("이정표 내용"); if (text == null) return;
    const d = HS.doc.days.find(x => x.date === b.dataset.date); (d.milestones = d.milestones || []).push({ at, text }); await hsSave();
  });
  c.querySelectorAll(".hs-msdel").forEach(b => b.onclick = async () => {
    if (!confirm("이 이정표를 지울까요?")) return;
    const d = HS.doc.days.find(x => x.date === b.dataset.date); d.milestones.splice(+b.dataset.j, 1); await hsSave();
  });
  if (c.querySelector(".hs-dayadd")) c.querySelector(".hs-dayadd").onclick = async () => {
    const date = prompt("날짜(YYYY-MM-DD)", hsToday()); if (!date) return;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) { alert("날짜 모양이 YYYY-MM-DD 가 아닙니다"); return; }
    if (HS.doc.days.some(d => d.date === date)) { alert("이미 있는 날짜입니다"); return; }
    HS.doc.days.push({ date, items: [] }); HS.doc.days.sort((a, b) => a.date < b.date ? 1 : -1); HS.open.add(date); await hsSave();
  };
  const f = c.querySelector(".hs-form");
  if (f) {
    const id = f.dataset.id, [d, i] = hsItem(id);
    f.querySelector('[name="t"]').focus();
    f.querySelector(".hs-save").onclick = async () => {
      const it = d.items[i], v = n => f.querySelector(`[name="${n}"]`).value.trim();
      if (!v("t")) { alert("항목을 적어 주세요"); return; }
      Object.assign(it, { s: v("s"), dec: v("dec"), t: v("t"), why: v("why"), sub: v("sub"), ref: v("ref"), cond: v("cond"), carry: v("carry"), item: v("item"), phase: v("phase") });
      if (it.item === "공통") delete it.item;                            // 없으면 공통(계약 v2). 파일에는 안 남긴다
      Object.keys(it).forEach(k => { if (it[k] === "") delete it[k]; });   // 빈 칸은 파일에 안 남긴다
      if (it.s !== "완료" && it.dec) { if (!confirm("판정은 완료 항목에만 둡니다. 판정을 지우고 저장할까요?")) return; delete it.dec; }
      await hsSave();
    };
    f.querySelector(".hs-cancel").onclick = () => { if (!d.items[i].t) d.items.splice(i, 1); HS.edit = null; hsRender(); };
    f.querySelector(".hs-del").onclick = async () => { if (!confirm("이 항목을 지울까요?")) return; d.items.splice(i, 1); await hsSave(); };
  }
}
