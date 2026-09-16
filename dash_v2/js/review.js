// dash_v2/js/review.js — 영상 검수 탭(목록·플레이어·재생바·구역·우측 정보). app.js 에서 분리(2026-09-09). 로드 순서: core → review → data → editor → main (dashboard.html)
// ---------- 좌: 원본 + 목록 ----------
// 영상 검수 = KISA 배포 4항목만 (손라벨 labelset 은 데이터 확인 탭으로)
const REVIEW_ITEMS = ["fire", "intrusion", "loiter", "fall"];
function buildSrc() {
  const sel = $("#srcSel"); sel.innerHTML = "";
  $(".srcbox label").textContent = "검수 항목";
  $("#filtBox").hidden = false;
  for (const k of REVIEW_ITEMS) {
    const v = META.items[k]; if (!v) continue;
    const o = el("option"); o.value = k; o.textContent = `${v.title} (${v.rows.length}편)`; sel.appendChild(o);
  }
  if (!REVIEW_ITEMS.includes(CUR.item)) CUR.item = "fire";
  sel.value = CUR.item;
  sel.onchange = () => {
    CUR.item = sel.value; CUR.name = null; renderList();
    $("#center").innerHTML = '<div class="empty">영상을 선택하세요</div>';
    $("#right").innerHTML = '<div class="empty">—</div>';
  };
}
function buildFilt() {
  const box = $("#filtBox"); box.innerHTML = "";
  [["all", "전체"], ["정검", "정검"], ["미검", "미검"], ["오검", "오검"]].forEach(([k, label]) => {
    const b = el("button", k === FILT ? "on" : "", label);
    b.onclick = () => { FILT = k; buildFilt(); renderList(); };
    box.appendChild(b);
  });
}
function renderList() {
  const box = $("#list"); box.innerHTML = "";
  const rows = META.items[CUR.item].rows;
  if (CUR.item === "labelset") {
    const clips = rows.length, boxes = rows.reduce((s, r) => s + (r.box_count || 0), 0);
    const frames = rows.reduce((s, r) => s + (r.frame_count || 0), 0);
  } else {
    // KISA 집계: 창 밖 알람(오검)은 오검+미검 이중 감점. 오검이면 fp 와 fn 을 모두 올린다.
    let tp = 0, fn = 0, fp = 0;
    rows.forEach(r => {
      const v = verdict(r, CUR.item);
      if (v === "정검") tp++;
      else if (v === "미검") fn++;
      else if (v === "오검") { fp++; fn++; }
      else if (v === "오탐") fp++;   // GT 없는 정상 영상에서의 헛알람은 fp 만
    });
    const rc = tp + fn ? tp / (tp + fn) : 0, pr = tp + fp ? tp / (tp + fp) : 0;
    const f1 = rc + pr ? 2 * rc * pr / (rc + pr) * 100 : 0;
  }
  rows.forEach(r => {
    const v = verdict(r, CUR.item);
    if (FILT !== "all" && v !== FILT) return;
    const it = el("div", "item" + (r.name === CUR.name ? " on" : ""));
    const vc = vClass(v);
    const col = { ok: "#3fb950", bad: "#f85149", miss: "#d29922", none: "#8b949e" }[vc] || "#8b949e";
    const vb = el("span", null, v);
    vb.style.cssText = `flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;min-width:42px;height:20px;padding:0 8px;border-radius:6px;font:700 11px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:.02em;color:${col};background:${col}22;border:1px solid ${col}55`;
    it.appendChild(vb);
    it.appendChild(el("span", "nm", r.name));
    it.onclick = () => {
      CUR.name = r.name; renderList();
      if (CUR.item === "labelset") renderLabelset(r); else { renderCenter(r); renderRight(r); }
    };
    box.appendChild(it);
  });
}

