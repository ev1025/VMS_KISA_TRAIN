// dash_v2/js/main.js — 모드 전환·결과 탭·boot(). app.js 에서 분리(2026-09-09). 로드 순서: core → review → data → editor → main (dashboard.html)
// ---------- 모드 ----------
let IS_BENCH = false;                 // 라벨 작업대(서버로 보내는 쪽)인가. boot 에서 /api/pushinfo 로 정한다
function buildMode() {
  const box = $("#modeBox"); box.innerHTML = "";
  const TABS = IS_BENCH ? [["data", "데이터 확인"]]                                  // 작업대는 라벨만 한다
                        : [["data", "데이터 확인"], ["review", "영상 검수"], ["results", "결과"], ["history", "히스토리"]];
  TABS.forEach(([k, label]) => {
    const b = el("button", k === CUR.mode ? "on" : "", label);
    b.onclick = () => {
      if (CUR.mode === k) return;
      if (CUR.mode === "data" && typeof saveSession === "function") {          // 탭을 오갔다 와도 자리를 지키려고 떠나기 전에 적는다
        try { saveSession({ dsKind: DS_KIND, dsSel: DS_SEL }); } catch (e) {}
      }
      CUR.mode = k; buildMode(); applyMode();
    };
    box.appendChild(b);
  });
  const g = $("#gfBox"); g.innerHTML = "";                                        // 전역 항목 필터: 모든 탭에 적용(core.js GF)
  Object.entries(GF_DEF).forEach(([k, d]) => {
    const b = el("button", k === GF ? "on" : "", d.label);
    b.setAttribute("aria-pressed", k === GF);
    b.onclick = () => {
      if (GF === k) return;
      GF = k; try { localStorage.setItem("kisa_gf", k); } catch (e) {}
      applyMode._first = true;                       // 필터를 바꾸면 보던 영상으로 되돌리지 않는다(목록만 바뀌고 가운데는 옛 영상이 남던 것). 새 목록의 첫 영상이 열린다
      buildMode(); applyMode();
    };
    g.appendChild(b);
  });
}
function applyMode() {
  document.onkeydown = null;   // 편집기 밖에선 단축키 끄기
  const wide = CUR.mode === "results" || CUR.mode === "history";   // 결과 · 히스토리 탭은 가운데만
  $("#right").hidden = wide;
  $(".left").style.display = wide ? "none" : "";   // 결과 탭은 결과만(왼쪽 패널째 숨김). .srcbox 의 display:flex 가 [hidden] 을 이겨 드롭다운이 남던 것도 여기서 끝(2026-09-29)
  if (CUR.mode !== "review") {                      // 검수 탭의 항목 이름표 · 모델 · 판정 필터를 바로 거둔다. 데이터 탭은 목록을 받아 온 뒤에야 다시 그려 그 사이 남아 보였다
    $("#filtBox").hidden = true; $("#filtBox").innerHTML = "";
    const lb = $(".srcbox label"); if (lb && lb.textContent === "검수 항목") lb.textContent = "데이터 원본";
  }
  const kindBox = $("#dsKind"); if (kindBox) kindBox.style.display = (CUR.mode === "data") ? "flex" : "none";   // 원본/학습 버튼은 데이터 확인에서만
  const emptyMsg = { data: "데이터셋과 이미지를 선택하세요", review: "영상을 선택하세요" }[CUR.mode];
  $("#center").innerHTML = '<div class="empty">' + emptyMsg + '</div>';
  $("#right").innerHTML = '<div class="empty">—</div>';
  if (CUR.mode === "data") {
    buildDatasetSrc();
  if (typeof initPushButton === "function") initPushButton();
    if (!applyMode._first && typeof restoreLast === "function") {              // 첫 진입은 boot 이 복원한다. 탭을 오갔다 온 경우만 여기서
      try { restoreLast(loadSession()); } catch (e) {}
    }
    applyMode._first = false;
  } else if (CUR.mode === "results") {
    $("#list").innerHTML = ""; buildResults();
  } else if (CUR.mode === "history") {
    $("#list").innerHTML = ""; buildHistory();
  } else {
    enterReview();   // 모델 목록 · 판정을 서버에서 받아 첫 영상(또는 보던 영상)을 연다(review.js)
  }
}
// ---------- 부트 ----------

