// dash_v2/js/train.js: 3단계 '모델 학습' 탭(2026-10-02 사용자 확정 시안 P3-A). 옛 '영상 검수' · '결과' 탭을 한 탭으로. main.js 앞에 로드, main.js · review.js 함수를 실행 시점에 부른다
//   왼쪽 = 고정 플레이어(<video> 하나): 항목 · 고른 모델(최대 3, 모델 색) · 영상(박스를 모델 색으로 겹침) · 재생바 · 영상 목록(모델별 판정)
//   오른쪽 = 단계 탭(이름표 = /api/result_blocks phases, 1 ~ 4단계만) · 단계별 비교 묶음(조건은 접힘) · 3규칙 · 판정기 기술
//   best · last 단추 = 그 모델 저장값(review_summary · review_clip)을 플레이어에 올리고 바로 재생(추론 없음)
//   줄마다 같은 값(모델 · 단계 배지, 채점 완료, 항목 이름, 학습 종료)은 그 줄만 다를 때만. API 에 없는 지표는 '아직 없음' 한 번
//   리더보드 · 큐 없음(큐는 히스토리 맨 위 띠, history.js hqDraw)
const P3 = { item: null, sel: { fire: [], person: [], fall: [] }, auto: {}, clip: {}, flt: "all", seq: 0,
  req: new Map(), got: new Map(), v: null, rate: 1, D: null, q: null, fallKey: null, go: false };
const P3ST = { on: false, t0: 0, w0: 0, timer: 0, ours: false };   // 초당 6장 재생(review.js renderCenter 와 같은 방식)
const P3FAM = { fire: "fire", intrusion: "person", loiter: "person", fall: "fall" };   // 사람 모델은 침입 · 배회 둘 다 본다
const P3IT = { 침입: "intrusion", 배회: "loiter", 방화: "fire", 쓰러짐: "fall" };
const P3COL = ["#58a6ff", "#ff9b50", "#f778ba"], P3MAX = 3;
const p3Sel = () => P3.sel[P3FAM[P3.item]] || [];
const p3Row = () => ((META.items[P3.item] || {}).rows || []).find(r => r.name === P3.clip[P3.item]) || null;
const p3Stages = D => Object.keys(D.phases || {}).filter(k => k !== "grid0");   // 1 ~ 4단계만(10-02 사용자: 0단계 · 전체 · 단계 없음 탭 지움)
const p3PhOf = r => r.phase || "_none";
const p3Ph = (D, ph) => (D.phases || {})[ph] ? `<span class="nr-bdg ph" title="${nrEsc(D.phases[ph])}">${nrEsc(String(D.phases[ph]).split("(")[0])}</span>` : "";   // 줄 안 단계 배지 = 짧은 이름
const p3Chip = (v, r) => v ? `<span class="nr-chip ${v.call === "동률" ? "tie" : v.call === "개선" ? "win" : "lose"}">${v.call}</span>`
  : `<span class="nr-chip wait">${r.status === "train" ? "학습 중" : r.status === "queue" ? "대기" : "채점 대기"}</span>`;
const p3Obj = it => it === "방화" ? "최대 F1-Score (IoU 0.5 기준) · mAP50" : "최대 F1-Score (IoU 0.5~0.95 기준) · mAP50-95";

// ---------- 읽기(옛 결과 탭 buildResults 와 같은 값) ----------
async function trBuild() {
  const c = $("#center"), y = c.scrollTop;
  if (!c.querySelector(".p3")) c.innerHTML = '<div class="empty">불러오는 중…</div>';
  let D, q = { running: [], jobs: [], log: [] };
  try { D = await (await fetch("/api/result_blocks")).json(); } catch (e) { D = { error: "결과를 못 읽었습니다" }; }
  try { q = await (await fetch("/api/queue")).json(); } catch (e) {}
  if (CUR.mode !== "train") return;
  if (D.error) { c.innerHTML = `<div class="empty">${nrEsc(D.error)}</div>`; return; }
  p3Draw(D, q);
  c.scrollTop = y;
  clearTimeout(window._resT);                     // 학습 중 · 채점 대기 실험이 있으면 1분마다 다시 읽는다(표만, 플레이어 · 스크롤 유지)
  if (Object.values(D.runs).some(r => r.status === "train" || r.status === "scoring")) window._resT = setTimeout(() => { if (CUR.mode === "train") trBuild(); }, 60000);
}

