// dash_v2/js/data.js — 데이터 확인 탭(원본/학습 데이터 브라우징·이미지·영상). app.js 에서 분리(2026-09-09). 로드 순서: core → review → data → editor → main (dashboard.html)
// ---------- 데이터 확인 탭 ----------
let DSMETA = null, DS_CUR = null, DS_ONLY_LABELED = false, DS_SEL = null, DS_KIND = "raw", DS_EDIT = false;   // raw=원본, ds=학습
let SOURCES = null;                           // 원본 카테고리 목록(/api/sources). 한 번 받아 재사용
const DS_SEL_BY = { raw: null, ds: null };   // 원본/학습 각각 마지막에 고른 항목
const CONDS_BY = {};                          // 카테고리 → 촬영조건(한 번 받으면 재사용)
let RAW_CAT = "", SUBSEL = "", COND_REDRAW = null;   // 지금 보는 카테고리 · 하위폴더 드롭다운 값 · 조건칩 다시그리기
async function buildDatasetSrc() {
  // 학습 데이터셋 목록. DS_KIND 가 "raw" 로 못 박혀 있어 지금은 화면에서 안 쓰지만,
  // 없을 때 터지면 데이터 확인 탭 전체가 안 뜬다. 빈 값으로 넘어간다.
  if (!DSMETA) {
    try { DSMETA = await (await fetch("/api/dataset")).json(); }
    catch (e) { DSMETA = { datasets: [] }; }
  }
  if (!SOURCES) { try { SOURCES = await (await fetch("/api/sources")).json(); } catch (e) { SOURCES = []; } }
  const sel = $("#srcSel"); sel.innerHTML = "";
  $("#filtBox").hidden = true;
  // 드롭다운 위: 원본 데이터 / 학습 데이터 고르는 버튼
  let kb = $("#dsKind");
  if (!kb) { kb = el("div"); kb.id = "dsKind"; $(".srcbox").insertBefore(kb, $(".srcbox").firstChild); }   // srcbox 맨 위(이름표보다 위)로. 이름표는 바로 아래 드롭다운의 것이다
  kb.hidden = false;
  kb.className = "tools"; kb.style.cssText = "";   // 모양은 dashboard.html 의 .srcbox .tools 가 정한다
  kb.innerHTML = "";
  DS_KIND = "raw";                                  // 학습 데이터(의사라벨 세트) 탭은 뺐다. 원본만 본다
  // 고를 종류가 원본 하나뿐이라 '원본 데이터' 버튼은 없앴다(2026-09-15). 새로고침만 남긴다.
  // 새로고침은 카테고리 드롭다운 오른쪽에 둔다(무엇을 다시 읽는 단추인지 붙어 있어야 분명하다)
  let sr = document.getElementById("srcRow");
  if (!sr) {
    sr = el("div"); sr.id = "srcRow";
    sr.style.cssText = "display:flex;gap:6px;align-items:stretch";
    sel.parentElement.insertBefore(sr, sel); sr.appendChild(sel);
    sel.style.flex = "1 1 auto"; sel.style.minWidth = "0";   // 드롭다운이 남는 폭을 쓰고, 좁아져도 단추를 밀지 않게
  }
  { const _old = document.getElementById("refreshBtn"); if (_old) _old.remove(); }
  const cb = el("button", null, "\u21bb"); cb.id = "refreshBtn";
  cb.title = "서버 폴더 캐시 새로고침(데이터 폴더를 옮기거나 이름 바꾼 뒤)";
  cb.style.cssText = "flex:0 0 34px;border-radius:7px;padding:0;cursor:pointer;font-size:13px;background:var(--panel);color:var(--mut);border:1px solid var(--line)";
  cb.onclick = async () => { cb.textContent = "\u2026"; try { await fetch("/api/refresh_cache", { method: "POST" }); } catch (e) {} SOURCES = null; DSMETA = null; buildDatasetSrc(); };
  sr.appendChild(cb);
  initPushButton();                               // 보내기 버튼은 이 줄(새로고침 왼쪽)에 붙는다
  // 드롭다운은 고른 쪽만
  if (DS_KIND === "raw") {
    $(".srcbox label").hidden = true;   // 드롭다운만 봐도 알아볼 수 있어 이름표를 안 둔다
    SOURCES.forEach(x => {
      const o = el("option"); o.value = "raw:" + x.key;
      o.textContent = x.count ? `${x.key} (영상 ${x.count}편)` : x.key;
      sel.appendChild(o);
    });
  } else {
    $(".srcbox label").textContent = "학습 데이터셋";
    DSMETA.datasets.forEach(d => {
      const o = el("option"); o.value = "ds:" + d.key;
      o.textContent = `${d.title} (${d.total.toLocaleString()}장)`; sel.appendChild(o);
    });
  }
  if (!DS_SEL || ![...sel.options].some(o => o.value === DS_SEL)) DS_SEL = (sel.options[0] || {}).value;
  if (!DS_SEL) { $("#list").innerHTML = '<div class="empty">보여줄 데이터가 없습니다</div>'; return; }
  sel.value = DS_SEL; DS_SEL_BY[DS_KIND] = DS_SEL;
  sel.onchange = () => { DS_SEL_BY[DS_KIND] = sel.value; pickDataSrc(sel.value); };
  pickDataSrc(DS_SEL);
}

function pickDataSrc(v) {
  DS_SEL = v;
  if (v.startsWith("ds:")) { DS_CUR = DSMETA.datasets.find(d => d.key === v.slice(3)); renderDatasetList(); }
  else renderRawList(v.slice(4));
}

