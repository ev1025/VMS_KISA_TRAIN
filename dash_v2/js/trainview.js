// dash_v2/js/trainview.js — 데이터 확인 탭의 '학습 데이터' 보기(2026-10-01). 실험이 실제로 학습에 쓴 셋 · 사진 · 박스를 눈으로 확인한다.
// 읽기만 한다. 계산 · 셋 찾기는 서버 dash_v2/trainview.py(/api/tv_exps · /api/tv_set · /api/tv_thumb). 수상한 사진(오류 의심)부터 보여 준다
let TV_ON = (() => { try { return localStorage.getItem("tv_on") === "1"; } catch (e) { return false; } })();
const TV = { exps: null, exp: null, set: null, flag: "sus", off: 0, data: null, pick: null, seq: 0 };
const TV_PAGE = 60;
const TV_STRONG = ["eval", "out", "cls", "dup", "nolabel"], TV_SOFT = ["tiny", "huge", "many"];   // 오류 의심 / 확인 권장
const tvFire = () => ((TV.exps || []).find(e => e.exp === TV.exp) || {}).item === "방화";
const tvColor = c => tvFire() ? (c === 1 ? "#a371f7" : "#f85149") : "#58a6ff";

function tvToggle(row) {                                // 데이터 확인 탭 맨 위: [원본 데이터 | 학습 데이터]
  let seg = document.getElementById("tvSeg");
  if (!seg) { seg = el("div", "tv-seg"); seg.id = "tvSeg"; seg.setAttribute("role", "group"); seg.setAttribute("aria-label", "보기"); }
  seg.innerHTML = "";
  [["raw", "원본 데이터"], ["tv", "학습 데이터"]].forEach(([k, l]) => {
    const b = el("button", (k === "tv") === TV_ON ? "on" : "", l);
    b.setAttribute("aria-pressed", (k === "tv") === TV_ON);
    b.onclick = () => { if ((k === "tv") === TV_ON) return; TV_ON = k === "tv"; try { localStorage.setItem("tv_on", TV_ON ? "1" : "0"); } catch (e) {} buildDatasetSrc(); };
    seg.appendChild(b);
  });
  row.insertBefore(seg, row.firstChild);
}

async function tvEnter() {
  const sr = document.getElementById("srcRow"); if (sr) sr.style.display = "none";
  $(".srcbox label").hidden = true;
  const list = $("#list"); list.innerHTML = '<div class="empty">실험 목록 읽는 중…</div>';
  $("#center").innerHTML = '<div class="empty">왼쪽에서 실험과 셋을 고르세요</div>';
  $("#right").innerHTML = '<div class="empty">—</div>';
  if (!TV.exps) {
    try { const r = await (await fetch("/api/tv_exps")).json(); if (r.error) throw r.error; TV.exps = r.exps; }
    catch (e) { list.innerHTML = `<div class="empty">학습 데이터를 못 읽었습니다${typeof e === "string" ? "<br>" + nrEsc(e) : ""}</div>`; return; }
  }
  if (CUR.mode !== "data" || !TV_ON) return;
  if (!TV.exps.length) { list.innerHTML = '<div class="empty">이 서버에는 실험 기록이 없습니다</div>'; return; }
  if (!TV.exps.some(e => e.exp === TV.exp)) TV.exp = TV.exps[0].exp;
  tvLeft();
  if (TV.set) tvLoad(); else { const e = TV.exps.find(x => x.exp === TV.exp); if (e && e.sets.length) { TV.set = e.sets[0].name; tvLeft(); tvLoad(); } }
}