// ---------- 결과 탭(2026-09-29 재설계): 새 데이터 실험만, 비교 블록으로 ----------
// 블록 = 대조군 하나 + 독립변수 하나만 다른 실험들. 정의는 configs/result_blocks.yaml, 계산은 dash_v2/results_newdata.py(/api/result_blocks).
// 맨 위 = 큐 상자(옛 결과 탭과 같은 모양, 30초 갱신). 블록 머리 표 = 독립변수 · 종속변수 · 판정 기준 · 통제변수(데이터 / 학습 설정, 실제 args.yaml 로 대조) · 교란 변수 · 참고. 진행 · 예상 종료는 /api/queue 를 합친다.
// 문구 규칙(09-29 사용자 교정안): 명사형 종결, 긴 괄호 부연 금지, 가운데 점 나열 대신 줄마다 불릿.
const NR_KO = { intrusion: "침입", loitering: "배회", fire: "방화" };
const nrEsc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const nrFmt = v => Array.isArray(v) ? (v.length ? v.join(", ") : "없음") : String(v);
const nrMut = s => `<span class="nr-mut">${s}</span>`;
const nrList = a => (a || []).length ? `<ul class="nr-ul">${a.map(x => `<li>${x}</li>`).join("")}</ul>` : nrMut("-");
const nrArr = v => v == null ? [] : Array.isArray(v) ? v : [v];
let NR_PH = "";                                   // 단계 필터: "" 전체 · 단계 코드 · "_none" 단계 없음
try { NR_PH = localStorage.getItem("nr_ph") || ""; } catch (e) {}
const nrPhOk = r => !NR_PH || (NR_PH === "_none" ? !r.phase : r.phase === NR_PH);
const nrPhBdg = (D, ph) => (D.phases || {})[ph] ? `<span class="nr-bdg ph">${nrEsc(D.phases[ph])}</span>` : "";   // 이름표는 phases 값 그대로
function nrBadges(D, r) {                         // 실험마다 모델 · 단계 배지
  const m = r.args && r.args.model ? String(r.args.model).replace(/\.pt$/, "").replace(/^yolo/i, "YOLO") : "";
  return `<div>${m ? `<span class="nr-bdg">${nrEsc(m)}</span>` : ""}${nrPhBdg(D, r.phase)}</div>`;
}
function nrJob(q, exp) { return (q.jobs || []).find(j => j.name === exp); }
const nrOpen = (() => { try { const v = JSON.parse(localStorage.getItem("nr_open") || "null"); if (Array.isArray(v)) return new Set(v); } catch (e) {} return new Set(["_queue"]); })();   // 펼친 블록(새로고침 · 다시 열어도 유지)
function nrSaveOpen() { try { localStorage.setItem("nr_open", JSON.stringify([...nrOpen])); } catch (e) {} }
function nrBindToggles(root) {
  root.querySelectorAll("details[data-id]").forEach(d => { d.ontoggle = () => { d.open ? nrOpen.add(d.dataset.id) : nrOpen.delete(d.dataset.id); nrSaveOpen(); }; });
}
function nrStatus(r, q) {                        // 상태만(날짜는 '학습 종료' 칸)
  if (r.status === "done") return '<span class="nr-ok">채점 완료</span>';
  if (r.status === "scoring") return "채점 대기";
  if (r.status === "train") {
    const j = nrJob(q, r.exp), ep = j && j.epoch != null ? j.epoch : r.epochs_run, n = (j && j.epochs) || r.args.epochs || 60;
    return `<span class="nr-pbar"><i><b style="width:${Math.round(ep / n * 100)}%"></b></i>${ep}/${n} 에폭</span>` +
      ((q.running || []).includes(r.exp) ? "" : nrMut(" 러너에 없음"));
  }
  if (r.status === "queue") return nrMut("대기");
  if (r.status === "skip") return nrMut("건너뜀");
  return nrMut(nrEsc(r.status));
}
function nrEnded(r, q) {                         // 학습 종료 시각(KST). 학습 중이면 러너의 예상 시각
  if (r.ended) return nrEsc(r.ended.slice(5, 16));
  const j = nrJob(q, r.exp);
  return j && j.finish_kst ? nrMut("예상 " + nrEsc(j.finish_kst)) : nrMut("-");
}
function nrScore(r) {                            // best / last, 굵게 = 비교에 쓴 값(낮은 쪽)
  if (r.status !== "done") return nrMut("-");
  return r.items.map(it => {
    const s = r.scores[it] || {}, f = ck => s[ck] ? `<span class="${ck === r.lo[it] ? "nr-lo" : "nr-hi"}" title="정검 ${s[ck].tp} / 미검 ${s[ck].fn} / 오검 ${s[ck].fp}">${s[ck].f1.toFixed(2)}</span>` : "-";
    return `<div><span class="nr-it">${NR_KO[it]}</span>${f("best")} / ${f("last")}</div>`;
  }).join("");
}
function nrRule3(r) {                            // 3규칙 F1(초당 2장 · 시작 0, 채점편은 측정만). 규칙은 채점편 밖(연구개발 안 본 편 · 헛불 38편)에서 고른 것
  const R = r.rule3;
  if (!R) return nrMut("-");
  const f1 = s => !s ? "-" : (s[0] ? (200 * s[0] / (2 * s[0] + s[1] + s[2])).toFixed(1) : "0.0");
  const FAM = { intrusion: ["G", "B", "T", "B+S"], loitering: ["G", "B", "T"], fire: ["B", "T"] };
  return r.items.map(it => ["best", "last"].map(ck => {
    const x = (R[ck] || {})[it];
    if (!x) return "";
    return `<div><span class="nr-it">${NR_KO[it]} ${ck}</span>` + FAM[it].map(f => {
      const s = x[f], tip = s ? `정검 ${s[0]} / 미검 ${s[1]} / 오검 ${s[2]}` : (it === "fire" && f === "B" ? "헛불 38편 헛경보 0 인 규칙 없음" : "없음");
      return `<span title="${tip}">${f} <b>${f1(s)}</b></span>`;
    }).join(" · ") + "</div>";
  }).join("")).join("");
}
function nrKeys(r, clips) {                      // 방화 변별 편: 비교에 쓴 체크포인트의 편 판정
  if (r.status !== "done") return nrMut("-");
  const bad = ((r.scores.fire || {})[r.lo.fire] || {}).bad || {};
  return '<span class="nr-keys">' + clips.map(c => {
    const v = bad[c], k = v === "미검" ? "miss" : v === "오검" ? "bad" : "ok";
    return `<span class="${k}" title="${c} ${v || "정검"}">${c.slice(4, 7)} ${v ? v[0] : "정"}</span>`;
  }).join("") + "</span>";
}
function nrChanged(b, r) {                       // 조건 = 블록에 적은 값 + 파일에서 읽은 실제 데이터(이름 한 줄씩, 총 장수)
  const lab = b.labels[r.exp] || "";
  const sub = [];
  b.diffs.filter(d => d.declared).forEach(d => {
    const v = d.values[r.exp];
    if (d.key === "data") { (v.length ? v : ["추가 데이터 없음"]).forEach(x => sub.push(nrEsc(x))); if (r.n_train) sub.push(`총 ${r.n_train.toLocaleString()}장`); }
    else if (!lab.includes(nrFmt(v))) sub.push(`${d.label} ${nrEsc(nrFmt(v))}`);   // 조건 문구에 이미 있는 값은 다시 안 쓴다
  });
  return `<b>${nrEsc(lab)}</b>` + (sub.length ? `<div class="nr-sub">${sub.join("<br>")}</div>` : "");
}
function nrTrain(T, rest) {                      // 통제변수 · 학습 설정 불릿
  const out = [];
  if ("model" in T) out.push(`모델: ${nrEsc(String(T.model).replace(/^yolo/i, "YOLO"))} (COCO 사전학습)`);
  const P = [["imgsz", "해상도"], ["batch", "배치"], ["epochs", "Epoch"], ["patience", "Patience"], ["seed", "Seed"], ["multi_scale", "Multi_scale"]]
    .filter(([k]) => k in T).map(([k, l]) => `${l} ${nrEsc(nrFmt(T[k]))}`);
  if (P.length) out.push("파라미터: " + P.join(" / "));
  if ("optimizer" in T) out.push("Optimizer: " + nrEsc(T.optimizer));
  if (rest) out.push(`기타 학습 인자: ${rest}개 동일`);
  return out;
}
function nrCond(b, D) {                          // 블록 머리 표
  const s = b.same, name = x => nrEsc(b.labels[x] || x), code = a => `<span class="nr-code">${a.map(nrEsc).join("<br>")}</span>`;
  const data = [];
  if (s.data_all) data.push(s.data.length === 1 ? `학습셋: ${nrEsc(b.same_data || "")} (${nrEsc(s.data[0])})` : `학습셋: ${nrEsc(b.same_data || "")}<br>${code(s.data)}`);
  else {
    if (b.same_data) data.push(`학습셋: ${nrEsc(b.same_data)}`);
    if (s.data.length) data.push(`공통 데이터:<br>${code(s.data)}`);
  }
  if (s.val) data.push(`검증셋: ${nrEsc(s.val.text)} (best 선택용, ${nrEsc(s.val.note)})`);
  const rows = [
    ["독립변수", nrList(nrArr(b.iv).map(nrEsc))],
    ["종속변수", nrList(nrArr((D.dv || {})[b.item]).map(nrEsc))],
    ["판정 기준", nrList([...nrArr((D.rule || {})[b.item]), ...nrArr(b.rule_extra)].map(nrEsc))],
    ["통제변수 · 데이터", nrList(data)],
    ["통제변수 · 학습 설정", nrList(nrTrain(Object.fromEntries(s.train), s.rest))],
  ];
  b.diffs.filter(d => !d.declared).forEach(d => {
    const vals = Object.entries(d.values).map(([x, v]) => `${name(x)}: ${nrEsc(nrFmt(v))}`);
    rows.push([(d.harmless ? "차이 · " : "교란 변수 · ") + d.label, nrList(d.harmless ? [...vals, "영향 없음: " + nrEsc(d.harmless)] : vals), d.harmless ? "" : "warn"]);
  });
  const ref = nrArr(b.note).map(nrEsc);
  if (b.planned) ref.push("대기 중 실험: 큐(Queue) 설정값 기준", "학습 시작 시: 실제 인자 기준으로 재비교");
  if (ref.length) rows.push(["참고", nrList(ref)]);
  return '<table class="nr-cond">' + rows.map(([k, v, c]) => `<tr class="${c || ""}"><th>${k}</th><td>${v}</td></tr>`).join("") + "</table>";
}
function nrBlock(b, D, q) {
  const kc = (D.key_clips || {})[b.item];
  const head = `<tr><th>실험</th><th>조건</th><th>상태</th><th>학습 종료</th><th>F1 best / last<br>${nrMut("굵게 = 비교값")}</th><th>3규칙 F1<br>${nrMut("초당 2장 · 시작 0")}</th>` +
    (kc ? "<th>변별 편</th>" : "") + "<th>기준 실험과 차이<br>(정검 편수)</th><th>판정</th></tr>";
  const rows = [b.control, ...b.members].map((x, i) => {
    const r = D.runs[x], v = b.verdicts[x];
    const delta = !i ? nrMut("-") : v ? Object.entries(v.delta).map(([it, d]) => `<div><span class="nr-it">${NR_KO[it]}</span>${d > 0 ? "+" : ""}${d}</div>`).join("") : nrMut("-");
    const chip = !i ? "" : v ? `<span class="nr-chip ${v.call === "동률" ? "tie" : v.call === "개선" ? "win" : "lose"}">${v.call}</span>`
      : `<span class="nr-chip wait">${r.status === "train" ? "학습 중" : r.status === "queue" ? "대기" : "채점 대기"}</span>`;
    return `<tr class="${i ? "" : "ctl"}"><td class="nr-exp">${nrEsc(x).replace(/_/g, "_<wbr>")}${i ? "" : '<span class="nr-role">기준 실험</span>'}${nrBadges(D, r)}${r.new ? "" : '<div class="nr-warn">새 데이터 실험 아님</div>'}</td>` +
      `<td class="nr-chg">${nrChanged(b, r)}</td><td class="nr-st">${nrStatus(r, q)}</td><td class="nr-num">${nrEnded(r, q)}</td>` +
      `<td class="nr-num">${nrScore(r)}</td><td class="nr-r3">${nrRule3(r)}</td>${kc ? `<td>${nrKeys(r, kc)}</td>` : ""}<td class="nr-num">${delta}</td><td>${chip}</td></tr>`;
  }).join("");
  const concl = nrArr(b.conclusion);
  const chips = b.members.map(x => { const v = b.verdicts[x], r = D.runs[x];     // 접었을 때도 판정이 보이게
    return v ? `<span class="nr-chip ${v.call === "동률" ? "tie" : v.call === "개선" ? "win" : "lose"}">${v.call}</span>`
      : `<span class="nr-chip wait">${r.status === "train" ? "학습 중" : r.status === "queue" ? "대기" : "채점 대기"}</span>`; }).join("");
  return `<details class="nr-block" data-id="${nrEsc(b.id)}"${nrOpen.has(b.id) ? " open" : ""}><summary class="nr-bt">${nrEsc(b.date ? `[${b.date}] ` : "")}${nrEsc(b.title)}<span class="nr-sum">${nrPhBdg(D, D.runs[b.control].phase)}${chips}</span></summary><div class="nr-body">` +
    (b.question ? `<p class="nr-q"><b>목적:</b> ${nrEsc(b.question)}</p>` : "") + nrCond(b, D) +
    `<div class="nr-tbl"><table>${head}${rows}</table></div>` +
    (concl.length ? `<div class="nr-note"><b>결론</b>${nrList(concl.map(nrEsc))}</div>` : "") + "</div></details>";
}
function nrOthers(D, q) {                        // 블록에 아직 안 넣은 새 데이터 실험(끝난 것 · 학습 중인 것)
  const os = D.others.filter(x => gfMeta(D.runs[x].item) && nrPhOk(D.runs[x]));
  if (!os.length) return "";
  const rows = os.map(x => { const r = D.runs[x];
    return `<tr><td class="nr-exp">${nrEsc(x).replace(/_/g, "_<wbr>")}${nrBadges(D, r)}</td><td>${r.item}</td><td class="nr-num">${nrEsc(r.args.imgsz)} / ${nrEsc(r.args.batch)}</td>` +
      `<td class="nr-chg"><div class="nr-sub">${r.data.map(nrEsc).join("<br>")}</div></td><td class="nr-st">${nrStatus(r, q)}</td><td class="nr-num">${nrEnded(r, q)}</td><td class="nr-num">${nrScore(r)}</td><td class="nr-r3">${nrRule3(r)}</td></tr>`; }).join("");
  return `<details class="nr-block" data-id="_others"${nrOpen.has("_others") ? " open" : ""}><summary class="nr-bt">비교 묶음에 없는 실험 ${nrMut(os.length + "개")}</summary><div class="nr-body">` +
    `<p class="nr-q">비교 묶음에 추가 시 위로 이동</p>` +
    `<div class="nr-tbl"><table><tr><th>실험</th><th>항목</th><th>해상도 / 배치</th><th>학습 데이터</th><th>상태</th><th>학습 종료</th><th>F1 best / last</th><th>3규칙 F1<br>${nrMut("초당 2장 · 시작 0")}</th></tr>${rows}</table></div></div></details>`;
}
function nrTerms(T) {                            // 맨 위 '용어 정리'(접힘). 정의는 result_blocks.yaml terms
  if (!T.length) return "";
  let g0 = null;
  const rows = T.map(t => { const g = t.g === g0 ? "" : (g0 = t.g); return `<tr><td class="nr-mut">${nrEsc(g)}</td><th>${nrEsc(t.t)}</th><td>${nrEsc(t.d)}</td></tr>`; }).join("");
  return `<details class="nr-terms"${nrTerms.open ? " open" : ""}><summary>용어 정리 ${nrMut(T.length + "개")}</summary><div class="nr-tscroll"><table>${rows}</table></div></details>`;
}
function nrScoreCard(S) {                        // 항목별 실제로 낼 수 있는 최고 점수(공식 채점) · 그 모델. 누르면 판정기 설정(학습 외)
  if (!S.length) return "";
  nrScoreCard.S = S;
  return `<div class="nr-score">` + S.map(s => {
    const has = s.f1 != null, cls = (!has ? "" : (s.f1 >= 90 ? " ok" : " bad")) + (nrScoreCard.open === s.item ? " on" : "");
    const tip = has && s.tp != null ? ` title="정검 ${s.tp} · 미검 ${s.fn} · 오검 ${s.fp}"` : "";
    return `<button type="button" class="nr-sc${cls}" data-it="${nrEsc(s.item)}"${tip}><div class="nr-sc-it">${nrEsc(s.item)}</div><div class="nr-sc-v">${has ? s.f1.toFixed(2) : "–"}</div>` +
      `<div class="nr-sc-m">${has ? nrEsc(s.model || s.exp) + (s.ck ? " · " + nrEsc(s.ck) : "") : "채점 전"}</div></button>`;
  }).join("") + `</div><div id="nrJudge">${nrJudge()}</div>`;
}
function nrJudge() {                              // 누른 스코어카드 항목의 판정기 설정: 적용 중 · 시험한 기술(결과 · 판정 · 이유)
  const s = (nrScoreCard.S || []).find(x => x.item === nrScoreCard.open), j = s && s.judge;
  if (!j) return "";
  const pill = d => `<span class="nr-dec nr-dec-${{채택: "ok", 기각: "no", 보류: "hold"}[d] || "wait"}">${nrEsc(d || "")}</span>`;
  const here = t => !t.variant ? nrMut("–") : !t.here ? nrMut("계산 전") :
    `${s.f1 != null ? s.f1.toFixed(2) + " → " : ""}<b>${t.here["점수"].toFixed(2)}</b> ${nrMut(`정 ${t.here["정검"]} · 미 ${t.here["미검"]} · 오 ${t.here["오검"]}`)}`;
  const rows = (j.tried || []).map(t => `<tr><th>${nrEsc(t.name)}${t.phase && nrJudge.ph[t.phase] ? `<div><span class="nr-bdg ph">${nrEsc(nrJudge.ph[t.phase])}</span></div>` : ""}</th><td>${nrEsc(t.what || "")}</td><td>${pill(t.dec)}</td><td>${nrEsc(t.result || "")}</td><td>${nrEsc(t.why || "")}</td><td class="nr-num">${here(t)}</td></tr>`).join("");
  return `<div class="nr-judge"><div class="nr-jh">${nrEsc(s.item)} 판정기 설정 (학습 외)${s.exp ? nrMut(` · ${s.exp} · ${s.ck}`) : ""}</div>` +
    `<div class="nr-jc"><b>적용 중</b><ul>${(j.applied || []).map(a => `<li>${nrEsc(a)}</li>`).join("")}</ul></div>` +
    (rows ? `<div class="nr-jc"><b>시험한 기술</b><div class="nr-tbl"><table><tr><th>기술</th><th>내용</th><th>판정</th><th>결과</th><th>이유</th><th>이 모델에 적용<br>${nrMut("채점편, 측정만")}</th></tr>${rows}</table></div></div>` : "") + `</div>`;
}
function nrScoreBind(root) {                      // 스코어카드 누르면 펼침 · 다시 누르면 접힘
  root.querySelectorAll(".nr-sc[data-it]").forEach(b => { b.onclick = () => {
    nrScoreCard.open = nrScoreCard.open === b.dataset.it ? null : b.dataset.it;
    root.querySelectorAll(".nr-sc[data-it]").forEach(x => x.classList.toggle("on", x.dataset.it === nrScoreCard.open));
    const box = root.querySelector("#nrJudge"); if (box) box.innerHTML = nrJudge();
  }; });
}
function nrQueueHtml(q) {                       // 맨 위 큐 상자: 옛 결과 탭과 같은 모양(실행 중 실험 · 에폭 · 이 에폭 · 속도 · 에폭당 · 예상 종료 · 최근 mAP · GPU + 러너 로그)
  const Y = new Date().getFullYear();
  const kst = l => l.replace(/^\[(\d\d)-(\d\d) (\d\d):(\d\d)\]/, (_, mo, da, h, mi) => {   // 옛 러너 줄(UTC, KST 표기 없음) → +9시간. 새 줄은 러너가 KST 로 쓴다
    const d = new Date(Date.UTC(Y, +mo - 1, +da, +h, +mi) + 9 * 3600e3), z = n => String(n).padStart(2, "0");
    return `[${z(d.getUTCMonth() + 1)}-${z(d.getUTCDate())} ${z(d.getUTCHours())}:${z(d.getUTCMinutes())} KST]`;
  });
  const run = q.running || [], jobs = q.jobs || [];
  const lastLog = (q.log || []).slice(-6).map(l => `<div class="nr-qlog">${nrEsc(kst(l))}</div>`).join("");
  return `<div class="nr-qhead">큐 <span style="color:${run.length ? "#3fb950" : "var(--mut)"}">${run.length ? "실행 중 " + run.length + "잡" : "대기/없음"}</span>` +
    (run.length ? ` <span style="color:var(--tx);font-weight:600">${run.map(nrEsc).join(" · ")}</span>` : "") + `</div>` +
    (jobs.length ? `<div class="nr-qtbl"><table style="border-collapse:collapse;margin:8px 0 4px;font-size:var(--fs-xs)"><thead><tr style="color:var(--mut);text-align:left"><th style="padding:2px 10px 2px 0">실험</th><th style="padding:2px 10px">에폭</th><th style="padding:2px 10px">이 에폭</th><th style="padding:2px 10px">속도</th><th style="padding:2px 10px">에폭당</th><th style="padding:2px 10px">남음 → 예상 종료(KST)</th><th style="padding:2px 10px" title="직전 에폭 검증">최근 mAP50 / 50-95</th><th style="padding:2px 10px">GPU</th></tr></thead><tbody>` +
      jobs.map(j => j.epoch == null ? `<tr><td style="padding:3px 10px 3px 0;font-weight:700">${nrEsc(j.name)}</td><td colspan="7" style="color:var(--mut)">${nrEsc(j.state || "")}</td></tr>` :
        `<tr><td style="padding:3px 10px 3px 0;font-weight:700;white-space:nowrap">${nrEsc(j.name)}</td>` +
        `<td style="padding:3px 10px;font-variant-numeric:tabular-nums;white-space:nowrap"><b>${j.epoch}</b>/${j.epochs} <span style="display:inline-block;width:70px;height:6px;background:var(--panel2);border-radius:var(--r-sm);vertical-align:middle;margin-left:4px"><span style="display:block;width:${Math.round(j.epoch / j.epochs * 100)}%;height:100%;background:#3fb950;border-radius:var(--r-sm)"></span></span></td>` +
        `<td style="padding:3px 10px;font-variant-numeric:tabular-nums">${j.pct}% <span style="color:var(--mut)">(${j.it}/${j.its} · ${nrEsc(j.elapsed)} 경과 · ${nrEsc(j.eta)} 남음)</span></td>` +
        `<td style="padding:3px 10px;font-variant-numeric:tabular-nums;white-space:nowrap">${j.it_s} it/s</td><td style="padding:3px 10px;white-space:nowrap">${j.epoch_min != null ? j.epoch_min + "분" : "–"}</td>` +
        `<td style="padding:3px 10px;font-variant-numeric:tabular-nums;white-space:nowrap">${j.remain_h}시간 → <b>${nrEsc(j.finish_kst || "–")}</b></td>` +
        `<td style="padding:3px 10px;font-variant-numeric:tabular-nums;white-space:nowrap">${j.val ? `${j.val.map50.toFixed(3)} / ${j.val.map5095.toFixed(3)} <span style="color:var(--mut)">(P ${j.val.P.toFixed(2)} R ${j.val.R.toFixed(2)})</span>` : '<span style="color:var(--mut)">첫 검증 전</span>'}</td>` +
        `<td style="padding:3px 10px;white-space:nowrap">${nrEsc(j.mem == null ? "–" : j.mem)}</td></tr>`).join("") + `</tbody></table></div>` : "") +
    `<div class="nr-qdet"><div style="color:var(--mut)">러너 로그</div>${lastLog || '<div style="color:var(--mut)">로그 없음</div>'}</div>`;   // 토글 없이 항상 보임(09-30 사용자)
}
function nrQueueBind(box) {}                     // 러너 로그는 항상 펼침(09-30). 부르는 곳이 있어 이름만 남김
async function nrQueueTick() {                   // 학습 중이면 30초마다 큐 상자만 갱신(화면 전체를 다시 그리지 않음)
  const box = $("#nrQ");
  if (CUR.mode !== "results" || !box) return;
  try {
    const q2 = await (await fetch("/api/queue")).json();
    box.innerHTML = nrQueueHtml(q2); nrQueueBind(box);
    if ((q2.jobs || []).length) window._resQ = setTimeout(nrQueueTick, 30000);
  } catch (e) {}
}
async function buildResults() {
  const c = $("#center"), y = c.scrollTop;
  if (!c.querySelector(".nr")) c.innerHTML = '<div class="empty">불러오는 중…</div>';
  let D, q = { running: [], jobs: [], log: [] };
  try { D = await (await fetch("/api/result_blocks")).json(); } catch (e) { c.innerHTML = '<div class="empty">결과를 못 읽었습니다</div>'; return; }
  try { q = await (await fetch("/api/queue")).json(); } catch (e) {}
  if (CUR.mode !== "results") return;
  if (D.error) { c.innerHTML = `<div class="empty">${nrEsc(D.error)}</div>`; return; }
  nrDraw(D, q);
  c.scrollTop = y;
  clearTimeout(window._resQ); if ((q.jobs || []).length) window._resQ = setTimeout(nrQueueTick, 30000);
  clearTimeout(window._resT);                     // 학습 중 · 채점 대기 실험이 있으면 1분마다 다시 읽는다(스크롤 유지)
  if (Object.values(D.runs).some(r => r.status === "train" || r.status === "scoring")) window._resT = setTimeout(() => { if (CUR.mode === "results") buildResults(); }, 60000);
}
function nrDraw(D, q) {                           // 전역 항목 필터 · 단계 필터를 걸어 그린다
  const c = $("#center");
  nrJudge.ph = D.phases || {};
  const used = new Set(Object.values(D.runs).map(r => r.phase).filter(Boolean));
  const phf = `<div class="nr-phf"><label for="nrPh">단계</label><select id="nrPh"><option value="">전체</option>` +
    Object.entries(D.phases || {}).filter(([k]) => used.has(k)).map(([k, v]) => `<option value="${nrEsc(k)}"${k === NR_PH ? " selected" : ""}>${nrEsc(v)}</option>`).join("") +
    `<option value="_none"${NR_PH === "_none" ? " selected" : ""}>단계 없음</option></select></div>`;
  const blocks = D.blocks.filter(b => gfMeta(b.item) && [b.control, ...b.members].some(x => nrPhOk(D.runs[x])));
  const body = blocks.map(b => nrBlock(b, D, q)).join("") + nrOthers(D, q);
  c.innerHTML = `<div class="nr"><div class="nr-top">${nrScoreCard((D.score || []).filter(s => GF === "all" || gf().card.includes(s.item)))}<div class="nr-queue" id="nrQ">${nrQueueHtml(q)}</div>` +   // 위에 고정: 항목별 최고 점수 · 큐(항상 펼침) · 용어 정리
    nrTerms(D.terms || []) + phf + `</div>` + (body || '<div class="empty">이 조건인 실험 없음</div>') + "</div>";
  nrScoreBind(c);
  $("#nrPh").onchange = e => { NR_PH = e.target.value; try { localStorage.setItem("nr_ph", NR_PH); } catch (x) {} nrDraw(D, q); };
  const tm = c.querySelector(".nr-terms"); if (tm) tm.ontoggle = () => { nrTerms.open = tm.open; };   // 1분 갱신 때 펼친 상태 유지
  nrQueueBind($("#nrQ")); nrBindToggles(c);
}