// ---------- 오른쪽: 단계 · 표 ----------
function p3Draw(D, q) {
  const c = $("#center");
  P3.D = D; P3.q = q;
  let main = c.querySelector(".p3-main");
  const first = !main;
  if (first) {                                               // 1분마다 다시 그려도 플레이어는 그대로 둔다(표 쪽만 다시)
    c.innerHTML = '<div class="nr p3"><aside class="p3-pl" id="p3Pl" aria-label="플레이어"></aside><div class="p3-main"></div></div>';
    main = c.querySelector(".p3-main");
    main.onclick = p3MainClick;
    c.querySelector("#p3Pl").onclick = p3PlClick;
    main.addEventListener("toggle", e => p3Ovf(e.target), true);
  }
  if (!p3Stages(D).includes(NR_PH)) NR_PH = p3Stages(D)[0] || "";   // 고른 단계가 없으면(전체 · 0단계 · 단계 없음이던 것) 1단계
  const ks = NR_PH ? [NR_PH] : [];
  main.innerHTML = '<i class="p3-anc"></i>' + p3Tabs(D) + ks.map(k => p3Sec(D, q, k)).join("") + nrOthers(D, q) + nrTerms(D.terms || []);
  const o = main.querySelector('.nr-block[data-id="_others"] .nr-tbl table');   // 비교 묶음에 없는 실험(지금 결과 탭 표 그대로)에도 재생 칸
  if (o) { const ids = D.others.filter(x => gfMeta(D.runs[x].item) && nrPhOk(D.runs[x])); [...o.rows].forEach((tr, i) => tr.prepend(el(i ? "td" : "th", "p3-pc", i ? p3Btns(ids[i - 1]) : ""))); }
  nrBindToggles(main); p3Ovf(main);
  const pop = $("#nrTermsPop"), tb = main.querySelector(".nr-tbtn");
  if (pop) pop.addEventListener("beforetoggle", e => {
    if (e.newState !== "open") return;
    const r = tb.getBoundingClientRect(); pop.style.top = r.bottom + 8 + "px"; pop.style.right = Math.max(8, innerWidth - r.right) + "px";
  });
  if (first) { p3PickItem(); p3Load(); } else p3Sync();
}
function p3MainClick(e) {
  const b = e.target.closest("[data-p3k]");
  if (b) return p3Add(b.dataset.p3k, b.dataset.p3i);
  const t = e.target.closest("[data-tab]");
  if (!t) return;
  NR_PH = t.dataset.tab; try { localStorage.setItem("nr_ph", NR_PH); } catch (x) {}
  p3Draw(P3.D, P3.q);
  const c = $("#center"), a = c.querySelector(".p3-anc"), y = a.getBoundingClientRect().top - c.getBoundingClientRect().top + c.scrollTop;
  if (c.scrollTop > y) c.scrollTop = y;                      // 내려가 있었으면 단계 탭 바로 아래부터
}
function p3Blocks(D, k) { return D.blocks.filter(b => gfMeta(b.item) && b.members.some(x => p3PhOf(D.runs[x]) === k)); }   // 단계 = 견주는 실험 기준(결과 탭과 같음)
function p3Tried(D, k) {                                    // 판정기 기술(result_blocks.yaml judge.tried) 중 이 단계
  return (D.score || []).filter(s => gfMeta(s.item)).flatMap(s => ((s.judge || {}).tried || []).filter(t => (t.phase || "_none") === k).map(t => ({ s, t })));
}
function p3R3(D) { return Object.values(D.runs).filter(r => r.rule3 && gfMeta(r.item)); }
function p3Count(D, k) { return p3Blocks(D, k).length + p3Tried(D, k).length + (k === "grid3" && p3R3(D).length ? 1 : 0); }
function p3Tabs(D) {
  const tabs = p3Stages(D).map(k => [k, String(D.phases[k]).split("(")[0], p3Count(D, k)]);
  const n = (D.terms || []).length;
  return `<div class="p3-bar"><div class="dt-tabs" role="tablist">` + tabs.map(([k, l, c]) =>
    `<button type="button" role="tab" data-tab="${k}" class="${k === NR_PH ? "on" : ""}${c === 0 ? " p3-0" : ""}" title="${nrEsc(k && k !== "_none" ? D.phases[k] : l)}">${nrEsc(l)}${c != null ? `<small>${c}</small>` : ""}</button>`).join("") +
    `</div>${n ? `<button type="button" class="nr-tbtn" popovertarget="nrTermsPop">용어 정리 <span class="nr-mut">${n}개</span></button>` : ""}</div>`;
}
function p3Sec(D, q, k) {                                    // 단계 한 칸: 전체 이름표 · 단계 최고(KISA F1, 눌러 재생) · 비교 묶음 · 3규칙 · 판정기 기술(모두 접는 칸)
  const bl = p3Blocks(D, k), tr = p3Tried(D, k), r3 = k === "grid3" ? p3R3(D) : [], best = {};
  Object.values(D.runs).forEach(r => {
    if (r.status !== "done" || !gfMeta(r.item) || p3PhOf(r) !== k) return;
    r.items.forEach(it => Object.entries(r.scores[it] || {}).forEach(([ck, s]) => { if (!best[it] || s.f1 > best[it].f1) best[it] = { f1: s.f1, exp: r.exp, ck }; }));
  });
  const bests = Object.entries(best).map(([it, b]) => `<button type="button" class="p3-bc" data-p3k="${nrEsc(b.exp)}|${b.ck}" data-p3i="${it === "loitering" ? "loiter" : it}" title="${nrEsc(b.exp)} · ${b.ck}">${NR_KO[it]} <b>${b.f1.toFixed(2)}</b></button>`).join("");
  const body = bl.map(b => p3Block(b, D, q, k)).join("") + (r3.length ? p3R3Html(D, r3, k) : "") + (tr.length ? p3TriedHtml(tr) : "");
  return `<section class="p3-sec"><div class="p3-sh"><h3>${nrEsc(k === "_none" ? "단계 없음" : D.phases[k] || k)}</h3>` +
    (bests ? `<div class="p3-sb"><span class="p3-k">KISA 시나리오 F1 최고</span>${bests}</div>` : "") +
    `</div>${body || '<div class="p3-empty">이 단계 시도 없음</div>'}</section>`;
}
function p3Btns(exp) {                                       // 실험 줄의 재생 단추(끝난 판만). 사람 판은 침입 · 배회 중 지금 보는 쪽으로
  const r = P3.D.runs[exp];
  if (!r || r.status !== "done") return "";
  const fam = r.item === "방화" ? "fire" : "person";
  return `<div class="p3-cks">${["best", "last"].map(ck => `<button type="button" class="p3-ck" data-p3k="${nrEsc(exp)}|${ck}" data-p3i="${fam}">${ck}</button>`).join("")}</div>`;
}
function p3F1(r, it) {                                       // best / last, 굵게 = 비교값(낮은 쪽). 끝나지 않은 판은 빈칸(판정 칸에 대기 · 학습 중)
  if (r.status !== "done") return "";
  const s = r.scores[it] || {}, f = ck => s[ck] ? `<span class="${ck === r.lo[it] ? "nr-lo" : "nr-hi"}" title="${ck} · 정검 ${s[ck].tp} / 미검 ${s[ck].fn} / 오검 ${s[ck].fp}">${s[ck].f1.toFixed(2)}</span>` : "-";
  return `${f("best")} / ${f("last")}`;
}
function p3Exp(D, r, k, extra) {                             // 실험 이름 칸: 긴 이름은 줄임(전체 · 학습 종료는 마우스). 모델 · 단계 배지는 그 줄만 다를 때
  const m = String(r.args.model || "").replace(/\.pt$/, "").replace(/^yolo/i, "YOLO");
  const bd = (extra.model ? `<span class="nr-bdg">${nrEsc(m)}</span>` : "") + (p3PhOf(r) !== k ? p3Ph(D, r.phase) : "");
  return `<td class="nr-exp"><span class="p3-ell" title="${nrEsc(r.exp)}${r.ended ? ` · 학습 종료 ${nrEsc(r.ended.slice(5, 16))}` : ""}">${nrEsc(r.exp)}</span>${extra.role || ""}` +
    (bd ? `<div>${bd}</div>` : "") + (r.new ? "" : '<div class="nr-warn">새 데이터 실험 아님</div>') + "</td>";
}
const P3COLS = ["imgsz", "batch", "epochs"];                  // 열로 따로 보이는 학습 설정(10-02 사용자: 해상도 · 배치 · 에폭 = 열 이름)
const P3COLONLY = /^\s*(해상도|배치|epoch|에폭)\s*\d+(\s*[,·]\s*(해상도|배치|epoch|에폭)\s*\d+)*\s*$/i;   // 조건 글이 이 열들뿐이면 조건 칸은 비움
function p3Chg(b, r) {                                       // 조건 칸(nrChanged 와 같은 값): 데이터 모듈 이름은 조건 이름표에 마우스(이름표가 같은 뜻), 총 장수는 그대로
  const lab0 = b.labels[r.exp] || "", lab = P3COLONLY.test(lab0) ? "" : lab0, sub = [], tip = [];
  b.diffs.filter(d => d.declared && !P3COLS.includes(d.key)).forEach(d => {
    const v = d.values[r.exp];
    if (d.key === "data") { tip.push(...(v.length ? v : ["추가 데이터 없음"])); if (r.n_train) sub.push(`총 ${r.n_train.toLocaleString()}장`); }
    else if (!lab.includes(nrFmt(v))) sub.push(`${d.label} ${nrEsc(nrFmt(v))}`);
  });
  return (lab ? `<b${tip.length ? ` class="p3-tip" title="${nrEsc(tip.join(" · "))}"` : ""}>${nrEsc(lab)}</b>` : "") + (sub.length ? `<div class="nr-sub">${sub.join("<br>")}</div>` : "");
}
function p3Cols(r) {                                         // 해상도 · 배치 · 에폭 칸(학습 설정 원본 값). 에폭: 학습 중 · 덜 돈 판 = 돈 / 정한
  const a = r.args && typeof r.args === "object" ? r.args : {}, ep = a.epochs, run = r.epochs_run, v = x => x == null ? "-" : nrEsc(String(x));
  const e = ep == null && run == null ? "-" : r.status === "train" || (run != null && ep != null && run !== ep) ? `${run == null ? 0 : run} / ${ep}` : v(ep != null ? ep : run);
  return `<td class="nr-num">${v(a.imgsz)}</td><td class="nr-num">${v(a.batch)}</td><td class="nr-num">${e}</td>`;
}
function p3Block(b, D, q, k) {                               // 비교 묶음(결과 탭 nrBlock 과 같은 값, 줄마다 반복되던 것을 걷어낸 표)
  const ids = [b.control, ...b.members], its = D.runs[b.control].items, kc = (D.key_clips || {})[b.item];
  const oneModel = b.same.train.some(([x]) => x === "model");
  const ko = it => its.length > 1 ? NR_KO[it] + " " : "";
  const chg = Object.fromEntries(ids.map(x => [x, p3Chg(b, D.runs[x])])), hasChg = ids.some(x => chg[x]);   // 조건 글이 열(해상도 · 배치 · 에폭)뿐인 묶음은 조건 칸을 통째로 뺀다
  const head = `<tr><th class="p3-pc"></th><th>실험</th>${hasChg ? "<th>조건</th>" : ""}<th>해상도</th><th>배치</th><th>에폭</th>` +
    its.map((it, i) => `<th>${ko(it)}F1<br>${nrMut(i ? "best / last" : "best / last · 굵게 = 비교값")}</th>`).join("") +
    (kc ? "<th>변별 편</th>" : "") + `<th>기준 대비 정검${its.length > 1 ? "<br>" + nrMut(its.map(it => NR_KO[it]).join(" / ")) : ""}</th><th>판정</th></tr>`;
  const rows = ids.map((x, i) => {
    const r = D.runs[x], v = b.verdicts[x];
    const st = r.status === "train" ? `<div class="p3-pg">${nrStatus(r, q)}<div>${nrEnded(r, q)}</div></div>` : !i && r.status !== "done" ? nrStatus(r, q) : "";
    return `<tr class="${i ? "" : "ctl"}"><td class="p3-pc">${p3Btns(x)}</td>${p3Exp(D, r, k, { model: !oneModel, role: i ? "" : '<span class="nr-role">기준 실험</span>' })}` +
      (hasChg ? `<td class="nr-chg">${chg[x]}</td>` : "") + p3Cols(r) + its.map(it => `<td class="nr-num">${p3F1(r, it)}</td>`).join("") +
      (kc ? `<td>${r.status === "done" ? nrKeys(r, kc) : ""}</td>` : "") +
      `<td class="nr-num">${i && v ? its.map(it => (v.delta[it] > 0 ? "+" : "") + v.delta[it]).join(" / ") : ""}</td>` +
      `<td>${i ? p3Chip(v, r) : ""}${st}</td></tr>`;
  }).join("");
  const iv = nrArr(b.iv), warn = b.diffs.filter(d => !d.declared && !d.harmless).length, concl = nrArr(b.conclusion);
  const obj = k === "grid1" ? `<span class="p3-na" title="${p3Obj(b.item)}">객체 인식 지표 아직 없음</span>` : "";   // 1단계 지표(API 에 없음): 열 대신 묶음 머리에 한 번
  const cond = `<details class="p3-cond" data-id="_c_${nrEsc(b.id)}"${nrOpen.has("_c_" + b.id) ? " open" : ""}><summary><span class="p3-k">조건</span>` +
    `<span class="p3-cs">${iv.map(x => `<span class="p3-tag">${nrEsc(x)}</span>`).join("")}${warn ? `<span class="tag warn">교란 변수 ${warn}</span>` : ""}</span></summary>${nrCond(b, D)}</details>`;
  return `<details class="nr-block" data-id="${nrEsc(b.id)}"${nrOpen.has(b.id) ? " open" : ""}><summary class="nr-bt">${nrEsc(b.date ? `[${b.date}] ` : "")}${nrEsc(b.title)}` +
    `<span class="nr-sum">${b.phase && b.phase !== k ? p3Ph(D, b.phase) : ""}${b.members.map(x => p3Chip(b.verdicts[x], D.runs[x])).join("")}</span></summary><div class="nr-body">` +
    (b.question || obj ? `<div class="p3-bh">${b.question ? `<p class="nr-q"><b>목적:</b> ${nrEsc(b.question)}</p>` : ""}${obj}</div>` : "") + cond +
    `<div class="nr-tbl"><table>${head}${rows}</table></div>` + (concl.length ? `<div class="nr-note"><b>결론</b>${nrList(concl.map(nrEsc))}</div>` : "") + "</div></details>";
}
function p3R3Html(D, rs, k) {                                // 3단계: 같은 모델을 G · B · T 규칙으로 잰 채점편 F1(rule3.json). 항목 · 규칙 = 머리 한 번, 칸 = best / last
  const R = D.rule3 || {}, RULE = { intrusion: ["G", "B", "T", "B+S"], loitering: ["G", "B", "T"], fire: ["B", "T"] };
  const f1 = s => !s ? "-" : (s[0] ? (200 * s[0] / (2 * s[0] + s[1] + s[2])).toFixed(1) : "0.0");   // main.js nrRule3 와 같은 계산
  const cell = (r, it, f) => ["best", "last"].map(ck => { const x = ((r.rule3[ck] || {})[it] || {})[f];
    return `<span title="${ck} · ${x ? `정검 ${x[0]} / 미검 ${x[1]} / 오검 ${x[2]}` : it === "fire" && f === "B" ? "헛불 38편 헛경보 0 인 규칙 없음" : "없음"}">${f1(x)}</span>`; }).join(" / ");
  const grp = [["사람", ["intrusion", "loitering"]], ["방화", ["fire"]]].map(([nm, its]) => [nm, its, rs.filter(r => r.items.join() === its.join())]).filter(g => g[2].length);
  const oneModel = new Set(rs.map(r => r.args.model)).size === 1;
  const html = grp.map(([nm, its, rr]) => (grp.length > 1 ? `<div class="p3-gt">${nm}</div>` : "") +
    `<div class="nr-tbl"><table><tr><th class="p3-pc" rowspan="2"></th><th rowspan="2">실험</th>${its.map(it => `<th class="p3-gh" colspan="${1 + RULE[it].length}">${NR_KO[it]}</th>`).join("")}</tr>` +
    `<tr>${its.map(it => `<th>F1</th>${RULE[it].map(f => `<th>${f}</th>`).join("")}`).join("")}</tr>` +
    rr.map(r => `<tr><td class="p3-pc">${p3Btns(r.exp)}</td>${p3Exp(D, r, k, { model: !oneModel })}` +
      its.map(it => `<td class="nr-num">${p3F1(r, it)}</td>` + RULE[it].map(f => `<td class="nr-num p3-r3">${cell(r, it, f)}</td>`).join("")).join("") + "</tr>").join("") +
    "</table></div>").join("");
  return `<details class="nr-block" data-id="_p3r3"${nrOpen.has("_p3r3") ? " open" : ""}><summary class="nr-bt">3규칙 F1 (G · B · T)<span class="nr-sum"><span class="nr-bdg">${rs.length}개 실험</span>` +
    `<span class="nr-bdg">칸 = best / last</span>${R.rate ? `<span class="nr-bdg">${nrEsc(R.rate)}</span>` : ""}${R.made ? `<span class="nr-bdg">계산 ${nrEsc(R.made)}</span>` : ""}</span></summary>` +
    `<div class="nr-body">${html}</div></details>`;
}
function p3TriedHtml(tr) {                                   // 판정기 기술: 항목마다 기준 모델 한 줄(이름 · F1) 아래 기술들. 내용은 기술 이름에 마우스
  const DC = { 채택: "ok", 기각: "no", 보류: "hold" }, pill = (d, n) => `<span class="nr-dec nr-dec-${DC[d] || "wait"}">${nrEsc(d || "")}${n != null ? " " + n : ""}</span>`;
  const here = t => !t.variant ? "" : !t.here ? nrMut("계산 전") : `<b>${t.here["점수"].toFixed(2)}</b><div class="nr-mut">정검 ${t.here["정검"]} · 미검 ${t.here["미검"]} · 오검 ${t.here["오검"]}</div>`;
  const ss = [...new Set(tr.map(x => x.s))];
  const rows = ss.map(s => `<tr class="p3-grp"><td colspan="6"><b>${nrEsc(s.item)}</b> <span class="nr-mut">기준 모델</span> <span class="nr-exp p3-ell" title="${nrEsc(s.exp ? `${s.exp} · ${s.ck}` : s.model || "")}">${nrEsc(s.exp ? `${s.exp} · ${s.ck}` : s.model || "")}</span>` +
      (s.f1 != null ? ` <span class="nr-mut">F1</span> <b>${s.f1.toFixed(2)}</b>` : "") + "</td></tr>" +
    tr.filter(x => x.s === s).map(({ t }) => {
      const key = t.variant && t.here && s.exp ? `${s.exp}|${s.ck}+${t.variant}` : "";
      return `<tr><td class="p3-pc">${key ? `<button type="button" class="p3-ck" data-p3k="${nrEsc(key)}" data-p3i="${P3IT[s.item]}">재생</button>` : ""}</td>` +
        `<td><b${t.what ? ` class="p3-tip" title="${nrEsc(t.what)}"` : ""}>${nrEsc(t.name)}</b></td><td>${pill(t.dec)}</td><td>${nrEsc(t.result || "")}</td><td>${nrEsc(t.why || "")}</td><td class="nr-num">${here(t)}</td></tr>`;
    }).join("")).join("");
  const decs = [...new Set(tr.map(x => x.t.dec))].map(d => pill(d, tr.filter(x => x.t.dec === d).length)).join("");
  const k = (tr[0].t.phase || "_none");
  return `<details class="nr-block" data-id="_p3tr_${nrEsc(k)}"${nrOpen.has("_p3tr_" + k) ? " open" : ""}><summary class="nr-bt">판정기 기술<span class="nr-sum"><span class="nr-bdg">${tr.length}개</span>${decs}</span></summary>` +
    `<div class="nr-body"><div class="nr-tbl"><table><tr><th class="p3-pc"></th><th>기술</th><th>판정</th><th>결과</th><th>이유</th><th>기준 모델에 적용<br>${nrMut("채점편, 측정만")}</th></tr>${rows}</table></div></div></details>`;
}
function p3Ovf(root) {                                       // 칸 안에서 가로로 넘치는 표 · 탭 줄 = 오른쪽 끝 흐림(끝까지 밀면 사라짐)
  if (!root || !root.querySelectorAll) return;
  root.querySelectorAll(".nr-tbl, .p3-bar .dt-tabs").forEach(t => {
    const f = () => t.classList.toggle("p3-ovf", t.scrollLeft + t.clientWidth < t.scrollWidth - 2);
    f(); t.onscroll = f;
  });
}
function p3Sync() {                                          // 표 단추 = 지금 플레이어에 올라간 모델이면 그 모델 색(모델 이름은 플레이어 위 한 줄에만)
  const fam = P3FAM[P3.item], sel = p3Sel();
  document.querySelectorAll(".p3-main [data-p3k]").forEach(b => {
    const m = (b.dataset.p3i === "person" ? "person" : P3FAM[b.dataset.p3i]) === fam && sel.find(x => x.key === b.dataset.p3k);
    b.classList.toggle("on", !!m);
    if (m) b.style.setProperty("--c", m.col); else b.style.removeProperty("--c");
  });
}