// ---------- 손라벨 프레임 뷰어 (중앙에 큰 이미지 + 박스, 우측에 썸네일) ----------
let LB_FRAME = 0;
function renderLabelset(row) {
  LB_FRAME = 0;
  const c = $("#center"); c.innerHTML = "";
  const r = $("#right"); r.innerHTML = "";
  if (!row.frames || !row.frames.length) { c.innerHTML = '<div class="empty">프레임 없음</div>'; return; }
  const wrap = el("div", "lblframe"); wrap.style.cssText = "margin:16px;max-width:900px";
  const img = el("img"); img.style.cssText = "width:100%;border-radius:8px;display:block";
  const ov = el("div"); ov.style.cssText = "position:absolute;inset:0";
  wrap.appendChild(img); wrap.appendChild(ov); c.appendChild(wrap);
  const cap = el("div"); cap.style.cssText = "margin:0 16px;color:var(--mut)"; c.appendChild(cap);
  const show = i => {
    const f = row.frames[i]; LB_FRAME = i;
    img.dataset.file = f.file; img.src = "/frame/" + encodeURIComponent(f.file);
    const drawBoxes = () => {
      let s = `<svg viewBox="0 0 ${f.W} ${f.H}" style="position:absolute;inset:0;width:100%;height:100%">`;
      (f.boxes || []).forEach(b => {
        // 손라벨 툴은 x,y 를 박스 좌상단으로 저장한다 (중앙 아님)
        const x = b[1] * f.W, y = b[2] * f.H;
        s += `<rect x="${x}" y="${y}" width="${b[3] * f.W}" height="${b[4] * f.H}" fill="none" stroke="${b[0] ? "#a371f7" : "#f85149"}" stroke-width="3"/>`;
      });
      s += "</svg>"; ov.innerHTML = s;
    };
    img.onload = drawBoxes; if (img.complete) drawBoxes();
    cap.innerHTML = `프레임 <b>${i + 1}/${row.frames.length}</b> · ${f.file} · 박스 ${(f.boxes || []).length}개` + (f.gt != null ? ` · GT ${fmt(f.gt)}` : "");
    $("#right").querySelectorAll(".tw").forEach((z, j) => z.classList.toggle("on", j === i));
  };
  // 우측: 썸네일 격자
  r.appendChild(el("div", "rtitle", `${row.name} <span class="tag">${row.frames.length}프레임 ${row.box_count}박스</span>`));
  const th = el("div", "thumbs");
  row.frames.forEach((f, i) => {
    const tw = el("div", "tw" + (i === 0 ? " on" : "")); const ti = el("img"); ti.src = "/frame/" + encodeURIComponent(f.file); tw.appendChild(ti);
    if ((f.boxes || []).length) { const badge = el("span"); badge.style.cssText = "position:absolute;top:2px;right:4px;font-size:10px;color:#f85149;font-weight:700"; badge.textContent = f.boxes.length; tw.appendChild(badge); }
    tw.onclick = () => show(i);
    th.appendChild(tw);
  });
  r.appendChild(th);
  r.appendChild(el("div", "leg", '<span><i style="background:#f85149"></i>불</span><span><i style="background:#a371f7"></i>연기</span>'));
  show(0);
}

