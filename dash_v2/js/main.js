// dash_v2/js/main.js — 모드 전환·결과 탭·boot(). app.js 에서 분리(2026-09-09). 로드 순서: core → review → data → editor → main (dashboard.html)
// ---------- 모드 ----------
function buildMode() {
  const box = $("#modeBox"); box.innerHTML = "";
  [["data", "데이터 확인"], ["review", "영상 검수"], ["results", "결과"]].forEach(([k, label]) => {
    const b = el("button", k === CUR.mode ? "on" : "", label);
    b.onclick = () => { if (CUR.mode === k) return; CUR.mode = k; buildMode(); applyMode(); };
    box.appendChild(b);
  });
}
function applyMode() {
  document.onkeydown = null;   // 편집기 밖에선 단축키 끄기
  $("#right").hidden = (CUR.mode === "results");   // 결과 탭은 우측 없이
  $(".srcbox").hidden = (CUR.mode === "results");   // 결과 탭은 소스 드롭다운 숨김
  const kindBox = $("#dsKind"); if (kindBox) kindBox.style.display = (CUR.mode === "data") ? "flex" : "none";   // 원본/학습 버튼은 데이터 확인에서만
  const emptyMsg = { data: "데이터셋과 이미지를 선택하세요", review: "영상을 선택하세요" }[CUR.mode];
  $("#center").innerHTML = '<div class="empty">' + emptyMsg + '</div>';
  $("#right").innerHTML = '<div class="empty">—</div>';
  if (CUR.mode === "data") {
    buildDatasetSrc();
  if (typeof initPushButton === "function") initPushButton();
  } else if (CUR.mode === "results") {
    $("#list").innerHTML = ""; buildResults();
  } else {
    buildSrc(); buildFilt(); renderList();
    // 첫 진입 시 첫 영상 자동 열기(현재 선택이 목록에 있으면 유지)
    const _rows = META.items[CUR.item].rows.filter(r => FILT === "all" || verdict(r, CUR.item) === FILT);
    const _cur = _rows.find(r => r.name === CUR.name) || _rows[0];
    if (_cur) { CUR.name = _cur.name; renderList(); renderCenter(_cur); renderRight(_cur); }
  }
}
// ---------- 부트 ----------

