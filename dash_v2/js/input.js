// dash_v2/js/input.js: 2단계 '입력 데이터' 탭(2026-10-02 사용자 확정 시안 P2-4 '한 장씩 점검'). main.js 앞에 로드, main.js · trainview.js 함수를 실행 시점에 부른다
//   목적: 학습용으로 구성된 데이터(모듈)를 하나씩 확인하고 잘못된 라벨을 걸러 낸다. 여기서 데이터를 만들지 않는다
//   왼쪽 = 모듈 목록(GET /api/data_modules = configs/data_modules.yaml) · 오류 의심 수(GET /api/tv_summary, 서버가 디스크에 기억하고 세는 중이면 pending)
//   가운데 = 큰 사진 한 장 + 통과(O) · 제외(X) · ← → · 되돌리기(Z) + 아래 줄. 사진 · 라벨 · 의심 사유 = /api/tv_set · /api/tv_thumb(dash_v2/trainview.py)
//   학습 제외 = 서버 저장(GET · POST /api/train_exclude → data/학습데이터/손라벨/train_exclude.json, ML 이 걸러 내기로 쓴다). 통과 표시는 이 브라우저에만
"use strict";
const P2 = { mods: null, modErr: "", by: {}, cnt: {}, pending: [], sumOk: true, sumT: 0, msg: "", msgTip: "", focus: "", flag: "sus", off: 0, data: null, cur: 0, seq: 0, lbTop: 0, exOk: true };
const P2_PAGE = 60;
const P2X = { ex: {}, ok: {}, undo: [] };                 // ex = 학습 제외 {경로: {set, path, name, why, by, at}}(서버), ok = 통과 {경로: 셋}(이 브라우저)
try { P2X.ok = JSON.parse(localStorage.getItem("in_ok") || "{}") || {}; } catch (e) {}
try { P2.focus = localStorage.getItem("in_focus") || ""; } catch (e) {}
const p2Now = () => { const d = new Date(), z = n => String(n).padStart(2, "0"); return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}`; };
const p2SaveOk = () => { try { localStorage.setItem("in_ok", JSON.stringify(P2X.ok)); } catch (e) {} };
const p2SaveUi = () => { try { localStorage.setItem("in_focus", P2.focus); } catch (e) {} };
const p2Items = () => ["방화", "사람"].filter(gfMeta);
const p2N = n => n == null ? "?" : Number(n).toLocaleString();
const p2Nm = n => nrEsc(n).replace(/_/g, "_<wbr>");     // 긴 이름은 밑줄에서만 접는다
const p2Url = (n, f, o) => `/api/tv_set?name=${encodeURIComponent(n)}&flag=${f}&offset=${o}&limit=${P2_PAGE}`;
const p2Thumb = (p, w) => `/api/tv_thumb?w=${w}&p=${encodeURIComponent(p)}`;
const p2Empty = msg => `<div class="empty">${msg}</div>`;
const p2Mods = () => (P2.mods || []).filter(m => m.kind === "module");     // 걸러 내기(flt_*)는 이름 목록이라 사진이 없어 뺀다

// ---------- 태그(모듈 label · role · 이름에서 규칙으로) ----------
const P2_COND = [[/fog|안개/i, "안개"], [/snow|눈/i, "눈"], [/night|야간/i, "야간"], [/흑백|gray/i, "흑백(IR)"]];
const P2_SRC = [[/coco/i, "COCO"], [/fasdd/i, "FASDD"], [/aihub|AI허브/i, "AI허브"], [/wildfire|산불/i, "산불"], [/azimjaan/i, "azimjaan"],
  [/kisa/i, "KISA 영상"], [/우리 영상|_own_|handset/i, "우리 영상"], [/손라벨/, "손라벨"], [/전파/, "확인 전파"], [/헛불|_hn_/i, "헛불 억제"]];
function p2Tags(name) {
  const m = P2.by[name] || { name, label: "", role: "" }, s = m.name + " " + m.label, out = [];
  if (m.role === "pos") out.push(["양성", "r-pos"]); else if (m.role === "mixed") out.push(["양성 + 배경", "r-mix"]); else if (m.role === "neg") out.push(["배경", "r-neg"]);
  const cond = P2_COND.filter(([re]) => re.test(s)).map(x => x[1]), syn = /합성|aug/i.test(s);
  if (syn && cond.length === 1) out.push([cond[0] + " 합성", "c"]);
  else { cond.forEach(c => out.push([c, "c"])); if (syn) out.push(["합성", "c"]); }
  P2_SRC.forEach(([re, t]) => { if (re.test(s) && !out.some(x => x[0] === t)) out.push([t, "s"]); });
  if (/공개/.test(m.label) && !out.some(x => ["COCO", "FASDD", "azimjaan"].includes(x[0]))) out.push(["공개셋", "s"]);
  return out.map(([t, k]) => `<span class="p2-tag ${k}">${nrEsc(t)}</span>`).join("");
}
const P2_LV = { l: "약", m: "중", h: "강" };
function p2Var(p) {                                       // 합성 변형: 파일 이름 꼬리 _fogh · _snowm → {base, ext, v: '안개 강'}
  const m = p.split("/").pop().match(/^(.*)_(fog|snow)([lmh])(\.\w+)$/);
  return m ? { base: m[1], ext: m[4], v: (m[2] === "fog" ? "안개 " : "눈 ") + P2_LV[m[3]], o: "lmh".indexOf(m[3]) } : null;
}
function p2PhotoTags(it) {
  const t = [], v = p2Var(it.p), m = it.p.split("/").pop().match(/^NegativeDB_([^_]+)_/);
  if (!it.boxes.length) t.push("배경");
  if (v) t.push(v.v);
  if (m) t.push(m[1]);
  return t;
}
const P2_CLS = { 방화: [["불", "#f85149"], ["연기", "#a371f7"]], 사람: [["사람", "#58a6ff"]] };
const p2Cls = c => (P2_CLS[(P2.by[P2.focus] || {}).item] || [])[c] || ["번호 " + c, "#d29922"];
function p2Boxes(boxes, label) {                          // 라벨 파일 박스 그대로(YOLO cx cy w h), 클래스 색. label = 큰 사진에서 클래스 이름표
  if (!boxes.length) return "";
  return '<svg class="tv-svg" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">' + boxes.map(b =>
    `<rect x="${b[1] - b[3] / 2}" y="${b[2] - b[4] / 2}" width="${b[3]}" height="${b[4]}" fill="none" stroke="${p2Cls(b[0])[1]}" stroke-width="2" vector-effect="non-scaling-stroke"/>`).join("") + "</svg>" +
    (label ? boxes.map(b => `<span class="p2-bl${b[2] - b[4] / 2 < 0.05 ? " in" : ""}" style="left:${((b[1] - b[3] / 2) * 100).toFixed(2)}%;top:${((b[2] - b[4] / 2) * 100).toFixed(2)}%;background:${p2Cls(b[0])[1]}">${p2Cls(b[0])[0]}</span>`).join("") : "");
}
const p2Why = (it, r) => it.flags.map(f => `<span class="p2-tag ${TV_STRONG.includes(f) ? "r-flt" : "r-pref"}">${nrEsc(r.labels[f])}</span>`).join("");

// ---------- 서버 읽기: 모듈 · 요약 · 학습 제외 ----------
async function p2Json(url, opt) {                         // 실패하면 {error}. 404 · 405 = 서버에 이 기능이 아직 없음(재시작 전)
  try {
    const r = await fetch(url, opt);
    if (r.status === 404 || r.status === 405) return { error: "서버 반영 전", old: true };
    if (!r.ok) return { error: "HTTP " + r.status };
    return await r.json();
  } catch (e) { return { error: "못 읽음" }; }
}
async function p2SumGet() {                               // 모듈별 오류 의심 수(서버가 기억해 둔 것 + 세는 중 목록)
  const j = await p2Json("/api/tv_summary");
  P2.sumOk = !j.error;
  if (!j.error) { (j.mods || []).forEach(m => { P2.cnt[m.name] = m; }); P2.pending = j.pending || []; }
}
function p2SumNext() {                                    // 세는 중인 모듈이 있으면 5초 뒤 다시(이 탭에 있을 때만)
  clearTimeout(P2.sumT);
  if (P2.pending.length) P2.sumT = setTimeout(async () => { await p2SumGet(); if (CUR.mode === "input") { p2DrawLeft(); p2SumNext(); } }, 5000);
}
async function p2ExLoad() {
  const j = await p2Json("/api/train_exclude");
  P2.exOk = !j.error;
  if (!j.error) P2X.ex = Object.fromEntries((j.items || []).map(x => [x.path, x]));
}
async function p2ExPost(path, set, why, on, prev) {       // 학습 제외 넣기 · 빼기. 화면은 먼저 바꾸고, 저장 못 하면 되돌린다
  const j = await p2Json("/api/train_exclude", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ set, path, why, on }) });
  if (j.ok) {                                              // 이 경로만 서버 값으로(먼저 보낸 저장의 응답이 늦게 와도 다른 표시를 덮지 않게)
    const x = (j.items || []).find(y => y.path === path);
    if (x) P2X.ex[path] = x; else delete P2X.ex[path];
    P2.exOk = true; P2.msg = "";
  }
  else {
    if (prev) P2X.ex[path] = prev; else delete P2X.ex[path];
    P2.msg = "학습 제외 저장 안 됨" + (j.old ? " · 서버 반영 전" : "");
    P2.msgTip = j.err || j.error || "";
  }
  if (CUR.mode !== "input") return;
  if (P2.data) p2Show(); else p2DrawLeftMarks();
  const pop = document.getElementById("p2ExPop"); if (pop && pop.matches(":popover-open")) p2ExList();
}

// ---------- 왼쪽: 모듈 목록(오류 의심 많은 순) ----------
const p2ExN = set => Object.values(P2X.ex).filter(x => x.set === set).length;
function p2Sorted(item) {
  const k = m => { const c = P2.cnt[m.name]; return c && !c.error ? c.sus : -1; };
  return p2Mods().filter(m => m.item === item).sort((a, b) => k(b) - k(a) || b.count - a.count);
}
function p2ModHtml(m) {
  const c = P2.cnt[m.name], nx = p2ExN(m.name);
  const sus = c ? (c.error ? `<span class="p2-sus wait" title="${nrEsc(c.error)}">사진 없음</span>` : `<span class="p2-sus${c.sus ? "" : " zero"}">의심 ${p2N(c.sus)}</span>`)
    : P2.pending.includes(m.name) ? '<span class="p2-sus wait">세는 중</span>' : "";
  return `<button type="button" class="p2-mod${m.name === P2.focus ? " on" : ""}" data-n="${nrEsc(m.name)}"><span class="p2-mb"><span class="p2-ml">${nrEsc(m.label)}</span>` +
    `<span class="p2-nm">${p2Nm(m.name)}</span><span class="p2-tags">${p2Tags(m.name)}</span></span>` +
    `<span class="p2-mr">${sus}<span class="p2-cnt">${p2N(c && c.total != null ? c.total : m.count)}장</span>${nx ? `<span class="p2-exn">제외 ${nx}</span>` : ""}</span></button>`;
}
function p2DrawLeft() {
  const pl = document.getElementById("p2Left"); if (!pl) return;
  const items = p2Items(), nx = Object.keys(P2X.ex).length, all = p2Mods();
  const note = !P2.mods ? "" : !P2.exOk ? '<span class="p2-mut p2-prog" title="GET /api/train_exclude 없음">학습 제외 서버 반영 전</span>'
    : !P2.sumOk ? '<span class="p2-mut p2-prog" title="GET /api/tv_summary 없음">의심 수 서버 반영 전</span>'
    : P2.pending.length ? `<span class="p2-mut p2-prog">세는 중 ${all.length - P2.pending.length} / ${all.length}</span>` : "";
  pl.innerHTML = `<div class="p2-lh"><button type="button" class="p2-exbtn" data-exlist="1">학습 제외 <b>${P2.exOk ? p2N(nx) : "-"}</b></button>${note}</div>` +
    `<div class="p2-lb">${!P2.mods ? p2Empty(P2.modErr ? "모듈 목록 " + nrEsc(P2.modErr) : "불러오는 중…")
      : items.length ? items.map(it => `<div class="p2-ih">${it}</div><div class="p2-mods">${p2Sorted(it).map(p2ModHtml).join("")}</div>`).join("") : p2Empty("쓰러짐 학습 데이터 모듈 없음")}</div>`;
  const lb = pl.querySelector(".p2-lb"); lb.scrollTop = P2.lbTop || 0;
  lb.onscroll = () => { P2.lbTop = lb.scrollTop; };
}
function p2PickTop() {
  const top = p2Items().map(it => p2Sorted(it)[0]).filter(Boolean).sort((a, b) => ((P2.cnt[b.name] || {}).sus || 0) - ((P2.cnt[a.name] || {}).sus || 0))[0];
  if (top) p2Pick(top.name);
}
function p2Pick(n) {
  P2.focus = n; P2.flag = "sus"; P2.off = 0; P2.cur = 0; P2Z.z = 1; p2SaveUi();
  document.querySelectorAll("#p2Left .p2-mod").forEach(e => e.classList.toggle("on", e.dataset.n === n));
  p2Load(0);
}

// ---------- 가운데: 큰 사진 한 장 ----------
async function p2Load(at) {
  const n = P2.focus, my = ++P2.seq, c = $("#center");
  if (!n) { c.innerHTML = p2Empty(P2.mods ? "왼쪽에서 모듈을 고르세요" : "불러오는 중…"); return; }
  c.innerHTML = `<div class="p2-gal p2-one">${p2Head(null)}${p2Empty("읽는 중… 처음 여는 큰 모듈은 수십 초")}</div>`;
  const r = await p2Json(p2Url(n, P2.flag, P2.off));
  if (my !== P2.seq || CUR.mode !== "input") return;
  if (r.error) { P2.data = null; c.innerHTML = `<div class="p2-gal p2-one">${p2Head(null)}${p2Empty(nrEsc(r.error))}</div>`; return; }
  if (!P2.cnt[n]) { P2.cnt[n] = { name: n, total: r.total, sus: r.sus, counts: r.counts }; p2DrawLeft(); }   // 요약이 아직이면 이 셋을 연 값으로
  if (P2.flag === "sus" && !r.sus && !P2.off) { P2.flag = "all"; return p2Load(at); }   // 의심이 없으면 전체
  P2.data = r;
  P2.cur = at === "last" ? r.items.length - 1 : Math.max(0, Math.min(at || 0, r.items.length - 1));
  p2DrawCenter();
}
function p2Head(r) {
  const m = P2.by[P2.focus] || { label: P2.focus };
  const seg = `<div class="dt-seg p2-seg" role="group" aria-label="보기">` + [["sus", "의심", r && r.sus], ["all", "전체", r && r.total]].map(([k, l, n]) =>
    `<button type="button" class="${P2.flag === k ? "on" : ""}" data-flag="${k}" aria-pressed="${P2.flag === k}">${l}${n != null ? ` <small>${p2N(n)}</small>` : ""}</button>`).join("") + "</div>";
  const why = r ? [...TV_STRONG, ...TV_SOFT].filter(k => r.counts[k]).map(k =>
    `<button type="button" class="tv-chip ${TV_STRONG.includes(k) ? "s" : "w"}${P2.flag === k ? " on" : ""}" data-flag="${k}" aria-pressed="${P2.flag === k}">${nrEsc(r.labels[k])} <b>${p2N(r.counts[k])}</b></button>`).join("") : "";
  const ok = Object.values(P2X.ok).filter(s => s === P2.focus).length;
  const nav = r ? `<div class="p2-progress"><b>${p2N(P2.off + P2.cur + 1)}</b> / ${p2N(r.sel)}<span class="p2-mut">통과 ${p2N(ok)} · 제외 ${p2N(p2ExN(P2.focus))}</span></div>` : "";
  return `<div class="p2-galh"><div class="p2-gt"><b>${nrEsc(m.label)}</b><span class="p2-nm">${p2Nm(P2.focus)}</span><span class="p2-tags">${p2Tags(P2.focus)}</span></div>` +
    (r ? `<div class="p2-gc">${seg}${why ? `<div class="tv-chips">${why}</div>` : ""}${nav}</div>` : "") + "</div>";
}
function p2CellHtml(it, i) {                              // 아래 줄 한 칸: 의심 = 빨간 점, 통과 = 초록 점, 제외 = 흐림 + 표시
  const ex = P2X.ex[it.p], ok = P2X.ok[it.p];
  return `<button type="button" class="p2-cell${ex ? " ex" : ""}${ok ? " ok" : ""}${i === P2.cur ? " cur" : ""}${it.flags.some(f => TV_STRONG.includes(f)) ? " sus" : ""}" data-i="${i}" title="${nrEsc(it.p.split("/").pop())}">` +
    `<span class="tv-img"><img loading="lazy" alt="" src="${p2Thumb(it.p, 320)}">${p2Boxes(it.boxes)}${ex ? '<span class="p2-exmark">제외</span>' : ""}</span></button>`;
}
function p2BigHtml(it) {                                  // 크게: 라벨 박스 그대로 + 클래스 이름표 · 의심 사유 · 같은 원본 묶음
  const r = P2.data, ex = P2X.ex[it.p], ok = P2X.ok[it.p], pt = p2PhotoTags(it);
  return `<div class="p2-big${ex ? " ex" : ""}"><div class="p2-stage"><span class="p2-bimg"><img alt="" src="${p2Thumb(it.p, 1280)}">${p2Boxes(it.boxes, true)}</span></div>${p2SibsHtml(it)}` +
    `<div class="p2-binfo"><div class="p2-tags">${ex ? '<span class="p2-tag r-flt p2-st">학습 제외</span>' : ok ? '<span class="p2-tag r-pos p2-st">통과</span>' : ""}${p2Why(it, r)}` +
    `${pt.map(t => `<span class="p2-tag c">${nrEsc(t)}</span>`).join("")}<span class="p2-tag s">박스 ${it.boxes.length}</span></div>` +
    `<div class="p2-file" title="${nrEsc(it.p)}"><b>${p2Nm(it.p.split("/").pop())}</b><span class="p2-dir"><bdi>${nrEsc(it.p.split("/").slice(0, -1).join("/"))}</bdi></span></div></div></div>`;   // 경로는 앞을 '…' 로 줄이고 마우스를 올리면 전체
}
function p2SibsHtml(it) {                                 // 같은 원본: 원본(meta.source 폴더에서 이름 꼬리를 뗀 것, 없으면 숨김) + 이 쪽에 있는 다른 변형
  const v = p2Var(it.p); if (!v) return "";
  const r = P2.data, sibs = r.items.map((x, i) => [x, i, p2Var(x.p)]).filter(([, , w]) => w && w.base === v.base).sort((a, b) => a[2].v.split(" ")[0].localeCompare(b[2].v.split(" ")[0]) || a[2].o - b[2].o);   // 안개 → 눈, 약 → 중 → 강
  const src = r.meta && r.meta.source, dir = it.p.split("/").slice(0, -1).join("/");
  const orig = src && dir.includes("/" + P2.focus + "/") ? dir.replace("/" + P2.focus + "/", "/" + src + "/") + "/" + v.base + v.ext : "";
  return `<div class="p2-sibs">${orig ? `<span class="p2-sib o"><img alt="" src="${p2Thumb(orig, 320)}" onerror="this.parentNode.remove()"><span>원본</span></span>` : ""}` +
    sibs.map(([x, i, w]) => `<button type="button" class="p2-sib${x.p === it.p ? " on" : ""}" data-i="${i}"><span class="tv-img"><img alt="" src="${p2Thumb(x.p, 320)}">${p2Boxes(x.boxes)}</span><span>${w.v}</span></button>`).join("") + "</div>";
}
const P2Z = { z: 1, tx: 0, ty: 0 };                      // 큰 사진 확대 · 위치. 모듈을 바꾸면 푼다
let p2SwapSeq = 0;                                        // 사진 바꾸기 순번(늦게 받은 옛 사진이 새 사진을 덮지 않게)
function p2ZoomApply(b) {
  const w = b.offsetWidth, h = b.offsetHeight;
  P2Z.tx = Math.min(0, Math.max(w * (1 - P2Z.z), P2Z.tx)); P2Z.ty = Math.min(0, Math.max(h * (1 - P2Z.z), P2Z.ty));   // 사진 밖 빈 곳이 안 보이게
  if (P2Z.z === 1) P2Z.tx = P2Z.ty = 0;
  b.style.transformOrigin = "0 0"; b.style.transform = P2Z.z === 1 ? "" : `translate(${P2Z.tx}px,${P2Z.ty}px) scale(${P2Z.z})`;
  b.parentNode.classList.toggle("zoomed", P2Z.z > 1);
}
function p2ZoomBind() {                                   // 큰 사진에 휠 확대 · 끌어 이동 · 두 번 눌러 원래대로(10-02 사용자: 전처리와 같게)
  const st = document.querySelector("#p2Big .p2-stage"), b = st && st.querySelector(".p2-bimg"); if (!b) return;
  const img = b.querySelector("img"); if (img && !img.complete) img.addEventListener("load", () => p2ZoomApply(b), { once: true });
  p2ZoomApply(b);
  st.onwheel = e => {
    e.preventDefault();
    const r = b.getBoundingClientRect(), cx = e.clientX - (r.left - P2Z.tx), cy = e.clientY - (r.top - P2Z.ty), z0 = P2Z.z;   // 커서 밑 지점(확대 전 좌표)
    P2Z.z = Math.min(8, Math.max(1, z0 * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
    P2Z.tx = cx - (P2Z.z / z0) * (cx - P2Z.tx); P2Z.ty = cy - (P2Z.z / z0) * (cy - P2Z.ty);
    p2ZoomApply(b);
  };
  st.onmousedown = e => {
    if (P2Z.z === 1 || e.button !== 0) return;
    e.preventDefault();
    const x0 = e.clientX - P2Z.tx, y0 = e.clientY - P2Z.ty;
    const mv = ev => { P2Z.tx = ev.clientX - x0; P2Z.ty = ev.clientY - y0; p2ZoomApply(b); };
    const up = () => { removeEventListener("mousemove", mv); removeEventListener("mouseup", up); };
    addEventListener("mousemove", mv); addEventListener("mouseup", up);
  };
  st.ondblclick = () => { P2Z.z = 1; p2ZoomApply(b); };
}
function p2DrawCenter() {
  const r = P2.data, it = r.items[P2.cur];
  $("#center").innerHTML = `<div class="p2-gal p2-one">${p2Head(r)}${it ? `<div id="p2Big">${p2BigHtml(it)}</div>${p2ActsHtml(it)}<div class="p2-strip" id="p2Strip">${r.items.map(p2CellHtml).join("")}</div>` : p2Empty("이 조건인 사진 없음")}</div>`;
  p2ZoomBind(); p2StripScroll();
  p2Preload();
}
function p2ActsHtml(it) {
  const ex = P2X.ex[it.p];
  return `<div class="p2-acts" id="p2Acts">${P2.msg ? `<span class="p2-msg" title="${nrEsc(P2.msgTip || "")}">${nrEsc(P2.msg)}</span>` : ""}<button type="button" class="p2-nav" data-mv="-1" aria-label="이전 사진">‹</button>` +
    `<button type="button" class="p2-okb" data-mark="ok">통과<kbd>O</kbd></button><button type="button" class="p2-exb${ex ? " on" : ""}" data-mark="ex">${ex ? "제외 취소" : "제외"}<kbd>X</kbd></button>` +
    `<button type="button" class="p2-nav" data-mv="1" aria-label="다음 사진">›</button>${P2X.undo.length ? '<button type="button" class="p2-undo" data-undo="1">되돌리기<kbd>Z</kbd></button>' : ""}</div>`;
}
function p2StripScroll() { const s = document.getElementById("p2Strip"), e = s && s.querySelector(".cur"); if (e) s.scrollLeft = e.offsetLeft - s.clientWidth / 2 + e.offsetWidth / 2; }
function p2Preload() { const r = P2.data; if (r) [1, 2, -1].forEach(k => { const n = r.items[P2.cur + k]; if (n) new Image().src = p2Thumb(n.p, 1280); }); }   // 앞뒤 사진 미리 받기
function p2Show() {                                       // 고른 사진 · 표시가 바뀜: 필요한 곳만 다시
  const r = P2.data, it = r && r.items[P2.cur], big = document.getElementById("p2Big");
  if (!it || !big) return p2DrawLeftMarks();
  document.querySelectorAll(".p2-cell").forEach(e => { const x = r.items[+e.dataset.i]; e.classList.toggle("cur", +e.dataset.i === P2.cur); e.classList.toggle("ex", !!P2X.ex[x.p]); e.classList.toggle("ok", !!P2X.ok[x.p]);
    const im = e.querySelector(".tv-img"), mk = im.querySelector(".p2-exmark"); if (P2X.ex[x.p] && !mk) im.insertAdjacentHTML("beforeend", '<span class="p2-exmark">제외</span>'); if (!P2X.ex[x.p] && mk) mk.remove(); });
  const h = document.querySelector(".p2-galh"); if (h) h.outerHTML = p2Head(r);
  $("#p2Acts").outerHTML = p2ActsHtml(it);
  const my = ++p2SwapSeq, pre = new Image();                // 새 사진을 다 받은 뒤 바꿔 끼운다(10-02: 넘길 때 사진 칸이 잠깐 비던 것)
  const swap = () => { if (my !== p2SwapSeq || !big.isConnected) return; big.innerHTML = p2BigHtml(it); p2ZoomBind(); };
  pre.onload = pre.onerror = swap; pre.src = p2Thumb(it.p, 1280); if (pre.complete) swap();
  p2StripScroll(); p2Preload(); p2DrawLeftMarks();
}
function p2DrawLeftMarks() {                              // 제외 수만 바꾼다(목록 순서 · 스크롤은 그대로)
  const b = document.querySelector(".p2-exbtn b"); if (b) b.textContent = P2.exOk ? p2N(Object.keys(P2X.ex).length) : "-";
  document.querySelectorAll("#p2Left .p2-mod").forEach(m => {
    const row = m.querySelector(".p2-mr"), nx = p2ExN(m.dataset.n), e = row.querySelector(".p2-exn");
    if (nx && e) e.textContent = "제외 " + nx; else if (nx) row.insertAdjacentHTML("beforeend", `<span class="p2-exn">제외 ${nx}</span>`); else if (e) e.remove();
  });
}

// ---------- 훑기 · 표시 ----------
async function p2Move(d) {
  const r = P2.data; if (!r) return;
  const i = P2.cur + d;
  if (i >= r.items.length) { if (P2.off + P2_PAGE < r.sel) { P2.off += P2_PAGE; await p2Load(0); } return; }   // 쪽 끝이면 다음 쪽
  if (i < 0) { if (P2.off > 0) { P2.off = Math.max(0, P2.off - P2_PAGE); await p2Load("last"); } return; }
  P2.cur = i; p2Show();
}
function p2Mark(kind) {                                   // ex = 학습 제외(다시 누르면 취소), ok = 통과. 표시하면 다음 사진으로
  const r = P2.data, it = r && r.items[P2.cur]; if (!it) return;
  const was = P2X.ex[it.p] || null;
  P2X.undo.push({ p: it.p, ex: was, ok: P2X.ok[it.p] || null, focus: P2.focus, flag: P2.flag, off: P2.off, cur: P2.cur });
  let next = true;
  if (kind === "ex" && was) { delete P2X.ex[it.p]; next = false; p2ExPost(it.p, was.set, was.why, false, was); }
  else if (kind === "ex") {
    const why = it.flags.map(f => r.labels[f]);
    P2X.ex[it.p] = { set: P2.focus, path: it.p, why, at: p2Now() }; delete P2X.ok[it.p];
    p2ExPost(it.p, P2.focus, why, true, null);
  } else {
    P2X.ok[it.p] = P2.focus;
    if (was) { delete P2X.ex[it.p]; p2ExPost(it.p, was.set, was.why, false, was); }
  }
  p2SaveOk();
  if (next && P2.cur < r.items.length - 1 || next && P2.off + P2_PAGE < r.sel) p2Move(1); else p2Show();
}
function p2Undo() {
  const u = P2X.undo.pop(); if (!u) return;
  const now = P2X.ex[u.p] || null;
  if (u.ex && !now) { P2X.ex[u.p] = u.ex; p2ExPost(u.p, u.ex.set, u.ex.why, true, null); }
  else if (!u.ex && now) { delete P2X.ex[u.p]; p2ExPost(u.p, now.set, now.why, false, now); }
  if (u.ok) P2X.ok[u.p] = u.ok; else delete P2X.ok[u.p];
  p2SaveOk();
  if (u.focus === P2.focus && u.flag === P2.flag && u.off === P2.off) { P2.cur = u.cur; p2Show(); }
  else { P2.focus = u.focus; P2.flag = u.flag; P2.off = u.off; p2SaveUi(); p2DrawLeft(); p2Load(u.cur); }
}
function p2ExList() {                                     // 학습 제외 목록(떠 있는 창). 줄마다 되돌리기
  let pop = document.getElementById("p2ExPop");
  if (!pop) {
    pop = el("div", "p2-pop"); pop.id = "p2ExPop"; pop.setAttribute("popover", ""); document.body.appendChild(pop);
    pop.addEventListener("click", e => {
      const x = e.target.closest("[data-unex],[data-pclose]"); if (!x) return;
      if (x.dataset.pclose) { pop.hidePopover(); return; }
      const p = x.dataset.unex, was = P2X.ex[p]; if (!was) return;
      delete P2X.ex[p]; p2ExList(); p2DrawLeftMarks(); if (P2.data) p2Show();
      p2ExPost(p, was.set, was.why, false, was);
    });
  }
  const by = {};
  Object.entries(P2X.ex).forEach(([p, v]) => (by[v.set] = by[v.set] || []).push([p, v]));
  pop.innerHTML = `<div class="p2-poph"><b>학습 제외 ${p2N(Object.keys(P2X.ex).length)}</b>${P2.exOk ? "" : '<span class="p2-mut">서버 반영 전</span>'}<span class="p2-grow"></span><button type="button" class="p2-sbtn" data-pclose="1">닫기</button></div>` +
    (Object.keys(by).length ? Object.entries(by).map(([s, rows]) => `<div class="p2-exg"><div class="p2-exh">${nrEsc((P2.by[s] || {}).label || s)}<span class="p2-nm">${p2Nm(s)}</span><span class="p2-mut">${rows.length}</span></div>` +
      rows.map(([p, v]) => `<div class="p2-exr"><img alt="" loading="lazy" src="${p2Thumb(p, 320)}"><span class="p2-exf"><b>${p2Nm(p.split("/").pop())}</b><span class="p2-tags">${(v.why || []).map(w => `<span class="p2-tag r-flt">${nrEsc(w)}</span>`).join("")}<span class="p2-mut">${nrEsc(v.at || "")}</span></span></span>` +
        `<button type="button" class="p2-sbtn" data-unex="${nrEsc(p)}">되돌리기</button></div>`).join("") + "</div>").join("") : p2Empty("제외한 사진 없음"));
  if (!pop.matches(":popover-open")) pop.showPopover();
}

// ---------- 들어가기 · 나가기(main.js applyMode 가 부른다) ----------
function p2Render() {
  if (P2.focus && !(P2.by[P2.focus] && p2Items().includes(P2.by[P2.focus].item))) P2.focus = "";   // 항목 필터 밖이거나 목록에서 빠진 모듈
  p2DrawLeft();
  if (!P2.focus) { p2PickTop(); if (!P2.focus) $("#center").innerHTML = p2Empty("쓰러짐 학습 데이터 모듈 없음"); }
  else if (P2.data && P2.data.name === P2.focus) p2DrawCenter();
  else p2Load(0);
}
async function p2Enter() {                                // 모듈 목록 · 학습 제외 · 요약을 같이 받은 뒤 그린다(처음 고르는 모듈 = 오류 의심이 가장 많은 것)
  $("#center").innerHTML = p2Empty("불러오는 중…");
  if (!document.getElementById("p2Left")) { const pl = el("div"); pl.id = "p2Left"; $(".left").appendChild(pl); }
  p2DrawLeft();
  const [j] = await Promise.all([P2.mods ? {} : p2Json("/api/data_modules"), p2ExLoad(), p2SumGet()]);
  if (!P2.mods) {
    const list = j.error ? null : (Array.isArray(j) ? j : j.modules);
    if (list) { P2.mods = list.map(m => Object.assign({}, m)); P2.mods.forEach(m => { P2.by[m.name] = m; }); P2.modErr = ""; }
    else P2.modErr = j.error || "없음";
  }
  if (CUR.mode !== "input") return;
  if (!P2.mods) { p2DrawLeft(); $("#center").innerHTML = p2Empty("모듈 목록 " + nrEsc(P2.modErr)); return; }
  p2Render();
  p2SumNext();
}
function p2Leave() {
  clearTimeout(P2.sumT);
  const pl = document.getElementById("p2Left"); if (pl) pl.remove();
  const p = document.getElementById("p2ExPop"); if (p && p.matches(":popover-open")) p.hidePopover();
}

// ---------- 동작 ----------
document.querySelector(".main").addEventListener("click", e => {
  if (CUR.mode !== "input") return;
  const t = e.target;
  let x;
  if ((x = t.closest("[data-exlist]"))) { p2ExList(); return; }
  if ((x = t.closest(".p2-mod[data-n]"))) { if (x.dataset.n !== P2.focus) p2Pick(x.dataset.n); return; }
  if ((x = t.closest("[data-flag]"))) { if (P2.flag !== x.dataset.flag) { P2.flag = x.dataset.flag; P2.off = 0; p2Load(0); } return; }
  if ((x = t.closest("[data-mv]"))) { p2Move(+x.dataset.mv); return; }
  if ((x = t.closest("[data-mark]"))) { p2Mark(x.dataset.mark); return; }
  if ((x = t.closest("[data-undo]"))) { p2Undo(); return; }
  if ((x = t.closest(".p2-cell, .p2-sib[data-i]"))) { P2.cur = +x.dataset.i; p2Show(); }
});
document.addEventListener("keydown", e => {                // 키보드만으로 훑기: ← → 사진 · X 제외 · O 통과 · Z 되돌리기
  if (CUR.mode !== "input" || !P2.data || e.altKey || e.metaKey) return;
  const tg = e.target.tagName;
  if (tg === "INPUT" || tg === "SELECT" || tg === "TEXTAREA") return;
  if (document.querySelector("[popover]:popover-open")) return;     // 학습 제외 목록 · 알림 창이 떠 있으면 안 먹는다
  const k = e.code, ctrl = e.ctrlKey;
  if (ctrl && k !== "KeyZ") return;
  if (k === "ArrowRight" || k === "ArrowLeft") { e.preventDefault(); p2Move(k === "ArrowRight" ? 1 : -1); }
  else if (k === "KeyX") { e.preventDefault(); p2Mark("ex"); }
  else if (k === "KeyO") { e.preventDefault(); p2Mark("ok"); }
  else if (k === "KeyZ") { e.preventDefault(); p2Undo(); }
});
