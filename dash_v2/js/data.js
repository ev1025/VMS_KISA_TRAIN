// dash_v2/js/data.js — 데이터 확인 탭(원본/학습 데이터 브라우징·이미지·영상). app.js 에서 분리(2026-09-09). 로드 순서: core → review → data → editor → main (dashboard.html)
// ---------- 데이터 확인 탭 ----------
let DSMETA = null, DS_CUR = null, DS_ONLY_LABELED = false, DS_SEL = null, DS_KIND = "raw";   // raw=원본, ds=학습
let SOURCES = null;                           // 원본 카테고리 목록(/api/sources). 한 번 받아 재사용
const DS_SEL_BY = { raw: null, ds: null };   // 원본/학습 각각 마지막에 고른 항목
const CONDS_BY = {};                          // 카테고리 → 촬영조건(한 번 받으면 재사용)
let RAW_CAT = "", SUBSEL = "", COND_REDRAW = null;   // 지금 보는 카테고리 · 하위폴더 드롭다운 값 · 조건칩 다시그리기
let NAMEQ = "", NAMEQ_OPEN = false;                  // 영상 이름 찾기(돋보기로 열고 닫는다)
// 데이터 드롭다운 표시 이름 = 출처_항목(사람 · 방화 · 공통)_용도(10-02 사용자). 화면 표기만, 폴더 이름(값 · 경로)은 그대로. 여기 없는 폴더는 폴더 이름으로 보인다
// (파생) = 우리가 원본에서 뽑아 만든 셋(AI허브 71751 영상 → 클립당 12프레임 사진)
const SRC_NAME = {
  KISA_악천후_사람: "KISA_사람_악천후", kisa_연구개발_사람영상: "KISA_사람_연구개발", kisa_연구개발_방화영상: "KISA_방화_연구개발",
  kisa_산불_합성영상: "KISA_방화_산불합성", kisa_산불_정지이미지: "KISA_방화_산불이미지", kisa_배포_검증영상: "KISA_공통_배포검증",
  aihub171_이상행동: "AIHUB171_사람_이상행동", aihub71953_다각도: "AIHUB71953_사람_다각도", aihub_침입쓰러짐영상: "AIHUB_사람_침입쓰러짐",
  aihub71330_산불: "AIHUB71330_방화_산불", aihub71751_48k: "AIHUB71751_방화_48k(파생)", aihub71751_night_20260928: "AIHUB71751_방화_야간(파생)",
  open_coco: "COCO_사람_공개셋", open_fasdd: "FASDD_방화_공개셋", open_dfire: "DFIRE_방화_공개셋", open_azimjaan_fire: "AZIMJAAN_방화_공개셋",
};
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
  cb.style.cssText = "flex:0 0 34px;border-radius:var(--r);padding:0;cursor:pointer;font-size:var(--fs-md);background:var(--panel);color:var(--mut);border:1px solid var(--line)";
  cb.onclick = async () => { cb.textContent = "\u2026"; try { await fetch("/api/refresh_cache", { method: "POST" }); } catch (e) {} SOURCES = null; DSMETA = null; buildDatasetSrc(); };
  sr.appendChild(cb);
  initPushButton();                               // 보내기 버튼은 이 줄(새로고침 왼쪽)에 붙는다
  sr.style.display = "flex";
  // 드롭다운은 고른 쪽만
  if (DS_KIND === "raw") {
    $(".srcbox label").hidden = true;   // 드롭다운만 봐도 알아볼 수 있어 이름표를 안 둔다
    // 데이터 확인은 전역 필터와 무관하다(10-01). 규격 use 가 train(학습) · eval(채점 전용, 라벨을 고친다)인 것만 보인다.
    // none(학습 금지) · 그 밖의 값(지금 안 씀 등)은 숨긴다. 규격에 없는 폴더는 보인다(10-02 사용자)
    // 표시 이름 순으로(출처끼리 모인다). 값(폴더 이름)은 그대로
    SOURCES.filter(x => !DATASETS[x.key] || ["train", "eval"].includes(DATASETS[x.key].use))
      .map(x => [x, SRC_NAME[x.key] || x.key]).sort((a, b) => a[1].localeCompare(b[1])).forEach(([x, nm]) => {
      const o = el("option"); o.value = "raw:" + x.key;
      o.textContent = nm;                           // 편수는 안 쓴다(10-02 사용자)
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
  const box = $("#list"); box.innerHTML = '<div class="empty">불러오는 중…</div>';
  $("#center").innerHTML = '<div class="empty">항목을 선택하세요</div>';
  $("#right").innerHTML = '<div class="empty">—</div>';
  let r;
  try { r = await (await fetch("/api/raw?src=" + encodeURIComponent(cat))).json(); }
  catch (e) { box.innerHTML = '<div class="empty">이 카테고리를 못 읽었습니다</div>'; return; }
  if (CUR.mode !== "data") return;               // 받아 오는 사이 다른 탭으로 갔으면 그 탭 목록을 덮지 않는다(09-30 검수 목록에 데이터 목록이 뜨던 원인)
  box.innerHTML = "";
  RAW_CAT = cat; SUBSEL = ""; COND_REDRAW = null;
  // 목록 머리(항목 탭 · 조건 · 표시 · 이름 찾기). 목록 안이 아니라 드롭다운 바로 아래(.srcbox)에 둔다:
  // 목록과 같이 스크롤되지 않고, 목록 스크롤 막대에 폭이 밀리지 않아 드롭다운과 끝이 맞는다(10-02 사용자)
  { const old = document.getElementById("listHead"); if (old) old.remove(); }
  const head = el("div"); head.id = "listHead";
  $(".srcbox").appendChild(head);
  // 하위 폴더가 여럿인 카테고리(kisa_연구개발_사람영상 = 배회·침입·쓰러짐 825편)는 폴더별 밑줄 탭으로 추린다
  const subs = [...new Set(r.videos.map(v => subOf(cat, v)).filter(Boolean))].sort();
  if (subs.length > 1) {
    const tabs = segGroup("dt-tabs", "항목"); tabs.id = "subFilterRow";
    const pretty = sub => sub.replace(/^\d+\.\s*/, "").replace(/\s*\(\d+개\)\s*$/, "");
    const drawSubs = () => {
      tabs.innerHTML = "";
      const pick = v => { SUBSEL = v; drawSubs(); if (COND_REDRAW) COND_REDRAW(); applyCondFilter(box); openFirstVisible(box); };
      tabs.appendChild(segBtn("전체", SUBSEL === "", () => pick(""), r.videos.length));
      subs.forEach(sub => tabs.appendChild(segBtn(pretty(sub), SUBSEL === sub, () => pick(sub), r.videos.filter(v => subOf(cat, v) === sub).length)));
    };
    drawSubs(); head.appendChild(tabs);
  }
  // 촬영조건 필터(야간·눈·비·안개). 조건 XML 이 있는 카테고리에서만 뜬다.
  if (r.videos.length) {
    const cf = el("div"); cf.id = "condFilterRow";
    head.appendChild(cf);
    let cd = CONDS_BY[cat];                       // 조건을 먼저 받아 목록과 같이 그린다(늦게 따로 뜨지 않게)
    if (!cd) { try { cd = await (await fetch("/api/clipconds?src=" + encodeURIComponent(cat))).json(); } catch (e) { cd = {}; } CONDS_BY[cat] = cd || {}; }
    {
      CONDS = cd || {}; CLIPFILTER = "";
      const draw = () => {                         // 이름표 · 편수 없이 세그먼트 두 줄(10-02 사용자). 조건 줄 끝 = 이름 찾기 돋보기
        cf.innerHTML = "";
        const cnt = key => { const k0 = CLIPFILTER; CLIPFILTER = key; const n = r.videos.filter(v => (!SUBSEL || subOf(cat, v) === SUBSEL) && passFilter(v.split("/").pop().replace(/\.mp4$/, ""))).length; CLIPFILTER = k0; return n; };
        const rowC = el("div", "dt-row"), segC = segGroup("dt-seg", "조건");
        [["", "전체"], ["night", "야간"], ["day", "주간"]]   // 눈·비·안개는 편수가 적고, 야간·악천후는 야간과 같은 편이라 뺐다
          .forEach(([key, label]) => {
            if (key && !cnt(key)) return;              // 그 조건 영상이 없으면 단추를 안 둔다
            segC.appendChild(segBtn(label, CLIPFILTER === key, () => { CLIPFILTER = key; draw(); applyCondFilter(box); }));
          });
        const sb = el("button", "dt-sbtn" + (NAMEQ_OPEN ? " on" : ""), SVG_SEARCH); sb.type = "button";
        sb.title = "영상 이름 찾기"; sb.setAttribute("aria-label", "영상 이름 찾기"); sb.setAttribute("aria-expanded", NAMEQ_OPEN);
        sb.onclick = () => { NAMEQ_OPEN = !NAMEQ_OPEN; if (!NAMEQ_OPEN) NAMEQ = ""; draw(); applyCondFilter(box); const i = cf.querySelector(".dt-search"); if (i) i.focus(); };
        rowC.appendChild(segC); rowC.appendChild(sb);
        const segM = segGroup("dt-seg", "표시");     // 기본 · 전파 · 완료 순, 연기미완은 뺐다(10-02 사용자)
        [["", "전체"], ["base", "기본"], ["prop", "전파"], ["hand", "완료"]].forEach(([key, label]) =>
          segM.appendChild(segBtn(label, MARKFILTER === key, () => { MARKFILTER = key; draw(); applyCondFilter(box); })));
        cf.appendChild(rowC); cf.appendChild(segM);
        if (NAMEQ_OPEN) {
          const i = el("input", "dt-search"); i.type = "search"; i.placeholder = "영상 이름"; i.autocomplete = "off"; i.value = NAMEQ;
          i.setAttribute("aria-label", "영상 이름 찾기");
          i.oninput = () => { NAMEQ = i.value.trim().toLowerCase(); applyCondFilter(box); };
          i.onkeydown = e => { e.stopPropagation(); if (e.key === "Escape") { NAMEQ_OPEN = false; NAMEQ = ""; draw(); applyCondFilter(box); } };   // 편집기 단축키로 새지 않게
          cf.appendChild(i);
        }
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
      const it = el("div", "item"); it.dataset.rel = rel; it.dataset.mark = markOf(labelKeyOf(rel));   // 강조·배지가 영상과 같은 규칙으로 찾을 수 있게
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
      const it = el("div", "item"); it.dataset.rel = rel; it.dataset.mark = markOf(labelKeyOf(rel));
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

// 항목 · 조건 · 표시 · 이름 찾기를 목록 항목에 적용한다(hidden 만 건드린다).
function applyCondFilter(box) {
  box.querySelectorAll(".item").forEach(it => {
    const nm = it.querySelector(".nm");
    const rel = (nm && (nm.title || nm.textContent)) || "";
    const okName = !NAMEQ || rel.split("/").pop().toLowerCase().includes(NAMEQ);
    if (!/\.mp4$/i.test(rel)) { it.hidden = !okName; return; }   // 이미지 항목은 조건이 없다
    const okSub = !SUBSEL || subOf(RAW_CAT, rel) === SUBSEL;
    const stem = rel.split("/").pop().replace(/\.mp4$/, "");
    it.hidden = !(okName && okSub && passFilter(stem) && passMark(stem));
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
  img.style.cssText = "display:block;max-width:100%;max-height:calc(100vh - 150px);width:auto;height:auto;border-radius:var(--r-lg)";
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
  modeBox().appendChild(catModeRow(rel, () => openImage(rel)));
}
// 이미지 항목 열기: 라벨 모드가 '편집 안 함'이 아니면 편집기(기본), 아니면 보기
function openImage(rel) {
  saveSession({ img: rel, rel: null });
  markListItem(rel);                                    // 지금 보는 이미지 표시(영상과 같은 규칙)
  if (catMode(rel) !== "none") openImageEdit(rel); else showRawImage(rel);
}
// 표시 · 라벨 모드 칸 = 편집기 도구 줄 오른쪽 끝(프레임 오른쪽 끝과 맞춤). 편집기가 없으면(편집 안 함) 가운데 맨 위. 오른쪽 패널은 없앴다(10-02 사용자)
function modeBox() {
  { const old = document.getElementById("edMode"); if (old) old.remove(); }
  const b = el("div"); b.id = "edMode";
  const acts = document.getElementById("edActs");
  if (acts) acts.appendChild(b); else { b.className = "solo"; $("#center").prepend(b); }
  return b;
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
// 라벨 모드 줄: [불·연기 v] [적용]. 적용하면 그 데이터셋 전체에 고정된다. 이름표 글자는 없다(10-02 사용자)
function catModeRow(rel, onApply) {
  const cat = catOf(rel);
  const row = el("div"); row.style.cssText = "display:flex;gap:6px;align-items:center";
  const sel = el("select"); sel.title = "라벨 모드"; sel.setAttribute("aria-label", "라벨 모드");
  sel.style.cssText = "flex:0 0 auto;height:var(--ctl-h);background:var(--panel);color:var(--tx);border:1px solid var(--line);border-radius:var(--r);font-size:var(--fs-sm);padding:0 6px";
  [["fire", "불·연기"], ["person", "사람"], ["none", "편집 안 함"]].forEach(([k, t]) => { const o = el("option"); o.value = k; o.textContent = t; sel.appendChild(o); });
  sel.value = catMode(rel);
  const ap = el("button", null, "적용");
  ap.style.cssText = "flex:0 0 auto;width:auto;padding:0 10px;height:var(--ctl-h);background:var(--blue);color:#06090f;border:1px solid var(--blue);border-radius:var(--r);font-weight:700;font-size:var(--fs-sm);cursor:pointer";
  ap.onclick = async () => { ap.textContent = "..."; await setCatMode(cat, sel.value); ap.textContent = "적용"; if (onApply) onApply(); };
  row.appendChild(sel); row.appendChild(ap);
  return row;
}
function zoneToggle() {                              // '영역' 체크: KISA 영역(.map) 구역을 편집 화면에 켜고 끔. 브라우저에 기억
  const w = el("label"); w.title = "KISA 영역 파일(.map)의 감시 구역";
  w.style.cssText = "display:inline-flex;align-items:center;gap:4px;white-space:nowrap;cursor:pointer;font-size:var(--fs-sm);font-weight:700;color:#3fb950";
  const cb = el("input"); cb.type = "checkbox"; cb.checked = ZONE_ON; cb.style.cssText = "margin:0;cursor:pointer";
  cb.onchange = () => { ZONE_ON = cb.checked; try { localStorage.setItem("zone_on", ZONE_ON ? "1" : "0"); } catch (e) {} if (ED && ED.redraw) ED.redraw(); };
  w.appendChild(cb); w.appendChild(el("span", null, "영역"));
  return w;
}
// ---------- 클립 상태(표시 기본/전파/손 + 전파 구간) ----------
// 서버 저장이라 다른 PC 에서도 같이 보인다(손라벨 폴더에 있어 '서버로 라벨 보내기' 에 같이 간다).
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
const markOf = key => (CLIPST[key] || {}).mark || "base";
function passMark(stem) { return !MARKFILTER || markOf(stem) === MARKFILTER; }
const SVG_SEARCH = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg>';
function segGroup(cls, label) { const g = el("div", cls); g.setAttribute("role", "group"); g.setAttribute("aria-label", label); return g; }
function segBtn(label, on, onclick, n) {              // 탭 · 세그먼트 단추 하나(데이터 확인 왼쪽 위). n 을 주면 옆에 작게 편수
  const b = el("button", on ? "on" : ""); b.type = "button"; b.textContent = label; b.setAttribute("aria-pressed", on);
  if (n != null) b.appendChild(el("small", "", String(n)));
  b.onclick = onclick;
  return b;
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
    it.dataset.mark = markOf(key);
    const old = it.querySelector(":scope > span.bg"); if (old) old.remove();
    const b = listBadge(key, it.dataset.rel);
    if (b) it.insertBefore(b, it.querySelector(":scope > span.nm"));
  });
}
function markRadioRow(stem) {          // 기본/전파/손 라디오. 고르면 바로 서버에 저장하고 목록도 고친다
  const row = el("div");
  row.style.cssText = "display:flex;align-items:center;gap:6px 10px";
  row.setAttribute("role", "radiogroup"); row.setAttribute("aria-label", "표시");   // 이름표 글자는 없다(10-02 사용자)
  const cur = (CLIPST[stem] || {}).mark || "base";
  [["base", "기본"], ["prop", "전파"], ["hand", "완료"]].forEach(([v, t]) => {
    const w = el("label"); w.style.cssText = "display:inline-flex;align-items:center;gap:4px;white-space:nowrap;cursor:pointer;font-size:var(--fs-sm);font-weight:700;color:"
      + (MARK_COL[v] || "var(--tx)");
    const rb = el("input"); rb.type = "radio"; rb.name = "clipmark_" + stem; rb.value = v; rb.checked = (v === cur);
    rb.style.cssText = "margin:0;cursor:pointer";
    rb.onchange = () => { if (rb.checked) { saveClipState(stem, { mark: v }); updateListBadge(stem); if (COND_REDRAW) COND_REDRAW(); } };
    w.appendChild(rb); w.appendChild(el("span", null, t)); row.appendChild(w);
  });
  // 연기 미완: 불만 치고 연기를 아직 안 친 편. 표시를 '완료' 로 올려도 남은 일이 사라지지 않게 따로 적는다.
  const sw = el("label");
  sw.style.cssText = "display:inline-flex;align-items:center;gap:4px;white-space:nowrap;cursor:pointer;font-size:var(--fs-sm);font-weight:700;"
    + "color:#d29922;margin-left:4px;padding-left:10px;border-left:1px solid var(--line)";
  const cb = el("input"); cb.type = "checkbox"; cb.checked = ((CLIPST[stem] || {}).smoke === "todo");
  cb.style.cssText = "margin:0;cursor:pointer";
  cb.onchange = () => { saveClipState(stem, { smoke: cb.checked ? "todo" : null }); updateListBadge(stem); if (COND_REDRAW) COND_REDRAW(); };
  sw.appendChild(cb); sw.appendChild(el("span", null, "연기 미완"));
  row.appendChild(sw);
  return row;
}
const BADGE_CSS = "flex:0 0 auto;display:inline-flex;align-items:center;gap:4px;justify-content:center;min-width:26px;height:18px;padding:0 6px;border-radius:var(--r);font:700 var(--fs-xs)/1 ui-monospace,Menlo,monospace;color:#cfe4ff;background:#58a6ff22;border:1px solid #58a6ff55;margin-right:6px";   // 목록 배지(영상·이미지 공통)
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
  showRawVideo(rel);   // 라벨 모드가 '편집 안 함' 이 아니면 편집기, 맞으면 영상 재생
}
// 원본 영상 한 편. XML 정답(이벤트 시각)이 있으면 같이 보여준다.
let _SRV_SEQ = 0;   // 늦게 끝난 이전 호출이 표시 · 라벨 모드 칸을 덮지 않게(새로고침 복원 때 첫 항목과 경쟁)
async function showRawVideo(rel) {
  const _my = ++_SRV_SEQ;
  try { saveSession({ dsKind: DS_KIND, dsSel: DS_SEL, rel: rel, img: null }); } catch (e) {}   // 새로고침 복원용(이미지 기록은 비운다)
  const clip = rel.replace(/^data\/원본데이터\//, "").replace(/\.mp4$/, "");
  let events = [];
  try { events = (await (await fetch("/api/clipinfo?clip=" + encodeURIComponent(clip))).json()).fire || []; } catch (e) {}
  if (_my !== _SRV_SEQ || CUR.mode !== "data") return;   // 받아 오는 사이 다른 탭으로 갔으면 그 탭 화면을 덮지 않는다(10-02 히스토리 탭에 편집기가 뜨던 것)
  markListItem(rel);                                    // 지금 보는 영상 표시
  const first = events[0] || {};
  document.onkeydown = null;
  const _mode0 = clipMode(rel);   // 배포 검증영상처럼 한 카테고리에 항목이 섞이면 폴더로 가른다
  const _editing = _mode0 !== "none";               // 데이터 확인은 늘 라벨 편집(SAM2 · 손라벨). 영상 보기 · 예측 박스 고르기는 없앴다(10-02 사용자)
  if (_editing) {
    await openFrameAt(clip, null, _mode0);   // 시작 프레임은 openFrameAt 이 고른다(자동라벨 첫 검출 → 정답 시각 → 0). 기다려야 새로고침 복원이 두 번 열지 않는다
    if (_my !== _SRV_SEQ || CUR.mode !== "data") return;
  } else {
    ED = null;   // 영상 볼 땐 에디터 재사용상태 초기화(다음 라벨편집이 새로 그리게)
    // 재생 화면이 쓸 갈래. 라벨 모드를 "편집 안 함"으로 둔 경우는 이름으로 짐작한다
    const _kind0 = (_mode0 === "fire" || _mode0 === "person") ? _mode0 : catModeAuto(catOf(rel));
    renderCenter({ video: rel, name: rel.split("/").pop(), signal_type: "raw", signal: [], zone: [], tracks: null, kind: _kind0,
                   weather: [], tod: null, gt: (first.start != null ? first.start : null), gt_dur: first.dur || 0, sa: null });
  }
  const b = modeBox();
  if (_mode0 !== "none") {
    const mr = markRadioRow(stemOf(clip)); b.appendChild(mr);   // 이 클립을 무엇으로 채웠나(기본/전파/손) · 고르면 바로 저장
    zoneOf(clip).then(z => { if (z.length && mr.isConnected) { mr.appendChild(zoneToggle()); if (ED && ED.clip === clip && ED.redraw) ED.redraw(); } });   // KISA 영역 파일이 있으면 '영역' 체크(연기 미완 오른쪽)
  }
  b.appendChild(catModeRow(rel, () => showRawVideo(rel)));          // 이 데이터셋을 무엇으로 라벨할지
}
function renderDatasetList() {
  const box = $("#list"); box.innerHTML = "";
  const d = DS_CUR;
  const shown = d.total > d.shown ? `표시 ${d.shown} / ${d.total.toLocaleString()}장` : `${d.total.toLocaleString()}장`;
  // 필터 대신 라벨만 보기 토글
  const bar = el("div"); bar.style.cssText = "padding:6px 3px;display:flex;gap:6px";
  const tog = el("button", DS_ONLY_LABELED ? "on" : "", "라벨 있는 것만");
  tog.style.cssText = "flex:1;background:var(--panel);color:" + (DS_ONLY_LABELED ? "var(--tx)" : "var(--mut)") + ";border:1px solid " + (DS_ONLY_LABELED ? "var(--blue)" : "var(--line)") + ";border-radius:var(--r);padding:5px;cursor:pointer;font-size:var(--fs-xs)";
  tog.onclick = () => { DS_ONLY_LABELED = !DS_ONLY_LABELED; renderDatasetList(); };
  bar.appendChild(tog); box.appendChild(bar);
  // 좌측은 이미지가 많아 격자 썸네일로
  const grid = el("div"); grid.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:4px";
  let imgs = d.images; if (DS_ONLY_LABELED) imgs = imgs.filter(x => x.labeled);
  imgs.slice(0, 300).forEach(im => {
    const tw = el("div"); tw.style.cssText = "position:relative;cursor:pointer;border-radius:var(--r-sm);overflow:hidden;border:1px solid var(--line);aspect-ratio:16/10;background:#000";
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
  img.style.cssText = "display:block;max-width:100%;max-height:calc(100vh - 150px);width:auto;height:auto;border-radius:var(--r-lg)";
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
    const pre = el("div"); pre.style.cssText = "font-family:ui-monospace,monospace;font-size:var(--fs-xs);color:var(--mut);white-space:pre-wrap;word-break:break-all";
    pre.textContent = boxes.map(b => b.map((x, i) => i ? x.toFixed(4) : d.classes[x] || x).join(" ")).join("\n");
    r.appendChild(pre);
  }
}

// ---------- 서버와 라벨 맞추기 (라벨 작업대 = 보내는 쪽에서만 보인다) ----------
// 양쪽으로 합친다. 겹치는 값은 이 장비가 이긴다.
// 먼저 미리보기(합치지 않고 무엇이 오갈지만)를 보여주고, 한 번 더 누르면 실제로 합친다.
async function initPushButton() {
  let info = {};
  try { info = await (await fetch("/api/pushinfo")).json(); } catch (e) { return; }
  if (!info.enabled) return;                       // 서버 쪽에서는 아예 안 만든다
  const box = document.querySelector(".srcbox");
  if (!box) return;
  const row = document.getElementById("dsKind");     // 새로고침(↻) 이 있는 줄
  const CSS_ROW = "flex:1 1 auto;padding:6px 9px;font-size:var(--fs-xs);font-weight:700;border-radius:var(--r);" +
                  "background:var(--panel);color:var(--tx);border:1px solid var(--line);cursor:pointer";
  const CSS_BOX = "width:100%;margin-top:8px;padding:7px 9px;font-size:var(--fs-sm);font-weight:700;border-radius:var(--r);" +
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
    note.style.cssText = "margin-top:4px;font-size:var(--fs-xs);color:var(--mut);white-space:pre-wrap;line-height:1.5";
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
