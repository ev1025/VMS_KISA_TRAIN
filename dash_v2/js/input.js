// dash_v2/js/input.js: 2단계 '입력 데이터' 탭(2026-10-02 사용자 확정 시안 P2-4 '한 장씩 점검'). main.js 앞에 로드, main.js · trainview.js 함수를 실행 시점에 부른다
//   목적: 학습용으로 구성된 데이터(모듈)를 하나씩 확인하고 잘못된 라벨을 걸러 낸다. 여기서 데이터를 만들지 않는다
//   왼쪽 = 모듈 목록(GET /api/data_modules = configs/data_modules.yaml) · 오류 의심 수(GET /api/tv_summary, 서버가 디스크에 기억하고 세는 중이면 pending)
//   가운데 = 큰 사진 한 장 + 통과(O) · 제외(X) · ← → · 되돌리기(Z) + 아래 줄. 사진 · 라벨 · 의심 사유 = /api/tv_set · /api/tv_thumb(dash_v2/trainview.py)
//   학습 제외 = 서버 저장(GET · POST /api/train_exclude → data/학습데이터/손라벨/train_exclude.json, ML 이 걸러 내기로 쓴다). 통과 표시는 이 브라우저에만
//   박스 지우기 = 큰 사진에서 박스를 눌러 고르고 D · Delete. 서버 기록(GET · POST /api/train_fix → 손라벨/train_label_fix.json)만 하고 모듈 라벨 파일은 안 고친다(ML 이 반영)
"use strict";
const P2 = { mods: null, modErr: "", by: {}, cnt: {}, pending: [], sumOk: true, sumT: 0, msg: "", msgTip: "", focus: "", flag: "sus", off: 0, data: null, cur: 0, seq: 0, lbTop: 0, exOk: true, fixOk: true, box: -1, boxFor: "", md: null };
const P2_PAGE = 60;
const P2X = { ex: {}, ok: {}, fx: {}, undo: [] };         // ex = 학습 제외 {경로: {set, path, name, why, by, at}}(서버), ok = 통과 {경로: 셋}(이 브라우저), fx = 지운 박스 {p2FixKey: {set, path, name, box, why, by, at}}(서버)
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
const p2FixKey = (p, b) => p + "|" + b.map(v => Math.round(v * 1e5) / 1e5).join(",");   // 같은 박스 = 같은 경로 + 값(소수 5자리), 서버와 같은 규칙
const p2Del = (it, b) => !!P2X.fx[p2FixKey(it.p, b)];
function p2Iou(a, b) {                                    // trainview._iou 와 같은 계산(YOLO cx cy w h)
  const iw = Math.max(0, Math.min(a[1] + a[3] / 2, b[1] + b[3] / 2) - Math.max(a[1] - a[3] / 2, b[1] - b[3] / 2));
  const ih = Math.max(0, Math.min(a[2] + a[4] / 2, b[2] + b[4] / 2) - Math.max(a[2] - a[4] / 2, b[2] - b[4] / 2)), u = a[3] * a[4] + b[3] * b[4] - iw * ih;
  return u > 0 ? iw * ih / u : 0;
}
function p2BoxBad(it) {                                   // 박스마다 의심 사유 이름표. 기준 = trainview.check 와 같고, 서버가 그 사진에 단 사유(it.flags)만 본다
  const B = it.boxes, f = it.flags, L = (P2.data || {}).labels || {}, ncls = (P2_CLS[(P2.by[P2.focus] || {}).item] || []).length || 1, out = B.map(() => []);
  const add = (i, k) => { if (f.includes(k)) out[i].push(L[k] || k); };
  B.forEach((b, i) => {
    if (b[3] <= 0 || b[4] <= 0 || b[1] - b[3] / 2 < -0.01 || b[1] + b[3] / 2 > 1.01 || b[2] - b[4] / 2 < -0.01 || b[2] + b[4] / 2 > 1.01) add(i, "out");
    if (!Number.isInteger(b[0]) || b[0] < 0 || b[0] >= ncls) add(i, "cls");
    if ((b[3] > 0 && b[3] < 0.008) || (b[4] > 0 && b[4] < 0.008)) add(i, "tiny");     // 1280 기준 10px 미만
    if (b[3] * b[4] > 0.85) add(i, "huge");
    if (B.slice(0, i).some(a => a[0] === b[0] && p2Iou(a, b) >= 0.6)) add(i, "dup");   // 겹친 쌍 중 뒤 박스
  });
  return out;
}
function p2Boxes(it, big) {                               // 라벨 파일 박스 그대로(YOLO cx cy w h), 클래스 색. 지운 박스 = 점선
  if (!it.boxes.length) return "";                        // big = 큰 사진: 의심 박스 빨강 + 사유 이름표, 지운 박스 ×, 고른 박스 흰 점선
  const bad = big ? p2BoxBad(it) : [], R = (b, a) => `<rect x="${b[1] - b[3] / 2}" y="${b[2] - b[4] / 2}" width="${b[3]}" height="${b[4]}" fill="none" vector-effect="non-scaling-stroke" ${a}/>`;
  const svg = it.boxes.map((b, i) => {
    const del = p2Del(it, b), sus = big && bad[i].length;
    return R(b, `stroke="${del || sus ? "#f85149" : p2Cls(b[0])[1]}" stroke-width="${sus && !del ? 3 : 2}"${del ? ' stroke-dasharray="5 4"' : ""}`) +
      (big && i === P2.box ? R(b, 'stroke="#fff" stroke-width="2" stroke-dasharray="4 3"') : "");
  }).join("");
  return `<svg class="tv-svg" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">${svg}</svg>` + (big ? it.boxes.map((b, i) => {
    const del = p2Del(it, b), at = `left:${((b[1] - b[3] / 2) * 100).toFixed(2)}%;top:${((b[2] - b[4] / 2) * 100).toFixed(2)}%`;
    return `<span class="p2-bl${b[2] - b[4] / 2 < 0.05 ? " in" : ""}${bad[i].length ? " bad" : ""}${del ? " del" : ""}" style="${at}${bad[i].length ? "" : ";background:" + p2Cls(b[0])[1]}">${p2Cls(b[0])[0]}${bad[i].length ? " · " + nrEsc(bad[i].join(", ")) : ""}</span>` +
      (del ? `<span class="p2-bx" style="left:${(b[1] * 100).toFixed(2)}%;top:${(b[2] * 100).toFixed(2)}%">×</span>` : "");
  }).join("") : "");
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
    if (!P2.exOk && CUR.mode === "input") { P2.exOk = true; p2DrawLeft(); }   // 서버 반영 전이던 것이 이제 됨: 왼쪽 머리 글도 다시
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

async function p2FixLoad() {
  const j = await p2Json("/api/train_fix");
  P2.fixOk = !j.error;
  if (!j.error) P2X.fx = Object.fromEntries((j.items || []).filter(x => Array.isArray(x.box)).map(x => [p2FixKey(x.path, x.box), x]));
}
async function p2FixPost(x, on, prev) {                   // 박스 지우기 넣기 · 빼기. 화면은 먼저 바꾸고, 저장 못 하면 되돌린다
  const key = p2FixKey(x.path, x.box);
  const j = await p2Json("/api/train_fix", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ set: x.set, path: x.path, box: x.box, why: x.why, on }) });
  if (j.ok) {
    const y = (j.items || []).find(z => Array.isArray(z.box) && p2FixKey(z.path, z.box) === key);
    if (y) P2X.fx[key] = y; else delete P2X.fx[key];
    if (!P2.fixOk && CUR.mode === "input") { P2.fixOk = true; p2DrawLeft(); }
    P2.fixOk = true; P2.msg = "";
  } else {
    if (prev) P2X.fx[key] = prev; else delete P2X.fx[key];
    P2.msg = "라벨 고침 저장 안 됨" + (j.old ? " · 서버 반영 전" : "");
    P2.msgTip = j.err || j.error || "";
  }
  if (CUR.mode !== "input") return;
  p2BoxDraw();
  const pop = document.getElementById("p2FixPop"); if (pop && pop.matches(":popover-open")) p2FixList();
}

