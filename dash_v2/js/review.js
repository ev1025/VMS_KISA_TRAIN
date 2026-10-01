// dash_v2/js/review.js — 영상 검수 탭(목록·플레이어·재생바·구역·우측 정보). app.js 에서 분리(2026-09-09). 로드 순서: core → review → data → editor → main (dashboard.html)
// 2026-09-28 재설계
//   모델 = '지금 데이터' 로 처음부터 학습해 끝난 판만. 고르는 기준과 계산은 서버 scripts/review_cache.py 한 곳(채점과 같은 판정 모듈로 영상 끝까지 돌려 저장)
//   모델을 눌러도 추론하지 않는다. /api/review_models · review_summary · review_clip 로 저장된 값만 읽는다
//   목록 판정 · 재생바 신호 · 예측 경보 · 박스가 모두 고른 모델 하나에서 나온다. 모델이 없으면 정답과 구역만 보인다
//   예전 화면은 박스만 모델을 따르고 재생바 · 판정은 배포 모델 값(dash_meta.json)과 JS 로 옮겨 둔 옛 규칙이라 서로 맞지 않았다
//   renderCenter(row) 를 인자 하나로 부르면(데이터 확인 탭) 예전 동작 그대로다

// ---------- 영상 검수: 상태 ----------
const REVIEW_ITEMS = ["fire", "intrusion", "loiter", "fall"];
const RV = { models: {}, sel: {}, summ: null, clip: new Map() };   // 항목별 모델 목록 · 고른 모델 · 그 모델의 편별 판정 · 편 결과
const RV_SHOW_MIN = 0.20;                                             // 이보다 낮은 박스는 안 그린다(방화는 0.05 부터 저장돼 화면이 덮인다)
let _RV_SEQ = 0;                                                      // 늦게 온 응답이 새 화면을 덮지 않게

const rvKey = () => RV.sel[CUR.item] || "";
const rvModel = () => (RV.models[CUR.item] || []).find(m => m.key === rvKey()) || null;
const rvClipInfo = name => (RV.summ && RV.summ.clips && RV.summ.clips[name]) || null;
const rvVerdict = name => { const c = rvClipInfo(name); return c ? c.verdict : null; };
const rvSec = v => v == null ? "-" : `${fmt(v)} (${v.toFixed(1)}초)`;
function rvRows() {
  return META.items[CUR.item].rows.filter(r => FILT === "all" || rvVerdict(r.name) === FILT);
}
async function rvLoadModels(item) {
  RV.groups = RV.groups || {};
  try { const j = await (await fetch("/api/review_models?item=" + item)).json(); RV.models[item] = j.models || []; RV.groups[item] = j.groups || []; }   // 계산이 끝난 판이 늘어나므로 매번 받는다
  catch (e) { RV.models[item] = RV.models[item] || []; }
  const ready = RV.models[item].filter(m => m.done);
  let want = RV.sel[item];
  if (want == null) { try { want = localStorage.getItem("rv_sel_" + item); } catch (e) { want = null; } }
  RV.sel[item] = ready.some(m => m.key === want) ? want : (ready[0] ? ready[0].key : "");   // '모델 없음' 은 없앴다(09-30)
}
async function rvLoadSummary() {
  RV.summ = null;
  const key = rvKey(); if (!key) return;
  try {
    const r = await fetch(`/api/review_summary?key=${encodeURIComponent(key)}&item=${CUR.item}`);
    RV.summ = r.ok ? await r.json() : null;
  } catch (e) { RV.summ = null; }
}
function rvClip(name) {
  const key = rvKey(); if (!key) return Promise.resolve(null);
  const k = key + "|" + CUR.item + "|" + name;
  if (!RV.clip.has(k)) {
    RV.clip.set(k, fetch(`/api/review_clip?key=${encodeURIComponent(key)}&item=${CUR.item}&clip=${encodeURIComponent(name)}`)
      .then(r => r.ok ? r.json() : null).catch(() => null)
      .then(j => { if (!j) RV.clip.delete(k); return j; }));   // 없던 편은 다음에 다시 묻는다(계산이 끝났을 수 있다)
  }
  return RV.clip.get(k);
}
// 검수 탭에 들어올 때 · 항목이나 모델을 바꿀 때
async function enterReview() {
  buildSrc();
  await rvRefresh();
}
async function rvRefresh() {
  const my = ++_RV_SEQ;
  $("#list").innerHTML = '<div class="empty">불러오는 중…</div>';
  await rvLoadModels(CUR.item);
  await rvLoadSummary();
  if (my !== _RV_SEQ || CUR.mode !== "review") return;   // 받아 오는 사이 다른 탭으로 갔으면 그 탭 목록을 덮지 않는다
  buildFilt(); renderList();
  const rows = rvRows();
  const cur = rows.find(r => r.name === CUR.name) || rows[0];
  if (cur) { CUR.name = cur.name; renderList(); openRow(cur); }
  else { $("#center").innerHTML = '<div class="empty">영상을 선택하세요</div>'; $("#right").innerHTML = '<div class="empty">—</div>'; }
}
async function openRow(row) {
  const my = ++_RV_SEQ;
  let rv = null;
  if (rvKey()) {
    $("#center").innerHTML = '<div class="empty">저장된 결과를 읽는 중…</div>';
    rv = await rvClip(row.name);
    if (my !== _RV_SEQ || CUR.mode !== "review") return;   // 받아 오는 사이 다른 탭으로 갔으면 그 탭 목록을 덮지 않는다
  }
  renderCenter(row, { review: true, rv, missing: !!rvKey() && !rv });
  renderRight(row, rv);
}