function tvLeft() {                                     // 왼쪽: 실험 고르기 + 그 실험의 셋 목록
  const list = $("#list"); list.innerHTML = "";
  const e = TV.exps.find(x => x.exp === TV.exp);
  const lab = el("label", "tv-lab", "실험"); lab.htmlFor = "tvExp"; list.appendChild(lab);
  const sel = el("select", "tv-exp"); sel.id = "tvExp";
  TV.exps.forEach(x => { const o = el("option", "", `${x.exp}${x.status === "학습 중" || x.status === "대기" ? " · " + x.status : ""}`); o.value = x.exp; sel.appendChild(o); });
  sel.value = TV.exp;
  sel.onchange = () => { TV.exp = sel.value; const n = TV.exps.find(x => x.exp === TV.exp); TV.set = n && n.sets[0] ? n.sets[0].name : null; TV.off = 0; tvLeft(); tvLoad(); };
  list.appendChild(sel);
  if (e && e.n_train) list.appendChild(el("div", "tv-note", `학습 목록 ${e.n_train.toLocaleString()}장`));
  list.appendChild(el("div", "tv-lab", "셋"));
  (e ? e.sets : []).forEach(s => {
    const it = el("div", "item" + (s.name === TV.set ? " on" : ""));
    it.appendChild(el("span", "nm", nrEsc(s.name))); it.title = s.name;
    it.appendChild(el("span", "tv-role", s.role + (s.k > 1 ? ` ×${s.k}` : "") + (s.frac && s.frac < 1 ? ` ${Math.round(s.frac * 100)}%` : "")));
    it.onclick = () => { TV.set = s.name; TV.off = 0; TV.flag = "sus"; tvLeft(); tvLoad(); };
    list.appendChild(it);
  });
}

async function tvLoad() {
  const my = ++TV.seq, c = $("#center");
  c.innerHTML = '<div class="empty">셋을 읽는 중… 처음 여는 큰 셋은 수십 초 걸립니다</div>';
  let r;
  try { r = await (await fetch(`/api/tv_set?name=${encodeURIComponent(TV.set)}&flag=${TV.flag}&offset=${TV.off}&limit=${TV_PAGE}`)).json(); }
  catch (e) { if (my === TV.seq) c.innerHTML = '<div class="empty">셋을 못 읽었습니다</div>'; return; }
  if (my !== TV.seq || CUR.mode !== "data" || !TV_ON) return;
  if (r.error) { c.innerHTML = `<div class="empty">${nrEsc(r.error)}</div>`; return; }
  TV.data = r; tvCenter();
}