// ---------- 중: 플레이어 + 재생바 ----------
function estDur(row) {
  const arr = row.signal_type === "fall" ? (row.curves[0] || []) : (row.signal || []);
  return arr.length ? arr[arr.length - 1][0] : 300;
}
function renderCenter(row) {
  const c = $("#center"); c.innerHTML = "";
  const gt = row.gt, sa = ("sa" in row) ? row.sa : alarmOf(row, CUR.item), gdur = row.gt_dur || 0;
  const stage = el("div", "stage");
  const v = el("video"); v.controls = false; v.preload = "metadata";
  v.src = "/vid/" + row.video.replace(/\\/g, "/").split("/").map(encodeURIComponent).join("/");
  const zoneov = el("div", "zoneov");
  v.onerror = () => { stage.innerHTML = '<div class="novid">⚠ 영상을 불러올 수 없습니다<br><small>' + row.video + "</small></div>"; };
  stage.appendChild(v); stage.appendChild(zoneov); c.appendChild(stage); VID = v;

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
  // 모델을 바꾸면 박스와 재생바 곡선을 같이 다시 그린다(곡선도 그 모델 덤프에서 나온다)
  const redrawAll = () => { drawZone(zoneov, row, v.currentTime); drawBar(bar, row, gt, sa, total || v.duration, v.currentTime); };
  ctrl.appendChild(boxPicker(row, redrawAll));   // 모델 예측 박스
  c.appendChild(ctrl);

  const tl = el("div", "tl");
  const bar = el("div", "tlbar"); tl.appendChild(bar);
  const leg = el("div", "leg");
  leg.innerHTML = row.signal_type === "raw"
    ? '<span><i style="background:#3fb95055"></i>정답 유효창</span>'
    : row.signal_type === "fire_smoke"
    ? '<span><i style="background:var(--fire)"></i>불</span><span><i style="background:var(--smoke)"></i>연기</span><span><i style="background:#3fb95055"></i>GT 유효창</span><span><i style="background:#e3b341"></i>예측알람</span>'
    : '<span><i style="background:var(--blue)"></i>신호</span><span><i style="background:#3fb95055"></i>GT 유효창</span><span><i style="background:#e3b341"></i>예측알람</span>';
  tl.appendChild(leg); c.appendChild(tl);
  // 정답/예측/판정/시간대/날씨는 우측 정보창(renderRight)에 있으므로 중앙 하단 중복 표시는 제거

  let total = estDur(row);
  v.onloadedmetadata = () => { total = v.duration || total; drawBar(bar, row, gt, sa, total, 0); };
  v.ontimeupdate = () => { now.textContent = fmt(v.currentTime); drawBar(bar, row, gt, sa, total || v.duration, v.currentTime); drawZone(zoneov, row, v.currentTime); };
  bar.onclick = e => { const r = bar.getBoundingClientRect(); const t = (e.clientX - r.left) / r.width * (total || v.duration || 1); if (v.duration) v.currentTime = t; };
  drawBar(bar, row, gt, sa, total, 0);
}
// 고른 모델의 박스 덤프에서 곡선을 만든다. 표본마다 클래스별 최고 신뢰도.
// 박스와 같은 자료를 쓰므로 그림과 곡선이 어긋날 수 없다.
function signalFromTracks(tracks) {
  if (!tracks || !tracks.length) return null;
  return tracks.map(r => {
    let f = 0, sm = 0;
    for (const b of (r.boxes || [])) { if (b[0]) { if (b[1] > sm) sm = b[1]; } else if (b[1] > f) f = b[1]; }
    return [r.t, f, sm];
  });
}
function drawBar(bar, row, gt, sa, total, cur) {
  total = total || estDur(row) || 300;
  const W = 1000, H = 64, px = t => t / total * W;
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
  if (gt != null) {
    const x0 = px(Math.max(0, gt - BEFORE)), x1 = px(Math.min(total, gt + AFTER));
    s += `<rect x="${x0}" y="0" width="${x1 - x0}" height="${H}" fill="#3fb95033"/>`;
    s += `<line x1="${px(gt)}" y1="0" x2="${px(gt)}" y2="${H}" stroke="#3fb950" stroke-width="2"/>`;
  }
  // 값이 거의 0 인 구간은 선을 그리지 않는다 (하단에 빨간 직선이 쭉 깔리는 것 방지).
  // 0 이하 점은 건너뛰고, 신호가 살아있는 구간만 이어 그린다.
  const plot = (pts, idx, color) => {
    if (!pts || !pts.length) return "";
    const MIN = 0.02;
    let d = "", pen = false;
    pts.forEach(p => {
      const v = p[idx];
      if (v < MIN) { pen = false; return; }               // 신호 없음 → 선 끊기
      const x = px(p[0]), y = H - Math.min(1, v) * (H - 6) - 3;
      d += (pen ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1) + " ";
      pen = true;
    });
    return d ? `<path d="${d}" fill="none" stroke="${color}" stroke-width="1.4"/>` : "";
  };
  // 모델을 고르면 그 모델 곡선, 안 골랐으면 배포 구성 곡선
  const sig = signalFromTracks(row.tracks) || row.signal;
  if (row.signal_type === "fire_smoke") { s += plot(sig, 1, "#f85149"); s += plot(sig, 2, "#a371f7"); }
  else if (row.signal_type === "fall") { (row.curves || []).forEach(c => s += plot(c, 1, "#58a6ff99")); }
  else { s += plot(sig, 1, "#58a6ff"); }
  // 예측알람은 노랑. 불 곡선(빨강)과 같은 색이면 어느 쪽인지 헷갈린다.
  if (sa != null) s += `<line x1="${px(sa)}" y1="0" x2="${px(sa)}" y2="${H}" stroke="#e3b341" stroke-width="2" stroke-dasharray="4 3"/>`;
  if (cur) s += `<line x1="${px(cur)}" y1="0" x2="${px(cur)}" y2="${H}" stroke="#58a6ff" stroke-width="1.5"/>`;
  s += "</svg>";
  bar.innerHTML = s;
}
// 박스 겹침 정도(IoU). 박스는 [식별, conf, x1,y1,x2,y2].
function iouBox(a, b) {
  const x1 = Math.max(a[2], b[2]), y1 = Math.max(a[3], b[3]), x2 = Math.min(a[4], b[4]), y2 = Math.min(a[5], b[5]);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const A = (a[4] - a[2]) * (a[5] - a[3]), B = (b[4] - b[2]) * (b[5] - b[3]);
  return inter / (A + B - inter + 1e-6);
}
// 타일 추론이 같은 대상을 풀프레임+타일에서 여러 번 잡아 박스가 겹쳐 보이는 것 제거.
// 제출 도구(_kisa_port/tools/kisa_items.py 의 nms)와 같은 규칙을 쓴다.
//   겹침(IoU >= iouTh) 이거나 작은 박스가 큰 박스 안에 containTh 이상 들어가면 지운다.
//   타일 경계에 걸려 잘린 박스는 IoU 가 낮아 겹침만으로는 안 지워진다. 그래서 포함도 같이 본다.
// 클래스가 다르면 지우지 않는다(불 위의 연기는 둘 다 보여야 한다).
function containedIn(a, b) {          // a 가 b 안에 얼마나 들어가 있나 (a 기준 넓이 비율)
  const ix = Math.max(0, Math.min(a[4], b[4]) - Math.max(a[2], b[2]));
  const iy = Math.max(0, Math.min(a[5], b[5]) - Math.max(a[3], b[3]));
  const A = (a[4] - a[2]) * (a[5] - a[3]);
  return A > 0 ? (ix * iy) / A : 0;
}
function nmsBoxes(boxes, iouTh, containTh) {
  const ct = containTh == null ? 0.75 : containTh;
  const keep = [];
  for (const b of boxes.slice().sort((p, q) => q[1] - p[1])) {
    // 포함은 양쪽으로 본다. 연기는 같은 기둥을 작게도 크게도 잡아서
    // '새 박스가 남은 박스 안' 만 보면 큰 박스가 살아남아 겹겹이 쌓인다(t=252 에서 5개 -> 2개 -> 1개).
    const dup = keep.some(k => k[0] === b[0] &&
      (iouBox(b, k) >= iouTh || containedIn(b, k) >= ct || containedIn(k, b) >= ct));
    if (!dup) keep.push(b);
  }
  return keep;
}
// ---------- 모델 예측 박스 오버레이 ----------
// 학습한 실험을 고르면 그 모델이 이 클립에서 낸 박스를 영상 위에 겹쳐 본다.
// 덤프가 없으면 서버가 그 자리에서 추론해 만든다(0.5초 간격·타일, 채점과 같은 조건).
let BOXEXP = { fire: "", person: "" };   // 고른 실험을 갈래별로 따로 기억한다
let BOXCONF = 0.25;                      // 이 신뢰도 아래는 안 그린다(화면에서 조절한다)
let BOXMODELS = null;     // 모델 목록은 한 번만 받는다
function boxModels() {
  if (!BOXMODELS) BOXMODELS = fetch("/api/boxmodels").then(r => r.json()).catch(() => []);
  return BOXMODELS;
}
// 이 클립에 겹쳐 볼 모델의 갈래. 방화 클립에 사람 모델을 올리면 볼 의미가 없다.
function rowKind(row) {
  if (row && (row.kind === "fire" || row.kind === "person")) return row.kind;   // 데이터 확인 탭이 넘겨준다
  return CUR.item === "fire" ? "fire" : "person";   // 평가 검수 탭(침입·배회·쓰러짐은 전부 사람)
}
function boxPicker(row, redraw) {
  const kind = rowKind(row);
  const wrap = el("div", "", "");
  wrap.style.cssText = "display:flex;align-items:center;gap:6px;margin-left:auto";
  const sel = el("select");
  sel.style.cssText = "background:#21262d;color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:5px 8px;font-size:12px;max-width:260px";
  sel.innerHTML = '<option value="">예측 박스 없음</option>';
  const note = el("span", "", "");
  note.style.cssText = "font-size:11px;color:var(--mut);white-space:nowrap";

  // 신뢰도 문턱. 박스가 너무 많다/적다는 이 값 하나로 갈린다.
  const conf = el("input");
  conf.type = "range"; conf.min = "0.10"; conf.max = "0.90"; conf.step = "0.05";
  conf.value = String(BOXCONF);
  conf.title = "신뢰도 문턱";
  conf.style.cssText = "width:90px;accent-color:var(--acc)";
  const confTx = el("span", "", "conf " + BOXCONF.toFixed(2));
  confTx.style.cssText = "font-size:11px;color:var(--mut);white-space:nowrap;min-width:62px";
  conf.oninput = () => {
    BOXCONF = parseFloat(conf.value);
    confTx.textContent = "conf " + BOXCONF.toFixed(2);
    redraw();
  };

  wrap.appendChild(sel); wrap.appendChild(conf); wrap.appendChild(confTx); wrap.appendChild(note);

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
      note.textContent = "추론 시작…";
      await fetch(`/api/boxdump_start?exp=${encodeURIComponent(exp)}&clip=${encodeURIComponent(clip)}`).catch(() => {});
    } else {
      // 도는 중이어도 지금까지 나온 박스는 그린다(사건 구간부터 훑으므로 초반에 이미 쓸 만하다)
      if (r.rows && r.rows.length) { row.tracks = r.rows; redraw(); }
      const nb = (r.rows || []).reduce((a, x) => a + (x.boxes || []).length, 0);
      note.textContent = `추론 중… ${r.pct != null ? r.pct + "%" : ""}`
        + (r.rows && r.rows.length ? ` (표본 ${r.rows.length} · 박스 ${nb})` : "");
    }
    timer = setTimeout(() => load(exp), 3000);           // 다 될 때까지 3초마다 확인
  }

  boxModels().then(all => {
    const list = (all || []).filter(m => m.kind === kind);   // 이 클립과 같은 갈래만
    list.forEach(m => {
      // mAP 가 아니라 실제 KISA 점수를 보여준다(순위도 그것으로 매겨져 있다)
      const tag = m.deploy ? ` · ${m.deploy}` : (m.why ? ` · ${m.why}` : "");
      const o = el("option", "", `${m.exp}${tag}`);
      o.value = m.exp; sel.appendChild(o);
    });
    if (!list.length) { note.textContent = kind === "fire" ? "불 학습 모델 없음" : "사람 학습 모델 없음"; return; }
    const want = BOXEXP[kind];
    if (want && list.some(m => m.exp === want)) { sel.value = want; load(want); }
  });
  sel.onchange = () => { BOXEXP[kind] = sel.value; row.tracks = null; redraw(); load(sel.value); };
  return wrap;
}
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
      for (const b of nmsBoxes(near.boxes.filter(x => x[1] >= BOXCONF), 0.5, 0.75)) {
        const col = fire ? (b[0] ? "#a371f7" : "#f85149") : "#f85149";
        s += `<rect x="${b[2]}" y="${b[3]}" width="${b[4] - b[2]}" height="${b[5] - b[3]}" fill="none" stroke="${col}" stroke-width="2"/>`;
      }
    }
  }
  s += "</svg>"; ov.innerHTML = s;
}

