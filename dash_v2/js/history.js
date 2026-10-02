// ---------- 히스토리 탭(2026-09-30): 모델 개선 기록. 원본 = configs/history.yaml(GET/POST /api/history)
// 상태(일이 끝났나) = 할 일 · 진행 · 완료(계약 v3: 아이디어는 없앴다. 할지 덜 정한 것도 할 일 + 선행 조건), 판정(결과를 쓸 건가, 완료만) = 채택 · 기각 · 보류. 사용자가 여기서 고치고 Claude 는 연구일지를 쓸 때 고친다
// 2026-10-01 계약 v2 · v3: 맨 위 Quick Add(할 일 한 줄 메모) + item · phase 배지 + 전역 항목 필터(core.js GF). 칸반 보기는 넣었다가 같은 날 뺐다(사용자), 날짜별 보기 하나
// 2026-10-01 알림(파일의 days[].milestones)은 목록에 안 그린다. 머리줄 '알림' 단추로 여는 창에 모았다(맨 아래 nt*)
const HS_ST = ["할 일", "진행", "완료"], HS_DEC = ["채택", "기각", "보류"], HS_ITEM = ["방화", "사람", "쓰러짐", "공통"];
const HS_LBL = { "할 일": "할 일", "진행": "진행 중", "완료": "완료" };
const hsCls = s => ({ "할 일": "todo", "진행": "run" }[s] || "ok");
const HS = { doc: null, f: null, df: null, edit: null, open: new Set() };        // 문서 · 상태 필터 · 판정 필터 · 고치는 항목 id · 펼친 날짜
const hsEsc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const HS_WD = "일월화수목금토";
const hsDay = d => { const t = new Date(d + "T00:00:00+09:00"); return `${d.slice(5)} (${HS_WD[t.getDay()]})`; };
const hsToday = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
const hsGf = it => GF === "all" || !it.item || it.item === "공통" || it.item === gf().meta;   // 전역 필터: 같은 항목 + 공통(item 없음 = 공통)
const hsVis = d => d.items.length || !(d.milestones || []).length;   // 목록에 보일 날짜. 알림만 있고 항목이 없는 날짜는 알림 창에만 나온다
const hsCopy = () => JSON.parse(JSON.stringify(HS.doc.days));   // 고칠 때 쓰는 사본. 사본에 고쳐 보내면 저장이 안 됐을 때 화면의 문서는 그대로라 다시 눌러도 두 번 들어가지 않는다
const hsBusy = () => CUR.mode === "history" && HS.edit ? (alert("고치던 히스토리 항목을 먼저 저장하거나 취소해 주세요"), true) : false;   // 통째 저장은 고치던 칸을 닫는다 → 입력이 날아가지 않게 먼저 막는다(알림 창 · 빠른 추가 · 날짜 추가)