// ---------- 좌: 항목 · 모델 · 목록 ----------
// 영상 검수 = KISA 배포 4항목만 (손라벨 labelset 은 데이터 확인 탭으로)
function buildSrc() {
  const sel = $("#srcSel"); sel.innerHTML = "";
  $(".srcbox label").hidden = false; $(".srcbox label").textContent = "검수 항목";
  { const _rb = document.getElementById("refreshBtn"); if (_rb) _rb.remove(); }   // 데이터 탭이 드롭다운 옆에 붙인 새로고침은 여기엔 안 쓴다
  $("#filtBox").hidden = false;                                                     // 데이터 탭이 숨긴 것을 되살린다
  const items = REVIEW_ITEMS.filter(k => GF === "all" || gf().review.includes(k));   // 전역 필터
  for (const k of items) {
    const v = META.items[k]; if (!v) continue;
    const o = el("option"); o.value = k; o.textContent = `${v.title} (${v.rows.length}편)`; sel.appendChild(o);
  }
  if (!items.includes(CUR.item)) { CUR.item = items[0]; CUR.name = null; FILT = "all"; }
  sel.value = CUR.item;
  sel.onchange = () => { CUR.item = sel.value; CUR.name = null; FILT = "all"; rvRefresh(); };
}
function rvLabel(m) {
  const sc = m.official && m.official["점수"] != null ? ` · 공식 ${m.official["점수"].toFixed(2)}`
           : m.score && m.score["점수"] != null ? ` · ${m.score["점수"].toFixed(2)}` : "";
  const wait = m.done ? "" : (m.progress ? ` (계산 중 ${m.progress.done}/${m.progress.total})` : " (계산 대기)");
  return `${m.exp} · ${m.ckLabel || m.ckpt} · ${m.res}${sc}${wait}`;
}
// '실험' 묶음 안의 모델만 고르게 한다. _top = 상위권(keys: 판 · 기술 결과 하나하나), 블록 = 실험 이름(runs), _other = 블록에 없는 실험
function rvInGroup(id, gs, inAny) {
  if (id === "_other") return m => !m.variant && !inAny.has(m.exp);
  const g = gs.find(x => x.id === id);
  if (g && g.keys) { const k = new Set(g.keys); return m => k.has(m.key); }
  const s = new Set(g ? g.runs || [] : []);
  return m => !m.variant && s.has(m.exp);
}
function rvGroup(gs, inAny) {                            // 고른 묶음. 처음이거나 지금 모델이 밖이면 지금 모델이 든 묶음
  RV.grp = RV.grp || {};
  let g = RV.grp[CUR.item];
  if (g == null) { try { g = localStorage.getItem("rv_grp_" + CUR.item); } catch (e) { g = null; } }
  const ok = id => id === "_other" || gs.some(x => x.id === id);
  const m = rvModel();
  if (!g || !ok(g) || (m && !rvInGroup(g, gs, inAny)(m))) {       // 처음 · 지금 모델이 밖이면 상위권 → 그 모델이 든 블록 → 블록 밖
    const hit = gs.find(x => m && rvInGroup(x.id, gs, inAny)(m));
    g = hit ? hit.id : (m && !inAny.has(m.exp) ? "_other" : (gs[0] ? gs[0].id : "_other"));
  }
  RV.grp[CUR.item] = g;
  return g;
}
// 실험 고르기 + 모델 고르기 + 점수 한 줄 + 판정 필터. #filtBox 는 데이터 확인 탭에서 숨겨져 검수 탭에만 보인다
function buildFilt() {
  const box = $("#filtBox"); box.innerHTML = "";
  box.style.cssText = "display:flex;flex-direction:column;gap:6px";
  const all = RV.models[CUR.item] || [], gs = (RV.groups || {})[CUR.item] || [];
  let ms = all;
  if (gs.length) {
    const inAny = new Set(gs.flatMap(g => g.runs || []));
    box.appendChild(el("label", "", "실험"));
    const gsel = el("select");
    [...gs.map(g => [g.id, g.label]), ...(all.some(m => !m.variant && !inAny.has(m.exp)) ? [["_other", "비교 묶음에 없는 실험"]] : [])]
      .forEach(([v, t]) => { const o = el("option", "", t); o.value = v; gsel.appendChild(o); });
    gsel.value = rvGroup(gs, inAny);
    gsel.onchange = () => {
      RV.grp[CUR.item] = gsel.value;
      try { localStorage.setItem("rv_grp_" + CUR.item, gsel.value); } catch (e) {}
      const inG = rvInGroup(gsel.value, gs, inAny);
      if (!all.some(m => m.key === rvKey() && inG(m))) {           // 지금 모델이 밖이면 그 묶음의 첫 끝난 모델로
        const f = all.find(m => m.done && inG(m));
        RV.sel[CUR.item] = f ? f.key : "";
        try { localStorage.setItem("rv_sel_" + CUR.item, RV.sel[CUR.item]); } catch (e) {}
      }
      FILT = "all"; rvRefresh();
    };
    box.appendChild(gsel);
    ms = all.filter(rvInGroup(gsel.value, gs, inAny));
    const gk = (gs.find(x => x.id === gsel.value) || {}).keys;   // 상위권 = 1위 · 1위의 기술들 · 2위 … 순서
    if (gk) ms.sort((x, y) => gk.indexOf(x.key) - gk.indexOf(y.key));
  }
  const lab = el("label", "", "모델"); box.appendChild(lab);
  const msel = el("select");
  ms.forEach(m => { const o = el("option", "", rvLabel(m)); o.value = m.key; o.disabled = !m.done; msel.appendChild(o); });
  if (!ms.some(m => m.key === rvKey())) {                  // 묶음 밖 모델이면 그 묶음의 첫 끝난 모델로('모델 없음' 은 없앴다)
    const f = ms.find(m => m.done);
    if (f) { RV.sel[CUR.item] = f.key; setTimeout(rvRefresh, 0); }   // 경보 · 편별 판정도 그 모델 것으로 다시 받는다
  }
  msel.value = rvKey();
  msel.onchange = () => {
    RV.sel[CUR.item] = msel.value;
    try { localStorage.setItem("rv_sel_" + CUR.item, msel.value); } catch (e) {}
    FILT = "all"; rvRefresh();
  };
  box.appendChild(msel);
  const note = el("div"); note.style.cssText = "font-size:var(--fs-xs);color:var(--mut);line-height:1.5";
  if (!ms.length) note.textContent = CUR.item === "fall" ? "쓰러짐은 이번 데이터로 새로 학습한 판이 없습니다" : "지금 데이터로 학습해 끝난 판이 아직 없습니다. 끝나면 서버가 미리 계산해 여기에 올립니다";
  else if (!ms.some(m => m.done)) note.textContent = "미리 계산하는 중입니다. 끝난 판부터 고를 수 있습니다";
  else if (RV.summ && RV.summ.score) {
    const s = RV.summ.score, o = RV.summ.official;
    note.innerHTML = `이 화면: 정검 <b>${s["정검"]}</b> · 미검 <b>${s["미검"]}</b> · 오검 <b>${s["오검"]}</b> → <b>${s["점수"].toFixed(2)}</b>` +
      (o ? `<br>공식 채점: ${o["점수"].toFixed(2)}${o["점수"] !== s["점수"] ? ' <span class="tag warn">다름</span>' : ""}` : "");
  }
  box.appendChild(note);
  if (!rvKey()) return;                                   // 판정은 모델이 있어야 있다
  const row = el("div"); row.style.cssText = "display:flex;gap:4px";
  [["all", "전체"], ["정검", "정검"], ["미검", "미검"], ["오검", "오검"]].forEach(([k, label]) => {
    const b = el("button", k === FILT ? "on" : "", label);
    b.onclick = () => { FILT = k; buildFilt(); renderList(); };
    row.appendChild(b);
  });
  box.appendChild(row);
}
function renderList() {
  const box = $("#list"); box.innerHTML = "";
  const has = !!rvKey();
  META.items[CUR.item].rows.forEach(r => {
    const v = has ? (rvVerdict(r.name) || "없음") : null;
    if (FILT !== "all" && v !== FILT) return;
    const it = el("div", "item" + (r.name === CUR.name ? " on" : ""));
    if (v) {
      const col = { ok: "#3fb950", bad: "#f85149", miss: "#d29922", none: "#8b949e" }[vClass(v)] || "#8b949e";
      const vb = el("span", null, v);
      vb.style.cssText = `flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;min-width:42px;height:20px;padding:0 8px;border-radius:var(--r);font:700 var(--fs-xs)/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:.02em;color:${col};background:${col}22;border:1px solid ${col}55`;
      it.appendChild(vb);
    }
    it.appendChild(el("span", "nm", r.name));
    it.onclick = () => { CUR.name = r.name; renderList(); openRow(r); };
    box.appendChild(it);
  });
}