// ---------- 우: 맵 / 손라벨 ----------
function renderRight(row) {
  const r = $("#right"); r.innerHTML = "";
  r.appendChild(el("div", "rtitle", "영상 정보"));
  const KV = (k, val) => { const d = el("div", "kv"); d.appendChild(el("span", "", k)); d.appendChild(el("b", "", val)); return d; };
  r.appendChild(KV("이름", row.name));
  r.appendChild(KV("정답 GT", fmt(row.gt)));
  r.appendChild(KV("예측 알람", fmt(alarmOf(row, CUR.item))));
  r.appendChild(KV("판정", verdict(row, CUR.item)));
  r.appendChild(KV("시간대", row.tod || "-"));
  if ((row.weather || []).length) {
    const d = el("div", "kv"); d.appendChild(el("span", "", "특이날씨"));
    const b = el("b"); row.weather.forEach(w => b.appendChild(el("span", "tag warn", w))); d.appendChild(b); r.appendChild(d);
  }
  if (row.zone && row.zone.length) {
    r.appendChild(el("div", "rtitle", `구역맵 <span class="tag">${row.zone_tag}</span>`));
    const wrap = el("div", "zonewrap");
    const W = row.framew || 1280, He = row.frameh || 720;
    let s = `<svg viewBox="0 0 ${W} ${He}">`;
    if (row.detect && row.detect.length) s += `<polygon points="${row.detect.map(p => p.join(",")).join(" ")}" fill="none" stroke="#8b949e" stroke-width="2" stroke-dasharray="6 4"/>`;
    s += `<polygon points="${row.zone.map(p => p.join(",")).join(" ")}" fill="#3fb95022" stroke="#3fb950" stroke-width="3"/></svg>`;
    wrap.innerHTML = s; r.appendChild(wrap);
    r.appendChild(el("div", "leg", '<span><i style="background:#3fb950"></i>탐지구역</span><span><i style="background:#8b949e"></i>전체영역</span>'));
  }
  if (CUR.item === "fire") renderLabels(r, row);
}
function renderLabels(r, row) {
  if (!LABELS) return;
  const mine = LABELS.filter(l => l.clip === row.name);
  if (!mine.length) return;   // 손라벨(사람이 그린 정답)이 없으면 섹션 자체를 숨김 — 배포 영상은 원래 없음
  r.appendChild(el("div", "rtitle", `손라벨(사람 정답) <span class="tag">${mine.length}박스</span>`));
  const frames = [...new Set(mine.map(l => l.file))];
  // 그림은 미리 뽑아 둔 PNG 가 아니라 영상에서 그때 뽑는다(그 폴더는 만든 적이 없다).
  // 손라벨 행에 src(영상 상대경로)와 t(초)가 들어 있다.
  const srcOfFile = {};
  mine.forEach(l => { if (l.src && !srcOfFile[l.file]) srcOfFile[l.file] = l; });
  const frameUrl = (file, w) => {
    const l = srcOfFile[file];
    if (!l) return "/frame/" + encodeURIComponent(file);       // 옛 자료(src 없는 행) 대비
    const clip = String(l.src).replace(/\.mp4$/i, "");
    return "/frameat?clip=" + encodeURIComponent(clip) + "&t=" + l.t + (w ? "&w=" + w : "");
  };
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
  img.dataset.file = frames[0]; img.src = frameUrl(frames[0]);
  if (frames.length > 1) {
    const th = el("div", "thumbs");
    frames.slice(0, 12).forEach((f, i) => {
      const tw = el("div", "tw" + (i === 0 ? " on" : "")); const ti = el("img");
      ti.loading = "lazy"; ti.src = frameUrl(f, 180); tw.appendChild(ti);
      tw.onclick = () => { img.dataset.file = f; img.src = frameUrl(f); th.querySelectorAll(".tw").forEach(z => z.classList.remove("on")); tw.classList.add("on"); };
      th.appendChild(tw);
    });
    r.appendChild(th);
  }
}