// ---------- 왼쪽: 고정 플레이어 ----------
function p3PickItem() {
  const ok = GF === "all" ? REVIEW_ITEMS : gf().review;
  if (!P3.item) try { P3.item = localStorage.getItem("p3_item"); } catch (e) {}
  if (!ok.includes(P3.item)) P3.item = ok[0];
}
async function p3FallKey() {                                 // 쓰러짐 = 배포 모델 하나. 키는 검수 목록에서(점수 카드에는 없다)
  if (!P3.fallKey) try { P3.fallKey = (((await (await fetch("/api/review_models?item=fall")).json()).models || [])[0] || {}).key || null; } catch (e) {}
  return P3.fallKey;
}
async function p3Add(key, it) {
  if (it === "person") it = P3FAM[P3.item] === "person" ? P3.item : "intrusion";
  if (P3.item !== it) { p3Stop(); P3.item = it; try { localStorage.setItem("p3_item", it); } catch (e) {} }
  P3.auto[P3FAM[it]] = true;
  const s = p3Sel(), i = s.findIndex(m => m.key === key);
  if (i >= 0) s.splice(i, 1);                               // 다시 누르면 뺀다
  else { if (s.length >= P3MAX) s.shift(); s.push({ key, col: P3COL.find(c => !s.some(m => m.col === c)) }); P3.go = true; }
  p3Load();
}
async function p3Default() {                                 // 처음 열면 그 항목 공식 채점 최고 모델 하나(결과 탭 점수 카드와 같은 모델)
  const fam = P3FAM[P3.item];
  if (P3.auto[fam] || !P3.D) return;
  P3.auto[fam] = true;
  if (P3.sel[fam].length) return;
  const s = (P3.D.score || []).find(x => P3IT[x.item] === P3.item);
  const key = s && s.exp ? `${s.exp}|${s.ck}` : P3.item === "fall" ? await p3FallKey() : null;
  if (key && !P3.sel[fam].length) P3.sel[fam].push({ key, col: P3COL[0] });
}
function p3Get(k, url) {                                     // 저장값 읽기(같은 것은 한 번만). 80건 넘으면 오래된 것부터 버린다
  if (!P3.req.has(k)) {
    P3.req.set(k, fetch(url).then(r => r.ok ? r.json() : null).catch(() => null).then(j => { P3.got.set(k, j); if (!j) P3.req.delete(k); return j; }));
    if (P3.req.size > 80) { const o = P3.req.keys().next().value; P3.req.delete(o); P3.got.delete(o); }
  }
  return P3.req.get(k);
}
const p3SK = m => `s|${m.key}|${P3.item}`, p3CK = m => `c|${m.key}|${P3.item}|${P3.clip[P3.item]}`;
const p3S = m => P3.got.get(p3SK(m)), p3C = m => P3.got.get(p3CK(m));   // undefined = 읽는 중, null = 저장값 없음
async function p3Load() {
  const my = ++P3.seq;
  await p3Default();
  const it = P3.item, rows = (META.items[it] || {}).rows || [];
  if (!rows.some(r => r.name === P3.clip[it])) P3.clip[it] = rows[0] ? rows[0].name : null;
  p3Render();
  const c = P3.clip[it];
  await Promise.all(p3Sel().flatMap(m => [p3Get(p3SK(m), `/api/review_summary?key=${encodeURIComponent(m.key)}&item=${it}`),
    c && p3Get(p3CK(m), `/api/review_clip?key=${encodeURIComponent(m.key)}&item=${it}&clip=${encodeURIComponent(c)}`)]));
  if (my !== P3.seq) return;
  p3Render();
  if (P3.go) { P3.go = false; p3Go(); }
}
function p3Go() {                                            // 표에서 모델을 올리면 바로 재생: 처음 자리(1초 전)면 정답 3초 전부터
  const v = P3.v, go = () => {
    const r0 = p3Sel().map(p3C).find(Boolean), row = p3Row(), gt = r0 && r0.gt != null ? r0.gt : row && row.gt;
    if (v.currentTime < 1 && gt != null) v.currentTime = Math.max(0, gt - 3);
    if (!P3ST.on) p3Play();
  };
  if (v.duration) go(); else v.addEventListener("loadedmetadata", go, { once: true });
}
function p3Video() {                                         // <video> 는 하나만 만들어 다시 그릴 때마다 옮겨 꽂는다
  if (P3.v) return P3.v;
  const v = P3.v = document.createElement("video");
  v.preload = "metadata"; v.muted = true; v.playsInline = true;
  ["loadeddata", "seeked", "timeupdate"].forEach(e => v.addEventListener(e, p3Paint));
  v.addEventListener("seeking", () => { if (P3ST.on && !P3ST.ours) p3Anchor(); });
  v.onerror = () => {
    const e = v.error;
    if (e && e.code === 3 && !v.src.includes("safe=1")) {   // 디코딩 오류 → 시청용 사본(검수 탭과 같음)
      const t = v.currentTime; v.addEventListener("loadedmetadata", () => { v.currentTime = t; }, { once: true });
      v.src = v.src.split("?")[0] + "?safe=1"; return;
    }
    const w = document.querySelector(".p3-view"); if (w) w.dataset.err = "영상을 불러올 수 없습니다" + (e ? ` · 오류 ${e.code}` : "");
  };
  return v;
}
const p3Anchor = () => { P3ST.t0 = P3.v.currentTime; P3ST.w0 = performance.now(); };
function p3Stop() { P3ST.on = false; clearTimeout(P3ST.timer); const b = document.getElementById("p3PP"); if (b) b.textContent = "▶"; }
function p3Tick() {
  const v = P3.v;
  if (!P3ST.on || !document.body.contains(v)) return p3Stop();
  const k = Math.floor((P3ST.t0 + (performance.now() - P3ST.w0) / 1000 * P3.rate) * 6 + 1e-6) / 6;
  if (v.duration && k >= v.duration - 1e-3) return p3Stop();
  const next = () => { P3ST.timer = setTimeout(p3Tick, Math.max(0, P3ST.w0 + (k + 1 / 6 - P3ST.t0) / P3.rate * 1000 - performance.now())); };
  if (Math.abs(v.currentTime - (k + 0.001)) < 1e-4) return next();
  P3ST.ours = true;
  v.addEventListener("seeked", () => { P3ST.ours = false; next(); }, { once: true });
  v.currentTime = k + 0.001;
}
function p3Play() {
  const v = P3.v;
  if (P3ST.on) return p3Stop();
  if (!v || !v.duration) return;
  P3ST.on = true; p3Anchor(); document.getElementById("p3PP").textContent = "❚❚"; p3Tick();
}
function p3PlClick(e) {
  const b = e.target.closest("[data-it],[data-rm],[data-jmp],[data-rate],[data-clip],[data-flt],#p3PP");
  if (!b) return;
  const d = b.dataset, v = P3.v;
  if (b.id === "p3PP") return p3Play();
  if (d.it) { if (d.it !== P3.item) { p3Stop(); P3.item = d.it; try { localStorage.setItem("p3_item", d.it); } catch (x) {} p3Load(); } return; }
  if (d.rm != null) { p3Sel().splice(+d.rm, 1); P3.auto[P3FAM[P3.item]] = true; return p3Load(); }
  if (d.jmp != null) { if (v && v.duration) v.currentTime = Math.max(0, +d.jmp - 3); return; }
  if (d.rate) { if (P3ST.on) p3Anchor(); P3.rate = +d.rate; b.parentNode.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b)); return; }
  if (d.clip) { if (d.clip !== P3.clip[P3.item]) { p3Stop(); P3.clip[P3.item] = d.clip; p3Load(); } return; }
  if (d.flt) { P3.flt = d.flt; p3Render(); }
}
function p3Render() {
  const pl = document.getElementById("p3Pl");
  if (!pl || !META) return;
  const it = P3.item, sel = p3Sel(), row = p3Row(), rows = (META.items[it] || {}).rows || [];
  const ok = GF === "all" ? REVIEW_ITEMS : gf().review;
  const seg = `<div class="dt-seg" role="tablist">${REVIEW_ITEMS.filter(k => ok.includes(k) || k === it).map(k => `<button type="button" data-it="${k}" class="${k === it ? "on" : ""}">${nrEsc(META.items[k].title)}</button>`).join("")}</div>`;
  const ms = sel.map((m, i) => {                             // 고른 모델 = 색 · 이름 · 빼기만(판정 · 점수는 영상 목록 · 표에 있다). 읽는 중 · 저장값 없음 · 공식과 다른 값만 배지
    const [exp, ck] = m.key.split("|"), s = p3S(m);
    const st = s === undefined ? '<span class="nr-chip wait">읽는 중</span>' : !s ? '<span class="nr-chip tie">저장값 없음</span>' :
      s.official && s.score && s.official["점수"] !== s.score["점수"] ? `<span class="tag warn" title="공식 채점 ${s.official["점수"].toFixed(2)} · 목록 판정 · 경보는 이 값 기준">이 화면 ${s.score["점수"].toFixed(2)}</span>` : "";
    return `<span class="p3-m" style="--c:${m.col}"><i></i><span class="p3-mn" title="${nrEsc(exp)} · ${nrEsc(ck)}"><span class="p3-ell">${nrEsc(exp)}</span><small>· ${nrEsc(ck)}</small></span>${st}<button type="button" class="p3-x" data-rm="${i}" aria-label="빼기" title="빼기">×</button></span>`;
  }).join("") || `<span class="p3-m p3-m0"><span class="nr-chip tie">모델 없음</span><span class="nr-mut">오른쪽 표의 best · last · 최대 ${P3MAX}개</span></span>`;
  const r0 = sel.map(p3C).find(Boolean), gt = r0 && r0.gt != null ? r0.gt : row ? row.gt : null;
  const al = sel.map(m => { const rv = p3C(m); return rv && rv.alarm != null ? `<button type="button" class="jmp p3-aj" style="--c:${m.col}" data-jmp="${rv.alarm}" title="${nrEsc(m.key.replace("|", " · "))}"><i></i>${fmt(rv.alarm)}</button>` : ""; }).join("");
  const ctrl = `<div class="ctrl"><button type="button" id="p3PP" aria-label="재생">${P3ST.on ? "❚❚" : "▶"}</button><span class="now p3-now">0:00</span>` +
    (gt != null ? `<button type="button" class="jmp gt" data-jmp="${gt}">GT ${fmt(gt)}</button>` : "") + (al ? `<span class="p3-k">예측</span>${al}` : "") +
    `<span class="p3-grow"></span><div class="rate">${[1, 2, 4, 8].map(x => `<button type="button" data-rate="${x}" class="${x === P3.rate ? "on" : ""}">${x}x</button>`).join("")}</div></div>`;
  const ths = [...new Set(sel.map(p3C).filter(r => r && r.conf != null).map(r => r.conf))];
  const sw = sel.length ? `linear-gradient(90deg,${sel.map(m => m.col).join(",")})` : "var(--tx2)";
  const tl = `<div class="tl"><div class="tlbar"></div><div class="leg"><span><i style="background:#3fb95055"></i>정답 유효창(-2~+10초)</span>` +
    `<span><i style="background:${sw}"></i>${it === "fire" ? "불 최고 확신도 · 옅은 선 = 연기" : it === "fall" ? "쓰러짐 판정 확률(사람별 최고)" : "구역 안 사람 최고 확신도"}</span>` +
    (ths.length ? `<span><i class="p3-th"></i>규칙 문턱 ${ths.join(" · ")}</span>` : "") + `<span><i class="p3-dash"></i>예측 경보</span><span>초당 6장</span></div></div>`;
  const vs = n => sel.map(m => { const s = p3S(m), c = s && s.clips && s.clips[n]; return c ? c.verdict : null; });
  const diff = rows.filter(r => new Set(vs(r.name).filter(Boolean)).size > 1);
  const shown = sel.length > 1 && P3.flt === "diff" ? diff : rows;
  const head = `<div class="p3-lh"><span class="nr-mut">${rows.length}편</span><span class="p3-grow"></span>` +
    (sel.length > 1 ? `<div class="dt-seg">${[["all", "전체"], ["diff", `판정 다름 ${diff.length}`]].map(([k, l]) => `<button type="button" data-flt="${k}" class="${P3.flt === k ? "on" : ""}">${l}</button>`).join("")}</div>` : "") + "</div>";
  const list = shown.map(r => `<div class="item${row && r.name === row.name ? " on" : ""}" data-clip="${nrEsc(r.name)}"><span class="nm">${nrEsc(r.name)}</span>` +
    `<div class="p3-vs">${vs(r.name).map((v, i) => `<span class="p3-v ${v ? vClass(v) : ""}" style="--c:${sel[i].col}" title="${nrEsc(sel[i].key)}${v ? " · " + v : ""}">${v ? nrEsc(v[0]) : "-"}</span>`).join("")}</div></div>`).join("") ||
    '<div class="empty">판정이 갈린 편 없음</div>';
  const ls = (pl.querySelector(".p3-cl") || {}).scrollTop || 0;
  pl.innerHTML = seg + `<div class="p3-ms">${ms}</div><div class="p3-view"><div class="zoneov"></div></div>` + ctrl + tl + head + `<div class="p3-clw"><div class="p3-cl">${list}</div></div>`;
  pl.querySelector(".p3-cl").scrollTop = ls;
  const v = p3Video();
  pl.querySelector(".p3-view").prepend(v);
  const src = row ? "/vid/" + row.video.replace(/\\/g, "/").split("/").map(encodeURIComponent).join("/") : "";
  if (v.dataset.src !== src) { p3Stop(); v.dataset.src = src; if (src) v.src = src; else v.removeAttribute("src"); }
  pl.querySelector(".tlbar").onclick = e => { const r = e.currentTarget.getBoundingClientRect(); if (v.duration) v.currentTime = (e.clientX - r.left) / r.width * p3Total(); };
  p3Paint(); p3Sync();
}
function p3Total() {
  const e = p3Sel().map(p3C).filter(r => r && r.signal && r.signal.length).map(r => r.signal[r.signal.length - 1][0]);
  return (P3.v && P3.v.duration) || Math.max(0, ...e) || 300;
}
function p3Paint() {                                         // 시각이 바뀔 때마다: 박스 · 재생바
  const v = P3.v, pl = document.getElementById("p3Pl");
  if (!v || !pl || !pl.contains(v)) return;
  const t = v.currentTime, row = p3Row(), now = pl.querySelector(".p3-now");
  if (now) now.textContent = fmt(t);
  if (!row) return;
  const ov = pl.querySelector(".p3-view .zoneov"); if (ov) ov.innerHTML = p3Boxes(row, t);
  const bar = pl.querySelector(".tlbar"); if (bar) bar.innerHTML = p3BarSvg(row, t);
}
function p3Boxes(row, t) {                                   // 겹침: 모델 색 = 박스 색, 문턱 밑은 점선. 같은 물체 글자는 모델마다 한 줄씩 위로. 글자 · 선은 화면 폭에 맞춰 키움
  const sel = p3Sel(), rvs = sel.map(p3C), r0 = rvs.find(Boolean);
  const W = (r0 && r0.wh ? r0.wh[0] : row.framew) || 1280, H = (r0 && r0.wh ? r0.wh[1] : row.frameh) || 720, zone = (r0 && r0.zone) || row.zone;
  const fs = Math.round(W / 48), sw = W / 320;
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:100%">`;
  if (zone && zone.length) s += `<polygon points="${zone.map(p => p.join(",")).join(" ")}" fill="#3fb95022" stroke="#3fb950" stroke-width="${sw}"/>`;
  sel.forEach((m, i) => {
    const rv = rvs[i], near = rv ? rvNear(rv, t) : null;
    if (!near) return;
    const fire = rv.item === "fire";
    let bx = near[1].filter(b => b[1] >= RV_SHOW_MIN);
    if (fire) bx = nmsBoxes(bx, 0.5);
    for (const b of bx) {
      const th = fire && b[0] === 1 ? (rv.smoke != null ? rv.smoke : rv.conf) : rv.conf, on = rv.item === "falldown" || b[1] >= th, up = i * (fs + 2);
      s += `<rect x="${b[2]}" y="${b[3]}" width="${b[4] - b[2]}" height="${b[5] - b[3]}" fill="none" stroke="${m.col}" stroke-width="${on ? sw : sw / 2}"${on ? "" : ` stroke-dasharray="${sw * 2} ${sw * 1.5}" opacity=".8"`}/>` +
        `<text x="${b[2] + 2}" y="${Math.max(fs + up, b[3] - 4 - up)}" font-size="${fs}" font-weight="700" fill="${m.col}" stroke="#000" stroke-width="${sw}" paint-order="stroke">${fire ? (b[0] === 1 ? "연기 " : "불 ") : ""}${b[1].toFixed(2)}</text>`;
    }
  });
  return s + "</svg>";
}
function p3BarSvg(row, t) {                                  // 재생바: 정답 유효창 + 모델마다 신호 선 · 예측 경보(모델 색) + 규칙 문턱
  const sel = p3Sel(), rvs = sel.map(p3C), r0 = rvs.find(Boolean), gt = r0 && r0.gt != null ? r0.gt : row.gt;
  const total = p3Total(), W = 1000, H = 64, px = x => x / total * W, th = new Set();
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">` + barFrame(gt, total, W, H, px);
  sel.forEach((m, i) => {
    const rv = rvs[i];
    if (!rv) return;
    s += plotPath(rv.signal, 1, m.col, px, H);
    if (rv.item === "fire") s += plotPath(rv.signal, 2, m.col + "66", px, H);
    if (rv.conf != null) th.add(rv.conf);
    if (rv.alarm != null) s += `<line x1="${px(rv.alarm)}" y1="0" x2="${px(rv.alarm)}" y2="${H}" stroke="${m.col}" stroke-width="2" stroke-dasharray="4 3"/>`;
  });
  th.forEach(c => { const y = H - Math.min(1, c) * (H - 6) - 3; s += `<line x1="0" y1="${y}" x2="${W}" y2="${y}" stroke="#c9d1d9" stroke-width="1" stroke-dasharray="3 4" opacity=".6"/>`; });
  if (t) s += `<line x1="${px(t)}" y1="0" x2="${px(t)}" y2="${H}" stroke="#e6edf3" stroke-width="1.5"/>`;
  return s + "</svg>";
}