// ---------- 중: 플레이어 + 재생바 ----------
function estDur(row) {
  const arr = row.signal_type === "fall" ? ((row.curves || [])[0] || []) : (row.signal || []);
  return arr.length ? arr[arr.length - 1][0] : 300;
}
// opt.review = 검수 탭(opt.rv = 고른 모델의 저장값, 없으면 null). opt 없이 부르면 데이터 확인 탭의 예전 동작
function renderCenter(row, opt) {
  const review = !!(opt && opt.review), rv = review ? opt.rv : null;
  const c = $("#center"); c.innerHTML = "";
  const gt = rv && rv.gt != null ? rv.gt : row.gt;
  const sa = review ? (rv ? rv.alarm : null) : (row.sa != null ? row.sa : null);
  const stage = el("div", "stage");
  const v = el("video"); v.controls = false; v.preload = "metadata";
  v.src = "/vid/" + row.video.replace(/\\/g, "/").split("/").map(encodeURIComponent).join("/");
  const zoneov = el("div", "zoneov");
  // 재생 중 연결이 끊기거나(서버 재시작 · 터널) 디코더가 오류를 내면 멈춘 자리에서 다시 불러와 이어 재생한다(최대 3번, 2026-09-29).
  // 그래도 안 되면 브라우저 오류 코드를 보인다(1 중단 · 2 네트워크 · 3 디코딩 · 4 형식)
  let _tries = 0, _lastT = 0, _wantPlay = false;
  v.addEventListener("timeupdate", () => { if (v.currentTime > 0) _lastT = v.currentTime; });
  v.addEventListener("play", () => { _wantPlay = true; }); v.addEventListener("pause", () => { if (!v.error) _wantPlay = false; });
  v.onerror = () => {
    const e = v.error, why = e ? `오류 ${e.code}${e.message ? " · " + e.message : ""}` : "";
    console.warn("영상 오류", row.video, _lastT.toFixed(2), why);
    if (e && e.code === 3 && !v.src.includes("safe=1")) {   // 디코딩 오류 → 다시 인코딩한 시청용 사본으로 그 자리부터(2026-09-30)
      const t = _lastT, go = _wantPlay;
      v.addEventListener("loadedmetadata", () => { v.currentTime = t; if (go) v.play().catch(() => {}); }, { once: true });
      v.src = v.src.split("?")[0] + "?safe=1";
      return;
    }
    if (_tries++ < 3) {
      const t = _lastT, go = _wantPlay;
      setTimeout(() => {
        v.addEventListener("loadedmetadata", () => { v.currentTime = t; if (go) v.play().catch(() => {}); }, { once: true });
        v.load();
      }, 600 * _tries);
      return;
    }
    stage.innerHTML = '<div class="novid">⚠ 영상을 불러올 수 없습니다<br><small>' + row.video + (why ? " · " + why + ` · ${fmt(_lastT)}` : "") + "</small></div>";
  };
  stage.appendChild(v); stage.appendChild(zoneov); c.appendChild(stage); VID = v;
  const overlay = t => review ? drawZoneRv(zoneov, row, rv, t) : drawZone(zoneov, row, t);

  const ctrl = el("div", "ctrl");
  const pp = el("button", "", "▶"); pp.onclick = () => v.paused ? v.play() : v.pause();
  v.onplay = () => pp.textContent = "❚❚"; v.onpause = () => pp.textContent = "▶";
  const now = el("span", "now", "0:00");
  ctrl.appendChild(pp); ctrl.appendChild(now);
  if (gt != null) { const j = el("button", "jmp gt", "GT " + fmt(gt)); j.onclick = () => v.currentTime = Math.max(0, gt - 3); ctrl.appendChild(j); }
  if (sa != null) { const j = el("button", "jmp sa", "예측 " + fmt(sa)); j.onclick = () => v.currentTime = Math.max(0, sa - 3); ctrl.appendChild(j); }
  const rate = el("div", "rate");
  let wantRate = 1;
  [1, 2, 4, 8].forEach(x => {
    const b = el("button", x === 1 ? "on" : "", x + "x");
    b.onclick = () => {
      wantRate = x; v.playbackRate = x;
      rate.querySelectorAll("button").forEach(z => z.classList.remove("on")); b.classList.add("on");
    };
    rate.appendChild(b);
  });
  // 브라우저가 seek·로드 후 배속을 1로 되돌리는 경우가 있어, 선택한 배속을 다시 강제한다
  v.addEventListener("ratechange", () => { if (Math.abs(v.playbackRate - wantRate) > 0.01) v.playbackRate = wantRate; });
  v.addEventListener("play", () => { v.playbackRate = wantRate; });
  ctrl.appendChild(rate);
  if (review) {                                          // 검수 탭: 모델은 왼쪽에서 고른다. 여기는 이름만
    const m = rvModel(), tag = el("span", "", "");
    tag.style.cssText = "margin-left:auto;font-size:var(--fs-xs);color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis";
    tag.textContent = m ? `${m.exp} · ${m.ckLabel || m.ckpt} · ${m.res}` + (opt.missing ? " · 이 편 저장값 없음" : "") : "모델 없음";
    ctrl.appendChild(tag);
  } else ctrl.appendChild(boxPicker(row, () => drawZone(zoneov, row, v.currentTime)));   // 데이터 확인 탭: 예전 모델 박스 고르기
  c.appendChild(ctrl);

  const tl = el("div", "tl");
  const bar = el("div", "tlbar"); tl.appendChild(bar);
  const leg = el("div", "leg");
  if (review) {
    leg.innerHTML = '<span><i style="background:#3fb95055"></i>정답 유효창(-2~+10초)</span>' + (!rv ? "" :
      (rv.item === "fire" ? '<span><i style="background:var(--fire)"></i>불 최고 확신도</span><span><i style="background:var(--smoke)"></i>연기</span>'
       : rv.item === "falldown" ? '<span><i style="background:var(--blue)"></i>쓰러짐 판정 확률(사람별 최고)</span>'
                          : '<span><i style="background:#8b949e"></i>화면 전체 사람 최고 확신도</span><span><i style="background:var(--blue)"></i>구역 안 사람 최고 확신도</span>') +
      `<span><i style="background:#c9d1d9"></i>규칙 문턱 ${rv.conf}</span><span><i style="background:var(--fire)"></i>예측 경보</span>`);
  } else {
    leg.innerHTML = row.signal_type === "raw"
      ? '<span><i style="background:#3fb95055"></i>정답 유효창</span>'
      : '<span><i style="background:var(--blue)"></i>신호</span><span><i style="background:#3fb95055"></i>GT 유효창</span><span><i style="background:var(--fire)"></i>예측알람</span>';
  }
  tl.appendChild(leg); c.appendChild(tl);

  const sigEnd = rv && rv.signal && rv.signal.length ? rv.signal[rv.signal.length - 1][0] : 0;
  let total = review ? (sigEnd || 300) : estDur(row);
  const paint = cur => review ? drawBarRv(bar, rv, gt, sa, total || v.duration, cur) : drawBar(bar, row, gt, sa, total || v.duration, cur);
  v.onloadedmetadata = () => { total = v.duration || total; paint(0); overlay(0); };
  v.ontimeupdate = () => { now.textContent = fmt(v.currentTime); paint(v.currentTime); overlay(v.currentTime); };
  bar.onclick = e => { const r = bar.getBoundingClientRect(); const t = (e.clientX - r.left) / r.width * (total || v.duration || 1); if (v.duration) v.currentTime = t; };
  paint(0); overlay(0);
}
// 값이 거의 0 인 구간은 선을 그리지 않는다 (하단에 빨간 직선이 쭉 깔리는 것 방지)
function plotPath(pts, idx, color, px, H) {
  if (!pts || !pts.length) return "";
  const MIN = 0.02;
  let d = "", pen = false;
  pts.forEach(p => {
    const val = p[idx];
    if (val < MIN) { pen = false; return; }
    const x = px(p[0]), y = H - Math.min(1, val) * (H - 6) - 3;
    d += (pen ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1) + " ";
    pen = true;
  });
  return d ? `<path d="${d}" fill="none" stroke="${color}" stroke-width="1.4"/>` : "";
}
function barFrame(gt, total, W, H, px) {
  if (gt == null) return "";
  const x0 = px(Math.max(0, gt - BEFORE)), x1 = px(Math.min(total, gt + AFTER));
  return `<rect x="${x0}" y="0" width="${x1 - x0}" height="${H}" fill="#3fb95033"/>` +
         `<line x1="${px(gt)}" y1="0" x2="${px(gt)}" y2="${H}" stroke="#3fb950" stroke-width="2"/>`;
}
// 데이터 확인 탭(예전 동작)
function drawBar(bar, row, gt, sa, total, cur) {
  total = total || estDur(row) || 300;
  const W = 1000, H = 64, px = t => t / total * W;
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">` + barFrame(gt, total, W, H, px);
  if (row.signal_type === "fire_smoke") { s += plotPath(row.signal, 1, "#f85149", px, H); s += plotPath(row.signal, 2, "#a371f7", px, H); }
  else if (row.signal_type === "fall") { (row.curves || []).forEach(c => s += plotPath(c, 1, "#58a6ff99", px, H)); }
  else { s += plotPath(row.signal, 1, "#58a6ff", px, H); }
  if (sa != null) s += `<line x1="${px(sa)}" y1="0" x2="${px(sa)}" y2="${H}" stroke="#f85149" stroke-width="2" stroke-dasharray="4 3"/>`;
  if (cur) s += `<line x1="${px(cur)}" y1="0" x2="${px(cur)}" y2="${H}" stroke="#58a6ff" stroke-width="1.5"/>`;
  bar.innerHTML = s + "</svg>";
}
// 검수 탭: 고른 모델의 신호 · 문턱 · 경보
function drawBarRv(bar, rv, gt, sa, total, cur) {
  total = total || 300;
  const W = 1000, H = 64, px = t => t / total * W;
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">` + barFrame(gt, total, W, H, px);
  if (rv) {
    if (rv.item === "fire") { s += plotPath(rv.signal, 1, "#f85149", px, H); s += plotPath(rv.signal, 2, "#a371f7", px, H); }
    else if (rv.item === "falldown") s += plotPath(rv.signal, 1, "#58a6ff", px, H);   // 쓰러짐 = 사람별 판정망 확률 최고
    else {                                               // 흐린 회색 = 화면 전체 사람(구역 밖 · 꼭짓점 미달 포함), 파랑 = 규칙이 구역 안으로 치는 사람
      rv._all = rv._all || (rv.samples || []).map(([t, bx]) => [t, bx.reduce((m, b) => Math.max(m, b[1]), 0)]);
      s += plotPath(rv._all, 1, "#8b949e99", px, H); s += plotPath(rv.signal, 1, "#58a6ff", px, H);
    }
    if (rv.conf != null) { const y = H - Math.min(1, rv.conf) * (H - 6) - 3; s += `<line x1="0" y1="${y}" x2="${W}" y2="${y}" stroke="#c9d1d9" stroke-width="1" stroke-dasharray="3 4" opacity=".6"/>`; }
  }
  if (sa != null) s += `<line x1="${px(sa)}" y1="0" x2="${px(sa)}" y2="${H}" stroke="#f85149" stroke-width="2" stroke-dasharray="4 3"/>`;
  if (cur) s += `<line x1="${px(cur)}" y1="0" x2="${px(cur)}" y2="${H}" stroke="#58a6ff" stroke-width="1.5"/>`;
  bar.innerHTML = s + "</svg>";
}
// 박스 겹침 정도(IoU). 박스는 [식별, conf, x1,y1,x2,y2].
function iouBox(a, b) {
  const x1 = Math.max(a[2], b[2]), y1 = Math.max(a[3], b[3]), x2 = Math.min(a[4], b[4]), y2 = Math.min(a[5], b[5]);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const A = (a[4] - a[2]) * (a[5] - a[3]), B = (b[4] - b[2]) * (b[5] - b[3]);
  return inter / (A + B - inter + 1e-6);
}
// 작은 박스가 큰 박스 안에 든 정도(교집합 / 작은 쪽 넓이). 풀프레임 박스 안에 타일 박스가 들면 IoU 는 낮아 안 걸렸다(2026-09-26).
function insideBox(a, b) {
  const x1 = Math.max(a[2], b[2]), y1 = Math.max(a[3], b[3]), x2 = Math.min(a[4], b[4]), y2 = Math.min(a[5], b[5]);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const A = (a[4] - a[2]) * (a[5] - a[3]), B = (b[4] - b[2]) * (b[5] - b[3]);
  return inter / (Math.min(A, B) + 1e-6);
}
// 타일 추론이 같은 대상을 풀프레임+타일에서 여러 번 잡아 박스가 겹쳐 보이는 것 제거.
// IoU 가 iouTh 를 넘거나, 같은 클래스끼리 포함률이 inTh 를 넘으면 conf 낮은 쪽을 뺀다(불 안의 불). 불·연기처럼 다른 클래스는 포함돼도 둔다.
function nmsBoxes(boxes, iouTh, inTh = 0.7) {
  const keep = [];
  for (const b of boxes.slice().sort((p, q) => q[1] - p[1])) {
    if (!keep.some(k => iouBox(b, k) > iouTh || (k[0] === b[0] && insideBox(b, k) > inTh))) keep.push(b);
  }
  return keep;
}
// 저장된 표본 중 t 에 가장 가까운 것(표본 간격의 절반 안). 없으면 null
function rvNear(rv, t) {
  const s = rv && rv.samples; if (!s || !s.length) return null;
  let lo = 0, hi = s.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (s[mid][0] < t) lo = mid + 1; else hi = mid; }
  let best = s[lo];
  if (lo > 0 && Math.abs(s[lo - 1][0] - t) < Math.abs(best[0] - t)) best = s[lo - 1];
  return Math.abs(best[0] - t) <= (rv.stride || 0.5) / 2 + 0.05 ? best : null;
}
// 검수 탭 겹쳐 그리기: 구역(판정기가 쓴 다각형) + 그 시각 박스. 문턱을 넘은 박스는 실선, 못 넘은 박스는 점선
function drawZoneRv(ov, row, rv, t) {
  const W = (rv && rv.wh ? rv.wh[0] : row.framew) || 1280, He = (rv && rv.wh ? rv.wh[1] : row.frameh) || 720;
  const zone = (rv && rv.zone) || row.zone;
  let s = `<svg viewBox="0 0 ${W} ${He}" preserveAspectRatio="none" style="width:100%;height:100%">`;
  if (zone && zone.length) s += `<polygon points="${zone.map(p => p.join(",")).join(" ")}" fill="#3fb95022" stroke="#3fb950" stroke-width="3"/>`;
  const near = rv ? rvNear(rv, t) : null;
  if (near) {
    const fire = rv.item === "fire";
    let bx = near[1].filter(b => b[1] >= RV_SHOW_MIN);
    if (fire) bx = nmsBoxes(bx, 0.5);                    // 6뷰가 같은 불을 여러 번 잡는다
    for (const b of bx) {
      const th = fire && b[0] === 1 ? (rv.smoke != null ? rv.smoke : rv.conf) : rv.conf;
      const on = rv.item === "falldown" || b[1] >= th, col = fire ? (b[0] === 1 ? "#a371f7" : "#f85149") : "#f85149";
      s += `<rect x="${b[2]}" y="${b[3]}" width="${b[4] - b[2]}" height="${b[5] - b[3]}" fill="none" stroke="${on ? col : "#c9d1d9"}" stroke-width="${on ? 3 : 1.5}"${on ? "" : ' stroke-dasharray="6 4" opacity=".8"'}/>`;
      s += `<text x="${b[2] + 2}" y="${Math.max(14, b[3] - 4)}" font-size="16" font-weight="700" fill="${on ? col : "#c9d1d9"}" stroke="#000" stroke-width="3" paint-order="stroke">${b[1].toFixed(2)}</text>`;
    }
  }
  ov.innerHTML = s + "</svg>";
}
// 데이터 확인 탭(예전 동작): 고른 모델 박스를 row.tracks 로 받아 그린다
function drawZone(ov, row, t) {
  const hasZone = row.zone && row.zone.length, hasTracks = row.tracks && row.tracks.length;
  if (!hasZone && !hasTracks) { ov.innerHTML = ""; return; }
  const W = row.framew || 1280, He = row.frameh || 720;
  let s = `<svg viewBox="0 0 ${W} ${He}" preserveAspectRatio="none" style="width:100%;height:100%">`;
  if (hasZone) s += `<polygon points="${row.zone.map(p => p.join(",")).join(" ")}" fill="#3fb95022" stroke="#3fb950" stroke-width="3"/>`;
  if (hasTracks) {
    let near = null, best = 1e9;
    for (const r of row.tracks) { const d = Math.abs(r.t - t); if (d < best) { best = d; near = r; } }
    if (near && best < 1) {
      const fire = row.signal_type === "fire_smoke";   // 방화면 클래스별 색(불=빨강, 연기=보라)
      for (const b of nmsBoxes(near.boxes.filter(x => x[1] >= 0.25), 0.5)) {
        const col = fire ? (b[0] ? "#a371f7" : "#f85149") : "#f85149";
        s += `<rect x="${b[2]}" y="${b[3]}" width="${b[4] - b[2]}" height="${b[5] - b[3]}" fill="none" stroke="${col}" stroke-width="2"/>`;
      }
    }
  }
  ov.innerHTML = s + "</svg>";
}
// ---------- 데이터 확인 탭: 모델 예측 박스 오버레이(예전 동작) ----------
// 학습한 실험을 고르면 그 모델이 이 클립에서 낸 박스를 영상 위에 겹쳐 본다.
// 덤프가 없으면 서버가 그 자리에서 추론해 만든다(0.5초 간격·타일). 검수 탭은 이 경로를 안 쓴다(2026-09-28)
let BOXEXP = { fire: "", person: "" };   // 고른 실험을 갈래별로 따로 기억한다
let BOXMODELS = null;     // 모델 목록은 한 번만 받는다
function boxModels() {
  if (!BOXMODELS) BOXMODELS = fetch("/api/boxmodels").then(r => r.json()).catch(() => []);
  return BOXMODELS;
}
// 이 클립에 겹쳐 볼 모델의 갈래. 방화 클립에 사람 모델을 올리면 볼 의미가 없다.
function rowKind(row) {
  if (row && (row.kind === "fire" || row.kind === "person")) return row.kind;   // 데이터 확인 탭이 넘겨준다
  return CUR.item === "fire" ? "fire" : "person";
}
function boxPicker(row, redraw) {
  const kind = rowKind(row);
  const wrap = el("div", "", "");
  wrap.style.cssText = "display:flex;align-items:center;gap:6px;margin-left:auto";
  const sel = el("select");
  sel.style.cssText = "background:#21262d;color:var(--tx);border:1px solid var(--line);border-radius:var(--r);padding:5px 8px;font-size:var(--fs-sm);max-width:260px";
  sel.innerHTML = '<option value="">예측 박스 없음</option>';
  const note = el("span", "", "");
  note.style.cssText = "font-size:var(--fs-xs);color:var(--mut);white-space:nowrap";
  wrap.appendChild(sel); wrap.appendChild(note);

  let timer = null;
  const stop = () => { if (timer) { clearTimeout(timer); timer = null; } };

  async function load(exp) {
    stop();
    if (!exp) { row.tracks = null; note.textContent = ""; redraw(); return; }
    const clip = row.name;
    const r = await fetch(`/api/boxdump?exp=${encodeURIComponent(exp)}&clip=${encodeURIComponent(clip)}`)
      .then(x => x.json()).catch(() => ({ state: "err:통신 실패" }));
    if (sel.value !== exp) return;                       // 그 사이 다른 모델을 골랐으면 버린다
    if (r.state === "done" && r.rows) {
      row.tracks = r.rows;
      const nb = r.rows.reduce((a, x) => a + (x.boxes || []).length, 0);
      note.textContent = `표본 ${r.rows.length} · 박스 ${nb}`;
      redraw(); return;
    }
    if (String(r.state).startsWith("err")) { note.textContent = "실패: " + String(r.state).slice(4, 60); return; }
    if (r.state === "none") {
      note.textContent = "추론 중…";
      await fetch(`/api/boxdump_start?exp=${encodeURIComponent(exp)}&clip=${encodeURIComponent(clip)}`).catch(() => {});
    } else note.textContent = "추론 중…";
    timer = setTimeout(() => load(exp), 3000);           // 다 될 때까지 3초마다 확인
  }

  boxModels().then(all => {
    const list = (all || []).filter(m => m.kind === kind);   // 이 클립과 같은 갈래만
    list.forEach(m => {
      const o = el("option", "", `${m.tag ? "[" + m.tag + "] " : ""}${m.exp}${m.why ? " · " + m.why : (m.map50 != null ? ` · mAP ${m.map50.toFixed(3)}` : "")}`);
      o.value = m.exp; sel.appendChild(o);
    });
    if (!list.length) { note.textContent = kind === "fire" ? "불 학습 모델 없음" : "사람 학습 모델 없음"; return; }
    const want = BOXEXP[kind];
    if (want && list.some(m => m.exp === want)) { sel.value = want; load(want); }
  });
  sel.onchange = () => { BOXEXP[kind] = sel.value; row.tracks = null; redraw(); load(sel.value); };
  return wrap;
}