function dedupResults(data) {
  const SUMMARY = /^(KISA_SCORES|NIGHT_SUMMARY|FOG_SUMMARY)$/;   // 실험이 아니라 요약 파일
  data = data.filter(d => !SUMMARY.test(d.name));
  const rank = d => { const m = d.meta || {}; return (m.model ? 4 : 0) + (m.kind === "live_sa" ? 2 : m.kind === "archive" ? 0 : 3) + (d.clips && Object.keys(d.clips).length ? 1 : 0); };   // 대표 우선순위(러너 메타 > 라이브 > 보관, 클립 있으면 가점)
  const g = {};
  data.forEach(d => { const k = d.item + "|" + d.name; (g[k] || (g[k] = [])).push(d); });   // 같은 실험의 중복 기록만 합친다(점수가 같다고 합치면 구성 비교가 깨진다)
  return Object.values(g).map(list => {
    list.sort((a, b) => rank(b) - rank(a) || b.mtime - a.mtime);
    const rep = list[0];
    rep._members = [...new Set(list.map(d => d.name))];   // 같은 실험의 중복 기록(러너 메타·라이브 로그·보관본)
    if (!(rep.clips && Object.keys(rep.clips).length)) { const c = list.find(d => d.clips && Object.keys(d.clips).length); if (c) rep.clips = c.clips; }
    if (!(rep.rules && rep.rules.length > 1)) { const r = list.find(d => d.rules && d.rules.length > 1); if (r) rep.rules = r.rules; }
    return rep;
  });
}
async function buildResults() {
  const c = $("#center");
  c.innerHTML = '<div class="empty">불러오는 중…</div>';
  let data, q = { running: [], log: [] };
  try { data = await (await fetch("/api/results")).json(); } catch (e) { c.innerHTML = '<div class="empty">결과를 못 읽었습니다</div>'; return; }
  try { q = await (await fetch("/api/queue")).json(); } catch (e) {}
  const ITEMS = ["방화", "침입", "배회", "쓰러짐"];
  data = dedupResults(data);   // 같은 결과 여러 출처/재시도 → 한 줄로 접고, 요약 파일 제외
  const wrap = el("div"); wrap.style.cssText = "padding:18px 22px;max-width:1180px;margin:0 auto;width:100%";
  const head = el("div"); head.style.cssText = "display:flex;align-items:center;gap:10px;margin-bottom:2px";
  head.appendChild(el("div", "rtitle", `실험 채점 비교 <span class="tag">${data.length}건</span> <span style="color:var(--mut);font-weight:400;font-size:11px">· KISA 검증영상 F1 (항목별)</span>`));
  const rf = el("button", null, "↻ 새로고침"); rf.style.cssText = "margin-left:auto;background:var(--panel);color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:5px 12px;font-size:11px;font-weight:700;cursor:pointer"; rf.onclick = buildResults;
  head.appendChild(rf); wrap.appendChild(head);

  // ---- 큐 상태 (exp_queue.py): 실행 중 실험 + 러너 로그 끝 ----
  const qb = el("div"); qb.style.cssText = "margin-top:10px;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel);font-size:11px;line-height:1.7";
  const renderQueue = q => {                        // 큐 상자만 다시 그린다(30초 갱신 때 화면 전체를 다시 만들지 않게: 펼친 행·스크롤 유지)
  const Y = new Date().getFullYear();
  const kst = l => l.replace(/^\[(\d\d)-(\d\d) (\d\d):(\d\d)\]/, (_, mo, da, h, mi) => {   // 옛 러너 줄(UTC, KST 표기 없음) → +9시간. 새 줄은 러너가 KST 로 쓴다
    const d = new Date(Date.UTC(Y, +mo - 1, +da, +h, +mi) + 9 * 3600e3), z = n => String(n).padStart(2, "0");
    return `[${z(d.getUTCMonth() + 1)}-${z(d.getUTCDate())} ${z(d.getUTCHours())}:${z(d.getUTCMinutes())} KST]`;
  });
    const open = !!(qb.querySelector("details") && qb.querySelector("details").open);   // 러너 로그 펼침 상태 유지
  const lastLog = (q.log || []).slice(-6).map(l => `<div style="color:var(--mut);font-family:ui-monospace,Menlo,monospace;white-space:pre-wrap">${kst(l).replace(/</g, "&lt;")}</div>`).join("");
  qb.innerHTML = `<div style="font-weight:800">큐 <span style="color:${q.running.length ? "#3fb950" : "var(--mut)"}">${q.running.length ? "실행 중 " + q.running.length + "잡" : "대기/없음"}</span>` +
    (q.running.length ? ` <span style="color:var(--tx);font-weight:600">${q.running.join(" · ")}</span>` : "") + `</div>` +
    ((q.jobs || []).length ? `<table style="border-collapse:collapse;margin:8px 0 4px;font-size:11px"><thead><tr style="color:var(--mut);text-align:left"><th style="padding:2px 10px 2px 0">실험</th><th style="padding:2px 10px">에폭</th><th style="padding:2px 10px">이 에폭</th><th style="padding:2px 10px">속도</th><th style="padding:2px 10px">에폭당</th><th style="padding:2px 10px">남음 → 예상 종료(KST)</th><th style="padding:2px 10px" title="직전 에폭 검증(학습 목록에서 뽑은 600장)">최근 mAP50 / 50-95</th><th style="padding:2px 10px">GPU</th></tr></thead><tbody>` +
      q.jobs.map(j => j.epoch == null ? `<tr><td style="padding:3px 10px 3px 0;font-weight:700">${j.name}</td><td colspan="7" style="color:var(--mut)">${j.state || ""}</td></tr>` :
        `<tr><td style="padding:3px 10px 3px 0;font-weight:700;white-space:nowrap">${j.name}</td>` +
        `<td style="padding:3px 10px;font-variant-numeric:tabular-nums"><b>${j.epoch}</b>/${j.epochs} <span style="display:inline-block;width:70px;height:6px;background:var(--panel2);border-radius:3px;vertical-align:middle;margin-left:4px"><span style="display:block;width:${Math.round(j.epoch / j.epochs * 100)}%;height:100%;background:#3fb950;border-radius:3px"></span></span></td>` +
        `<td style="padding:3px 10px;font-variant-numeric:tabular-nums">${j.pct}% <span style="color:var(--mut)">(${j.it}/${j.its} · ${j.elapsed} 경과 · ${j.eta} 남음)</span></td>` +
        `<td style="padding:3px 10px;font-variant-numeric:tabular-nums">${j.it_s} it/s</td><td style="padding:3px 10px">${j.epoch_min != null ? j.epoch_min + "분" : "–"}</td>` +
        `<td style="padding:3px 10px;font-variant-numeric:tabular-nums">${j.remain_h}시간 → <b>${j.finish_kst || "–"}</b></td>` +
        `<td style="padding:3px 10px;font-variant-numeric:tabular-nums">${j.val ? `${j.val.map50.toFixed(3)} / ${j.val.map5095.toFixed(3)} <span style="color:var(--mut)">(P ${j.val.P.toFixed(2)} R ${j.val.R.toFixed(2)})</span>` : '<span style="color:var(--mut)">첫 검증 전</span>'}</td>` +
        `<td style="padding:3px 10px">${j.mem}</td></tr>`).join("") + `</tbody></table>` : "") +
    `<details><summary style="cursor:pointer;color:var(--mut)">러너 로그</summary>${lastLog || '<div style="color:var(--mut)">로그 없음</div>'}</details>`;
    if (open) qb.querySelector("details").open = true;
  };
  renderQueue(q);
  wrap.appendChild(qb);
  const tick = async () => {                       // 학습 중이면 30초마다 큐 상자만 갱신
    if (CUR.mode !== "results" || !document.body.contains(qb)) return;
    try { const q2 = await (await fetch("/api/queue")).json(); renderQueue(q2); if ((q2.jobs || []).length) window._resT = setTimeout(tick, 30000); } catch (e) {}
  };
  clearTimeout(window._resT); if ((q.jobs || []).length) window._resT = setTimeout(tick, 30000);

  const col = s => s >= 90 ? "#3fb950" : s >= 70 ? "#d29922" : "#f85149";
  const fmtT = m => { const d = new Date(m * 1000); return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  // 학습셋 id → 읽는 이름(장수). 큐 yaml 의 base/extras/oversample 표기용. 새 셋을 쓰면 여기 한 줄 추가
  const DS_NAME = {
    aihub71751_48k: "AI허브 71751 48k(클립당 12프레임)", aihub71751_24k: "AI허브 71751 24k", fasdd_yolo: "FASDD 9.5만", fasdd_snowfog: "FASDD 눈·안개 3,579",
    fasdd_snow2: "FASDD 눈 2차 351", wildfire_pos_yolo: "산불 양성 5.9만", wildfire_fog_neg: "산불 안개 배경 1.2만", dfire_yolo: "D-Fire 2.2만",
    azimjaan_yolo: "Azimjaan 1.1만", human_fire: "손라벨 사람+불 1,140",
  };
  const dsName = id => DS_NAME[id] || id;
  const sep = '<span style="color:var(--mut)"> · </span>';
  const confOf = d => {                              // 한 줄 구성: 모델 · 베이스 · +추가셋 · 오버샘플 · 추가 옵션
    const m = d.meta || {};
    if (m.kind === "live_sa") return '<b>라이브 SA 생성기</b>';
    if (m.kind === "archive") return '<span style="color:var(--mut)">보관 결과</span>';
    const parts = [];
    if (m.model) parts.push(`<b>${m.model}</b>`);
    if (m.base) parts.push(`베이스 ${dsName(m.base)}`);
    (m.extras || []).forEach(x => parts.push(`+ ${dsName(x)}`));
    if (m.oversample) Object.entries(m.oversample).forEach(([k, v]) => parts.push(`${dsName(k)} ×${v}`));
    if (m.extra && Object.keys(m.extra).length) parts.push(`<span style="color:#d29922">${Object.entries(m.extra).map(([k, v]) => k + "=" + v).join(" ")}</span>`);
    return parts.join(sep) || "–";
  };
  const resOf = d => {                               // 해상도: 학습 / 채점 측정. 다르면 둘 다 보인다
    const m = d.meta || {}, t = m.train || {};
    if (!m.model) return '<span style="color:var(--mut)">–</span>';
    const tr = t.imgsz || null, ev = (m.eval_map || {}).imgsz || null;
    if (!tr && !ev) return '<span style="color:var(--mut)">–</span>';
    if (tr && ev && tr !== ev) return `<b>${tr}</b><br><span style="color:#d29922;font-size:10px">측정 ${ev}</span>`;
    return `<b>${tr || ev}</b>`;
  };
  const dataOf = d => {                              // 입력 데이터: 베이스 + 추가 데이터셋
    const m = d.meta || {};
    if (!m.model) return "";
    const parts = [];
    if (m.base) parts.push(dsName(m.base));
    (m.extras || []).forEach(x => parts.push("+ " + dsName(x)));
    if (!parts.length) return '<span style="color:var(--mut)">–</span>';
    // 총 학습 장수는 데이터의 성질이라 여기 붙인다(오버샘플 반영 후 실제 목록 수)
    if (m.n_train) parts.push(`<span style="color:var(--mut)">(총 ${Number(m.n_train).toLocaleString()}장)</span>`);
    return parts.join("<br>");
  };
  const wayOf = d => {                               // 기법: 오버샘플·다중스케일·베이스 비율 등 데이터 외 조작
    const m = d.meta || {}, t = m.train || {};
    if (!m.model) return "";
    const parts = [];
    if (m.oversample) Object.entries(m.oversample).forEach(([k, v]) => parts.push(`${dsName(k)} ×${v}`));
    if (t.multi_scale) parts.push(`다중스케일 ${t.multi_scale}`);
    if (m.base_frac && m.base_frac < 1) parts.push(`베이스 ${Math.round(m.base_frac * 100)}%`);
    if (m.extra && Object.keys(m.extra).length)
      parts.push(`<span style="color:#d29922">${Object.entries(m.extra).map(([k, v]) => k + "=" + v).join(" ")}</span>`);
    return parts.join("<br>") || '<span style="color:var(--mut)">–</span>';
  };
  const trainOf = d => {                             // 학습 요약: 에폭·배치·크기 / 장수 / 상태
    const m = d.meta || {}, t = m.train || {};
    if (!m.model) return "";
    const a = [t.epochs ? `${t.epochs}에폭` : "", t.batch ? `배치 ${t.batch}` : "", t.imgsz ? `${t.imgsz}px` : ""].filter(Boolean).join(" · ");
    return a + (m.status && m.status !== "ok" ? `<br><span style="color:${/fail|kill|error/i.test(m.status) ? "#f85149" : "var(--mut)"}">${m.status}</span>` : "");
  };
  const HEAD = '<thead><tr style="color:var(--mut);text-align:left;font-size:11px"><th style="padding:8px 6px;width:64px" title="학습 입력 크기. 다르면 채점 측정 크기도 같이 표시">해상도</th><th>입력데이터</th><th title="오버샘플·다중스케일 등 데이터 외 조작">기법</th><th style="width:60px" title="이 레시피가 낸 최고 F1">최고 F1</th><th style="width:74px" title="최고 F1 을 낸 실험의 한 표본 처리시간(GPU) · 괄호는 표본 주기 대비 여유">속도</th><th style="width:96px">시각</th><th style="width:20px"></th></tr></thead>';
  const VC = { "정검": "#3fb950", "미검": "#f85149", "오검": "#d29922", "무GT": "#484f58" };

  ITEMS.forEach(item => {
    const raw = data.filter(d => d.item === item).sort((a, b) => b.score - a.score);
    // 해상도·입력데이터·기법이 같으면 한 레시피. 구성 기록이 없는 옛 결과는 이름으로 각각 둔다.
    const rgroup = {};
    raw.forEach(d => {
      const m = d.meta || {}, t = m.train || {};
      const key = m.model
        ? [t.imgsz || "", m.base || "", (m.extras || []).join(","),
           Object.entries(m.oversample || {}).sort().map(([k, v]) => k + ":" + v).join(","),
           t.multi_scale || "", m.base_frac || ""].join("|")
        : "solo|" + d.name;
      (rgroup[key] || (rgroup[key] = [])).push(d);
    });
    const rows = Object.values(rgroup).map(list => {
      list.sort((a, b) => b.score - a.score);
      const rep0 = list[0]; rep0._family = list; return rep0;
    }).sort((a, b) => b.score - a.score);
    const sec = el("div"); sec.style.cssText = "margin-top:18px";
    const st = el("div", "rtitle", `${item} <span class="tag">${rows.length}건</span>`); st.style.cssText = "font-size:14px;margin-bottom:6px";
    sec.appendChild(st);
    if (!rows.length) { sec.appendChild(el("div", "", '<div style="color:var(--mut);font-size:11px;padding:4px 2px">채점 결과 없음 (실험 대기)</div>')); wrap.appendChild(sec); return; }
    const best = Math.max.apply(null, rows.map(d => d.score));
    const tbl = el("table"); tbl.style.cssText = "width:100%;border-collapse:collapse;font-size:12px"; tbl.innerHTML = HEAD;
    const tb = el("tbody");
    rows.forEach(d => {
      const top = d.score === best, m = d.meta || {};
      const tr = el("tr"); tr.style.cssText = "border-top:1px solid var(--line);cursor:pointer" + (top ? ";background:#3fb95012" : "");
      tr.innerHTML =
        `<td style="padding:9px 6px;font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:${top ? 800 : 600}">${top ? "★ " : ""}${resOf(d)}</td>` +
        `<td style="font-size:11px;line-height:1.5">${(d.meta || {}).model ? dataOf(d) : ((d.meta || {}).kind ? confOf(d) : `<span style="color:var(--mut)" title="구성 기록이 없는 옛 실험(09-08 이전)">${d.name.replace(/_\d{8}$/, "")}</span>`)}</td>` +
        `<td style="font-size:11px;line-height:1.5">${wayOf(d)}</td>` +
        `<td style="font-weight:800;font-size:14px;color:${col(d.score)};font-variant-numeric:tabular-nums">${d.score.toFixed(2)}</td>` +
        (() => { const b = (d.meta || {}).bench || {};
          if (b.pt_gpu == null) return '<td style="color:var(--mut);text-align:center">–</td>';
          const h = b.headroom;
          return `<td style="text-align:center;font-variant-numeric:tabular-nums;font-size:11px;white-space:nowrap">${b.pt_gpu.toFixed(0)}ms` +
            (h == null ? "" : `<br><span style="color:${h < 1 ? "#f85149" : h < 2 ? "#d29922" : "var(--mut)"}">${h}배</span>`) + `</td>`; })() +
        `<td style="color:var(--mut);font-variant-numeric:tabular-nums;white-space:nowrap;font-size:11px">${fmtT(d.mtime)}</td>` +
        `<td style="color:var(--mut);user-select:none" title="구성 상세 · 규칙 스윕 전체">▸</td>`;
      tb.appendChild(tr);
      // 펼침: 구성 표(이름 → 뜻) + 규칙 스윕 표
      const expName = d.name + ((d._members || []).length > 1 ? ` 외 ${d._members.length - 1}건` : "");
      const fam = (d._family || [d]).slice().sort((a, b) => b.score - a.score);
      const H3 = t => `<div style="margin:10px 0 4px;font-weight:700;color:var(--tx)">${t}</div>`;


      // ---- 2. 모델별 성능 ----
      const famTbl = (fam[0].meta || {}).model
        ? H3("모델별 성능") +
          `<table style="border-collapse:collapse"><thead><tr style="color:var(--mut)">` +
          `<th style="text-align:left;padding:2px 8px">모델</th><th style="padding:2px 8px">배치</th>` +
          `<th style="padding:2px 8px">F1</th><th style="padding:2px 8px">mAP50</th>` +
          `<th style="padding:2px 8px">정검</th><th style="padding:2px 8px">미검</th><th style="padding:2px 8px">오검</th>` +
          `<th style="padding:2px 8px" title="한 표본 처리시간. 한 표본 = 그 항목이 주기마다 돌리는 뷰 전부">.pt GPU</th>` +
          `<th style="padding:2px 8px">.pt CPU</th>` +
          `<th style="padding:2px 8px">onnx GPU</th>` +
          `<th style="padding:2px 8px">onnx CPU</th>` +
          `<th style="padding:2px 8px" title="표본 주기 ÷ 가장 빠른 경로. 1 미만이면 실시간 불가">여유</th></tr></thead><tbody>` +
          fam.map(x => { const xm = x.meta || {}, xt = xm.train || {}, em = xm.eval_map;
            return `<tr data-pick="${x.name}" style="cursor:pointer${x === d ? ';background:#3fb95022' : ''}" title="이 모델의 규칙 스윕 보기">` +
              `<td style="padding:2px 8px"><b>${xm.model || "–"}</b></td>` +
              `<td style="text-align:center;color:var(--mut)">${xt.batch || "–"}</td>` +
              `<td style="text-align:center;font-weight:700;color:${col(x.score)}">${x.score.toFixed(2)}</td>` +
              `<td style="text-align:center">${em ? em.map50.toFixed(3) : "–"}</td>` +
              `<td style="text-align:center;color:#3fb950">${x.tp}</td>` +
              `<td style="text-align:center;color:#d29922">${x.fn}</td>` +
              `<td style="text-align:center;color:#f85149">${x.fp}</td>` +
              (() => { const b = xm.bench || {};
                const ms = v => v == null ? '<span style="color:var(--mut)">–</span>' : v.toFixed(0) + "ms";
                const h = b.headroom;
                return `<td style="text-align:center;font-variant-numeric:tabular-nums">${ms(b.pt_gpu)}</td>` +
                  `<td style="text-align:center;font-variant-numeric:tabular-nums">${ms(b.pt_cpu)}</td>` +
                  `<td style="text-align:center;font-variant-numeric:tabular-nums">${ms(b.onnx_gpu)}</td>` +
                  `<td style="text-align:center;font-variant-numeric:tabular-nums">${ms(b.onnx_cpu)}</td>` +
                  `<td style="text-align:center;font-weight:700;color:${h == null ? "var(--mut)" : h < 1 ? "#f85149" : h < 2 ? "#d29922" : "#3fb950"}">${h == null ? "–" : h + "배"}</td>`; })() +
              `</tr>`; }).join("") +
          `</tbody></table>` : "";

      // ---- 3. 규칙 스윕: 고른 모델 기준. 기본 규칙 대비 증감을 같이 보여준다 ----
      const detailOf = (x) => {
        const xm = x.meta || {}, rules = x.rules || [];
        if (rules.length < 2) return "";
        return H3("규칙 스윕") +
          `<table style="border-collapse:collapse"><thead><tr style="color:var(--mut)">` +
          `<th style="text-align:left;padding:2px 8px">규칙</th><th style="padding:2px 8px">F1</th>` +
          `<th style="padding:2px 8px">정검</th>` +
          `<th style="padding:2px 8px">미검</th><th style="padding:2px 8px">오검</th></tr></thead><tbody>` +
          rules.map(r => { const on = r.rule === x.rule;
            return `<tr${on ? ' style="background:#3fb95022"' : ''}>` +
              `<td style="padding:2px 8px">${on ? "▸ " : ""}${r.rule}</td>` +
              `<td style="text-align:center;font-weight:700;color:${col(r.score)}">${r.score.toFixed(2)}</td>` +
              `<td style="text-align:center;color:#3fb950">${r.tp}</td>` +
              `<td style="text-align:center;color:#d29922">${r.fn}</td>` +
              `<td style="text-align:center;color:#f85149">${r.fp}</td></tr>`; }).join("") +
          `</tbody></table>`;
      };

      const sub = el("tr"); sub.hidden = true;
      sub.innerHTML = `<td colspan="7" style="padding:6px 14px 14px;font-size:11px">` + famTbl + `<div id="det_${d.name}">${detailOf(d)}</div>` +
        `</td>`;
      tb.appendChild(sub);
      sub.querySelectorAll("tr[data-pick]").forEach(rowEl => {          // 모델 행 클릭 → 그 모델 상세로 교체
        rowEl.onclick = ev => {
          ev.stopPropagation();
          const picked = fam.find(x => x.name === rowEl.dataset.pick);
          if (!picked) return;
          sub.querySelector("#det_" + d.name).innerHTML = detailOf(picked);
          sub.querySelectorAll("tr[data-pick]").forEach(r2 => r2.style.background = "");
          rowEl.style.background = "#3fb95022";
        };
      });
      tr.onclick = () => { sub.hidden = !sub.hidden; tr.lastElementChild.textContent = sub.hidden ? "▸" : "▾"; };
    });
    tbl.appendChild(tb); sec.appendChild(tbl);
    if (item === "방화") {                              // 이 항목 표에 나온 학습셋 이름 풀이
      const used = [...new Set(rows.flatMap(d => [(d.meta || {}).base, ...((d.meta || {}).extras || []), ...Object.keys((d.meta || {}).oversample || {})]).filter(Boolean))];
      if (used.length) sec.appendChild(el("div", "", `<div style="color:var(--mut);font-size:10px;margin-top:6px;line-height:1.6">학습셋: ${used.map(u => `<b style="color:var(--tx);font-weight:600">${u}</b> = ${dsName(u)}`).join(" · ")}</div>`));
    }
    // ---- 클립 × 실험 히트맵: 어떤 클립을 늘 놓치는지 (score_kisa 클립별 판정이 있는 실험만) ----
    const withClips = rows.filter(d => d.clips && Object.keys(d.clips).length);
    if (withClips.length) {
      const clips = [...new Set(withClips.flatMap(d => Object.keys(d.clips)))].sort();
      const hm = el("table"); hm.style.cssText = "border-collapse:collapse;font-size:11px;margin-top:10px";
      hm.innerHTML = `<thead><tr style="color:var(--mut)"><th style="text-align:left;padding:4px 6px">클립별 판정(최고 규칙)</th>${clips.map(cn => `<th style="padding:4px 5px;font-weight:600;writing-mode:vertical-rl;transform:rotate(180deg);white-space:nowrap">${cn.replace(/^C00_/, "")}</th>`).join("")}<th style="padding:4px 6px;color:var(--mut)">미검</th></tr></thead>`;
      const hb = el("tbody");
      withClips.forEach(d => {
        const tr = el("tr"); tr.style.cssText = "border-top:1px solid var(--line)";
        let miss = 0;
        tr.innerHTML = `<td style="padding:4px 6px;font-weight:600;white-space:nowrap">${d.name.replace(/_\d{8}$/, "")}</td>` + clips.map(cn => {
          const v = d.clips[cn] || ""; const k = v.startsWith("정검") ? "정검" : v.startsWith("미검") ? "미검" : v.startsWith("오검") ? "오검" : v ? "무GT" : "";
          if (k === "미검") miss++;
          return `<td title="${cn}: ${v || "없음"}" style="width:22px;height:20px;text-align:center;background:${k ? VC[k] + (k === "무GT" ? "" : "cc") : "transparent"};color:#06090f;font-weight:800;font-size:10px">${k === "정검" ? "○" : k === "미검" ? "✕" : k === "오검" ? "!" : k ? "·" : ""}</td>`;
        }).join("") + `<td style="padding:4px 6px;color:#f85149;font-weight:800">${miss}</td>`;
        hb.appendChild(tr);
      });
      hm.appendChild(hb);
      const hw = el("div"); hw.style.cssText = "overflow-x:auto"; hw.appendChild(hm); sec.appendChild(hw);
      sec.appendChild(el("div", "", '<div style="color:var(--mut);font-size:10px;margin-top:4px">○ 정검 · ✕ 미검 · ! 오검(GT 없는 클립) · 열 전체가 ✕인 클립 = 데이터/규칙으로 풀어야 할 병목</div>'));
    }
    wrap.appendChild(sec);
  });
  wrap.appendChild(el("div", "", '<div style="color:var(--mut);font-size:11px;margin-top:16px;line-height:1.7">· 점수 = KISA 배포 검증영상 F1(규칙 스윕 중 최고). 초록 ≥90 · 노랑 ≥70 · 빨강 70미만 · 행을 누르면 구성 상세와 규칙 스윕 전체<br>· 방화 = 러너 실험(exp_queue.py) · 침입·배회·쓰러짐 = 라이브 SA 생성기 채점 로그(val_*.log) + 09-07 정리본(ALL_RESULTS.json)<br>· 시각은 전부 한국 시간(KST)</div>'));
  c.innerHTML = ""; c.appendChild(wrap);
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
  try { DATASETS = await (await fetch("/api/datasets")).json(); } catch (e) { DATASETS = {}; }   // 데이터 규격(카테고리별 mode·gt·use)
  for (const [k, v] of Object.entries(META.items)) v.rows.forEach(row => row.item = k);
  const last = (typeof loadSession === "function") ? loadSession() : {};
  if (last.mode === "data" || last.mode === "review" || last.mode === "results") CUR.mode = last.mode;
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