// ---------- 왼쪽: 모듈 목록(오류 의심 많은 순) ----------
const p2ExN = set => Object.values(P2X.ex).filter(x => x.set === set).length;
const p2FxN = set => Object.values(P2X.fx).filter(x => x.set === set).length;
function p2Sorted(item) {
  const k = m => { const c = P2.cnt[m.name]; return c && !c.error ? c.sus : -1; };
  return p2Mods().filter(m => m.item === item).sort((a, b) => k(b) - k(a) || b.count - a.count);
}
function p2ModHtml(m) {
  const c = P2.cnt[m.name], nx = p2ExN(m.name), nf = p2FxN(m.name);
  const sus = c ? (c.error ? `<span class="p2-sus wait" title="${nrEsc(c.error)}">사진 없음</span>` : `<span class="p2-sus${c.sus ? "" : " zero"}">의심 ${p2N(c.sus)}</span>`)
    : P2.pending.includes(m.name) ? '<span class="p2-sus wait">세는 중</span>' : "";
  return `<button type="button" class="p2-mod${m.name === P2.focus ? " on" : ""}" data-n="${nrEsc(m.name)}"><span class="p2-mb"><span class="p2-ml">${nrEsc(m.label)}</span>` +
    `<span class="p2-nm">${p2Nm(m.name)}</span><span class="p2-tags">${p2Tags(m.name)}</span></span>` +
    `<span class="p2-mr">${sus}<span class="p2-cnt">${p2N(c && c.total != null ? c.total : m.count)}장</span>${nx ? `<span class="p2-exn">제외 ${nx}</span>` : ""}${nf ? `<span class="p2-fxn">고침 ${nf}</span>` : ""}</span></button>`;
}
function p2DrawLeft() {
  const pl = document.getElementById("p2Left"); if (!pl) return;
  const items = p2Items(), nx = Object.keys(P2X.ex).length, all = p2Mods();
  const note = !P2.mods ? "" : !P2.exOk || !P2.fixOk ? `<span class="p2-mut p2-prog" title="${!P2.exOk ? "GET /api/train_exclude " : ""}${!P2.fixOk ? "GET /api/train_fix " : ""}없음">서버 반영 전</span>`
    : !P2.sumOk ? '<span class="p2-mut p2-prog" title="GET /api/tv_summary 없음">의심 수 서버 반영 전</span>'
    : P2.pending.length ? `<span class="p2-mut p2-prog">세는 중 ${all.length - P2.pending.length} / ${all.length}</span>` : "";
  pl.innerHTML = `<div class="p2-lh"><button type="button" class="p2-exbtn" data-exlist="1">학습 제외 <b>${P2.exOk ? p2N(nx) : "-"}</b></button>` +
    `<button type="button" class="p2-exbtn p2-fxbtn" data-fixlist="1">라벨 고침 <b>${P2.fixOk ? p2N(Object.keys(P2X.fx).length) : "-"}</b></button>${note}</div>` +
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
    `<span class="tv-img"><img loading="lazy" alt="" src="${p2Thumb(it.p, 320)}">${p2Boxes(it)}${ex ? '<span class="p2-exmark">제외</span>' : ""}</span></button>`;
}
function p2BigHtml(it) {                                  // 크게: 라벨 박스 그대로 + 클래스 이름표 · 의심 사유 · 같은 원본 묶음
  const r = P2.data, ex = P2X.ex[it.p], ok = P2X.ok[it.p], pt = p2PhotoTags(it);
  return `<div class="p2-big${ex ? " ex" : ""}" data-p="${nrEsc(it.p)}"><div class="p2-stage"><span class="p2-bimg"><img alt="" src="${p2Thumb(it.p, 1280)}"><span class="p2-ov">${p2Boxes(it, true)}</span></span></div>${p2SibsHtml(it)}` +
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
    sibs.map(([x, i, w]) => `<button type="button" class="p2-sib${x.p === it.p ? " on" : ""}" data-i="${i}"><span class="tv-img"><img alt="" src="${p2Thumb(x.p, 320)}">${p2Boxes(x)}</span><span>${w.v}</span></button>`).join("") + "</div>";
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
    P2.md = [e.clientX, e.clientY];
    if (P2Z.z === 1 || e.button !== 0) return;
    e.preventDefault();
    const x0 = e.clientX - P2Z.tx, y0 = e.clientY - P2Z.ty;
    const mv = ev => { P2Z.tx = ev.clientX - x0; P2Z.ty = ev.clientY - y0; p2ZoomApply(b); };
    const up = () => { removeEventListener("mousemove", mv); removeEventListener("mouseup", up); };
    addEventListener("mousemove", mv); addEventListener("mouseup", up);
  };
  st.ondblclick = () => { P2Z.z = 1; p2ZoomApply(b); };
  st.onclick = e => {                                     // 박스 고르기: 끌어 이동과 구분(누른 곳에서 4px 미만 움직였을 때만)
    if (P2.md && Math.hypot(e.clientX - P2.md[0], e.clientY - P2.md[1]) >= 4) return;
    const it = P2.data && P2.data.items[P2.cur]; if (!it || st.closest(".p2-big").dataset.p !== it.p) return;
    const r = b.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height, px = 6 / r.width, py = 6 / r.height;
    let pick = -1, area = Infinity;                        // 누른 곳을 덮는 박스 중 가장 작은 것(가장자리 6px 여유), 없으면 고르기 풀기
    it.boxes.forEach((q, i) => { if (Math.abs(x - q[1]) <= q[3] / 2 + px && Math.abs(y - q[2]) <= q[4] / 2 + py && q[3] * q[4] < area) { pick = i; area = q[3] * q[4]; } });
    P2.box = pick; p2BoxDraw();
  };
}
function p2BoxInit(it) {                                  // 사진이 바뀌면 첫 의심 박스(지우지 않은 것)를 미리 고른다 → D 한 번이면 지움
  if (!it || P2.boxFor === it.p) return;
  P2.boxFor = it.p;
  const bad = p2BoxBad(it);
  P2.box = it.boxes.findIndex((b, i) => bad[i].length && !p2Del(it, b));
}
function p2BoxDraw() {                                    // 박스 고르기 · 지우기가 바뀜: 큰 사진 겹침 · 단추 줄 · 아래 줄 칸 · 왼쪽 수만 다시(사진 · 확대는 그대로)
  const r = P2.data, it = r && r.items[P2.cur], big = document.querySelector("#p2Big .p2-big");
  if (it && big && big.dataset.p === it.p) big.querySelector(".p2-ov").innerHTML = p2Boxes(it, true);
  const a = document.getElementById("p2Acts"); if (a && it) a.outerHTML = p2ActsHtml(it);
  if (r) document.querySelectorAll("#p2Strip .p2-cell").forEach(c => { const x = r.items[+c.dataset.i], s = c.querySelector(".tv-svg"); if (x && s) s.outerHTML = p2Boxes(x); });
  p2DrawLeftMarks();
}
function p2DrawCenter() {
  const r = P2.data, it = r.items[P2.cur];
  p2BoxInit(it);
  $("#center").innerHTML = `<div class="p2-gal p2-one">${p2Head(r)}${it ? `<div id="p2Big">${p2BigHtml(it)}</div>${p2ActsHtml(it)}<div class="p2-strip" id="p2Strip">${r.items.map(p2CellHtml).join("")}</div>` : p2Empty("이 조건인 사진 없음")}</div>`;
  p2ZoomBind(); p2StripScroll();
  p2Preload();
}
function p2ActsHtml(it) {
  const ex = P2X.ex[it.p], b = it.boxes[P2.box];
  return `<div class="p2-acts" id="p2Acts">${P2.msg ? `<span class="p2-msg" title="${nrEsc(P2.msgTip || "")}">${nrEsc(P2.msg)}</span>` : ""}<button type="button" class="p2-nav" data-mv="-1" aria-label="이전 사진">‹</button>` +
    `<button type="button" class="p2-okb" data-mark="ok">통과<kbd>O</kbd></button><button type="button" class="p2-exb${ex ? " on" : ""}" data-mark="ex">${ex ? "제외 취소" : "제외"}<kbd>X</kbd></button>` +
    `<button type="button" class="p2-nav" data-mv="1" aria-label="다음 사진">›</button><span class="p2-actr">` +
    `<button type="button" class="p2-undo p2-bdel" data-bdel="1"${b ? "" : ' disabled title="큰 사진에서 박스를 누르면 고름"'}>${b && p2Del(it, b) ? "지우기 취소" : "박스 지우기"}<kbd>D</kbd></button>` +
    `${P2X.undo.length ? '<button type="button" class="p2-undo" data-undo="1">되돌리기<kbd>Z</kbd></button>' : ""}</span></div>`;
}
function p2StripScroll() { const s = document.getElementById("p2Strip"), e = s && s.querySelector(".cur"); if (e) s.scrollLeft = e.offsetLeft - s.clientWidth / 2 + e.offsetWidth / 2; }
function p2Preload() { const r = P2.data; if (r) [1, 2, -1].forEach(k => { const n = r.items[P2.cur + k]; if (n) new Image().src = p2Thumb(n.p, 1280); }); }   // 앞뒤 사진 미리 받기
function p2Show() {                                       // 고른 사진 · 표시가 바뀜: 필요한 곳만 다시
  const r = P2.data, it = r && r.items[P2.cur], big = document.getElementById("p2Big");
  if (!it || !big) return p2DrawLeftMarks();
  p2BoxInit(it);
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
    const row = m.querySelector(".p2-mr");
    [["p2-exn", "제외 ", p2ExN(m.dataset.n)], ["p2-fxn", "고침 ", p2FxN(m.dataset.n)]].forEach(([c, t, n]) => {
      const e = row.querySelector("." + c);
      if (n && e) e.textContent = t + n; else if (n) row.insertAdjacentHTML("beforeend", `<span class="${c}">${t}${n}</span>`); else if (e) e.remove();
    });
  });
  const f = document.querySelector(".p2-fxbtn b"); if (f) f.textContent = P2.fixOk ? p2N(Object.keys(P2X.fx).length) : "-";
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
function p2BoxDel() {                                    // 고른 박스 지움 표시(다시 누르면 취소). 기록만 하고 라벨 파일은 안 고친다
  const r = P2.data, it = r && r.items[P2.cur], b = it && it.boxes[P2.box]; if (!b) return;
  const key = p2FixKey(it.p, b), was = P2X.fx[key] || null;
  P2X.undo.push({ kind: "box", p: it.p, key, bi: P2.box, was, focus: P2.focus, flag: P2.flag, off: P2.off, cur: P2.cur });
  if (was) { delete P2X.fx[key]; p2FixPost(was, false, was); }
  else { const x = { set: P2.focus, path: it.p, name: it.p.split("/").pop(), box: b, why: p2BoxBad(it)[P2.box], at: p2Now() }; P2X.fx[key] = x; p2FixPost(x, true, null); }
  p2BoxDraw();
}
function p2Undo() {
  const u = P2X.undo.pop(); if (!u) return;
  if (u.kind === "box") {                                  // 박스 지우기 되돌리기(되돌린 박스를 다시 고른 채로)
    const now = P2X.fx[u.key] || null;
    if (u.was && !now) { P2X.fx[u.key] = u.was; p2FixPost(u.was, true, null); }
    else if (!u.was && now) { delete P2X.fx[u.key]; p2FixPost(now, false, now); }
    P2.boxFor = u.p; P2.box = u.bi;
  } else {
    const now = P2X.ex[u.p] || null;
    if (u.ex && !now) { P2X.ex[u.p] = u.ex; p2ExPost(u.p, u.ex.set, u.ex.why, true, null); }
    else if (!u.ex && now) { delete P2X.ex[u.p]; p2ExPost(u.p, now.set, now.why, false, now); }
    if (u.ok) P2X.ok[u.p] = u.ok; else delete P2X.ok[u.p];
    p2SaveOk();
  }
  if (u.focus === P2.focus && u.flag === P2.flag && u.off === P2.off) { P2.cur = u.cur; p2Show(); p2BoxDraw(); }
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

function p2FixList() {                                    // 라벨 고침 목록(떠 있는 창): 모듈별, 줄마다 사진(지운 박스 점선) · 클래스 · 사유 · 시각 · 되돌리기
  let pop = document.getElementById("p2FixPop");
  if (!pop) {
    pop = el("div", "p2-pop"); pop.id = "p2FixPop"; pop.setAttribute("popover", ""); document.body.appendChild(pop);
    pop.addEventListener("click", e => {
      const x = e.target.closest("[data-unfix],[data-pclose]"); if (!x) return;
      if (x.dataset.pclose) { pop.hidePopover(); return; }
      const was = P2X.fx[x.dataset.unfix]; if (!was) return;
      delete P2X.fx[x.dataset.unfix]; p2FixList(); p2BoxDraw();
      p2FixPost(was, false, was);
    });
  }
  const by = {}, all = Object.entries(P2X.fx);
  all.forEach(([k, v]) => (by[v.set] = by[v.set] || []).push([k, v]));
  const cls = (s, c) => ((P2_CLS[(P2.by[s] || {}).item] || [])[c] || ["번호 " + c])[0];
  pop.innerHTML = `<div class="p2-poph"><b>라벨 고침 ${p2N(all.length)}</b><span class="p2-mut">지운 박스</span>${P2.fixOk ? "" : '<span class="p2-mut">서버 반영 전</span>'}<span class="p2-grow"></span><button type="button" class="p2-sbtn" data-pclose="1">닫기</button></div>` +
    (all.length ? Object.entries(by).map(([s, rows]) => `<div class="p2-exg"><div class="p2-exh">${nrEsc((P2.by[s] || {}).label || s)}<span class="p2-nm">${p2Nm(s)}</span><span class="p2-mut">${rows.length}</span></div>` +
      rows.map(([k, v]) => `<div class="p2-exr"><span class="tv-img"><img alt="" loading="lazy" src="${p2Thumb(v.path, 320)}"><svg class="tv-svg" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">` +
        `<rect x="${v.box[1] - v.box[3] / 2}" y="${v.box[2] - v.box[4] / 2}" width="${v.box[3]}" height="${v.box[4]}" fill="none" stroke="#f85149" stroke-width="2" stroke-dasharray="5 4" vector-effect="non-scaling-stroke"/></svg></span>` +
        `<span class="p2-exf"><b>${p2Nm(v.path.split("/").pop())}</b><span class="p2-tags"><span class="p2-tag s">${nrEsc(cls(s, v.box[0]))}</span>${(v.why || []).map(w => `<span class="p2-tag r-flt">${nrEsc(w)}</span>`).join("")}<span class="p2-mut">${nrEsc(v.at || "")}</span></span></span>` +
        `<button type="button" class="p2-sbtn" data-unfix="${nrEsc(k)}">되돌리기</button></div>`).join("") + "</div>").join("") : p2Empty("지운 박스 없음"));
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
  const [j] = await Promise.all([P2.mods ? {} : p2Json("/api/data_modules"), p2ExLoad(), p2FixLoad(), p2SumGet()]);
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
  ["p2ExPop", "p2FixPop"].forEach(id => { const p = document.getElementById(id); if (p && p.matches(":popover-open")) p.hidePopover(); });
}

// ---------- 동작 ----------
document.querySelector(".main").addEventListener("click", e => {
  if (CUR.mode !== "input") return;
  const t = e.target;
  let x;
  if ((x = t.closest("[data-exlist]"))) { p2ExList(); return; }
  if ((x = t.closest("[data-fixlist]"))) { p2FixList(); return; }
  if ((x = t.closest("[data-bdel]"))) { p2BoxDel(); return; }
  if ((x = t.closest(".p2-mod[data-n]"))) { if (x.dataset.n !== P2.focus) p2Pick(x.dataset.n); return; }
  if ((x = t.closest("[data-flag]"))) { if (P2.flag !== x.dataset.flag) { P2.flag = x.dataset.flag; P2.off = 0; p2Load(0); } return; }
  if ((x = t.closest("[data-mv]"))) { p2Move(+x.dataset.mv); return; }
  if ((x = t.closest("[data-mark]"))) { p2Mark(x.dataset.mark); return; }
  if ((x = t.closest("[data-undo]"))) { p2Undo(); return; }
  if ((x = t.closest(".p2-cell, .p2-sib[data-i]"))) { P2.cur = +x.dataset.i; p2Show(); }
});
document.addEventListener("keydown", e => {                // 키보드만으로 훑기: ← → 사진 · X 제외 · O 통과 · D · Delete 박스 지우기 · Z 되돌리기
  if (CUR.mode !== "input" || !P2.data || e.altKey || e.metaKey) return;
  const tg = e.target.tagName;
  if (tg === "INPUT" || tg === "SELECT" || tg === "TEXTAREA") return;
  if (document.querySelector("[popover]:popover-open")) return;     // 학습 제외 목록 · 알림 창이 떠 있으면 안 먹는다
  const k = e.code, ctrl = e.ctrlKey;
  if (ctrl && k !== "KeyZ") return;
  if (k === "ArrowRight" || k === "ArrowLeft") { e.preventDefault(); p2Move(k === "ArrowRight" ? 1 : -1); }
  else if (k === "KeyX") { e.preventDefault(); p2Mark("ex"); }
  else if (k === "KeyO") { e.preventDefault(); p2Mark("ok"); }
  else if (k === "KeyD" || k === "Delete") { e.preventDefault(); p2BoxDel(); }
  else if (k === "KeyZ") { e.preventDefault(); p2Undo(); }
});