// ---------- 원본데이터 둘러보기 (이미지·영상 원재료) ----------
async function renderRawList(cat) {
  DS_EDIT = true;   // 카테고리 새로 고르면 편집가능 항목은 라벨편집부터(catMode 가 none 이면 자동으로 재생)
  const box = $("#list"); box.innerHTML = '<div class="empty">불러오는 중…</div>';
  $("#center").innerHTML = '<div class="empty">항목을 선택하세요</div>';
  $("#right").innerHTML = '<div class="empty">—</div>';
  let r;
  try { r = await (await fetch("/api/raw?src=" + encodeURIComponent(cat))).json(); }
  catch (e) { box.innerHTML = '<div class="empty">이 카테고리를 못 읽었습니다</div>'; return; }
  box.innerHTML = "";
  RAW_CAT = cat; SUBSEL = ""; COND_REDRAW = null;
  // 목록 맨 위 머리글. 하위폴더 드롭다운과 촬영조건 칩을 한 상자에 넣고 이 상자만 고정한다
  // (둘을 각각 sticky 로 붙이면 높이가 서로 달라 겹친다).
  const head = el("div"); head.id = "listHead";
  head.style.cssText = "position:sticky;top:-6px;z-index:3;background:var(--bg,#0d1117);" +
    "margin:-6px -6px 6px;padding:8px 6px 6px;border-bottom:1px solid var(--line);" +
    "display:flex;flex-direction:column;gap:6px";
  box.appendChild(head);
  // 하위 폴더가 여럿인 카테고리(kisa_연구개발_사람영상 = 배회·침입·쓰러짐 825편)는
  // 한 목록에 다 쏟아지면 고르기 어렵다. 폴더별로 추려 보는 드롭다운을 위에 둔다.
  const subs = [...new Set(r.videos.map(v => subOf(cat, v)).filter(Boolean))].sort();
  if (subs.length > 1) {
    const row = filterRow("항목");         // 드롭다운 대신 칩. 조건·표시 줄과 같은 모양이라 한눈에 읽힌다
    row.id = "subFilterRow";
    const pretty = sub => sub.replace(/^\d+\.\s*/, "").replace(/\s*\(\d+개\)\s*$/, "");
    const drawSubs = () => {
      row.wrap.innerHTML = "";
      const pick = v => { SUBSEL = v; drawSubs(); if (COND_REDRAW) COND_REDRAW(); applyCondFilter(box); openFirstVisible(box); };
      row.wrap.appendChild(filterChip("전체", r.videos.length, SUBSEL === "", () => pick("")));
      subs.forEach(sub => {
        const n = r.videos.filter(v => subOf(cat, v) === sub).length;
        row.wrap.appendChild(filterChip(pretty(sub), n, SUBSEL === sub, () => pick(sub)));
      });
    };
    drawSubs(); head.appendChild(row);
  }
  // 촬영조건 필터(야간·눈·비·안개). 조건 XML 이 있는 카테고리에서만 뜬다.
  if (r.videos.length) {
    const cf = el("div"); cf.id = "condFilterRow";
    head.appendChild(cf);
    let cd = CONDS_BY[cat];                       // 조건을 먼저 받아 목록과 같이 그린다(늦게 따로 뜨지 않게)
    if (!cd) { try { cd = await (await fetch("/api/clipconds?src=" + encodeURIComponent(cat))).json(); } catch (e) { cd = {}; } CONDS_BY[cat] = cd || {}; }
    {
      CONDS = cd || {}; CLIPFILTER = "";
      const draw = () => {
        cf.innerHTML = ""; cf.style.cssText = "display:flex;flex-direction:column;gap:5px";   // 고정은 바깥 #listHead 가 한다
        const rowC = filterRow("조건"), rowM = filterRow("표시");
        const cnt = key => { const k0 = CLIPFILTER; CLIPFILTER = key; const n = r.videos.filter(v => (!SUBSEL || subOf(cat, v) === SUBSEL) && passFilter(v.split("/").pop().replace(/\.mp4$/, ""))).length; CLIPFILTER = k0; return n; };
        [["", "전체"], ["night", "야간"], ["day", "주간"]]   // 눈·비·안개는 편수가 적고, 야간·악천후는 야간과 같은 편이라 뺐다
          .forEach(([key, label]) => {
            const n = cnt(key);
            if (key && !n) return;
            rowC.wrap.appendChild(filterChip(label, n, CLIPFILTER === key,
              () => { CLIPFILTER = key; draw(); applyCondFilter(box); }));
          });
        // 표시 필터(손·전파·기본). 조건 칩과 같은 기준(하위폴더·조건)으로 센다
        const mcnt = key => { const k0 = MARKFILTER; MARKFILTER = key; const n = r.videos.filter(v => {
            const st = v.split("/").pop().replace(/\.mp4$/, "");
            return (!SUBSEL || subOf(cat, v) === SUBSEL) && passFilter(st) && passMark(st); }).length; MARKFILTER = k0; return n; };
        [["", "전체"], ["hand", "완료"], ["prop", "전파"], ["base", "기본"], ["smoke", "연기미완"]].forEach(([key, label]) => {
          rowM.wrap.appendChild(filterChip(label, mcnt(key), MARKFILTER === key,
            () => { MARKFILTER = key; draw(); applyCondFilter(box); }));
        });
        cf.appendChild(rowC); cf.appendChild(rowM);
      };
      draw(); COND_REDRAW = draw;
    }
  }
  if (!head.children.length) head.remove();      // 드롭다운도 조건칩도 없으면 빈 줄만 남는다
  if (!r.images.length && !r.videos.length) {
    box.innerHTML = '<div class="empty">이 폴더엔 이미지·영상이 없습니다<br><small>압축 상태이거나 라벨 파일만 있는 폴더</small></div>';
    return;
  }
  if (r.images.length) {
    r.images.forEach(rel => {
      const it = el("div", "item"); it.dataset.rel = rel;   // 강조·배지가 영상과 같은 규칙으로 찾을 수 있게
      { const _b = listBadge("img:" + rel); if (_b) it.appendChild(_b); }   // 영상과 같은 배지
      const nm = el("span", "nm", rel.split("/").pop()); nm.title = rel; nm.style.userSelect = "text"; nm.style.cursor = "text";
      it.appendChild(nm);
      it.onclick = () => { if (window.getSelection && String(window.getSelection())) return; openImage(rel); };
      box.appendChild(it);
    });
    openImage(r.images[0]);
  }
  if (r.videos.length) {
    r.videos.forEach(rel => {
      const it = el("div", "item"); it.dataset.rel = rel;
      { const _b = listBadge(rel.split("/").pop().replace(/\.mp4$/, ""), rel); if (_b) it.appendChild(_b); }   // [표시 숫자][파일명]
      const nm = el("span", "nm", rel.split("/").pop()); nm.title = rel; nm.style.userSelect = "text"; nm.style.cursor = "text";
      it.appendChild(nm);
      it.onclick = () => { if (window.getSelection && String(window.getSelection())) return; openClip(rel); };
      box.appendChild(it);
    });
    applyCondFilter(box);
    if (!r.images.length) {
      let last = null; try { last = (loadSession() || {}).rel; } catch (e) {}
      openClip(last && r.videos.includes(last) ? last : r.videos[0]);   // 마지막에 보던 영상이 이 목록에 있으면 그걸로
    }
  }
}