async function hsLoad() {                            // 문서만 읽는다(화면은 안 건드린다 → 알림 창이 어느 탭에서든 쓴다). 못 읽으면 false
  let ok = true;
  try { HS.doc = await (await fetch("/api/history")).json(); } catch (e) { ok = false; }
  ntSync();
  return ok;
}
async function buildHistory() {
  const c = $("#center");
  c.innerHTML = '<div class="empty">불러오는 중…</div>';
  const ok = await hsLoad();
  if (CUR.mode !== "history") return;
  if (!ok) { c.innerHTML = '<div class="empty">히스토리를 못 읽었습니다</div>'; return; }
  if (HS.doc.error) { c.innerHTML = `<div class="empty">${hsEsc(HS.doc.error)}</div>`; return; }
  if (!HS.open.size) HS.doc.days.filter(hsVis).slice(0, 2).forEach(d => HS.open.add(d.date));   // 처음엔 최근 이틀 펼침
  hsRender();
}
async function hsSave(days) {                         // 문서 통째로 저장(days = 고친 사본, 안 주면 지금 문서). 그 사이 다른 곳에서 고쳤으면(시각이 다르면) 저장하지 않고 새로 읽는다
  let r;
  try {
    r = await (await fetch("/api/history", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base: HS.doc.updated_at, by: "사용자", doc: { days: days || HS.doc.days } }) })).json();
  } catch (e) { alert("저장 못 함: " + e); return false; }
  if (!r.ok) {
    alert(r.conflict ? "다른 곳에서 먼저 고쳤습니다. 새로 불러옵니다(방금 고친 것은 다시 입력해 주세요)" : "저장 못 함: " + (r.err || ""));
    HS.edit = null;
    if (CUR.mode === "history") await buildHistory(); else await hsLoad();   // 다른 탭에서(알림 창) 저장하다 실패하면 그 탭 화면은 그대로 두고 문서만 다시 읽는다
    return false;
  }
  HS.doc = r.doc; HS.edit = null;
  if (CUR.mode === "history") hsRender();              // 알림 창은 어느 탭에서든 저장한다. 히스토리 탭이 아니면 가운데 화면을 안 그린다
  ntSync();
  return true;
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
  const days = D.days.filter(hsVis).map(d => {
    const mine = d.items.filter(hsGf), it = d.items.filter(keep), cnt = HS_ST.map(s => [s, mine.filter(i => i.s === s).length]).filter(x => x[1]);
    const pct = mine.length ? Math.round(100 * mine.filter(i => i.s === "완료").length / mine.length) : 0;
    const isOpen = HS.open.has(d.date) || HS.f || HS.df;
    return `<details class="hs-day${d.date === hsToday() ? " today" : ""}" data-date="${d.date}"${isOpen ? " open" : ""}>
      <summary class="hs-dh"><span class="d">${hsDay(d.date)}</span>${d.note ? `<span class="t">${hsEsc(d.note)}</span>` : ""}
        <span class="hs-cnt">${cnt.map(([s, n]) => `<span class="hs-c-${hsCls(s)}">${HS_LBL[s]} ${n}</span>`).join("")}</span>
        <span class="hs-prog"><i style="width:${pct}%"></i></span></summary>
      <div class="hs-items">${it.length ? it.map(x => hsRow(x)).join("") : '<div class="hs-empty">이 조건인 항목 없음</div>'}</div>
      ${D.readonly ? "" : `<div class="hs-dayact"><button class="hs-add" data-date="${d.date}">+ 항목</button></div>`}</details>`;
  }).join("");
  return `${open}<div class="hs-tl">${days}</div>`;
}
// ---------- 맨 위 서버 큐 띠(4단계 개편, 10-02 사용자 시안 P4-1) ----------
// 한 줄 = 실행 중 · 대기 판 수 · GPU. 누르면 큐 표(결과 탭 nrQueueHtml 그대로) · 대기 판 · 러너 로그(접는 단추 없이 늘 펼침). 30초마다 /api/queue
// 띠 요소는 하나를 두고 hsRender 가 다시 그릴 때마다 붙인다(펼침 상태가 그대로 남는다). 결과 탭 큐 상자는 그대로
const HQ = { q: null, at: 0, el: null, busy: false };
async function hqFetch() {
  if (HQ.busy) return;
  HQ.busy = true;
  try { HQ.q = await (await fetch("/api/queue")).json(); } catch (e) { HQ.q = { error: true }; }
  HQ.at = Date.now(); HQ.busy = false;
}
function hqDraw() {
  if (!HQ.el) { HQ.el = document.createElement("details"); HQ.el.className = "hq"; }
  const q = HQ.q;
  if (!q || q.error) { HQ.el.innerHTML = `<summary class="hq-sum">${nrMut(q ? "큐를 못 읽었습니다" : "큐 불러오는 중…")}</summary>`; return; }
  const run = q.running || [], w = q.waiting || [], g = q.gpu, box = document.createElement("div");
  box.innerHTML = nrQueueHtml(q);
  const log = box.querySelector(".nr-qdet");
  if (log) {
    const tip = x => nrEsc([x.item, x.queue, x.imgsz ? `${x.imgsz} / 배치 ${x.batch}` : ""].filter(Boolean).join(" · "));   // 대기 판 = 러너가 집는 순서 그대로
    log.insertAdjacentHTML("beforebegin", `<div class="nr-qbox"><div class="hq-h">대기 ${w.length}판</div>` +
      (w.length ? `<div class="hq-tags">${w.map(x => `<span class="hs-tag" title="${tip(x)}">${nrEsc(x.name)}</span>`).join("")}</div>` : "") + "</div>");
    const plain = document.createElement("div"); plain.className = "nr-qbox";   // 러너 로그: 접는 단추 없이 늘 펼침, 내용은 결과 탭과 같음
    plain.innerHTML = `<div class="hq-h">러너 로그</div>` + [...log.querySelectorAll(".nr-qlog, .nr-mut")].map(x => x.outerHTML).join("");
    log.replaceWith(plain);
  }
  const gpu = g && g.total_mib ? `<span class="hq-gpu"><span class="hq-k">GPU</span><i class="hq-bar"><b style="width:${Math.round(100 * g.used_mib / g.total_mib)}%"></b></i>` +
    `<span>${g.used_mib.toLocaleString()} / ${g.total_mib.toLocaleString()} MiB</span><span class="nr-mut">사용률 ${g.util}%</span></span>` : "";
  HQ.el.innerHTML = `<summary class="hq-sum"><span class="hq-c${run.length ? " run" : ""}">${run.length ? `실행 중 ${run.length}판` : "실행 중 없음"}</span>` +
    `<span class="hq-c">대기 ${w.length}판</span>${gpu}</summary><div class="hq-body">${box.innerHTML}</div>`;
}
function hqMount(top) {                               // 위 고정 줄(빠른 추가 · 상태 카드) 맨 앞에 띠
  if (!top) return;
  if (!HQ.el) hqDraw();
  top.prepend(HQ.el);
  if (Date.now() - HQ.at > 30000) hqFetch().then(hqDraw);
}
setInterval(async () => {                             // 결과 탭처럼 30초마다 큐만 다시 읽는다(히스토리 탭에 띠가 붙어 있을 때만)
  if (CUR.mode !== "history" || document.hidden || !HQ.el || !HQ.el.isConnected) return;
  await hqFetch(); hqDraw();
}, 30000);
function hsRender() {
  const c = $("#center"), D = HS.doc, all = D.days.flatMap(d => d.items).filter(hsGf), y = c.scrollTop;
  const cards = '<div class="hs-cards">' + `<button class="hs-card${HS.f ? "" : " on"}" data-s="" aria-pressed="${!HS.f}"><div class="k">전체</div><div class="v">${all.length}</div></button>` + HS_ST.map(s => `<button class="hs-card hs-c-${hsCls(s)}${HS.f === s ? " on" : ""}" data-s="${s}" aria-pressed="${HS.f === s}">
      <div class="k">${HS_LBL[s]}</div><div class="v">${all.filter(i => i.s === s).length}</div></button>`).join("") + "</div>";
  const decf = HS_DEC.map(x => `<button class="hs-dfb hs-d-${x}${HS.df === x ? " on" : ""}" data-d="${x}" aria-pressed="${HS.df === x}">${x} ${all.filter(i => i.dec === x).length}</button>`).join("");
  const qa = D.readonly ? "" : `<form class="hs-qa"><input name="t" placeholder="해 볼 것 한 줄 메모${GF === "all" ? "" : " · " + gf().label}" aria-label="할 일 빠른 추가" autocomplete="off"><button>+ 할 일</button></form>`;   // Quick Add: {id, s: 할 일, t}(+ 전역 필터 항목)만(계약 v3)
  c.innerHTML = `<div class="hs"><div class="hs-top">${qa}${cards}
      <div class="hs-meta"><div class="hs-decf">${decf}</div>${D.readonly ? '<span class="hs-ro">보기 전용(고치기는 서버 B 대시보드)</span>' : '<button class="hs-dayadd">+ 날짜</button>'}
      <span class="sp">마지막 수정 ${hsEsc(D.updated_at)}${D.updated_by ? " · " + hsEsc(D.updated_by) : ""}</span></div></div>${hsDays(D, all)}</div>`;
  hqMount(c.querySelector(".hs-top"));                // 맨 위 서버 큐 띠
  c.scrollTop = y;
  const q = c.querySelector(".hs-qa");
  if (q) q.onsubmit = async e => {
    e.preventDefault();
    const t = q.t.value.trim(), date = hsToday(); if (!t || hsBusy()) return;
    const days = hsCopy();
    let d = days.find(x => x.date === date);
    if (!d) { d = { date, items: [] }; days.push(d); days.sort((a, b) => a.date < b.date ? 1 : -1); }
    d.items.unshift(Object.assign({ id: hsNewId(date), s: "할 일", t }, GF === "all" ? {} : { item: gf().meta }));
    await hsSave(days);
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
  if (c.querySelector(".hs-dayadd")) c.querySelector(".hs-dayadd").onclick = async () => {
    if (hsBusy()) return;
    const date = prompt("날짜(YYYY-MM-DD)", hsToday()); if (!date) return;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) { alert("날짜 모양이 YYYY-MM-DD 가 아닙니다"); return; }
    const ex = HS.doc.days.find(d => d.date === date);
    if (ex && hsVis(ex)) { alert("이미 있는 날짜입니다"); return; }
    if (ex) { const id = hsNewId(date); ex.items.unshift({ id, s: "할 일", t: "" }); HS.edit = id; HS.open.add(date); hsRender(); return; }   // 알림만 있어 목록에 안 보이던 날짜 → 새 항목 칸을 연다(저장하면 목록에 나온다)
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

// ---------- 알림 창(2026-10-01): 날짜마다 적힌 알림을 히스토리 목록에서 빼 머리줄 '알림' 단추로 여는 창에 모았다
// 저장 칸(days[].milestones [{at, text}])과 저장 방식(문서 통째로 POST)은 그대로다. 어느 탭에서든 열리므로 저장 뒤 가운데 화면은 히스토리 탭일 때만 다시 그린다(hsSave)
// 열기 · 닫기(단추, Esc, 바깥 누르기, 닫기 단추) · 초점 되돌리기는 브라우저의 popover 가 한다(dashboard.html 의 popover · popovertarget). 여기서는 그리기 · 추가 · 삭제만
const ntOpen = () => $("#ntPanel").matches(":popover-open");
function ntSync() {                                  // 단추의 '오늘 N' + 열려 있으면 창 다시 그리기. 문서를 읽거나 저장한 뒤마다 부른다
  const b = $("#ntBtn"), D = HS.doc;
  if (!D || D.error) { b.hidden = true; if (ntOpen()) $("#ntPanel").hidePopover(); return; }   // 히스토리를 못 읽는 서버
  const n = ((D.days.find(d => d.date === hsToday()) || {}).milestones || []).length;
  b.hidden = false; b.title = `오늘 알림 ${n}건`; b.setAttribute("aria-label", n ? `알림, 오늘 ${n}건` : "알림");
  b.classList.toggle("has", n > 0);                    // 오늘 알림이 있으면 종 위에 빨간 점(10-01 사용자: '오늘 N' 글자 대신)
  if (ntOpen()) ntRender();
}
function ntRender(reset) {                           // 최근 날짜 먼저, 같은 날짜 안에서는 나중에 적은 것 먼저. reset 이 아니면 쓰던 입력은 남긴다(다시 읽거나 저장이 안 됐을 때 날아가지 않게)
  const p = $("#ntPanel"), D = HS.doc, days = D.days.filter(d => (d.milestones || []).length), old = p.querySelector(".nt-form");
  const keep = old && !reset ? [old.date.value, old.at.value, old.text.value] : null;
  const form = D.readonly ? "" :
    `<form class="nt-form"><label>날짜<input type="date" name="date" value="${hsToday()}" max="9999-12-31" required></label>
      <label class="nt-at-l">시각 · 이름<input name="at" value="${new Date(Date.now() + 9 * 3600e3).toISOString().slice(11, 16)}" placeholder="예: 10:00, 사전시험" maxlength="20" required autocomplete="off"></label>
      <label class="nt-tx-l">내용<textarea name="text" rows="2" required></textarea></label><button>+ 알림</button></form>`;
  const list = days.map(d => `<section class="nt-day"><h3>${hsDay(d.date)}${d.date === hsToday() ? '<span class="nt-today">오늘</span>' : ""}</h3>` +
    d.milestones.map((m, j) => `<div class="nt-row"><b class="nt-at">${hsEsc(m.at)}</b><div class="nt-tx">${hsEsc(m.text)}</div>${D.readonly ? "" :
      `<button type="button" class="nt-del" data-date="${hsEsc(d.date)}" data-j="${j}" aria-label="${hsEsc(m.at)} 알림 지우기">지우기</button>`}</div>`).reverse().join("") + "</section>").join("");
  p.innerHTML = `<div class="nt-head"><h2>알림<span>${days.reduce((n, d) => n + d.milestones.length, 0)}건</span></h2>${D.readonly ? '<span class="nt-ro">보기 전용(고치기는 서버 B 대시보드)</span>' : ""}` +
    `<button type="button" class="nt-x" popovertarget="ntPanel" popovertargetaction="hide">닫기</button></div>` + form + (list || '<div class="nt-empty">알림 없음</div>');
  const f = p.querySelector(".nt-form");
  if (f && keep) [f.date.value, f.at.value, f.text.value] = keep;
  if (f) f.onsubmit = async e => {
    e.preventDefault();
    const date = f.date.value, at = f.at.value.trim(), text = f.text.value.trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !at || !text || hsBusy()) return;   // 내용이 빈 알림은 서버가 버린다 → 여기서 막는다
    const days = hsCopy();
    let d = days.find(x => x.date === date);
    if (!d) { d = { date, items: [] }; days.push(d); days.sort((a, b) => a.date < b.date ? 1 : -1); }
    (d.milestones = d.milestones || []).push({ at, text });
    if (await hsSave(days)) ntRender(true);            // 저장됐으면 입력 칸을 비운다
  };
  p.querySelectorAll(".nt-del").forEach(b => b.onclick = async () => {
    if (hsBusy() || !confirm("이 알림을 지울까요?")) return;
    const days = hsCopy(), d = days.find(x => x.date === b.dataset.date);
    d.milestones.splice(+b.dataset.j, 1);
    if (!d.items.length && !d.milestones.length && !d.note) days.splice(days.indexOf(d), 1);   // 알림 때문에만 생긴 빈 날짜는 같이 지운다(목록에 빈 날짜로 남지 않게)
    await hsSave(days);
  });
  if (ntOpen() && !p.contains(document.activeElement)) p.focus();   // 다시 그리면 누르던 단추가 사라진다 → 초점을 창에 둔다(글쇠가 편집기로 새지 않게)
}
function ntInit() {                                  // boot 에서 한 번(작업대 모드는 부르지 않는다 → 단추가 숨은 채로 남는다)
  const p = $("#ntPanel");
  p.addEventListener("beforetoggle", e => {
    if (e.newState !== "open") return;
    const r = $("#ntBtn").getBoundingClientRect();
    p.style.top = r.bottom + 8 + "px"; p.style.right = Math.max(8, window.innerWidth - r.right) + "px";   // 단추 바로 아래 오른쪽 끝에 맞춘다
    ntRender(true);
  });
  p.addEventListener("toggle", e => {
    if (e.newState !== "open") return;
    p.focus();
    if (CUR.mode !== "history") hsLoad();              // 다른 탭에서 열면 새로 읽어 다시 그린다. 히스토리 탭에서는 화면에 떠 있는 문서를 그대로 쓴다(고치던 칸을 건드리지 않게)
  });
  p.addEventListener("keydown", e => e.stopPropagation());   // 창 안에서 누른 글쇠가 편집기 단축키(document.onkeydown)로 새지 않게. Esc 닫기는 브라우저가 따로 처리한다
  setInterval(() => { if (CUR.mode !== "history" && !ntOpen() && !document.hidden) hsLoad(); }, 60000);   // 다른 곳에서 알림을 더하면 단추의 '오늘 N' 이 1분 안에 따라온다
  hsLoad();
}