// 전파 작업 전역 표시(헤더). 서버 큐를 2초마다 조회
let _JOBS_T = null;
async function pollJobs() {
  const box = $("#jobStat"); if (!box) return;
  let jobs = [];
  try { jobs = await (await fetch("/api/sam2_jobs")).json(); } catch (e) { jobs = []; }
  const run = jobs.filter(j => j.state === "running"), q = jobs.filter(j => j.state === "queued");
  try {                                                // 지금 열린 편집기 클립에 작업이 있으면 편집기도 진행률을 보이게(다른 곳에서 시작된 작업 포함)
    if (typeof ED !== "undefined" && ED && ED.watch && [...run, ...q].some(j => j.clip === ED.clip.split("/").pop())) ED.watch();
  } catch (e) {}
  if (!run.length && !q.length) { box.hidden = true; box.innerHTML = ""; return; }
  const spin = '<span style="display:inline-block;width:11px;height:11px;border:2px solid #58a6ff55;border-top-color:#58a6ff;border-radius:50%;animation:ed_sp .8s linear infinite"></span>';
  if (!document.getElementById("ed_sp")) { const st = document.createElement("style"); st.id = "ed_sp"; st.textContent = "@keyframes ed_sp{to{transform:rotate(360deg)}}"; document.head.appendChild(st); }
  const parts = run.map(j => `<b>${j.clip}</b> ${j.total ? Math.min(99, Math.round(j.done / j.total * 100)) : 0}%`);
  if (q.length) parts.push(`<span style="color:var(--mut)">대기 ${q.length}</span>`);
  box.innerHTML = spin + `<span>전파 ${parts.join(" · ")}</span>`;
  box.hidden = false;
  box.onclick = () => {                              // 진행 중 클립으로 이동(원본 데이터 목록에 있을 때)
    const j = run[0] || q[0]; if (!j) return;
    const it = [...document.querySelectorAll("#list .item")].find(e => (e.dataset.rel || "").split("/").pop().replace(/\.mp4$/, "") === j.clip);
    if (it) it.click();
  };
}
function startJobPoll() { if (_JOBS_T) return; pollJobs(); _JOBS_T = setInterval(pollJobs, 2000); }
async function boot() {
  startJobPoll();
  META = await (await fetch("/api/meta")).json();
  try { LABELS = await (await fetch("/api/labels")).json(); } catch (e) { LABELS = null; }
  try { PLABELS = await (await fetch("/api/labels?kind=person")).json(); } catch (e) { PLABELS = null; }
  try { IMGLABELS = await (await fetch("/api/labels?kind=image")).json(); } catch (e) { IMGLABELS = []; }
  try { SAMFR = await (await fetch("/api/sam2frames")).json(); } catch (e) { SAMFR = {}; }   // SAM 전파 프레임(목록 배지 합산용)
  await loadClipStates();   // 클립 표시(기본/전파/손)·전파 구간. 목록을 그리기 전에 한 번만 읽는다
  try { DATASETS = await (await fetch("/api/datasets")).json(); } catch (e) { DATASETS = {}; }   // 데이터 규격(카테고리별 mode·gt·use)
  for (const [k, v] of Object.entries(META.items)) v.rows.forEach(row => row.item = k);
  try { IS_BENCH = !!(await (await fetch("/api/pushinfo")).json()).enabled; } catch (e) { IS_BENCH = false; }
  const last = (typeof loadSession === "function") ? loadSession() : {};
  if (["data", "review", "results", "history"].includes(last.mode)) CUR.mode = last.mode;
  if (IS_BENCH) CUR.mode = "data";     // 작업대엔 다른 탭이 없다(지난 세션이 검수였어도 데이터 확인으로)
  DS_KIND = "raw";                                  // 학습 데이터 탭은 없다
  if (last.dsSel && String(last.dsSel).startsWith("raw:")) DS_SEL = last.dsSel;
  buildMode(); applyMode();   // 시작 모드에 맞는 좌측/중앙 패널을 그린다(데이터 확인=데이터셋 패널)
  restoreLast(last);
}

// 새로고침 전에 보던 영상·프레임으로 되돌린다. 목록이 그려질 때까지만 기다리고, 없으면 조용히 포기.
async function restoreLast(last) {
  if (!last || CUR.mode !== "data") return;
  if (last.img && !last.rel) {                          // 이미지 편집 중이었으면 그 이미지로
    for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector("#list .item")) break; }
    try { openImage(last.img); } catch (e) {}
    return;
  }
  if (!last.rel) return;
  for (let i = 0; i < 40; i++) {
    await new Promise(r => setTimeout(r, 150));
    if (document.querySelector("#list .item")) break;
  }
  try {
    DS_EDIT = true;
    await showRawVideo(last.rel);                         // 편집기 열기(시작 프레임까지 열고 돌아온다)
    const mode = last.lmode || catMode(last.rel);        // 모드는 저장값, 없으면 카테고리로(방화 클립이 사람 모드로 열리지 않게)
    if (last.sec != null && LB.clip && mode !== "none") await openFrameAt(LB.clip, last.sec, mode);
  } catch (e) {}
}
boot();
