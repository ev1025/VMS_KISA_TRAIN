# -*- coding: utf-8 -*-
"""헤더(결과 탭 오른쪽)에 전파 작업 상태를 전역으로 표시: 진행 중 클립·%·대기 수. 2초마다 갱신, 없으면 숨김. 클릭하면 그 클립으로 이동(목록에 있으면)."""
import io
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/"
def patch(name, pairs):
    p = V + name; s = io.open(p, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, (name, s.count(old), old[:90])
        s = s.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8").write(s); print(name, "ok")

patch("dashboard.html", [
    (""" <div class="mode" id="modeBox"></div>
""", """ <div class="mode" id="modeBox"></div>
 <span id="jobStat" hidden style="margin-left:14px;font-size:12px;color:var(--tx);display:inline-flex;align-items:center;gap:8px;cursor:pointer"></span>
"""),
])
patch("js/main.js", [
    ("""async function boot() {""",
     """// 전파 작업 전역 표시(헤더). 서버 큐를 2초마다 조회
let _JOBS_T = null;
async function pollJobs() {
  const box = $("#jobStat"); if (!box) return;
  let jobs = [];
  try { jobs = await (await fetch("/api/sam2_jobs")).json(); } catch (e) { jobs = []; }
  const run = jobs.filter(j => j.state === "running"), q = jobs.filter(j => j.state === "queued");
  if (!run.length && !q.length) { box.hidden = true; box.innerHTML = ""; return; }
  const spin = '<span style="display:inline-block;width:11px;height:11px;border:2px solid #58a6ff55;border-top-color:#58a6ff;border-radius:50%;animation:ed_sp .8s linear infinite"></span>';
  if (!document.getElementById("ed_sp")) { const st = document.createElement("style"); st.id = "ed_sp"; st.textContent = "@keyframes ed_sp{to{transform:rotate(360deg)}}"; document.head.appendChild(st); }
  const parts = run.map(j => `<b>${j.clip}</b> ${j.total ? Math.min(99, Math.round(j.done / j.total * 100)) : 0}%`);
  if (q.length) parts.push(`<span style="color:var(--mut)">대기 ${q.length}</span>`);
  box.innerHTML = spin + `<span>전파 ${parts.join(" · ")}</span>`;
  box.hidden = false;
  box.onclick = () => {                              // 진행 중 클립으로 이동(원본 데이터 목록에 있을 때)
    const j = run[0] || q[0]; if (!j) return;
    const it = [...document.querySelectorAll("#list .item")].find(e => (e.dataset.rel || "").split("/").pop().replace(/\\.mp4$/, "") === j.clip);
    if (it) it.click();
  };
}
function startJobPoll() { if (_JOBS_T) return; pollJobs(); _JOBS_T = setInterval(pollJobs, 2000); }
async function boot() {
  startJobPoll();"""),
])