// ---------- 우: 영상 · 판정 · 모델 정보 ----------
function renderRight(row, rv) {
  const r = $("#right"); r.innerHTML = "";
  const KV = (k, val) => { const d = el("div", "kv"); d.appendChild(el("span", "", k)); d.appendChild(el("b", "", val)); return d; };
  const m = rvModel(), ci = rvClipInfo(row.name);
  r.appendChild(el("div", "rtitle", "영상 정보"));
  r.appendChild(KV("이름", row.name));
  r.appendChild(KV("정답 GT", rvSec(rv && rv.gt != null ? rv.gt : row.gt)));
  if (m) {
    r.appendChild(KV("예측 경보", rvSec(rv ? rv.alarm : (ci ? ci.alarm : null))));
    const v = rv ? rv.verdict : (ci ? ci.verdict : "-");
    const d = el("div", "kv"); d.appendChild(el("span", "", "판정"));
    const b = el("b", "", v);
    if (ci && ci.official && ci.official !== v) b.appendChild(el("span", "tag warn", "공식: " + ci.official));   // 장비 차이로 갈린 편
    d.appendChild(b); r.appendChild(d);
  }
  r.appendChild(KV("시간대", row.tod || "-"));
  if ((row.weather || []).length) {
    const d = el("div", "kv"); d.appendChild(el("span", "", "특이날씨"));
    const b = el("b"); row.weather.forEach(w => b.appendChild(el("span", "tag warn", w))); d.appendChild(b); r.appendChild(d);
  }
  const zone = (rv && rv.zone) || row.zone;
  if (zone && zone.length) {
    r.appendChild(el("div", "rtitle", `구역맵 <span class="tag">${row.zone_tag || ""}</span>`));
    const wrap = el("div", "zonewrap");
    const W = (rv && rv.wh ? rv.wh[0] : row.framew) || 1280, He = (rv && rv.wh ? rv.wh[1] : row.frameh) || 720;
    let s = `<svg viewBox="0 0 ${W} ${He}">`;
    if (row.detect && row.detect.length) s += `<polygon points="${row.detect.map(p => p.join(",")).join(" ")}" fill="none" stroke="#8b949e" stroke-width="2" stroke-dasharray="6 4"/>`;
    s += `<polygon points="${zone.map(p => p.join(",")).join(" ")}" fill="#3fb95022" stroke="#3fb950" stroke-width="3"/></svg>`;
    wrap.innerHTML = s; r.appendChild(wrap);
    r.appendChild(el("div", "leg", '<span><i style="background:#3fb950"></i>탐지구역</span><span><i style="background:#8b949e"></i>전체영역</span>'));
  }
  if (m) {
    r.appendChild(el("div", "rtitle", "모델"));
    r.appendChild(KV("실험", m.exp));
    r.appendChild(KV("체크포인트 · 해상도", `${m.ckLabel || m.ckpt} · ${m.res}`));
    r.appendChild(KV("학습 데이터", (m.data || []).join(" · ") || "-"));
    const s = RV.summ && RV.summ.score, o = RV.summ && RV.summ.official;
    if (s) r.appendChild(KV("이 항목 점수", `${s["점수"].toFixed(2)}` + (o ? ` · 공식 ${o["점수"].toFixed(2)}` : "")));
    if (RV.summ && RV.summ.made) r.appendChild(KV("계산 시각", RV.summ.made));
  }
  if (CUR.item === "fire") renderLabels(r, row);
}
function renderLabels(r, row) {
  if (!LABELS) return;
  const mine = LABELS.filter(l => l.clip === row.name);
  if (!mine.length) return;   // 손라벨(사람이 그린 정답)이 없으면 섹션 자체를 숨김 — 배포 영상은 원래 없음
  r.appendChild(el("div", "rtitle", `손라벨(사람 정답) <span class="tag">${mine.length}박스</span>`));
  const frames = [...new Set(mine.map(l => l.file))];
  const wrap = el("div", "lblframe");
  const img = el("img"); const ov = el("div"); ov.style.cssText = "position:absolute;inset:0";
  wrap.appendChild(img); wrap.appendChild(ov); r.appendChild(wrap);
  const draw = file => {
    const bx = mine.filter(l => l.file === file);
    let s = `<svg viewBox="0 0 ${bx[0].W} ${bx[0].H}" style="position:absolute;inset:0;width:100%;height:100%">`;
    bx.forEach(l => {
      const x = l.x * l.W, y = l.y * l.H;   // 손라벨 x,y = 좌상단
      s += `<rect x="${x}" y="${y}" width="${l.w * l.W}" height="${l.h * l.H}" fill="none" stroke="${l.cls ? "#a371f7" : "#f85149"}" stroke-width="3"/>`;
    });
    s += "</svg>"; ov.innerHTML = s;
  };
  img.onload = () => draw(img.dataset.file);
  img.dataset.file = frames[0]; img.src = "/frame/" + encodeURIComponent(frames[0]);
  if (frames.length > 1) {
    const th = el("div", "thumbs");
    frames.slice(0, 12).forEach((f, i) => {
      const tw = el("div", "tw" + (i === 0 ? " on" : "")); const ti = el("img"); ti.src = "/frame/" + encodeURIComponent(f); tw.appendChild(ti);
      tw.onclick = () => { img.dataset.file = f; img.src = "/frame/" + encodeURIComponent(f); th.querySelectorAll(".tw").forEach(z => z.classList.remove("on")); tw.classList.add("on"); };
      th.appendChild(tw);
    });
    r.appendChild(th);
  }
}