function tvCenter() {
  const r = TV.data, c = $("#center");
  const chip = (k, label, n) => n || k === TV.flag ? `<button class="tv-chip${k === TV.flag ? " on" : ""}" data-f="${k}" aria-pressed="${k === TV.flag}">${label} <b>${n.toLocaleString()}</b></button>` : "";
  const head = `<div class="tv-head"><div class="tv-title"><b>${nrEsc(r.name)}</b><span class="nr-mut">${nrEsc(r.dir)}</span></div>` +
    (r.meta && (r.meta.built || r.meta.note) ? `<div class="tv-meta nr-mut">${r.meta.built ? "만든 날 " + nrEsc(r.meta.built) : ""}${r.meta.note ? " · " + nrEsc(r.meta.note) : ""}</div>` : "") +
    `<div class="tv-chips"><span class="tv-gl">보기</span>${chip("all", "전체", r.total)}${chip("sus", "오류 의심", r.sus)}${chip("bg", "배경(박스 없음)", r.bg)}</div>` +
    `<div class="tv-chips"><span class="tv-gl">오류 의심</span>${TV_STRONG.map(k => chip(k, r.labels[k], r.counts[k])).join("") || '<span class="nr-mut">없음</span>'}</div>` +
    `<div class="tv-chips"><span class="tv-gl">확인 권장</span>${TV_SOFT.map(k => chip(k, r.labels[k], r.counts[k])).join("") || '<span class="nr-mut">없음</span>'}</div>` +
    `<div class="tv-pager"><button class="tv-prev"${TV.off ? "" : " disabled"}>이전</button><span>${r.sel ? `${(TV.off + 1).toLocaleString()} ~ ${Math.min(TV.off + TV_PAGE, r.sel).toLocaleString()} / ${r.sel.toLocaleString()}장` : "0장"}</span>` +
    `<button class="tv-next"${TV.off + TV_PAGE < r.sel ? "" : " disabled"}>다음</button></div></div>`;
  const cells = r.items.map((it, i) => `<button type="button" class="tv-cell${TV.pick === it.p ? " on" : ""}" data-i="${i}" title="${nrEsc(it.p)}">` +
    `<span class="tv-img"><img loading="lazy" alt="" src="/api/tv_thumb?w=320&p=${encodeURIComponent(it.p)}">${tvBoxes(it.boxes)}</span>` +
    `<span class="tv-cap">${nrEsc(it.p.split("/").pop())}</span>` +
    (it.flags.length ? `<span class="tv-flags">${it.flags.map(f => `<span class="tv-flag${TV_STRONG.includes(f) ? " s" : ""}">${nrEsc(r.labels[f])}</span>`).join("")}</span>` : "") + "</button>").join("");
  c.innerHTML = `<div class="tv">${head}<div class="tv-grid">${cells || '<div class="empty">이 조건인 사진 없음</div>'}</div></div>`;
  c.querySelectorAll(".tv-chip").forEach(b => b.onclick = () => { TV.flag = b.dataset.f; TV.off = 0; tvLoad(); });
  c.querySelector(".tv-prev").onclick = () => { TV.off = Math.max(0, TV.off - TV_PAGE); tvLoad(); c.scrollTop = 0; };
  c.querySelector(".tv-next").onclick = () => { TV.off += TV_PAGE; tvLoad(); c.scrollTop = 0; };
  c.querySelectorAll(".tv-cell").forEach(b => b.onclick = () => { const it = r.items[+b.dataset.i]; TV.pick = it.p; c.querySelectorAll(".tv-cell").forEach(x => x.classList.toggle("on", x === b)); tvRight(it); });
}

function tvBoxes(boxes) {                               // 정규화 박스(YOLO cx cy w h) → 사진 위 SVG
  if (!boxes.length) return "";
  return '<svg class="tv-svg" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">' + boxes.map(b =>
    `<rect x="${b[1] - b[3] / 2}" y="${b[2] - b[4] / 2}" width="${b[3]}" height="${b[4]}" fill="none" stroke="${tvColor(b[0])}" stroke-width="2" vector-effect="non-scaling-stroke"/>`).join("") + "</svg>";
}

function tvRight(it) {                                  // 오른쪽: 크게 + 경로 + 라벨 줄 + 수상한 점
  const r = TV.data, rp = $("#right");
  const cls = c => tvFire() ? (c === 1 ? "연기" : c === 0 ? "불" : "번호 " + c) : (c === 0 ? "사람" : "번호 " + c);
  rp.innerHTML = `<div class="rtitle">사진 정보</div><div class="tv-big"><img alt="" src="/api/tv_thumb?w=900&p=${encodeURIComponent(it.p)}">${tvBoxes(it.boxes)}</div>` +
    `<div class="kv"><span>파일</span><b>${nrEsc(it.p.split("/").pop())}</b></div>` +
    `<div class="tv-path nr-mut">${nrEsc(it.p)}</div>` +
    `<div class="kv"><span>박스</span><b>${it.boxes.length ? it.boxes.length + "개" : "없음(배경)"}</b></div>` +
    (it.flags.length ? `<div class="tv-flags">${it.flags.map(f => `<span class="tv-flag${TV_STRONG.includes(f) ? " s" : ""}">${nrEsc(r.labels[f])}</span>`).join("")}</div>` : "") +
    (it.boxes.length ? `<table class="tv-tbl"><tr><th>클래스</th><th>가운데 x</th><th>가운데 y</th><th>너비</th><th>높이</th></tr>${it.boxes.map(b =>
      `<tr><td>${cls(b[0])}</td>${b.slice(1).map(v => `<td>${v.toFixed(4)}</td>`).join("")}</tr>`).join("")}</table>` : "");
}