// 조건 필터를 목록 항목에 적용한다(검색 필터와 겹치지 않게 hidden 만 건드린다).
function applyCondFilter(box) {
  box.querySelectorAll(".item").forEach(it => {
    const nm = it.querySelector(".nm");
    const rel = (nm && (nm.title || nm.textContent)) || "";
    if (!/\.mp4$/i.test(rel)) return;                 // 이미지 항목은 조건이 없다
    const okSub = !SUBSEL || subOf(RAW_CAT, rel) === SUBSEL;
    const stem = rel.split("/").pop().replace(/\.mp4$/, "");
    it.hidden = !(okSub && passFilter(stem) && passMark(stem));
  });
}

// 원본데이터 기준 상대경로에서 '카테고리 바로 아래 폴더' 이름. 카테고리 밑 파일이면 빈 문자열.
function subOf(cat, rel) {
  const p = String(rel).replace(/^data\/원본데이터\//, "").split("/");
  return p[0] === cat && p.length > 2 ? p[1] : "";
}

// 지금 보이는 첫 항목을 연다(하위 폴더를 바꾸면 그 폴더 첫 영상으로).
function openFirstVisible(box) {
  const it = [...box.querySelectorAll(".item")].find(x => !x.hidden);
  if (it) it.click();
}

// 원본 이미지 한 장. 같은 이름 YOLO txt 가 있으면 박스도 그린다.
async function showRawImage(rel) {
  const c = $("#center"); c.innerHTML = "";
  const enc = rel.split("/").map(encodeURIComponent).join("/");
  const wrap = el("div", "lblframe");
  wrap.style.cssText = "position:relative;display:inline-block;align-self:center;margin:auto;max-width:calc(100% - 32px)";
  const img = el("img");
  img.style.cssText = "display:block;max-width:100%;max-height:calc(100vh - 150px);width:auto;height:auto;border-radius:8px";
  const ov = el("div"); ov.style.cssText = "position:absolute;inset:0";
  img.src = "/dsimg/" + enc;
  wrap.appendChild(img); wrap.appendChild(ov); c.appendChild(wrap);
  let boxes = [];
  try {
    const txt = await (await fetch("/api/rawlabel?rel=" + encodeURIComponent(rel))).text();
    boxes = txt.trim().split("\n").filter(Boolean).map(l => l.split(/\s+/).map(Number)).filter(b => b.length >= 5);
  } catch (e) {}
  const draw = () => {
    const W = img.naturalWidth || 1280, H = img.naturalHeight || 720;
    let g = `<svg viewBox="0 0 ${W} ${H}" style="position:absolute;inset:0;width:100%;height:100%">`;
    boxes.forEach(b => {
      const x = (b[1] - b[3] / 2) * W, y = (b[2] - b[4] / 2) * H;
      g += `<rect x="${x}" y="${y}" width="${b[3] * W}" height="${b[4] * H}" fill="none" stroke="${clsColorFor(catMode(rel), b[0])}" stroke-width="3"/>`;   // 편집기와 같은 색 규약(화재 0 불·1 연기, 사람 객체색)
    });
    ov.innerHTML = g + "</svg>";
  };
  img.onload = draw; if (img.complete) draw();
  const r = $("#right"); r.innerHTML = "";
  r.appendChild(el("div", "rtitle", "이미지 정보"));
  const KV = (k, val) => { const dv = el("div", "kv"); dv.appendChild(el("span", "", k)); dv.appendChild(el("b", "", val)); return dv; };
  // 긴 파일명·경로는 한 줄에 안 들어간다 → 제목 아래에 쌓아서 줄바꿈으로 보여준다
  const KVstack = (k, val) => {
    const d = el("div"); d.style.cssText = "padding:6px 0;border-bottom:1px solid var(--line)";
    const t = el("div", "", k); t.style.cssText = "color:var(--mut);font-size:11px;margin-bottom:2px";
    const v = el("div", "", val);
    v.style.cssText = "font-family:ui-monospace,Menlo,monospace;font-size:11px;word-break:break-all;line-height:1.45";
    d.appendChild(t); d.appendChild(v); return d;
  };
  imageRightPanel(rel, false, boxes.length);
}
// 이미지 항목 열기: 라벨 모드가 '편집 안 함'이 아니면 편집기(기본), 아니면 보기
function openImage(rel) {
  saveSession({ img: rel, rel: null });
  markListItem(rel);                                    // 지금 보는 이미지 표시(영상과 같은 규칙)
  if (catMode(rel) !== "none") openImageEdit(rel); else showRawImage(rel);
}
// 이미지 우측 패널: 정보(파일·경로·정답 수) → 라벨 편집/사진 보기 → 라벨 모드
function imageRightPanel(rel, editing, nGT) {
  const r = $("#right"); r.innerHTML = "";
  r.appendChild(el("div", "rtitle", "이미지 정보"));
  const KV = (k, val) => { const dv = el("div", "kv"); dv.appendChild(el("span", "", k)); dv.appendChild(el("b", "", val)); return dv; };
  const KVstack = (k, val) => { const d = el("div"); d.style.cssText = "padding:6px 0;border-bottom:1px solid var(--line)"; const t = el("div", "", k); t.style.cssText = "color:var(--mut);font-size:11px;margin-bottom:2px"; const v = el("div", "", val); v.style.cssText = "font-family:ui-monospace,Menlo,monospace;font-size:11px;word-break:break-all;line-height:1.45"; d.appendChild(t); d.appendChild(v); return d; };
  r.appendChild(KVstack("파일", rel.split("/").pop()));
  r.appendChild(KVstack("경로", rel.replace(/\/[^/]+$/, "")));
  r.appendChild(KV("정답(원본)", nGT ? nGT + "박스" : "없음"));
  const _n = (typeof IMGLABELS !== "undefined" && IMGLABELS) ? IMGLABELS.filter(x => x.clip === "img:" + rel && x.cls >= 0).length : 0;
  r.appendChild(KV("손라벨", _n ? _n + "박스" : "없음"));
  if (isScoringCat(catOf(rel))) r.appendChild(KV("주의", "채점 전용 · 라벨해도 학습셋 제외"));
  const eb = el("button", null, editing ? "\u25B6 사진 보기" : "라벨 편집");
  eb.style.cssText = "width:100%;margin-top:10px;padding:8px;border-radius:6px;cursor:pointer;font-weight:700;font-size:12px;" +
    (editing ? "background:var(--panel2);color:var(--tx);border:1px solid var(--blue)" : "background:var(--blue);color:#06090f;border:1px solid var(--blue)");
  eb.onclick = () => { if (editing) { LB.img = null; ED = null; showRawImage(rel); } else openImageEdit(rel); };
  r.appendChild(eb);
  r.appendChild(catModeRow(rel, () => openImage(rel)));
}

// 카테고리(데이터셋)별 라벨 모드. 사용자가 고른 값(서버 catmode.json)이 이름 규칙보다 우선한다.
let DATASETS = {};                                 // 데이터 규격(datasets.yaml): {카테고리: {mode, media, gt, classes, use, note}} main.js boot 에서 받는다
function catOf(rel) { return (rel || "").split("/")[2] || ""; }
function isScoringCat(cat) {                       // 채점 전용: 라벨해도 학습셋엔 안 들어간다(행에 eval 표시). 규격 파일(use: eval)이 기준, 없는 카테고리만 이름으로 짐작
  const u = (DATASETS[cat] || {}).use;
  return u ? u === "eval" : /검증|채점|배포/.test(cat);
}
function catModeAuto(cat) {                        // 이름으로 짐작하는 기본값(사용자가 안 고른 경우)
  if (/사람|침입|쓰러짐|배회|스토킹|이상행동|다각도|person|human|llvip|coco/i.test(cat)) return "person";
  return "fire";                                   // 나머지는 불·연기로 연다. 다르면 사용자가 바꾼다
}
function clipMode(rel) {                           // 클립 하나의 라벨 모드. 한 카테고리에 항목이 섞여 있을 때 폴더 이름으로 가른다
  const p = String(rel || "");
  if (/(^|\/)[^/]*(방화|화재|fire)[^/]*\//i.test(p)) return "fire";
  if (/(^|\/)[^/]*(침입|배회|쓰러짐|사람|person)[^/]*\//i.test(p)) return "person";
  return catMode(rel);                            // 폴더로 못 가르면 카테고리 규격대로
}
function catMode(rel) {
  const v = (DATASETS[catOf(rel)] || {}).mode;
  return (v === "fire" || v === "person" || v === "none") ? v : catModeAuto(catOf(rel));
}
async function setCatMode(cat, mode) {             // datasets.yaml 의 mode 를 바꾼다(서버 저장, 브라우저 무관)
  DATASETS[cat] = Object.assign(DATASETS[cat] || {}, { mode });
  try { await fetch("/api/datasets", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cat, mode }) }); } catch (e) {}
}
// 우측 패널의 모드 선택 줄: [불·연기 v] [적용]. 적용하면 그 데이터셋 전체에 고정된다.
function catModeRow(rel, onApply) {
  const cat = catOf(rel);
  const row = el("div"); row.style.cssText = "display:flex;gap:6px;align-items:center;margin-top:10px";
  const lab = el("span", null, "라벨 모드"); lab.style.cssText = "color:var(--mut);font-size:11px;flex:0 0 auto";
  const sel = el("select");
  sel.style.cssText = "flex:1;height:28px;background:var(--panel);color:var(--tx);border:1px solid var(--line);border-radius:6px;font-size:12px;padding:0 6px";
  [["fire", "불·연기"], ["person", "사람"], ["none", "편집 안 함"]].forEach(([k, t]) => { const o = el("option"); o.value = k; o.textContent = t; sel.appendChild(o); });
  sel.value = catMode(rel);
  const ap = el("button", null, "적용");
  ap.style.cssText = "flex:0 0 auto;width:auto;padding:0 10px;height:28px;background:var(--blue);color:#06090f;border:1px solid var(--blue);border-radius:6px;font-weight:700;font-size:12px;cursor:pointer";
  ap.onclick = async () => { ap.textContent = "..."; await setCatMode(cat, sel.value); ap.textContent = "적용"; if (onApply) onApply(); };
  row.appendChild(lab); row.appendChild(sel); row.appendChild(ap);
  return row;
}
// ---------- 클립 상태(표시 기본/전파/손 + 전파 구간) ----------
// 서버 저장이라 다른 PC·Thor 에서도 같이 보인다(손라벨 폴더에 있어 '서버로 라벨 보내기' 에 같이 간다).
let CLIPST = {};                       // stem -> {mark, a, b, smoke}   smoke:"todo" = 불은 쳤고 연기가 아직 덜 쳐진 편
const MARK_TXT = { hand: "완료", prop: "전파" };   // 저장값은 hand 그대로(이미 적힌 것·병합 규칙이 그 값을 쓴다)
const MARK_COL = { hand: "#3fb950", prop: "#f85149" };
async function loadClipStates() {
  try { CLIPST = await (await fetch("/api/clipstates")).json(); } catch (e) { CLIPST = {}; }
}
async function saveClipState(stem, patch) {   // patch 에 넣은 항목만 고친다. mark:"base" 나 a:null 이면 지운다
  const cur = Object.assign({}, CLIPST[stem] || {});
  Object.keys(patch).forEach(k => { if (patch[k] === null || patch[k] === "base") delete cur[k]; else cur[k] = patch[k]; });
  CLIPST[stem] = cur;
  if (!Object.keys(cur).length) delete CLIPST[stem];
  try { await fetch("/api/clipstate", { method: "POST", headers: { "Content-Type": "application/json" },
                                        body: JSON.stringify(Object.assign({ clip: stem }, patch)) }); } catch (e) {}
}
let MARKFILTER = "";                   // "" 전체 · hand 손 · prop 전파 · base 기본(표시 없음)
function passMark(stem) {
  if (!MARKFILTER) return true;
  const st = CLIPST[stem] || {};
  if (MARKFILTER === "smoke") return st.smoke === "todo";   // 연기 미완은 표시와 따로 본다(완료 편에도 붙는다)
  return (st.mark || "base") === MARKFILTER;
}
function filterChip(label, n, on, onclick) {           // 필터 줄에 쓰는 칩. 모양을 한 곳에서 만든다
  const b = el("button", null, n == null ? label : `${label} ${n}`);
  b.style.cssText = "flex:0 0 auto;width:auto;padding:3px 9px;font-size:11px;font-weight:700;border-radius:6px;cursor:pointer;font-variant-numeric:tabular-nums;white-space:nowrap;" +   // 고정폭 숫자: 825 -> 100 이 돼도 칩 폭이 안 흔들린다
    (on ? "background:#58a6ff22;color:#cfe4ff;border:1px solid #58a6ff55" : "background:var(--panel);color:var(--mut);border:1px solid var(--line)");
  b.onclick = onclick;
  return b;
}
function filterRow(title) {                            // [이름표][칩 …] 한 줄. 칩은 넘치면 접힌다
  const row = el("div");
  row.style.cssText = "display:flex;align-items:flex-start;gap:6px";
  const t = el("span", null, title);
  t.style.cssText = "flex:0 0 26px;padding-top:4px;font-size:11px;font-weight:700;color:var(--mut)";
  const wrap = el("div");
  wrap.style.cssText = "flex:1 1 auto;display:flex;flex-wrap:wrap;gap:4px";
  row.appendChild(t); row.appendChild(wrap); row.wrap = wrap;
  return row;
}
function listBadge(key, rel) {          // 목록 배지 한 덩어리: '전파 32' · '완료' · 기본이면 '32'
  const n = labeledCount(key, rel ? clipMode(rel) : null);   // 그 클립 모드의 라벨만 센다(방화 클립은 불·연기만)
  const st = CLIPST[key] || {};
  const m = st.mark;                   // 표시(hand/prop). 기본이면 없다
  const sm = st.smoke === "todo";      // 연기가 아직 덜 쳐진 편
  if (!n && !m && !sm) return null;
  const b = el("span"); b.className = "bg"; b.style.cssText = BADGE_CSS;
  const showN = n && m !== "hand";                      // 완료 편은 프레임 수를 안 쓴다
  if (!showN && !m && !sm) return null;
  b.innerHTML = (m ? `<span style="color:${MARK_COL[m]}">${MARK_TXT[m]}</span>` : "")
              + (sm ? `${m ? " " : ""}<span style="color:#d29922">연기</span>` : "")
              + (showN ? ((m || sm) ? " " : "") + `<span style="color:#fff">${n}</span>` : "");   // 한글만 색 · 숫자는 흰색
  return b;
}
function updateListBadge(key) {        // 라디오를 누르거나 프레임이 늘면 그 항목 배지만 다시 그린다
  document.querySelectorAll("#list .item").forEach(it => {
    if (!it.dataset.rel || labelKeyOf(it.dataset.rel) !== key) return;
    const old = it.querySelector(":scope > span.bg"); if (old) old.remove();
    const b = listBadge(key, it.dataset.rel);
    if (b) it.insertBefore(b, it.querySelector(":scope > span.nm"));
  });
}
function markRadioRow(stem) {          // 기본/전파/손 라디오. 고르면 바로 서버에 저장하고 목록도 고친다
  const row = el("div");
  row.style.cssText = "display:flex;align-items:center;gap:10px;margin-top:10px;padding-top:10px;border-top:1px solid var(--line)";
  const lab = el("span", null, "표시");
  lab.style.cssText = "flex:0 0 auto;font-size:11px;font-weight:700;color:var(--mut)";
  row.appendChild(lab);
  const cur = (CLIPST[stem] || {}).mark || "base";
  [["base", "기본"], ["prop", "전파"], ["hand", "완료"]].forEach(([v, t]) => {
    const w = el("label"); w.style.cssText = "display:inline-flex;align-items:center;gap:4px;cursor:pointer;font-size:12px;font-weight:700;color:"
      + (MARK_COL[v] || "var(--tx)");
    const rb = el("input"); rb.type = "radio"; rb.name = "clipmark_" + stem; rb.value = v; rb.checked = (v === cur);
    rb.style.cssText = "margin:0;cursor:pointer";
    rb.onchange = () => { if (rb.checked) { saveClipState(stem, { mark: v }); updateListBadge(stem); if (COND_REDRAW) COND_REDRAW(); } };
    w.appendChild(rb); w.appendChild(el("span", null, t)); row.appendChild(w);
  });
  // 연기 미완: 불만 치고 연기를 아직 안 친 편. 표시를 '완료' 로 올려도 남은 일이 사라지지 않게 따로 적는다.
  const sw = el("label");
  sw.style.cssText = "display:inline-flex;align-items:center;gap:4px;cursor:pointer;font-size:12px;font-weight:700;"
    + "color:#d29922;margin-left:4px;padding-left:10px;border-left:1px solid var(--line)";
  const cb = el("input"); cb.type = "checkbox"; cb.checked = ((CLIPST[stem] || {}).smoke === "todo");
  cb.style.cssText = "margin:0;cursor:pointer";
  cb.onchange = () => { saveClipState(stem, { smoke: cb.checked ? "todo" : null }); updateListBadge(stem); if (COND_REDRAW) COND_REDRAW(); };
  sw.appendChild(cb); sw.appendChild(el("span", null, "연기 미완"));
  row.appendChild(sw);
  return row;
}
const BADGE_CSS = "flex:0 0 auto;display:inline-flex;align-items:center;gap:4px;justify-content:center;min-width:26px;height:18px;padding:0 6px;border-radius:6px;font:700 11px/1 ui-monospace,Menlo,monospace;color:#cfe4ff;background:#58a6ff22;border:1px solid #58a6ff55;margin-right:6px";   // 목록 배지(영상·이미지 공통)
const labelKeyOf = rel => /\.mp4$/i.test(rel) ? rel.split("/").pop().replace(/\.mp4$/, "") : "img:" + rel;   // 목록 항목 → 라벨 저장소 키(영상=stem · 이미지=img:<rel>)
// 지금 보는 항목을 목록에서 강조(영상·이미지 공통)
function markListItem(rel) {
  document.querySelectorAll("#list .item").forEach(e => { const on = e.dataset.rel === rel; e.classList.toggle("on", on); if (on) e.scrollIntoView({ block: "nearest" }); });
}
// 목록 배지(학습데이터 프레임 수) 한 항목만 다시 그린다 — 전파·삭제 직후. key = 영상 stem 또는 img:<rel>
function updateRawBadge(key) { updateListBadge(key); }   // 표시와 숫자가 한 덩어리라 같은 함수를 쓴다
// 좌측 영상 클릭: 편집 중이면 그 영상 편집 유지, 아니면 재생
function openClip(rel) {
  saveSession({ dsKind: DS_KIND, dsSel: DS_SEL, rel: rel, img: null });   // 새로고침 복원용(이미지 기록은 비운다)
  showRawVideo(rel);   // showRawVideo 가 DS_EDIT 를 보고 에디터/영상 결정
}
// 원본 영상 한 편. XML 정답(이벤트 시각)이 있으면 같이 보여준다.
let _SRV_SEQ = 0;   // 늦게 끝난 이전 호출이 우측 정보를 덮지 않게(새로고침 복원 때 첫 항목과 경쟁)
async function showRawVideo(rel) {
  const _my = ++_SRV_SEQ;
  try { saveSession({ dsKind: DS_KIND, dsSel: DS_SEL, rel: rel, img: null }); } catch (e) {}   // 새로고침 복원용(이미지 기록은 비운다)
  const clip = rel.replace(/^data\/원본데이터\//, "").replace(/\.mp4$/, "");
  let events = [], dur = 0, ci = null;
  try { ci = await (await fetch("/api/clipinfo?clip=" + encodeURIComponent(clip))).json(); dur = ci.dur || 0; events = ci.fire || []; } catch (e) {}
  if (_my !== _SRV_SEQ) return;
  markListItem(rel);                                    // 지금 보는 영상 표시
  const first = events[0] || {};
  document.onkeydown = null;
  const _mode0 = clipMode(rel);   // 배포 검증영상처럼 한 카테고리에 항목이 섞이면 폴더로 가른다
  const _editing = DS_EDIT && _mode0 !== "none";
  if (_editing) {
    await openFrameAt(clip, null, _mode0);   // 시작 프레임은 openFrameAt 이 고른다(자동라벨 첫 검출 → 정답 시각 → 0). 기다려야 새로고침 복원이 두 번 열지 않는다
    if (_my !== _SRV_SEQ) return;
  } else {
    ED = null;   // 영상 볼 땐 에디터 재사용상태 초기화(다음 라벨편집이 새로 그리게)
    // 예측 박스 드롭다운이 쓸 갈래. 라벨 모드를 "편집 안 함"으로 둔 경우는 이름으로 짐작한다
    const _kind0 = (_mode0 === "fire" || _mode0 === "person") ? _mode0 : catModeAuto(catOf(rel));
    renderCenter({ video: rel, name: rel.split("/").pop(), signal_type: "raw", signal: [], zone: [], tracks: null, kind: _kind0,
                   weather: [], tod: null, gt: (first.start != null ? first.start : null), gt_dur: first.dur || 0, sa: null });
  }
  // 우측 정보(파일/경로/정답)
  const r = $("#right"); r.innerHTML = "";
  r.appendChild(el("div", "rtitle", "영상 정보"));
  const KV = (k, val) => { const dv = el("div", "kv"); dv.appendChild(el("span", "", k)); dv.appendChild(el("b", "", val)); return dv; };
  const KVstack = (k, val) => {
    const d = el("div"); d.style.cssText = "padding:6px 0;border-bottom:1px solid var(--line)";
    const t = el("div", "", k); t.style.cssText = "color:var(--mut);font-size:11px;margin-bottom:2px";
    const vv = el("div", "", val); vv.style.cssText = "font-family:ui-monospace,Menlo,monospace;font-size:11px;word-break:break-all;line-height:1.45";
    d.appendChild(t); d.appendChild(vv); return d;
  };
  r.appendChild(KVstack("파일", rel.split("/").pop()));
  r.appendChild(KVstack("경로", rel.replace(/\/[^/]+$/, "")));
  if (ci) {
    r.appendChild(KV("길이", `${Math.floor(dur)}초`));
    r.appendChild(KV("해상도", `${ci.W}x${ci.H} · ${ci.fps}fps`));
    events.forEach((fs, i) => r.appendChild(KV(events.length > 1 ? `정답 ${i + 1}` : "정답", `${fmt(fs.start)} · ${fs.dur}초간`)));
    if (!events.length) r.appendChild(KV("정답", "XML 없음"));
  } else r.appendChild(KV("정답", "정보 없음"));
  // 라벨 대상 클립이면 버튼: 편집중=영상보기 / 아니면 라벨편집 (영상정보는 그대로). 정답이 있든 없든 편집할 수 있다(정답 원본은 읽기만).
  const _stem = stemOf(clip);
  const _btn = (txt, primary) => { const b = el("button", null, txt); b.style.cssText = "width:100%;margin-top:10px;padding:8px;border-radius:6px;cursor:pointer;font-weight:700;font-size:12px;" + (primary ? "background:var(--blue);color:#06090f;border:1px solid var(--blue)" : "background:var(--panel2);color:var(--tx);border:1px solid var(--blue)"); return b; };
  if (isScoringCat(catOf(rel))) r.appendChild(KV("주의", "채점 전용 · 라벨해도 학습셋 제외"));
  if (_mode0 !== "none") {
    { const _n = labeledCount(_stem, clipMode(rel)); r.appendChild(KV("학습 라벨", _n ? _n + "프레임" : "없음")); }   // 손라벨 ∪ SAM
    const _eb = _btn(_editing ? "\u25B6 영상 보기" : "라벨 편집", !_editing);
    _eb.onclick = () => { DS_EDIT = !_editing; showRawVideo(rel); };
    r.appendChild(_eb);
  }
  if (_mode0 !== "none") r.appendChild(markRadioRow(_stem));   // 이 클립을 무엇으로 채웠나(기본/전파/손) · 고르면 바로 저장
  r.appendChild(catModeRow(rel, () => { DS_EDIT = true; showRawVideo(rel); }));   // 이 데이터셋을 무엇으로 라벨할지
}
function renderDatasetList() {
  const box = $("#list"); box.innerHTML = "";
  const d = DS_CUR;
  const shown = d.total > d.shown ? `표시 ${d.shown} / ${d.total.toLocaleString()}장` : `${d.total.toLocaleString()}장`;
  // 필터 대신 라벨만 보기 토글
  const bar = el("div"); bar.style.cssText = "padding:6px 3px;display:flex;gap:6px";
  const tog = el("button", DS_ONLY_LABELED ? "on" : "", "라벨 있는 것만");
  tog.style.cssText = "flex:1;background:var(--panel);color:" + (DS_ONLY_LABELED ? "var(--tx)" : "var(--mut)") + ";border:1px solid " + (DS_ONLY_LABELED ? "var(--blue)" : "var(--line)") + ";border-radius:6px;padding:5px;cursor:pointer;font-size:11px";
  tog.onclick = () => { DS_ONLY_LABELED = !DS_ONLY_LABELED; renderDatasetList(); };
  bar.appendChild(tog); box.appendChild(bar);
  // 좌측은 이미지가 많아 격자 썸네일로
  const grid = el("div"); grid.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:4px";
  let imgs = d.images; if (DS_ONLY_LABELED) imgs = imgs.filter(x => x.labeled);
  imgs.slice(0, 300).forEach(im => {
    const tw = el("div"); tw.style.cssText = "position:relative;cursor:pointer;border-radius:5px;overflow:hidden;border:1px solid var(--line);aspect-ratio:16/10;background:#000";
    const t = el("img"); t.loading = "lazy"; t.style.cssText = "width:100%;height:100%;object-fit:cover"; t.src = "/dsimg/" + (im.rel || d.rel) + "/images/train/" + encodeURIComponent(im.file);
    tw.appendChild(t);
    if (im.labeled) { const dot = el("span"); dot.style.cssText = "position:absolute;top:3px;right:3px;width:7px;height:7px;border-radius:50%;background:#3fb950"; tw.appendChild(dot); }
    tw.onclick = () => { box.querySelectorAll(".dson").forEach(z => z.classList.remove("dson")); tw.classList.add("dson"); tw.style.outline = "2px solid var(--blue)"; showDatasetImage(d, im); };
    grid.appendChild(tw);
  });
  box.appendChild(grid);
  if (imgs.length) showDatasetImage(d, imgs[0]);
}
async function showDatasetImage(d, im) {
  const c = $("#center"); c.innerHTML = "";
  const wrap = el("div", "lblframe");
  wrap.style.cssText = "position:relative;display:inline-block;align-self:center;margin:auto;max-width:calc(100% - 32px)";
  const img = el("img");
  img.style.cssText = "display:block;max-width:100%;max-height:calc(100vh - 150px);width:auto;height:auto;border-radius:8px";
  const ov = el("div"); ov.style.cssText = "position:absolute;inset:0";
  img.src = "/dsimg/" + (im.rel || d.rel) + "/images/train/" + encodeURIComponent(im.file);
  wrap.appendChild(img); wrap.appendChild(ov); c.appendChild(wrap);
  // 라벨(YOLO txt) 로드 → 박스
  let boxes = [];
  if (im.labeled) {
    try {
      const txt = await (await fetch("/dslabel/" + (im.rel || d.rel) + "/labels/train/" + encodeURIComponent(im.stem) + ".txt")).text();
      boxes = txt.trim().split("\n").filter(Boolean).map(l => l.split(/\s+/).map(Number));
    } catch (e) {}
  }
  const COL = ["#f85149", "#a371f7", "#58a6ff", "#3fb950", "#d29922"];
  const drawBoxes = () => {
    const W = img.naturalWidth || 1280, H = img.naturalHeight || 720;
    let s = `<svg viewBox="0 0 ${W} ${H}" style="position:absolute;inset:0;width:100%;height:100%">`;
    boxes.forEach(b => {
      // YOLO: cls cx cy w h (중앙 정규화)
      const x = (b[1] - b[3] / 2) * W, y = (b[2] - b[4] / 2) * H;
      s += `<rect x="${x}" y="${y}" width="${b[3] * W}" height="${b[4] * H}" fill="none" stroke="${COL[b[0]] || "#f85149"}" stroke-width="3"/>`;
    });
    s += "</svg>"; ov.innerHTML = s;
  };
  img.onload = drawBoxes; if (img.complete) drawBoxes();
  // 우측: 파일 정보 + 클래스별 박스 수 + 원시 라벨
  const r = $("#right"); r.innerHTML = "";
  r.appendChild(el("div", "rtitle", "데이터 정보"));
  const KV = (k, val) => { const dv = el("div", "kv"); dv.appendChild(el("span", "", k)); dv.appendChild(el("b", "", val)); return dv; };
  r.appendChild(KV("데이터셋", d.title));
  r.appendChild(KV("파일", im.file));
  r.appendChild(KV("YOLO 라벨", boxes.length ? boxes.length + "박스" : "없음 (정상 이미지)"));
  const cnt = {};
  boxes.forEach(b => cnt[b[0]] = (cnt[b[0]] || 0) + 1);
  d.classes.forEach((cl, i) => r.appendChild(KV(cl, String(cnt[i] || 0) + "박스")));
  if (boxes.length) {
    r.appendChild(el("div", "rtitle", "YOLO 라벨 (원문)"));
    const pre = el("div"); pre.style.cssText = "font-family:ui-monospace,monospace;font-size:11px;color:var(--mut);white-space:pre-wrap;word-break:break-all";
    pre.textContent = boxes.map(b => b.map((x, i) => i ? x.toFixed(4) : d.classes[x] || x).join(" ")).join("\n");
    r.appendChild(pre);
  }
}

// ---------- 서버와 라벨 맞추기 (Thor 등 보내는 쪽에서만 보인다) ----------
// 양쪽으로 합친다. 겹치는 값은 이 장비가 이긴다.
// 먼저 미리보기(합치지 않고 무엇이 오갈지만)를 보여주고, 한 번 더 누르면 실제로 합친다.
async function initPushButton() {
  let info = {};
  try { info = await (await fetch("/api/pushinfo")).json(); } catch (e) { return; }
  if (!info.enabled) return;                       // 서버 쪽에서는 아예 안 만든다
  const box = document.querySelector(".srcbox");
  if (!box) return;
  const row = document.getElementById("dsKind");     // 새로고침(↻) 이 있는 줄
  const CSS_ROW = "flex:1 1 auto;padding:6px 9px;font-size:11px;font-weight:700;border-radius:6px;" +
                  "background:var(--panel);color:var(--tx);border:1px solid var(--line);cursor:pointer";
  const CSS_BOX = "width:100%;margin-top:8px;padding:7px 9px;font-size:12px;font-weight:700;border-radius:7px;" +
                  "background:var(--panel);color:var(--tx);border:1px solid var(--line);cursor:pointer";
  const had = document.getElementById("pushBtn");
  if (had) {                                        // 화면이 만들어지기 전에 먼저 붙었던 버튼은 줄이 생기면 옮긴다
    if (row && had.parentElement !== row) { had.style.cssText = CSS_ROW; row.insertBefore(had, row.firstChild); }
    return;
  }
  const b = el("button", null, "서버와 라벨 맞추기");
  b.id = "pushBtn";
  b.style.cssText = row ? CSS_ROW : CSS_BOX;
  // 안내 줄은 .srcbox 에 남는데 버튼은 #dsKind 를 비울 때마다 다시 만들어진다.
  // 그때 안내 줄도 새로 만들면 화면에 안 붙은 채 글자만 쓰게 돼 아무것도 안 보인다. 있으면 그것을 쓴다.
  let note = document.getElementById("pushNote");
  if (!note) {
    note = el("div", null, "");
    note.id = "pushNote";
    note.style.cssText = "margin-top:4px;font-size:11px;color:var(--mut);white-space:pre-wrap;line-height:1.5";
    box.appendChild(note);
  }
  let staged = false;                               // 미리보기를 본 뒤인가
  b.onclick = async () => {
    b.disabled = true;
    const dry = !staged;
    b.textContent = dry ? "확인 중…" : "맞추는 중…";
    let r;
    try { r = await (await fetch("/api/push_labels?dry=" + (dry ? "1" : "0"),
                                 { method: "POST" })).json(); }
    catch (e) { r = { ok: false, err: String(e) }; }
    b.disabled = false;
    if (!r.ok) { note.textContent = "실패: " + (r.err || r.log || "").slice(0, 300); b.textContent = "서버와 라벨 맞추기"; staged = false; return; }
    note.textContent = (r.log || "").trim();
    if (dry) { staged = true; b.textContent = "이대로 맞추기(한 번 더)"; }
    else { staged = false; b.textContent = "서버와 라벨 맞추기"; }
  };
  if (row) row.insertBefore(b, row.firstChild);   // 새로고침 왼쪽
  else box.appendChild(b);
}
